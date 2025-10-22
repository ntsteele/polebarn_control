const channelWidgets = new Map();
let masterSliderEl;
let masterValueEl;
let fohListEl;
let masterLogEl;
let masterStatusEl;
let telemetrySocket;
let currentSnapshot = null;

function linearToDb(linear) {
  const value = Math.max(parseFloat(linear), 1e-6);
  return 20 * Math.log10(value);
}

function formatDb(db, digits = 1) {
  if (!isFinite(db)) return '--';
  return `${db.toFixed(digits)} dB`;
}

function setSelectOptions(select, options, selected) {
  const previous = select.value;
  select.innerHTML = '';
  options.forEach(opt => {
    const option = document.createElement('option');
    option.value = opt.id;
    option.textContent = opt.name || opt.id;
    select.appendChild(option);
  });
  if (selected && options.some(o => o.id === selected)) {
    select.value = selected;
  } else if (previous && options.some(o => o.id === previous)) {
    select.value = previous;
  }
}

function createChannelCard(channel) {
  const col = document.createElement('div');
  col.className = 'col';
  const card = document.createElement('div');
  card.className = 'card border-warning-subtle h-100';
  card.innerHTML = `
    <div class="card-header bg-dark text-warning small text-uppercase d-flex justify-content-between align-items-center">
      <span>${channel.label}</span>
      <span class="text-secondary">Ch ${channel.xr18_channel}</span>
    </div>
    <div class="card-body small d-flex flex-column gap-2">
      <div>
        <label class="text-secondary text-uppercase mb-1">Fader</label>
        <input type="range" min="0" max="1" step="0.01" class="form-range channel-fader" data-channel="${channel.id}">
        <div class="d-flex justify-content-between align-items-center mt-1">
          <span class="text-secondary" data-field="faderDb">${formatDb(channel.fader_db, 1)}</span>
          <button class="btn btn-outline-warning btn-sm" data-action="suggestion" style="display:none"></button>
        </div>
      </div>
      <div>
        <label class="text-secondary text-uppercase mb-1">Pan</label>
        <input type="range" min="-100" max="100" step="1" class="form-range channel-pan" data-channel="${channel.id}">
        <div class="text-secondary mt-1" data-field="panText"></div>
      </div>
      <div class="text-secondary" data-field="meter">RMS: --</div>
    </div>
  `;
  col.appendChild(card);

  const fader = card.querySelector('.channel-fader');
  const pan = card.querySelector('.channel-pan');
  const suggestionBtn = card.querySelector('[data-action="suggestion"]');

  fader.addEventListener('input', () => {
    fader.dataset.dragging = '1';
    card.querySelector('[data-field="faderDb"]').textContent = formatDb(linearToDb(fader.value), 1);
  });
  fader.addEventListener('change', () => {
    sendChannelUpdate(channel.id, { fader: parseFloat(fader.value) });
    setTimeout(() => { fader.dataset.dragging = '0'; }, 50);
  });

  pan.addEventListener('input', () => {
    pan.dataset.dragging = '1';
    const pct = parseFloat(pan.value);
    card.querySelector('[data-field="panText"]').textContent = formatPan(pct);
  });
  pan.addEventListener('change', () => {
    sendChannelUpdate(channel.id, { pan: percentToLinear(parseFloat(pan.value)) });
    setTimeout(() => { pan.dataset.dragging = '0'; }, 50);
  });

  suggestionBtn.addEventListener('click', () => {
    const delta = parseFloat(suggestionBtn.dataset.delta);
    if (!isFinite(delta) || delta === 0) return;
    sendChannelUpdate(channel.id, { adjust_db: delta });
  });

  channelWidgets.set(channel.id, {
    element: card,
    fader,
    pan,
    suggestionBtn,
    fields: {
      faderDb: card.querySelector('[data-field="faderDb"]'),
      panText: card.querySelector('[data-field="panText"]'),
      meter: card.querySelector('[data-field="meter"]')
    }
  });

  return col;
}

