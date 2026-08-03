// herald-ui.js
//
// Behavior for asl3-herald's shared UI (herald-ui-fragment.php). Loaded via
// a real <script src> tag by whichever page includes the fragment — kept
// separate from the markup because scripts inserted via innerHTML never
// execute, and some host pages (e.g. asl3-herald.html inside Allmon3's own
// web root) inject the fragment that way.
(function () {
  const API = '/asl3-herald/api/';

  // Auto-clears after 6 s so users don't have to refresh to dismiss notices.
  function showMsg(el, text, ok) {
    el.textContent = text;
    el.className = 'msg ' + (ok ? 'ok' : 'err');
    clearTimeout(el._autoHide);
    el._autoHide = setTimeout(() => {
      el.textContent = '';
      el.className = 'msg';
    }, 6000);
  }

  function escapeAttr(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/"/g, '&quot;')
      .replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function basename(path) {
    return String(path || '').split('/').pop();
  }

  function titleCase(s) {
    return String(s || '').replace(/\b\w/g, c => c.toUpperCase());
  }

  async function api(path, options) {
    const res = await fetch(API + path, options || {});
    let data;
    try { data = await res.json(); } catch (e) { data = { success: false, message: 'Invalid server response' }; }
    return data;
  }

  // ── Countdown timer ────────────────────────────────────────────────────────────────────
  let _cdTimer = null;
  let _cdPoller = null;
  let _cdMinInt = 300;
  let _cdLastPlayed = 0;

  function _tickCountdown() {
    const el = document.getElementById('hs-countdown');
    if (!el) return;
    if (_cdLastPlayed === 0) {
      el.textContent = 'Ready';
      el.style.color = '#27ae60';
      return;
    }
    const remaining = _cdMinInt - (Date.now() / 1000 - _cdLastPlayed);
    if (remaining <= 0) {
      el.textContent = 'Ready';
      el.style.color = '#27ae60';
    } else {
      const m = Math.floor(remaining / 60);
      const s = Math.floor(remaining % 60);
      el.textContent = m + ':' + String(s).padStart(2, '0');
      el.style.color = '';
    }
  }

  function startCountdown(minInterval, lastTailPlayed) {
    _cdMinInt = minInterval;
    _cdLastPlayed = lastTailPlayed;
    clearInterval(_cdTimer);
    _tickCountdown();
    _cdTimer = setInterval(_tickCountdown, 1000);
  }

  // Polls the server every 10 s so the countdown resets automatically when a
  // tail message plays, without requiring a page refresh.
  async function _pollCountdown() {
    const data = await api('list.php');
    if (!data || !data.tail_message) return;
    const newLastPlayed = data.tail_message.last_tail_played || 0;
    if (newLastPlayed !== _cdLastPlayed) {
      startCountdown(data.tail_message.min_interval, newLastPlayed);
    }
    renderUpdateBadge(data.update_check);
  }

  // ── Update-available header badge ──────────────────────────────────────────
  // Shared by the automatic nightly check (reflected via list.php's
  // update_check field, picked up by the 10 s poll above and by loadAll())
  // and the manual "Check for Updates" button (which calls this directly
  // with its own fresh response so the badge appears immediately instead of
  // waiting up to 10 s for the next poll).
  function renderUpdateBadge(updateCheck) {
    const badge = document.getElementById('hs-update');
    if (!badge || !updateCheck) return;
    if (updateCheck.update_available) {
      const version = updateCheck.latest_version || '?';
      document.getElementById('hs-update-version').textContent = version;
      badge.href = 'https://github.com/N6LKA/ASL3-Herald/releases/tag/v' + version;
      badge.style.display = '';
    } else {
      badge.style.display = 'none';
    }
  }

  // ── Tabs ───────────────────────────────────────────────────────────────────────────────
  // History tab polls every 10 s while active so new plays appear without
  // a manual page refresh; the interval is stopped when leaving the tab.
  let historyPoller = null;
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
      if (btn.dataset.tab === 'history') {
        loadHistory();
        if (!historyPoller) historyPoller = setInterval(loadHistory, 10000);
      } else {
        clearInterval(historyPoller);
        historyPoller = null;
      }
    });
  });

  // ── Source toggles (TTS vs file upload) ────────────────────────────────────────────
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

  // ── Speed sliders (Tail Messages / Scheduled Announcements / Time & Weather
  // Template messages) ─────────────────────────────────────────────────────
  // 1.0x = normal. Converted to Piper's own --length-scale (the inverse)
  // server-side only at the moment of TTS generation - see
  // speed_to_length_scale() in asl3-herald.py.
  function setSpeedSlider(sliderId, displayId, value) {
    const v = (parseFloat(value) || 1.0).toFixed(1);
    document.getElementById(sliderId).value = v;
    document.getElementById(displayId).textContent = v + 'x';
  }
  ['tail', 'sched', 'tw-msg'].forEach(prefix => {
    const slider = document.getElementById(prefix + '-speed');
    const display = document.getElementById(prefix + '-speed-display');
    slider.addEventListener('input', () => {
      display.textContent = parseFloat(slider.value).toFixed(1) + 'x';
    });
  });

  // "Daily" checkbox disables the individual day checkboxes (tail messages only)
  function wireDailyToggle(dailyId, containerId) {
    document.getElementById(dailyId).addEventListener('change', function () {
      document.querySelectorAll('#' + containerId + ' input[type=checkbox]:not(#' + dailyId + ')')
        .forEach(cb => { cb.disabled = this.checked; if (this.checked) cb.checked = false; });
    });
  }
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

  // ── Load voices ────────────────────────────────────────────────────────────────────────────
  const DEFAULT_VOICE = 'en_US-amy-medium';
  const VOICE_LABELS = {
    'en_US-amy-medium':                    'Amy (US Female)',
    'en_US-arctic-medium':                 'Arctic (US Multi-speaker)',
    'en_US-bryce-medium':                  'Bryce (US Male)',
    'en_US-hfc_female-medium':             'HFC Female (US Female)',
    'en_US-hfc_male-medium':               'HFC Male (US Male)',
    'en_US-joe-medium':                    'Joe (US Male)',
    'en_US-john-medium':                   'John (US Male)',
    'en_US-kristin-medium':                'Kristin (US Female)',
    'en_US-kusal-medium':                  'Kusal (US Male)',
    'en_US-lessac-medium':                 'Lessac (US Female)',
    'en_US-libritts_r-medium':             'LibriTTS (US Neutral)',
    'en_US-norman-medium':                 'Norman (US Male)',
    'en_US-ryan-medium':                   'Ryan (US Male)',
    'en_GB-alan-medium':                   'Alan (British Male)',
    'en_GB-alba-medium':                   'Alba (Scottish Female)',
    'en_GB-aru-medium':                    'Aru (British Female)',
    'en_GB-cori-medium':                   'Cori (British Female)',
    'en_GB-jenny_dioco-medium':            'Jenny (British Female)',
    'en_GB-northern_english_male-medium':  'Northern English Male',
  };
  // ── Voice catalog (Global Settings -> Voices) ─────────────────────────────
  // Catalog-derived labels take priority so any voice installed via the
  // Voices tab (or via SkywarnPlus-NG/asl3-tts, since they share the same
  // catalog + voice directory) gets a friendly name, not just the original
  // fixed 19-voice VOICE_LABELS map above.
  let _voiceCatalog = [];
  let _catalogLabels = {};

  function voiceLabel(id) {
    return VOICE_LABELS[id] || _catalogLabels[id] || id;
  }

  async function loadVoices() {
    const data = await api('voices.php');
    const voices = (data && data.voices) || [];
    ['tail-voice', 'sched-voice', 'tw-msg-voice', 'nodeid-voice'].forEach(id => {
      const sel = document.getElementById(id);
      sel.innerHTML = '';
      if (voices.length === 0) {
        sel.innerHTML = '<option value="">Default</option>';
        return;
      }
      voices.forEach(v => {
        const opt = document.createElement('option');
        opt.value = v; opt.textContent = voiceLabel(v);
        sel.appendChild(opt);
      });
      if (voices.includes(DEFAULT_VOICE)) sel.value = DEFAULT_VOICE;
    });
  }

  async function loadVoiceCatalog() {
    const data = await api('catalog_voices.php');
    if (!data || data.success === false) return;
    _voiceCatalog = data.voices || [];
    _catalogLabels = {};
    _voiceCatalog.forEach(v => { _catalogLabels[v.id] = v.label; });

    const regionSel = document.getElementById('voices-region');
    const prevRegion = regionSel.value;
    regionSel.innerHTML = '';
    (data.regions || []).forEach(r => {
      const opt = document.createElement('option');
      opt.value = r; opt.textContent = r;
      regionSel.appendChild(opt);
    });
    if (prevRegion && (data.regions || []).includes(prevRegion)) regionSel.value = prevRegion;

    populateVoiceCatalogSelect();
  }

  function populateVoiceCatalogSelect() {
    const region = document.getElementById('voices-region').value;
    const sel = document.getElementById('voices-select');
    const prevVoice = sel.value;
    sel.innerHTML = '';
    _voiceCatalog.filter(v => v.region === region).forEach(v => {
      const opt = document.createElement('option');
      opt.value = v.id;
      opt.textContent = v.label + (v.installed ? ' (installed)' : ' (not installed)');
      sel.appendChild(opt);
    });
    if (prevVoice) sel.value = prevVoice;

    const installedCount = _voiceCatalog.filter(v => v.installed).length;
    const countEl = document.getElementById('voices-count');
    if (countEl) countEl.textContent = installedCount + ' of ' + _voiceCatalog.length + ' voices installed';

    updateVoiceButtons();
  }

  function updateVoiceButtons() {
    const voiceId = document.getElementById('voices-select').value;
    const entry = _voiceCatalog.find(v => v.id === voiceId);
    const installed = !!(entry && entry.installed);
    document.getElementById('btn-install-voice').classList.toggle('btn-hidden', installed);
    document.getElementById('btn-remove-voice').classList.toggle('btn-hidden', !installed);
  }

  // ── Load status + lists ────────────────────────────────────────────────────────────────────────
  async function loadAll() {
    const data = await api('list.php');
    if (!data || data.success === false) return;

    document.getElementById('hs-node').textContent = data.node || '—';
    document.getElementById('hs-mininterval').textContent = data.tail_message.min_interval;
    const swpEnabled = !!data.tail_message.skywarnplus.enable;
    const swpIsNg = !!data.tail_message.skywarnplus.ng_enable;
    document.getElementById('hs-swp-label').textContent = swpIsNg ? 'SkywarnPlus-NG:' : 'SkywarnPlus:';
    const hsSwp = document.getElementById('hs-swp');
    hsSwp.textContent = swpEnabled ? 'Enabled' : 'Disabled';
    hsSwp.style.color = swpEnabled ? '#27ae60' : '#e74c3c';
    hsSwp.style.fontWeight = 'bold';
    startCountdown(data.tail_message.min_interval, data.tail_message.last_tail_played || 0);
    renderUpdateBadge(data.update_check);

    const heraldEnabled = !!data.herald_enabled;
    const heraldStatusText = heraldEnabled ? 'Enabled' : 'Disabled';
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
    document.getElementById('set-min-interval').value = data.tail_message.min_interval;
    document.getElementById('set-debug').checked = !!data.debug;
    document.getElementById('set-network-keyup-trigger').checked = !!data.tail_message.network_keyup_trigger;
    document.getElementById('set-swp-enable').checked = !!data.tail_message.skywarnplus.enable;
    document.getElementById('set-swp-wxfile').value = data.tail_message.skywarnplus.wx_tail_file || '';
    document.getElementById('set-swp-threshold').value = data.tail_message.skywarnplus.silence_threshold;
    updateSwpFieldsVisibility();
    document.getElementById('set-swp-ng-enable').checked = !!data.tail_message.skywarnplus.ng_enable;
    document.getElementById('set-swp-ng-apibase').value = data.tail_message.skywarnplus.ng_apibase || '';
    document.getElementById('set-swp-ng-pollinterval').value = data.tail_message.skywarnplus.ng_pollinterval;
    updateSwpNgFieldsVisibility();

    const defaultNode = data.node || '—';
    const tbody = document.querySelector('#tail-table tbody');
    tbody.innerHTML = '';
    const rotationList = data.tail_message.rotation || [];
    rotationList.forEach((entry, i) => {
      const isObj = entry && typeof entry === 'object';
      const file = isObj ? (entry.File || '') : entry;
      const text = isObj ? entry.Text : null;
      const voice = isObj ? entry.Voice : null;
      const speed = isObj ? (entry.Speed || 1.0) : 1.0;
      const days = isObj ? entry.Days : null;
      const timeStart = isObj ? entry.TimeStart : null;
      const timeEnd = isObj ? entry.TimeEnd : null;
      const node = isObj ? entry.Node : null;
      const enabled = isObj ? (entry.Enabled !== false) : true;
      const fileMissing = isObj && !!entry.FileMissing;
      const daysAttr = Array.isArray(days) ? days.join(',') : (days || 'daily');
      const daysDisplay = Array.isArray(days) ? days.map(titleCase).join(', ') : titleCase(days || 'daily');
      const windowDisplay = (timeStart || timeEnd) ? ((timeStart || '00:00') + '–' + (timeEnd || '23:59')) : '—';
      const name = basename(file).replace(/\.wav$/, '');
      const canMoveUp = i > 0;
      const canMoveDown = i < rotationList.length - 1;
      const tr = document.createElement('tr');
      if (!enabled) tr.classList.add('sched-disabled');
      tr.innerHTML = '<td>' + (i + 1) + '</td><td class="col-wrap">' + basename(file) + (fileMissing ? ' <span class="badge-missing">MISSING FILE</span>' : '') + '</td><td>' + daysDisplay + '</td>' +
        '<td>' + windowDisplay + '</td><td>' + (node || defaultNode) + '</td>' +
        '<td><button class="' + (enabled ? 'btn-enable' : 'btn-disable') + ' btn-toggle-rot" data-name="' + escapeAttr(name) + '">' + (enabled ? 'Enabled' : 'Disabled') + '</button></td>' +
        '<td>' +
        '<button class="btn-reorder" data-name="' + name + '" data-direction="up" title="Move up"' + (canMoveUp ? '' : ' disabled') + '>&uarr;</button>' +
        '<button class="btn-reorder" data-name="' + name + '" data-direction="down" title="Move down"' + (canMoveDown ? '' : ' disabled') + '>&darr;</button>' +
        '<button class="btn-play" data-name="' + name + '">Test (local playback)</button>' +
        '<button class="btn-edit" data-type="tail" data-name="' + name + '" data-text="' + escapeAttr(text) + '" data-voice="' + escapeAttr(voice) + '" data-speed="' + escapeAttr(speed) + '" data-days="' + escapeAttr(daysAttr) + '" data-time-start="' + escapeAttr(timeStart) + '" data-time-end="' + escapeAttr(timeEnd) + '" data-node="' + escapeAttr(node) + '">Edit</button>' +
        '<button class="btn-danger" data-name="' + name + '">Remove</button></td>';
      tbody.appendChild(tr);
    });
    const stbody = document.querySelector('#sched-table tbody');
    stbody.innerHTML = '';
    (data.scheduled || []).forEach(s => {
      const playMode = s.PlayMode === 'global' ? 'global' : 'local';
      const fileMissing = !!s.FileMissing;
      const enabled = s.Enabled !== false;
      const cron = s.Cron || '* * * * *';
      const cronParts = cron.split(/\s+/);
      const [cMin, cHour, cDom, cMon, cDow] = [
        cronParts[0] || '*', cronParts[1] || '*', cronParts[2] || '*',
        cronParts[3] || '*', cronParts[4] || '*',
      ];
      const tr = document.createElement('tr');
      if (!enabled) tr.classList.add('sched-disabled');
      tr.innerHTML =
        '<td class="col-wrap">' + escapeAttr(s.Name) + '</td>' +
        '<td><code>' + escapeAttr(cMin)  + '</code></td>' +
        '<td><code>' + escapeAttr(cHour) + '</code></td>' +
        '<td><code>' + escapeAttr(cDom)  + '</code></td>' +
        '<td><code>' + escapeAttr(cMon)  + '</code></td>' +
        '<td><code>' + escapeAttr(cDow)  + '</code></td>' +
        '<td>' + (playMode === 'global' ? 'Global' : 'Local') + '</td>' +
        '<td>' + escapeAttr(s.Node || defaultNode) + '</td>' +
        '<td class="col-wrap">' + basename(s.File) + (fileMissing ? ' <span class="badge-missing">MISSING FILE</span>' : '') + '</td>' +
        '<td><button class="' + (enabled ? 'btn-enable' : 'btn-disable') + ' btn-toggle-sched" data-name="' + escapeAttr(s.Name) + '">' + (enabled ? 'Enabled' : 'Disabled') + '</button></td>' +
        '<td>' +
        '<button class="btn-play" data-name="' + escapeAttr(s.Name) + '">Test (local playback)</button>' +
        '<button class="btn-edit" data-type="sched" data-name="' + escapeAttr(s.Name) + '" data-cron="' + escapeAttr(cron) + '" data-playmode="' + playMode + '" data-node="' + escapeAttr(s.Node) + '" data-text="' + escapeAttr(s.Text) + '" data-voice="' + escapeAttr(s.Voice) + '" data-speed="' + escapeAttr(s.Speed || 1.0) + '">Edit</button>' +
        '<button class="btn-danger" data-name="' + escapeAttr(s.Name) + '">Remove</button>' +
        '</td>';
      stbody.appendChild(tr);
    });

    const tw = data.timeweather || {};
    const twWeather = tw.Weather || {};
    const twTemplates = tw.Templates || {};
    const twHealth = tw._health || {};
    document.getElementById('tw-enable').checked = !!tw.Enable;
    document.querySelector('input[name="tw-mode"][value="' + (tw.Mode === 'template' ? 'template' : 'recordings') + '"]').checked = true;
    document.getElementById('tw-announce-time').checked = tw.AnnounceTime !== false;
    document.getElementById('tw-time-format').value = tw.TimeFormat || '12';
    document.getElementById('tw-use-oclock').value = tw.UseOclock === true ? 'true' : 'false';
    document.getElementById('tw-minute-zero-word').value = tw.MinuteZeroWord === 'zero' ? 'zero' : 'oh';
    document.getElementById('tw-smart-greeting').checked = tw.SmartGreeting !== false;
    applyTwCronToPicker((tw.Schedule && tw.Schedule.Cron) || '0 * * * *');
    document.getElementById('tw-weather-enable').checked = twWeather.Enable !== false;
    document.getElementById('tw-provider').value = twWeather.Provider || 'auto';
    document.getElementById('tw-location').value = twWeather.Location || '';
    document.getElementById('tw-temp-unit').value = twWeather.TemperatureUnit || 'F';
    document.getElementById('tw-announce-condition').checked = twWeather.AnnounceCondition !== false;
    document.getElementById('tw-announce-feels-like').checked = !!twWeather.AnnounceFeelsLike;
    document.getElementById('tw-announce-humidity').checked = !!twWeather.AnnounceHumidity;
    document.getElementById('tw-cache-max-age').value = twWeather.CacheMaxAgeMin || 10;
    document.getElementById('tw-tempest-token').value = (twWeather.Tempest && twWeather.Tempest.Token) || '';
    document.getElementById('tw-tempest-station').value = (twWeather.Tempest && twWeather.Tempest.StationID) || '';
    document.getElementById('tw-wunderground-apikey').value = (twWeather.Wunderground && twWeather.Wunderground.ApiKey) || '';
    document.getElementById('tw-wunderground-station').value = (twWeather.Wunderground && twWeather.Wunderground.StationID) || '';
    document.getElementById('tw-snapshot-enable').checked = !!twWeather.SnapshotEnable;
    document.getElementById('tw-snapshot-path').value = twWeather.SnapshotPath || '/tmp/asl3-herald/weather.json';
    document.getElementById('tw-snapshot-label').value = twWeather.SnapshotLabel || '';
    updateSnapshotFieldsVisibility();
    document.getElementById('tw-callsign').value = twTemplates.Callsign || '';
    document.getElementById('tw-lookahead-seconds').value = twTemplates.LookaheadSeconds || 5;
    twSwpNgInstalled = !!twHealth.skywarnplus_ng_installed;
    updateTwProviderFields();
    updateTwSectionVisibility();

    document.getElementById('tw-sounds-warning').style.display =
      twHealth.sound_files_installed === false ? 'block' : 'none';
    document.getElementById('tw-piper-warning').style.display =
      twHealth.piper_installed === false ? 'block' : 'none';

    const twmbody = document.querySelector('#tw-messages-table tbody');
    twmbody.innerHTML = '';
    const twMessages = twTemplates.Messages || [];
    if (twMessages.length === 0) {
      twmbody.innerHTML = '<tr><td colspan="4" class="muted">(no messages yet - add one below)</td></tr>';
    }
    twMessages.forEach(m => {
      const enabled = m.Enabled !== false;
      const tr = document.createElement('tr');
      if (!enabled) tr.classList.add('sched-disabled');
      tr.innerHTML =
        '<td class="col-wrap">' + escapeAttr(m.Text) + '</td>' +
        '<td>' + escapeAttr(voiceLabel(m.Voice)) + '</td>' +
        '<td><button class="' + (enabled ? 'btn-enable' : 'btn-disable') + ' btn-toggle-tw-msg" data-id="' + escapeAttr(m.Id) + '">' + (enabled ? 'Enabled' : 'Disabled') + '</button></td>' +
        '<td>' +
        '<button class="btn-test-tw-msg" data-id="' + escapeAttr(m.Id) + '">Test</button>' +
        '<button class="btn-edit" data-type="tw-msg" data-id="' + escapeAttr(m.Id) + '" data-text="' + escapeAttr(m.Text) + '" data-voice="' + escapeAttr(m.Voice) + '" data-speed="' + escapeAttr(m.Speed || 1.0) + '">Edit</button>' +
        '<button class="btn-remove-tw-msg" data-id="' + escapeAttr(m.Id) + '">Remove</button>' +
        '</td>';
      twmbody.appendChild(tr);
    });

    const nodeId = data.node_id || {};
    const nodeIdHealth = nodeId._health || {};
    document.getElementById('nodeid-text').value = nodeId.Text || '';
    if (nodeId.Voice) document.getElementById('nodeid-voice').value = nodeId.Voice;
    document.getElementById('nodeid-piper-warning').style.display =
      nodeIdHealth.piper_installed === false ? 'block' : 'none';
    const nodeIdStatus = document.getElementById('nodeid-status');
    if (!nodeIdHealth.file_exists) {
      nodeIdStatus.textContent = 'No Node ID has been generated yet.';
    } else {
      nodeIdStatus.textContent = 'Currently deployed: "' + (nodeId.Text || '') + '" (' +
        voiceLabel(nodeId.Voice) + ')' +
        (nodeId.GeneratedAt ? ' - generated ' + nodeId.GeneratedAt : '');
    }

    wireRowButtons();
    loadHistory();
  }

  // ── Time & Weather Announcements ──────────────────────────────────────────────────────────
  let twSwpNgInstalled = false;

  function applyTwCronToPicker(cronExpr) {
    const parts = String(cronExpr || '0 * * * *').split(/\s+/);
    document.getElementById('tw-cron-min').value  = parts[0] || '0';
    document.getElementById('tw-cron-hour').value = parts[1] || '*';
    document.getElementById('tw-cron-dom').value  = parts[2] || '*';
    document.getElementById('tw-cron-mon').value  = parts[3] || '*';
    document.getElementById('tw-cron-dow').value  = parts[4] || '*';
  }

  function readTwCronFromPicker() {
    return [
      document.getElementById('tw-cron-min').value.trim()  || '0',
      document.getElementById('tw-cron-hour').value.trim() || '*',
      document.getElementById('tw-cron-dom').value.trim()  || '*',
      document.getElementById('tw-cron-mon').value.trim()  || '*',
      document.getElementById('tw-cron-dow').value.trim()  || '*',
    ].join(' ');
  }

  function updateSwpFieldsVisibility() {
    const enabled = document.getElementById('set-swp-enable').checked;
    // 'flex', not 'block' - #set-swp-fields is a flex row (WX Tail File
    // Path + Silence Threshold side by side); setting 'block' here was
    // silently clobbering that layout back to stacked on every page load.
    document.getElementById('set-swp-fields').style.display = enabled ? 'flex' : 'none';
    // The whole NG toggle/fields column is meaningless with WX tail
    // integration off, so hide it too rather than leaving an orphaned
    // "written by SkywarnPlus-NG" toggle with nothing for it to apply to.
    document.getElementById('set-swp-ng-block').style.display = enabled ? '' : 'none';
  }

  function updateSwpNgFieldsVisibility() {
    document.getElementById('set-swp-ng-fields').style.display =
      document.getElementById('set-swp-ng-enable').checked ? 'flex' : 'none';
  }

  function updateSnapshotFieldsVisibility() {
    document.getElementById('tw-snapshot-fields').style.display =
      document.getElementById('tw-snapshot-enable').checked ? 'flex' : 'none';
  }

  function updateTwProviderFields() {
    const provider = document.getElementById('tw-provider').value;
    document.getElementById('tw-tempest-fields').style.display = provider === 'tempest' ? 'block' : 'none';
    document.getElementById('tw-wunderground-fields').style.display = provider === 'wunderground' ? 'block' : 'none';
    document.getElementById('tw-location-field').style.display =
      (provider === 'tempest' || provider === 'wunderground') ? 'none' : 'block';
    document.getElementById('tw-swp-ng-banner').style.display = twSwpNgInstalled ? 'block' : 'none';
  }

  // Time/Weather cards only make sense once their own toggle is on -
  // matches the "What to Announce" card's toggles right above them.
  function updateTwSectionVisibility() {
    const enabled = document.getElementById('tw-enable').checked;
    const isTemplate = document.getElementById('tw-mode-template').checked;
    const announceTime = document.getElementById('tw-announce-time').checked;
    const announceWeather = document.getElementById('tw-weather-enable').checked;
    // In Template mode, whether there's "content" depends on whether any
    // message is configured - not on the Recordings-only Announce Time/
    // Weather toggles, which the daemon doesn't even read in that mode. The
    // messages table itself (always visible when Template mode is picked)
    // is where that gets surfaced, so just always allow Save/Test here.
    const hasContent = isTemplate ? true : (announceTime || announceWeather);

    // Master switch off: hide every option (nothing to configure), but
    // leave Save & Reload reachable so the disabled state can still be
    // saved, and hide Test since there'd be nothing to test.
    document.getElementById('tw-mode-row').style.display = enabled ? 'block' : 'none';
    document.getElementById('tw-options-block').style.display = (enabled && !isTemplate) ? 'block' : 'none';
    document.getElementById('tw-templates-block').style.display = (enabled && isTemplate) ? 'block' : 'none';
    // Time Format and Weather are shared settings - Template mode's
    // {time}/{conditions}/{temperature}/etc. tags use them too, so they
    // stay visible there regardless of the Recordings-only toggles.
    document.getElementById('tw-time-card').style.display = (enabled && (isTemplate || announceTime)) ? 'block' : 'none';
    document.getElementById('tw-weather-card').style.display = (enabled && (isTemplate || announceWeather)) ? 'block' : 'none';
    // The three Announce.../feels-like/humidity toggles only affect the
    // Recordings-mode audio builder - Template mode substitutes
    // {conditions}/{feels_like}/{humidity} whenever weather data is
    // available, regardless of these toggles, so they don't apply there.
    document.getElementById('tw-weather-announce-toggles').style.display = isTemplate ? 'none' : 'block';
    // Only meaningful in 12-hour format - 24-hour times don't use "o'clock".
    document.getElementById('tw-oclock-field').style.display =
      document.getElementById('tw-time-format').value === '24' ? 'none' : 'block';
    // Only meaningful in Template mode - Recordings mode has no "zero"
    // recording, so this setting has no effect there.
    document.getElementById('tw-minutezero-field').style.display = isTemplate ? 'block' : 'none';
    // Nothing to schedule if neither Time nor Weather is on - a smart
    // greeting alone was never a supported standalone announcement.
    document.getElementById('tw-schedule-card').style.display = (enabled && hasContent) ? 'block' : 'none';
    // A plain style.display here loses to the "#herald-ui button { display:
    // inline-block !important }" rule (added to defeat Bootstrap's flex
    // stretching on Allmon3 host pages) - toggle a class with matching
    // !important + higher specificity instead.
    document.getElementById('btn-test-timeweather').classList.toggle('btn-hidden', !(enabled && hasContent));
    document.getElementById('tw-nothing-warning').style.display = (enabled && !isTemplate && !hasContent) ? 'block' : 'none';
  }

  // ── Playback history ───────────────────────────────────────────────────────────────────
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
    const typeLabels = {
      rotation: 'Tail Message',
      wx: 'Tail Message (WX)',
      scheduled: 'Scheduled Announcement',
      timeweather: 'Time & Weather Announcements',
      'dtmf-timeweather': 'Time & Weather Announcements (DTMF)',
      'test-tail': 'Tail Message (Test)',
      'test-scheduled': 'Scheduled Announcement (Test)',
      'test-timeweather': 'Time & Weather Announcements (Test)',
      test: 'Manual Test',
    };
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
        const data = await api('reorder_rotation.php', { method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ name: btn.dataset.name, direction: btn.dataset.direction }) });
        if (data.success === false) {
          showMsg(document.getElementById('tail-msg'), data.message || 'Reorder failed', false);
        }
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
        else if (btn.dataset.type === 'tw-msg') startEditTwMsg(btn.dataset);
        else startEditSched(btn.dataset);
      };
    });
    document.querySelectorAll('.btn-remove-tw-msg').forEach(btn => {
      btn.onclick = async () => {
        if (!confirm('Remove this message?')) return;
        await api('remove_timeweather_message.php', { method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ id: btn.dataset.id }) });
        loadAll();
      };
    });
    document.querySelectorAll('.btn-test-tw-msg').forEach(btn => {
      btn.onclick = async () => {
        const msgEl = document.getElementById('timeweather-msg');
        btn.disabled = true;
        try {
          const data = await api('timeweather_test.php', { method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ message_id: btn.dataset.id, at: document.getElementById('tw-test-at').value.trim() }) });
          showMsg(msgEl, data.message || (data.success ? 'Playing now' : 'Failed'), data.success);
          if (data.success) loadHistory();
        } finally {
          btn.disabled = false;
        }
      };
    });
    document.querySelectorAll('.btn-toggle-tw-msg').forEach(btn => {
      btn.onclick = async () => {
        const data = await api('toggle_timeweather_message.php', { method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ id: btn.dataset.id }) });
        if (data.success === false) {
          alert(data.message || 'Toggle failed');
          return;
        }
        loadAll();
      };
    });
    document.querySelectorAll('.btn-toggle-sched').forEach(btn => {
      btn.onclick = async () => {
        const data = await api('toggle_scheduled.php', { method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ name: btn.dataset.name }) });
        if (data.success === false) {
          alert(data.message || 'Toggle failed');
          return;
        }
        loadAll();
      };
    });
    document.querySelectorAll('.btn-toggle-rot').forEach(btn => {
      btn.onclick = async () => {
        const data = await api('toggle_rotation.php', { method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ name: btn.dataset.name }) });
        if (data.success === false) {
          alert(data.message || 'Toggle failed');
          return;
        }
        loadAll();
      };
    });
  }

  // ── Edit tail message ───────────────────────────────────────────────────────────────────
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
    setSpeedSlider('tail-speed', 'tail-speed-display', hasText ? d.speed : 1.0);
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
    setSpeedSlider('tail-speed', 'tail-speed-display', 1.0);
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

  // ── Edit scheduled announcement ─────────────────────────────────────────────────────────
  let editingSchedName = null;

  function applyCronToPicker(cronExpr) {
    const parts = String(cronExpr || '* * * * *').split(/\s+/);
    document.getElementById('sched-cron-min').value  = parts[0] || '*';
    document.getElementById('sched-cron-hour').value = parts[1] || '*';
    document.getElementById('sched-cron-dom').value  = parts[2] || '*';
    document.getElementById('sched-cron-mon').value  = parts[3] || '*';
    document.getElementById('sched-cron-dow').value  = parts[4] || '*';
  }

  function readCronFromPicker() {
    return [
      document.getElementById('sched-cron-min').value.trim()  || '*',
      document.getElementById('sched-cron-hour').value.trim() || '*',
      document.getElementById('sched-cron-dom').value.trim()  || '*',
      document.getElementById('sched-cron-mon').value.trim()  || '*',
      document.getElementById('sched-cron-dow').value.trim()  || '*',
    ].join(' ');
  }

  function startEditSched(d) {
    editingSchedName = d.name;
    document.getElementById('sched-name').value = d.name;
    applyCronToPicker(d.cron || '* * * * *');
    document.getElementById('sched-playmode').value = d.playmode || 'local';
    document.getElementById('sched-node').value = d.node || '';

    const hasText = !!d.text;
    document.querySelector('input[name="sched-source"][value="' + (hasText ? 'tts' : 'file') + '"]').checked = true;
    document.getElementById('sched-tts-fields').style.display = hasText ? '' : 'none';
    document.getElementById('sched-file-fields').style.display = hasText ? 'none' : '';
    document.getElementById('sched-text').value = hasText ? d.text : '';
    document.getElementById('sched-voice').value = hasText ? (d.voice || '') : '';
    setSpeedSlider('sched-speed', 'sched-speed-display', hasText ? d.speed : 1.0);
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
    applyCronToPicker('* * * * *');
    document.getElementById('sched-text').value = '';
    setSpeedSlider('sched-speed', 'sched-speed-display', 1.0);
    document.getElementById('sched-file').value = '';
    document.getElementById('sched-file-keep-note').style.display = 'none';
    document.getElementById('sched-playmode').value = 'local';
    document.getElementById('sched-node').value = '';
    document.getElementById('sched-form-heading').textContent = 'Add a Scheduled Announcement';
    document.getElementById('btn-add-sched').textContent = 'Add Scheduled Announcement';
    document.getElementById('sched-edit-cancel').style.display = 'none';
    document.getElementById('sched-msg').textContent = '';
  }
  document.getElementById('sched-edit-cancel').addEventListener('click', cancelEditSched);

  // ── Edit Time & Weather template message ────────────────────────────────────────────────────
  let editingTwMsgId = null;

  function startEditTwMsg(d) {
    editingTwMsgId = d.id;
    document.getElementById('tw-msg-text').value = d.text || '';
    document.getElementById('tw-msg-voice').value = d.voice || '';
    setSpeedSlider('tw-msg-speed', 'tw-msg-speed-display', d.speed);
    document.getElementById('tw-msg-form-heading').textContent = 'Edit Message';
    document.getElementById('btn-add-tw-msg').textContent = 'Save Changes';
    document.getElementById('tw-msg-edit-cancel').style.display = '';
    document.getElementById('tw-msg-msg').textContent = '';
    document.getElementById('tw-msg-text').scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function cancelEditTwMsg() {
    editingTwMsgId = null;
    document.getElementById('tw-msg-text').value = '';
    setSpeedSlider('tw-msg-speed', 'tw-msg-speed-display', 1.0);
    document.getElementById('tw-msg-form-heading').textContent = 'Add a Message';
    document.getElementById('btn-add-tw-msg').textContent = 'Add Message';
    document.getElementById('tw-msg-edit-cancel').style.display = 'none';
    document.getElementById('tw-msg-msg').textContent = '';
  }
  document.getElementById('tw-msg-edit-cancel').addEventListener('click', cancelEditTwMsg);

  document.getElementById('btn-add-tw-msg').addEventListener('click', async () => {
    const msgEl = document.getElementById('tw-msg-msg');
    const text = document.getElementById('tw-msg-text').value.trim();
    const voice = document.getElementById('tw-msg-voice').value;
    const speed = document.getElementById('tw-msg-speed').value;
    if (!text) { showMsg(msgEl, 'Text is required', false); return; }

    // Include the currently-selected mode so it isn't lost on the loadAll()
    // reload below if the user picked "Custom Templates" but hasn't yet
    // clicked "Save Changes" - otherwise the reload reads Mode back from
    // the server (still "recordings") and the radio silently reverts.
    const mode = document.querySelector('input[name="tw-mode"]:checked').value;

    const data = editingTwMsgId
      ? await api('edit_timeweather_message.php', { method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ id: editingTwMsgId, text, voice, speed, mode }) })
      : await api('add_timeweather_message.php', { method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ text, voice, speed, mode }) });

    showMsg(msgEl, data.message || (data.success ? 'Saved' : 'Failed'), data.success);
    if (data.success) {
      cancelEditTwMsg();
      loadAll();
    }
  });

  // ── Enable/disable + reload ───────────────────────────────────────────────────────────────────
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
    // Reflect the result in the header badge immediately - same field shape
    // as list.php's update_check, so no waiting on the next 10 s poll.
    renderUpdateBadge(data);
    if (data.update_available) {
      showMsg(msgEl, 'Update available: v' + data.latest_version + ' (currently running v' + data.current_version + '). See the README for update instructions.', false);
    } else if (data.ahead_of_main) {
      showMsg(msgEl, 'Running v' + data.current_version + ', ahead of the latest release on main (v' + data.latest_version + ') - expected if installed from the develop branch for testing.', true);
    } else {
      showMsg(msgEl, 'Up to date (v' + data.current_version + ').', true);
    }
  });

  // ── Backup / restore ─────────────────────────────────────────────────────────────────────
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

  // ── Settings ──────────────────────────────────────────────────────────────────────────────
  // Shared by both Save & Reload buttons - Node/Debug live on the Global
  // Settings tab, Min Interval/RF-Network/SkywarnPlus live on the Tail
  // Messages tab (moved there since they're tail-message-specific), but
  // it's all one settings.php call either way - whichever button you click
  // saves the full current state of every field, regardless of which tab
  // it's currently showing.
  async function saveSettings(msgElId) {
    const msgEl = document.getElementById(msgElId);
    const data = await api('settings.php', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        node: document.getElementById('set-node').value.trim(),
        min_interval: document.getElementById('set-min-interval').value,
        debug: document.getElementById('set-debug').checked,
        network_keyup_trigger: document.getElementById('set-network-keyup-trigger').checked,
        swp_enable: document.getElementById('set-swp-enable').checked,
        swp_wxfile: document.getElementById('set-swp-wxfile').value.trim(),
        swp_threshold: document.getElementById('set-swp-threshold').value,
        swp_ng_enable: document.getElementById('set-swp-ng-enable').checked,
        swp_ng_apibase: document.getElementById('set-swp-ng-apibase').value.trim(),
        swp_ng_pollinterval: document.getElementById('set-swp-ng-pollinterval').value,
      }),
    });
    showMsg(msgEl, data.message || (data.success ? 'Settings saved and reloaded' : 'Failed'), data.success);
    if (data.success) loadAll();
  }
  document.getElementById('btn-save-settings').addEventListener('click', () => saveSettings('settings-msg'));
  document.getElementById('btn-save-tail-settings').addEventListener('click', () => saveSettings('tail-settings-msg'));
  document.getElementById('set-swp-enable').addEventListener('change', updateSwpFieldsVisibility);
  document.getElementById('set-swp-ng-enable').addEventListener('change', updateSwpNgFieldsVisibility);

  // ── Time & Weather Announcements ─────────────────────────────────────────────────────────────
  document.getElementById('tw-cron-hourly').addEventListener('click', () => {
    applyTwCronToPicker('0 * * * *');
  });

  document.getElementById('tw-provider').addEventListener('change', updateTwProviderFields);
  document.getElementById('tw-enable').addEventListener('change', updateTwSectionVisibility);
  document.getElementById('tw-snapshot-enable').addEventListener('change', updateSnapshotFieldsVisibility);
  document.getElementById('tw-announce-time').addEventListener('change', updateTwSectionVisibility);
  document.getElementById('tw-time-format').addEventListener('change', updateTwSectionVisibility);
  document.getElementById('tw-weather-enable').addEventListener('change', updateTwSectionVisibility);
  document.querySelectorAll('input[name="tw-mode"]').forEach(r => r.addEventListener('change', updateTwSectionVisibility));

  // ── Show/hide toggle for secret fields (Tempest token, Wunderground key) ──
  const EYE_SVG = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z"/><circle cx="12" cy="12" r="3"/></svg>';
  const EYE_OFF_SVG = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-11-8-11-8a21.8 21.8 0 0 1 5.06-6.06M9.9 4.24A10.94 10.94 0 0 1 12 4c7 0 11 8 11 8a21.8 21.8 0 0 1-3.22 4.56M14.12 14.12a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
  document.querySelectorAll('#herald-ui .btn-eye').forEach(btn => {
    btn.innerHTML = EYE_SVG;
    btn.addEventListener('click', () => {
      const input = document.getElementById(btn.dataset.target);
      if (!input) return;
      const reveal = input.type === 'password';
      input.type = reveal ? 'text' : 'password';
      btn.innerHTML = reveal ? EYE_OFF_SVG : EYE_SVG;
      btn.setAttribute('aria-label', reveal ? 'Hide' : 'Show');
    });
  });

  document.getElementById('btn-save-timeweather').addEventListener('click', async () => {
    const msgEl = document.getElementById('timeweather-msg');
    const data = await api('timeweather.php', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        enable: document.getElementById('tw-enable').checked,
        mode: document.querySelector('input[name="tw-mode"]:checked').value,
        announce_time: document.getElementById('tw-announce-time').checked,
        time_format: document.getElementById('tw-time-format').value,
        use_oclock: document.getElementById('tw-use-oclock').value === 'true',
        minute_zero_word: document.getElementById('tw-minute-zero-word').value,
        smart_greeting: document.getElementById('tw-smart-greeting').checked,
        cron: readTwCronFromPicker(),
        weather_enable: document.getElementById('tw-weather-enable').checked,
        provider: document.getElementById('tw-provider').value,
        location: document.getElementById('tw-location').value.trim(),
        temp_unit: document.getElementById('tw-temp-unit').value,
        announce_condition: document.getElementById('tw-announce-condition').checked,
        announce_feels_like: document.getElementById('tw-announce-feels-like').checked,
        announce_humidity: document.getElementById('tw-announce-humidity').checked,
        cache_max_age: document.getElementById('tw-cache-max-age').value,
        tempest_token: document.getElementById('tw-tempest-token').value.trim(),
        tempest_station: document.getElementById('tw-tempest-station').value.trim(),
        wunderground_api_key: document.getElementById('tw-wunderground-apikey').value.trim(),
        wunderground_station: document.getElementById('tw-wunderground-station').value.trim(),
        weather_snapshot_enable: document.getElementById('tw-snapshot-enable').checked,
        weather_snapshot_path: document.getElementById('tw-snapshot-path').value.trim(),
        weather_snapshot_label: document.getElementById('tw-snapshot-label').value.trim(),
        callsign: document.getElementById('tw-callsign').value.trim(),
        lookahead_seconds: document.getElementById('tw-lookahead-seconds').value,
      }),
    });
    showMsg(msgEl, data.message || (data.success ? 'Settings saved and reloaded' : 'Failed'), data.success);
    if (data.success) loadAll();
  });

  document.getElementById('btn-test-timeweather').addEventListener('click', async () => {
    const msgEl = document.getElementById('timeweather-msg');
    const data = await api('timeweather_test.php', { method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ at: document.getElementById('tw-test-at').value.trim() }) });
    showMsg(msgEl, data.message || (data.success ? 'Playing now' : 'Failed'), data.success);
    if (data.success) loadHistory();
  });

  // ── Node ID ───────────────────────────────────────────────────────────────────────────────
  document.getElementById('btn-test-nodeid').addEventListener('click', async () => {
    const msgEl = document.getElementById('nodeid-msg');
    const text = document.getElementById('nodeid-text').value.trim();
    const voice = document.getElementById('nodeid-voice').value;
    if (!text) { showMsg(msgEl, 'ID text is required', false); return; }
    const data = await api('node_id_test.php', { method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ text, voice }) });
    showMsg(msgEl, data.message || (data.success ? 'Playing test ID now' : 'Failed'), data.success);
  });

  document.getElementById('btn-save-nodeid').addEventListener('click', async () => {
    const msgEl = document.getElementById('nodeid-msg');
    const text = document.getElementById('nodeid-text').value.trim();
    const voice = document.getElementById('nodeid-voice').value;
    if (!text) { showMsg(msgEl, 'ID text is required', false); return; }
    if (!confirm('This overwrites the real Node ID file app_rpt reads. Continue?')) return;
    const data = await api('node_id.php', { method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ text, voice }) });
    showMsg(msgEl, data.message || (data.success ? 'Node ID generated and saved - live immediately, no reload needed' : 'Failed'), data.success);
    if (data.success) loadAll();
  });

  // ── Add / edit tail message ────────────────────────────────────────────────────────────────
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
      form.append('speed', document.getElementById('tail-speed').value);
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

  // ── Add / edit scheduled announcement ──────────────────────────────────────────────────
  document.getElementById('btn-add-sched').addEventListener('click', async () => {
    const msgEl = document.getElementById('sched-msg');
    const name = document.getElementById('sched-name').value.trim();
    const cron = readCronFromPicker();
    const playMode = document.getElementById('sched-playmode').value;
    const isTts = document.querySelector('input[name="sched-source"]:checked').value === 'tts';

    const form = new FormData();
    form.append('name', name);
    form.append('cron', cron);
    form.append('play_mode', playMode);
    form.append('node', document.getElementById('sched-node').value.trim());
    if (isTts) {
      form.append('mode', 'tts');
      form.append('text', document.getElementById('sched-text').value);
      form.append('voice', document.getElementById('sched-voice').value);
      form.append('speed', document.getElementById('sched-speed').value);
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

  // ── Clear history ──────────────────────────────────────────────────────────────────────────
  document.getElementById('btn-clear-history').addEventListener('click', async () => {
    if (!confirm('Clear all playback history?')) return;
    const msgEl = document.getElementById('history-msg');
    const data = await api('clear_history.php', { method: 'POST' });
    showMsg(msgEl, data.message || (data.success !== false ? 'History cleared' : 'Failed'), data.success !== false);
    if (data.success !== false) loadHistory();
  });

  document.getElementById('voices-region').addEventListener('change', populateVoiceCatalogSelect);
  document.getElementById('voices-select').addEventListener('change', updateVoiceButtons);
  document.getElementById('btn-refresh-voices').addEventListener('click', () => loadVoiceCatalog());
  document.getElementById('btn-install-voice').addEventListener('click', async () => {
    const voiceId = document.getElementById('voices-select').value;
    if (!voiceId) return;
    const msgEl = document.getElementById('voices-msg');
    const btn = document.getElementById('btn-install-voice');
    btn.disabled = true;
    showMsg(msgEl, 'Installing ' + voiceId + ' ...', true);
    const data = await api('install_voice.php', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ voice_id: voiceId }),
    });
    btn.disabled = false;
    showMsg(msgEl, data.message || (data.success ? 'Installed' : 'Failed'), data.success !== false);
    if (data.success !== false) {
      await loadVoiceCatalog();
      await loadVoices();
    }
  });
  document.getElementById('btn-remove-voice').addEventListener('click', async () => {
    const voiceId = document.getElementById('voices-select').value;
    if (!voiceId) return;
    if (!confirm('Remove voice ' + voiceLabel(voiceId) + '? Already-generated announcements keep playing fine, but editing one that still uses this voice (without picking a different one) will fail until it\'s reinstalled.')) return;
    const msgEl = document.getElementById('voices-msg');
    const btn = document.getElementById('btn-remove-voice');
    btn.disabled = true;
    showMsg(msgEl, 'Removing ' + voiceId + ' ...', true);
    const data = await api('remove_voice.php', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ voice_id: voiceId }),
    });
    btn.disabled = false;
    showMsg(msgEl, data.message || (data.success ? 'Removed' : 'Failed'), data.success !== false);
    if (data.success !== false) {
      await loadVoiceCatalog();
      await loadVoices();
    }
  });

  // Catalog first so voiceLabel() has friendly names ready before anything
  // that renders a voice dropdown/label (loadVoices, loadAll) runs.
  loadVoiceCatalog().then(() => {
    loadVoices();
    loadAll();
  });
  _cdPoller = setInterval(_pollCountdown, 10000);
})();
