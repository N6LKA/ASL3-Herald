<img src="web/img/herald-logo.png" height="240" alt="Herald logo"><img src="web/img/herald-title-banner.png" height="240" alt="AllStarLink Herald - Announcement Manager Suite">

![Release Version](https://img.shields.io/github/v/release/N6LKA/ASL3-Herald?label=Version&color=2f6f9f)
![Release Date](https://img.shields.io/github/release-date/N6LKA/ASL3-Herald?label=released&color=green)
![Last Commit](https://img.shields.io/github/last-commit/N6LKA/ASL3-Herald)
![Lint](https://img.shields.io/github/actions/workflow/status/N6LKA/ASL3-Herald/lint.yml?branch=main&label=lint)
![Open Issues](https://img.shields.io/github/issues/N6LKA/ASL3-Herald)
![License](https://img.shields.io/badge/license-GPLv3-lightgrey)

**A full-featured announcement and audio suite for ASL3/app_rpt.**

`asl3-herald` started as a drop-in replacement for the native `app_rpt` tail message function and has grown into a complete announcement toolkit: reliable unkey-triggered tail messages, cron-style scheduled announcements, SkywarnPlus weather alert integration, built-in time & weather announcements, a station ID audio generator, neural TTS voices throughout, and an optional web UI for Allmon3 and Supermon.

📖 **[Full documentation, configuration reference, and troubleshooting → see the Wiki](https://github.com/N6LKA/ASL3-Herald/wiki)**

---

## Key Features

- **Tail Messages** — reliable, unkey-triggered rotating announcements with SkywarnPlus WX priority and optional day/time-window gating
- **Scheduled Announcements** — cron-style, clock-triggered, local or global playback
- **Time & Weather Announcements** — built-in `saytime.pl`/`weather.sh` replacement with recordings or custom Piper-TTS templates
- **Node ID Generator** — generate a station ID recording for AllStarLink's own ID feature
- **Piper neural TTS** — natural-sounding voices with adjustable speech speed (0.5x–2.0x), festival/espeak-ng fallback
- **Web UI** — optional browser-based management for Allmon3 and Supermon, gated behind each app's own login
- **One-click updates** — check for and install updates from the web UI, with automatic post-restart health verification
- **Config backup/restore, playback history, missing-file health checks** — see the Wiki for details

---

## Screenshots

<table>
<tr>
<td width="50%">

**How It Works** — a plain-language overview of Tail Messages, Scheduled Announcements, and Time & Weather Announcements, shown before you touch any settings.

<img src="screenshots/how-it-works.png" width="100%">

</td>
<td width="50%">

**Tail Messages** — General Settings, SkywarnPlus integration, the rotation table, and the add-message form.

<img src="screenshots/tail-messages.png" width="100%">

</td>
</tr>
<tr>
<td width="50%">

**Scheduled Announcements** — cron-driven announcements with a live schedule picker and reference table.

<img src="screenshots/scheduled-announcements.png" width="100%">

</td>
<td width="50%">

**Time & Weather Announcements** — Custom Templates mode, with tag-based messages rendered fresh by Piper TTS each time.

<img src="screenshots/time-weather-announcements.png" width="100%">

</td>
</tr>
<tr>
<td width="50%">

**Node ID Generator** — generate a station ID recording with Piper TTS, test it locally, and see exactly what to add to `rpt.conf`.

<img src="screenshots/node-id-generator.png" width="100%">

</td>
<td width="50%"></td>
</tr>
</table>

---

## Installation

**Stable (recommended):** installs from `main` — the tested, working release.

```bash
curl -fsSL -H "Cache-Control: no-cache" https://raw.githubusercontent.com/N6LKA/ASL3-Herald/main/install.sh | sudo bash
```

**Development (testing only):** installs from `develop` — whatever's currently being worked on ahead of the next release.

> ⚠️ **Warning:** `develop` may contain incomplete, untested, or broken features at any given time. Only use this on a system where you can tolerate things breaking (or reinstall from `main` to recover). Don't use it on a repeater or node you depend on for daily use.

```bash
curl -fsSL "https://github.com/N6LKA/ASL3-Herald/archive/refs/heads/develop.tar.gz" \
  | tar -xzO ASL3-Herald-develop/install.sh \
  | sudo bash -s -- --branch develop
```

This tarball form is used instead of the raw GitHub URL because `raw.githubusercontent.com` is CDN-cached and can serve a stale `install.sh` for an extended period — the tarball download goes through GitHub's codeload service, which always returns the current commit.

The installer will:
1. Install `python3-yaml`, `sox`, and `libsox-fmt-mp3` if not already present
2. Install Piper TTS 1.2.0 (binary + the default `en_US-amy-medium` voice) into the shared `/var/lib/piper-tts` — more voices can be installed later from the web UI's Voices tab
3. Copy `asl3-herald.py` to `/usr/local/bin/asl3-herald/`
4. Install the `herald` management command to `/usr/local/bin/herald`
5. Create `/etc/asterisk/scripts/asl3-herald/` with an example config (if no config exists)
6. Install and enable the `asl3-herald` systemd service, and start it automatically
7. Install the web UI to `/var/www/html/asl3-herald/` — installs `apache2` + `php` first if neither Allmon3 nor Supermon is already present, then installs a dedicated page directly into Allmon3's and/or Supermon's own directory (with a sidebar/footer link to it) for whichever is detected

**After installation:**

1. Edit the config: `sudo nano /etc/asterisk/scripts/asl3-herald/asl3-herald.conf`
2. Check it's running: `herald status`

---

## Uninstalling

```bash
curl -fsSL -H "Cache-Control: no-cache" https://raw.githubusercontent.com/N6LKA/ASL3-Herald/main/uninstall.sh | sudo bash
```

By default this removes the daemon, `herald` CLI, systemd service, web UI, sudoers rule, and the Allmon3/Supermon integration lines it added — while **preserving** your config, announcements, state, and Piper TTS install so a future reinstall picks up where you left off. To also remove those:

```bash
curl -fsSL -H "Cache-Control: no-cache" https://raw.githubusercontent.com/N6LKA/ASL3-Herald/main/uninstall.sh | sudo bash -s -- --purge-all
```

(`--purge-config` and `--purge-piper` are available individually too.)

---

## Support the Project

If asl3-herald has been useful on your repeater or node, please consider supporting its development!

<p align="center"><a href="https://www.paypal.me/LarryAycock"><img src="https://raw.githubusercontent.com/stefan-niedermann/paypal-donate-button/master/paypal-donate-button.png" width="300px" alt="Donate with PayPal"/></a></p>

---

## License

GPLv3 © 2026 Larry Aycock (N6LKA)

This software is free and open source. You may use, modify, and redistribute it, but derivative works must remain open source under the same license — it may not be resold or relicensed as proprietary software.

See [LICENSE](LICENSE) for details.