function ensureChannels(channels) {
  const lane = document.getElementById('faderLane');
  const existingIds = new Set(channelWidgets.keys());

  channels.forEach(ch => {
    let widget = channelWidgets.get(ch.id);
    if (!widget) {
      const card = createChannelCard(ch);
      lane.appendChild(card);
      widget = channelWidgets.get(ch.id);
    }
    updateChannelWidget(widget, ch);
    existingIds.delete(ch.id);
  });

  existingIds.forEach(id => {
    const widget = channelWidgets.get(id);
    if (widget) {
      widget.element.parentElement?.remove();
    }
    channelWidgets.delete(id);
  });
}

function updateChannelWidget(widget, channel) {
  if (!widget) return;
  if (widget.fader.dataset.dragging !== '1') {
    widget.fader.value = channel.fader_linear.toFixed(3);
    widget.fields.faderDb.textContent = formatDb(channel.fader_db, 1);
  }
  if (widget.pan.dataset.dragging !== '1') {
    widget.pan.value = channel.pan_percent.toFixed(0);
    widget.fields.panText.textContent = formatPan(channel.pan_percent);
  }
  widget.fields.meter.textContent = `RMS: ${channel.meter_db.toFixed(1)} dBFS`;

  const delta = channel.suggestion_db;
  if (Math.abs(delta) >= 0.1) {
    widget.suggestionBtn.style.display = '';
    widget.suggestionBtn.dataset.delta = delta;
    widget.suggestionBtn.textContent = `${delta > 0 ? '+' : ''}${delta.toFixed(1)} dB`;
  } else {
    widget.suggestionBtn.style.display = 'none';
    widget.suggestionBtn.dataset.delta = '0';
  }
}

function formatPan(percent) {
  const value = parseFloat(percent);
  if (Math.abs(value) < 1) return 'Center';
  return value < 0 ? `L${Math.abs(value).toFixed(0)}` : `R${Math.abs(value).toFixed(0)}`;
}

function percentToLinear(percent) {
  return Math.max(0, Math.min(1, 0.5 + percent / 200));
}

function updateMaster(master) {
  if (!masterSliderEl) return;
  if (masterSliderEl.dataset.dragging !== '1') {
    const clamped = Math.max(-18, Math.min(6, master.master_db));
    masterSliderEl.value = clamped;
    masterValueEl.textContent = formatDb(master.master_db, 1);
  }
  const parts = [];
  if (master.message) parts.push(master.message);
  if (typeof master.last_adjust_db === 'number' && Math.abs(master.last_adjust_db) > 0.01) {
    parts.push(`Coach nudged ${master.last_adjust_db.toFixed(2)} dB`);
  }
  masterStatusEl.textContent = parts.join(' · ');

  fohListEl.innerHTML = '';
  master.foh.forEach(member => {
    const item = document.createElement('li');
    item.className = 'list-group-item bg-dark text-secondary d-flex justify-content-between align-items-center';
    item.innerHTML = `<span>${member.label}</span><span>${formatDb(member.current_db, 1)}</span>`;
    fohListEl.appendChild(item);
  });

  masterLogEl.innerHTML = '';
  if (master.log && master.log.length) {
    master.log.slice(-6).reverse().forEach(entry => {
      const div = document.createElement('div');
      const ts = new Date(entry.timestamp * 1000).toLocaleTimeString();
      div.textContent = `${ts}: +${entry.excess_db.toFixed(1)} dB over safe (${entry.spl.toFixed(1)} dB)`;
      masterLogEl.appendChild(div);
    });
  }
}

function updateTelemetry(telemetry) {
  document.getElementById('bpmShort').textContent = telemetry.bpm_short.toFixed(1);
  document.getElementById('bpmLong').textContent = telemetry.bpm_long.toFixed(1);
  document.getElementById('bpmConfidence').textContent = telemetry.bpm_confidence.toFixed(2);
  document.getElementById('splFast').textContent = telemetry.spl_fast.toFixed(1);
  document.getElementById('splSlow').textContent = telemetry.spl_slow.toFixed(1);
  document.getElementById('splWeighting').textContent = telemetry.weighting;

  const warnings = [];
  if (typeof telemetry.target_max === 'number' && telemetry.spl_slow > telemetry.target_max) {
    warnings.push(`Crowd is ${(telemetry.spl_slow - telemetry.target_max).toFixed(1)} dB above safe window.`);
  }
  if (typeof telemetry.target_min === 'number' && telemetry.spl_slow < telemetry.target_min) {
    warnings.push(`Room is ${(telemetry.target_min - telemetry.spl_slow).toFixed(1)} dB under target.`);
  }
  document.getElementById('splWarnings').textContent = warnings.join(' ');
}

