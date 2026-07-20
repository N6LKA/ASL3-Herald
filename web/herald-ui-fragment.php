<?php
// herald-ui-fragment.php
//
// Markup-only fragment for asl3-herald's shared UI (styles + HTML, no
// <script>). Fetched client-side and injected via innerHTML by pages that
// can't run PHP themselves (e.g. asl3-herald.html living inside Allmon3's
// own static web root), or included server-side by pages that can (e.g.
// asl3-herald.php living inside Supermon's own directory).
//
// The behavior lives separately in herald-ui.js, loaded via a real
// <script src> tag by whichever page includes this fragment — scripts
// inserted via innerHTML never execute, so the JS can't live in here.
?>
<div id="herald-ui">
<style>
  #herald-ui {
    font-family: Arial, sans-serif;
    font-size: 16px;
    max-width: 100%;
    color: #222;
  }
  #herald-ui h3 { margin-bottom: 8px; }
  #herald-ui .card {
    display: block; /* some host pages (Allmon3) load Bootstrap, whose .card
                        sets display:flex - that stretches our buttons to
                        full width via default flex align-items:stretch even
                        though the buttons themselves are width:auto */
    background: #fff;
    border: 1px solid #ccc;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 16px;
  }
  #herald-ui .status-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    align-items: center;
    background: #f4f4f4;
    border: 1px solid #ccc;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 16px;
  }
  #herald-ui .status-bar span { font-size: 1em; }
  #herald-ui .tabs { display: flex; gap: 4px; margin-bottom: 12px; }
  #herald-ui .tab-btn {
    padding: 8px 16px;
    border: 1px solid #ccc;
    border-bottom: none;
    background: #eee;
    cursor: pointer;
    border-radius: 6px 6px 0 0;
  }
  #herald-ui .tab-btn.active { background: #fff; font-weight: bold; }
  #herald-ui .tab-panel { display: none; }
  #herald-ui .tab-panel.active { display: block; }
  #herald-ui table { width: 100%; border-collapse: collapse; margin-bottom: 12px; table-layout: auto; }
  #herald-ui th, #herald-ui td {
    text-align: left;
    padding: 6px 8px;
    border-bottom: 1px solid #ddd;
    font-size: 1em;
    white-space: nowrap;
  }
  #herald-ui .col-wrap { white-space: normal; }
  #herald-ui button {
    cursor: pointer;
    padding: 4px 10px;
    margin-right: 4px;
    display: inline-block !important;
    width: auto !important;
  }
  #herald-ui .btn-danger { background: #e74c3c; color: #fff; border: none; border-radius: 4px; }
  #herald-ui .btn-play   { background: #2980b9; color: #fff; border: none; border-radius: 4px; }
  #herald-ui .btn-primary{ background: #27ae60; color: #fff; border: none; border-radius: 4px; padding: 8px 16px; }
  #herald-ui .btn-toggle { background: #8e44ad; color: #fff; border: none; border-radius: 4px; }
  #herald-ui input[type=text], #herald-ui input[type=time], #herald-ui select, #herald-ui textarea {
    padding: 6px; margin: 4px 6px 4px 0;
  }
  #herald-ui textarea {
    resize: vertical;
    min-height: 72px;
    font-family: inherit;
    font-size: inherit;
    box-sizing: border-box;
    margin: 4px 0;
  }
  #herald-ui .tts-row {
    display: flex;
    gap: 16px;
    align-items: flex-start;
    margin-top: 4px;
  }
  #herald-ui .tts-row .tts-voice { flex: 0 0 auto; }
  #herald-ui .tts-row .tts-text  { flex: 1 1 auto; min-width: 0; }
  #herald-ui .add-form { border-top: 2px solid #eee; margin-top: 12px; padding-top: 12px; }
  #herald-ui label { display: block; font-size: 0.95em; margin-top: 8px; }
  #herald-ui .field-row { display: flex; flex-wrap: wrap; gap: 24px; align-items: flex-start; }
  #herald-ui .field-row > div { flex: 0 0 auto; }
  #herald-ui .days-picker label { display: inline-block; margin-right: 10px; font-weight: normal; }
  #herald-ui .days-picker input[type=checkbox] { margin-right: 10px; }
  #herald-ui .source-toggle { margin: 8px 0; }
  #herald-ui .msg { font-weight: bold; margin-top: 8px; min-height: 1.2em; }
  #herald-ui .msg.ok { color: #27ae60; }
  #herald-ui .msg.err { color: #e74c3c; }
  #herald-ui .muted { color: #777; font-size: 0.95em; }
  #herald-ui .btn-reorder { padding: 4px 8px; }
  #herald-ui .btn-reorder:disabled { opacity: 0.3; cursor: default; }
  #herald-ui .btn-enable  { background: #27ae60; color: #fff; border: none; border-radius: 4px; }
  #herald-ui .btn-disable { background: #888;    color: #fff; border: none; border-radius: 4px; }
  #herald-ui .btn-edit    { background: #e67e22; color: #fff; border: none; border-radius: 4px; }
  #herald-ui tr.sched-disabled td { opacity: 0.5; }
  #herald-ui code { color: #333; background: #eee; padding: 1px 5px; border-radius: 3px; font-size: 0.95em; }
  #herald-ui #sched-table th { white-space: normal; }
  #herald-ui .badge-missing {
    background: #e74c3c; color: #fff; font-size: 0.75em;
    padding: 2px 6px; border-radius: 4px; margin-left: 6px; white-space: nowrap;
  }
  #herald-ui .toggle-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 12px;
    flex-wrap: wrap;
  }
  #herald-ui .toggle-row .toggle-label {
    font-size: 0.95em;
    color: #555;
    display: inline;
    margin: 0;
    font-weight: normal;
  }
  #herald-ui .toggle-switch {
    position: relative;
    display: inline-block;
    width: 52px;
    height: 26px;
    flex-shrink: 0;
  }
  #herald-ui .toggle-switch input { opacity: 0; width: 0; height: 0; position: absolute; }
  #herald-ui .toggle-slider {
    position: absolute;
    cursor: pointer;
    top: 0; left: 0; right: 0; bottom: 0;
    background-color: #aaa;
    border-radius: 26px;
    transition: .3s;
  }
  #herald-ui .toggle-slider:before {
    position: absolute;
    content: "";
    height: 20px;
    width: 20px;
    left: 3px;
    bottom: 3px;
    background-color: #fff;
    border-radius: 50%;
    transition: .3s;
  }
  #herald-ui .toggle-switch input:checked + .toggle-slider { background-color: #27ae60; }
  #herald-ui .toggle-switch input:checked + .toggle-slider:before { transform: translateX(26px); }
  #herald-ui .banner-info {
    background: #eaf6ff; border: 1px solid #a9d6f5; border-radius: 6px;
    padding: 10px 14px; margin-bottom: 14px; font-size: 0.92em; color: #1a5276;
  }
  #herald-ui .banner-warn {
    background: #fff8e1; border: 1px solid #f0d78c; border-radius: 6px;
    padding: 10px 14px; margin-bottom: 14px; font-size: 0.92em; color: #7a5c00;
  }
