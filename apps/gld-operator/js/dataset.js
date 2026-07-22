// Dataset capture workflow: parameters -> SET_MODE dataset handshake ->
// MQTT START_DATASET/STOP_DATASET -> row capture -> CSV + session log.

import { $, elements, state, SENSOR_NAMES, DATASET_RUNTIME_READY_TIMEOUT_MS, DATASET_WAITING_STUCK_MS, DATASET_WIZARD_LABELS, initialDatasetSession } from "./state.js";
import { appendLog, getField, numberField, saveForm, downloadText, csvCell, stamp, nowText, switchTab, showConfirm, showBanner, wait, setPanelOpen } from "./ui.js";
import { bridgeFetch } from "./bridge-client.js";
import { tokenValue, handleLine, sendCommand, applyAndAlert } from "./serial-protocol.js";
import { emitMockInfo, emitMockStatus } from "./mock.js";
import { drawChart } from "./chart.js";

// ---- 6-step capture wizard (Mode -> Confirm -> Start -> Capturing -> Stop -> Save) ----
// A visual progress tracker layered on top of the existing dataset workflow.
// It observes the same events the workflow already produces (mode switch,
// session start/done, save/download) rather than gating them, so an operator
// who jumps ahead (e.g. clicks Start Dataset directly) still gets a
// sensible in-order picture instead of a stuck indicator.

export function initDatasetWizard() {
  state.datasetWizard = ["pending", "pending", "pending", "pending", "pending", "pending"];
  renderDatasetWizard();
}

function setWizardStep(index, status) {
  if (state.datasetWizard[index] === status) return;
  state.datasetWizard[index] = status;
  renderDatasetWizard();
}

// Marks every step up to (but not including) `index` as done, for when the
// operator skips ahead (e.g. Start Dataset without using Switch to Dataset
// first) - the indicator should read as "already past this" rather than
// stuck on gray.
function fastForwardWizardTo(index) {
  for (let i = 0; i < index; i += 1) {
    if (state.datasetWizard[i] !== "done") state.datasetWizard[i] = "done";
  }
  renderDatasetWizard();
}

export function renderDatasetWizard() {
  if (!elements.datasetWizard) return;
  elements.datasetWizard.innerHTML = "";
  state.datasetWizard.forEach((status, index) => {
    const step = document.createElement("div");
    step.className = `wizard-step wizard-step--${status}`;
    const dot = document.createElement("span");
    dot.className = "wizard-dot";
    dot.textContent = String(index + 1);
    const label = document.createElement("span");
    label.className = "wizard-label";
    label.textContent = DATASET_WIZARD_LABELS[index];
    step.append(dot, label);
    elements.datasetWizard.append(step);
  });
}

// Resolves once the given drawer closes, however the operator closes it
// (Close button, backdrop click, Escape) - reviewing/editing the actual
// editable settings and then closing is treated as "confirmed", rather than
// requiring a separate read-only summary popup.
function waitForDrawerClose(panel) {
  return new Promise((resolve) => {
    const observer = new MutationObserver(() => {
      if (!panel.classList.contains("open")) {
        observer.disconnect();
        resolve();
      }
    });
    observer.observe(panel, { attributes: true, attributeFilter: ["class"] });
  });
}

async function waitForModeDataset(timeoutMs = 6000) {
  const start = Date.now();
  if (String(state.mode || "").toLowerCase() === "dataset") return true;
  while (Date.now() - start < timeoutMs) {
    await wait(400);
    if (String(state.mode || "").toLowerCase() === "dataset") return true;
    await sendCommand("GET_STATUS");
  }
  return String(state.mode || "").toLowerCase() === "dataset";
}

// Step 1 + 2: switch the GLD to dataset mode, then open the actual editable
// Dataset Settings drawer so the operator can review and, if needed, change
// the capture parameters before Start Dataset (step 3) becomes the natural
// next click. Wired to the "Switch to Dataset" button in main.js.
export async function beginDatasetSwitch() {
  setWizardStep(0, "active");
  await sendCommand("SET_MODE dataset");
  const confirmed = await waitForModeDataset();
  if (!confirmed) {
    setWizardStep(0, "pending");
    showBanner("Could not confirm the GLD switched to dataset mode.", "warn");
    return;
  }
  setWizardStep(0, "done");
  setWizardStep(1, "active");
  const panel = $("datasetSettingsPanel");
  setPanelOpen(panel, true);
  await waitForDrawerClose(panel);
  setWizardStep(1, "done");
  setWizardStep(2, "active");
}

// Step 3: called when Start Dataset is actually clicked, regardless of
// whether the operator went through steps 1-2 first.
export function markDatasetWizardStarted() {
  fastForwardWizardTo(2);
  setWizardStep(2, "done");
  setWizardStep(3, "active");
}

// Step 6: called after a successful Save CSV or Download CSV.
export function markDatasetWizardSaved() {
  setWizardStep(5, "done");
}

function safeJson(text) {
  try { return JSON.parse(text); } catch { return null; }
}

function safeFilePart(value) {
  return String(value).trim().replace(/[^A-Za-z0-9_.-]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40) || "dataset";
}

