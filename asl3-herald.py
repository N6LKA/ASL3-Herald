#!/usr/bin/python3
"""
asl3-herald - Enhanced Tail Message & Announcement Daemon for ASL3/app_rpt
https://github.com/N6LKA/asl3-herald

Replaces and enhances the native app_rpt tail message function with reliable
unkey detection, rotating messages, SkywarnPlus WX integration, and scheduled
announcements.
"""

import os
import re
import sys
import time
import json
import signal
import socket
import argparse
import subprocess
import traceback
import configparser
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: sudo apt install python3-yaml", flush=True)
    sys.exit(1)

# ── Paths ─────────────────────────────────────────────────────────────────────

INSTALL_DIR  = "/etc/asterisk/scripts/asl3-herald"
CONF_FILE    = os.path.join(INSTALL_DIR, "asl3-herald.conf")
STATE_FILE   = os.path.join(INSTALL_DIR, "asl3-herald.state")
DISABLE_FLAG = os.path.join(INSTALL_DIR, "asl3-herald-disabled")
ANNOUNCE_DIR = os.path.join(INSTALL_DIR, "announcements")

# Pre-recorded sound snippets (digits, greetings, condition words) shared with
# Time-Weather-Announce and other ASL3 programs — installed by install.sh.
TW_SOUND_BASE   = "/usr/local/share/asterisk/sounds/custom"
TW_COORD_CACHE  = os.path.join(INSTALL_DIR, "timeweather-coords.cache")
TW_TEMP_OUTDIR  = "/tmp"
SWP_WEATHER_FILE = "/tmp/SkywarnPlus/swp-data.json"
DEFAULT_TW_CRON = "0 * * * *"
DEFAULT_TW_WEATHER_CACHE_MIN = 10

try:
    with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "version.txt")) as _vf:
        VERSION = _vf.read().strip()
except FileNotFoundError:
    VERSION = "unknown"

DEBUG = False

# Fallback estimate (seconds) for how long a scheduled announcement's audio
# takes to play, used only if `soxi` can't determine the real duration.
DEFAULT_ANNOUNCEMENT_DURATION = 8.0
BUSY_GRACE_SECONDS = 1.5
# Hard ceiling on how long a single scheduled announcement can hold off tail
# messages — a corrupt file or bad soxi reading must never wedge playback silent.
MAX_BUSY_SECONDS = 60.0

# How many playback events to keep in state["playback_history"].
MAX_PLAYBACK_HISTORY = 200

# Fixed internal poll interval — replaces the old user-configured PollInterval.
# AMI connections are persistent sockets so 0.5s polling has negligible CPU cost
# even on a Raspberry Pi; it also gives faster unkey-to-play response than the
# previous 1s subprocess-based poll.
POLL_INTERVAL = 0.5

# ── AMI state (module-level, refreshed every POLL_INTERVAL by main()) ─────────
# These are read by node_is_keyed() so scheduled-announcement gating always
# reflects the most recent poll without making extra AMI calls.

_ami_rx_keyed   = False  # RPT_RXKEYED from XStat (local RF receiving)
_ami_conn_keyed = False  # any Conn PTT=1 from SawStat (network audio active)
_ami_up         = False  # True when AMI is available and last poll succeeded

# ── AMI connection ────────────────────────────────────────────────────────────

