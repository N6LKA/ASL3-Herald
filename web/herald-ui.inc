<?php
// herald-ui.inc
// Shared UI for asl3-herald, included by herald-frame-allmon3.php and
// herald-frame-supermon.php after each has independently verified the
// visitor is logged into its host app. Do not include this file directly.
?>
<div id="herald-ui">
<style>
  #herald-ui {
    font-family: Arial, sans-serif;
    max-width: 900px;
    margin: 0 auto;
    color: #222;
  }
  #herald-ui h2 { margin-top: 0; }
  #herald-ui h3 { margin-bottom: 8px; }
  #herald-ui .card {
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
  #herald-ui .status-bar span { font-size: 0.9em; }
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
  #herald-ui table { width: 100%; border-collapse: collapse; margin-bottom: 12px; }
  #herald-ui th, #herald-ui td {
    text-align: left;
    padding: 6px 8px;
    border-bottom: 1px solid #ddd;
    font-size: 0.9em;
  }
  #herald-ui button { cursor: pointer; padding: 4px 10px; margin-right: 4px; }
  #herald-ui .btn-danger { background: #e74c3c; color: #fff; border: none; border-radius: 4px; }
  #herald-ui .btn-play   { background: #2980b9; color: #fff; border: none; border-radius: 4px; }
  #herald-ui .btn-primary{ background: #27ae60; color: #fff; border: none; border-radius: 4px; padding: 8px 16px; }
  #herald-ui .btn-toggle { background: #8e44ad; color: #fff; border: none; border-radius: 4px; }
  #herald-ui input[type=text], #herald-ui input[type=time], #herald-ui select {
    padding: 6px; margin: 4px 6px 4px 0;
  }
  #herald-ui .add-form { border-top: 2px solid #eee; margin-top: 12px; padding-top: 12px; }
  #herald-ui .add-form label { display: block; font-size: 0.85em; margin-top: 8px; }
  #herald-ui .days-picker label { display: inline-block; margin-right: 10px; font-weight: normal; }
  #herald-ui .source-toggle { margin: 8px 0; }
  #herald-ui .msg { font-weight: bold; margin-top: 8px; min-height: 1.2em; }
  #herald-ui .msg.ok { color: #27ae60; }
  #herald-ui .msg.err { color: #e74c3c; }
  #herald-ui .muted { color: #777; font-size: 0.85em; }
</style>

<h2>ASL3 Herald</h2>

<div class="status-bar" id="herald-status-bar">
  <span><strong>Node:</strong> <span id="hs-node">—</span></span>
  <span><strong>MinInterval:</strong> <span id="hs-mininterval">—</span>s</span>
  <span><strong>SkywarnPlus:</strong> <span id="hs-swp">—</span></span>
  <span>
    <button class="btn-toggle" id="btn-toggle-enable">Enable/Disable</button>
    <button id="btn-reload">Reload Config</button>
  </span>
</div>

<div class="tabs">
  <button class="tab-btn active" data-tab="tail">Tail Messages</button>
  <button class="tab-btn" data-tab="scheduled">Scheduled Announcements</button>
</div>

<!-- ════════════════════════ TAIL MESSAGES (unkey-triggered) ════════════════════════ -->
<div class="tab-panel active" id="tab-tail">
  <div class="card">
    <h3>Rotation</h3>
    <p class="muted">Plays on the next transmission unkey, gated by MinInterval. A SkywarnPlus WX alert always takes priority over the rotation.</p>
    <table id="tail-table">
      <thead><tr><th>#</th><th>File</th><th></th></tr></thead>
      <tbody></tbody>
    </table>

    <div class="add-form">
      <h3>Add a Tail Message</h3>
      <div class="source-toggle">
        <label><input type="radio" name="tail-source" value="tts" checked> Text-to-Speech</label>
        <label><input type="radio" name="tail-source" value="file"> Upload File</label>
      </div>

      <div id="tail-tts-fields">
        <label>Text</label>
        <input type="text" id="tail-text" style="width: 100%;" placeholder="e.g. This is a test transmission">
        <label>Voice</label>
        <select id="tail-voice"></select>
      </div>
      <div id="tail-file-fields" style="display:none;">
        <label>Audio file (.wav or .mp3)</label>
        <input type="file" id="tail-file" accept=".wav,.mp3">
      </div>

      <label>Name (letters, numbers, hyphens only)</label>
      <input type="text" id="tail-name" placeholder="e.g. weekend-notice">

      <br><br>
      <button class="btn-primary" id="btn-add-tail">Add to Rotation</button>
      <div class="msg" id="tail-msg"></div>
    </div>
  </div>
</div>

