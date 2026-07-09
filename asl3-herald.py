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
import argparse
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

# ── Logging ────────────────────────────────────────────────────────────────────

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
    # NOTE: this round-trips through PyYAML, which does not preserve comments.
    # Config files edited via the CLI/web UI will lose the explanatory
    # comments present in asl3-herald.conf.example after their first edit.
    with open(CONF_FILE, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

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

def wx_is_active(wx_file, threshold):
    if not wx_file or not os.path.exists(wx_file):
        return False
    return os.path.getsize(wx_file) > threshold

def week_of_month_range(week):
    # week: 1-5 (5 = last week, runs through end of month)
    low = (week - 1) * 7 + 1
    high = 31 if week == 5 else low + 6
    return low, high

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
    poll = config.get("PollInterval", 1)
    debug = config.get("Debug", False)

    tm       = config.get("TailMessage", {}) or {}
    tm_on    = tm.get("Enable", True)
    min_int  = tm.get("MinInterval", 300)
    rotation = tm.get("Rotation", []) or []

    swp      = tm.get("SkywarnPlus", {}) or {}
    swp_on   = swp.get("Enable", True)
    swp_file = swp.get("WxTailFile", "/tmp/SkywarnPlus/wx-tail.wav")
    swp_thr  = swp.get("SilenceThreshold", 5000)

    scheduled = config.get("Scheduled", []) or []

    return (node, poll, debug, tm_on, min_int, rotation,
            swp_on, swp_file, swp_thr, scheduled)

# ── CLI subcommands (used by the `herald` bash CLI and the web UI) ────────────

def cmd_list_json(config):
    (node, poll, debug, tm_on, min_int, rotation,
     swp_on, swp_file, swp_thr, scheduled) = extract_config(config)
    out = {
        "node": node,
        "poll_interval": poll,
        "debug": debug,
        "tail_message": {
            "enable": tm_on,
            "min_interval": min_int,
            "rotation": rotation,
            "skywarnplus": {
                "enable": swp_on,
                "wx_tail_file": swp_file,
                "silence_threshold": swp_thr,
            },
        },
        "scheduled": scheduled,
    }
    print(json.dumps(out, indent=2))

def cmd_add_rotation(config, filepath):
    tm = config.setdefault("TailMessage", {})
    rotation = tm.setdefault("Rotation", [])
    if filepath in rotation:
        print(json.dumps({"success": False, "message": f"Already in rotation: {filepath}"}))
        return
    rotation.append(filepath)
    save_config(config)
    print(json.dumps({"success": True, "message": f"Added to rotation: {filepath}"}))

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
    }
    if args.week:
        entry["Week"] = int(args.week)

    scheduled.append(entry)
    save_config(config)
    print(json.dumps({"success": True, "message": f"Added scheduled announcement: {args.name}"}))

def cmd_remove(config, identifier):
    tm = config.get("TailMessage", {}) or {}
    rotation = tm.get("Rotation", []) or []
    scheduled = config.get("Scheduled", []) or []

    for i, s in enumerate(scheduled):
        if s.get("Name") == identifier:
            del scheduled[i]
            save_config(config)
            print(json.dumps({"success": True, "type": "scheduled",
                               "message": f"Removed scheduled announcement: {identifier}"}))
            return

    target = os.path.basename(identifier)
    target_noext = os.path.splitext(target)[0]
    for i, filepath in enumerate(rotation):
        base = os.path.basename(filepath)
        base_noext = os.path.splitext(base)[0]
        if base == target or base_noext == target_noext:
            removed = rotation.pop(i)
            save_config(config)
            print(json.dumps({"success": True, "type": "rotation",
                               "message": f"Removed from rotation: {removed}"}))
            return

    print(json.dumps({"success": False, "message": f"No match found for: {identifier}"}))

def cmd_update_settings(config, args):
    if args.node is not None:
        config["Node"] = args.node
    if args.poll_interval is not None:
        config["PollInterval"] = args.poll_interval
    if args.debug is not None:
        config["Debug"] = (args.debug == "true")

    tm = config.setdefault("TailMessage", {})
    if args.min_interval is not None:
        tm["MinInterval"] = args.min_interval

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

    p_add_sched = sub.add_parser("add-scheduled", help="Add a scheduled announcement")
    p_add_sched.add_argument("--name", required=True)
    p_add_sched.add_argument("--time", required=True, help="HH:MM 24-hour")
    p_add_sched.add_argument("--days", default="daily", help='"daily" or comma-separated day names')
    p_add_sched.add_argument("--week", default=None, help="1-5 (5 = last week of month)")
    p_add_sched.add_argument("--file", required=True)

    p_remove = sub.add_parser("remove", help="Remove a rotation file or scheduled announcement by name")
    p_remove.add_argument("identifier")

    p_settings = sub.add_parser("update-settings", help="Update general daemon settings")
    p_settings.add_argument("--node")
    p_settings.add_argument("--poll-interval", type=int)
    p_settings.add_argument("--debug", choices=["true", "false"])
    p_settings.add_argument("--min-interval", type=int)
    p_settings.add_argument("--swp-enable", choices=["true", "false"])
    p_settings.add_argument("--swp-wxfile")
    p_settings.add_argument("--swp-threshold", type=int)

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
        cmd_add_rotation(config, args.filepath)
    elif args.command == "add-scheduled":
        cmd_add_scheduled(config, args)
    elif args.command == "remove":
        cmd_remove(config, args.identifier)
    elif args.command == "update-settings":
        cmd_update_settings(config, args)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global DEBUG

    log_info(f"asl3-herald v{VERSION} starting")

    config = load_config()
    (node, poll, DEBUG, tm_on, min_int, rotation,
     swp_on, swp_file, swp_thr, scheduled) = extract_config(config)

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
                 swp_on, swp_file, swp_thr, scheduled) = extract_config(config)
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

                        if (now - state["last_tail_played"]) < min_int:
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
    cli_main()
