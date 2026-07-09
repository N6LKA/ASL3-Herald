# asl3-herald

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Release Date](https://img.shields.io/badge/released-2026--07--09-green)
![License](https://img.shields.io/badge/license-GPLv3-lightgrey)

**Enhanced tail message daemon for ASL3/app_rpt with advanced announcement features.**

`asl3-herald` is a drop-in replacement and enhancement for the native `app_rpt` tail message function. It provides reliable unkey detection, rotating messages, SkywarnPlus weather alert integration with priority playback, scheduled time-based announcements, and configurable blackout windows — all things the built-in tail message either doesn't support or handles unreliably.

---

## What It Does

- **Reliable unkey detection** — polls the `rpt stats` kerchunk counter every 2 seconds to detect transmissions; not dependent on the inconsistent native tail message trigger
- **Rotating tail messages** — cycles through a list of announcement files in order with a configurable minimum interval between plays
- **SkywarnPlus WX integration** — when weather alerts are active, plays the SkywarnPlus `wx-tail.wav` file instead of the normal rotation (WX always has priority)
- **Scheduled announcements** — plays a specific file at a configured time of day on selected days of the week, independent of the tail message interval (e.g., ARRL Audio News every Saturday at 07:30)
- **Blackout window** — suppresses tail messages between two configurable times (e.g., overnight 22:00–07:00); overnight spans are supported
- **Instant disable/enable** — use `herald disable` / `herald enable` without touching the config or restarting the service
- **Live config reload** — `herald reload` sends SIGHUP to pick up config changes immediately
- **TTS announcement builder** — `herald add "text"` generates a 8 kHz mono WAV from text using festival or espeak-ng and adds it to the rotation automatically
- **v2 (planned)** — Web UI for managing announcements

---

## Installation

```bash
sudo bash <(curl -fsSL -H "Cache-Control: no-cache" https://raw.githubusercontent.com/N6LKA/asl3-herald/main/install.sh)
```

The installer will:
1. Install `python3-yaml` and `sox` if not already present
2. Copy `asl3-herald.py` to `/usr/local/bin/asl3-herald/`
3. Install the `herald` management command to `/usr/local/bin/herald`
4. Create `/etc/asterisk/scripts/asl3-herald/` with an example config (if no config exists)
5. Install and enable the `asl3-herald` systemd service

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
| `TailMessage.BlackoutStart` | _(empty)_ | No tail messages after this time (HH:MM, 24-hour) |
| `TailMessage.BlackoutEnd` | _(empty)_ | Resume tail messages at this time (HH:MM, 24-hour) |
| `TailMessage.Rotation` | _(empty)_ | List of WAV file paths to rotate through |
| `TailMessage.SkywarnPlus.Enable` | `true` | Enable SkywarnPlus WX tail integration |
| `TailMessage.SkywarnPlus.WxTailFile` | `/tmp/SkywarnPlus/wx-tail.wav` | Path to SkywarnPlus wx-tail.wav |
| `TailMessage.SkywarnPlus.SilenceThreshold` | `5000` | File size (bytes) to distinguish active alerts from silence |
| `Scheduled[].Name` | _(required)_ | Unique name for the scheduled announcement |
| `Scheduled[].Time` | _(required)_ | Time to play, `HH:MM` (24-hour) |
| `Scheduled[].Days` | `daily` | `daily` or a list: `[saturday, sunday]` |
| `Scheduled[].File` | _(required)_ | Path to WAV file to play |

**Example config:**

```yaml
Node: "501260"
PollInterval: 2
Debug: false

TailMessage:
  Enable: true
  MinInterval: 300
  BlackoutStart: "22:00"
  BlackoutEnd:   "07:00"
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
```

---

## herald Command

| Command | Description |
|---|---|
| `herald status` | Show daemon status and config summary |
| `sudo herald enable` | Remove disable flag and start daemon |
| `sudo herald disable` | Set disable flag — tail messages suppressed immediately |
| `sudo herald reload` | Reload config file without restarting (SIGHUP) |
| `sudo herald add "<text>" [--name <name>]` | Generate TTS WAV and add to rotation |
| `sudo herald add-file <path> [--name <name>]` | Copy an existing WAV into rotation |
| `herald list` | List all rotation files and scheduled announcements |
| `sudo herald remove <name>` | Remove announcement from config and delete WAV |
| `sudo herald play <name>` | Play an announcement on the node immediately |

**TTS generation** (`herald add`) requires `festival + sox` or `espeak-ng + sox`:
```bash
sudo apt install festival sox
# or
sudo apt install espeak-ng sox
```

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
| `/usr/local/bin/asl3-herald/asl3-herald.py` | Main daemon |
| `/usr/local/bin/asl3-herald/version.txt` | Version file |
| `/usr/local/bin/herald` | Management command |
| `/etc/asterisk/scripts/asl3-herald/asl3-herald.conf` | Configuration file |
| `/etc/asterisk/scripts/asl3-herald/asl3-herald.state` | Runtime state (rotation index, last played time) |
| `/etc/asterisk/scripts/asl3-herald/asl3-herald-disabled` | Disable flag (presence disables tail messages) |
| `/etc/asterisk/scripts/asl3-herald/announcements/` | Announcement WAV files |
| `/etc/systemd/system/asl3-herald.service` | systemd service unit |

---

## How It Works

`asl3-herald` polls `asterisk -rx "rpt stats <node>"` every 2 seconds and watches the **Kerchunks today** counter. Each time a transmission ends (unkey), the counter increments by one. This is the same reliable method used by other ASL3 monitoring tools such as `asl3-link-activity-monitor`.

When an unkey is detected, the daemon checks in priority order:
1. **SkywarnPlus WX alert** — if the `wx-tail.wav` file is larger than `SilenceThreshold` bytes, it plays the WX file. **WX alerts override the blackout window** — safety messages always play regardless of time of day. Only the minimum interval applies.
2. **Blackout window** — if active, non-WX tail messages are suppressed
3. **Minimum interval** — if not enough time has passed since the last play, skip
4. **Rotation** — plays the next file in the rotation list and advances the index

**Scheduled announcements** run on a separate time-based path and are not affected by the tail message interval. They fire once per configured `HH:MM` per day.

State (rotation index and last played time) is saved to a JSON file so it survives service restarts.

---

## SkywarnPlus Integration

No changes to SkywarnPlus are required. `asl3-herald` reads the existing `wx-tail.wav` file that SkywarnPlus already generates:

- **No active alerts:** `wx-tail.wav` is a small silent file (~1644 bytes)
- **Active alerts:** `wx-tail.wav` contains the weather alert audio (typically 50KB+)

Set `SilenceThreshold: 5000` (the default) to reliably distinguish between the two.

WX alerts always take priority and will play even during the configured blackout window.

---

## License

GPLv3 © 2026 Larry Aycock (N6LKA)

This software is free and open source. You may use, modify, and redistribute it, but derivative works must remain open source under the same license — it may not be resold or relicensed as proprietary software.

See [LICENSE](LICENSE) for details.
