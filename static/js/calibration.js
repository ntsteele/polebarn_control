(function () {
  const logEl = document.getElementById('gain-trim-log');
  const metricsBody = document.querySelector('#gain-trim-metrics tbody');
  const routinesBody = document.querySelector('#calibration-routines tbody');
  const presetSelect = document.getElementById('eq-preset');
  const eqCurrent = document.getElementById('eq-current');
  const eqPreview = document.getElementById('eq-preview-data');
  const eqConfirm = document.getElementById('eq-confirm');
  const runSelect = document.getElementById('deep-venue-runs');
  const runSummary = document.getElementById('deep-venue-summary');
  const runAnalysis = document.getElementById('deep-venue-analysis');

  if (!logEl) {
    return;
  }

  function appendLog(line) {
    if (!line) return;
    const shouldAutoScroll = logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 10;
    logEl.textContent = `${logEl.textContent}\n${line}`.trim();
    if (shouldAutoScroll) {
      logEl.scrollTop = logEl.scrollHeight;
    }
  }

  function updateMetrics(metrics) {
    metricsBody.innerHTML = '';
    Object.entries(metrics || {}).forEach(([channel, payload]) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${channel}</td><td>${payload.peak_dbfs?.toFixed ? payload.peak_dbfs.toFixed(2) : payload.peak_dbfs}</td>`;
      metricsBody.appendChild(tr);
    });
  }

  async function refreshGainTrimStatus() {
    try {
      const res = await fetch('/api/cal/gain-trim/status');
      if (!res.ok) throw new Error('status failed');
      const data = await res.json();
      updateMetrics(data.metrics || {});
      if (Array.isArray(data.log_tail)) {
      logEl.textContent = data.log_tail.join("\n");
      logEl.scrollTop = logEl.scrollHeight;
    }
    } catch (err) {
      console.error(err);
    }
  }

  async function startGainTrim() {
    const target = parseFloat(document.getElementById('gain-trim-target').value || '-12');
    const safety = parseFloat(document.getElementById('gain-trim-safety').value || '-6');
    const channels = Array.from(document.getElementById('gain-trim-channels').selectedOptions).map(o => parseInt(o.value, 10));
    try {
      const res = await fetch('/api/cal/gain-trim/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_dbfs: target, safety_dbfs_cap: safety, channels })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.err || 'Unable to start');
      showToast('Gain trim started');
      logEl.textContent = '';
    } catch (err) {
      console.error(err);
      showToast(`⚠️ ${err.message}`);
    }
  }

  async function stopGainTrim() {
    try {
      await fetch('/api/cal/gain-trim/stop', { method: 'POST' });
      showToast('Gain trim stop requested');
    } catch (err) {
      console.error(err);
    }
  }

  async function saveGainTrimLog() {
    try {
      const res = await fetch('/api/cal/gain-trim/log');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'gain_trim.log';
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        URL.revokeObjectURL(url);
        a.remove();
      }, 100);
    } catch (err) {
      console.error(err);
    }
  }

  async function fetchCalibrations() {
    try {
      const res = await fetch('/api/calibrations/summary');
      if (!res.ok) throw new Error('Unable to load calibrations');
      const data = await res.json();
      routinesBody.innerHTML = '';
      (data.calibrations || []).forEach(item => {
        const tr = document.createElement('tr');
        const value = item.value || '—';
        const lastRun = item.last_run ? new Date(item.last_run).toLocaleString() : 'Never';
        tr.innerHTML = `
          <td>${item.label}</td>
          <td>${value}</td>
          <td>${lastRun}</td>
          <td class="text-end">
            <button class="btn btn-sm ${item.running ? 'btn-secondary' : 'btn-outline-primary'}" data-calibration-run="${item.id}" ${item.running ? 'disabled' : ''}>
              ${item.running ? 'Running…' : 'Rerun'}
            </button>
          </td>`;
        routinesBody.appendChild(tr);
      });
    } catch (err) {
      console.error(err);
    }
  }

  routinesBody.addEventListener('click', async (event) => {
    const btn = event.target.closest('button[data-calibration-run]');
    if (!btn) return;
    const calId = btn.getAttribute('data-calibration-run');
    btn.disabled = true;
    btn.textContent = 'Running…';
    try {
      const res = await fetch(`/api/calibrations/${calId}/run`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.err || 'Unable to start calibration');
      showToast(`${calId} started`);
    } catch (err) {
      console.error(err);
      showToast(`⚠️ ${err.message}`);
    } finally {
      setTimeout(fetchCalibrations, 2000);
    }
  });

  async function fetchEqCurrent() {
    try {
      const res = await fetch('/api/eq/current');
      if (!res.ok) throw new Error('Unable to fetch EQ');
      const data = await res.json();
      eqCurrent.textContent = JSON.stringify(data, null, 2);
    } catch (err) {
      console.error(err);
      showToast(`⚠️ ${err.message}`);
    }
  }

  async function previewEq() {
    try {
      const res = await fetch('/api/eq/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: presetSelect.value })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.err || 'Unable to preview');
      eqPreview.textContent = JSON.stringify(data.filters, null, 2);
      showToast('Preset preview ready');
    } catch (err) {
      console.error(err);
      showToast(`⚠️ ${err.message}`);
    }
  }

  async function applyEq(dryRun = false) {
    try {
      const filters = eqPreview.textContent ? JSON.parse(eqPreview.textContent || '{}') : {};
      const payload = { filters, confirmation: eqConfirm.value };
      const res = await fetch(`/api/eq/apply?dry_run=${dryRun ? '1' : '0'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.err || 'Apply failed');
      showToast(data.message || (dryRun ? 'Dry run succeeded' : 'EQ applied'));
      await fetchEqCurrent();
    } catch (err) {
      console.error(err);
      showToast(`⚠️ ${err.message}`);
    }
  }

  async function rollbackEq() {
    try {
      const res = await fetch('/api/eq/rollback', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.err || 'Rollback failed');
      showToast('EQ rollback restored');
      await fetchEqCurrent();
    } catch (err) {
      console.error(err);
      showToast(`⚠️ ${err.message}`);
    }
  }

  async function fetchAnalyses() {
    try {
      const res = await fetch('/api/deep-venue/analyses');
      if (!res.ok) throw new Error('Unable to load analyses');
      const data = await res.json();
      const currentValue = runSelect.value;
      runSelect.innerHTML = '<option value="">Select a saved run…</option>';
      (data.runs || []).forEach(run => {
        const option = document.createElement('option');
        option.value = run.id;
        const ts = run.timestamp ? new Date(run.timestamp).toLocaleString() : run.id;
        option.textContent = `${ts}`;
        option.dataset.summary = JSON.stringify(run.summary || {});
        runSelect.appendChild(option);
      });
      if (currentValue) {
        runSelect.value = currentValue;
      }
      if (runSelect.value) {
        await loadAnalysis(runSelect.value);
      }
    } catch (err) {
      console.error(err);
    }
  }

  async function loadAnalysis(runId) {
    if (!runId) {
      runSummary.textContent = '';
      runAnalysis.textContent = '';
      return;
    }
    try {
      const res = await fetch(`/api/deep-venue/analysis/${runId}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.err || 'Unable to load analysis');
      runAnalysis.textContent = JSON.stringify(data.analysis, null, 2);
      const option = runSelect.selectedOptions[0];
      if (option && option.dataset.summary) {
        const summary = JSON.parse(option.dataset.summary);
        runSummary.textContent = Object.entries(summary).map(([k, v]) => `${k}: ${v}`).join(', ');
      }
    } catch (err) {
      console.error(err);
      showToast(`⚠️ ${err.message}`);
    }
  }

  // socket wiring -------------------------------------------------------
  const calSocket = io('/ws/calibration');
  calSocket.on('calibration_log', payload => appendLog(payload.line));
  calSocket.on('calibration_metrics', payload => updateMetrics(payload.metrics));
  calSocket.on('calibration_finished', () => {
    fetchCalibrations();
    showToast('Calibration complete');
  });

  // button wiring -------------------------------------------------------
  document.getElementById('gain-trim-start').addEventListener('click', startGainTrim);
  document.getElementById('gain-trim-stop').addEventListener('click', stopGainTrim);
  document.getElementById('gain-trim-save').addEventListener('click', saveGainTrimLog);
  document.getElementById('eq-preview').addEventListener('click', previewEq);
  document.getElementById('eq-fetch').addEventListener('click', fetchEqCurrent);
  document.getElementById('eq-apply').addEventListener('click', () => applyEq(false));
  document.getElementById('eq-apply-dry').addEventListener('click', () => applyEq(true));
  document.getElementById('eq-rollback').addEventListener('click', rollbackEq);
  runSelect.addEventListener('change', () => loadAnalysis(runSelect.value));

  // initial load --------------------------------------------------------
  refreshGainTrimStatus();
  fetchCalibrations();
  fetchEqCurrent();
  fetchAnalyses();

  // refresh loops -------------------------------------------------------
  setInterval(fetchCalibrations, 15000);
  setInterval(refreshGainTrimStatus, 5000);
})();
