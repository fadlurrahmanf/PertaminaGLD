// QC tab: per-channel (0-7) MQ sensor quality-control tracking. A channel
// must pass nulling first (firmware-confirmed channelOk), then the operator
// records a manual Pass/Fail verdict. Verdicts persist on the GLD's own NVS
// (see GldQcProfile in firmware) so they survive app reconnects and cable
// unplug/replug - GET_QC_STATUS is always the source of truth, never a
// locally-remembered guess.

import { $, elements, state, SENSOR_NAMES, SENSOR_STATUS_NAMES } from "./state.js";
import { sendCommand, sendCommandAndWaitAck, togglePolling, channelIndexFromLog, tokenValue } from "./serial-protocol.js";
import { showAlert, showConfirm, withBusy, saveUiSession, setPanelOpen, downloadText, csvCell, stamp, onAppendLog } from "./ui.js";
import { drawOneChart, drawFullScaleSweepChart } from "./chart.js";
import { renderNullingChannels, DAC_CODE_MAX } from "./nulling.js";

// Single-channel nulling runs the same physical search algorithm as a full
// 8-channel nulling pass, just for one channel - it can legitimately take
// longer than the app's default serial-ack timeout, so it gets its own
// generous timeout instead of SERIAL_RESPONSE_TIMEOUT_MS.
const SINGLE_NULLING_TIMEOUT_MS = 30000;

// A full-scale sweep steps the DAC across every single code from 0 to 4095
// (see GldNullingService::runFullScaleSweep), each step doing a settle + 8x
// ADS average across all ~4096 codes - that easily runs longer than a
// single-channel null.
const FULL_SCALE_SWEEP_TIMEOUT_MS = 90000;

function emptyQcChannels() {
  return Array.from({ length: 8 }, (_, index) => ({
    channel: index, sensor: SENSOR_NAMES[index], nullingOk: false, tested: false, pass: false, timestamp: ""
  }));
}

// Called when the active fleet slot changes (a different GLD's port becomes
// the one shown in the tabs) so stale QC verdicts from the previous board
// don't linger on screen until the next GET_QC_STATUS reply arrives.
export function resetQcStatus() {
  state.qc.channels = emptyQcChannels();
  renderQc();
}

export function updateQcStatus(payload) {
  const incoming = Array.isArray(payload?.channels) ? payload.channels : [];
  state.qc.channels = emptyQcChannels().map((fallback, index) => {
    const match = incoming.find((item) => Number(item.channel) === index);
    if (!match) return fallback;
    return {
      channel: index,
      sensor: match.sensor || fallback.sensor,
      nullingOk: Boolean(match.nullingOk),
      tested: Boolean(match.tested),
      pass: Boolean(match.pass),
      timestamp: match.timestamp || ""
    };
  });
  renderQc();
  // Freshly-known nullingOk can flip a channel's card from "Waiting" to
  // "Done (saved)" in both the Nulling tab and QC's own grids without
  // waiting for a new NULLING_ log line - refresh them right away.
  renderNullingChannels();
  renderQcNullingViews();
}

function qcTone(channel) {
  if (!channel.tested) return "";
  return channel.pass ? "pass" : "fail";
}

function qcStageText(channel) {
  if (!channel.tested) return channel.nullingOk ? "Nulling OK - awaiting QC" : "Not tested";
  return channel.pass ? "QC Passed" : "QC Failed";
}

function buildQcChannelCard(channel) {
  const card = document.createElement("article");
  card.className = `channel-card ${qcTone(channel)}`.trim();

  const head = document.createElement("div");
  head.className = "channel-card-head";
  const title = document.createElement("strong");
  title.textContent = channel.sensor;
  const key = document.createElement("span");
  key.textContent = `CH${channel.channel + 1}`;
  head.append(title, key);

  const stage = document.createElement("span");
  stage.className = "channel-stage";
  stage.textContent = qcStageText(channel);

  const detail = document.createElement("small");
  detail.textContent = channel.nullingOk ? "Nulling: OK" : "Nulling: not confirmed";

  const extra = document.createElement("small");
  extra.textContent = channel.tested ? `Last QC: ${channel.timestamp || "unknown time"}` : "Never QC'd";

  card.append(head, stage, detail, extra);
  return card;
}

function renderQcAll() {
  const grid = $("qcAllGrid");
  if (!grid) return;
  grid.innerHTML = "";
  state.qc.channels.forEach((channel) => grid.append(buildQcChannelCard(channel)));

  const passCount = state.qc.channels.filter((c) => c.tested && c.pass).length;
  const failCount = state.qc.channels.filter((c) => c.tested && !c.pass).length;
  const untestedCount = state.qc.channels.filter((c) => !c.tested).length;
  const summary = $("qcAllSummary");
  if (summary) summary.textContent = `${passCount}/8 passed - ${failCount} failed - ${untestedCount} untested`;
}

function renderQcChannelPanel(index) {
  const channel = state.qc.channels[index];
  if (!channel) return;

  const nullingStatus = $(`qcNullingStatus-${index}`);
  if (nullingStatus) {
    nullingStatus.textContent = channel.nullingOk
      ? "Nulling: OK - sensor responded to the DAC."
      : "Nulling: not confirmed yet - run nulling first.";
    nullingStatus.className = `status-line${channel.nullingOk ? "" : " error"}`;
  }

  const passBtn = $(`qcPassBtn-${index}`);
  const failBtn = $(`qcFailBtn-${index}`);
  if (passBtn) passBtn.disabled = !channel.nullingOk;
  if (failBtn) failBtn.disabled = !channel.nullingOk;

  const history = $(`qcHistory-${index}`);
  if (history) {
    history.textContent = channel.tested
      ? `Last verdict: ${channel.pass ? "PASS" : "FAIL"} at ${channel.timestamp || "unknown time"}`
      : "No QC verdict recorded yet.";
  }
}

