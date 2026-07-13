#!/usr/bin/python3
"""
asl3-herald - Enhanced Tail Message & Announcement Daemon for ASL3/app_rpt
https://github.com/N6LKA/asl3-herald

Replaces and enhances the native app_rpt tail message function with reliable
unkey detection, rotating messages, SkywarnPlus WX integration, and scheduled
announcements.
"""

import os
import sys
import time
import json
import signal
import socket
import argparse
import subprocess
import traceback
import configparser
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

def scheduled_time_matches(sched, now):
    if now.strftime("%H:%M") != sched.get("Time", ""):
        return False

    days = sched.get("Days", "daily")
    if days != "daily":
        day_list = [d.lower() for d in (days if isinstance(days, list) else [days])]
        if now.strftime("%A").lower() not in day_list:
            return False

    week = sched.get("Week")
    if week:
        try:
            week = int(week)
        except (TypeError, ValueError):
            week = None
        if week in (1, 2, 3, 4, 5):
            low, high = week_of_month_range(week)
            if not (low <= now.day <= high):
                return False

    return True

def should_play_scheduled(sched, state, node, now):
    name = sched.get("Name", "")
    date = now.strftime("%Y-%m-%d")

    if state["scheduled_played"].get(name) == date:
        return False

    already_pending = state["scheduled_pending"].get(name) == date
    if not already_pending and not scheduled_time_matches(sched, now):
        return False

    filepath = sched.get("File", "")
    if not filepath or not os.path.exists(filepath):
        log_warn(f"Scheduled file not found: {filepath}  ({name})")
        return False

    entry_node = sched.get("Node")
    target_node = str(entry_node) if entry_node else node
    keyed = node_is_keyed(target_node)

    if keyed:
        if not already_pending:
            state["scheduled_pending"][name] = date
            log_info(f"Scheduled announcement '{name}' due but node {target_node} is keyed - waiting for unkey")
        else:
            log_debug(f"Scheduled announcement '{name}' still waiting for unkey")
        return False

    if already_pending:
        state["scheduled_pending"].pop(name, None)

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
    }

# ── CLI subcommands (used by the `herald` bash CLI and the web UI) ────────────

def normalize_rotation(rotation):
    out = []
    for e in rotation:
        if isinstance(e, str):
            entry = {"File": e, "Text": None, "Voice": None,
                      "Days": "daily", "TimeStart": None, "TimeEnd": None, "Node": None}
        else:
            entry = {
                "File": e.get("File", ""),
                "Text": e.get("Text"),
                "Voice": e.get("Voice"),
                "Days": e.get("Days", "daily"),
                "TimeStart": e.get("TimeStart"),
                "TimeEnd": e.get("TimeEnd"),
                "Node": e.get("Node"),
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
        out.append(s2)
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
        "Time": args.time,
        "Days": "daily" if args.days == "daily" else [d.strip().lower() for d in args.days.split(",")],
        "File": args.file,
        "PlayMode": args.play_mode or "local",
    }
    if args.week:
        entry["Week"] = int(args.week)
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
    entry["Name"] = new_name
    if args.time is not None:
        entry["Time"] = args.time
    if args.days is not None:
        entry["Days"] = "daily" if args.days == "daily" else [d.strip().lower() for d in args.days.split(",")]
    if args.week is not None:
        if args.week == "":
            entry.pop("Week", None)
        else:
            try:
                entry["Week"] = int(args.week)
            except ValueError:
                pass
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
    p_add_sched.add_argument("--time", required=True)
    p_add_sched.add_argument("--days", default="daily")
    p_add_sched.add_argument("--week", default=None)
    p_add_sched.add_argument("--file", required=True)
    p_add_sched.add_argument("--play-mode", dest="play_mode", choices=["local", "global"], default="local")
    p_add_sched.add_argument("--text", default=None)
    p_add_sched.add_argument("--voice", default=None)
    p_add_sched.add_argument("--node", default=None)

    p_edit_sched = sub.add_parser("edit-scheduled", help="Edit an existing scheduled announcement")
    p_edit_sched.add_argument("old_name")
    p_edit_sched.add_argument("--new-name", dest="new_name", default=None)
    p_edit_sched.add_argument("--time", default=None)
    p_edit_sched.add_argument("--days", default=None)
    p_edit_sched.add_argument("--week", default=None)
    p_edit_sched.add_argument("--play-mode", dest="play_mode", choices=["local", "global"], default=None)
    p_edit_sched.add_argument("--text", default=None)
    p_edit_sched.add_argument("--voice", default=None)
    p_edit_sched.add_argument("--file", default=None)
    p_edit_sched.add_argument("--node", default=None)

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

            # ── Scheduled announcements (time-driven) ─────────────────────
            for sched in scheduled:
                if should_play_scheduled(sched, state, node, now_dt):
                    name = sched.get("Name", sched.get("File", ""))
                    log_info(f"Scheduled announcement: {name}")
                    target_node = str(sched["Node"]) if sched.get("Node") else node
                    play_mode   = sched.get("PlayMode", "local")
                    play_file(target_node, sched["File"], play_mode)
                    log_playback(state, "scheduled", name, sched["File"], target_node, play_mode)
                    state["scheduled_played"][sched.get("Name", "")] = now_dt.strftime("%Y-%m-%d")
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
