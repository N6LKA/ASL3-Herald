#!/usr/bin/python3
"""
asl3-herald - Enhanced Tail Message & Announcement Daemon for ASL3/app_rpt
https://github.com/N6LKA/asl3-herald

Replaces and enhances the native app_rpt tail message function with reliable
unkey detection, rotating messages, SkywarnPlus WX integration, scheduled
announcements, and blackout windows.
"""

import os
import sys
import time
import json
import signal
import subprocess
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

# ── State ─────────────────────────────────────────────────────────────────────

def load_state():
    defaults = {
        "rotation_index": 0,
        "last_tail_played": 0.0,
        "scheduled_played": {}
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

def get_kerchunk_count(node):
    out = asterisk_cmd(f"rpt stats {node}")
    for line in out.splitlines():
        if "Kerchunks today" in line:
            try:
                return int(line.split(":")[-1].strip())
            except ValueError:
                pass
    return None

def play_file(node, filepath):
    path_no_ext = str(Path(filepath).with_suffix(""))
    log_info(f"Playing: {Path(filepath).name} on node {node}")
    asterisk_cmd(f"rpt localplay {node} {path_no_ext}")

# ── Helpers ───────────────────────────────────────────────────────────────────

def in_blackout(start, end):
    if not start or not end:
        return False
    now = datetime.now().strftime("%H:%M")
    if start <= end:
        return start <= now < end
    return now >= start or now < end  # overnight span

def wx_is_active(wx_file, threshold):
    if not wx_file or not os.path.exists(wx_file):
        return False
    return os.path.getsize(wx_file) > threshold

def should_play_scheduled(sched, state):
    now   = datetime.now()
    hhmm  = now.strftime("%H:%M")
    today = now.strftime("%A").lower()
    date  = now.strftime("%Y-%m-%d")

    if hhmm != sched.get("Time", ""):
        return False

    days = sched.get("Days", "daily")
    if days != "daily":
        day_list = [d.lower() for d in (days if isinstance(days, list) else [days])]
        if today not in day_list:
            return False

    filepath = sched.get("File", "")
    if not filepath or not os.path.exists(filepath):
        log_warn(f"Scheduled file not found: {filepath}  ({sched.get('Name', '')})")
        return False

    key = sched.get("Name", "")
    if state["scheduled_played"].get(key) == f"{date} {hhmm}":
        return False

    return True

# ── Config extraction helper ──────────────────────────────────────────────────

def extract_config(config):
    node = str(config.get("Node", "")).strip()
    poll = config.get("PollInterval", 2)
    debug = config.get("Debug", False)

    tm       = config.get("TailMessage", {}) or {}
    tm_on    = tm.get("Enable", True)
    min_int  = tm.get("MinInterval", 300)
    rotation = tm.get("Rotation", []) or []
    bk_start = tm.get("BlackoutStart", "") or ""
    bk_end   = tm.get("BlackoutEnd",   "") or ""

    swp      = tm.get("SkywarnPlus", {}) or {}
    swp_on   = swp.get("Enable", False)
    swp_file = swp.get("WxTailFile", "/tmp/SkywarnPlus/wx-tail.wav")
    swp_thr  = swp.get("SilenceThreshold", 5000)

    scheduled = config.get("Scheduled", []) or []

    return (node, poll, debug, tm_on, min_int, rotation,
            bk_start, bk_end, swp_on, swp_file, swp_thr, scheduled)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global DEBUG

    log_info(f"asl3-herald v{VERSION} starting")

    config = load_config()
    (node, poll, DEBUG, tm_on, min_int, rotation,
     bk_start, bk_end, swp_on, swp_file, swp_thr, scheduled) = extract_config(config)

    if not node:
        log_error("Node not set in config. Exiting.")
        sys.exit(1)

    state = load_state()

    last_kerchunks = get_kerchunk_count(node) or 0
    log_info(f"Node: {node} | Poll: {poll}s | Min interval: {min_int}s")
    log_info(f"Initial kerchunk count: {last_kerchunks}")
    if swp_on:
        log_info(f"SkywarnPlus integration enabled ({swp_file})")
    if rotation:
        log_info(f"Rotation: {len(rotation)} message(s)")
    if scheduled:
        log_info(f"Scheduled: {len(scheduled)} announcement(s)")
    if bk_start and bk_end:
        log_info(f"Blackout window: {bk_start} - {bk_end}")

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
                (node, poll, DEBUG, tm_on, min_int, rotation,
                 bk_start, bk_end, swp_on, swp_file, swp_thr, scheduled) = extract_config(config)
                log_info("Config reloaded")

            # ── Disabled flag ─────────────────────────────────────────────
            if os.path.exists(DISABLE_FLAG):
                if not disabled_logged:
                    log_info("Herald disabled - tail messages suppressed")
                    disabled_logged = True
                time.sleep(poll)
                continue
            elif disabled_logged:
                log_info("Herald re-enabled")
                disabled_logged = False

            # ── Asterisk availability ─────────────────────────────────────
            if not asterisk_available():
                log_warn("Asterisk not responding - waiting")
                time.sleep(10)
                continue

            now = time.time()

            # ── Scheduled announcements (time-driven) ─────────────────────
            for sched in scheduled:
                if should_play_scheduled(sched, state):
                    log_info(f"Scheduled announcement: {sched.get('Name', sched.get('File', ''))}")
                    play_file(node, sched["File"])
                    key = sched.get("Name", "")
                    dt  = datetime.now()
                    state["scheduled_played"][key] = f"{dt.strftime('%Y-%m-%d')} {dt.strftime('%H:%M')}"
                    save_state(state)

            # ── Kerchunk / tail message (unkey-driven) ────────────────────
            if tm_on:
                cur = get_kerchunk_count(node)

                if cur is not None:
                    # Midnight rollover
                    if cur < last_kerchunks:
                        log_debug("Kerchunk counter rolled over at midnight - reseeding")
                        last_kerchunks = cur

                    if cur > last_kerchunks:
                        last_kerchunks = cur
                        log_debug(f"Unkey detected (kerchunks now {cur})")

                        if in_blackout(bk_start, bk_end):
                            log_debug("Blackout window active - skipping tail message")

                        elif (now - state["last_tail_played"]) < min_int:
                            remaining = int(min_int - (now - state["last_tail_played"]))
                            log_debug(f"Min interval not reached - {remaining}s remaining")

                        elif swp_on and wx_is_active(swp_file, swp_thr):
                            log_info("Playing SkywarnPlus WX tail message (priority)")
                            play_file(node, swp_file)
                            state["last_tail_played"] = now
                            save_state(state)

                        elif rotation:
                            idx      = state["rotation_index"] % len(rotation)
                            filepath = rotation[idx]
                            if os.path.exists(filepath):
                                log_info(f"Playing rotation [{idx + 1}/{len(rotation)}]: {Path(filepath).name}")
                                play_file(node, filepath)
                                state["rotation_index"]   = (idx + 1) % len(rotation)
                                state["last_tail_played"] = now
                                save_state(state)
                            else:
                                log_warn(f"Rotation file not found: {filepath}")
                        else:
                            log_debug("No tail messages configured - skipping")

            time.sleep(poll)

        except KeyboardInterrupt:
            log_info("Shutting down")
            sys.exit(0)
        except Exception as e:
            log_error(f"Unexpected error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
