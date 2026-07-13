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
    max-width: 1400px;
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
</style>

<div class="status-bar" id="herald-status-bar">
  <span><strong>Node:</strong> <span id="hs-node">—</span></span>
  <span><strong>MinInterval:</strong> <span id="hs-mininterval">—</span>s</span>
  <span><strong>SkywarnPlus:</strong> <span id="hs-swp">—</span></span>
  <span><strong>Herald:</strong> <span id="hs-enabled">—</span></span>
</div>

<div class="tabs">
  <button class="tab-btn active" data-tab="tail">Tail Messages</button>
  <button class="tab-btn" data-tab="scheduled">Scheduled Announcements</button>
  <button class="tab-btn" data-tab="history">Playback History</button>
  <button class="tab-btn" data-tab="settings">Settings</button>
</div>

<!-- ══════════════════ TAIL MESSAGES (unkey-triggered) ══════════════════ -->
<div class="tab-panel active" id="tab-tail">
  <div class="card">
    <h3>Rotation</h3>
    <p class="muted">Plays on the next transmission unkey, gated by MinInterval. A SkywarnPlus WX alert always takes priority over the rotation.</p>
    <table id="tail-table">
      <thead><tr><th>#</th><th>File</th><th>Days</th><th>Window</th><th>Node</th><th></th></tr></thead>
      <tbody></tbody>
    </table>

    <div class="add-form">
      <h3 id="tail-form-heading">Add a Tail Message</h3>

      <label>Name (letters, numbers, hyphens only)</label>
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
    <p class="muted">Plays at a specific time of day, independent of repeater activity or MinInterval.</p>
    <table id="sched-table">
      <thead><tr><th>Name</th><th>Time</th><th>Days</th><th>Week</th><th>Play Mode</th><th>Node</th><th>File</th><th></th></tr></thead>
      <tbody></tbody>
    </table>

    <div class="add-form">
      <h3 id="sched-form-heading">Add a Scheduled Announcement</h3>

      <label>Name</label>
      <input type="text" id="sched-name" placeholder="e.g. arrl-news">

      <div class="field-row" style="margin-top: 8px;">
        <div>
          <label>Time (24-hour)</label>
          <input type="time" id="sched-time">
        </div>
        <div>
          <label>Days</label>
          <div class="days-picker" id="sched-days">
            <label><input type="checkbox" value="daily" id="sched-day-daily" checked> Daily</label>
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
          <label>Week of month (optional)</label>
          <select id="sched-week">
            <option value="">Every week</option>
            <option value="1">1st week</option>
            <option value="2">2nd week</option>
            <option value="3">3rd week</option>
            <option value="4">4th week</option>
            <option value="5">Last week</option>
          </select>
        </div>
      </div>

      <div class="field-row">
        <div>
          <label>Play Mode</label>
          <select id="sched-playmode">
            <option value="local" selected>Local (this node only)</option>
            <option value="global">Global (all connected/linked nodes)</option>
          </select>
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
    </div>
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

  <div style="display:flex; gap:16px; align-items:flex-start; flex-wrap:wrap;">
    <div class="card" style="flex:1 1 300px;">
      <h3>General Settings</h3>
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

      <br><br>
      <button class="btn-primary" id="btn-save-settings">Save &amp; Reload</button>
      <div class="msg" id="settings-msg"></div>
    </div>

    <div class="card" style="flex:1 1 280px;">
      <h3>SkywarnPlus</h3>
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
    </div>
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