export function renderQc() {
  renderQcAll();
  for (let index = 0; index < 8; index += 1) renderQcChannelPanel(index);
}

export function switchQcTab(tabId) {
  state.qc.activeTab = tabId;
  document.querySelectorAll(".qc-subnav .qc-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.qctab === tabId);
  });
  document.querySelectorAll(".qc-subview").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.qctab === tabId);
  });
  drawQcCharts();
  saveUiSession({ qcActiveTab: tabId });
}

// Top-level QC category: "mq" (per-sensor nulling/QC, existing behaviour)
// vs "tpl" (TPL5010 watchdog DONE/CLR pin injection, below).
export function switchQcGroup(groupId) {
  state.qc.activeGroup = groupId;
  document.querySelectorAll(".qc-groupnav .qc-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.qcgroup === groupId);
  });
  $("qcMqGroup")?.classList.toggle("active", groupId === "mq");
  $("qcTplGroup")?.classList.toggle("active", groupId === "tpl");
  if (groupId === "mq") drawQcCharts();
  saveUiSession({ qcActiveGroup: groupId });
}

async function runSingleNulling(index) {
  const sensor = SENSOR_NAMES[index];
  const passBtn = $(`qcPassBtn-${index}`);
  const failBtn = $(`qcFailBtn-${index}`);
  if (passBtn) passBtn.disabled = true;
  if (failBtn) failBtn.disabled = true;

  const command = `RUN_NULLING_SINGLE_JSON ${JSON.stringify({ channel: index })}`;
  try {
    const ack = await sendCommandAndWaitAck(command, "RUN_NULLING_SINGLE", SINGLE_NULLING_TIMEOUT_MS);
    await sendCommand("GET_QC_STATUS");
    if (ack.status !== "ok") {
      await showAlert(`Nulling ${sensor} (CH${index + 1}): GAGAL - ${ack.message || ack.status}`, "error", "Single-Channel Nulling");
    }
  } catch (error) {
    await showAlert(`Nulling ${sensor} (CH${index + 1}): GAGAL - ${error.message}`, "error", "Single-Channel Nulling");
  } finally {
    renderQcChannelPanel(index);
  }
}

async function submitQcResult(index, pass) {
  const timestamp = new Date().toISOString();
  const command = `SET_QC_RESULT_JSON ${JSON.stringify({ channel: index, pass, timestamp })}`;
  try {
    await sendCommandAndWaitAck(command, "SET_QC_RESULT");
    await sendCommand("GET_QC_STATUS");
  } catch (error) {
    await showAlert(`QC ${pass ? "Pass" : "Fail"} for CH${index + 1}: GAGAL - ${error.message}`, "error", "QC Result");
  }
}

async function resetSingleQc(index) {
  const sensor = SENSOR_NAMES[index];
  const confirmed = await showConfirm(
    `Reset status QC untuk ${sensor} (CH${index + 1})? Verdict pass/fail dan timestamp channel ini akan dihapus dan kembali abu-abu (belum tested). Status nulling tidak ikut di-reset.`,
    "warn",
    "Reset QC"
  );
  if (!confirmed) return;

  const command = `RESET_QC_RESULT_JSON ${JSON.stringify({ channel: index })}`;
  try {
    await sendCommandAndWaitAck(command, "RESET_QC_RESULT");
    await sendCommand("GET_QC_STATUS");
  } catch (error) {
    await showAlert(`Reset QC ${sensor} (CH${index + 1}): GAGAL - ${error.message}`, "error", "Reset QC");
  }
}

async function resetAllQc() {
  const confirmed = await showConfirm(
    "Reset status QC untuk SEMUA 8 channel? Semua verdict pass/fail dan timestamp akan dihapus dan kembali abu-abu (belum tested). Status nulling tidak ikut di-reset.",
    "warn",
    "Reset All QC"
  );
  if (!confirmed) return;

  try {
    await sendCommandAndWaitAck("RESET_QC_ALL", "RESET_QC_ALL");
    await sendCommand("GET_QC_STATUS");
  } catch (error) {
    await showAlert(`Reset All QC: GAGAL - ${error.message}`, "error", "Reset All QC");
  }
}

// ---- TPL group: TPL5010 watchdog DONE/CLR pin injection ----
// Manual bench QC for the always-on timer/latch circuit (see
// docs/firmware/gld-tpl5010-wake-sleep-com10-report.md): DONE is the
// keepalive pulse the firmware normally sends the TPL5010 automatically,
// CLR is the active-low pulse that resets the SN74AUP1G74 power latch and
// therefore cuts power to the board - the same path SLEEP_NOW uses.

const tplInject = {
  autoTimerId: null,
  autoBusy: false,
  autoCount: 0,
  logLines: [],
  logPaused: false,
  logPausedCount: 0
};

const TPL_AUTO_INJECT_INTERVAL_MS = 1000;
const TPL_LOG_MAX_LINES = 300;
// Matches the outgoing command text, the firmware's GLD_SERIAL_INJECT_TPL_*
// log line, and the GLD_CMD_ACK_JSON reply (which embeds "cmd":"INJECT_TPL_*").
const TPL_LOG_LINE_PATTERN = /INJECT_TPL_DONE|INJECT_TPL_CLR/;

function tplStatusEl() {
  return $("qcTplStatus");
}

function setTplStatus(text) {
  const el = tplStatusEl();
  if (el) el.textContent = text;
}

