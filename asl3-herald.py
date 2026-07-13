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
import traceback
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: sudo apt install python3-yaml", flush=True)
    sys.exit(1)

# ── Paths ────────────────────────────────────────────────────────────────────────────────

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
# takes to play, used only if `soxi` can't determine the real duration -
# governs how long tail messages are held off after a scheduled announcement
# starts (see scheduled_busy_until in state).
DEFAULT_ANNOUNCEMENT_DURATION = 8.0
BUSY_GRACE_SECONDS = 1.5
# Hard ceiling on how long a single scheduled announcement can hold off tail
# messages, regardless of its real/estimated duration - a corrupt file or a
# bad soxi reading must never be able to wedge scheduled_busy_until far into
# the future and silence tail messages (and SkywarnPlus) indefinitely.
MAX_BUSY_SECONDS = 60.0

# How many playback events to keep in state["playback_history"] - old entries
# are trimmed off the front so the state file can't grow unbounded.
MAX_PLAYBACK_HISTORY = 200

# ── Logging ──────────────────────────────────────────────────────────────────────────────

def log(level, msg):
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [{level}] {msg}", flush=True)

def log_info(msg):  log("INFO",  msg)
def log_warn(msg):  log("WARN",  msg)
def log_error(msg): log("ERROR", msg)
def log_debug(msg):
    if DEBUG:
        log("DEBUG", msg)

# ── Config ────────────────────────────────────────────────────────────────────────────────

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

# ── State ────────────────────────────────────────────────────────────────────────────────

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

# ── Asterisk ──────────────────────────────────────────────────────────────────────────────

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

def node_is_keyed(node):
    # Best-effort real-time carrier/keyed detection via `rpt stats`'s
    # "Signal on input" field (reflects live COS/carrier state, distinct from
    # the Kerchunks counter which only increments after an unkey completes).
    # Returns True/False, or None if the field can't be found (parsing
    # failure, unexpected app_rpt version, etc.) - callers should treat None
    # as "unknown, don't block" so a missing field fails open rather than
    # wedging scheduled playback indefinitely.
    out = asterisk_cmd(f"rpt stats {node}")
    for line in out.splitlines():
        if "Signal on input" in line:
            value = line.split(":")[-1].strip().upper()
            return value.startswith("YES")
    return None

def audio_duration(filepath):
    try:
        r = subprocess.run(["soxi", "-D", filepath], capture_output=True, text=True, timeout=5)
        duration = float(r.stdout.strip())
        # A corrupt/garbage file could make soxi report 0, negative, or an
        # absurdly large number - fall back to the default rather than
        # trusting it, same reasoning as MAX_BUSY_SECONDS below.
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

# ── Helpers ──────────────────────────────────────────────────────────────────────────────

def rotation_entry_file(entry):
    # Rotation entries were originally plain filepath strings; entries added
    # or edited since also carry Text/Voice metadata (for re-editing TTS
    # announcements) as a dict. Both forms can coexist in one config.
    return entry if isinstance(entry, str) else entry.get("File", "")

def wx_is_active(wx_file, threshold):
    if not wx_file or not os.path.exists(wx_file):
        return False
    return os.path.getsize(wx_file) > threshold

def week_of_month_range(week):
    # week: 1-5 (5 = last week, runs through end of month)
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
    # Optional HH:MM-HH:MM eligibility window for rotation entries (Days is
    # the same idea but for day-of-week rather than time-of-day). Absent
    # Start/End means "always eligible", matching plain legacy string entries.
    if not isinstance(entry, dict):
        return True
    start = entry.get("TimeStart")
    end = entry.get("TimeEnd")
    if not start and not end:
        return True
    hhmm = now.strftime("%H:%M")
    if start and end:
        if start <= end:
            return start <= hhmm <= end
        return hhmm >= start or hhmm <= end  # window wraps past midnight
    if start:
        return hhmm >= start
    return hhmm <= end

def rotation_entry_eligible(entry, now):
    # Node is a playback-target override (see rotation_entry_node()), not an
    # eligibility gate - an entry with Node set still plays on its normal
    # schedule, just directed at a different node number.
    if not entry_days_ok(entry, now):
        return False
    if not entry_time_window_ok(entry, now):
        return False
    return True