class AmiConn:
    """
    Minimal synchronous Asterisk Manager Interface client.
    Supports the RptStatus XStat and SawStat commands used for keyup detection.
    """

    def __init__(self, host, port, user, secret):
        self._host   = host
        self._port   = int(port)
        self._user   = user
        self._secret = secret
        self._sock   = None

    def connect(self):
        """Open connection and authenticate. Returns True on success."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((self._host, self._port))

            # Read the AMI banner (single line ending \r\n, not \r\n\r\n)
            banner = b""
            while not banner.endswith(b"\r\n"):
                chunk = s.recv(256)
                if not chunk:
                    raise ConnectionError("Connection closed reading banner")
                banner += chunk

            if b"Asterisk Call Manager" not in banner:
                raise ConnectionError(f"Unexpected banner: {banner!r}")

            self._sock = s
            resp = self._action([
                "ACTION: LOGIN",
                f"USERNAME: {self._user}",
                f"SECRET: {self._secret}",
                "EVENTS: 0",
            ])
            if "Response: Success" not in resp:
                raise ConnectionError(f"AMI login failed: {resp!r}")
            return True

        except Exception as e:
            log_warn(f"AMI connect failed: {e}")
            self.close()
            return False

    def _action(self, lines):
        """Send an AMI action block and read the response (ends with \\r\\n\\r\\n)."""
        if self._sock is None:
            raise ConnectionError("Not connected to AMI")
        cmd = "\r\n".join(lines) + "\r\n\r\n"
        self._sock.sendall(cmd.encode("utf-8"))
        buf = b""
        while not buf.endswith(b"\r\n\r\n"):
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("AMI connection closed mid-response")
            buf += chunk
        return buf.decode("utf-8", errors="replace")

    def xstat(self, node):
        """
        Query XStat for RPT_RXKEYED / RPT_TXKEYED state.
        Returns dict with boolean RXKEYED, TXKEYED, TXEKEYED keys.
        """
        resp = self._action([
            "ACTION: RptStatus",
            "COMMAND: XStat",
            f"NODE: {node}",
        ])
        result = {"RXKEYED": False, "TXKEYED": False, "TXEKEYED": False}
        for line in resp.splitlines():
            line = line.strip()
            if line == "Var: RPT_RXKEYED=1":
                result["RXKEYED"] = True
            elif line == "Var: RPT_TXKEYED=1":
                result["TXKEYED"] = True
            elif line == "Var: RPT_TXEKEYED=1":
                result["TXEKEYED"] = True
        return result

    def sawstat(self, node):
        """
        Query SawStat for per-connected-node PTT state.
        Returns dict with CONNKEYED (bool) and CONNKEYEDNODE (str or None).
        """
        resp = self._action([
            "ACTION: RptStatus",
            "COMMAND: SawStat",
            f"NODE: {node}",
        ])
        result = {"CONNKEYED": False, "CONNKEYEDNODE": None}
        for line in resp.splitlines():
            line = line.strip()
            if line.startswith("Conn:"):
                # Conn: NODE PTT SEC_SINCE_KEY SEC_SINCE_UNKEY
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        if int(parts[2]) == 1:
                            result["CONNKEYED"] = True
                            result["CONNKEYEDNODE"] = parts[1]
                    except (ValueError, IndexError):
                        pass
        return result

    def close(self):
        """Attempt a clean logoff then close the socket."""
        try:
            if self._sock:
                self._sock.sendall(b"ACTION: Logoff\r\n\r\n")
        except Exception:
            pass
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass
        self._sock = None

# ── AMI credential discovery ──────────────────────────────────────────────────

def load_ami_credentials():
    """
    Read AMI host/port/user/secret from the system — never from asl3-herald.conf.
    Tries /etc/allmon3/allmon3.ini first (preferred: already configured if
    Allmon3 is installed and stays in sync automatically when Allmon3 changes).
    Falls back to /etc/asterisk/manager.conf.
    Returns (host, port, user, secret) or (None, None, None, None) if not found.
    """
    allmon3_ini = "/etc/allmon3/allmon3.ini"
    if os.path.exists(allmon3_ini):
        try:
            cp = configparser.ConfigParser()
            cp.read(allmon3_ini)
            for section in cp.sections():
                user   = cp.get(section, "user", fallback=None)
                secret = cp.get(section, "pass", fallback=None)
                if user and secret:
                    host = cp.get(section, "host", fallback="127.0.0.1")
                    # "localhost" → loopback; any non-loopback bind is unusual
                    # but we leave it as-is and let the connect attempt fail with
                    # a clear error if it can't reach the AMI port.
                    if host.lower() == "localhost":
                        host = "127.0.0.1"
                    port = cp.getint(section, "port", fallback=5038)
                    return host, port, user, secret
        except Exception as e:
            log_warn(f"Could not parse {allmon3_ini}: {e}")

    manager_conf = "/etc/asterisk/manager.conf"
    if os.path.exists(manager_conf):
        try:
            cp = configparser.ConfigParser()
            cp.read(manager_conf)
            host = cp.get("general", "bindaddr", fallback="127.0.0.1")
            if host in ("0.0.0.0", "::"):
                host = "127.0.0.1"
            port = cp.getint("general", "port", fallback=5038)
            for section in cp.sections():
                if section.lower() == "general":
                    continue
                secret = cp.get(section, "secret", fallback=None)
                if secret:
                    return host, port, section, secret
        except Exception as e:
            log_warn(f"Could not parse {manager_conf}: {e}")

    return None, None, None, None

# ── Logging ───────────────────────────────────────────────────────────────────

def log(level, msg):
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [{level}] {msg}", flush=True)

def log_info(msg):  log("INFO",  msg)
def log_warn(msg):  log("WARN",  msg)
def log_error(msg): log("ERROR", msg)
def log_debug(msg):
    if DEBUG:
        log("DEBUG", msg)

# ── Config ────────────────────────────────────────────────────────────────────

def load_config():
    if not os.path.exists(CONF_FILE):
        log_error(f"Config not found: {CONF_FILE}")
        sys.exit(1)
    with open(CONF_FILE) as f:
        return yaml.safe_load(f)

def save_config(config):
    # NOTE: round-trips through PyYAML — does not preserve comments.
    with open(CONF_FILE, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

# ── State ─────────────────────────────────────────────────────────────────────

def load_state():
    defaults = {
        "rotation_index": 0,
        "last_tail_played": 0.0,
        "scheduled_played": {},
        "scheduled_pending": {},
        "scheduled_busy_until": 0.0,
        "swp_last_mtime": None,
        "swp_next_is_rotation": False,
        "playback_history": [],
        "timeweather_played": None,
        "timeweather_pending": False,
        "timeweather_busy_until": 0.0,
        "timeweather_weather_cache": None,
        "timeweather_tempest_station": None,
    }
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                defaults.update(json.load(f))
    except Exception:
        pass
    return defaults

def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log_error(f"Failed to save state: {e}")

# ── Asterisk ──────────────────────────────────────────────────────────────────

def asterisk_cmd(cmd):
    try:
        r = subprocess.run(
            ["/usr/sbin/asterisk", "-rx", cmd],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip()
    except Exception as e:
        log_error(f"asterisk cmd failed ({cmd}): {e}")
        return ""

def asterisk_available():
    return "Asterisk" in asterisk_cmd("core show version")

def node_is_keyed(node):
    """
    Returns True if the node is currently keyed (receiving audio from any source),
    False if idle, or None if the state cannot be determined.

    When AMI is active (_ami_up), uses the module-level cache populated by the
    most recent poll cycle — both local RF (RPT_RXKEYED) and active network audio
    (any connected node with PTT=1) count as "keyed" for scheduled-announcement
    gating. Falls back to the `rpt stats` CLI on Signal-on-input when AMI is
    unavailable (local RF only, same as pre-AMI behavior).
    """
    global _ami_up, _ami_rx_keyed, _ami_conn_keyed
    if _ami_up:
        return _ami_rx_keyed or _ami_conn_keyed
    # CLI fallback — local RF only
    out = asterisk_cmd(f"rpt stats {node}")
    for line in out.splitlines():
        if "Signal on input" in line:
            return line.split(":")[-1].strip().upper().startswith("YES")
    return None

def audio_duration(filepath):
    try:
        r = subprocess.run(["soxi", "-D", filepath], capture_output=True, text=True, timeout=5)
        duration = float(r.stdout.strip())
        if duration <= 0 or duration > 300:
            return None
        return duration
    except Exception:
        return None

def play_file(node, filepath, play_mode="local"):
    path_no_ext = str(Path(filepath).with_suffix(""))
    cmd = "rpt playback" if play_mode == "global" else "rpt localplay"
    log_info(f"Playing ({play_mode}): {Path(filepath).name} on node {node}")
    asterisk_cmd(f"{cmd} {node} {path_no_ext}")

# ── Helpers ───────────────────────────────────────────────────────────────────

def rotation_entry_file(entry):
    return entry if isinstance(entry, str) else entry.get("File", "")

def wx_is_active(wx_file, threshold):
    if not wx_file or not os.path.exists(wx_file):
        return False
    return os.path.getsize(wx_file) > threshold

def week_of_month_range(week):
    low = (week - 1) * 7 + 1
    high = 31 if week == 5 else low + 6
    return low, high

def cron_field_matches(field, value):
    field = str(field).strip()
    if field == "*":
        return True
    for part in field.split(","):
        part = part.strip()
        if "/" in part:
            base, step = part.split("/", 1)
            try:
                step = int(step)
                start = 0 if base == "*" else int(base)
                if value >= start and (value - start) % step == 0:
                    return True
            except ValueError:
                pass
        elif "-" in part:
            lo, hi = part.split("-", 1)
            try:
                if int(lo) <= value <= int(hi):
                    return True
            except ValueError:
                pass
        else:
            try:
                if int(part) == value:
                    return True
            except ValueError:
                pass
    return False

def cron_matches(expr, now):
    parts = str(expr or "").split()
    if len(parts) != 5:
        return False
    cron_min, cron_hour, cron_dom, cron_mon, cron_dow = parts
    dow_val = now.isoweekday() % 7  # Sun=0, Mon=1, ..., Sat=6
    return (
        cron_field_matches(cron_min,  now.minute) and
        cron_field_matches(cron_hour, now.hour)   and
        cron_field_matches(cron_dom,  now.day)    and
        cron_field_matches(cron_mon,  now.month)  and
        cron_field_matches(cron_dow,  dow_val)
    )

_DAY_TO_DOW = {
    "sunday": 0, "monday": 1, "tuesday": 2, "wednesday": 3,
    "thursday": 4, "friday": 5, "saturday": 6,
}

def legacy_to_cron(sched):
    """Convert legacy Time/Days/Week fields to a 5-field cron expression."""
    time_str = sched.get("Time", "00:00") or "00:00"
    try:
        hh, mm = str(time_str).split(":")
        hour, minute = int(hh), int(mm)
    except (ValueError, AttributeError):
        hour, minute = 0, 0

    days = sched.get("Days", "daily")
    if not days or days == "daily":
        dow_field = "*"
    else:
        day_list = days if isinstance(days, list) else [days]
        nums = [str(_DAY_TO_DOW[d.lower()]) for d in day_list if d.lower() in _DAY_TO_DOW]
        dow_field = ",".join(nums) if nums else "*"

    week = sched.get("Week")
    if week:
        try:
            low, high = week_of_month_range(int(week))
            dom_field = f"{low}-{high}"
        except (TypeError, ValueError):
            dom_field = "*"
    else:
        dom_field = "*"

    return f"{minute} {hour} {dom_field} * {dow_field}"

def sched_cron_expr(sched):
    """Return the cron expression for a scheduled entry, converting legacy fields if needed."""
    cron = sched.get("Cron")
    return cron if cron else legacy_to_cron(sched)

def entry_days_ok(entry, now):
    days = entry.get("Days") if isinstance(entry, dict) else None
    if not days or days == "daily":
        return True
    day_list = [d.lower() for d in (days if isinstance(days, list) else [days])]
    return now.strftime("%A").lower() in day_list

def entry_time_window_ok(entry, now):
    if not isinstance(entry, dict):
        return True
    start = entry.get("TimeStart")
    end   = entry.get("TimeEnd")
    if not start and not end:
        return True
    hhmm = now.strftime("%H:%M")
    if start and end:
        if start <= end:
            return start <= hhmm <= end
        return hhmm >= start or hhmm <= end
    if start:
        return hhmm >= start
    return hhmm <= end

def rotation_entry_eligible(entry, now):
    if isinstance(entry, dict) and not entry.get("Enabled", True):
        return False
    if not entry_days_ok(entry, now):
        return False
    if not entry_time_window_ok(entry, now):
        return False
    return True

def rotation_entry_node(entry, node):
    entry_node = entry.get("Node") if isinstance(entry, dict) else None
    return str(entry_node) if entry_node else node

def log_playback(state, entry_type, name, filepath, node, play_mode="local"):
    history = state.setdefault("playback_history", [])
    history.append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": entry_type,
        "name": name,
        "file": os.path.basename(filepath) if filepath else "",
        "node": node,
        "play_mode": play_mode,
    })
    state["playback_history"] = history[-MAX_PLAYBACK_HISTORY:]

def should_play_scheduled(sched, state, node, now):
    if not sched.get("Enabled", True):
        return False

    name = sched.get("Name", "")
    minute_key = now.strftime("%Y-%m-%d %H:%M")

    if state["scheduled_played"].get(name) == minute_key:
        return False

    already_pending = name in state["scheduled_pending"]
    if not already_pending and not cron_matches(sched_cron_expr(sched), now):
        return False

    filepath = sched.get("File", "")
    if not filepath or not os.path.exists(filepath):
        log_warn(f"Scheduled file not found: {filepath}  ({name})")
        return False

    # Hourly Time & Weather takes priority over Scheduled Announcements when
    # both are due at the same moment — same pending/retry pattern as the
    # keyed-node case below, so the scheduled entry plays right after T&W
    # finishes instead of being skipped outright.
    if now.timestamp() < state.get("timeweather_busy_until", 0):
        if not already_pending:
            state["scheduled_pending"][name] = minute_key
            log_info(f"Scheduled announcement '{name}' due but Time & Weather is playing - waiting")
        else:
            log_debug(f"Scheduled announcement '{name}' still waiting on Time & Weather")
        return False

    entry_node = sched.get("Node")
    target_node = str(entry_node) if entry_node else node
    keyed = node_is_keyed(target_node)

    if keyed:
        if not already_pending:
            state["scheduled_pending"][name] = minute_key
            log_info(f"Scheduled announcement '{name}' due but node {target_node} is keyed - waiting for unkey")
        else:
            log_debug(f"Scheduled announcement '{name}' still waiting for unkey")
        return False

    if already_pending:
        state["scheduled_pending"].pop(name, None)

    return True

# ── Hourly Time & Weather ──────────────────────────────────────────────────────
# Ported from Time-Weather-Announce (saytime.pl / weather.sh) into native
# Python so weather fetch + audio assembly live in one process/language with
# the rest of the daemon, instead of shelling out to a second script.

# Antarctic/remote research-station and island locations with no postal code —
# ported verbatim from weather.sh's get_special_coordinates().
_TW_SPECIAL_COORDS = {
    "SOUTHPOLE": (-90.0, 0.0), "MCMURDO": (-77.85, 166.67), "PALMER": (-64.77, -64.05),
    "VOSTOK": (-78.46, 106.84), "CASEY": (-66.28, 110.53), "MAWSON": (-67.60, 62.87),
    "DAVIS": (-68.58, 77.97), "SCOTTBASE": (-77.85, 166.76), "SYOWA": (-69.00, 39.58),
    "CONCORDIA": (-75.10, 123.33), "HALLEY": (-75.58, -26.66), "DUMONT": (-66.66, 140.01),
    "SANAE": (-71.67, -2.84), "ALERT": (82.50, -62.35), "EUREKA": (79.99, -85.93),
    "THULE": (76.53, -68.70), "LONGYEARBYEN": (78.22, 15.65), "BARROW": (71.29, -156.79),
    "RESOLUTE": (74.72, -94.83), "GRISE": (76.42, -82.90), "ASCENSION": (-7.95, -14.36),
    "STHELENA": (-15.97, -5.72), "TRISTAN": (-37.11, -12.28), "BOUVET": (-54.42, 3.38),
    "HEARD": (-53.10, 73.51), "KERGUELEN": (-49.35, 70.22), "CROZET": (-46.43, 51.86),
    "AMSTERDAM": (-37.83, 77.57), "MACQUARIE": (-54.62, 158.86), "MIDWAY": (28.21, -177.38),
    "WAKE": (19.28, 166.65), "JOHNSTON": (16.73, -169.53), "PALMYRA": (5.89, -162.08),
    "JARVIS": (-0.37, -159.99), "HOWLAND": (0.81, -176.62), "BAKER": (0.19, -176.48),
    "KINGMAN": (6.38, -162.42), "DIEGO": (-7.26, 72.40), "CHAGOS": (-7.26, 72.40),
    "COCOS": (-12.19, 96.83), "CHRISTMAS": (-10.49, 105.62), "FALKLANDS": (-51.70, -59.52),
    "SOUTHGEORGIA": (-54.28, -36.51), "SOUTHSANDWICH": (-59.43, -26.35),
    "MARQUESAS": (-9.00, -140.00), "EASTER": (-27.11, -109.36), "PITCAIRN": (-25.07, -130.10),
    "CLIPPERTON": (10.30, -109.22), "GALAPAGOS": (-0.95, -90.97), "MAUNA": (19.54, -155.58),
    "JUNGFRAUJOCH": (46.55, 7.98), "MCMURDODRY": (-77.85, 163.00), "ATACAMA": (-24.50, -69.25),
    "GOUGH": (-40.35, -9.88), "MARION": (-46.88, 37.86), "PRINCE": (-46.88, 37.86),
    "CAMPBELL": (-52.55, 169.15), "AUCKLAND": (-50.73, 166.09), "KERMADEC": (-29.25, -177.92),
    "CHATHAM": (-43.95, -176.55),
}

# Canadian FSA (first 3 chars of postal code) -> nearest major city, used only
# as a fallback when Nominatim's direct postal-code lookup fails.
_TW_CANADIAN_FSA_CITY = {
    "N7L": "Chatham-Kent, Ontario", "N7M": "Sarnia, Ontario", "N7T": "Sarnia, Ontario",
    "N1G": "Guelph, Ontario", "N1H": "Guelph, Ontario", "N1K": "Guelph, Ontario", "N1L": "Guelph, Ontario",
    "N3C": "Cambridge, Ontario", "N3E": "Cambridge, Ontario", "N3H": "Cambridge, Ontario",
    "N2C": "Kitchener, Ontario", "N2E": "Kitchener, Ontario", "N2G": "Kitchener, Ontario",
    "N2H": "Kitchener, Ontario", "N2J": "Kitchener, Ontario", "N2K": "Kitchener, Ontario",
    "N2L": "Kitchener, Ontario", "N2M": "Kitchener, Ontario", "N2N": "Kitchener, Ontario",
    "N2P": "Kitchener, Ontario", "N2R": "Kitchener, Ontario",
}
for _fsa in ("N6A", "N6B", "N6C", "N6E", "N6G", "N6H", "N6J", "N6K"):
    _TW_CANADIAN_FSA_CITY[_fsa] = "London, Ontario"
for _fsa in ("N8A", "N8H", "N8N", "N8P", "N8R", "N8S", "N8T", "N8V", "N8W", "N8X", "N8Y",
             "N9A", "N9B", "N9C", "N9E", "N9G", "N9H", "N9J", "N9K", "N9Y"):
    _TW_CANADIAN_FSA_CITY[_fsa] = "Windsor, Ontario"
_TW_CANADIAN_FSA_PREFIX = {
    "M": "Toronto, Ontario", "V": "Vancouver, British Columbia", "H": "Montreal, Quebec",
    "T": "Calgary, Alberta", "R": "Winnipeg, Manitoba", "K": "Ottawa, Ontario",
    "L": "Mississauga, Ontario", "N": "London, Ontario", "P": "Thunder Bay, Ontario",
    "S": "Regina, Saskatchewan", "E": "Moncton, New Brunswick", "B": "Halifax, Nova Scotia",
}

def tw_is_icao_code(loc):
    return bool(re.fullmatch(r"[A-Z]{4}", loc.upper()))

def tw_is_special_location(loc):
    return loc.upper().replace(" ", "") in _TW_SPECIAL_COORDS

def tw_special_coordinates(loc):
    return _TW_SPECIAL_COORDS.get(loc.upper().replace(" ", ""))

def tw_canadian_fsa_city(fsa):
    fsa = fsa.upper()
    if fsa in _TW_CANADIAN_FSA_CITY:
        return _TW_CANADIAN_FSA_CITY[fsa]
    return _TW_CANADIAN_FSA_PREFIX.get(fsa[0])

def tw_http_get(url, timeout=10):
    """GET a URL and return the response body as text, or None on any failure."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "asl3-herald/{} (github.com/N6LKA/asl3-herald)".format(VERSION),
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        log_debug(f"HTTP GET failed ({url}): {e}")
        return None