function datasetFileName(deviceId, label) {
  const safeDevice = safeFilePart(deviceId || "GLD");
  const safeLabel = safeFilePart(label || "dataset");
  return `${safeDevice}_${safeLabel}_${stamp()}.csv`;
}

// File created on Confirm Config uses just label+timestamp (no device
// prefix) per the operator-facing naming this feature was asked for - the
// device id is still recorded as a column inside every row.
function confirmedDatasetFileName(label) {
  return `${safeFilePart(label || "dataset")}_${stamp()}.csv`;
}

const DATASET_CSV_HEADERS = [
  "timeIso",
  "session_id",
  "source",
  "device_id",
  "node_id",
  "mode",
  "seq",
  "timestamp_ms",
  "label",
  "nulling_profile_id",
  ...SENSOR_NAMES.map((name) => `sv_${name}`),
  ...SENSOR_NAMES.map((name) => `gain_${name}`),
  ...SENSOR_NAMES.map((name) => `status_${name}`),
  ...Array.from({ length: 8 }, (_, index) => `feature_${index + 1}`)
];

function datasetCsvHeaderLine() {
  return DATASET_CSV_HEADERS.map(csvCell).join(",");
}

function datasetRowCsvLine(row, sessionId) {
  const cells = [
    row.timeIso,
    sessionId,
    row.source,
    row.device_id,
    row.node_id,
    row.mode,
    row.seq,
    row.timestamp_ms,
    row.label,
    row.nulling_profile_id,
    ...row.sensor_voltage,
    ...row.sensor_gain,
    ...row.sensor_status,
    ...row.feature_order
  ];
  return cells.map(csvCell).join(",");
}

function formatDuration(start, end) {
  if (!start) return "00:00";
  const seconds = Math.max(0, Math.floor(((end || Date.now()) - start) / 1000));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

function formatDatasetTime(value) {
  if (!Number.isFinite(value)) return "--:--:--";
  return new Date(value).toLocaleTimeString("en-GB", { hour12: false });
}

function formatNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(6) : "";
}

function metricValue(source, ...keys) {
  for (const key of keys) {
    const number = Number(source?.[key]);
    if (Number.isFinite(number)) return number;
  }
  return null;
}

function datasetQueueText(source) {
  const pending = metricValue(source, "queuePending", "queue_pending", "pending");
  const dropped = metricValue(source, "queueDropped", "queue_dropped", "dropped");
  const failed = metricValue(source, "publishFailCount", "publish_fail_count", "failCount");
  const parts = [];
  if (pending !== null && (pending > 0 || dropped > 0 || failed > 0)) parts.push(`pending ${pending}`);
  if (dropped !== null && dropped > 0) parts.push(`dropped ${dropped}`);
  if (failed !== null && failed > 0) parts.push(`publish fail ${failed}`);
  return parts.length ? `Queue ${parts.join(", ")}` : "";
}

function queueTextFromSerial(line) {
  const pending = tokenValue(line, "pending");
  const seq = tokenValue(line, "seq");
  if (line.startsWith("DATASET_QUEUE_DROP")) return seq ? `Queue full, dropped seq ${seq}` : "Queue full, dropped oldest sample";
  if (line.startsWith("DATASET_QUEUE_ENQUEUE")) return `Queue ${pending ? `pending ${pending}` : "sample buffered"}`;
  if (line.startsWith("DATASET_QUEUE_RETRY")) return `Queue retry ${line.includes("ok=1") ? "sent" : "waiting"}${pending ? `, pending ${pending}` : ""}`;
  return "Dataset queue event";
}

// ---- session lifecycle ----

// Step 2 of the wizard, now an explicit action instead of "drawer closed =
// confirmed": creates the CSV file on disk immediately (header row only) so
// it exists before any recording starts. Every sample captured afterward is
// appended to this same file in real time (see appendDatasetRowToFile), so a
// sudden crash/disconnect mid-session still leaves every reading recorded up
// to that point on disk - Start Dataset stays disabled until this succeeds.
export async function confirmDatasetConfig() {
  if (!state.datasetGldConfigApplied) {
    const status = $("datasetConfirmStatus");
    if (status) status.textContent = "Apply WiFi/MQTT settings above first - Confirm Config unlocks once that succeeds.";
    setDatasetState(state.dataset.state, "Apply GLD Settings (WiFi/MQTT) first", "DATASET_CONFIRM_BLOCKED wifi/mqtt not applied", true);
    return;
  }
  const label = getField("datasetLabel") || "dataset";
  saveForm();
  if (!state.bridgeAvailable) {
    const status = $("datasetConfirmStatus");
    if (status) status.textContent = "Local bridge required to create the live CSV file.";
    setDatasetState(state.dataset.state, "Bridge required to create the live CSV file", "DATASET_CONFIRM_SKIPPED bridge unavailable", true);
    return;
  }
  const filename = confirmedDatasetFileName(label);
  try {
    const result = await bridgeFetch("/api/dataset/create", {
      method: "POST",
      body: JSON.stringify({ filename, header: datasetCsvHeaderLine() })
    });
    state.dataset.label = label;
    state.dataset.fileName = result.filename || filename;
    state.dataset.outputName = result.filename || filename;
    state.dataset.outputPath = result.path || "Created";
    state.dataset.configConfirmed = true;
    state.dataset.lastEvent = `${nowText()} Confirmed config, created ${state.dataset.fileName}`;
    const status = $("datasetConfirmStatus");
    if (status) status.textContent = `Confirmed - recording will write live to ${state.dataset.fileName}.`;
    setWizardStep(1, "done");
    setWizardStep(2, "active");
    renderDatasetSession();
    updateStartDatasetAvailability();
    setPanelOpen($("datasetSettingsPanel"), false);
  } catch (error) {
    const status = $("datasetConfirmStatus");
    if (status) status.textContent = `Failed to create file: ${error.message}`;
    setDatasetState("Error", "Failed to create dataset CSV", `DATASET_CONFIRM_ERROR ${error.message}`, true);
  }
}

