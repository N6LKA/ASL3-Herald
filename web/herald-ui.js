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

  async function api(path, options) {
    const res = await fetch(API + path, options || {});
    let data;
    try { data = await res.json(); } catch (e) { data = { success: false, message: 'Invalid server response' }; }
    return data;
  }

  // ── Tabs ─────────────────────────────────────────────────────
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    });
  });

  // ── Source toggles (TTS vs file upload) ───────────────────────────────────────
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

  // ── Load voices ──────────────────────────────────────────────────────────────
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

  // ── Load status + lists ───────────────────────────────────────────────────────
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

  // ── Enable/disable + reload ────────────────────────────────────────────────
  document.getElementById('btn-toggle-enable').addEventListener('click', async () => {
    await api('toggle.php', { method: 'POST' });
    loadAll();
  });
  document.getElementById('btn-reload').addEventListener('click', async () => {
    await api('reload.php', { method: 'POST' });
    loadAll();
  });

  // ── Add tail message ─────────────────────────────────────────────────────
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

  // ── Add scheduled announcement ─────────────────────────────────────────────
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