def tw_http_get_json(url, timeout=10):
    text = tw_http_get(url, timeout=timeout)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None

# ── Condition-word mapping (drives which pre-recorded audio snippet plays) ────

def tw_metar_condition_word(metar_text):
    m = metar_text or ""
    if re.search(r"(\+|-)?TS", m):
        return "thunderstorm"
    if re.search(r"FZRA|FZDZ|\+RA|-RA|RA", m):
        return "rain"
    if re.search(r"SN", m):
        return "snow"
    if re.search(r"PL", m):
        return "hail"
    if re.search(r"FG", m):
        return "fog"
    if re.search(r"BR|HZ|FU|DU|SA", m):
        return "mist"
    if re.search(r"OVC|BKN|SCT", m):
        return "cloudy"
    return "clear"

def tw_openmeteo_condition_word(code, is_day=True):
    code = int(code) if code is not None else 0
    if code == 0:
        return "clear"
    if code in (1, 2):
        return "sunny" if is_day else "clear"
    if code == 3:
        return "cloudy"
    if code in (45, 48):
        return "fog"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if code in (95, 96, 99):
        return "thunderstorm"
    return "clear"

def tw_text_condition_word(text):
    """Map a free-text condition description (Tempest's `conditions` string,
    or SkywarnPlus's passthrough condition text) to our fixed audio vocabulary."""
    c = (text or "").lower()
    if "thunderstorm" in c or "thunder" in c:
        return "thunderstorm"
    if "drizzle" in c or "rain" in c:
        return "rain"
    if "snow" in c or "sleet" in c or "blizzard" in c:
        return "snow"
    if "hail" in c:
        return "hail"
    if "fog" in c or "mist" in c:
        return "fog"
    if "partly" in c and "cloud" in c:
        return "partly cloudy"
    if "cloud" in c or "overcast" in c:
        return "cloudy"
    if "sunny" in c or "clear" in c or "fair" in c:
        return "clear"
    return None if not c else "clear"

# ── Coordinate resolution (Open-Meteo needs lat/lon, not a postal code) ───────

def _tw_load_coord_cache():
    try:
        with open(TW_COORD_CACHE) as f:
            return json.load(f)
    except Exception:
        return {}

def _tw_save_coord_cache(cache):
    try:
        os.makedirs(os.path.dirname(TW_COORD_CACHE), exist_ok=True)
        with open(TW_COORD_CACHE, "w") as f:
            json.dump(cache, f)
    except Exception as e:
        log_warn(f"Could not write coordinate cache: {e}")

def tw_postal_to_coordinates(postal, default_country="us"):
    postal_upper = postal.upper()
    cache = _tw_load_coord_cache()
    if postal_upper in cache:
        return tuple(cache[postal_upper])

    if re.fullmatch(r"\d{5}", postal_upper):
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
            "postalcode": postal, "country": default_country, "format": "json", "limit": 1,
        })
    elif re.fullmatch(r"[A-Z]\d[A-Z] ?\d[A-Z]\d", postal_upper):
        normalized = postal_upper.replace(" ", "")
        normalized = normalized[:3] + " " + normalized[3:]
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
            "postalcode": normalized, "country": "ca", "format": "json", "limit": 1,
        })
    else:
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
            "postalcode": postal, "format": "json", "limit": 1,
        })

    data = tw_http_get_json(url)
    if data:
        try:
            lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
            cache[postal_upper] = [lat, lon]
            _tw_save_coord_cache(cache)
            return (lat, lon)
        except (IndexError, KeyError, ValueError, TypeError):
            pass

    # Canadian FSA fallback: look up the nearest major city by name instead
    if re.match(r"^[A-Z]\d[A-Z]", postal_upper):
        city = tw_canadian_fsa_city(postal_upper[:3])
        if city:
            time.sleep(1)  # be polite to Nominatim between requests
            url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
                "q": city, "format": "json", "limit": 1,
            })
            data = tw_http_get_json(url)
            if data:
                try:
                    lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
                    cache[postal_upper] = [lat, lon]
                    _tw_save_coord_cache(cache)
                    return (lat, lon)
                except (IndexError, KeyError, ValueError, TypeError):
                    pass

    log_warn(f"Could not resolve coordinates for location: {postal}")
    return None

def tw_icao_coordinates(icao):
    data = tw_http_get_json(
        "https://aviationweather.gov/api/data/airport?ids={}&format=json".format(icao)
    )
    try:
        info = data[0] if isinstance(data, list) else data
        return (float(info["lat"]), float(info["lon"]))
    except (IndexError, KeyError, TypeError, ValueError):
        return None

def tw_resolve_coordinates(location, default_country="us"):
    if tw_is_special_location(location):
        return tw_special_coordinates(location)
    if tw_is_icao_code(location):
        return tw_icao_coordinates(location.upper())
    return tw_postal_to_coordinates(location, default_country)

# ── Per-provider fetchers ──────────────────────────────────────────────────────
# All return a dict {temp_f, condition, feels_like_f, humidity} (any value may
# be None if unavailable) or None on total failure. Temperatures always in F;
# build_timeweather_audio() converts to C itself if TemperatureUnit is C.

def fetch_weather_metar(icao):
    icao = icao.upper()
    metar = tw_http_get(
        "https://aviationweather.gov/api/data/metar?ids={}&format=raw&hours=0&taf=false".format(icao)
    )
    if metar:
        metar = metar.splitlines()[0].strip()
    if not metar:
        metar = tw_http_get(
            "https://tgftp.nws.noaa.gov/data/observations/metar/stations/{}.TXT".format(icao)
        )
        if metar:
            lines = [l for l in metar.splitlines() if l.strip()]
            metar = lines[-1].strip() if lines else None
    if not metar:
        log_debug(f"METAR: no data for {icao}")
        return None

    m = re.search(r" (M?\d{2})/(M?\d{2}) ", metar)
    if not m:
        log_debug(f"METAR: no temp field in report for {icao}")
        return None
    t_c = -int(m.group(1)[1:]) if m.group(1).startswith("M") else int(m.group(1))
    temp_f = round(t_c * 9 / 5 + 32)

    return {
        "temp_f": temp_f,
        "condition": tw_metar_condition_word(metar),
        "feels_like_f": None,   # not available from METAR
        "humidity": None,       # not available from METAR
    }

def fetch_weather_openmeteo(location, default_country="us"):
    coords = tw_resolve_coordinates(location, default_country)
    if not coords:
        return None
    lat, lon = coords

    data = tw_http_get_json(
        "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                       "weather_code,is_day",
            "temperature_unit": "fahrenheit", "timezone": "auto",
        })
    )
    if not data or "current" not in data:
        log_debug(f"OpenMeteo: no current-conditions data for {location}")
        return None

    cur = data["current"]
    if cur.get("temperature_2m") is None:
        return None

    return {
        "temp_f": round(cur["temperature_2m"]),
        "condition": tw_openmeteo_condition_word(cur.get("weather_code", 0), cur.get("is_day", 1) == 1),
        "feels_like_f": round(cur["apparent_temperature"]) if cur.get("apparent_temperature") is not None else None,
        "humidity": round(cur["relative_humidity_2m"]) if cur.get("relative_humidity_2m") is not None else None,
    }