// Mirrors only TPL-relevant lines from the global serial log (see
// onAppendLog in ui.js) so the operator can see send/response pairs right
// here in the QC TPL panel instead of switching to the Log tab.
function renderTplLog() {
  const el = $("qcTplLog");
  if (!el) return;
  el.textContent = tplInject.logLines.join("\n");
  el.scrollTop = el.scrollHeight;
}

function applyTplLogPauseVisibility() {
  const pauseBtn = $("qcTplLogPauseBtn");
  if (!pauseBtn) return;
  pauseBtn.textContent = tplInject.logPaused
    ? `Resume${tplInject.logPausedCount ? ` (${tplInject.logPausedCount} new)` : ""}`
    : "Pause";
  pauseBtn.classList.toggle("primary", tplInject.logPaused);
}

// Auto Inject fires every second, which can make the log scroll too fast to
// read - pausing still records every line (nothing is lost, see
// trackTplLogEntry), it just stops re-rendering the <pre> until resumed.
function toggleTplLogPause() {
  tplInject.logPaused = !tplInject.logPaused;
  if (!tplInject.logPaused) {
    tplInject.logPausedCount = 0;
    renderTplLog();
  }
  applyTplLogPauseVisibility();
}

function trackTplLogEntry(entry, line) {
  if (!TPL_LOG_LINE_PATTERN.test(line)) return;
  tplInject.logLines.push(entry);
  if (tplInject.logLines.length > TPL_LOG_MAX_LINES) {
    tplInject.logLines.splice(0, tplInject.logLines.length - TPL_LOG_MAX_LINES);
  }
  if (tplInject.logPaused) {
    tplInject.logPausedCount += 1;
    applyTplLogPauseVisibility();
    return;
  }
  renderTplLog();
}

let tplLogSubscribed = false;

async function injectTplDoneOnce() {
  try {
    await sendCommandAndWaitAck("INJECT_TPL_DONE", "INJECT_TPL_DONE");
    setTplStatus(`Kaki DONE injected once at ${new Date().toLocaleTimeString()}.`);
  } catch (error) {
    setTplStatus(`Inject DONE GAGAL: ${error.message}`);
  }
}

async function tplAutoInjectTick() {
  if (tplInject.autoBusy) return;
  tplInject.autoBusy = true;
  try {
    await sendCommandAndWaitAck("INJECT_TPL_DONE", "INJECT_TPL_DONE");
    tplInject.autoCount += 1;
    setTplStatus(`Auto Inject DONE aktif - ${tplInject.autoCount} pulses sent, last at ${new Date().toLocaleTimeString()}.`);
  } catch (error) {
    setTplStatus(`Auto Inject DONE error: ${error.message}`);
  } finally {
    tplInject.autoBusy = false;
  }
}

function applyTplAutoInjectVisibility() {
  const autoBtn = $("qcTplAutoInjectBtn");
  const onceBtn = $("qcTplInjectDoneBtn");
  if (autoBtn) autoBtn.textContent = state.qc.tplAutoInject ? "Auto Inject DONE: ON" : "Auto Inject DONE per Detik";
  if (autoBtn) autoBtn.classList.toggle("primary", state.qc.tplAutoInject);
  if (onceBtn) onceBtn.disabled = state.qc.tplAutoInject;
}

function toggleTplAutoInject() {
  state.qc.tplAutoInject = !state.qc.tplAutoInject;
  if (state.qc.tplAutoInject) {
    tplInject.autoCount = 0;
    tplAutoInjectTick();
    tplInject.autoTimerId = window.setInterval(tplAutoInjectTick, TPL_AUTO_INJECT_INTERVAL_MS);
    setTplStatus("Auto Inject DONE aktif - mengirim setiap detik (latching).");
  } else {
    if (tplInject.autoTimerId != null) window.clearInterval(tplInject.autoTimerId);
    tplInject.autoTimerId = null;
    setTplStatus(`Auto Inject DONE dihentikan setelah ${tplInject.autoCount} pulses.`);
  }
  applyTplAutoInjectVisibility();
}

async function injectTplClrOnce() {
  const confirmed = await showConfirm(
    "Inject kaki CLR sekali? Pulsa ini akan me-reset power latch (SN74AUP1G74) - sama seperti SLEEP_NOW - dan bisa langsung memutus daya GLD serta koneksi serial.",
    "warn",
    "Inject Kaki CLR"
  );
  if (!confirmed) return;
  try {
    await sendCommandAndWaitAck("INJECT_TPL_CLR", "INJECT_TPL_CLR");
    setTplStatus(`Kaki CLR injected once at ${new Date().toLocaleTimeString()} - board mungkin mati/putus koneksi.`);
  } catch (error) {
    setTplStatus(`Inject CLR GAGAL: ${error.message}`);
  }
}

function buildTplPanel() {
  const panel = document.createElement("div");
  panel.innerHTML = `
    <div class="module-head module-head--wrap">
      <h3>TPL5010 Watchdog Pin Injection</h3>
    </div>
    <div class="status-line">Kirim pulsa serial manual ke kaki DONE dan CLR milik TPL5010 / power latch untuk QC bench.</div>
    <div class="toolbar">
      <button id="qcTplInjectDoneBtn" type="button">Inject Once (Kaki DONE)</button>
      <button id="qcTplAutoInjectBtn" type="button">Auto Inject DONE per Detik</button>
      <button id="qcTplInjectClrBtn" type="button">Inject Once (Kaki CLR)</button>
    </div>
    <div id="qcTplStatus" class="status-line">Belum ada injeksi.</div>
    <div class="module-head module-head--inner">
      <h3>TPL Command Log</h3>
      <div class="toolbar">
        <button id="qcTplLogPauseBtn" type="button">Pause</button>
        <button id="qcTplLogClearBtn" type="button">Clear</button>
      </div>
    </div>
    <pre id="qcTplLog" class="terminal compact-log"></pre>
  `;
  return panel;
}

