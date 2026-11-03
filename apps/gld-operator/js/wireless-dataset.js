import { bridgeFetch } from './bridge-client.js';
import { state as legacyState, CHART_COLORS } from './state.js';
import { applyWirelessEvent, mergeWirelessSnapshot, WIRELESS_SENSOR_NAMES } from './wireless-dataset-model.js';

const $ = (id) => document.getElementById(id);
let snapshot = { connected: false, ready: false, state: 'disconnected', history: [], count: 0, gap_count: 0 };
let busy = false;
let message = '';
let syncMessage = '';
let syncPending = false;
let initialized = false;
let viewRevision = 0;
let mode = 'direct';
let discoveredModes = false;
let syncSequence = 0;
const modeSnapshots = {};
const colors = CHART_COLORS;

function replayAvailable() {
  return !legacyState.bridgeFeatures || legacyState.bridgeFeatures.wirelessReplay === true;
}

function apiPrefix(selected = mode) {
  return selected === 'replay' ? '/api/wireless-replay' : '/api/wireless-dataset';
}

function inUse(value = snapshot) {
  return Boolean(value.connected || value.recovery_active || value.cleanup_pending ||
    ['connecting', 'starting', 'running', 'capturing', 'recording', 'recovering',
      'reconnecting', 'resuming', 'replaying', 'stopping', 'stop_pending'].includes(value.state));
}

function isRecording() {
  return Boolean(snapshot.recovery_active || snapshot.cleanup_pending || ['starting', 'running', 'capturing', 'recording',
    'recovering', 'reconnecting', 'resuming', 'replaying', 'stopping', 'stop_pending'].includes(String(snapshot.state).toLowerCase()));
}

function selectMode(selected) {
  modeSnapshots[mode] = snapshot;
  mode = selected;
  snapshot = modeSnapshots[mode] || { connected: false, ready: false, state: 'disconnected', history: [], count: 0, gap_count: 0 };
  if ($('wirelessMode')) $('wirelessMode').value = mode;
  viewRevision += 1;
  syncSequence += 1;
  syncPending = false;
  message = syncMessage = '';
}

function render() {
  const active = isRecording();
  const replay = mode === 'replay';
  const cleanup = snapshot.cleanup_pending === true;
  const cleanupPaused = cleanup && snapshot.cleanup_paused === true;
  if ($('wirelessReplayOption')) $('wirelessReplayOption').disabled = !replayAvailable();
  if ($('wirelessMode')) $('wirelessMode').disabled = busy || inUse();
  $('wirelessConnectBtn').disabled = busy || snapshot.connected || active && !cleanupPaused;
  $('wirelessConnectBtn').textContent = cleanupPaused ? 'Selesaikan sesi' : 'Connect GLD';
  $('wirelessDisconnectBtn').disabled = busy || !(snapshot.connected || replay && active || cleanup && !cleanupPaused);
  $('wirelessDisconnectBtn').textContent = cleanup && !cleanupPaused ? 'Batal menunggu' : 'Disconnect';
  $('wirelessStartBtn').disabled = busy || !snapshot.connected || !snapshot.ready || active;
  $('wirelessStopBtn').disabled = busy || cleanup || !active || (replay
    ? !snapshot.session_id || snapshot.stop_requested
    : !snapshot.connected);
  $('wirelessExportBtn').disabled = busy || !snapshot.filename || !snapshot.count;
  $('wirelessPassword').disabled = busy || inUse() && !cleanupPaused;
  $('wirelessLabel').disabled = busy || active;
  const completion = snapshot.complete ? ' · sesi lengkap' : snapshot.filename && !active ? ' · sesi tidak lengkap' : '';
  $('wirelessState').textContent = `${snapshot.device_id || 'GLD'} · ${snapshot.state || 'disconnected'} · ${snapshot.count || 0} sampel tersimpan · ${snapshot.gap_count || 0} sampel hilang${completion}`;
  const status = $('wirelessMessage');
  status.textContent = message || syncMessage || snapshot.error || snapshot.reason || (snapshot.connected
    ? 'Koneksi wireless aktif. Start memulai sesi dan file CSV baru.'
    : 'Sambungkan Wi-Fi laptop ke GLD-DATASET-…, lalu masukkan password hotspot.');
  status.dataset.wirelessError = Boolean(message || syncMessage || snapshot.error) ? 'true' : 'false';
  if ($('wirelessRecovery')) {
    $('wirelessRecovery').textContent = cleanup
      ? cleanupPaused
        ? 'Rekaman sudah berhenti. Sambungkan kembali ke hotspot, isi password, lalu klik Selesaikan sesi sebelum mulai rekaman baru. CSV tetap sama.'
        : 'Rekaman sudah berhenti dan CSV tidak ditambah. Hub sedang menyelesaikan sesi di GLD. Sambungkan kembali ke hotspot agar sesi berikutnya bisa dimulai.'
      : !replay ? '' : snapshot.stop_requested && active
      ? 'Stop menunggu konfirmasi GLD. Backend akan memulihkan koneksi dan menyelesaikan CSV yang sama.'
      : snapshot.state === 'replaying'
          ? `Memulihkan data ke CSV yang sama. Data yang masih tertahan di GLD, terakhir diketahui: ${snapshot.buffered_samples ?? '—'} sampel.`
        : snapshot.recovery_active || snapshot.state === 'recovering'
          ? `Menunggu koneksi ke hotspot GLD; sampel ditahan di GLD selama tetap menyala. Percobaan koneksi: ${snapshot.reconnect_attempt || 0}.`
          : `Data yang masih tertahan di GLD, terakhir diketahui: ${snapshot.buffered_samples ?? 0} sampel · batas terputus 5 menit.`;
  }
  if ($('wirelessPolicy')) $('wirelessPolicy').textContent = replay
    ? 'Saat Wi-Fi terputus, GLD tetap merekam hingga 5 menit. Setelah tersambung, data otomatis masuk ke CSV yang sama. Biarkan GLD menyala. Jika batas terlewati, rekaman berhenti dan sesi ditandai tidak lengkap.'
    : 'Rekaman berhenti jika Wi-Fi terputus. Data selama terputus tidak dapat dipulihkan.';
  $('wirelessFile').textContent = snapshot.path ? `CSV: ${snapshot.path}` : 'CSV akan dibuat oleh backend saat Start diterima GLD.';
  const last = snapshot.history.at(-1);
  $('wirelessTiming').textContent = last
    ? `Target 500 ms · scan ${Math.max(0, Number(last.scan_end_ms ?? last.timestamp_ms) - last.timestamp_ms)} ms · overrun ${last.overrun_count || 0}`
    : 'Target: satu pembacaan lengkap delapan sensor setiap 500 ms.';
  const body = $('wirelessRows');
  body.replaceChildren();
  for (const row of snapshot.history.slice(-10).reverse()) {
    const tr = document.createElement('tr');
    for (const value of [row.seq, `${(row.timestamp_ms / 1000).toFixed(3)} s`, ...row.sensor_voltage.map((v) => v.toFixed(6))]) {
      const td = document.createElement('td');
      td.textContent = String(value);
      tr.append(td);
    }
    body.append(tr);
  }
  if (!body.children.length) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 10;
    td.textContent = 'Belum ada sampel wireless.';
    tr.append(td);
    body.append(tr);
  }
  drawWirelessChart();
}

