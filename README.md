![asl3-herald](web/img/asl3-herald-banner.svg)

![Version](https://img.shields.io/badge/version-1.4.0-blue)
![Release Date](https://img.shields.io/badge/released-2026--07--12-green)
![License](https://img.shields.io/badge/license-GPLv3-lightgrey)

**Enhanced tail message daemon for ASL3/app_rpt with advanced announcement features.**

`asl3-herald` is a drop-in replacement and enhancement for the native `app_rpt` tail message function. It provides reliable unkey detection, rotating messages, SkywarnPlus weather alert integration with priority playback, scheduled time-based announcements (including nth-week-of-month scheduling), neural TTS voices, and an optional web UI for Allmon3 and Supermon 7 — all things the built-in tail message either doesn't support or handles unreliably.

---

## What It Does

`asl3-herald` covers two distinct functions:

- **Tail Messages** — unkey-triggered, reactive to repeater activity:
  - **Reliable unkey detection** — polls the `rpt stats` kerchunk counter every second (configurable via `PollInterval`) to detect transmissions; not dependent on the inconsistent native tail message trigger
  - **Rotating messages** — cycles through a list of announcement files in order with a configurable minimum interval between plays
  - **SkywarnPlus WX integration** — when weather alerts are active, plays the SkywarnPlus `wx-tail.wav` file instead of the normal rotation (WX always takes priority)
  - **Optional day/time-window gating per entry** — a rotation entry can be restricted to specific days of the week and/or a time-of-day window (e.g. a net-announcement tail message that's only eligible Tuesday evenings); entries without gating stay eligible all the time, same as before

- **Scheduled Announcements** — clock-triggered, independent of repeater activity:
  - Plays a specific file at a configured time of day, on selected days of the week
  - Optional nth-week-of-month scheduling (e.g. "2nd Saturday of the month")
  - **Local or global playback** — each scheduled announcement can play locally on this node only (`rpt localplay`, the default) or globally to all connected/linked nodes (`rpt playback`)
  - **Waits for unkey** — if the node is currently keyed when a scheduled announcement is due, it holds off rather than playing over live traffic, and keeps checking every poll until the node unkeys
  - **Takes precedence over tail messages** — if a scheduled announcement and a tail message would both fire at the same moment, the scheduled announcement always plays; the tail message simply retries on its next unkey once the announcement has finished, with no penalty against `MinInterval`

Both Tail Messages and Scheduled Announcements can be edited in place (name, text, voice, schedule, play mode) via `herald edit-rotation` / `herald edit-schedule` or the web UI, instead of removing and re-adding.

**Node targeting for `multinodes=` setups:** any rotation or scheduled entry can optionally carry a `Node` override, targeting a specific node number for playback instead of the daemon's own configured `Node` — useful when one AMI connection serves several node numbers (Allmon3's `multinodes=`) and you want a given announcement to go out on a particular one.

Plus:
- **Piper neural TTS** — generate announcements from text with natural-sounding voices (6 included), with festival/espeak-ng as a fallback
- **Web UI** — optional browser-based management linked from Allmon3 or Supermon 7, gated behind each app's own login
- **Instant disable/enable** — `herald toggle` / `herald enable` / `herald disable`, no config edits or restarts needed
- **Live config reload** — `herald reload` sends SIGHUP to pick up config changes immediately
- **Reorderable rotation** — move a rotation entry earlier/later in the cycle from the web UI or CLI, no remove-and-re-add needed
- **Playback history** — the last 200 plays (rotation, WX, scheduled, and manual test plays) are logged with timestamp, node, and play mode, viewable in the web UI's Playback History tab
- **Test playback, always local** — the Play/Test button (web UI and `herald play`) always plays immediately on this node only, regardless of a scheduled announcement's configured `PlayMode` — it's for confirming an entry sounds right, never a live broadcast
- **Config backup/restore** — export the full rotation/scheduled/settings config as a JSON file, or restore from one, via the Settings tab or `herald export-config` / `herald import-config`
- **Missing-file health check** — a rotation or scheduled entry whose WAV file no longer exists on disk is flagged (`herald status`'s missing-file count, `herald list`, and a badge in the web UI) instead of failing silently
- **Version display + update check** — the installed version is shown in the web UI's Settings tab, with a "Check for Updates" button that compares it against the latest `main` release on GitHub

---

## Installation

**Stable (recommended):** installs from `main` — the tested, working release.

```bash
curl -fsSL -H "Cache-Control: no-cache" https://raw.githubusercontent.com/N6LKA/asl3-herald/main/install.sh | sudo bash
```

**Development (testing only):** installs from `develop` — whatever's currently being worked on ahead of the next release.

> ⚠️ **Warning:** `develop` may contain incomplete, untested, or broken features at any given time. Only use this on a system where you can tolerate things breaking (or reinstall from `main` to recover). Don't use it on a repeater you depend on for daily use.

```bash
curl -fsSL -H "Cache-Control: no-cache" https://raw.githubusercontent.com/N6LKA/asl3-herald/develop/install.sh | sudo bash -s -- --branch develop
```

`--branch develop` must be passed as a script argument exactly as shown (not an environment variable — those don't reliably survive the `sudo` call on a piped command).

The installer will:
1. Install `python3-yaml`, `sox`, and `libsox-fmt-mp3` if not already present
2. Install Piper TTS 1.2.0 (binary + 6 voices) — this step downloads a few hundred MB and may take a few minutes
3. Copy `asl3-herald.py` to `/usr/local/bin/asl3-herald/`
4. Install the `herald` management command to `/usr/local/bin/herald`
5. Create `/etc/asterisk/scripts/asl3-herald/` with an example config (if no config exists)
6. Install and enable the `asl3-herald` systemd service
7. Install the web UI to `/var/www/html/asl3-herald/` — installs `apache2` + `php` first if neither Allmon3 nor Supermon is already present, then installs a dedicated page directly into Allmon3's and/or Supermon's own directory (with a sidebar/footer link to it) for whichever is detected

**After installation:**

1. Edit the config: `sudo nano /etc/asterisk/scripts/asl3-herald/asl3-herald.conf`
2. Start the service: `sudo systemctl start asl3-herald`
3. Check it's running: `herald status`

---

## Uninstalling

```bash
curl -fsSL -H "Cache-Control: no-cache" https://raw.githubusercontent.com/N6LKA/asl3-herald/main/uninstall.sh | sudo bash
```

By default this removes the daemon, `herald` CLI, systemd service, web UI, sudoers rule, and the Allmon3/Supermon integration lines it added — while **preserving** your config, announcements, state, and Piper TTS install so a future reinstall picks up where you left off. To also remove those:

```bash
curl -fsSL -H "Cache-Control: no-cache" https://raw.githubusercontent.com/N6LKA/asl3-herald/main/uninstall.sh | sudo bash -s -- --purge-all
```

(`--purge-config` and `--purge-piper` are available individually too.)

---

## Configuration

Config file: `/etc/asterisk/scripts/asl3-herald/asl3-herald.conf`

| Setting | Default | Description |
|---|---|---|
| `Node` | _(required)_ | Your ASL3 node number |
| `PollInterval` | `1` | Seconds between kerchunk counter polls |
| `Debug` | `false` | Enable verbose debug logging |
| `TailMessage.Enable` | `true` | Enable/disable tail message function |
| `TailMessage.MinInterval` | `300` | Minimum seconds between tail messages |
| `TailMessage.Rotation` | _(empty)_ | List of rotation entries (WAV file paths, or dicts with `File` plus optional `Days`/`TimeStart`/`TimeEnd`/`Node`) |
| `TailMessage.Rotation[].Days` | _(always eligible)_ | Optional: `daily` (default) or a list, e.g. `[tuesday]` — restricts this entry to those days |
| `TailMessage.Rotation[].TimeStart` / `TimeEnd` | _(none)_ | Optional: `HH:MM` window this entry is eligible in; omit either side for open-ended |
| `TailMessage.Rotation[].Node` | _(daemon's `Node`)_ | Optional: target a specific node number for this entry (multinodes= setups) |
| `TailMessage.SkywarnPlus.Enable` | `true` | Enable SkywarnPlus WX tail integration |
| `TailMessage.SkywarnPlus.WxTailFile` | `/tmp/SkywarnPlus/wx-tail.wav` | Path to SkywarnPlus wx-tail.wav |
| `TailMessage.SkywarnPlus.SilenceThreshold` | `5000` | File size (bytes) to distinguish active alerts from silence |
| `Scheduled[].Name` | _(required)_ | Unique name for the scheduled announcement |
| `Scheduled[].Time` | _(required)_ | Time to play, `HH:MM` (24-hour) |
| `Scheduled[].Days` | `daily` | `daily` or a list: `[saturday, sunday]` |
| `Scheduled[].Week` | _(none)_ | Optional: 1-5 (5 = last week of month); omit for every matching day |
| `Scheduled[].File` | _(required)_ | Path to WAV file to play |
| `Scheduled[].PlayMode` | `local` | `local` (this node only) or `global` (all connected/linked nodes) |
| `Scheduled[].Node` | _(daemon's `Node`)_ | Optional: target a specific node number for this entry (multinodes= setups) |

**Example config:**

```yaml
Node: "501260"
PollInterval: 1
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
| `herald playback-history` | Print recent playback history as JSON |
| `herald export-config` | Print the full config as JSON (for backup) |
| `sudo herald import-config <path>` | Restore the full config from an exported JSON file (replaces everything) |

**Tail Messages:**

| Command | Description |
|---|---|
| `sudo herald add "<text>" [--name <name>] [--voice <voice>] [--days daily\|d1,d2] [--time-start HH:MM] [--time-end HH:MM] [--node <n>]` | Generate TTS WAV and add to rotation |
| `sudo herald add-file <path> [--name <name>] [--days daily\|d1,d2] [--time-start HH:MM] [--time-end HH:MM] [--node <n>]` | Copy an existing WAV into rotation |
| `sudo herald edit-rotation <name> [--new-name <n>] [--text "<text>"] [--voice <v>] [--file <path>] [--days ...] [--time-start HH:MM] [--time-end HH:MM] [--node <n>]` | Edit an existing rotation entry in place |
| `sudo herald reorder-rotation <name> <up\|down>` | Move a rotation entry earlier/later in the cycle |
| `herald list` | List rotation + scheduled announcements (flags entries with a missing file) |
| `sudo herald remove <name>` | Remove a rotation file or scheduled announcement |
| `sudo herald play <name>` | Test-play an announcement on the node immediately (always local, ignores `PlayMode`) |

`--days`/`--time-start`/`--time-end` restrict a rotation entry to specific days-of-week and/or a time-of-day window; leave unset for an entry that's always eligible. `--node` targets a specific node number instead of the daemon's configured `Node`.

**Scheduled Announcements:**

| Command | Description |
|---|---|
| `sudo herald add-schedule "<text>" --name <name> --time HH:MM [--days daily\|d1,d2] [--week 1-5] [--voice <voice>] [--play-mode local\|global] [--node <n>]` | Generate TTS WAV and schedule it |
| `sudo herald add-schedule-file <path> --name <name> --time HH:MM [--days daily\|d1,d2] [--week 1-5] [--play-mode local\|global] [--node <n>]` | Schedule an existing WAV file |
| `sudo herald edit-schedule <name> [--new-name <n>] [--time HH:MM] [--days ...] [--week 1-5] [--play-mode local\|global] [--text "<text>"] [--voice <v>] [--file <path>] [--node <n>]` | Edit an existing scheduled announcement in place |

A scheduled announcement waits for the node to unkey before playing (rather than interrupting live traffic) and always takes precedence over a tail message due at the same moment.

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

An optional browser-based UI for managing both Tail Messages and Scheduled Announcements. The shared UI and JSON API live at `/var/www/html/asl3-herald/`, but the actual entry points are installed *inside* Allmon3's and Supermon's own directories — not as a separate app linked via cookie-forwarding. The two functions are kept on clearly separate panels in the UI, matching the CLI's own Tail Message / Scheduled Announcement split — they're never mixed into one list.

- **Allmon3**: `install.sh` installs `asl3-herald.html` directly into Allmon3's own web root (`/usr/share/allmon3/`, alongside `index.html`) and appends a `[Herald]` entry to the bottom of `/etc/allmon3/menu.ini` (Allmon3's own supported sidebar-customization mechanism) pointing at it. Because the page lives inside Allmon3's own directory, it loads Allmon3's real `functions.js`/`index.js` unmodified — same header/sidebar chrome as any other Allmon3 page, and a same-origin `master/auth/check` fetch for login detection. (A page living outside Allmon3's own directory can't reliably read Allmon3's session cookie server-side — its `Path` ends up scoped to Allmon3's own API prefix — which is why an earlier design based on a separate PHP page cookie-forwarding to Allmon3's internal port didn't reliably work.)
- **Optional**: `install.sh` also appends a rule to `/etc/allmon3/custom.css` that hides the sidebar link entirely until you're logged into Allmon3, using Allmon3's own stock `body.logged-in`/`body.logged-out` class toggle. This is cosmetic only — the page itself still gates its content on real login status regardless of whether the link is visible.
- **Supermon 7**: `install.sh` installs `asl3-herald.php` directly into Supermon's own directory (`/var/www/html/supermon/`) and adds a link at the bottom of the page after logging in (added to `footer.inc`, inside Supermon's own existing login-conditional block — so it's already hidden until logged in, natively). Because the page lives inside Supermon's own directory, it includes Supermon's real `session.inc`/`header.inc`/`footer.inc` unmodified — same nav and login dialog as any other Supermon page, and the same named session cookie (`supermon61`) Supermon itself uses, so login detection always matches Supermon's actual state.
- Both pages support adding announcements via typed text (with Piper voice selection) or by uploading an existing `.wav`/`.mp3` file (auto-converted to 8kHz mono).
- **Playback History tab** — the last 200 plays (rotation, WX, scheduled, manual test) with timestamp, node, and play mode.
- **Settings tab** also shows the installed version with a "Check for Updates" button (compares against `main`'s `version.txt` via GitHub's API), plus a Backup & Restore card to download the full config as JSON or restore from a previously exported file.
- Rotation entries in the Tail Messages tab have Up/Down buttons to reorder the cycle, and any entry (rotation or scheduled) whose WAV file no longer exists on disk shows a "MISSING FILE" badge.
- All mutations go through the same `herald` CLI used at the command line — the web UI never edits the YAML config directly. `www-data` is granted narrow, passwordless `sudo` access to run `herald` only (see `/etc/sudoers.d/asl3-herald-web`). The JSON API endpoints themselves are not independently re-verified against Allmon3/Supermon login state (the display pages are gated, but the raw API URLs aren't) — a deliberate simplicity/portability tradeoff, since properly closing that gap would require a per-user Apache config change that isn't reliable across arbitrary installs. The API's own blast radius is narrow regardless: `www-data` can only run the `herald` CLI, nothing else.

If neither Allmon3 nor Supermon is detected at install time, `install.sh` installs `apache2` + `php` on its own so the shared UI still has somewhere to run. `menu.ini` and `custom.css` changes are always appended to the end of the file (never inserted in the middle) so they don't disturb any existing customizations, and both are idempotent — re-running `install.sh` won't duplicate them. The Allmon3/Supermon pages themselves are always overwritten on install/update, since they're fully managed by asl3-herald.

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
| `/etc/asterisk/scripts/asl3-herald/asl3-herald.state` | Runtime state (rotation index, last played time, playback history) |
| `/etc/asterisk/scripts/asl3-herald/asl3-herald-disabled` | Disable flag (presence disables tail messages) |
| `/etc/asterisk/scripts/asl3-herald/announcements/` | Announcement WAV files |
| `/etc/systemd/system/asl3-herald.service` | systemd service unit |
| `/var/www/html/asl3-herald/` | Shared UI fragment/JS and JSON API (PHP) |
| `/var/www/html/asl3-herald/img/` | Logo assets (icon + banner), used by the Allmon3/Supermon page headers |
| `/usr/share/allmon3/asl3-herald.html` | Allmon3 entry point (installed alongside Allmon3's own `index.html`) |
| `/var/www/html/supermon/asl3-herald.php` | Supermon entry point (installed alongside Supermon's own `index.php`) |
| `install.sh` / `uninstall.sh` (repo root) | Installer / uninstaller — not installed on the node itself |
| `/etc/sudoers.d/asl3-herald-web` | Narrow passwordless sudo rule for `www-data` to run `herald` |
| `/opt/piper/` | Piper TTS binary and voice models |

---

## How It Works

`asl3-herald` polls `asterisk -rx "rpt stats <node>"` every second (configurable via `PollInterval`) and watches the **Kerchunks today** counter. Each time a transmission ends (unkey), the counter increments by one. This is the same reliable method used by other ASL3 monitoring tools such as `asl3-link-activity-monitor`.

Every poll, **scheduled announcements are checked first**, before the unkey/tail-message logic. When an unkey is detected, the daemon then checks in priority order:
1. **Minimum interval** — if not enough time has passed since the last tail message, skip
2. **Scheduled announcement in progress** — if one just started playing (see below), skip this unkey; it isn't counted against `MinInterval`, so the tail message simply retries on the next unkey
3. **SkywarnPlus WX alert** — if the `wx-tail.wav` file is larger than `SilenceThreshold` bytes, an alert is active
4. **Rotation** — otherwise, play the next *eligible* file in the rotation list (skipping any with `Days`/`TimeStart`/`TimeEnd` gating that doesn't currently match) and advance the index

A newly-appeared or changed WX alert always plays immediately, taking priority over the rotation. But a **persistent** alert (unchanged since it last played — detected via `wx-tail.wav`'s own modification time, not a separate/optional SkywarnPlus feed) alternates with the rotation on each unkey instead of playing every single time, so a long-running alert (common in some areas, e.g. summer heat warnings) doesn't shut the rotation out entirely. As soon as the alert changes or a new one appears, it immediately jumps back to the front of the line.

**Scheduled announcements** run on a separate time-based path, unaffected by the tail message interval or repeater activity. They fire once per configured `HH:MM` per day, optionally restricted to a specific week of the month via `Week`. If the node is currently keyed when a scheduled announcement is due (checked via `rpt stats`'s "Signal on input" field), it holds off and keeps re-checking every poll — even after the matching minute has passed — until the node unkeys, rather than missing the announcement or talking over live traffic. Once a scheduled announcement plays, its estimated audio duration (via `soxi`, or an 8-second fallback estimate) holds off any tail message for that long, so the two never overlap — this is also how a scheduled announcement takes precedence when both would fire at the same moment.

State (rotation index, WX alternation, scheduled "waiting for unkey" status, and last played times) is saved to a JSON file so it survives service restarts.

---

## SkywarnPlus Integration

No changes to SkywarnPlus are required. `asl3-herald` reads the existing `wx-tail.wav` file that SkywarnPlus already generates:

- **No active alerts:** `wx-tail.wav` is a small silent file (~1644 bytes)
- **Active alerts:** `wx-tail.wav` contains the weather alert audio (typically 50KB+)

Set `SilenceThreshold: 5000` (the default) to reliably distinguish between the two.

**Note:** the original SkywarnPlus author, Mason (Mason10198), no longer maintains the project — [the original repo](https://github.com/Mason10198/SkywarnPlus) is archived and read-only. Larry (N6LKA) maintains an active fork that keeps SkywarnPlus working and up to date: **[github.com/N6LKA/SkywarnPlus](https://github.com/N6LKA/SkywarnPlus)**.

---

## License

GPLv3 © 2026 Larry Aycock (N6LKA)

This software is free and open source. You may use, modify, and redistribute it, but derivative works must remain open source under the same license — it may not be resold or relicensed as proprietary software.

See [LICENSE](LICENSE) for details.