// ---- full scale sweep popup (voltage-vs-DAC-code characterization curve) ----
// Firmware streams one FULLSCALE_STEP line per DAC code as
// RUN_FULLSCALE_SWEEP_JSON runs (see GldNullingService::runFullScaleSweep),
// so this state/UI is driven entirely by log lines routed in from
// appendFullScaleSweep(), not by the command's own ack.

const fullScaleSweep = {
  channel: null,
  running: false,
  points: [],
  statusText: "Click Start to sweep MCP min to max."
};

// Sweeping every one of the ~4096 codes (not a stride of 32) means up to
// 4096 FULLSCALE_STEP lines can arrive back-to-back - rebuilding the whole
// table and redrawing the canvas on every single line would make the popup
// visibly choke, so steps append one row at a time and coalesce chart
// redraws onto a single animation frame instead of one draw per line.
let sweepChartRedrawScheduled = false;

function fullScaleSweepModalEls() {
  return {
    modal: $("fullScaleSweepModal"),
    title: $("fullScaleSweepTitle"),
    status: $("fullScaleSweepStatus"),
    chart: $("fullScaleSweepChart"),
    tableBody: $("fullScaleSweepTableBody"),
    tableWrap: $("fullScaleSweepTableBody")?.closest(".fullscale-table-wrap"),
    startBtn: $("fullScaleSweepStartBtn"),
    exportBtn: $("fullScaleSweepExportBtn")
  };
}

function scheduleSweepChartRedraw() {
  if (sweepChartRedrawScheduled) return;
  sweepChartRedrawScheduled = true;
  requestAnimationFrame(() => {
    sweepChartRedrawScheduled = false;
    drawFullScaleSweepChart($("fullScaleSweepChart"), fullScaleSweep.points, DAC_CODE_MAX);
  });
}

function appendFullScaleSweepRow(point) {
  const els = fullScaleSweepModalEls();
  if (!els.tableBody) return;
  const sensor = fullScaleSweep.channel != null ? SENSOR_NAMES[fullScaleSweep.channel] : "-";
  const row = document.createElement("tr");
  [sensor, String(point.code), point.voltage.toFixed(6)].forEach((text) => {
    const cell = document.createElement("td");
    cell.textContent = text;
    row.append(cell);
  });
  els.tableBody.append(row);
  if (els.tableWrap) els.tableWrap.scrollTop = els.tableWrap.scrollHeight;
}

// Full rebuild - used only on open/start/finish, not per FULLSCALE_STEP line.
function renderFullScaleSweepView() {
  const els = fullScaleSweepModalEls();
  if (!els.modal) return;
  if (els.status) els.status.textContent = fullScaleSweep.statusText;
  drawFullScaleSweepChart(els.chart, fullScaleSweep.points, DAC_CODE_MAX);

  if (els.tableBody) {
    const sensor = fullScaleSweep.channel != null ? SENSOR_NAMES[fullScaleSweep.channel] : "-";
    els.tableBody.innerHTML = "";
    for (const point of fullScaleSweep.points) {
      const row = document.createElement("tr");
      const cells = [sensor, String(point.code), point.voltage.toFixed(6)];
      cells.forEach((text) => {
        const cell = document.createElement("td");
        cell.textContent = text;
        row.append(cell);
      });
      els.tableBody.append(row);
    }
    if (els.tableWrap) els.tableWrap.scrollTop = els.tableWrap.scrollHeight;
  }
  if (els.startBtn) els.startBtn.disabled = fullScaleSweep.running;
  if (els.exportBtn) els.exportBtn.disabled = fullScaleSweep.points.length === 0;
}

function openFullScaleSweepModal(index) {
  fullScaleSweep.channel = index;
  fullScaleSweep.running = false;
  fullScaleSweep.points = [];
  fullScaleSweep.statusText = "Click Start to sweep MCP min to max.";
  const els = fullScaleSweepModalEls();
  if (els.title) els.title.textContent = `Full Scale MCP Sweep - ${SENSOR_NAMES[index]} (CH${index + 1})`;
  renderFullScaleSweepView();
  setPanelOpen(els.modal, true);
}

async function startFullScaleSweep() {
  const index = fullScaleSweep.channel;
  if (index == null || fullScaleSweep.running) return;
  fullScaleSweep.running = true;
  fullScaleSweep.points = [];
  fullScaleSweep.statusText = `Sweeping ${SENSOR_NAMES[index]} (CH${index + 1})...`;
  renderFullScaleSweepView();

  const command = `RUN_FULLSCALE_SWEEP_JSON ${JSON.stringify({ channel: index })}`;
  try {
    const ack = await sendCommandAndWaitAck(command, "RUN_FULLSCALE_SWEEP", FULL_SCALE_SWEEP_TIMEOUT_MS);
    if (ack.status !== "ok") {
      fullScaleSweep.running = false;
      fullScaleSweep.statusText = `Sweep DITOLAK: ${ack.message || ack.status}`;
      renderFullScaleSweepView();
    }
    // On "ok" the ack just means the sweep started - FULLSCALE_START/STEP/DONE
    // log lines (routed via appendFullScaleSweep) drive the rest of the view.
  } catch (error) {
    fullScaleSweep.running = false;
    fullScaleSweep.statusText = `Sweep GAGAL: ${error.message}`;
    renderFullScaleSweepView();
  }
}