function drawWirelessChart() {
  const canvas = $('wirelessChart');
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (!width || !height) return;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const text = getComputedStyle(canvas).color || '#888';
  ctx.font = '12px sans-serif';
  ctx.fillStyle = text;
  const right = width - 16, top = 18, left = 65, bottom = height - 38;
  const end = snapshot.history.at(-1)?.timestamp_ms || 0;
  const start = Math.max(0, end - 60000);
  const points = snapshot.history.filter((r) => r.timestamp_ms >= start);
  const values = points.flatMap((r) => r.sensor_voltage);
  let min = values.length ? Math.min(...values) : 0;
  let max = values.length ? Math.max(...values) : 1;
  const pad = Math.max((max - min) * .08, .00001);
  min -= pad; max += pad;
  ctx.strokeStyle = text;
  for (let i = 0; i <= 4; i += 1) {
    const y = top + (bottom - top) * i / 4;
    ctx.globalAlpha = .15;
    ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke();
    ctx.globalAlpha = 1;
    ctx.fillText((max - (max - min) * i / 4).toFixed(5), 3, y + 4);
  }
  ctx.fillText('V', 5, 12);
  ctx.fillText('60 detik terakhir · waktu pengukuran GLD', left, height - 8);
  if (!points.length) { ctx.fillText('Menunggu sampel wireless…', left + 12, top + 25); return; }
  const range = Math.max(60000, end - start);
  for (let channel = 0; channel < 8; channel += 1) {
    ctx.strokeStyle = colors[channel];
    ctx.fillStyle = colors[channel];
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    let previous;
    for (const row of points) {
      const x = left + (row.timestamp_ms - start) / range * (right - left);
      const y = bottom - (row.sensor_voltage[channel] - min) / (max - min) * (bottom - top);
      if (!previous || row.seq !== previous.seq + 1) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
      if (points.length === 1) ctx.fillRect(x - 2, y - 2, 4, 4);
      previous = row;
    }
    ctx.stroke();
  }
}