function updateStartDatasetAvailability() {
  const button = $("startDatasetBtn");
  if (button) button.disabled = !state.dataset.configConfirmed;
}

function startDatasetSession(dataset, deviceId) {
  const label = dataset.label || state.dataset.label || getField("datasetLabel") || "dataset";
  const confirmedFile = {
    fileName: state.dataset.fileName,
    outputName: state.dataset.outputName,
    outputPath: state.dataset.outputPath,
    configConfirmed: state.dataset.configConfirmed
  };
  const session = initialDatasetSession();
  Object.assign(session, confirmedFile);
  session.active = true;
  session.state = "Starting";
  session.phase = "Publishing START_DATASET";
  session.sessionId = dataset.session_id || crypto.randomUUID();
  session.label = label;
  session.deviceId = deviceId || state.info?.deviceId || "F001";
  session.target = 0; // recording is unbounded - only Stop Dataset ends it
  session.startedAt = Date.now();
  session.nullingFirst = dataset.run_nulling_first === true;
  session.lastEvent = `START_DATASET prepared for ${session.deviceId}`;
  state.dataset = session;
  renderDatasetSession();
  drawChart();
}

export function setDatasetState(nextState, phase, eventText, isError = false) {
  state.dataset.state = nextState || state.dataset.state;
  if (phase) state.dataset.phase = phase;
  if (eventText) state.dataset.lastEvent = `${nowText()} ${eventText}`;
  if (isError) state.dataset.error = eventText || nextState;
  renderDatasetSession();
}

function resetDatasetRuntimeReadiness() {
  state.datasetRuntime = { mode: false, ready: false, mqtt: false };
}

function datasetRuntimeIsReady() {
  return state.datasetRuntime.mode && state.datasetRuntime.ready && state.datasetRuntime.mqtt;
}

function resolveDatasetReadyWaiters(value) {
  const waiters = state.datasetReadyWaiters.splice(0);
  for (const waiter of waiters) {
    clearTimeout(waiter.timer);
    waiter.resolve(value);
  }
}

function notifyDatasetRuntimeReady() {
  if (datasetRuntimeIsReady()) resolveDatasetReadyWaiters(true);
}

export function trackDatasetRuntimeLine(line) {
  if (line.startsWith("GLD_MODE=dataset") || line.includes('"mode":"dataset"')) {
    state.datasetRuntime.mode = true;
  }
  if (line.startsWith("DATASET_READY")) {
    state.datasetRuntime.ready = true;
  }
  if (line.startsWith("MQTT_CONNECT_RESULT=OK")) {
    state.datasetRuntime.mqtt = true;
  }
  if (line.startsWith("GLD_MODE=inference") || line.startsWith("WIFI_OFF mode=inference")) {
    resetDatasetRuntimeReadiness();
  }
  notifyDatasetRuntimeReady();
}

function waitForDatasetRuntimeReady(timeoutMs = DATASET_RUNTIME_READY_TIMEOUT_MS) {
  if (datasetRuntimeIsReady()) return Promise.resolve(true);
  return new Promise((resolve) => {
    const waiter = {
      resolve,
      timer: setTimeout(() => {
        state.datasetReadyWaiters = state.datasetReadyWaiters.filter((item) => item !== waiter);
        resolve(false);
      }, timeoutMs)
    };
    state.datasetReadyWaiters.push(waiter);
  });
}

function markDatasetDone(reason) {
  if (!state.dataset.endedAt) state.dataset.endedAt = Date.now();
  state.dataset.active = false;
  state.dataset.state = "Done";
  state.dataset.phase = reason || "Capture complete";
  state.dataset.lastEvent = `${nowText()} ${reason || "Dataset complete"}`;
  // The file was already written live throughout the session (every row
  // appended as it was captured), so there is nothing left to save here -
  // just reflect that and require a fresh Confirm Config (new file) before
  // the operator can start another take.
  state.dataset.saved = true;
  state.dataset.configConfirmed = false;
  fastForwardWizardTo(4);
  setWizardStep(3, "done");
  setWizardStep(4, "done");
  markDatasetWizardSaved();
  renderDatasetSession();
  drawChart();
  updateStartDatasetAvailability();
  saveSessionLog(state.dataset.sessionId || stamp(), "serial");
}

export async function saveSessionLog(sessionId, kind) {
  if (!state.bridgeAvailable) return;
  const lines = kind === "nulling" ? state.nullingLogs : state.logs;
  if (!lines.length) return;
  const filename = `${safeFilePart(sessionId)}_${kind}.log`;
  try {
    await bridgeFetch("/api/session/log", {
      method: "POST",
      body: JSON.stringify({ filename, text: `${lines.join("\n")}\n` })
    });
  } catch {
    /* best-effort; Download Log remains available manually */
  }
}