function exportFullScaleSweepCsv() {
  if (!fullScaleSweep.points.length) return;
  const sensor = fullScaleSweep.channel != null ? SENSOR_NAMES[fullScaleSweep.channel] : "unknown";
  const rows = [["Sensor", "MCP", "Voltage"], ...fullScaleSweep.points.map((point) => [sensor, point.code, point.voltage.toFixed(6)])];
  const csv = rows.map((row) => row.map(csvCell).join(",")).join("\n");
  downloadText(`GLD_fullscale_sweep_${sensor}_${stamp()}.csv`, `${csv}\n`, "text/csv");
}

// Routed in from serial-protocol.js for every "FULLSCALE_" prefixed line.
export function appendFullScaleSweep(line) {
  const ch = channelIndexFromLog(line);
  if (ch == null || ch !== fullScaleSweep.channel) return;

  if (line.startsWith("FULLSCALE_START")) {
    fullScaleSweep.running = true;
    fullScaleSweep.points = [];
    fullScaleSweep.statusText = `Sweeping ${SENSOR_NAMES[ch]} (CH${ch + 1})...`;
    renderFullScaleSweepView();
  } else if (line.startsWith("FULLSCALE_STEP")) {
    const code = Number(tokenValue(line, "code"));
    const voltage = Number(tokenValue(line, "voltage"));
    const valid = tokenValue(line, "valid") === "1";
    if (valid && Number.isFinite(code) && Number.isFinite(voltage)) {
      const point = { code, voltage };
      fullScaleSweep.points.push(point);
      appendFullScaleSweepRow(point);
      scheduleSweepChartRedraw();
      const exportBtn = $("fullScaleSweepExportBtn");
      if (exportBtn && exportBtn.disabled) exportBtn.disabled = false;
    }
  } else if (line.startsWith("FULLSCALE_BLOCKED")) {
    fullScaleSweep.running = false;
    fullScaleSweep.statusText = `Sweep blocked: ${tokenValue(line, "status") || "hardware not ready"}`;
    renderFullScaleSweepView();
  } else if (line.startsWith("FULLSCALE_DONE")) {
    fullScaleSweep.running = false;
    const status = tokenValue(line, "status") || "Unknown";
    fullScaleSweep.statusText = status === "Ok"
      ? `Sweep complete - ${fullScaleSweep.points.length} points captured, DAC restored.`
      : `Sweep finished with status ${status} - see log for detail.`;
    renderFullScaleSweepView();
  }
}

function buildAllSensorPanel() {
  const panel = document.createElement("div");
  panel.className = "qc-subview active";
  panel.dataset.qctab = "all";
  panel.innerHTML = `
    <div class="module-head module-head--wrap">
      <h3>All Sensors</h3>
      <div class="toolbar">
        <button id="qcRunNullingBtn" type="button">Run Nulling (All Channels)</button>
        <button id="qcRefreshBtn" type="button">Refresh QC Status</button>
        <button id="qcResetAllBtn" type="button">Reset All QC</button>
      </div>
    </div>
    <div id="qcAllChartWrap" class="chart-wrap qc-chart-wrap" hidden>
      <canvas id="qcAllChart" width="1200" height="420"></canvas>
    </div>
    <div id="qcAllChartLegend" class="legend qc-chart-wrap" hidden></div>
    <div class="status-line qc-chart-off-hint">QC-OFF - click QC-ON above to show live sensor graphs.</div>
    <div id="qcAllSummary" class="status-line">Waiting for GET_QC_STATUS.</div>
    <div id="qcAllGrid" class="channel-grid" aria-label="QC status per channel"></div>
    <div class="module-head module-head--inner">
      <h3>Nulling Progress (All Channels)</h3>
    </div>
    <div id="qcAllNullingGrid" class="channel-grid" aria-label="Nulling progress per channel"></div>
  `;
  return panel;
}

function buildChannelPanel(index) {
  const sensor = SENSOR_NAMES[index];
  const panel = document.createElement("div");
  panel.className = "qc-subview";
  panel.dataset.qctab = String(index);
  panel.innerHTML = `
    <div class="module-head module-head--wrap">
      <h3>${sensor} - Channel ${index + 1}</h3>
    </div>
    <div id="qcChannelChartWrap-${index}" class="chart-wrap qc-chart-wrap" hidden>
      <canvas id="qcChannelChart-${index}" width="1200" height="420"></canvas>
    </div>
    <div id="qcChannelChartLegend-${index}" class="legend qc-chart-wrap" hidden></div>
    <div class="status-line qc-chart-off-hint">QC-OFF - click QC-ON above to show this sensor's live graph.</div>
    <div id="qcStatsWrap-${index}" class="qc-chart-wrap" hidden>
      <div class="module-head module-head--inner">
        <h3>Signal Analysis</h3>
      </div>
      <dl id="qcStats-${index}" class="kv qc-stats"></dl>
    </div>
    <div id="qcNullingStatus-${index}" class="status-line">Nulling: unknown.</div>
    <div class="toolbar">
      <button id="qcNullSingleBtn-${index}" type="button">Null ${sensor} Only</button>
      <button id="qcFullScaleBtn-${index}" type="button">Full Scale MCP Sweep</button>
    </div>
    <div id="qcChannelNullingGrid-${index}" class="channel-grid" aria-label="Nulling progress"></div>
    <div class="toolbar">
      <button id="qcPassBtn-${index}" type="button" class="primary" disabled>Pass QC</button>
      <button id="qcFailBtn-${index}" type="button" disabled>Fail QC</button>
      <button id="qcResetBtn-${index}" type="button">Reset QC</button>
    </div>
    <div id="qcHistory-${index}" class="status-line">No QC verdict recorded yet.</div>
  `;
  return panel;
}

// ---- live chart (QC-ON) ----