async function sync() {
  if (syncPending || !legacyState.bridgeAvailable) return;
  syncPending = true;
  const requestSequence = ++syncSequence;
  const requestedRevision = viewRevision;
  const requestedMode = mode;
  try {
    if (!discoveredModes && replayAvailable()) {
      const results = await Promise.allSettled([
        bridgeFetch('/api/wireless-dataset/state'), bridgeFetch('/api/wireless-replay/state'),
      ]);
      if (requestedRevision !== viewRevision || requestedMode !== mode) return;
      discoveredModes = true;
      for (const [index, result] of results.entries()) {
        if (result.status === 'fulfilled') {
          const target = index ? 'replay' : 'direct';
          modeSnapshots[target] = mergeWirelessSnapshot(modeSnapshots[target] || {}, result.value);
        }
      }
      const other = mode === 'direct' ? 'replay' : 'direct';
      if (inUse(modeSnapshots[other] || {}) && !inUse(modeSnapshots[mode] || {})) {
        selectMode(other);
      }
      const selectedResult = results[mode === 'replay' ? 1 : 0];
      if (selectedResult.status === 'rejected') throw selectedResult.reason;
      if (!modeSnapshots[mode]) throw new Error('Status recorder belum tersedia');
      snapshot = modeSnapshots[mode];
    } else {
      const data = await bridgeFetch(`${apiPrefix(requestedMode)}/state`);
      if (requestedRevision !== viewRevision || requestedMode !== mode) return;
      snapshot = mergeWirelessSnapshot(snapshot, data);
      modeSnapshots[mode] = snapshot;
    }
    syncMessage = '';
    render();
  } catch (error) {
    if (requestedRevision === viewRevision) {
      syncMessage = `Status wireless belum tersedia: ${error.message}`;
      render();
    }
  } finally { if (requestSequence === syncSequence) syncPending = false; }
}

async function action(command, payload = {}) {
  if (busy) return;
  if (!legacyState.bridgeAvailable) { message = 'Jalankan backend Operator Hub terlebih dahulu.'; render(); return; }
  if (command === 'connect' && (legacyState.connected || legacyState.mock)) {
    message = 'Putuskan koneksi COM dan matikan Mock sebelum menyambungkan Wireless.';
    render(); return;
  }
  busy = true; message = ''; render();
  viewRevision += 1;
  try {
    const data = await bridgeFetch(`${apiPrefix()}/${command}`, {
      method: 'POST', body: JSON.stringify(payload), timeoutMs: 20000,
    });
    snapshot = mergeWirelessSnapshot(snapshot, data);
    modeSnapshots[mode] = snapshot;
    if (command === 'connect') $('wirelessPassword').value = '';
  } catch (error) { message = error.message; }
  finally { busy = false; render(); await sync(); }
}

async function exportFile() {
  busy = true; render();
  try {
    const data = await bridgeFetch(`${apiPrefix()}/export`, { method: 'POST', body: '{}' });
    const url = URL.createObjectURL(new Blob([data.csv], { type: 'text/csv;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url; a.download = data.filename; a.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { message = error.message; }
  finally { busy = false; render(); }
}

export function initWirelessDataset() {
  if (initialized || !$('wirelessDataset')) return;
  initialized = true;
  $('wirelessMode')?.addEventListener('change', async () => {
    const selected = $('wirelessMode').value;
    if (busy || inUse() || !['direct', 'replay'].includes(selected) || selected === 'replay' && !replayAvailable()) {
      $('wirelessMode').value = mode;
      render(); return;
    }
    discoveredModes = true;
    selectMode(selected);
    render(); await sync();
  });
  $('wirelessConnectBtn').addEventListener('click', () => action('connect', { password: $('wirelessPassword').value }));
  $('wirelessDisconnectBtn').addEventListener('click', () => action('disconnect'));
  $('wirelessStartBtn').addEventListener('click', () => action('start', { label: $('wirelessLabel').value, interval_ms: 500 }));
  $('wirelessStopBtn').addEventListener('click', () => action('stop'));
  $('wirelessExportBtn').addEventListener('click', exportFile);
  for (let i = 0; i < 8; i += 1) {
    const span = document.createElement('span');
    const dot = document.createElement('i'); dot.style.background = colors[i];
    span.append(dot, document.createTextNode(WIRELESS_SENSOR_NAMES[i]));
    $('wirelessLegend').append(span);
  }
  function receiveModeEvent(target, event) {
    const previous = target === mode ? snapshot : (modeSnapshots[target] || {});
    modeSnapshots[target] = applyWirelessEvent(previous, event.detail);
    if (target !== mode) {
      if (!inUse() && inUse(modeSnapshots[target])) selectMode(target);
      else return;
    }
    viewRevision += 1;
    snapshot = modeSnapshots[target];
    syncMessage = '';
    render();
  }
  window.addEventListener('gld-wireless-dataset', (event) => receiveModeEvent('direct', event));
  window.addEventListener('gld-wireless-dataset-replay', (event) => receiveModeEvent('replay', event));
  window.addEventListener('gld-bridge-events-open', sync);
  window.addEventListener('resize', drawWirelessChart);
  new ResizeObserver(drawWirelessChart).observe($('wirelessChart'));
  // Snapshot recovery also repairs missed SSE events and browser reloads.
  window.setInterval(sync, 10000);
  render(); sync();
}