export function handleDatasetSerialLine(line) {
  if (line.startsWith("DATASET_READY")) {
    setDatasetState("Ready", "GLD dataset runtime ready", line);
    return;
  }
  if (line.startsWith("DATASET_START_REJECT") || line.startsWith("DATASET_CMD_PARSE_ERROR")) {
    setDatasetState("Error", "GLD rejected dataset command", line, true);
    return;
  }
  if (line.startsWith("DATASET_START")) {
    const target = Number.parseInt(tokenValue(line, "target") || "", 10);
    if (Number.isFinite(target) && target > 0) state.dataset.target = target;
    state.dataset.active = true;
    if (!state.dataset.startedAt) state.dataset.startedAt = Date.now();
    setDatasetState("Capturing", "GLD accepted START_DATASET", line);
    return;
  }
  if (line.startsWith("DATASET_RECORD")) {
    state.dataset.active = true;
    const seq = Number.parseInt(tokenValue(line, "seq") || "", 10);
    const queueText = datasetQueueText({
      pending: tokenValue(line, "pending"),
      failCount: line.includes("ok=0") ? 1 : 0
    });
    if (Number.isFinite(seq)) {
      state.dataset.phase = queueText ? `Serial record ${seq} seen, ${queueText.toLowerCase()}` : `Serial record ${seq} seen`;
    } else {
      state.dataset.phase = queueText ? `Serial dataset record seen, ${queueText.toLowerCase()}` : "Serial dataset record seen";
    }
    state.dataset.lastSampleAt = Date.now();
    state.dataset.lastEvent = `${nowText()} ${line}`;
    renderDatasetSession();
    return;
  }
  if (line.startsWith("DATASET_QUEUE_")) {
    setDatasetState(state.dataset.state, queueTextFromSerial(line), line);
    return;
  }
  if (line.startsWith("DATASET_AUTOSTOP")) {
    const total = tokenValue(line, "total");
    markDatasetDone(total ? `Autostop complete, total ${total}` : line);
    return;
  }
  if (line.startsWith("DATASET_STOP")) {
    const total = tokenValue(line, "totalSeq");
    markDatasetDone(total ? `Stopped, total ${total}` : line);
    return;
  }
  setDatasetState(state.dataset.state, "Dataset event", line);
}

export function handleDatasetMqttEvent(payload) {
  const kind = payload.kind || "message";
  const data = payload.json || safeJson(payload.payload || "") || {};
  const text = payload.payload || "";

  if (kind === "data" && data.sensor_voltage) {
    if (addDatasetRecord(data, "mqtt")) {
      setDatasetState("Capturing", "MQTT dataset/data received", `MQTT data seq=${data.seq ?? state.dataset.rows.length}`);
    } else {
      setDatasetState("Rejected Data", "Invalid, duplicate, or unhealthy dataset sample was not saved", `MQTT data rejected seq=${data.seq ?? "?"}`, true);
    }
    return;
  }
  if (kind === "status") {
    const sampleCount = Number(data.sample_count ?? data.samples ?? data.total ?? data.seq);
    const queueText = datasetQueueText(data);
    if (Number.isFinite(sampleCount) && sampleCount >= 0) state.dataset.phase = `Status samples ${sampleCount}`;
    const remoteState = String(data.state || data.status || "").trim();
    const remoteIdleWhileWaiting = state.dataset.active && state.dataset.rows.length === 0 && /^idle$/i.test(remoteState);
    if (remoteState) {
      if (remoteIdleWhileWaiting) {
        state.dataset.state = "Waiting Data";
        state.dataset.phase = "GLD reports dataset idle. Check START_DATASET ACK, device ID/topic, and nulling profile.";
      } else {
        state.dataset.state = remoteState;
      }
    }
    if (queueText && !remoteIdleWhileWaiting) state.dataset.phase = queueText;
    state.dataset.lastEvent = `${nowText()} MQTT status ${text}`;
    renderDatasetSession();
    return;
  }
  if (kind === "summary") {
    const total = data.total_samples ?? data.total ?? data.count ?? state.dataset.rows.length;
    markDatasetDone(`MQTT summary received, total ${total}`);
    return;
  }
  if (kind === "ack") {
    const result = data.result || data.status || data.message || text;
    const cmd = data.cmd || data.command || "";
    const ok = /ok|accepted|success/i.test(String(result));
    const noProfile = /reject_no_profile/i.test(String(result));
    const rejected = /reject|error|fail/i.test(String(result));
    if (ok && String(cmd).toUpperCase() === "SET_MODE" && state.pendingMqttMode) {
      state.mode = state.pendingMqttMode;
      $("modeValue").textContent = state.pendingMqttMode;
      elements.topModeStatus.textContent = state.pendingMqttMode;
      state.pendingMqttMode = "";
    }
    const phase = noProfile
      ? "No nulling profile in GLD. Run nulling once, then start dataset again."
      : ok && String(cmd).toUpperCase() === "SET_MODE" ? "GLD acknowledged MQTT SET_MODE"
        : ok ? "GLD acknowledged dataset command" : "GLD command response";
    setDatasetState(ok ? "Command ACK" : noProfile ? "Needs Nulling" : "Command response", phase, `MQTT ack ${cmd} ${result}`, !ok && rejected);
    return;
  }
  state.dataset.lastEvent = `${nowText()} MQTT ${kind} ${text}`;
  renderDatasetSession();
}