<!-- ════════════════════════ SCHEDULED ANNOUNCEMENTS (clock-triggered) ════════════════════════ -->
<div class="tab-panel" id="tab-scheduled">
  <div class="card">
    <h3>Scheduled Announcements</h3>
    <p class="muted">Plays at a specific time of day, independent of repeater activity or MinInterval.</p>
    <table id="sched-table">
      <thead><tr><th>Name</th><th>Time</th><th>Days</th><th>Week</th><th>File</th><th></th></tr></thead>
      <tbody></tbody>
    </table>

    <div class="add-form">
      <h3>Add a Scheduled Announcement</h3>
      <div class="source-toggle">
        <label><input type="radio" name="sched-source" value="tts" checked> Text-to-Speech</label>
        <label><input type="radio" name="sched-source" value="file"> Upload File</label>
      </div>

      <div id="sched-tts-fields">
        <label>Text</label>
        <input type="text" id="sched-text" style="width: 100%;" placeholder="e.g. ARRL Audio News follows">
        <label>Voice</label>
        <select id="sched-voice"></select>
      </div>
      <div id="sched-file-fields" style="display:none;">
        <label>Audio file (.wav or .mp3)</label>
        <input type="file" id="sched-file" accept=".wav,.mp3">
      </div>

      <label>Name</label>
      <input type="text" id="sched-name" placeholder="e.g. arrl-news">

      <label>Time (24-hour)</label>
      <input type="time" id="sched-time">

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

      <label>Week of month (optional — leave blank for every matching day)</label>
      <select id="sched-week">
        <option value="">Every week</option>
        <option value="1">1st week</option>
        <option value="2">2nd week</option>
        <option value="3">3rd week</option>
        <option value="4">4th week</option>
        <option value="5">Last week</option>
      </select>

      <br><br>
      <button class="btn-primary" id="btn-add-sched">Add Scheduled Announcement</button>
      <div class="msg" id="sched-msg"></div>
    </div>
  </div>
</div>