def fetch_weather_tempest(state, token, station_id):
    if not token:
        log_warn("Tempest requires TimeWeather.Weather.Tempest.Token")
        return None

    cached = state.get("timeweather_tempest_station") or {}
    resolved_station_id = station_id or (cached.get("station_id") if cached.get("token") == token else None)
    if not resolved_station_id:
        stations = tw_http_get_json(
            "https://swd.weatherflow.com/swd/rest/stations?token={}".format(token)
        )
        found = (stations or {}).get("stations") or []
        if not found:
            log_warn("Tempest: could not auto-detect station ID")
            return None
        resolved_station_id = found[0]["station_id"]
        state["timeweather_tempest_station"] = {"token": token, "station_id": resolved_station_id}
        log_info(f"Tempest: auto-detected station ID {resolved_station_id}")

    data = tw_http_get_json(
        "https://swd.weatherflow.com/swd/rest/better_forecast?" + urllib.parse.urlencode({
            "station_id": resolved_station_id, "units_temp": "f", "token": token,
        })
    )
    cc = (data or {}).get("current_conditions") or {}
    if cc.get("air_temperature") is None:
        log_debug(f"Tempest: no current conditions for station {resolved_station_id}")
        return None

    return {
        "temp_f": round(cc["air_temperature"]),
        "condition": tw_text_condition_word(cc.get("conditions", "")),
        "feels_like_f": round(cc["feels_like"]) if cc.get("feels_like") is not None else None,
        "humidity": round(cc["relative_humidity"]) if cc.get("relative_humidity") is not None else None,
    }

def fetch_weather_skywarnplus():
    try:
        with open(SWP_WEATHER_FILE) as f:
            payload = json.load(f)
    except Exception:
        log_warn(f"SkywarnPlus weather file not found or unreadable: {SWP_WEATHER_FILE}")
        return None

    w = payload.get("weather")
    if not w:
        log_warn("SkywarnPlus weather file has no 'weather' data (WeatherEnable may be off in its config.yaml)")
        return None

    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    temp_f = _num(w.get("temp_f"))
    feels_f = _num(w.get("feels_like_f"))
    humidity = _num(w.get("humidity"))
    return {
        "temp_f": round(temp_f) if temp_f is not None else None,
        "condition": tw_text_condition_word(w.get("condition", "")),
        "feels_like_f": round(feels_f) if feels_f is not None else None,
        "humidity": round(humidity) if humidity is not None else None,
    }

def fetch_weather(state, provider, location, tempest_token, tempest_station, default_country="us"):
    """Dispatch to the right provider(s), matching weather.sh's fallback rules."""
    provider = (provider or "auto").lower()

    if provider == "skywarnplus":
        return fetch_weather_skywarnplus()

    if provider == "tempest":
        result = fetch_weather_tempest(state, tempest_token, tempest_station)
        if result is None and location:
            result = fetch_weather_openmeteo(location, default_country)
        return result

    is_icao = bool(location) and tw_is_icao_code(location)

    if is_icao:
        if provider == "openmeteo":
            return fetch_weather_openmeteo(location, default_country) or fetch_weather_metar(location)
        result = fetch_weather_metar(location)
        return result if result is not None else fetch_weather_openmeteo(location, default_country)

    if location and tw_is_special_location(location):
        return fetch_weather_openmeteo(location, default_country)

    # Postal/ZIP code (or provider explicitly forced to metar with a non-ICAO
    # location, which will simply fail and fall through to Open-Meteo)
    if provider == "metar":
        result = fetch_weather_metar(location) if location else None
        return result if result is not None else fetch_weather_openmeteo(location, default_country)
    result = fetch_weather_openmeteo(location, default_country) if location else None
    return result if result is not None else fetch_weather_metar(location)

def fetch_weather_cached(state, provider, location, tempest_token, tempest_station,
                          cache_max_age_min=DEFAULT_TW_WEATHER_CACHE_MIN, default_country="us"):
    """Throttled wrapper: reuses the last successful reading if it's still
    fresh, and falls back to a stale reading (rather than nothing) if a fresh
    fetch fails outright."""
    cache = state.get("timeweather_weather_cache")
    if cache and cache.get("provider") == provider:
        try:
            fetched = datetime.fromisoformat(cache["fetched"])
            if (datetime.now() - fetched).total_seconds() < cache_max_age_min * 60:
                return cache["weather"]
        except Exception:
            pass

    weather = fetch_weather(state, provider, location, tempest_token, tempest_station, default_country)
    if weather:
        state["timeweather_weather_cache"] = {
            "provider": provider, "weather": weather,
            "fetched": datetime.now().isoformat(),
        }
    elif cache:
        log_warn("Time & Weather fetch failed, reusing last cached reading")
        weather = cache["weather"]
    return weather

# ── Announcement audio assembly ────────────────────────────────────────────────
# Concatenates pre-recorded GSM snippets exactly like saytime.pl did (GSM
# frames are directly concatenable — no re-encoding needed).

def _tw_find_sound(name):
    # Most snippets (greetings, condition words, digits) live directly in
    # TW_SOUND_BASE, but a few condition words the METAR mapper can produce
    # (e.g. "mist") only exist under its wx/ subdirectory in the shipped
    # sound pack — check both, matching weather.sh's own multi-directory
    # search for condition words.
    for candidate in (
        os.path.join(TW_SOUND_BASE, name + ".gsm"),
        os.path.join(TW_SOUND_BASE, "wx", name + ".gsm"),
    ):
        if os.path.exists(candidate):
            return candidate
    return None