function normalizeDatasetRecord(raw, source) {
  const telemetry = raw.telemetry || {};
  const sensorVoltage = raw.sensor_voltage || raw.sensorVoltage || telemetry.sensorVoltage || [];
  const sensorGain = raw.sensor_gain || raw.sensorGain || telemetry.sensorGain || [];
  const sensorStatus = raw.sensor_status || raw.sensorStatus || telemetry.sensorStatus || [];
  const featureOrder = raw.feature_order || raw.featureOrder || telemetry.featureOrder || [];
  const timestampMs = raw.timestamp_ms ?? raw.timestampMs ?? Date.now();
  const mode = String(raw.mode || state.status?.mode || state.mode || "").toUpperCase();
  const validVoltage = Array.isArray(sensorVoltage) && sensorVoltage.length === 8
    && sensorVoltage.every((value) => Number.isFinite(Number(value)));
  const validGain = Array.isArray(sensorGain) && sensorGain.length === 8
    && sensorGain.every((value) => [1, 2, 4, 8, 16, 32, 64].includes(Number(value)));
  const validStatus = Array.isArray(sensorStatus) && sensorStatus.length === 8
    && sensorStatus.every((value) => Number(value) === 0);
  const validOrder = Array.isArray(featureOrder) && featureOrder.length === 8
    && featureOrder.every((value, index) => value === SENSOR_NAMES[index]);
  if (mode !== "DATASET" || !validVoltage || !validGain || !validStatus || !validOrder) return null;
  return {
    timeIso: new Date(Number(timestampMs) > 100000000000 ? Number(timestampMs) : Date.now()).toISOString(),
    source,
    device_id: raw.device_id || raw.deviceId || state.dataset.deviceId || state.info?.deviceId || "",
    node_id: raw.node_id ?? raw.nodeId ?? state.status?.nodeId ?? state.info?.nodeId ?? "",
    mode,
    seq: raw.seq ?? "",
    timestamp_ms: timestampMs,
    label: raw.label || state.dataset.label || getField("datasetLabel"),
    nulling_profile_id: raw.nulling_profile_id ?? raw.nullingProfileId ?? "",
    sensor_voltage: Array.from({ length: 8 }, (_, index) => Number.isFinite(Number(sensorVoltage[index])) ? Number(sensorVoltage[index]) : ""),
    sensor_gain: Array.from({ length: 8 }, (_, index) => sensorGain[index] ?? ""),
    sensor_status: Array.from({ length: 8 }, (_, index) => Number(sensorStatus[index])),
    feature_order: Array.from({ length: 8 }, (_, index) => featureOrder[index])
  };
}

// Pushes the row straight to the CSV file on disk as it's captured (not
// awaited by the caller - a slow/failed write must never stall live
// capture) so a sudden crash mid-session still leaves every reading up to
// that point safely on disk, not just whatever made it into memory.
async function appendDatasetRowToFile(record) {
  if (!state.bridgeAvailable || !state.dataset.fileName) return;
  const line = datasetRowCsvLine(record, state.dataset.sessionId);
  try {
    await bridgeFetch("/api/dataset/append", {
      method: "POST",
      body: JSON.stringify({ filename: state.dataset.fileName, lines: [line] })
    });
  } catch (error) {
    appendLog(`DATASET_APPEND_ERROR ${error.message}`, "in");
  }
}

function addDatasetRecord(raw, source) {
  const record = normalizeDatasetRecord(raw, source);
  if (!record) {
    appendLog(`DATASET_RECORD_REJECTED source=${source} invalid mode/voltage/gain/status/feature_order`, "in");
    return false;
  }
  const key = record.seq !== "" ? `${record.device_id}:${record.seq}` : `${record.device_id}:${record.timestamp_ms}`;
  if (state.dataset.rowKeys.has(key)) return false;
  state.dataset.rowKeys.add(key);
  state.dataset.rows.push(record);
  if (state.dataset.rows.length > 5000) {
    state.dataset.rows.splice(0, state.dataset.rows.length - 5000);
  }
  state.dataset.active = true;
  state.dataset.state = "Capturing";
  state.dataset.phase = `Recording - ${state.dataset.rows.length} rows captured`;
  state.dataset.lastSampleAt = Date.now();
  if (!state.dataset.startedAt) state.dataset.startedAt = Date.now();
  renderDatasetSession();
  appendDatasetRowToFile(record);
  return true;
}

export function maybeCaptureDatasetTelemetry(status) {
  const mode = String(status.mode || state.mode || "").toLowerCase();
  if (state.datasetRuntime.mqtt) return;
  if (!state.dataset.active || mode !== "dataset") return;
  const telemetry = status.telemetry;
  if (!telemetry?.valid || !Array.isArray(telemetry.sensorVoltage)) return;
  addDatasetRecord(
    {
      deviceId: status.deviceId || state.info?.deviceId,
      nodeId: status.nodeId || state.info?.nodeId,
      mode: status.mode,
      seq: state.dataset.rows.length + 1,
      label: state.dataset.label || getField("datasetLabel"),
      telemetry
    },
    "serial-status"
  );
}