function applySnapshot(snapshot) {
  currentSnapshot = snapshot;
  ensureChannels(snapshot.channels || []);
  if (snapshot.master) updateMaster(snapshot.master);
  if (snapshot.telemetry) {
    updateTelemetry(Object.assign({ target_min: 0, target_max: 0 }, snapshot.telemetry));
  }

  const showSelect = document.getElementById('showSelect');
  const templateSelect = document.getElementById('templateSelect');
  const modeSelect = document.getElementById('modeSelect');
  const panPresetSelect = document.getElementById('panPresetSelect');

  if (snapshot.shows) setSelectOptions(showSelect, snapshot.shows, snapshot.show);
  if (snapshot.templates) setSelectOptions(templateSelect, snapshot.templates, snapshot.template);
  if (snapshot.modes) setSelectOptions(modeSelect, snapshot.modes, snapshot.mode);

  panPresetSelect.innerHTML = '';
  (snapshot.pan_presets || []).forEach(preset => {
    const option = document.createElement('option');
    option.value = preset.id;
    option.textContent = preset.name;
    panPresetSelect.appendChild(option);
  });
}

function sendChannelUpdate(channelId, payload) {
  const body = Object.assign({ channel: channelId }, payload);
  fetch('/api/asv/fader', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }).then(r => r.json()).then(applySnapshot).catch(err => console.error('channel update', err));
}

function bindSelectors() {
  const showSelect = document.getElementById('showSelect');
  const templateSelect = document.getElementById('templateSelect');
  const modeSelect = document.getElementById('modeSelect');
  const panPresetSelect = document.getElementById('panPresetSelect');
  const applyPanBtn = document.getElementById('applyPanPreset');

  showSelect.addEventListener('change', () => {
    postRoster({ show: showSelect.value });
  });
  templateSelect.addEventListener('change', () => {
    postRoster({ template: templateSelect.value });
  });
  modeSelect.addEventListener('change', () => {
    postRoster({ mode: modeSelect.value });
  });
  applyPanBtn.addEventListener('click', () => {
    const preset = panPresetSelect.value;
    if (!preset) return;
    fetch('/api/asv/pan_preset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preset })
    }).then(r => r.json()).then(applySnapshot).catch(err => console.error('pan preset', err));
  });
}

function postRoster(payload) {
  fetch('/api/asv/roster', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }).then(r => r.json()).then(applySnapshot).catch(err => console.error('roster', err));
}

function bindMaster() {
  masterSliderEl = document.getElementById('masterSlider');
  masterValueEl = document.getElementById('masterDb');
  fohListEl = document.getElementById('fohList');
  masterLogEl = document.getElementById('masterLog');
  masterStatusEl = document.getElementById('masterStatus');

  masterSliderEl.addEventListener('input', () => {
    masterSliderEl.dataset.dragging = '1';
    masterValueEl.textContent = formatDb(parseFloat(masterSliderEl.value), 1);
  });
  masterSliderEl.addEventListener('change', () => {
    fetch('/api/asv/master', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ master_db: parseFloat(masterSliderEl.value) })
    }).then(r => r.json()).then(resp => {
      if (resp.master) updateMaster(resp.master);
    }).catch(err => console.error('master', err));
    setTimeout(() => { masterSliderEl.dataset.dragging = '0'; }, 50);
  });
}

function connectSocket() {
  telemetrySocket = io('/ws/asv');
  telemetrySocket.on('telemetry', payload => {
    applySnapshot(payload);
  });
}

function init() {
  bindSelectors();
  bindMaster();
  fetch('/api/asv/roster').then(r => r.json()).then(applySnapshot).catch(err => console.error('init roster', err));
  connectSocket();
}

document.addEventListener('DOMContentLoaded', init);