def rotation_entry_node(entry, node):
    entry_node = entry.get("Node") if isinstance(entry, dict) else None
    return str(entry_node) if entry_node else node

def log_playback(state, entry_type, name, filepath, node, play_mode="local"):
    # entry_type: "rotation" | "wx" | "scheduled" | "test" (manual play from
    # the CLI/web UI). Kept in state (not a separate file) since writes only
    # happen on actual play events, not every poll cycle.
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
    # Once an entry's Time/Days/Week condition matches but the node is
    # keyed (someone's actively transmitting), it goes "pending" instead of
    # being skipped outright - it keeps getting re-checked every poll cycle
    # (even after the matching minute has passed) until it can finally play,
    # rather than silently missing the announcement for the day.
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

# ── Config extraction helper ──────────────────────────────────────────────────────────────────────

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

# ── CLI subcommands (used by the `herald` bash CLI and the web UI) ──────────────────────

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
    (node, poll, debug, tm_on, min_int, rotation,
     swp_on, swp_file, swp_thr, scheduled) = extract_config(config)
    tm = config.get("TailMessage") or {}
    out = {
        "node": node,
        "poll_interval": poll,
        "debug": debug,
        "herald_enabled": not os.path.exists(DISABLE_FLAG),
        "version": VERSION,
        "tail_message": {
            "enable": tm_on,
            "min_interval": min_int,
            "network_keyup_trigger": tm.get("NetworkKeyupTrigger", False),
            "rotation": normalize_rotation(rotation),
            "skywarnplus": {
                "enable": swp_on,
                "wx_tail_file": swp_file,
                "silence_threshold": swp_thr,
            },
        },
        "scheduled": scheduled_with_health(scheduled),
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
    print(json.dumps({"success": True, "message": f"Updated rotation entry: {os.path.basename(entry.get('File', ''))"}))

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
        if args.week:
            entry["Week"] = int(args.week)
        else:
            entry.pop("Week", None)
    if args.play_mode is not None:
        entry["PlayMode"] = args.play_mode
    if args.file is not None:
        entry["File"] = args.file
    if args.text is not None:
        entry["Text"] = args.text
    if args.voice is not None:
        entry["Voice"] = args.voice
    if args.node is not None:
        if args.node:
            entry["Node"] = args.node
        else:
            entry.pop("Node", None)

    scheduled[idx] = entry
    save_config(config)
    print(json.dumps({"success": True, "message": f"Updated scheduled announcement: {new_name}"}))

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
    for i, entry in enumerate(rotation):
        filepath = rotation_entry_file(entry)
        base = os.path.basename(filepath)
        base_noext = os.path.splitext(base)[0]
        if base == target or base_noext == target_noext:
            rotation.pop(i)
            save_config(config)
            print(json.dumps({"success": True, "type": "rotation",
                               "message": f"Removed from rotation: {filepath}"}))
            return

    print(json.dumps({"success": False, "message": f"No match found for: {identifier}"}))

def cmd_reorder_rotation(config, args):
    tm = config.setdefault("TailMessage", {})
    rotation = tm.setdefault("Rotation", [])

    target = os.path.basename(args.name)
    target_noext = os.path.splitext(target)[0]
    idx = None
    for i, e in enumerate(rotation):
        base = os.path.basename(rotation_entry_file(e))
        base_noext = os.path.splitext(base)[0]        
        if base == target or base_noext == target_noext:
            idx = i
            break

    if idx is None:
        print(json.dumps({"success": False, "message": f"No rotation entry found for: {args.name}"}))
        return

    if args.direction == "up":
        if idx == 0:
            print(json.dumps({"success": False, "message": "Already first in rotation"}))
            return
        rotation[idx - 1], rotation[idx] = rotation[idx], rotation[idx - 1]
    else:
        if idx == len(rotation) - 1:
            print(json.dumps({"success": False, "message": "Already last in rotation"}))
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
    if args.poll_interval is not None:
        config["PollInterval"] = args.poll_interval
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
    p_add_rot.add_argument("--days", default="daily", help='"daily" or comma-separated day names')
    p_add_rot.add_argument("--time-start", dest="time_start", default=None, help="HH:MM - only eligible at/after this time")
    p_add_rot.add_argument("--time-end", dest="time_end", default=None, help="HH:MM - only eligible at/before this time")
    p_add_rot.add_argument("--node", default=None, help="Target a specific node number instead of the daemon's configured Node")

    p_edit_rot = sub.add_parser("edit-rotation", help="Edit an existing tail message rotation entry")
    p_edit_rot.add_argument("old_name")
    p_edit_rot.add_argument("--new-name", dest="new_name", default=None)
    p_edit_rot.add_argument("--text", default=None)
    p_edit_rot.add_argument("--voice", default=None)
    p_edit_rot.add_argument("--file", default=None)
    p_edit_rot.add_argument("--days", default=None, help='"daily" (or empty) clears it, or comma-separated day names')
    p_edit_rot.add_argument("--time-start", dest="time_start", default=None, help="HH:MM, empty string clears it")
    p_edit_rot.add_argument("--time-end", dest="time_end", default=None, help="HH:MM, empty string clears it")
    p_edit_rot.add_argument("--node", default=None, help="Node number override, empty string clears it")

    p_add_sched = sub.add_parser("add-scheduled", help="Add a scheduled announcement")
    p_add_sched.add_argument("--name", required=True)
    p_add_sched.add_argument("--time", required=True, help="HH:MM 24-hour")
    p_add_sched.add_argument("--days", default="daily", help='"daily" or comma-separated day names')
    p_add_sched.add_argument("--week", default=None, help="1-5 (5 = last week of month)")
    p_add_sched.add_argument("--file", required=True)
    p_add_sched.add_argument("--play-mode", dest="play_mode", choices=["local", "global"], default="local")
    p_add_sched.add_argument("--text", default=None)
    p_add_sched.add_argument("--voice", default=None)
    p_add_sched.add_argument("--node", default=None, help="Target a specific node number instead of the daemon's configured Node")

    p_edit_sched = sub.add_parser("edit-scheduled", help="Edit an existing scheduled announcement")
    p_edit_sched.add_argument("old_name")
    p_edit_sched.add_argument("--new-name", dest="new_name", default=None)
    p_edit_sched.add_argument("--time", default=None)
    p_edit_sched.add_argument("--days", default=None)
    p_edit_sched.add_argument("--week", default=None, help="1-5 (5 = last week of month), empty string clears it")
    p_edit_sched.add_argument("--play-mode", dest="play_mode", choices=["local", "global"], default=None)
    p_edit_sched.add_argument("--text", default=None)
    p_edit_sched.add_argument("--voice", default=None)
    p_edit_sched.add_argument("--file", default=None)
    p_edit_sched.add_argument("--node", default=None, help="Node number override, empty string clears it")

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

    sub.add_parser("clear-history", help="Clear the playback history")

    sub.add_parser("export-config", help="Export the full daemon config as JSON (for backup)")

    p_import = sub.add_parser("import-config", help="Restore the full daemon config from an exported JSON file")
    p_import.add_argument("file")

    p_settings = sub.add_parser("update-settings", help="Update general daemon settings")
    p_settings.add_argument("--node")
    p_settings.add_argument("--poll-interval", type=int)
    p_settings.add_argument("--debug", choices=["true", "false"])
    p_settings.add_argument("--min-interval", type=int)
    p_settings.add_argument("--network-keyup-trigger", choices=["true", "false"])
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

# ── Main ────────────────────────────────────────────────────────────────────────────────

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
            # ── Config reload (SIGHUP) ────────────────────────────────────────────────
            if reload_flag[0]:
                reload_flag[0] = False
                log_info("Reloading config (SIGHUP)")
                config = load_config()
                (node, poll, DEBUG, tm_on, min_int, rotation,
                 swp_on, swp_file, swp_thr, scheduled) = extract_config(config)
                log_info("Config reloaded")

            # ── Disabled flag ───────────────────────────────────────────────────────────────
            if os.path.exists(DISABLE_FLAG):
                if not disabled_logged:
                    log_info("Herald disabled - tail messages suppressed")
                    disabled_logged = True
                time.sleep(poll)
                continue
            elif disabled_logged:
                log_info("Herald re-enabled")
                disabled_logged = False

            # ── Asterisk availability ────────────────────────────────────────────────────────
            if not asterisk_available():
                log_warn("Asterisk not responding - waiting")
                time.sleep(10)
                continue

            now    = time.time()
            now_dt = datetime.now()

            # ── Scheduled announcements (time-driven) ─────────────────────────────────────────
            # Checked before tail messages every iteration: a scheduled
            # announcement takes precedence if both would fire at once. Once
            # one plays, scheduled_busy_until holds off the tail-message
            # block below for the announcement's (estimated) duration, so a
            # simultaneous unkey doesn't overlap it - the tail message just
            # doesn't update last_tail_played, so it naturally retries on
            # the next unkey once MinInterval allows, with no penalty.
            for sched in scheduled:
                if should_play_scheduled(sched, state, node, now_dt):
                    name = sched.get("Name", sched.get("File", ""))
                    log_info(f"Scheduled announcement: {name}")
                    target_node = str(sched["Node"]) if sched.get("Node") else node
                    play_mode = sched.get("PlayMode", "local")
                    play_file(target_node, sched["File"], play_mode)
                    log_playback(state, "scheduled", name, sched["File"], target_node, play_mode)
                    state["scheduled_played"][sched.get("Name", "")] = now_dt.strftime("%Y-%m-%d")
                    state["scheduled_pending"].pop(sched.get("Name", ""), None)
                    duration = audio_duration(sched["File"]) or DEFAULT_ANNOUNCEMENT_DURATION
                    state["scheduled_busy_until"] = now + min(duration, MAX_BUSY_SECONDS) + BUSY_GRACE_SECONDS
                    save_state(state)

            # ── Kerchunk / tail message (unkey-driven) ─────────────────────────────────────────
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

                        # A persistent WX alert would otherwise starve the rotation
                        # entirely (constant alerts are common for some users, e.g.
                        # in summer heat-warning season). Reset the alternation
                        # state as soon as there's no active alert, so a future
                        # alert always plays immediately the first time it appears.
                        swp_active = swp_on and wx_is_active(swp_file, swp_thr)
                        if not swp_active:
                            state["swp_next_is_rotation"] = False
                            state["swp_last_mtime"] = None

                        if (now - state["last_tail_played"]) < min_int:
                            remaining = int(min_int - (now - state["last_tail_played"]))
                            log_debug(f"Min interval not reached - {remaining}s remaining")

                        elif now < state.get("scheduled_busy_until", 0):
                            # A scheduled announcement just started (or is about to,
                            # having been checked earlier this same iteration) -
                            # it takes precedence. Deliberately not touching
                            # last_tail_played here, so this unkey doesn't cost
                            # anything against MinInterval - it just tries again
                            # on the next unkey once the announcement has finished.
                            # Logged at INFO (not DEBUG) since this is a rare,
                            # notable event worth seeing without enabling Debug.
                            log_info("Scheduled announcement in progress - delaying tail message to next unkey")

                        elif swp_active:
                            try:
                                swp_mtime = os.path.getmtime(swp_file)
                            except OSError:
                                swp_mtime = None
                            is_new_alert = swp_mtime is not None and swp_mtime != state.get("swp_last_mtime")

                            if is_new_alert:
                                # New/changed alert always plays immediately,
                                # regardless of whose turn it was.
                                log_info("Playing SkywarnPlus WX tail message (new/changed alert)")
                                play_file(node, swp_file)
                                log_playback(state, "wx", "SkywarnPlus WX Alert", swp_file, node)
                                state["swp_last_mtime"] = swp_mtime
                                state["swp_next_is_rotation"] = True
                                state["last_tail_played"] = now
                                save_state(state)

                            elif rotation and state.get("swp_next_is_rotation"):
                                # Same alert as before - alternate with the rotation
                                # instead of playing the WX tail on every unkey.
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
                                    log_debug("No rotation entries eligible right now (day/time-window gating) - playing WX alert instead")
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

            time.sleep(poll)

        except KeyboardInterrupt:
            log_info("Shutting down")
            sys.exit(0)
        except Exception as e:
            log_error(f"Unexpected error: {e}")
            for line in traceback.format_exc().splitlines():
                log_error(line)
            time.sleep(5)


if __name__ == "__main__":
    cli_main()