export function updateDatasetFromStatus(status) {
  const mode = String(status.mode || "").toLowerCase();
  if (mode === "dataset" && state.dataset.state === "Idle") {
    state.dataset.state = "Dataset Mode";
    state.dataset.phase = "GLD is in dataset mode";
    state.dataset.lastEvent = `${nowText()} GLD status reports dataset mode`;
  }
  const dataset = status.dataset || status.datasetState;
  if (dataset && typeof dataset === "object") {
    if (dataset.running === true) state.dataset.active = true;
    if (dataset.done === true) state.dataset.active = false;
    const remoteState = String(dataset.state || dataset.status || "").trim();
    const remoteIdleWhileWaiting = state.dataset.active && state.dataset.rows.length === 0 && /^idle$/i.test(remoteState);
    if (remoteState) {
      if (remoteIdleWhileWaiting) {
        state.dataset.state = "Waiting Data";
        state.dataset.phase = "GLD reports dataset idle. Check START_DATASET ACK, device ID/topic, and nulling profile.";
      } else {
        state.dataset.state = remoteState;
      }
    }
    const count = Number(dataset.samples ?? dataset.sampleCount ?? dataset.total);
    const queueText = datasetQueueText(dataset);
    if (Number.isFinite(count) && !remoteIdleWhileWaiting) state.dataset.phase = `Status samples ${count}`;
    if (queueText && !remoteIdleWhileWaiting) state.dataset.phase = queueText;
    state.dataset.lastEvent = queueText
      ? `${nowText()} GLD dataset status updated (${queueText})`
      : `${nowText()} GLD dataset status updated`;
  }
  renderDatasetSession();
}

function datasetCsv() {
  const lines = state.dataset.rows.map((row) => datasetRowCsvLine(row, state.dataset.sessionId));
  return [datasetCsvHeaderLine(), ...lines].join("\n") + "\n";
}

// The authoritative file is written in real time to disk by the bridge as
// each row is captured (see appendDatasetRowToFile) - this is only a
// convenience client-side snapshot of whatever rows are currently held in
// the browser's in-memory buffer, for a quick look without leaving the app.
export function downloadDatasetCsv() {
  if (!state.dataset.rows.length) {
    setDatasetState(state.dataset.state, "No rows to download", "DATASET_DOWNLOAD_SKIPPED no rows", true);
    return;
  }
  const filename = state.dataset.fileName || datasetFileName(state.dataset.deviceId, state.dataset.label);
  downloadText(filename, datasetCsv(), "text/csv");
}

export async function openDatasetFolder() {
  if (!state.bridgeAvailable) {
    setDatasetState(state.dataset.state, "Bridge required to open folder", "DATASET_OPEN_FOLDER_SKIPPED bridge unavailable", true);
    return;
  }
  try {
    const result = await bridgeFetch("/api/dataset/open-folder", { method: "POST", body: "{}" });
    state.dataset.outputPath = result.path || state.dataset.outputPath;
    renderDatasetSession();
  } catch (error) {
    setDatasetState("Error", "Open folder failed", `DATASET_OPEN_FOLDER_ERROR ${error.message}`, true);
  }
}

export function clearDatasetSession() {
  state.dataset = initialDatasetSession();
  initDatasetWizard();
  updateStartDatasetAvailability();
  const status = $("datasetConfirmStatus");
  if (status) status.textContent = "Not confirmed yet - confirming creates the CSV file immediately (with header), before any recording starts.";
  renderDatasetSession();
  drawChart();
}

function datasetHint(session) {
  if (session.error) return session.error;
  if (session.state === "Needs Nulling") {
    return "Dataset was not started because this GLD has no saved nulling profile. Open the Nulling tab, run nulling once, then start dataset again.";
  }
  if (session.state === "Nulling First") {
    return "Nulling-first is enabled. The app switched GLD to nulling mode and did not publish START_DATASET yet. Wait for PASS, then start dataset again with the option off.";
  }
  if (!session.configConfirmed && !session.active && session.state === "Idle") {
    return "Confirm the dataset config (creates the CSV file) before Start Dataset becomes available.";
  }
  if (session.active && session.rows.length === 0) {
    return "No dataset samples yet. Confirm GLD is in dataset mode, device ID/topic root match, MQTT host is this PC, and START_DATASET was acknowledged.";
  }
  if (session.rows.length > 0 && session.active) {
    return "Recording - every row is being written live to the CSV file as it's captured. Click Stop Dataset when done.";
  }
  if (session.state === "Done") {
    return "Dataset session is complete. The CSV file already has every row - open the output folder to inspect it.";
  }
  return "No active dataset session.";
}