export function drawQcCharts() {
  if (!state.qc.latchOn) return;
  drawOneChart($("qcAllChart"), elements.rangeSelect, $("qcAllChartLegend"), [], [0, 1, 2, 3, 4, 5, 6, 7]);
  for (let index = 0; index < 8; index += 1) {
    drawOneChart($(`qcChannelChart-${index}`), elements.rangeSelect, $(`qcChannelChartLegend-${index}`), [], [index]);
    renderSignalAnalysis(index);
  }
}

// ---- signal analysis (QC-ON, per-channel sub-tabs) ----
const SIGNAL_QC_STANDARD = {
  minSamplesPass: 10,
  minSamplesWarn: 5,
  noiseStddevPassV: 0.0005,
  noiseStddevWarnV: 0.0010,
  driftPassVPerMin: 0.0010,
  driftWarnVPerMin: 0.0030,
  peakToPeakPassV: 0.0030,
  peakToPeakWarnV: 0.0100,
  minStableSamples: 5,
  outlierFloorV: 0.0020
};

function finiteNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : NaN;
}

function meanValue(values) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : NaN;
}

function stddevValue(values, center = meanValue(values)) {
  return values.length ? Math.sqrt(values.reduce((sum, value) => sum + (value - center) ** 2, 0) / values.length) : NaN;
}

