// herald-ui.js
//
// Behavior for asl3-herald's shared UI (herald-ui-fragment.php). Loaded via
// a real <script src> tag by whichever page includes the fragment — kept
// separate from the markup because scripts inserted via innerHTML never
// execute, and some host pages (e.g. asl3-herald.html inside Allmon3's own
// web root) inject the fragment that way.
(function () {
  const API = '/asl3-herald/api/';

  function showMsg(el, text, ok) {
    el.textContent = text;
    el.className = 'msg ' + (ok ? 'ok' : 'err');
  }

  function escapeAttr(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/"/g, '&quot;')
      .replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function basename(path) {
    return String(path || '').split('/').pop();
  }

  async function api(path, options) {
    const res = await fetch(API + path, options || {});
    let data;
    try { data = await res.json(); } catch (e) { data = { success: false, message: 'Invalid server response' }; }
    return data;
  }

  // ── Tabs ─────────────────────────────────────────────────────────────
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    });
  });

  // ── Source toggles (TTS vs file upload) ─────────────────────────────
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
  function wireDailyToggle(dailyId, containerId) {
    document.getElementById(dailyId).addEventListener('change', function () {
      document.querySelectorAll('#' + containerId + ' input[type=checkbox]:not(#' + dailyId + ')')
        .forEach(cb => { cb.disabled = this.checked; if (this.checked) cb.checked = false; });
    });
  }
  wireDailyToggle('sched-day-daily', 'sched-days');
  wireDailyToggle('tail-day-daily', 'tail-days');

  function pickedDays(dailyId, containerId) {
    if (document.getElementById(dailyId).checked) return 'daily';
    const picked = Array.from(document.querySelectorAll('#' + containerId + ' input[type=checkbox]:checked:not(#' + dailyId + ')'))
      .map(cb => cb.value);
    return picked.length ? picked.join(',') : 'daily';
  }

  function applyDaysToPicker(days, dailyId, containerId) {
    const isDaily = !days || days === 'daily';
    document.getElementById(dailyId).checked = isDaily;
    const dayList = String(days || '').split(',');
    document.querySelectorAll('#' + containerId + ' input[type=checkbox]:not(#' + dailyId + ')').forEach(cb => {
      cb.disabled = isDaily;
      cb.checked = !isDaily && dayList.includes(cb.value);
    });
  }

  // ── Load voices ──────────────────────────────────────────────────────
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

  // ── Load status + lists ──────────────────────────────────────────────
  async function loadAll() {
    const data = await api('list.php');
    if (!data || data.success === false) return;

    document.getElementById('hs-node').textContent = data.node || '—';
    document.getElementById('hs-mininterval').textContent = data.tail_message.min_interval;
    document.getElementById('hs-swp').textContent = data.tail_message.skywarnplus.enable ? 'enabled' : 'disabled';

    const heraldEnabled = !!data.herald_enabled;
    const heraldStatusText = heraldEnabled ? 'enabled' : 'DISABLED';
    const heraldStatusColor = heraldEnabled ? '#27ae60' : '#e74c3c';
    const hsEnabled = document.getElementById('hs-enabled');
    hsEnabled.textContent = heraldStatusText;
    hsEnabled.style.color = heraldStatusColor;
    hsEnabled.style.fontWeight = 'bold';
    const setHeraldStatus = document.getElementById('set-herald-status');
    setHeraldStatus.textContent = heraldStatusText;
    setHeraldStatus.style.color = heraldStatusColor;
    setHeraldStatus.style.fontWeight = 'bold';
    document.getElementById('set-herald-version').textContent = data.version || 'unknown';

    document.getElementById('set-node').value = data.node || '';
    document.getElementById('set-poll-interval').value = data.poll_interval;
    document.getElementById('set-min-interval').value = data.tail_message.min_interval;
    document.getElementById('set-debug').checked = !!data.debug;
    document.getElementById('set-swp-enable').checked = !!data.tail_message.skywarnplus.enable;
    document.getElementById('set-swp-wxfile').value = data.tail_message.skywarnplus.wx_tail_file || '';
    document.getElementById('set-swp-threshold').value = data.tail_message.skywarnplus.silence_threshold;

    const tbody = document.querySelector('#tail-table tbody');
    tbody.innerHTML = '';
    const rotationList = data.tail_message.rotation || [];
    rotationList.forEach((entry, i) => {
      const isObj = entry && typeof entry === 'object';
      const file = isObj ? (entry.File || '') : entry;
      const text = isObj ? entry.Text : null;
      const voice = isObj ? entry.Voice : null;
      const days = isObj ? entry.Days : null;
      const timeStart = isObj ? entry.TimeStart : null;
      const timeEnd = isObj ? entry.TimeEnd : null;
      const node = isObj ? entry.Node : null;
      const fileMissing = isObj && !!entry.FileMissing;
      const daysAttr = Array.isArray(days) ? days.join(',') : (days || 'daily');
      const daysDisplay = Array.isArray(days) ? days.join(', ') : (days || 'Daily');
      const windowDisplay = (timeStart || timeEnd) ? ((timeStart || '00:00') + '–' + (timeEnd || '23:59')) : '—';
      const name = basename(file).replace(/\.wav$/, '');
      const canMoveUp = i > 0;
      const canMoveDown = i < rotationList.length - 1;
      const tr = document.createElement('tr');
      tr.innerHTML = '<td>' + (i + 1) + '</td><td>' + basename(file) + (fileMissing ? ' <span class="badge-missing">MISSING FILE</span>' : '') + '</td><td>' + daysDisplay + '</td>' +
        '<td>' + windowDisplay + '</td><td>' + (node || '—') + '</td><td>' +
        '<button class="btn-reorder" data-name="' + name + '" data-direction="up" title="Move up"' + (canMoveUp ? '' : ' disabled') + '>&uarr;</button>' +
        '<button class="btn-reorder" data-name="' + name + '" data-direction="down" title="Move down"' + (canMoveDown ? '' : ' disabled') + '>&darr;</button>' +
        '<button class="btn-play" data-name="' + name + '">Test (local playback)</button>' +
        '<button class="btn-edit" data-type="tail" data-name="' + name + '" data-text="' + escapeAttr(text) + '" data-voice="' + escapeAttr(voice) + '" data-days="' + escapeAttr(daysAttr) + '" data-time-start="' + escapeAttr(timeStart) + '" data-time-end="' + escapeAttr(timeEnd) + '" data-node="' + escapeAttr(node) + '">Edit</button>' +
        '<button class="btn-danger" data-name="' + name + '">Remove</button></td>';
      tbody.appendChild(tr);
    });

    const stbody = document.querySelector('#sched-table tbody');
    stbody.innerHTML = '';
    (data.scheduled || []).forEach(s => {
      const daysAttr = Array.isArray(s.Days) ? s.Days.join(',') : (s.Days || 'daily');
      const daysDisplay = Array.isArray(s.Days) ? s.Days.join(', ') : s.Days;
      const playMode = s.PlayMode === 'global' ? 'global' : 'local';
      const fileMissing = !!s.FileMissing;
      const tr = document.createElement('tr');
      tr.innerHTML = '<td>' + s.Name + '</td><td>' + s.Time + '</td><td>' + daysDisplay + '</td>' +
        '<td>' + (s.Week || '—') + '</td><td>' + (playMode === 'global' ? 'Global' : 'Local') + '</td>' +
        '<td>' + (s.Node || '—') + '</td>' +
        '<td>' + basename(s.File) + (fileMissing ? ' <span class="badge-missing">MISSING FILE</span>' : '') + '</td><td>' +
        '<button class="btn-play" data-name="' + s.Name + '">Test (local playback)</button>' +
        '<button class="btn-edit" data-type="sched" data-name="' + s.Name + '" data-time="' + s.Time + '" data-days="' + daysAttr + '" data-week="' + (s.Week || '') + '" data-playmode="' + playMode + '" data-node="' + escapeAttr(s.Node) + '" data-text="' + escapeAttr(s.Text) + '" data-voice="' + escapeAttr(s.Voice) + '">Edit</button>' +
        '<button class="btn-danger" data-name="' + s.Name + '">Remove</button></td>';
      stbody.appendChild(tr);
    });

    wireRowButtons();
    loadHistory();
  }

  // ── Playback history ─────────────────────────────────────────────────
  async function loadHistory() {
    const data = await api('playback_history.php');
    const tbody = document.querySelector('#history-table tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    const history = (data && data.history) || [];
    if (!history.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="muted">(no playback recorded yet)</td></tr>';
      return;
    }
    const typeLabels = { rotation: 'Rotation', wx: 'SkywarnPlus WX', scheduled: 'Scheduled', test: 'Manual Test' };
    history.forEach(h => {
      const tr = document.createElement('tr');
      tr.innerHTML = '<td>' + escapeAttr(h.time) + '</td><td>' + (typeLabels[h.type] || escapeAttr(h.type)) + '</td>' +
        '<td>' + escapeAttr(h.name) + '</td><td>' + escapeAttr(h.file) + '</td>' +
        '<td>' + escapeAttr(h.node) + '</td><td>' + (h.play_mode === 'global' ? 'Global' : 'Local') + '</td>';
      tbody.appendChild(tr);
    });
  }

  function wireRowButtons() {
    document.querySelectorAll('.btn-play').forEach(btn => {
      btn.onclick = async () => {
        await api('play.php', { method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ name: btn.dataset.name }) });
        loadHistory();
      };
    });
    document.querySelectorAll('.btn-reorder').forEach(btn => {
      btn.onclick = async () => {
        if (btn.disabled) return;
        await api('reorder_rotation.php', { method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ name: btn.dataset.name, direction: btn.dataset.direction }) });
        loadAll();
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
    document.querySelectorAll('.btn-edit').forEach(btn => {
      btn.onclick = () => {
        if (btn.dataset.type === 'tail') startEditTail(btn.dataset);
        else startEditSched(btn.dataset);
      };
    });
  }

  // ── Edit tail message ────────────────────────────────────────────────
  let editingTailName = null;

  function startEditTail(d) {
    editingTailName = d.name;
    document.getElementById('tail-name').value = d.name;
    const hasText = !!d.text;
    document.querySelector('input[name="tail-source"][value="' + (hasText ? 'tts' : 'file') + '"]').checked = true;
    document.getElementById('tail-tts-fields').style.display = hasText ? '' : 'none';
    document.getElementById('tail-file-fields').style.display = hasText ? 'none' : '';
    document.getElementById('tail-text').value = hasText ? d.text : '';
    document.getElementById('tail-voice').value = hasText ? (d.voice || '') : '';
    document.getElementById('tail-file').value = '';
    document.getElementById('tail-file-keep-note').style.display = hasText ? 'none' : '';
    applyDaysToPicker(d.days, 'tail-day-daily', 'tail-days');
    document.getElementById('tail-time-start').value = d.timeStart || '';
    document.getElementById('tail-time-end').value = d.timeEnd || '';
    document.getElementById('tail-node').value = d.node || '';
    document.getElementById('tail-form-heading').textContent = 'Edit Tail Message';
    document.getElementById('btn-add-tail').textContent = 'Save Changes';
    document.getElementById('tail-edit-cancel').style.display = '';
    document.getElementById('tail-msg').textContent = '';
    document.getElementById('tail-name').scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function cancelEditTail() {
    editingTailName = null;
    document.getElementById('tail-name').value = '';
    document.getElementById('tail-text').value = '';
    document.getElementById('tail-file').value = '';
    document.getElementById('tail-file-keep-note').style.display = 'none';
    applyDaysToPicker('daily', 'tail-day-daily', 'tail-days');
    document.getElementById('tail-time-start').value = '';
    document.getElementById('tail-time-end').value = '';
    document.getElementById('tail-node').value = '';
    document.getElementById('tail-form-heading').textContent = 'Add a Tail Message';
    document.getElementById('btn-add-tail').textContent = 'Add to Rotation';
    document.getElementById('tail-edit-cancel').style.display = 'none';
    document.getElementById('tail-msg').textContent = '';
  }
  document.getElementById('tail-edit-cancel').addEventListener('click', cancelEditTail);

  // ── Edit scheduled announcement ──────────────────────────────────────
  let editingSchedName = null;

  function startEditSched(d) {
    editingSchedName = d.name;
    document.getElementById('sched-name').value = d.name;
    document.getElementById('sched-time').value = d.time || '';
    document.getElementById('sched-week').value = d.week || '';
    document.getElementById('sched-playmode').value = d.playmode || 'local';
    document.getElementById('sched-node').value = d.node || '';

    applyDaysToPicker(d.days || 'daily', 'sched-day-daily', 'sched-days');

    const hasText = !!d.text;
    document.querySelector('input[name="sched-source"][value="' + (hasText ? 'tts' : 'file') + '"]').checked = true;
    document.getElementById('sched-tts-fields').style.display = hasText ? '' : 'none';
    document.getElementById('sched-file-fields').style.display = hasText ? 'none' : '';
    document.getElementById('sched-text').value = hasText ? d.text : '';
    document.getElementById('sched-voice').value = hasText ? (d.voice || '') : '';
    document.getElementById('sched-file').value = '';
    document.getElementById('sched-file-keep-note').style.display = hasText ? 'none' : '';

    document.getElementById('sched-form-heading').textContent = 'Edit Scheduled Announcement';
    document.getElementById('btn-add-sched').textContent = 'Save Changes';
    document.getElementById('sched-edit-cancel').style.display = '';
    document.getElementById('sched-msg').textContent = '';
    document.getElementById('sched-name').scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function cancelEditSched() {
    editingSchedName = null;
    document.getElementById('sched-name').value = '';
    document.getElementById('sched-time').value = '';
    document.getElementById('sched-text').value = '';
    document.getElementById('sched-file').value = '';
    document.getElementById('sched-file-keep-note').style.display = 'none';
    document.getElementById('sched-week').value = '';
    document.getElementById('sched-playmode').value = 'local';
    document.getElementById('sched-node').value = '';
    applyDaysToPicker('daily', 'sched-day-daily', 'sched-days');
    document.getElementById('sched-form-heading').textContent = 'Add a Scheduled Announcement';
    document.getElementById('btn-add-sched').textContent = 'Add Scheduled Announcement';
    document.getElementById('sched-edit-cancel').style.display = 'none';
    document.getElementById('sched-msg').textContent = '';
  }
  document.getElementById('sched-edit-cancel').addEventListener('click', cancelEditSched);

  // ── Enable/disable + reload ──────────────────────────────────────────
  document.getElementById('btn-toggle-enable').addEventListener('click', async () => {
    const msgEl = document.getElementById('herald-daemon-msg');
    const data = await api('toggle.php', { method: 'POST' });
    showMsg(msgEl, data.message || 'Toggled', data.success !== false);
    loadAll();
  });
  document.getElementById('btn-reload').addEventListener('click', async () => {
    const msgEl = document.getElementById('herald-daemon-msg');
    const data = await api('reload.php', { method: 'POST' });
    showMsg(msgEl, data.message || 'Config reloaded', data.success !== false);
    loadAll();
  });

  document.getElementById('btn-check-update').addEventListener('click', async () => {
    const msgEl = document.getElementById('update-check-msg');
    showMsg(msgEl, 'Checking...', true);
    const data = await api('version_check.php');
    if (!data.success) {
      showMsg(msgEl, data.message || 'Could not check for updates', false);
      return;
    }
    if (data.update_available) {
      showMsg(msgEl, 'Update available: v' + data.latest_version + ' (currently running v' + data.current_version + '). See the README for update instructions.', false);
    } else if (data.ahead_of_main) {
      showMsg(msgEl, 'Running v' + data.current_version + ', ahead of the latest release on main (v' + data.latest_version + ') - expected if installed from the develop branch for testing.', true);
    } else {
      showMsg(msgEl, 'Up to date (v' + data.current_version + ').', true);
    }
  });

  // ── Backup / restore ──────────────────────────────────────────────────
  document.getElementById('btn-export-config').addEventListener('click', () => {
    window.location.href = API + 'config_export.php';
  });

  document.getElementById('btn-import-config').addEventListener('click', async () => {
    const msgEl = document.getElementById('backup-msg');
    const f = document.getElementById('config-import-file').files[0];
    if (!f) { showMsg(msgEl, 'Choose a backup file first', false); return; }
    if (!confirm('This will replace the ENTIRE current configuration. Continue?')) return;
    const form = new FormData();
    form.append('file', f);
    const res = await fetch(API + 'config_import.php', { method: 'POST', body: form });
    const data = await res.json().catch(() => ({ success: false, message: 'Invalid server response' }));
    showMsg(msgEl, data.message || (data.success ? 'Config restored' : 'Failed'), data.success);
    if (data.success) loadAll();
  });

  // ── Settings ──────────────────────────────────────────────────────────
  document.getElementById('btn-save-settings').addEventListener('click', async () => {
    const msgEl = document.getElementById('settings-msg');
    const data = await api('settings.php', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        node: document.getElementById('set-node').value.trim(),
        poll_interval: document.getElementById('set-poll-interval').value,
        min_interval: document.getElementById('set-min-interval').value,
        debug: document.getElementById('set-debug').checked,
        swp_enable: document.getElementById('set-swp-enable').checked,
        swp_wxfile: document.getElementById('set-swp-wxfile').value.trim(),
        swp_threshold: document.getElementById('set-swp-threshold').value,
      }),
    });
    showMsg(msgEl, data.message || (data.success ? 'Settings saved and reloaded' : 'Failed'), data.success);
    if (data.success) loadAll();
  });

  // ── Add / edit tail message ──────────────────────────────────────────
  document.getElementById('btn-add-tail').addEventListener('click', async () => {
    const msgEl = document.getElementById('tail-msg');
    const name = document.getElementById('tail-name').value.trim();
    const isTts = document.querySelector('input[name="tail-source"]:checked').value === 'tts';

    const form = new FormData();
    form.append('name', name);
    form.append('days', pickedDays('tail-day-daily', 'tail-days'));
    form.append('time_start', document.getElementById('tail-time-start').value);
    form.append('time_end', document.getElementById('tail-time-end').value);
    form.append('node', document.getElementById('tail-node').value.trim());
    if (isTts) {
      form.append('mode', 'tts');
      form.append('text', document.getElementById('tail-text').value);
      form.append('voice', document.getElementById('tail-voice').value);
    } else {
      form.append('mode', 'file');
      const f = document.getElementById('tail-file').files[0];
      if (f) {
        form.append('file', f);
      } else if (!editingTailName) {
        showMsg(msgEl, 'Choose a file first', false);
        return;
      }
    }

    let endpoint = 'add_rotation.php';
    if (editingTailName) {
      form.append('old_name', editingTailName);
      endpoint = 'edit_rotation.php';
    }

    const res = await fetch(API + endpoint, { method: 'POST', body: form });
    const data = await res.json().catch(() => ({ success: false, message: 'Invalid server response' }));
    showMsg(msgEl, data.message || (data.success ? (editingTailName ? 'Updated' : 'Added') : 'Failed'), data.success);
    if (data.success) {
      cancelEditTail();
      loadAll();
    }
  });

  // ── Add / edit scheduled announcement ────────────────────────────────
  document.getElementById('btn-add-sched').addEventListener('click', async () => {
    const msgEl = document.getElementById('sched-msg');
    const name = document.getElementById('sched-name').value.trim();
    const time = document.getElementById('sched-time').value;
    const week = document.getElementById('sched-week').value;
    const playMode = document.getElementById('sched-playmode').value;
    const isTts = document.querySelector('input[name="sched-source"]:checked').value === 'tts';
    const days = pickedDays('sched-day-daily', 'sched-days');

    const form = new FormData();
    form.append('name', name);
    form.append('time', time);
    form.append('days', days);
    form.append('play_mode', playMode);
    form.append('node', document.getElementById('sched-node').value.trim());
    if (week) form.append('week', week);
    if (isTts) {
      form.append('mode', 'tts');
      form.append('text', document.getElementById('sched-text').value);
      form.append('voice', document.getElementById('sched-voice').value);
    } else {
      form.append('mode', 'file');
      const f = document.getElementById('sched-file').files[0];
      if (f) {
        form.append('file', f);
      } else if (!editingSchedName) {
        showMsg(msgEl, 'Choose a file first', false);
        return;
      }
    }

    let endpoint = 'add_scheduled.php';
    if (editingSchedName) {
      form.append('old_name', editingSchedName);
      endpoint = 'edit_scheduled.php';
    }

    const res = await fetch(API + endpoint, { method: 'POST', body: form });
    const data = await res.json().catch(() => ({ success: false, message: 'Invalid server response' }));
    showMsg(msgEl, data.message || (data.success ? (editingSchedName ? 'Updated' : 'Added') : 'Failed'), data.success);
    if (data.success) {
      cancelEditSched();
      loadAll();
    }
  });

  loadVoices();
  loadAll();
})();