export function refreshDatasetWaitingState() {
  const session = state.dataset;
  if (!session.startedAt) {
    renderDatasetSession();
    return;
  }
  const ageMs = Date.now() - session.startedAt;
  const passiveStates = /^(Starting|Command Sent|Command ACK|Monitor Ready|Ready|Dataset Mode|idle)$/i;
  if (session.active && session.rows.length === 0 && ageMs > DATASET_WAITING_STUCK_MS && passiveStates.test(session.state)) {
    const ackSeen = session.state === "Command ACK" || /ack/i.test(session.lastEvent || "");
    session.state = "Waiting Data";
    session.phase = ackSeen
      ? "START_DATASET was acknowledged but no samples arrived yet. Check nulling profile and sensor wiring."
      : "No ACK seen yet for START_DATASET. Check GLD mode, MQTT topic/device ID, and broker reachability.";
  }
  renderDatasetSession();
}

export function renderDatasetSession() {
  const session = state.dataset;
  elements.datasetStateValue.textContent = session.state;
  elements.datasetPhaseValue.textContent = session.phase;
  elements.datasetRowsValue.textContent = String(session.rows.length);
  elements.datasetLastEvent.textContent = session.lastEvent;
  elements.datasetOutputName.textContent = session.outputName;
  elements.datasetOutputPath.textContent = session.outputPath;
  elements.datasetHint.textContent = datasetHint(session);
  elements.runNullingNowBtn.hidden = session.state !== "Needs Nulling";
  elements.datasetElapsedValue.textContent = `Elapsed ${formatDuration(session.startedAt, session.endedAt || Date.now())}`;
  elements.datasetLastSampleValue.textContent = session.lastSampleAt ? `Last ${formatDatasetTime(session.lastSampleAt)}` : "No samples";
  // Recording is unbounded (Start/Stop only, like a recorder) - there is no
  // target to show progress against, just a running row count and a simple
  // active/idle indicator bar.
  elements.datasetProgressValue.textContent = `${session.rows.length} row${session.rows.length === 1 ? "" : "s"}`;
  elements.datasetProgressBar.style.width = session.active ? "100%" : session.rows.length ? "100%" : "0%";
  renderDatasetRows();
}

function renderDatasetRows() {
  const rows = state.dataset.rows.slice(-20).reverse();
  elements.datasetRowsBody.innerHTML = "";
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 12;
    td.textContent = "No dataset rows captured.";
    tr.append(td);
    elements.datasetRowsBody.append(tr);
    return;
  }
  for (const row of rows) {
    const tr = document.createElement("tr");
    const cells = [
      formatDatasetTime(Date.parse(row.timeIso)),
      row.source,
      row.seq,
      row.label,
      ...Array.from({ length: 8 }, (_, index) => formatNumber(row.sensor_voltage[index]))
    ];
    for (const value of cells) {
      const td = document.createElement("td");
      td.textContent = String(value ?? "");
      tr.append(td);
    }
    elements.datasetRowsBody.append(tr);
  }
}

// ---- config + commands ----

export async function applyGldSettings() {
  const payload = {
    ssid: getField("wifiSsid"),
    password: $("wifiPassword").value,
    mqttHost: getField("mqttHost"),
    mqttPort: numberField("mqttPort"),
    mqttUser: getField("mqttUser"),
    mqttPass: $("mqttPass").value,
    topicRoot: getField("topicRoot"),
    reboot: true
  };
  if (!payload.ssid || !payload.mqttHost || !payload.topicRoot || !payload.mqttPort) {
    appendLog("CONFIG_REJECTED ssid, mqttHost, mqttPort, and topicRoot are required", "in");
    return;
  }
  saveForm();
  if (!(await showConfirm("Apply WiFi/MQTT settings to GLD and reboot it?", "warn", "Apply GLD Settings"))) return;
  const ack = await applyAndAlert(`SET_APP_CONFIG_JSON ${JSON.stringify(payload)}`, "SET_APP_CONFIG", "Apply GLD Settings");
  if (ack?.status === "ok") {
    state.datasetGldConfigApplied = true;
    const status = $("datasetGldConfigStatus");
    if (status) status.textContent = "Applied - GLD is rebooting with these WiFi/MQTT settings. Confirm Config is now unlocked.";
    updateConfirmDatasetConfigAvailability();
  }
}

function updateConfirmDatasetConfigAvailability() {
  const button = $("confirmDatasetConfigBtn");
  if (button) {
    button.disabled = !state.datasetGldConfigApplied;
    button.title = state.datasetGldConfigApplied ? "" : "Apply GLD Settings (WiFi/MQTT) first";
  }
  const status = $("datasetConfirmStatus");
  if (status && !state.dataset.configConfirmed) {
    status.textContent = state.datasetGldConfigApplied
      ? "Not confirmed yet - confirming creates the CSV file immediately (with header), before any recording starts."
      : "Apply WiFi/MQTT settings above first - Confirm Config unlocks once that succeeds.";
  }
}