def tw_add_number(n, files):
    n = int(abs(n))
    if n >= 100:
        files.append(os.path.join(TW_SOUND_BASE, "digits", "1.gsm"))
        files.append(os.path.join(TW_SOUND_BASE, "digits", "hundred.gsm"))
        if n > 100:
            n -= 100
    if n < 20:
        files.append(os.path.join(TW_SOUND_BASE, "digits", f"{n}.gsm"))
    else:
        tens, ones = (n // 10) * 10, n % 10
        files.append(os.path.join(TW_SOUND_BASE, "digits", f"{tens}.gsm"))
        if ones > 0:
            files.append(os.path.join(TW_SOUND_BASE, "digits", f"{ones}.gsm"))

def tw_gsm_duration(path):
    """GSM 06.10 full-rate is a fixed 33-bytes-per-20ms frame format with no
    file header, so the duration is exact from file size alone. Used instead
    of audio_duration() (soxi) because soxi reliably reports 0 for these raw
    headerless GSM files even though it can read them fine otherwise
    (confirmed against the actual shipped sound files)."""
    try:
        size = os.path.getsize(path)
        return (size / 33) * 0.020
    except OSError:
        return None

def build_timeweather_audio(tw_cfg, weather, now_dt, out_path, warnings=None):
    """Builds the announcement WAV/GSM file. Returns True on success.
    Any caller-visible problems are both logged (log_warn) and appended to
    `warnings` if a list is passed in, so on-demand callers (herald
    test-timeweather / the web UI's Test button) can surface them instead of
    losing them to the daemon's own log."""
    if warnings is None:
        warnings = []
    files = []
    hour, minute = now_dt.hour, now_dt.minute
    time_format = str(tw_cfg.get("TimeFormat", "12"))

    if time_format == "24":
        files.append(os.path.join(TW_SOUND_BASE, "the-time-is.gsm"))
        tw_add_number(hour, files)
        if minute == 0:
            files.append(os.path.join(TW_SOUND_BASE, "digits", "oclock.gsm"))
        elif minute < 10:
            files.append(os.path.join(TW_SOUND_BASE, "digits", "oh.gsm"))
            files.append(os.path.join(TW_SOUND_BASE, "digits", f"{minute}.gsm"))
        else:
            tens, ones = (minute // 10) * 10, minute % 10
            files.append(os.path.join(TW_SOUND_BASE, "digits", f"{tens}.gsm"))
            if ones > 0:
                files.append(os.path.join(TW_SOUND_BASE, "digits", f"{ones}.gsm"))
    else:
        if hour < 12:
            ampm, greeting = "AM", "good-morning"
        elif hour < 18:
            ampm, greeting = "PM", "good-afternoon"
        else:
            ampm, greeting = "PM", "good-evening"
        files.append(os.path.join(TW_SOUND_BASE, f"{greeting}.gsm"))

        hour12 = hour - 12 if hour > 12 else (12 if hour == 0 else hour)
        files.append(os.path.join(TW_SOUND_BASE, "the-time-is.gsm"))
        files.append(os.path.join(TW_SOUND_BASE, "digits", f"{hour12}.gsm"))
        if minute != 0:
            if minute < 10:
                files.append(os.path.join(TW_SOUND_BASE, "digits", "oh.gsm"))
                files.append(os.path.join(TW_SOUND_BASE, "digits", f"{minute}.gsm"))
            elif minute < 20:
                files.append(os.path.join(TW_SOUND_BASE, "digits", f"{minute}.gsm"))
            else:
                tens, ones = (minute // 10) * 10, minute % 10
                files.append(os.path.join(TW_SOUND_BASE, "digits", f"{tens}.gsm"))
                if ones > 0:
                    files.append(os.path.join(TW_SOUND_BASE, "digits", f"{ones}.gsm"))
        files.append(os.path.join(TW_SOUND_BASE, "digits", "a-m.gsm" if ampm == "AM" else "p-m.gsm"))

    wcfg = tw_cfg.get("Weather", {}) or {}
    if wcfg.get("Enable", True) and weather:
        unit_c = str(wcfg.get("TemperatureUnit", "F")).upper() == "C"

        def _convert(f_val):
            return round((f_val - 32) * 5 / 9) if unit_c else f_val

        if wcfg.get("AnnounceCondition", True) and weather.get("condition"):
            files.append(os.path.join(TW_SOUND_BASE, "silence", "1.gsm"))
            cond_files = []
            for word in weather["condition"].split():
                f = _tw_find_sound(word)
                if f:
                    cond_files.append(f)
            if cond_files:
                files.append(os.path.join(TW_SOUND_BASE, "weather.gsm"))
                files.append(os.path.join(TW_SOUND_BASE, "conditions.gsm"))
                files.extend(cond_files)

        if weather.get("temp_f") is not None:
            files.append(os.path.join(TW_SOUND_BASE, "wx", "temperature.gsm"))
            temp = _convert(weather["temp_f"])
            if temp < -1:
                files.append(os.path.join(TW_SOUND_BASE, "digits", "minus.gsm"))
            tw_add_number(temp, files)
            files.append(os.path.join(TW_SOUND_BASE, "degrees.gsm"))

        if wcfg.get("AnnounceFeelsLike", False) and weather.get("feels_like_f") is not None:
            files.append(os.path.join(TW_SOUND_BASE, "silence", "1.gsm"))
            feels_file = _tw_find_sound("feels-like") or _tw_find_sound("heat-index")
            if feels_file:
                files.append(feels_file)
            feels = _convert(weather["feels_like_f"])
            if feels < -1:
                files.append(os.path.join(TW_SOUND_BASE, "digits", "minus.gsm"))
            tw_add_number(feels, files)
            files.append(os.path.join(TW_SOUND_BASE, "degrees.gsm"))

        if wcfg.get("AnnounceHumidity", False) and weather.get("humidity") is not None:
            files.append(os.path.join(TW_SOUND_BASE, "silence", "1.gsm"))
            files.append(os.path.join(TW_SOUND_BASE, "wx", "humidity.gsm"))
            tw_add_number(weather["humidity"], files)
            files.append(os.path.join(TW_SOUND_BASE, "wx", "percent.gsm"))

    missing = [f for f in files if not os.path.exists(f)]
    if missing:
        names = ", ".join(os.path.basename(m) for m in missing[:3])
        log_warn(f"Time & Weather: missing sound file(s), skipping: {missing[:3]}")
        warnings.append(f"Missing sound file(s): {names}")
        return False
    if not files:
        log_warn("Time & Weather: nothing to announce (check config)")
        warnings.append("Nothing to announce - check config")
        return False

    try:
        with open(out_path, "wb") as out:
            for f in files:
                with open(f, "rb") as src:
                    out.write(src.read())
        return True
    except Exception as e:
        log_error(f"Time & Weather: failed writing {out_path}: {e}")
        return False

def should_play_timeweather(tw_cfg, state, node, now_dt):
    if not tw_cfg.get("Enable", False):
        return False

    minute_key = now_dt.strftime("%Y-%m-%d %H:%M")
    if state.get("timeweather_played") == minute_key:
        return False

    already_pending = state.get("timeweather_pending", False)
    cron_expr = (tw_cfg.get("Schedule", {}) or {}).get("Cron", DEFAULT_TW_CRON)
    if not already_pending and not cron_matches(cron_expr, now_dt):
        return False

    keyed = node_is_keyed(node)
    if keyed:
        if not already_pending:
            state["timeweather_pending"] = True
            log_info("Time & Weather due but node is keyed - waiting for unkey")
        else:
            log_debug("Time & Weather still waiting for unkey")
        return False

    if already_pending:
        state["timeweather_pending"] = False

    return True

def play_timeweather(tw_cfg, state, node, now, now_dt, test_mode=False, warnings=None):
    """test_mode=True is a manual on-demand preview (herald test-timeweather /
    the web UI's Test button): still fetches real weather and plays it, but
    never touches the daemon's own scheduling state (timeweather_played/
    _pending/_busy_until) so it can't interfere with the next real scheduled
    occurrence. `warnings`, if passed, collects human-readable problem
    descriptions for on-demand callers to surface (see build_timeweather_audio)."""
    if warnings is None:
        warnings = []
    wcfg = tw_cfg.get("Weather", {}) or {}
    weather = None
    if wcfg.get("Enable", True):
        tempest_cfg = wcfg.get("Tempest", {}) or {}
        weather = fetch_weather_cached(
            state, wcfg.get("Provider", "auto"), wcfg.get("Location", ""),
            tempest_cfg.get("Token", ""), tempest_cfg.get("StationID", ""),
            wcfg.get("CacheMaxAgeMin", DEFAULT_TW_WEATHER_CACHE_MIN),
        )
        if not weather:
            log_warn("Time & Weather: no weather data available, announcing time only")
            warnings.append("No weather data available - announced time only")

    out_path = os.path.join(TW_TEMP_OUTDIR, "asl3-herald-timeweather.gsm")
    if not build_timeweather_audio(tw_cfg, weather, now_dt, out_path, warnings=warnings):
        return False

    entry_type = "test-timeweather" if test_mode else "timeweather"
    label = "Hourly Time & Weather (Test)" if test_mode else "Hourly Time & Weather"
    log_info(f"Playing {label} announcement")
    play_file(node, out_path)

    # The weather fetch above can take several real seconds (network calls),
    # during which the long-running daemon process (a separate process from
    # `herald test-timeweather` / any other one-off CLI invocation) may have
    # saved its own state to disk - e.g. a real scheduled occurrence firing
    # in that window. Re-reading fresh right before this save (rather than
    # reusing the possibly-stale snapshot `state` held since the top of this
    # call) avoids blindly overwriting that with an outdated copy, which
    # would silently erase whatever the daemon just wrote (confirmed live:
    # a manual test play's playback_history entry was wiped out by the next
    # real hourly run). Preserves this call's own weather-cache/station-id
    # writes, which were already applied to `state` earlier in this function.
    fresh_state = load_state()
    fresh_state["timeweather_weather_cache"] = state.get("timeweather_weather_cache")
    fresh_state["timeweather_tempest_station"] = state.get("timeweather_tempest_station")
    log_playback(fresh_state, entry_type, label, out_path, node)

    if not test_mode:
        minute_key = now_dt.strftime("%Y-%m-%d %H:%M")
        fresh_state["timeweather_played"] = minute_key
        fresh_state["timeweather_pending"] = False
        duration = tw_gsm_duration(out_path) or audio_duration(out_path) or DEFAULT_ANNOUNCEMENT_DURATION
        fresh_state["timeweather_busy_until"] = now + min(duration, MAX_BUSY_SECONDS) + BUSY_GRACE_SECONDS
    save_state(fresh_state)
    # Keep the caller's own `state` object (the daemon's long-lived instance,
    # in the non-test path) in sync with what was actually just persisted.
    state.clear()
    state.update(fresh_state)
    return True

# ── Config extraction helper ──────────────────────────────────────────────────

def extract_config(config):
    node  = str(config.get("Node", "")).strip()
    debug = config.get("Debug", False)

    tm       = config.get("TailMessage", {}) or {}
    tm_on    = tm.get("Enable", True)
    min_int  = tm.get("MinInterval", 300)
    rotation = tm.get("Rotation", []) or []
    network_trigger = tm.get("NetworkKeyupTrigger", True)

    swp      = tm.get("SkywarnPlus", {}) or {}
    swp_on   = swp.get("Enable", True)
    swp_file = swp.get("WxTailFile", "/tmp/SkywarnPlus/wx-tail.wav")
    swp_thr  = swp.get("SilenceThreshold", 5000)

    scheduled = config.get("Scheduled", []) or []

    tw = config.get("TimeWeather", {}) or {}

    return {
        "node":            node,
        "debug":           debug,
        "tm_on":           tm_on,
        "min_int":         min_int,
        "rotation":        rotation,
        "network_trigger": network_trigger,
        "swp_on":          swp_on,
        "swp_file":        swp_file,
        "swp_thr":         swp_thr,
        "scheduled":       scheduled,
        "timeweather":     tw,
    }

# ── CLI subcommands (used by the `herald` bash CLI and the web UI) ────────────

def normalize_rotation(rotation):
    out = []
    for e in rotation:
        if isinstance(e, str):
            entry = {"File": e, "Text": None, "Voice": None,
                      "Days": "daily", "TimeStart": None, "TimeEnd": None, "Node": None,
                      "Enabled": True}
        else:
            entry = {
                "File": e.get("File", ""),
                "Text": e.get("Text"),
                "Voice": e.get("Voice"),
                "Days": e.get("Days", "daily"),
                "TimeStart": e.get("TimeStart"),
                "TimeEnd": e.get("TimeEnd"),
                "Node": e.get("Node"),
                "Enabled": e.get("Enabled", True),
            }
        entry["FileMissing"] = not (entry["File"] and os.path.exists(entry["File"]))
        out.append(entry)
    return out

def scheduled_with_health(scheduled):
    out = []
    for s in scheduled:
        s2 = dict(s)
        filepath = s.get("File", "")
        s2["FileMissing"] = not (filepath and os.path.exists(filepath))
        if not s2.get("Cron"):
            s2["Cron"] = legacy_to_cron(s)
        s2["Enabled"] = s.get("Enabled", True)
        out.append(s2)
    return out

SWP_INSTALL_MARKER = "/usr/local/bin/SkywarnPlus/SkywarnPlus.py"

def skywarnplus_weather_status():
    """Returns (installed, weather_available) for the UI's SkywarnPlus
    recommendation banner and provider validation."""
    installed = os.path.exists(SWP_INSTALL_MARKER)
    weather_available = False
    try:
        with open(SWP_WEATHER_FILE) as f:
            weather_available = bool(json.load(f).get("weather"))
    except Exception:
        pass
    return installed, weather_available

def timeweather_with_health(tw):
    out = dict(tw)
    wcfg = dict(out.get("Weather", {}) or {})
    tempest_cfg = dict(wcfg.get("Tempest", {}) or {})
    wcfg["Tempest"] = tempest_cfg
    out["Weather"] = wcfg
    out.setdefault("Schedule", {}).setdefault("Cron", DEFAULT_TW_CRON)

    swp_installed, swp_weather_available = skywarnplus_weather_status()

    # install.sh only pre-selects "skywarnplus" for a genuinely brand-new
    # config; an existing Herald install upgrading to pick up this feature
    # never gets that file mutation (existing configs are never touched), so
    # its Provider key is simply absent. Default the *displayed* value the
    # same smart way here, purely at read time - this doesn't write anything
    # to disk, it just means the UI shows the same recommended default
    # either way until the user actually saves a choice.
    if "Provider" not in wcfg:
        wcfg["Provider"] = "skywarnplus" if swp_installed else "auto"

    out["_health"] = {
        "sound_files_installed": os.path.exists(os.path.join(TW_SOUND_BASE, "the-time-is.gsm")),
        "skywarnplus_installed": swp_installed,
        "skywarnplus_weather_available": swp_weather_available,
    }
    return out

def cmd_list_json(config):
    cfg = extract_config(config)
    state = load_state()
    out = {
        "node":    cfg["node"],
        "debug":   cfg["debug"],
        "herald_enabled": not os.path.exists(DISABLE_FLAG),
        "version": VERSION,
        "ami_connected": _ami_up,
        "tail_message": {
            "enable":           cfg["tm_on"],
            "min_interval":     cfg["min_int"],
            "network_keyup_trigger": cfg["network_trigger"],
            "last_tail_played": state.get("last_tail_played", 0.0),
            "rotation":         normalize_rotation(cfg["rotation"]),
            "skywarnplus": {
                "enable":           cfg["swp_on"],
                "wx_tail_file":     cfg["swp_file"],
                "silence_threshold": cfg["swp_thr"],
            },
        },
        "scheduled": scheduled_with_health(cfg["scheduled"]),
        "timeweather": timeweather_with_health(cfg["timeweather"]),
    }
    print(json.dumps(out, indent=2))

def cmd_add_rotation(config, args):
    filepath = args.filepath
    tm = config.setdefault("TailMessage", {})
    rotation = tm.setdefault("Rotation", [])
    if any(rotation_entry_file(e) == filepath for e in rotation):
        print(json.dumps({"success": False, "message": f"Already in rotation: {filepath}"}))
        return
    entry = {"File": filepath, "Text": args.text, "Voice": args.voice}
    if args.days and args.days != "daily":
        entry["Days"] = [d.strip().lower() for d in args.days.split(",")]
    if args.time_start:
        entry["TimeStart"] = args.time_start
    if args.time_end:
        entry["TimeEnd"] = args.time_end
    if args.node:
        entry["Node"] = args.node
    rotation.append(entry)
    save_config(config)
    print(json.dumps({"success": True, "message": f"Added to rotation: {filepath}"}))

def cmd_edit_rotation(config, args):
    tm = config.setdefault("TailMessage", {})
    rotation = tm.setdefault("Rotation", [])

    target = os.path.basename(args.old_name)
    target_noext = os.path.splitext(target)[0]
    idx = None
    for i, e in enumerate(rotation):
        base = os.path.basename(rotation_entry_file(e))
        base_noext = os.path.splitext(base)[0]
        if base == target or base_noext == target_noext:
            idx = i
            break

    if idx is None:
        print(json.dumps({"success": False, "message": f"No rotation entry found for: {args.old_name}"}))
        return

    old = rotation[idx]
    entry = dict(old) if isinstance(old, dict) else {"File": old}

    if args.file is not None:
        entry["File"] = args.file
    if args.text is not None:
        entry["Text"] = args.text
    if args.voice is not None:
        entry["Voice"] = args.voice
    if args.days is not None:
        if args.days == "daily" or args.days == "":
            entry.pop("Days", None)
        else:
            entry["Days"] = [d.strip().lower() for d in args.days.split(",")]
    if args.time_start is not None:
        if args.time_start:
            entry["TimeStart"] = args.time_start
        else:
            entry.pop("TimeStart", None)
    if args.time_end is not None:
        if args.time_end:
            entry["TimeEnd"] = args.time_end
        else:
            entry.pop("TimeEnd", None)
    if args.node is not None:
        if args.node:
            entry["Node"] = args.node
        else:
            entry.pop("Node", None)

    rotation[idx] = entry
    save_config(config)
    print(json.dumps({"success": True, "message": f"Updated rotation entry: {os.path.basename(entry.get('File', ''))}"}))

def cmd_add_scheduled(config, args):
    scheduled = config.setdefault("Scheduled", [])
    if any(s.get("Name") == args.name for s in scheduled):
        print(json.dumps({"success": False, "message": f"Scheduled entry already exists: {args.name}"}))
        return

    entry = {
        "Name": args.name,
        "Cron": args.cron,
        "File": args.file,
        "PlayMode": args.play_mode or "local",
    }
    if args.text:
        entry["Text"] = args.text
    if args.voice:
        entry["Voice"] = args.voice
    if args.node:
        entry["Node"] = args.node

    scheduled.append(entry)
    save_config(config)
    print(json.dumps({"success": True, "message": f"Added scheduled announcement: {args.name}"}))

def cmd_edit_scheduled(config, args):
    scheduled = config.setdefault("Scheduled", [])
    idx = None
    for i, s in enumerate(scheduled):
        if s.get("Name") == args.old_name:
            idx = i
            break

    if idx is None:
        print(json.dumps({"success": False, "message": f"No scheduled entry found for: {args.old_name}"}))
        return

    old = scheduled[idx]
    new_name = args.new_name or old.get("Name")
    if new_name != old.get("Name") and any(s.get("Name") == new_name for s in scheduled):
        print(json.dumps({"success": False, "message": f"Scheduled entry already exists: {new_name}"}))
        return

    entry = dict(old)
    # Migrate any legacy Time/Days/Week fields when editing
    entry.pop("Time", None)
    entry.pop("Days", None)
    entry.pop("Week", None)
    entry["Name"] = new_name
    if args.cron is not None:
        entry["Cron"] = args.cron
    if args.play_mode is not None:
        entry["PlayMode"] = args.play_mode
    if args.text is not None:
        entry["Text"] = args.text
    if args.voice is not None:
        entry["Voice"] = args.voice
    if args.file is not None:
        entry["File"] = args.file
    if args.node is not None:
        if args.node:
            entry["Node"] = args.node
        else:
            entry.pop("Node", None)

    scheduled[idx] = entry
    save_config(config)
    print(json.dumps({"success": True, "message": f"Updated scheduled announcement: {new_name}"}))

def cmd_toggle_scheduled(config, args):
    scheduled = config.setdefault("Scheduled", [])
    for i, s in enumerate(scheduled):
        if s.get("Name") == args.name:
            current = s.get("Enabled", True)
            scheduled[i]["Enabled"] = not current
            save_config(config)
            state = "enabled" if not current else "disabled"
            print(json.dumps({"success": True, "message": f"Scheduled announcement '{args.name}' {state}", "enabled": not current}))
            return
    print(json.dumps({"success": False, "message": f"No scheduled entry found for: {args.name}"}))

def cmd_toggle_rotation(config, args):
    tm = config.setdefault("TailMessage", {})
    rotation = tm.setdefault("Rotation", [])
    target = args.name
    for i, e in enumerate(rotation):
        base = os.path.splitext(os.path.basename(rotation_entry_file(e)))[0]
        if base == target:
            current = e.get("Enabled", True) if isinstance(e, dict) else True
            if isinstance(e, str):
                rotation[i] = {"File": e, "Enabled": not current}
            else:
                rotation[i]["Enabled"] = not current
            save_config(config)
            state = "enabled" if not current else "disabled"
            print(json.dumps({"success": True, "message": f"Rotation entry '{target}' {state}", "enabled": not current}))
            return
    print(json.dumps({"success": False, "message": f"No rotation entry found for: {target}"}))

def cmd_remove(config, identifier):
    tm = config.setdefault("TailMessage", {})
    rotation = tm.setdefault("Rotation", [])
    scheduled = config.setdefault("Scheduled", [])

    target = os.path.basename(identifier)
    target_noext = os.path.splitext(target)[0]

    new_rotation = []
    removed_rotation = False
    for e in rotation:
        base = os.path.basename(rotation_entry_file(e))
        base_noext = os.path.splitext(base)[0]
        if base == target or base_noext == target_noext:
            removed_rotation = True
        else:
            new_rotation.append(e)

    new_scheduled = [s for s in scheduled if s.get("Name") != identifier]
    removed_scheduled = len(new_scheduled) < len(scheduled)

    if not removed_rotation and not removed_scheduled:
        print(json.dumps({"success": False, "message": f"Not found: {identifier}"}))
        return

    tm["Rotation"] = new_rotation
    config["Scheduled"] = new_scheduled
    save_config(config)
    print(json.dumps({"success": True, "message": f"Removed: {identifier}"}))

def cmd_reorder_rotation(config, args):
    tm = config.setdefault("TailMessage", {})
    rotation = tm.setdefault("Rotation", [])

    target = args.name
    idx = None
    for i, e in enumerate(rotation):
        base_noext = os.path.splitext(os.path.basename(rotation_entry_file(e)))[0]
        if base_noext == target or rotation_entry_file(e) == target:
            idx = i
            break

    if idx is None:
        print(json.dumps({"success": False, "message": f"Not found: {target}"}))
        return

    if args.direction == "up":
        if idx == 0:
            print(json.dumps({"success": False, "message": "Already at top"}))
            return
        rotation[idx - 1], rotation[idx] = rotation[idx], rotation[idx - 1]
    else:
        if idx == len(rotation) - 1:
            print(json.dumps({"success": False, "message": "Already at bottom"}))
            return
        rotation[idx + 1], rotation[idx] = rotation[idx], rotation[idx + 1]

    save_config(config)
    print(json.dumps({"success": True, "message": "Rotation reordered"}))

def cmd_log_playback(args):
    state = load_state()
    log_playback(state, args.type, args.name, args.file, args.node, args.play_mode)
    save_state(state)
    print(json.dumps({"success": True}))

def cmd_playback_history():
    state = load_state()
    history = state.get("playback_history", [])
    print(json.dumps({"history": list(reversed(history))}))

def cmd_clear_history():
    state = load_state()
    state["playback_history"] = []
    save_state(state)
    print(json.dumps({"success": True, "message": "Playback history cleared"}))

def cmd_export_config(config):
    print(json.dumps(config, indent=2))

def cmd_import_config(args):
    try:
        with open(args.file) as f:
            new_config = json.load(f)
    except Exception as e:
        print(json.dumps({"success": False, "message": f"Could not read import file: {e}"}))
        return
    if not isinstance(new_config, dict) or "Node" not in new_config:
        print(json.dumps({"success": False, "message": "Invalid config: not a recognizable asl3-herald config"}))
        return
    save_config(new_config)
    print(json.dumps({"success": True, "message": "Config imported and saved"}))

def cmd_update_settings(config, args):
    if args.node is not None:
        config["Node"] = args.node
    if args.debug is not None:
        config["Debug"] = (args.debug == "true")

    tm = config.setdefault("TailMessage", {})
    if args.min_interval is not None:
        tm["MinInterval"] = args.min_interval
    if args.network_keyup_trigger is not None:
        tm["NetworkKeyupTrigger"] = (args.network_keyup_trigger == "true")

    swp = tm.setdefault("SkywarnPlus", {})
    if args.swp_enable is not None:
        swp["Enable"] = (args.swp_enable == "true")
    if args.swp_wxfile is not None:
        swp["WxTailFile"] = args.swp_wxfile
    if args.swp_threshold is not None:
        swp["SilenceThreshold"] = args.swp_threshold

    save_config(config)
    print(json.dumps({"success": True, "message": "Settings updated"}))

def cmd_update_timeweather(config, args):
    tw = config.setdefault("TimeWeather", {})
    if args.enable is not None:
        tw["Enable"] = (args.enable == "true")
    if args.time_format is not None:
        tw["TimeFormat"] = args.time_format
    if args.cron is not None:
        tw.setdefault("Schedule", {})["Cron"] = args.cron

    w = tw.setdefault("Weather", {})
    if args.weather_enable is not None:
        w["Enable"] = (args.weather_enable == "true")
    if args.provider is not None:
        w["Provider"] = args.provider
    if args.location is not None:
        w["Location"] = args.location
    if args.temp_unit is not None:
        w["TemperatureUnit"] = args.temp_unit
    if args.announce_condition is not None:
        w["AnnounceCondition"] = (args.announce_condition == "true")
    if args.announce_feels_like is not None:
        w["AnnounceFeelsLike"] = (args.announce_feels_like == "true")
    if args.announce_humidity is not None:
        w["AnnounceHumidity"] = (args.announce_humidity == "true")
    if args.cache_max_age is not None:
        w["CacheMaxAgeMin"] = args.cache_max_age

    tempest = w.setdefault("Tempest", {})
    if args.tempest_token is not None:
        tempest["Token"] = args.tempest_token
    if args.tempest_station is not None:
        tempest["StationID"] = args.tempest_station

    save_config(config)
    print(json.dumps({"success": True, "message": "Time & Weather settings updated"}))

def cmd_test_timeweather(config):
    cfg = extract_config(config)
    node = cfg["node"]
    if not node:
        print(json.dumps({"success": False, "message": "Node not set in config"}))
        return
    state = load_state()
    now_dt = datetime.now()
    warnings = []
    ok = play_timeweather(cfg["timeweather"], state, node, time.time(), now_dt, test_mode=True, warnings=warnings)
    if ok:
        message = "Playing Hourly Time & Weather test announcement"
        if warnings:
            message += " (" + "; ".join(warnings) + ")"
        print(json.dumps({"success": True, "message": message}))
    else:
        message = "Could not build announcement"
        message += ": " + "; ".join(warnings) if warnings else " - check sound files and weather config"
        print(json.dumps({"success": False, "message": message}))

def build_arg_parser():
    parser = argparse.ArgumentParser(prog="asl3-herald.py")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list-json", help="Print current config as JSON")

    p_add_rot = sub.add_parser("add-rotation", help="Add a WAV file to the tail message rotation")
    p_add_rot.add_argument("filepath")
    p_add_rot.add_argument("--text", default=None)
    p_add_rot.add_argument("--voice", default=None)
    p_add_rot.add_argument("--days", default="daily")
    p_add_rot.add_argument("--time-start", dest="time_start", default=None)
    p_add_rot.add_argument("--time-end", dest="time_end", default=None)
    p_add_rot.add_argument("--node", default=None)

    p_edit_rot = sub.add_parser("edit-rotation", help="Edit an existing tail message rotation entry")
    p_edit_rot.add_argument("old_name")
    p_edit_rot.add_argument("--new-name", dest="new_name", default=None)
    p_edit_rot.add_argument("--text", default=None)
    p_edit_rot.add_argument("--voice", default=None)
    p_edit_rot.add_argument("--file", default=None)
    p_edit_rot.add_argument("--days", default=None)
    p_edit_rot.add_argument("--time-start", dest="time_start", default=None)
    p_edit_rot.add_argument("--time-end", dest="time_end", default=None)
    p_edit_rot.add_argument("--node", default=None)

    p_add_sched = sub.add_parser("add-scheduled", help="Add a scheduled announcement")
    p_add_sched.add_argument("--name", required=True)
    p_add_sched.add_argument("--cron", required=True)
    p_add_sched.add_argument("--file", required=True)
    p_add_sched.add_argument("--play-mode", dest="play_mode", choices=["local", "global"], default="local")
    p_add_sched.add_argument("--text", default=None)
    p_add_sched.add_argument("--voice", default=None)
    p_add_sched.add_argument("--node", default=None)

    p_edit_sched = sub.add_parser("edit-scheduled", help="Edit an existing scheduled announcement")
    p_edit_sched.add_argument("old_name")
    p_edit_sched.add_argument("--new-name", dest="new_name", default=None)
    p_edit_sched.add_argument("--cron", default=None)
    p_edit_sched.add_argument("--play-mode", dest="play_mode", choices=["local", "global"], default=None)
    p_edit_sched.add_argument("--text", default=None)
    p_edit_sched.add_argument("--voice", default=None)
    p_edit_sched.add_argument("--file", default=None)
    p_edit_sched.add_argument("--node", default=None)

    p_toggle_sched = sub.add_parser("toggle-scheduled", help="Toggle a scheduled announcement enabled/disabled")
    p_toggle_sched.add_argument("name")

    p_toggle_rot = sub.add_parser("toggle-rotation", help="Toggle a tail message rotation entry enabled/disabled")
    p_toggle_rot.add_argument("name")

    p_remove = sub.add_parser("remove", help="Remove a rotation file or scheduled announcement by name")
    p_remove.add_argument("identifier")

    p_reorder = sub.add_parser("reorder-rotation", help="Move a rotation entry up or down in the list")
    p_reorder.add_argument("name")
    p_reorder.add_argument("--direction", choices=["up", "down"], required=True)

    p_log_play = sub.add_parser("log-playback", help="Record a playback event in history (internal use)")
    p_log_play.add_argument("--type", default="test")
    p_log_play.add_argument("--name", required=True)
    p_log_play.add_argument("--file", default="")
    p_log_play.add_argument("--node", default="")
    p_log_play.add_argument("--play-mode", dest="play_mode", default="local")

    sub.add_parser("playback-history", help="Print playback history as JSON")
    sub.add_parser("clear-history",    help="Clear the playback history")
    sub.add_parser("export-config",    help="Export the full daemon config as JSON (for backup)")

    p_import = sub.add_parser("import-config", help="Restore the full daemon config from an exported JSON file")
    p_import.add_argument("file")

    p_settings = sub.add_parser("update-settings", help="Update general daemon settings")
    p_settings.add_argument("--node")
    p_settings.add_argument("--debug", choices=["true", "false"])
    p_settings.add_argument("--min-interval", dest="min_interval", type=int)
    p_settings.add_argument("--network-keyup-trigger", dest="network_keyup_trigger", choices=["true", "false"])
    p_settings.add_argument("--swp-enable",    dest="swp_enable",    choices=["true", "false"])
    p_settings.add_argument("--swp-wxfile",    dest="swp_wxfile")
    p_settings.add_argument("--swp-threshold", dest="swp_threshold", type=int)

    p_tw = sub.add_parser("update-timeweather", help="Update Hourly Time & Weather settings")
    p_tw.add_argument("--enable", choices=["true", "false"])
    p_tw.add_argument("--time-format", dest="time_format", choices=["12", "24"])
    p_tw.add_argument("--cron")
    p_tw.add_argument("--weather-enable", dest="weather_enable", choices=["true", "false"])
    p_tw.add_argument("--provider", choices=["auto", "metar", "openmeteo", "tempest", "skywarnplus"])
    p_tw.add_argument("--location")
    p_tw.add_argument("--temp-unit", dest="temp_unit", choices=["F", "C"])
    p_tw.add_argument("--announce-condition", dest="announce_condition", choices=["true", "false"])
    p_tw.add_argument("--announce-feels-like", dest="announce_feels_like", choices=["true", "false"])
    p_tw.add_argument("--announce-humidity", dest="announce_humidity", choices=["true", "false"])
    p_tw.add_argument("--cache-max-age", dest="cache_max_age", type=int)
    p_tw.add_argument("--tempest-token", dest="tempest_token")
    p_tw.add_argument("--tempest-station", dest="tempest_station")

    sub.add_parser("test-timeweather", help="Test-play the Hourly Time & Weather announcement immediately")

    return parser

def cli_main():
    parser = build_arg_parser()
    args = parser.parse_args()

    if not args.command:
        main()
        return

    config = load_config()

    if args.command == "list-json":
        cmd_list_json(config)
    elif args.command == "add-rotation":
        cmd_add_rotation(config, args)
    elif args.command == "edit-rotation":
        cmd_edit_rotation(config, args)
    elif args.command == "add-scheduled":
        cmd_add_scheduled(config, args)
    elif args.command == "toggle-scheduled":
        cmd_toggle_scheduled(config, args)
    elif args.command == "toggle-rotation":
        cmd_toggle_rotation(config, args)
    elif args.command == "edit-scheduled":
        cmd_edit_scheduled(config, args)
    elif args.command == "remove":
        cmd_remove(config, args.identifier)
    elif args.command == "reorder-rotation":
        cmd_reorder_rotation(config, args)
    elif args.command == "log-playback":
        cmd_log_playback(args)
    elif args.command == "playback-history":
        cmd_playback_history()
    elif args.command == "clear-history":
        cmd_clear_history()
    elif args.command == "export-config":
        cmd_export_config(config)
    elif args.command == "import-config":
        cmd_import_config(args)
    elif args.command == "update-settings":
        cmd_update_settings(config, args)
    elif args.command == "update-timeweather":
        cmd_update_timeweather(config, args)
    elif args.command == "test-timeweather":
        cmd_test_timeweather(config)

# ── Main ──────────────────────────────────────────────────────────────────────

def _ami_connect(host, port, user, secret):
    """Create and connect an AmiConn, return it on success or None on failure."""
    conn = AmiConn(host, port, user, secret)
    if conn.connect():
        return conn
    return None

def _poll_ami(ami, node):
    """
    Poll XStat + SawStat and update module-level AMI state cache.
    Returns (rx_keyed, conn_keyed) on success, raises on failure.
    """
    global _ami_rx_keyed, _ami_conn_keyed, _ami_up
    xstat = ami.xstat(node)
    saw   = ami.sawstat(node)
    _ami_rx_keyed   = xstat["RXKEYED"]
    _ami_conn_keyed = saw["CONNKEYED"]
    _ami_up = True
    return _ami_rx_keyed, _ami_conn_keyed

def main():
    global DEBUG, _ami_up, _ami_rx_keyed, _ami_conn_keyed

    log_info(f"asl3-herald v{VERSION} starting")

    config = load_config()
    cfg    = extract_config(config)

    node            = cfg["node"]
    DEBUG           = cfg["debug"]
    tm_on           = cfg["tm_on"]
    min_int         = cfg["min_int"]
    rotation        = cfg["rotation"]
    network_trigger = cfg["network_trigger"]
    swp_on          = cfg["swp_on"]
    swp_file        = cfg["swp_file"]
    swp_thr         = cfg["swp_thr"]
    scheduled       = cfg["scheduled"]
    timeweather     = cfg["timeweather"]

    if not node:
        log_error("Node not set in config. Exiting.")
        sys.exit(1)

    state = load_state()

    # ── AMI setup ──────────────────────────────────────────────────────────
    # Credentials are read from /etc/allmon3/allmon3.ini or
    # /etc/asterisk/manager.conf — never stored in asl3-herald.conf.
    ami_host, ami_port, ami_user, ami_secret = load_ami_credentials()
    ami = None
    if ami_user:
        log_info(f"Connecting to AMI at {ami_host}:{ami_port} as '{ami_user}' ...")
        ami = _ami_connect(ami_host, ami_port, ami_user, ami_secret)
        if ami:
            log_info("AMI connected — using event-driven unkey detection")
            if network_trigger:
                log_info("NetworkKeyupTrigger enabled — tail messages fire on network unkeys too")
        else:
            log_warn("AMI unavailable — falling back to CLI kerchunk counter (local RF only)")
    else:
        log_warn("No AMI credentials found in allmon3.ini or manager.conf")
        log_warn("Falling back to CLI kerchunk counter (local RF unkeys only)")

    # CLI fallback: seed kerchunk counter for midnight-rollover detection
    last_kerchunks = 0
    if ami is None:
        out = asterisk_cmd(f"rpt stats {node}")
        for line in out.splitlines():
            if "Kerchunks today" in line:
                try:
                    last_kerchunks = int(line.split(":")[-1].strip())
                except ValueError:
                    pass
        log_info(f"Node: {node} | Poll: {POLL_INTERVAL}s | Min interval: {min_int}s")
        log_info(f"Initial kerchunk count: {last_kerchunks}")
    else:
        log_info(f"Node: {node} | Poll: {POLL_INTERVAL}s | Min interval: {min_int}s")

    if swp_on:
        log_info(f"SkywarnPlus integration enabled ({swp_file})")
    if rotation:
        log_info(f"Rotation: {len(rotation)} message(s)")
    if scheduled:
        log_info(f"Scheduled: {len(scheduled)} announcement(s)")

    # AMI-based unkey detection: track keyed state transitions
    last_rx_keyed   = False
    last_conn_keyed = False

    disabled_logged = False
    reload_flag = [False]

    def handle_sighup(sig, frame):
        reload_flag[0] = True

    signal.signal(signal.SIGHUP, handle_sighup)

    while True:
        try:
            # ── Config reload (SIGHUP) ────────────────────────────────────
            if reload_flag[0]:
                reload_flag[0] = False
                log_info("Reloading config (SIGHUP)")
                config = load_config()
                cfg    = extract_config(config)
                node            = cfg["node"]
                DEBUG           = cfg["debug"]
                tm_on           = cfg["tm_on"]
                min_int         = cfg["min_int"]
                rotation        = cfg["rotation"]
                network_trigger = cfg["network_trigger"]
                swp_on          = cfg["swp_on"]
                swp_file        = cfg["swp_file"]
                swp_thr         = cfg["swp_thr"]
                scheduled       = cfg["scheduled"]
                timeweather     = cfg["timeweather"]
                # Re-read AMI credentials from system files on SIGHUP so changes
                # to allmon3.ini or manager.conf are picked up automatically.
                new_host, new_port, new_user, new_secret = load_ami_credentials()
                if (new_user != ami_user or new_secret != ami_secret
                        or new_host != ami_host or new_port != ami_port):
                    if ami:
                        ami.close()
                        ami = None
                    ami_host   = new_host
                    ami_port   = new_port
                    ami_user   = new_user
                    ami_secret = new_secret
                    if ami_user:
                        ami = _ami_connect(ami_host, ami_port, ami_user, ami_secret)
                        if ami:
                            log_info("AMI reconnected after credential change")
                        else:
                            log_warn("AMI reconnect failed — continuing in CLI fallback mode")
                log_info("Config reloaded")

            # ── Disabled flag ─────────────────────────────────────────────
            if os.path.exists(DISABLE_FLAG):
                if not disabled_logged:
                    log_info("Herald disabled - tail messages suppressed")
                    disabled_logged = True
                time.sleep(POLL_INTERVAL)
                continue
            elif disabled_logged:
                log_info("Herald re-enabled")
                disabled_logged = False

            # ── Asterisk availability ─────────────────────────────────────
            if not asterisk_available():
                log_warn("Asterisk not responding - waiting")
                time.sleep(10)
                continue

            now    = time.time()
            now_dt = datetime.now()

            # ── Poll AMI / CLI for keyup state ────────────────────────────
            unkey_detected = False

            if ami is not None:
                try:
                    rx_keyed, conn_keyed = _poll_ami(ami, node)

                    # Local RF unkey: RPT_RXKEYED 1 → 0
                    local_unkey = last_rx_keyed and not rx_keyed
                    # Network unkey: any connected node PTT 1 → 0
                    net_unkey = network_trigger and last_conn_keyed and not conn_keyed

                    if local_unkey:
                        log_debug("Local RF unkey detected (RPT_RXKEYED 1→0)")
                    if net_unkey:
                        log_debug("Network unkey detected (CONNKEYED 1→0)")

                    last_rx_keyed   = rx_keyed
                    last_conn_keyed = conn_keyed
                    unkey_detected  = local_unkey or net_unkey

                except Exception as e:
                    log_warn(f"AMI poll error: {e} — reconnecting")
                    _ami_up = False
                    try:
                        ami.close()
                    except Exception:
                        pass
                    ami = _ami_connect(ami_host, ami_port, ami_user, ami_secret)
                    if ami:
                        log_info("AMI reconnected")
                    else:
                        log_warn("AMI reconnect failed — skipping unkey detection this cycle")
                    unkey_detected = False

            else:
                # CLI fallback — kerchunk counter (local RF unkey only)
                _ami_up = False
                out = asterisk_cmd(f"rpt stats {node}")
                cur = None
                for line in out.splitlines():
                    if "Kerchunks today" in line:
                        try:
                            cur = int(line.split(":")[-1].strip())
                        except ValueError:
                            pass

                if cur is not None:
                    if cur < last_kerchunks:
                        log_debug("Kerchunk counter rolled over at midnight - reseeding")
                        last_kerchunks = cur
                    if cur > last_kerchunks:
                        last_kerchunks = cur
                        log_debug(f"Unkey detected (kerchunks now {cur})")
                        unkey_detected = True

            # ── Hourly Time & Weather (highest priority, time-driven) ──────
            # Checked before Scheduled Announcements so it always plays first
            # if both are due at the same moment; should_play_scheduled()
            # defers any Scheduled entry until timeweather_busy_until clears.
            if should_play_timeweather(timeweather, state, node, now_dt):
                play_timeweather(timeweather, state, node, now, now_dt)

            # ── Scheduled announcements (time-driven) ─────────────────────
            for sched in scheduled:
                if should_play_scheduled(sched, state, node, now_dt):
                    name = sched.get("Name", sched.get("File", ""))
                    log_info(f"Scheduled announcement: {name}")
                    target_node = str(sched["Node"]) if sched.get("Node") else node
                    play_mode   = sched.get("PlayMode", "local")
                    play_file(target_node, sched["File"], play_mode)
                    log_playback(state, "scheduled", name, sched["File"], target_node, play_mode)
                    state["scheduled_played"][sched.get("Name", "")] = now_dt.strftime("%Y-%m-%d %H:%M")
                    state["scheduled_pending"].pop(sched.get("Name", ""), None)
                    duration = audio_duration(sched["File"]) or DEFAULT_ANNOUNCEMENT_DURATION
                    state["scheduled_busy_until"] = now + min(duration, MAX_BUSY_SECONDS) + BUSY_GRACE_SECONDS
                    save_state(state)

            # ── Tail messages (unkey-driven) ───────────────────────────────
            if tm_on and unkey_detected:
                swp_active = swp_on and wx_is_active(swp_file, swp_thr)
                if not swp_active:
                    state["swp_next_is_rotation"] = False
                    state["swp_last_mtime"] = None

                if (now - state["last_tail_played"]) < min_int:
                    remaining = int(min_int - (now - state["last_tail_played"]))
                    log_debug(f"Min interval not reached - {remaining}s remaining")

                elif now < state.get("scheduled_busy_until", 0):
                    log_info("Scheduled announcement in progress - delaying tail message to next unkey")

                elif swp_active:
                    try:
                        swp_mtime = os.path.getmtime(swp_file)
                    except OSError:
                        swp_mtime = None
                    is_new_alert = swp_mtime is not None and swp_mtime != state.get("swp_last_mtime")

                    if is_new_alert:
                        log_info("Playing SkywarnPlus WX tail message (new/changed alert)")
                        play_file(node, swp_file)
                        log_playback(state, "wx", "SkywarnPlus WX Alert", swp_file, node)
                        state["swp_last_mtime"]     = swp_mtime
                        state["swp_next_is_rotation"] = True
                        state["last_tail_played"]   = now
                        save_state(state)

                    elif rotation and state.get("swp_next_is_rotation"):
                        eligible = [e for e in rotation if rotation_entry_eligible(e, now_dt)]
                        if eligible:
                            idx      = state["rotation_index"] % len(eligible)
                            entry    = eligible[idx]
                            filepath = rotation_entry_file(entry)
                            if os.path.exists(filepath):
                                log_info(f"Playing rotation [{idx + 1}/{len(eligible)}] (alternating with active WX alert): {Path(filepath).name}")
                                target_node = rotation_entry_node(entry, node)
                                play_file(target_node, filepath)
                                log_playback(state, "rotation", Path(filepath).name, filepath, target_node)
                                state["rotation_index"]       = (idx + 1) % len(eligible)
                                state["swp_next_is_rotation"] = False
                                state["last_tail_played"]     = now
                                save_state(state)
                            else:
                                log_warn(f"Rotation file not found: {filepath} - playing WX alert instead")
                                play_file(node, swp_file)
                                log_playback(state, "wx", "SkywarnPlus WX Alert", swp_file, node)
                                state["last_tail_played"] = now
                                save_state(state)
                        else:
                            log_debug("No rotation entries eligible right now - playing WX alert instead")
                            play_file(node, swp_file)
                            log_playback(state, "wx", "SkywarnPlus WX Alert", swp_file, node)
                            state["last_tail_played"] = now
                            save_state(state)

                    else:
                        log_info("Playing SkywarnPlus WX tail message (alternating)")
                        play_file(node, swp_file)
                        log_playback(state, "wx", "SkywarnPlus WX Alert", swp_file, node)
                        state["swp_next_is_rotation"] = True
                        state["last_tail_played"] = now
                        save_state(state)

                elif rotation:
                    eligible = [e for e in rotation if rotation_entry_eligible(e, now_dt)]
                    if eligible:
                        idx      = state["rotation_index"] % len(eligible)
                        entry    = eligible[idx]
                        filepath = rotation_entry_file(entry)
                        if os.path.exists(filepath):
                            log_info(f"Playing rotation [{idx + 1}/{len(eligible)}]: {Path(filepath).name}")
                            target_node = rotation_entry_node(entry, node)
                            play_file(target_node, filepath)
                            log_playback(state, "rotation", Path(filepath).name, filepath, target_node)
                            state["rotation_index"]   = (idx + 1) % len(eligible)
                            state["last_tail_played"] = now
                            save_state(state)
                        else:
                            log_warn(f"Rotation file not found: {filepath}")
                    else:
                        log_debug("No rotation entries eligible right now (day/time-window gating)")
                else:
                    log_debug("No tail messages configured - skipping")

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            log_info("Shutting down")
            if ami:
                ami.close()
            sys.exit(0)
        except Exception as e:
            log_error(f"Unexpected error: {e}")
            for line in traceback.format_exc().splitlines():
                log_error(line)
            time.sleep(5)


if __name__ == "__main__":
    cli_main()
