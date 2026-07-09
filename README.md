# asl3-herald

![Version](https://img.shields.io/badge/version-1.1.0-blue)
![Release Date](https://img.shields.io/badge/released-2026--07--09-green)
![License](https://img.shields.io/badge/license-GPLv3-lightgrey)

**Enhanced tail message daemon for ASL3/app_rpt with advanced announcement features.**

`asl3-herald` is a drop-in replacement and enhancement for the native `app_rpt` tail message function. It provides reliable unkey detection, rotating messages, SkywarnPlus weather alert integration with priority playback, scheduled time-based announcements (including nth-week-of-month scheduling), neural TTS voices, and an optional web UI for Allmon3 and Supermon 7 — all things the built-in tail message either doesn't support or handles unreliably.

---

## What It Does

`asl3-herald` covers two distinct functions:

- **Tail Messages** — unkey-triggered, reactive to repeater activity:
  - **Reliable unkey detection** — polls the `rpt stats` kerchunk counter every 2 seconds to detect transmissions; not dependent on the inconsistent native tail message trigger
  - **Rotating messages** — cycles through a list of announcement files in order with a configurable minimum interval between plays
  - **SkywarnPlus WX integration** — when weather alerts are active, plays the SkywarnPlus `wx-tail.wav` file instead of the normal rotation (WX always takes priority)

- **Scheduled Announcements** — clock-triggered, independent of repeater activity:
  - Plays a specific file at a configured time of day, on selected days of the week
  - Optional nth-week-of-month scheduling (e.g. "2nd Saturday of the month")

Plus:
- **Piper neural TTS** — generate announcements from text with natural-sounding voices (6 included), with festival/espeak-ng as a fallback
- **Web UI** — optional browser-based management embedded in Allmon3 or Supermon 7, gated behind each app's own login
- **Instant disable/enable** — `herald toggle` / `herald enable` / `herald disable`, no config edits or restarts needed
- **Live config reload** — `herald reload` sends SIGHUP to pick up config changes immediately

---

## Installation

```bash
sudo bash <(curl -fsSL -H "Cache-Control: no-cache" https://raw.githubusercontent.com/N6LKA/asl3-herald/main/install.sh)
```

The installer will:
1. Install `python3-yaml`, `sox`, and `libsox-fmt-mp3` if not already present
2. Install Piper TTS 1.2.0 (binary + 6 voices) — this step downloads a few hundred MB and may take a few minutes
3. Copy `asl3-herald.py` to `/usr/local/bin/asl3-herald/`
4. Install the `herald` management command to `/usr/local/bin/herald`
5. Create `/etc/asterisk/scripts/asl3-herald/` with an example config (if no config exists)
6. Install and enable the `asl3-herald` systemd service
7. Install the web UI to `/var/www/html/asl3-herald/` — installs `apache2` + `php` first if neither Allmon3 nor Supermon is already present, then wires an Allmon3 iframe entry and/or a Supermon footer link if either is detected

**After installation:**

1. Edit the config: `sudo nano /etc/asterisk/scripts/asl3-herald/asl3-herald.conf`
2. Start the service: `sudo systemctl start asl3-herald`
3. Check it's running: `herald status`

---

## Configuration

Config file: `/etc/asterisk/scripts/asl3-herald/asl3-herald.conf`

| Setting | Default | Description |
|---|---|---|
| `Node` | _(required)_ | Your ASL3 node number |
| `PollInterval` | `2` | Seconds between kerchunk counter polls |
| `Debug` | `false` | Enable verbose debug logging |
| `TailMessage.Enable` | `true` | Enable/disable tail message function |
| `TailMessage.MinInterval` | `300` | Minimum seconds between tail messages |
| `TailMessage.Rotation` | _(empty)_ | List of WAV file paths to rotate through |
| `TailMessage.SkywarnPlus.Enable` | `true` | Enable SkywarnPlus WX tail integration |
| `TailMessage.SkywarnPlus.WxTailFile` | `/tmp/SkywarnPlus/wx-tail.wav` | Path to SkywarnPlus wx-tail.wav |
| `TailMessage.SkywarnPlus.SilenceThreshold` | `5000` | File size (bytes) to distinguish active alerts from silence |
| `Scheduled[].Name` | _(required)_ | Unique name for the scheduled announcement |
| `Scheduled[].Time` | _(required)_ | Time to play, `HH:MM` (24-hour) |
| `Scheduled[].Days` | `daily` | `daily` or a list: `[saturday, sunday]` |
| `Scheduled[].Week` | _(none)_ | Optional: 1-5 (5 = last week of month); omit for every matching day |
| `Scheduled[].File` | _(required)_ | Path to WAV file to play |

**Example config:**

```yaml
Node: "501260"
PollInterval: 2
Debug: false

TailMessage:
  Enable: true
  MinInterval: 300
  Rotation:
    - /etc/asterisk/scripts/asl3-herald/announcements/tail1.wav
  SkywarnPlus:
    Enable: true
    WxTailFile: /tmp/SkywarnPlus/wx-tail.wav
    SilenceThreshold: 5000

Scheduled:
  - Name: "ARRL Audio News"
    Time: "07:30"
    Days: ["saturday"]
    File: /etc/asterisk/scripts/asl3-herald/announcements/arrl-news.wav

  - Name: "Second Saturday Breakfast Net"
    Time: "08:00"
    Days: ["saturday"]
    Week: 2
    File: /etc/asterisk/scripts/asl3-herald/announcements/breakfast-net.wav
```

---

## herald Command

**General:**

| Command | Description |
|---|---|
| `herald status` | Show daemon status and config summary |
| `sudo herald enable` | Remove disable flag and start daemon |
| `sudo herald disable` | Set disable flag — tail messages suppressed immediately |
| `sudo herald toggle` | Flip enabled/disabled state |
| `sudo herald reload` | Reload config file without restarting (SIGHUP) |
| `herald list-json` | Print config as JSON (used by the web UI) |
| `herald voices [--json]` | List available Piper voices |

**Tail Messages:**

| Command | Description |
|---|---|
| `sudo herald add "<text>" [--name <name>] [--voice <voice>]` | Generate TTS WAV and add to rotation |
| `sudo herald add-file <path> [--name <name>]` | Copy an existing WAV into rotation |
| `herald list` | List rotation + scheduled announcements |
| `sudo herald remove <name>` | Remove a rotation file or scheduled announcement |
| `sudo herald play <name>` | Play an announcement on the node immediately |

**Scheduled Announcements:**

| Command | Description |
|---|---|
| `sudo herald add-schedule "<text>" --name <name> --time HH:MM [--days daily\|d1,d2] [--week 1-5] [--voice <voice>]` | Generate TTS WAV and schedule it |
| `sudo herald add-schedule-file <path> --name <name> --time HH:MM [--days daily\|d1,d2] [--week 1-5]` | Schedule an existing WAV file |

---

## Text-to-Speech

`herald add` and `herald add-schedule` prefer **Piper** (neural TTS, installed by `install.sh`) for natural-sounding voices, and fall back to `festival` or `espeak-ng` if Piper isn't available.

**Included Piper voices** (all American English unless noted):

| Voice | Description |
|---|---|
| `en_US-lessac-medium` | Female (default) |
| `en_US-joe-medium` | Male |
| `en_US-amy-medium` | Female |
| `en_US-kristin-medium` | Female |
| `en_US-libritts_r-medium` | Female, British |
| `en_US-ryan-low` | Male, British |

```bash
herald voices                                              # list installed voices
sudo herald add "Net starts in 5 minutes" --voice en_US-joe-medium --name net-warning
```

Fallback TTS engines, if you don't want Piper's disk/bandwidth footprint:
```bash
sudo apt install festival sox
# or
sudo apt install espeak-ng sox
```

---

## Web UI

An optional browser-based UI for managing both Tail Messages and Scheduled Announcements, installed to `/var/www/html/asl3-herald/`. The two functions are kept on clearly separate panels in the UI, matching the CLI's own Tail Message / Scheduled Announcement split — they're never mixed into one list.

- **Allmon3**: appears as an iframe panel on the node page once `install.sh` adds the `iframepost` entry to `allmon3.ini`. Access is gated by calling Allmon3's own `master/auth/check` API server-side and forwarding your browser's session cookie — no separate login, and no reimplementation of Allmon3's session logic.
- **Supermon 7**: a link appears at the bottom of the page after logging in (added to `footer.inc` by `install.sh`). Access is gated by checking Supermon's own `$_SESSION['sm61loggedin']`.
- Both panels support adding announcements via typed text (with Piper voice selection) or by uploading an existing `.wav`/`.mp3` file (auto-converted to 8kHz mono).
- All mutations go through the same `herald` CLI used at the command line — the web UI never edits the YAML config directly. `www-data` is granted narrow, passwordless `sudo` access to run `herald` only (see `/etc/sudoers.d/asl3-herald-web`).

If neither Allmon3 nor Supermon is detected at install time, `install.sh` installs `apache2` + `php` on its own so the UI still has somewhere to run.

---

## Service Commands

```bash
sudo systemctl start asl3-herald      # Start the daemon
sudo systemctl stop asl3-herald       # Stop the daemon
sudo systemctl restart asl3-herald    # Restart the daemon
sudo systemctl status asl3-herald     # Show service status
journalctl -u asl3-herald -f          # Follow live log output
```

---

## Files

| Path | Description |
|---|---|
| `/usr/local/bin/asl3-herald/asl3-herald.py` | Main daemon (also exposes CLI subcommands used by `herald`) |
| `/usr/local/bin/asl3-herald/version.txt` | Version file |
| `/usr/local/bin/herald` | Management command |
| `/etc/asterisk/scripts/asl3-herald/asl3-herald.conf` | Configuration file |
| `/etc/asterisk/scripts/asl3-herald/asl3-herald.state` | Runtime state (rotation index, last played time) |
| `/etc/asterisk/scripts/asl3-herald/asl3-herald-disabled` | Disable flag (presence disables tail messages) |
| `/etc/asterisk/scripts/asl3-herald/announcements/` | Announcement WAV files |
| `/etc/systemd/system/asl3-herald.service` | systemd service unit |
| `/var/www/html/asl3-herald/` | Web UI (PHP) — shared UI, Allmon3/Supermon entry points, JSON API |
| `/etc/sudoers.d/asl3-herald-web` | Narrow passwordless sudo rule for `www-data` to run `herald` |
| `/opt/piper/` | Piper TTS binary and voice models |

---

## How It Works

`asl3-herald` polls `asterisk -rx "rpt stats <node>"` every 2 seconds and watches the **Kerchunks today** counter. Each time a transmission ends (unkey), the counter increments by one. This is the same reliable method used by other ASL3 monitoring tools such as `asl3-link-activity-monitor`.

When an unkey is detected, the daemon checks in priority order:
1. **Minimum interval** — if not enough time has passed since the last tail message, skip
2. **SkywarnPlus WX alert** — if the `wx-tail.wav` file is larger than `SilenceThreshold` bytes, play it (takes priority over rotation)
3. **Rotation** — otherwise, play the next file in the rotation list and advance the index

**Scheduled announcements** run on a separate time-based path, unaffected by the tail message interval or repeater activity. They fire once per configured `HH:MM` per day, optionally restricted to a specific week of the month via `Week`.

State (rotation index and last played time) is saved to a JSON file so it survives service restarts.

---

## SkywarnPlus Integration

No changes to SkywarnPlus are required. `asl3-herald` reads the existing `wx-tail.wav` file that SkywarnPlus already generates:

- **No active alerts:** `wx-tail.wav` is a small silent file (~1644 bytes)
- **Active alerts:** `wx-tail.wav` contains the weather alert audio (typically 50KB+)

Set `SilenceThreshold: 5000` (the default) to reliably distinguish between the two.

---

## License

GPLv3 © 2026 Larry Aycock (N6LKA)

This software is free and open source. You may use, modify, and redistribute it, but derivative works must remain open source under the same license — it may not be resold or relicensed as proprietary software.

See [LICENSE](LICENSE) for details.
