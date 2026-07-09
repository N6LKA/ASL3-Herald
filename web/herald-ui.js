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
  document.getElementById('sched-day-daily').addEventListener('change', function () {
    document.querySelectorAll('#sched-days input[type=checkbox]:not(#sched-day-daily)')
      .forEach(cb => { cb.disabled = this.checked; if (this.checked) cb.checked = false; });
  });

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

    document.getElementById('set-node').value = data.node || '';
    document.getElementById('set-poll-interval').value = data.poll_interval;
    document.getElementById('set-min-interval').value = data.tail_message.min_interval;
    document.getElementById('set-debug').checked = !!data.debug;
    document.getElementById('set-swp-enable').checked = !!data.tail_message.skywarnplus.enable;
    document.getElementById('set-swp-wxfile').value = data.tail_message.skywarnplus.wx_tail_file || '';
    document.getElementById('set-swp-threshold').value = data.tail_message.skywarnplus.silence_threshold;

    const tbody = document.querySelector('#tail-table tbody');
    tbody.innerHTML = '';
    (data.tail_message.rotation || []).forEach((entry, i) => {
      const isObj = entry && typeof entry === 'object';
      const file = isObj ? (entry.File || '') : entry;
      const text = isObj ? entry.Text : null;
      const voice = isObj ? entry.Voice : null;
      const name = basename(file).replace(/\.wav$/, '');
      const tr = document.createElement('tr');
      tr.innerHTML = '<td>' + (i + 1) + '</td><td>' + basename(file) + '</td><td>' +
        '<button class="btn-play" data-name="' + name + '">Play</button>' +
        '<button class="btn-edit" data-type="tail" data-name="' + name + '" data-text="' + escapeAttr(text) + '" data-voice="' + escapeAttr(voice) + '">Edit</button>' +
        '<button class="btn-danger" data-name="' + name + '">Remove</button></td>';
      tbody.appendChild(tr);
    });

    const stbody = document.querySelector('#sched-table tbody');
    stbody.innerHTML = '';
    (data.scheduled || []).forEach(s => {
      const daysAttr = Array.isArray(s.Days) ? s.Days.join(',') : (s.Days || 'daily');
      const daysDisplay = Array.isArray(s.Days) ? s.Days.join(', ') : s.Days;
      const playMode = s.PlayMode === 'global' ? 'global' : 'local';
      const tr = document.createElement('tr');
      tr.innerHTML = '<td>' + s.Name + '</td><td>' + s.Time + '</td><td>' + daysDisplay + '</td>' +
        '<td>' + (s.Week || '—') + '</td><td>' + (playMode === 'global' ? 'Global' : 'Local') + '</td>' +
        '<td>' + basename(s.File) + '</td><td>' +
        '<button class="btn-play" data-name="' + s.Name + '">Play</button>' +
        '<button class="btn-edit" data-type="sched" data-name="' + s.Name + '" data-time="' + s.Time + '" data-days="' + daysAttr + '" data-week="' + (s.Week || '') + '" data-playmode="' + playMode + '" data-text="' + escapeAttr(s.Text) + '" data-voice="' + escapeAttr(s.Voice) + '">Edit</button>' +
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

    const days = d.days || 'daily';
    const isDaily = days === 'daily';
    document.getElementById('sched-day-daily').checked = isDaily;
    const dayList = days.split(',');
    document.querySelectorAll('#sched-days input[type=checkbox]:not(#sched-day-daily)').forEach(cb => {
      cb.disabled = isDaily;
      cb.checked = !isDaily && dayList.includes(cb.value);
    });

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
    document.getElementById('sched-day-daily').checked = true;
    document.querySelectorAll('#sched-days input[type=checkbox]:not(#sched-day-daily)').forEach(cb => { cb.disabled = true; cb.checked = false; });
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
    form.append('play_mode', playMode);
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