<script>
(function () {
  const API = '/asl3-herald/api/';

  function showMsg(el, text, ok) {
    el.textContent = text;
    el.className = 'msg ' + (ok ? 'ok' : 'err');
  }

  async function api(path, options) {
    const res = await fetch(API + path, options || {});
    let data;
    try { data = await res.json(); } catch (e) { data = { success: false, message: 'Invalid server response' }; }
    return data;
  }

  // ── Tabs ────────────────────────────────────────────────────────
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    });
  });

  // ── Source toggles (TTS vs file upload) ────────────────────────
  function wireSourceToggle(name, ttsFieldsId, fileFieldsId) {
    document.querySelectorAll('input[name="' + name + '"]').forEach(radio => {
      radio.addEventListener('change', () => {
        const isTts = document.querySelector('input[name="' + name + '"]:checked').value === 'tts';
        document.getElementById(ttsFieldsId).style.display = isTts ? '' : 'none';
        document.getElementById(fileFieldsId).style.display = isTts ? 'none' : '';
      });
    });
  }
  wireSourceToggle('tail-source', 'tail-tts-fields', 'tail-file-fields');
  wireSourceToggle('sched-source', 'sched-tts-fields', 'sched-file-fields');

  // "Daily" checkbox disables the individual day checkboxes
  document.getElementById('sched-day-daily').addEventListener('change', function () {
    document.querySelectorAll('#sched-days input[type=checkbox]:not(#sched-day-daily)')
      .forEach(cb => { cb.disabled = this.checked; if (this.checked) cb.checked = false; });
  });

  // ── Load voices ──────────────────────────────────────────────────
  async function loadVoices() {
    const data = await api('voices.php');
    const voices = (data && data.voices) || [];
    ['tail-voice', 'sched-voice'].forEach(id => {
      const sel = document.getElementById(id);
      sel.innerHTML = '';
      if (voices.length === 0) {
        sel.innerHTML = '<option value="">Default</option>';
        return;
      }
      voices.forEach(v => {
        const opt = document.createElement('option');
        opt.value = v; opt.textContent = v;
        sel.appendChild(opt);
      });
    });
  }

  // ── Load status + lists ──────────────────────────────────────
  async function loadAll() {
    const data = await api('list.php');
    if (!data || data.success === false) return;

    document.getElementById('hs-node').textContent = data.node || '—';
    document.getElementById('hs-mininterval').textContent = data.tail_message.min_interval;
    document.getElementById('hs-swp').textContent = data.tail_message.skywarnplus.enable ? 'enabled' : 'disabled';

    const tbody = document.querySelector('#tail-table tbody');
    tbody.innerHTML = '';
    (data.tail_message.rotation || []).forEach((file, i) => {
      const name = file.split('/').pop().replace(/\.wav$/, '');
      const tr = document.createElement('tr');
      tr.innerHTML = '<td>' + (i + 1) + '</td><td>' + file + '</td><td>' +
        '<button class="btn-play" data-name="' + name + '">Play</button>' +
        '<button class="btn-danger" data-name="' + name + '">Remove</button></td>';
      tbody.appendChild(tr);
    });

    const stbody = document.querySelector('#sched-table tbody');
    stbody.innerHTML = '';
    (data.scheduled || []).forEach(s => {
      const days = Array.isArray(s.Days) ? s.Days.join(', ') : s.Days;
      const tr = document.createElement('tr');
      tr.innerHTML = '<td>' + s.Name + '</td><td>' + s.Time + '</td><td>' + days + '</td>' +
        '<td>' + (s.Week || '—') + '</td><td>' + s.File + '</td><td>' +
        '<button class="btn-play" data-name="' + s.Name + '">Play</button>' +
        '<button class="btn-danger" data-name="' + s.Name + '">Remove</button></td>';
      stbody.appendChild(tr);
    });

    wireRowButtons();
  }

  function wireRowButtons() {
    document.querySelectorAll('.btn-play').forEach(btn => {
      btn.onclick = async () => {
        await api('play.php', { method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ name: btn.dataset.name }) });
      };
    });
    document.querySelectorAll('.btn-danger').forEach(btn => {
      btn.onclick = async () => {
        if (!confirm('Remove "' + btn.dataset.name + '"?')) return;
        await api('remove.php', { method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ name: btn.dataset.name }) });
        loadAll();
      };
    });
  }

  // ── Enable/disable + reload ────────────────────────────────
  document.getElementById('btn-toggle-enable').addEventListener('click', async () => {
    await api('toggle.php', { method: 'POST' });
    loadAll();
  });
  document.getElementById('btn-reload').addEventListener('click', async () => {
    await api('reload.php', { method: 'POST' });
    loadAll();
  });

  // ── Add tail message ──────────────────────────────────────
  document.getElementById('btn-add-tail').addEventListener('click', async () => {
    const msgEl = document.getElementById('tail-msg');
    const name = document.getElementById('tail-name').value.trim();
    const isTts = document.querySelector('input[name="tail-source"]:checked').value === 'tts';

    const form = new FormData();
    form.append('name', name);
    if (isTts) {
      form.append('mode', 'tts');
      form.append('text', document.getElementById('tail-text').value);
      form.append('voice', document.getElementById('tail-voice').value);
    } else {
      form.append('mode', 'file');
      const f = document.getElementById('tail-file').files[0];
      if (!f) { showMsg(msgEl, 'Choose a file first', false); return; }
      form.append('file', f);
    }

    const res = await fetch(API + 'add_rotation.php', { method: 'POST', body: form });
    const data = await res.json().catch(() => ({ success: false, message: 'Invalid server response' }));
    showMsg(msgEl, data.message || (data.success ? 'Added' : 'Failed'), data.success);
    if (data.success) loadAll();
  });

  // ── Add scheduled announcement ──────────────────────────────
  document.getElementById('btn-add-sched').addEventListener('click', async () => {
    const msgEl = document.getElementById('sched-msg');
    const name = document.getElementById('sched-name').value.trim();
    const time = document.getElementById('sched-time').value;
    const week = document.getElementById('sched-week').value;
    const isTts = document.querySelector('input[name="sched-source"]:checked').value === 'tts';

    let days = 'daily';
    if (!document.getElementById('sched-day-daily').checked) {
      const picked = Array.from(document.querySelectorAll('#sched-days input[type=checkbox]:checked:not(#sched-day-daily)'))
        .map(cb => cb.value);
      days = picked.length ? picked.join(',') : 'daily';
    }

    const form = new FormData();
    form.append('name', name);
    form.append('time', time);
    form.append('days', days);
    if (week) form.append('week', week);
    if (isTts) {
      form.append('mode', 'tts');
      form.append('text', document.getElementById('sched-text').value);
      form.append('voice', document.getElementById('sched-voice').value);
    } else {
      form.append('mode', 'file');
      const f = document.getElementById('sched-file').files[0];
      if (!f) { showMsg(msgEl, 'Choose a file first', false); return; }
      form.append('file', f);
    }

    const res = await fetch(API + 'add_scheduled.php', { method: 'POST', body: form });
    const data = await res.json().catch(() => ({ success: false, message: 'Invalid server response' }));
    showMsg(msgEl, data.message || (data.success ? 'Added' : 'Failed'), data.success);
    if (data.success) loadAll();
  });

  loadVoices();
  loadAll();
})();
</script>
</div>