export async function publishDatasetCommand(command) {
  const deviceId = state.info?.deviceId || $("targetDeviceId").value.trim().toUpperCase();
  if (command === "START_DATASET" && !state.dataset.configConfirmed) {
    setDatasetState(state.dataset.state, "Confirm the dataset config first (creates the CSV file)", "DATASET_START_BLOCKED config not confirmed", true);
    return;
  }
  const dataset = command === "START_DATASET"
    ? {
        cmd: "START_DATASET",
        session_id: state.dataset.sessionId || crypto.randomUUID(),
        label: getField("datasetLabel"),
        // Unbounded, start/stop-only recording (like a video/audio recorder) -
        // 0 means "no limit" to the firmware for both fields.
        target_samples: 0,
        sample_interval_ms: numberField("sampleIntervalMs"),
        max_duration_ms: 0,
        run_nulling_first: elements.datasetNullingFirst.checked === true,
        use_fan_intake: true,
        fan_on_ms: numberField("fanOnMs"),
        post_fan_settle_ms: numberField("postFanSettleMs")
      }
    : { cmd: "STOP_DATASET" };
  if (command === "START_DATASET") {
    startDatasetSession(dataset, deviceId);
    if (dataset.run_nulling_first) {
      setDatasetState("Nulling First", "Switching GLD to nulling. START_DATASET not published yet.", "DATASET_WAIT_NULLING_FIRST selected");
      switchTab("nulling");
      await sendCommand("SET_MODE nulling");
      return;
    }
    const mode = String(state.status?.mode || state.info?.mode || state.mode || "").toLowerCase();
    if (!state.mock && mode !== "dataset") {
      resetDatasetRuntimeReadiness();
      setDatasetState("Switching Mode", "Waiting for GLD dataset WiFi/MQTT readiness", "SET_MODE dataset before START_DATASET");
      await sendCommand("SET_MODE dataset");
      const ready = await waitForDatasetRuntimeReady();
      if (!ready) {
        setDatasetState("Error", "Timed out waiting for DATASET_READY and MQTT_CONNECT_RESULT=OK", "DATASET_RUNTIME_READY_TIMEOUT", true);
        return;
      }
      setDatasetState("Runtime Ready", "GLD dataset MQTT is ready; publishing START_DATASET", "DATASET_RUNTIME_READY");
    }
  } else {
    setDatasetState("Stopping", "Publishing STOP_DATASET", "STOP_DATASET requested");
  }
  if (state.mock) {
    if (command === "START_DATASET") {
      state.mode = "dataset";
      handleLine(`DATASET_START label=${dataset.label} target=${dataset.target_samples} interval=${dataset.sample_interval_ms}`);
      emitMockInfo();
      emitMockStatus();
    } else {
      handleLine(`DATASET_STOP totalSeq=${state.dataset.rows.length}`);
      state.mode = "inference";
      emitMockInfo();
    }
    return;
  }
  if (!state.bridgeAvailable) {
    setDatasetState("Error", "Local bridge required for MQTT publish", "DATASET_MQTT_SKIPPED local bridge is required", true);
    appendLog("DATASET_MQTT_SKIPPED local bridge is required for MQTT publish", "in");
    return;
  }
  try {
    await bridgeFetch("/api/mqtt/dataset", {
      method: "POST",
      body: JSON.stringify({
        command,
        deviceId,
        slot: state.activeSlot,
        host: getField("mqttHost"),
        port: numberField("mqttPort"),
        username: getField("mqttUser"),
        password: $("mqttPass").value,
        topicRoot: getField("topicRoot"),
        dataset
      })
    });
    setDatasetState(command === "START_DATASET" ? "Command Sent" : "Stop Sent", "Waiting for GLD MQTT response", `${command} published to MQTT`);
  } catch (error) {
    setDatasetState("Error", "MQTT publish failed", `DATASET_MQTT_ERROR ${error.message}`, true);
    appendLog(`DATASET_MQTT_ERROR ${error.message}`, "in");
  }
}

export async function testMqttBroker() {
  if (!state.bridgeAvailable) {
    elements.mqttTestStatus.textContent = "Local bridge required to test broker reachability.";
    return;
  }
  elements.mqttTestStatus.textContent = "Testing...";
  try {
    const result = await bridgeFetch("/api/mqtt/test", {
      method: "POST",
      body: JSON.stringify({
        host: getField("mqttHost"),
        port: numberField("mqttPort"),
        username: getField("mqttUser"),
        password: $("mqttPass").value
      })
    });
    elements.mqttTestStatus.textContent = result.ok
      ? `Reachable - ${result.host}:${result.port} (${result.latencyMs} ms)`
      : `Unreachable - ${result.message}`;
  } catch (error) {
    elements.mqttTestStatus.textContent = `Test failed: ${error.message}`;
  }
}

export async function useLocalhost() {
  if (state.bridgeAvailable) {
    try {
      const info = await bridgeFetch("/api/network");
      if (info.ssid) $("wifiSsid").value = info.ssid;
      if (info.password) $("wifiPassword").value = info.password;
      if (info.ipv4) $("mqttHost").value = info.ipv4;
      if (!$("mqttPort").value) $("mqttPort").value = "1884";
      saveForm();
      appendLog(`USE_THIS_PC ssid=${info.ssid || ""} ipv4=${info.ipv4 || ""}`, "in");
      return;
    } catch (error) {
      appendLog(`USE_THIS_PC_ERROR ${error.message}`, "in");
    }
  }
  const host = location.hostname && location.hostname !== "localhost" ? location.hostname : "127.0.0.1";
  $("mqttHost").value = host;
  if (!$("mqttPort").value) $("mqttPort").value = "1884";
  saveForm();
  appendLog("LOCALHOST_FILL Browser cannot read Windows WiFi SSID/password in HTML-only mode.", "in");
}