function medianValue(values) {
  if (!values.length) return NaN;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function toneMax(value, passMax, warnMax) {
  if (!Number.isFinite(value)) return "warn";
  if (value <= passMax) return "pass";
  return value <= warnMax ? "warn" : "fail";
}

function toneMin(value, passMin, warnMin) {
  if (!Number.isFinite(value)) return "warn";
  if (value >= passMin) return "pass";
  return value >= warnMin ? "warn" : "fail";
}

function worstTone(tones) {
  if (tones.includes("fail")) return "fail";
  if (tones.includes("warn")) return "warn";
  return "pass";
}

function channelSignalPoints(index, rangeMs) {
  const cutoff = Date.now() - rangeMs;
  return state.history
    .filter((point) => point.ts >= cutoff)
    .map((point) => {
      const value = finiteNumber(point.sensorVoltage?.[index]);
      if (!Number.isFinite(value)) return null;
      return {
        ts: finiteNumber(point.ts),
        value,
        gain: finiteNumber(point.sensorGain?.[index]),
        status: finiteNumber(point.sensorStatus?.[index])
      };
    })
    .filter((point) => point && Number.isFinite(point.ts));
}

function latestFinite(values) {
  for (let index = values.length - 1; index >= 0; index -= 1) {
    if (Number.isFinite(values[index])) return values[index];
  }
  return NaN;
}

function latestSignalStatus(index, points) {
  const live = finiteNumber(state.status?.telemetry?.sensorStatus?.[index]);
  if (Number.isFinite(live)) return live;
  return latestFinite(points.map((point) => point.status));
}

function latestSignalGain(index, points) {
  const live = finiteNumber(state.status?.telemetry?.sensorGain?.[index]);
  if (Number.isFinite(live)) return live;
  return latestFinite(points.map((point) => point.gain));
}

function slopePerMinute(points) {
  if (points.length < 2) return NaN;
  const start = points[0].ts;
  const xs = points.map((point) => (point.ts - start) / 60000);
  const ys = points.map((point) => point.value);
  const xMean = meanValue(xs);
  const yMean = meanValue(ys);
  const denominator = xs.reduce((sum, x) => sum + (x - xMean) ** 2, 0);
  if (denominator === 0) return 0;
  const numerator = xs.reduce((sum, x, index) => sum + (x - xMean) * (ys[index] - yMean), 0);
  return numerator / denominator;
}

function signalOutlierCount(values, noiseStddev) {
  if (values.length < SIGNAL_QC_STANDARD.minStableSamples) return 0;
  const middle = medianValue(values);
  const mad = medianValue(values.map((value) => Math.abs(value - middle)));
  const robustSigma = mad > 0 ? mad * 1.4826 : noiseStddev;
  const threshold = Math.max(SIGNAL_QC_STANDARD.outlierFloorV, robustSigma * 4);
  return values.filter((value) => Math.abs(value - middle) > threshold).length;
}

function signalStableSeconds(points) {
  if (points.length < SIGNAL_QC_STANDARD.minStableSamples) return NaN;
  for (let start = 0; start <= points.length - SIGNAL_QC_STANDARD.minStableSamples; start += 1) {
    const suffix = points.slice(start);
    const values = suffix.map((point) => point.value);
    const suffixStddev = stddevValue(values);
    const suffixDrift = Math.abs(slopePerMinute(suffix));
    if (suffixStddev <= SIGNAL_QC_STANDARD.noiseStddevPassV
        && suffixDrift <= SIGNAL_QC_STANDARD.driftPassVPerMin) {
      return (points[points.length - 1].ts - suffix[0].ts) / 1000;
    }
  }
  return NaN;
}

function computeSignalAnalysis(index) {
  const rangeMs = (Number(elements.rangeSelect?.value) || 60) * 1000;
  const points = channelSignalPoints(index, rangeMs);
  const values = points.map((point) => point.value);
  const sampleCount = values.length;
  const latest = latestFinite(values);
  const max = sampleCount ? Math.max(...values) : NaN;
  const min = sampleCount ? Math.min(...values) : NaN;
  const average = meanValue(values);
  const noise = stddevValue(values, average);
  const peakToPeak = Number.isFinite(max) && Number.isFinite(min) ? max - min : NaN;
  const drift = slopePerMinute(points);
  const outliers = signalOutlierCount(values, noise);
  const gain = latestSignalGain(index, points);
  const uniqueGains = new Set(points.map((point) => point.gain).filter(Number.isFinite));
  const status = latestSignalStatus(index, points);

  const sampleTone = toneMin(sampleCount, SIGNAL_QC_STANDARD.minSamplesPass, SIGNAL_QC_STANDARD.minSamplesWarn);
  const adsTone = status === 0 ? "pass" : Number.isFinite(status) ? "fail" : "warn";
  const noiseTone = toneMax(noise, SIGNAL_QC_STANDARD.noiseStddevPassV, SIGNAL_QC_STANDARD.noiseStddevWarnV);
  const driftTone = toneMax(Math.abs(drift), SIGNAL_QC_STANDARD.driftPassVPerMin, SIGNAL_QC_STANDARD.driftWarnVPerMin);
  const spanTone = toneMax(peakToPeak, SIGNAL_QC_STANDARD.peakToPeakPassV, SIGNAL_QC_STANDARD.peakToPeakWarnV);
  const outlierWarnMax = Math.max(1, Math.floor(sampleCount * 0.05));
  const outlierTone = outliers === 0 ? "pass" : outliers <= outlierWarnMax ? "warn" : "fail";
  const gainTone = !Number.isFinite(gain) ? "warn" : uniqueGains.size <= 1 ? "pass" : uniqueGains.size <= 2 ? "warn" : "fail";
  const stableTone = worstTone([sampleTone, noiseTone, driftTone]);
  const stableForSec = signalStableSeconds(points);
  const verdictTone = worstTone([sampleTone, adsTone, noiseTone, driftTone, spanTone, outlierTone, gainTone, stableTone]);

  return {
    rangeSec: rangeMs / 1000,
    sampleCount,
    latest,
    average,
    noise,
    peakToPeak,
    drift,
    outliers,
    outlierWarnMax,
    gain,
    uniqueGainCount: uniqueGains.size,
    statusName: SENSOR_STATUS_NAMES[status] || (Number.isFinite(status) ? `Status ${status}` : "Unknown"),
    sampleTone,
    adsTone,
    noiseTone,
    driftTone,
    spanTone,
    outlierTone,
    gainTone,
    stableTone,
    stableForSec,
    verdictTone
  };
}

function formatSignalV(value) {
  return Number.isFinite(value) ? `${value.toFixed(6)} V` : "-";
}

function formatSignalDrift(value) {
  return Number.isFinite(value) ? `${value >= 0 ? "+" : ""}${value.toFixed(6)} V/min` : "-";
}

function signalIndicatorLabel(tone, fallback = "") {
  if (fallback) return fallback;
  if (tone === "pass") return "OK";
  if (tone === "warn") return "NEAR";
  if (tone === "fail") return "FAIL";
  return "REF";
}

function renderSignalAnalysis(index) {
  const dl = $(`qcStats-${index}`);
  if (!dl) return;
  const stats = computeSignalAnalysis(index);
  dl.innerHTML = "";

  const addSection = (label, detail) => {
    const item = document.createElement("div");
    item.className = "qc-stats-section";
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = detail;
    item.append(dt, dd);
    dl.append(item);
  };

  const addRow = (label, value, tone = "", marker = "") => {
    const item = document.createElement("div");
    if (tone) item.className = tone;
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    if (tone) {
      const indicator = document.createElement("span");
      indicator.className = `qc-indicator ${tone}`;
      indicator.textContent = signalIndicatorLabel(tone, marker);
      dd.append(indicator, document.createTextNode(value));
    } else {
      dd.textContent = value;
    }
    item.append(dt, dd);
    dl.append(item);
  };

  addSection("Live Signal QC", "Green meets standard, yellow is near limit, red is outside limit.");
  addRow(
    "Overall signal verdict",
    stats.verdictTone === "pass" ? "Ready for QC judgement" : stats.verdictTone === "warn" ? "Close, keep watching" : "Do not pass yet",
    stats.verdictTone
  );
  addRow(
    "Samples",
    `${stats.sampleCount} samples / standard >= ${SIGNAL_QC_STANDARD.minSamplesPass} in ${stats.rangeSec}s window`,
    stats.sampleTone
  );
  addRow(
    "ADS status",
    `${stats.statusName} / standard Ok`,
    stats.adsTone,
    stats.adsTone === "warn" ? "CHECK" : ""
  );
  addRow("Latest voltage", `${formatSignalV(stats.latest)} / mean ${formatSignalV(stats.average)}`);
  addRow(
    "Noise stddev",
    `${formatSignalV(stats.noise)} / OK <= ${formatSignalV(SIGNAL_QC_STANDARD.noiseStddevPassV)} / near <= ${formatSignalV(SIGNAL_QC_STANDARD.noiseStddevWarnV)}`,
    stats.noiseTone
  );
  addRow(
    "Peak-to-peak ripple",
    `${formatSignalV(stats.peakToPeak)} / OK <= ${formatSignalV(SIGNAL_QC_STANDARD.peakToPeakPassV)} / near <= ${formatSignalV(SIGNAL_QC_STANDARD.peakToPeakWarnV)}`,
    stats.spanTone
  );
  addRow(
    "Drift rate",
    `${formatSignalDrift(stats.drift)} / OK <= +/-${SIGNAL_QC_STANDARD.driftPassVPerMin.toFixed(6)} V/min / near <= +/-${SIGNAL_QC_STANDARD.driftWarnVPerMin.toFixed(6)} V/min`,
    stats.driftTone
  );
  addRow(
    "Outliers",
    `${stats.outliers} samples / OK 0 / near <= ${stats.outlierWarnMax}`,
    stats.outlierTone
  );
  addRow(
    "Gain stability",
    Number.isFinite(stats.gain)
      ? `latest gain ${stats.gain}, ${stats.uniqueGainCount || 1} gain mode(s) in window / OK 1`
      : "No gain evidence yet",
    stats.gainTone,
    stats.gainTone === "warn" && !Number.isFinite(stats.gain) ? "CHECK" : ""
  );
  addRow(
    "Time stable",
    Number.isFinite(stats.stableForSec)
      ? `${stats.stableForSec.toFixed(1)} s stable / standard stddev+drift both OK`
      : "Not stable inside current window",
    stats.stableTone
  );
}

function applyQcLatchVisibility() {
  document.querySelectorAll(".qc-chart-wrap").forEach((el) => { el.hidden = !state.qc.latchOn; });
  document.querySelectorAll(".qc-chart-off-hint").forEach((el) => { el.hidden = state.qc.latchOn; });
  const btn = $("qcLatchBtn");
  if (btn) btn.textContent = state.qc.latchOn ? "QC-ON" : "QC-OFF";
}

function toggleQcLatch() {
  state.qc.latchOn = !state.qc.latchOn;
  applyQcLatchVisibility();
  if (state.qc.latchOn) {
    if (!state.polling) togglePolling();
    drawQcCharts();
  }
  saveUiSession({ qcLatchOn: state.qc.latchOn });
}

// Restores the latch's ON/OFF display state after a page refresh, without
// touching polling itself - the general session restore in main.js already
// decides whether to resume polling, so this only needs to catch the latch
// display up to that decision instead of re-triggering it a second time.
export function restoreQcLatch(on) {
  state.qc.latchOn = Boolean(on);
  applyQcLatchVisibility();
  drawQcCharts();
}

// ---- live nulling visualization (reuses the Nulling tab's card renderer) ----

export function renderQcNullingViews() {
  renderNullingChannels($("qcAllNullingGrid"), null);
  for (let index = 0; index < 8; index += 1) {
    renderNullingChannels($(`qcChannelNullingGrid-${index}`), [index]);
  }
}

export function initQcTab() {
  const groupTrack = $("qcGroupNavTrack");
  if (groupTrack) {
    groupTrack.innerHTML = "";
    [{ id: "mq", label: "MQ" }, { id: "tpl", label: "TPL" }].forEach(({ id, label }) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `qc-tab${id === "mq" ? " active" : ""}`;
      button.dataset.qcgroup = id;
      button.textContent = label;
      button.addEventListener("click", () => switchQcGroup(id));
      groupTrack.append(button);
    });
  }

  const tplGroup = $("qcTplGroup");
  if (tplGroup) {
    tplGroup.innerHTML = "";
    tplGroup.append(buildTplPanel());
    $("qcTplInjectDoneBtn")?.addEventListener("click", () => {
      const button = $("qcTplInjectDoneBtn");
      withBusy(button, "Injecting...", injectTplDoneOnce);
    });
    $("qcTplAutoInjectBtn")?.addEventListener("click", toggleTplAutoInject);
    $("qcTplInjectClrBtn")?.addEventListener("click", () => {
      const button = $("qcTplInjectClrBtn");
      withBusy(button, "Injecting...", injectTplClrOnce);
    });
    $("qcTplLogClearBtn")?.addEventListener("click", () => {
      tplInject.logLines = [];
      tplInject.logPausedCount = 0;
      renderTplLog();
      applyTplLogPauseVisibility();
    });
    $("qcTplLogPauseBtn")?.addEventListener("click", toggleTplLogPause);
    applyTplAutoInjectVisibility();
    applyTplLogPauseVisibility();
    renderTplLog();
    if (!tplLogSubscribed) {
      tplLogSubscribed = true;
      onAppendLog(trackTplLogEntry);
    }
  }

  const track = $("qcSubnavTrack");
  const panels = $("qcPanels");
  if (!track || !panels) return;

  const tabs = [{ id: "all", label: "All Sensor" }, ...SENSOR_NAMES.map((name, index) => ({ id: String(index), label: name }))];
  track.innerHTML = "";
  tabs.forEach(({ id, label }) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `qc-tab${id === "all" ? " active" : ""}`;
    button.dataset.qctab = id;
    button.textContent = label;
    button.addEventListener("click", () => switchQcTab(id));
    track.append(button);
  });

  panels.innerHTML = "";
  panels.append(buildAllSensorPanel());
  for (let index = 0; index < 8; index += 1) panels.append(buildChannelPanel(index));

  $("qcRefreshBtn")?.addEventListener("click", () => sendCommand("GET_QC_STATUS"));
  $("qcRunNullingBtn")?.addEventListener("click", () => sendCommand("SET_MODE nulling"));
  $("qcResetAllBtn")?.addEventListener("click", () => {
    const button = $("qcResetAllBtn");
    withBusy(button, "Resetting...", resetAllQc);
  });
  $("qcLatchBtn")?.addEventListener("click", toggleQcLatch);
  for (let index = 0; index < 8; index += 1) {
    $(`qcPassBtn-${index}`)?.addEventListener("click", () => submitQcResult(index, true));
    $(`qcFailBtn-${index}`)?.addEventListener("click", () => submitQcResult(index, false));
    $(`qcNullSingleBtn-${index}`)?.addEventListener("click", () => {
      const button = $(`qcNullSingleBtn-${index}`);
      withBusy(button, "Nulling...", () => runSingleNulling(index));
    });
    $(`qcResetBtn-${index}`)?.addEventListener("click", () => {
      const button = $(`qcResetBtn-${index}`);
      withBusy(button, "Resetting...", () => resetSingleQc(index));
    });
    $(`qcFullScaleBtn-${index}`)?.addEventListener("click", () => openFullScaleSweepModal(index));
  }

  $("fullScaleSweepStartBtn")?.addEventListener("click", startFullScaleSweep);
  $("fullScaleSweepExportBtn")?.addEventListener("click", exportFullScaleSweepCsv);

  applyQcLatchVisibility();
  renderQc();
  renderQcNullingViews();
}