</style>

<div class="status-bar" id="herald-status-bar">
  <span><strong>Node:</strong> <span id="hs-node">—</span></span>
  <span><strong>MinInterval:</strong> <span id="hs-mininterval">—</span>s</span>
  <span><strong>SkywarnPlus:</strong> <span id="hs-swp">—</span></span>
  <span><strong>Herald:</strong> <span id="hs-enabled">—</span></span>
  <span><strong>Next tail:</strong> <span id="hs-countdown">—</span></span>
</div>

<div class="tabs">
  <button class="tab-btn active" data-tab="info">How It Works</button>
  <button class="tab-btn" data-tab="tail">Tail Messages</button>
  <button class="tab-btn" data-tab="scheduled">Scheduled Announcements</button>
  <button class="tab-btn" data-tab="timeweather">Time & Weather Announcements</button>
  <button class="tab-btn" data-tab="history">Playback History</button>
  <button class="tab-btn" data-tab="settings">Global Settings</button>
</div>

<!-- ══════════════════ HOW IT WORKS ══════════════════ -->
<div class="tab-panel active" id="tab-info">
  <div class="card">
    <h3>Tail Messages <span class="muted" style="font-weight:normal; font-size:0.85em;">(Unkey-Triggered)</span></h3>
    <p>A <strong>Tail Message</strong> plays automatically after someone unkeys on the node — timed so it plays after the courtesy tone, just like a native tail message. They rotate through your configured list in order, gated by the <strong>MinInterval</strong> so they don't play too frequently.</p>
    <ul style="margin: 8px 0 8px 20px; line-height: 1.8;">
      <li><strong>Tail messages always play on this local node only</strong> — they never go out to connected or linked nodes, regardless of any setting.</li>
      <li>When a SkywarnPlus WX alert is active, the WX audio takes priority over the rotation and plays instead (alternating with rotation entries while the alert persists).</li>
    </ul>

    <div style="background:#fff8e1; border:1px solid #f0c040; border-radius:6px; padding:10px 14px; margin-top:8px;">
      <strong>The RF / Network Trigger Toggle (in Settings)</strong><br>
      This toggle controls <em>what event triggers</em> a tail message — it does <strong>not</strong> change where the audio plays. Tail messages always play on this local node.
      <ul style="margin: 6px 0 0 20px; line-height:1.8;">
        <li><strong>RF only (toggle off):</strong> a tail message fires when a local RF transmission ends (someone keys up on your node's input).</li>
        <li><strong>RF + Network (toggle on):</strong> a tail message also fires when a connected AllStar node unkeys — useful if you want your node to tail-message after remote traffic too.</li>
      </ul>
    </div>
  </div>

  <div class="card">
    <h3>Scheduled Announcements <span class="muted" style="font-weight:normal; font-size:0.85em;">(Clock-Triggered)</span></h3>
    <p>A <strong>Scheduled Announcement</strong> plays at a configured time based on a cron schedule — completely independent of node activity or MinInterval. Common uses: ARRL Audio News every Saturday morning, a net reminder every Tuesday evening, or an ID drop every 30 minutes.</p>
    <ul style="margin: 8px 0 8px 20px; line-height: 1.8;">
      <li><strong>Waits for the node to unkey</strong> — if the node is in use when the scheduled time arrives, Herald holds the announcement and plays it as soon as the node is clear rather than talking over live traffic.</li>
      <li><strong>Takes priority over tail messages</strong> — if a tail message and a scheduled announcement would both fire at the same moment, the scheduled announcement always goes first.</li>
      <li><strong>Can play locally or globally</strong> — unlike tail messages, each scheduled announcement has its own <em>Play Mode</em>: <strong>Local</strong> plays on this node only; <strong>Global</strong> sends audio to all connected and linked AllStar nodes simultaneously.</li>
    </ul>

    <div style="background:#fdecea; border:1px solid #e74c3c; border-radius:6px; padding:10px 14px; margin-top:8px;">
      <strong>⚠ Use Global Play Mode with caution.</strong> Selecting Global sends the announcement audio to <em>every node currently linked to yours</em> — other clubs' repeaters, remote nodes, and any other systems in your AllStar network. Only choose Global if you are certain all connected nodes should receive this announcement. When in doubt, use Local.
    </div>
  </div>

  <div class="card">
    <h3>Time & Weather Announcements <span class="muted" style="font-weight:normal; font-size:0.85em;">(Clock-Triggered or On-Demand via DTMF)</span></h3>
    <p>Announces the current time (with an optional smart greeting — Good morning/afternoon/evening) and/or current weather conditions, on a cron schedule like Scheduled Announcements — top of every hour by default, but any cron pattern works. Unlike a fixed recording, the audio is generated fresh every time it plays.</p>
    <ul style="margin: 8px 0 8px 20px; line-height: 1.8;">
      <li><strong>Takes priority over Scheduled Announcements</strong> — if both are due at the same moment, Time & Weather always plays first; the Scheduled entry just plays right after instead of being skipped.</li>
      <li><strong>Waits for the node to unkey</strong>, same as Scheduled Announcements.</li>
      <li>Weather can come from NOAA METAR, Open-Meteo, your own WeatherFlow Tempest station, or — if SkywarnPlus is already installed — its already-fetched weather data, avoiding a second independent poller.</li>
      <li>Can also be triggered <strong>on demand over DTMF</strong> (e.g. a "press this code for the time and weather" function), independent of the schedule above (which doesn't have to be hourly - any cron pattern works). Add a function to your node's <code>rpt.conf</code> that runs <code>/usr/local/bin/herald play-timeweather</code> — pick whichever DTMF code fits your existing setup, this doesn't need to be any specific digit.</li>
    </ul>
  </div>
</div>

<!-- ══════════════════ TAIL MESSAGES (unkey-triggered) ══════════════════ -->
<div class="tab-panel" id="tab-tail">
  <div class="card">
    <h3>Rotation</h3>
    <p class="muted">Plays on the next transmission unkey, gated by MinInterval. A SkywarnPlus WX alert always takes priority over the rotation.</p>
    <table id="tail-table">
      <thead><tr><th>#</th><th>File</th><th>Days</th><th>Window</th><th>Node</th><th>Status</th><th>Actions</th></tr></thead>
      <tbody></tbody>
    </table>

    <div class="add-form">
      <h3 id="tail-form-heading">Add a Tail Message</h3>

      <label>Name (letters, numbers, hyphens only — no spaces)</label>
      <input type="text" id="tail-name" placeholder="e.g. weekend-notice">

      <div class="field-row" style="margin-top: 8px;">
        <div>
          <label>Days (optional — leave Daily for always eligible)</label>
          <div class="days-picker" id="tail-days">
            <label><input type="checkbox" value="daily" id="tail-day-daily" checked> Daily</label>
            <label><input type="checkbox" value="sunday"> Sun</label>
            <label><input type="checkbox" value="monday"> Mon</label>
            <label><input type="checkbox" value="tuesday"> Tue</label>
            <label><input type="checkbox" value="wednesday"> Wed</label>
            <label><input type="checkbox" value="thursday"> Thu</label>
            <label><input type="checkbox" value="friday"> Fri</label>
            <label><input type="checkbox" value="saturday"> Sat</label>
          </div>
        </div>
        <div>
          <label>Time Window (optional)</label>
          <input type="time" id="tail-time-start" style="width: 110px;">
          <span class="muted">to</span>
          <input type="time" id="tail-time-end" style="width: 110px;">
        </div>
        <div>
          <label>Node Override (optional)</label>
          <input type="text" id="tail-node" style="width: 120px;" placeholder="e.g. 501261">
        </div>
      </div>

      <div class="source-toggle" style="margin-top: 16px;">
        <label><input type="radio" name="tail-source" value="tts" checked> Text-to-Speech</label>
        <label><input type="radio" name="tail-source" value="file"> Upload File</label>
      </div>

      <div id="tail-tts-fields">
        <div class="tts-row">
          <div class="tts-voice">
            <label>Voice</label>
            <select id="tail-voice" style="display: block;"></select>
          </div>
          <div class="tts-text">
            <label>Text</label>
            <textarea id="tail-text" rows="3" placeholder="e.g. This is a test transmission" style="width: 100%;"></textarea>
          </div>
        </div>
      </div>
      <div id="tail-file-fields" style="display:none;">
        <label>Audio file (.wav or .mp3)</label>
        <input type="file" id="tail-file" accept=".wav,.mp3">
        <span class="muted" id="tail-file-keep-note" style="display:none;">Leave blank to keep the existing audio.</span>
      </div>

      <br>
      <button class="btn-primary" id="btn-add-tail">Add to Rotation</button>
      <button id="tail-edit-cancel" style="display:none;">Cancel Edit</button>
      <div class="msg" id="tail-msg"></div>
    </div>
  </div>
</div>

<!-- ══════════════════ SCHEDULED ANNOUNCEMENTS (clock-triggered) ══════════════════ -->
<div class="tab-panel" id="tab-scheduled">
  <div class="card">
    <h3>Scheduled Announcements</h3>
    <p class="muted">Plays on a cron schedule, independent of node activity or MinInterval.</p>
    <table id="sched-table">
      <thead><tr><th>Name</th><th>Minute</th><th>Hour</th><th>Day of Month</th><th>Month</th><th>Day of Week</th><th>Play Mode</th><th>Node</th><th>File</th><th>Status</th><th>Actions</th></tr></thead>
      <tbody></tbody>
    </table>

    <div class="add-form">
      <h3 id="sched-form-heading">Add a Scheduled Announcement</h3>

      <label>Name (letters, numbers, hyphens only — no spaces)</label>
      <input type="text" id="sched-name" placeholder="e.g. arrl-news">

      <div style="margin-top: 12px;">
        <label style="margin-bottom: 6px;">Cron Schedule</label>
        <div style="display:flex; gap:16px; align-items:flex-start; flex-wrap:wrap; margin-top:6px;">
          <div style="text-align:center;">
            <div style="font-size:0.9em; font-weight:bold; color:#444; margin-bottom:4px;">Minute</div>
            <input type="text" id="sched-cron-min"  value="*" style="width:72px; text-align:center; display:block; margin:0 auto;">
            <div style="font-size:0.88em; color:#666; margin-top:4px;">0–59</div>
          </div>
          <div style="text-align:center;">
            <div style="font-size:0.9em; font-weight:bold; color:#444; margin-bottom:4px;">Hour</div>
            <input type="text" id="sched-cron-hour" value="*" style="width:72px; text-align:center; display:block; margin:0 auto;">
            <div style="font-size:0.88em; color:#666; margin-top:4px;">0–23</div>
          </div>
          <div style="text-align:center;">
            <div style="font-size:0.9em; font-weight:bold; color:#444; margin-bottom:4px;">Day of Month</div>
            <input type="text" id="sched-cron-dom"  value="*" style="width:72px; text-align:center; display:block; margin:0 auto;">
            <div style="font-size:0.88em; color:#666; margin-top:4px;">1–31</div>
          </div>
          <div style="text-align:center;">
            <div style="font-size:0.9em; font-weight:bold; color:#444; margin-bottom:4px;">Month</div>
            <input type="text" id="sched-cron-mon"  value="*" style="width:72px; text-align:center; display:block; margin:0 auto;">
            <div style="font-size:0.88em; color:#666; margin-top:4px;">1–12</div>
          </div>
          <div style="text-align:center;">
            <div style="font-size:0.9em; font-weight:bold; color:#444; margin-bottom:4px;">Day of Week</div>
            <input type="text" id="sched-cron-dow"  value="*" style="width:110px; text-align:center; display:block; margin:0 auto;">
            <div style="font-size:0.88em; color:#666; margin-top:4px;">0=Sun … 6=Sat</div>
          </div>
        </div>
        <div style="margin-top:10px; font-size:1em; color:#333;">
          <strong>Syntax:</strong> &nbsp;<code>*</code> = every &nbsp;&nbsp; <code>*/n</code> = every n &nbsp;&nbsp; <code>n,m</code> = specific values &nbsp;&nbsp; <code>n-m</code> = range
        </div>
        <div style="font-size:1em; color:#555; margin-top:5px; font-style:italic;">
          ↓ See the Cron Reference and examples below.
        </div>
      </div>

      <div class="field-row" style="margin-top:12px;">
        <div>
          <label>Play Mode</label>
          <select id="sched-playmode">
            <option value="local" selected>Local (this node only)</option>
            <option value="global">Global (all connected/linked nodes)</option>
          </select>
          <p class="muted" style="margin-top:5px; margin-bottom:0; font-size:0.85em;"><strong>Global</strong> sends audio to every node currently linked to yours. Use with caution.</p>
        </div>
        <div>
          <label>Node Override (optional)</label>
          <input type="text" id="sched-node" style="width: 120px;" placeholder="e.g. 501261">
        </div>
      </div>

      <div class="source-toggle" style="margin-top: 16px;">
        <label><input type="radio" name="sched-source" value="tts" checked> Text-to-Speech</label>
        <label><input type="radio" name="sched-source" value="file"> Upload File</label>
      </div>

      <div id="sched-tts-fields">
        <div class="tts-row">
          <div class="tts-voice">
            <label>Voice</label>
            <select id="sched-voice" style="display: block;"></select>
          </div>
          <div class="tts-text">
            <label>Text</label>
            <textarea id="sched-text" rows="3" placeholder="e.g. ARRL Audio News follows" style="width: 100%;"></textarea>
          </div>
        </div>
      </div>
      <div id="sched-file-fields" style="display:none;">
        <label>Audio file (.wav or .mp3)</label>
        <input type="file" id="sched-file" accept=".wav,.mp3">
        <span class="muted" id="sched-file-keep-note" style="display:none;">Leave blank to keep the existing audio.</span>
      </div>

      <br>
      <button class="btn-primary" id="btn-add-sched">Add Scheduled Announcement</button>
      <button id="sched-edit-cancel" style="display:none;">Cancel Edit</button>
      <div class="msg" id="sched-msg"></div>

      <div style="margin-top:16px; padding:10px 14px; background:#f8f8f8; border:1px solid #ddd; border-radius:6px; font-size:0.88em; line-height:1.6;">
        <strong>Cron Reference</strong><br>
        <strong>Minute</strong> 0–59 &nbsp;|&nbsp; <strong>Hour</strong> 0–23 &nbsp;|&nbsp;
        <strong>Day of Month</strong> 1–31 &nbsp;|&nbsp; <strong>Month</strong> 1–12 &nbsp;|&nbsp;
        <strong>Day of Week</strong> 0=Sun, 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat<br>
        <strong>Syntax:</strong> &nbsp;<code>*</code> = every &nbsp;&nbsp;
        <code>*/n</code> = every n &nbsp;&nbsp;
        <code>n,m</code> = specific values &nbsp;&nbsp;
        <code>n-m</code> = range<br>
        <table style="margin-top:6px; border-collapse:collapse; width:auto;">
          <tr><td style="padding:1px 10px 1px 0; font-family:monospace; white-space:nowrap;">30 8 * * *</td><td style="color:#555;">Daily at 8:30 AM</td></tr>
          <tr><td style="padding:1px 10px 1px 0; font-family:monospace; white-space:nowrap;">*/20 * * * *</td><td style="color:#555;">Every 20 minutes</td></tr>
          <tr><td style="padding:1px 10px 1px 0; font-family:monospace; white-space:nowrap;">30 * * * *</td><td style="color:#555;">Every hour at :30 (12:30, 1:30, 2:30…)</td></tr>
          <tr><td style="padding:1px 10px 1px 0; font-family:monospace; white-space:nowrap;">0 8 * * 1-5</td><td style="color:#555;">Weekdays (Mon–Fri) at 8:00 AM</td></tr>
          <tr><td style="padding:1px 10px 1px 0; font-family:monospace; white-space:nowrap;">0 9 * * 0</td><td style="color:#555;">Sundays at 9:00 AM</td></tr>
          <tr><td style="padding:1px 10px 1px 0; font-family:monospace; white-space:nowrap;">0 9 1 * *</td><td style="color:#555;">1st of each month at 9:00 AM</td></tr>
          <tr><td style="padding:1px 10px 1px 0; font-family:monospace; white-space:nowrap;">0 12 * * 0,3</td><td style="color:#555;">Sundays and Wednesdays at noon</td></tr>
        </table>
      </div>
    </div>
  </div>
</div>

<!-- ══════════════════ TIME & WEATHER ANNOUNCEMENTS ══════════════════ -->
<div class="tab-panel" id="tab-timeweather">
  <div class="card">
    <h3>Time & Weather Announcements</h3>
    <p class="muted">Announces the time and/or current weather conditions, generated fresh every time it plays. Takes priority over Scheduled Announcements when both are due at the same moment — a Scheduled entry just plays right after this one finishes.</p>

    <div id="tw-sounds-warning" class="banner-warn" style="display:none;">
      The sound files this feature needs (digits, greetings, weather condition words) don't appear to be installed. Re-run <code>install.sh</code> to install them.
    </div>
    <div class="banner-info">
      Want this on-demand over DTMF too (independent of the schedule below)? Add a function to your node's <code>rpt.conf</code> that runs <code>/usr/local/bin/herald play-timeweather</code> — any DTMF code you like.
    </div>

    <div class="toggle-row">
      <label class="toggle-switch">
        <input type="checkbox" id="tw-enable">
        <span class="toggle-slider"></span>
      </label>
      <span class="toggle-label">Enable Time & Weather Announcements</span>
    </div>

    <p class="muted" style="margin-top:12px; margin-bottom:4px;">Choose what's included below — time, weather, or both. Each one reveals its own settings once turned on.</p>

    <div class="toggle-row" style="margin-top:8px;">
      <label class="toggle-switch">
        <input type="checkbox" id="tw-announce-time">
        <span class="toggle-slider"></span>
      </label>
      <span class="toggle-label">Announce Time</span>
    </div>
    <div class="toggle-row">
      <label class="toggle-switch">
        <input type="checkbox" id="tw-weather-enable">
        <span class="toggle-slider"></span>
      </label>
      <span class="toggle-label">Announce Weather</span>
    </div>
    <div class="toggle-row" style="margin-top:14px;">
      <label class="toggle-switch">
        <input type="checkbox" id="tw-smart-greeting">
        <span class="toggle-slider"></span>
      </label>
      <span class="toggle-label">Smart Greeting (Good morning/afternoon/evening, based on the hour)</span>
    </div>
    <p class="muted" style="margin-top:4px;">Plays before the announcement either way — with time, with weather, or with both.</p>
  </div>

  <div class="card" id="tw-time-card">
    <h3>Time</h3>
    <label>Time Format</label>
    <select id="tw-time-format" style="width:220px;">
      <option value="12">12-hour (with AM/PM)</option>
      <option value="24">24-hour</option>
    </select>
  </div>

  <div class="card" id="tw-weather-card">
    <h3>Weather</h3>
    <div id="tw-swp-banner" class="banner-info" style="display:none;">
      SkywarnPlus is installed on this system. Using the <strong>SkywarnPlus</strong> weather provider below avoids running a second, independent weather poller.
    </div>

    <div class="field-row">
      <div>
        <label>Weather Provider</label>
        <select id="tw-provider" style="width:340px;">
          <option value="auto">Auto (METAR for airport codes, Open-Meteo otherwise)</option>
          <option value="metar">NOAA METAR (ICAO airport codes only)</option>
          <option value="openmeteo">Open-Meteo (free, no key, any location)</option>
          <option value="tempest">My WeatherFlow Tempest station</option>
          <option value="skywarnplus">SkywarnPlus (reads its already-fetched weather)</option>
        </select>
      </div>
      <div id="tw-location-field">
        <label>Location (ZIP/postal code or ICAO airport code)</label>
        <input type="text" id="tw-location" style="width:180px;" placeholder="e.g. 92320 or KONT">
      </div>
      <div>
        <label>Temperature Unit</label>
        <select id="tw-temp-unit" style="width:90px;">
          <option value="F">°F</option>
          <option value="C">°C</option>
        </select>
      </div>
    </div>

    <div id="tw-tempest-fields" style="display:none; margin-top:10px;">
      <div class="field-row">
        <div>
          <label>Tempest Personal Access Token</label>
          <input type="text" id="tw-tempest-token" style="width:280px;" placeholder="tempest.earth/account">
        </div>
        <div>
          <label>Tempest Station ID (optional)</label>
          <input type="text" id="tw-tempest-station" style="width:140px;" placeholder="auto-detect if blank">
        </div>
      </div>
    </div>

    <div class="toggle-row" style="margin-top:14px;">
      <label class="toggle-switch">
        <input type="checkbox" id="tw-announce-condition">
        <span class="toggle-slider"></span>
      </label>
      <span class="toggle-label">Announce conditions (clear, rain, cloudy, ...)</span>
    </div>
    <div class="toggle-row">
      <label class="toggle-switch">
        <input type="checkbox" id="tw-announce-feels-like">
        <span class="toggle-slider"></span>
      </label>
      <span class="toggle-label">Announce feels-like temperature (if available from the provider)</span>
    </div>
    <div class="toggle-row">
      <label class="toggle-switch">
        <input type="checkbox" id="tw-announce-humidity">
        <span class="toggle-slider"></span>
      </label>
      <span class="toggle-label">Announce humidity percentage (if available from the provider)</span>
    </div>

    <div id="tw-cache-field" style="margin-top:14px;">
      <label>Weather Cache (minutes)</label>
      <input type="text" id="tw-cache-max-age" style="width:80px;">
      <span class="muted" style="margin-left:8px;">Skip re-fetching weather if the last reading is still this fresh — independent of how often the announcement itself plays.</span>
    </div>
  </div>

  <div class="card">
    <h3>Schedule</h3>
    <p class="muted">Same cron format as Scheduled Announcements.</p>
    <button id="tw-cron-hourly" style="margin-bottom:10px;">Every Hour (default)</button>
    <div style="display:flex; gap:16px; align-items:flex-start; flex-wrap:wrap; margin-top:6px;">
      <div style="text-align:center;">
        <div style="font-size:0.9em; font-weight:bold; color:#444; margin-bottom:4px;">Minute</div>
        <input type="text" id="tw-cron-min"  value="0" style="width:72px; text-align:center; display:block; margin:0 auto;">
        <div style="font-size:0.88em; color:#666; margin-top:4px;">0–59</div>
      </div>
      <div style="text-align:center;">
        <div style="font-size:0.9em; font-weight:bold; color:#444; margin-bottom:4px;">Hour</div>
        <input type="text" id="tw-cron-hour" value="*" style="width:72px; text-align:center; display:block; margin:0 auto;">
        <div style="font-size:0.88em; color:#666; margin-top:4px;">0–23</div>
      </div>
      <div style="text-align:center;">
        <div style="font-size:0.9em; font-weight:bold; color:#444; margin-bottom:4px;">Day of Month</div>
        <input type="text" id="tw-cron-dom"  value="*" style="width:72px; text-align:center; display:block; margin:0 auto;">
        <div style="font-size:0.88em; color:#666; margin-top:4px;">1–31</div>
      </div>
      <div style="text-align:center;">
        <div style="font-size:0.9em; font-weight:bold; color:#444; margin-bottom:4px;">Month</div>
        <input type="text" id="tw-cron-mon"  value="*" style="width:72px; text-align:center; display:block; margin:0 auto;">
        <div style="font-size:0.88em; color:#666; margin-top:4px;">1–12</div>
      </div>
      <div style="text-align:center;">
        <div style="font-size:0.9em; font-weight:bold; color:#444; margin-bottom:4px;">Day of Week</div>
        <input type="text" id="tw-cron-dow"  value="*" style="width:110px; text-align:center; display:block; margin:0 auto;">
        <div style="font-size:0.88em; color:#666; margin-top:4px;">0=Sun … 6=Sat</div>
      </div>
    </div>
    <div style="margin-top:10px; font-size:1em; color:#333;">
      <strong>Syntax:</strong> &nbsp;<code>*</code> = every &nbsp;&nbsp; <code>*/n</code> = every n &nbsp;&nbsp; <code>n,m</code> = specific values &nbsp;&nbsp; <code>n-m</code> = range
    </div>

    <br>
    <button class="btn-primary" id="btn-save-timeweather">Save &amp; Reload</button>
    <button class="btn-play" id="btn-test-timeweather">Test (local playback)</button>
    <div class="msg" id="timeweather-msg"></div>
  </div>
</div>

<!-- ══════════════════ PLAYBACK HISTORY ══════════════════ -->
<div class="tab-panel" id="tab-history">
  <div class="card">
    <h3>Playback History</h3>
    <p class="muted">Most recent plays first — rotation, SkywarnPlus WX, scheduled announcements, and manual test plays. Kept for the most recent 200 events.</p>
    <button class="btn-danger" id="btn-clear-history">Clear History</button>
    <div class="msg" id="history-msg"></div>
    <table id="history-table">
      <thead><tr><th>Time</th><th>Type</th><th>Name</th><th>File</th><th>Node</th><th>Play Mode</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>
</div>

<!-- ══════════════════ SETTINGS ══════════════════ -->
<div class="tab-panel" id="tab-settings">
  <div class="card">
    <h3>Herald Daemon</h3>
    <p class="muted">Status: <span id="set-herald-status">—</span></p>
    <p class="muted">Version: <span id="set-herald-version">—</span> <button id="btn-check-update">Check for Updates</button></p>
    <div class="msg" id="update-check-msg"></div>
    <button class="btn-toggle" id="btn-toggle-enable">Enable/Disable Herald</button>
    <button id="btn-reload">Reload Config</button>
    <div class="msg" id="herald-daemon-msg"></div>
  </div>

  <div class="card">
    <div style="display:flex; gap:32px; flex-wrap:wrap;">
      <div style="flex:1 1 280px;">
        <h3 style="margin-top:0;">General Settings</h3>
        <label>Node</label>
        <input type="text" id="set-node" style="width: 200px;">

        <label>Min Interval Between Tail Messages (seconds)</label>
        <input type="text" id="set-min-interval" style="width: 100px;">
        <span class="muted" style="margin-left: 8px;">e.g. 300 = 5 min, 600 = 10 min, 900 = 15 min</span>

        <div class="toggle-row">
          <span class="toggle-label">RF activation only</span>
          <label class="toggle-switch">
            <input type="checkbox" id="set-network-keyup-trigger">
            <span class="toggle-slider"></span>
          </label>
          <span class="toggle-label">RF and Network activation</span>
        </div>
        <p class="muted" style="margin-top: 6px; margin-bottom: 0;">Off: tail messages play after a local RF unkey only.<br>On: tail messages also play after a connected AllStar node unkeys.</p>

        <div class="toggle-row" style="margin-top: 16px;">
          <label class="toggle-switch">
            <input type="checkbox" id="set-debug">
            <span class="toggle-slider"></span>
          </label>
          <span class="toggle-label">Enable debug logging</span>
        </div>
      </div>

      <div style="flex:1 1 240px;">
        <h3 style="margin-top:0;">SkywarnPlus</h3>
        <div class="toggle-row" style="margin-top: 8px;">
          <label class="toggle-switch">
            <input type="checkbox" id="set-swp-enable">
            <span class="toggle-slider"></span>
          </label>
          <span class="toggle-label">Enable SkywarnPlus WX tail integration</span>
        </div>

        <label>WX Tail File Path</label>
        <input type="text" id="set-swp-wxfile" style="width: 100%;">

        <label>Silence Threshold (bytes)</label>
        <input type="text" id="set-swp-threshold" style="width: 100px;">
        <p class="muted" style="margin-top:10px; margin-bottom:0; font-size:0.9em;">When enabled, active WX alerts take priority over tail message rotation. Herald alternates between the WX alert and your normal rotation — the alert plays first, then one rotation message, then the alert again. A new or updated alert file always plays immediately on the next unkey. When no alert is active, normal rotation resumes. SkywarnPlus messages do not affect the cron-scheduled announcement timing.</p>
      </div>
    </div>

    <br>
    <button class="btn-primary" id="btn-save-settings">Save &amp; Reload</button>
    <div class="msg" id="settings-msg"></div>
  </div>

  <div class="card">
    <h3>Backup &amp; Restore</h3>
    <p class="muted">Export the full configuration (rotation, scheduled announcements, and settings) as a JSON file, or restore from a previously exported file. Restoring replaces the entire configuration.</p>
    <button id="btn-export-config">Download Config Backup</button>
    <br><br>
    <label>Restore from backup file</label>
    <input type="file" id="config-import-file" accept=".json">
    <button class="btn-danger" id="btn-import-config">Restore Config</button>
    <div class="msg" id="backup-msg"></div>
  </div>
</div>
</div>
