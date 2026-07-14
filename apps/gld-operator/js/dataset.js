// Dataset capture workflow: parameters -> SET_MODE dataset handshake ->
// MQTT START_DATASET/STOP_DATASET -> row capture -> CSV + session log.

import { $, elements, state, SENSOR_NAMES, DATASET_RUNTIME_READY_TIMEOUT_MS, DATASET_WAITING_STUCK_MS, initialDatasetSession } from "./state.js";
import { appendLog, getField, numberField, saveForm, downloadText, csvCell, stamp, nowText, switchTab } from "./ui.js";
import { bridgeFetch } from "./bridge-client.js";
import { tokenValue, handleLine, sendCommand } from "./serial-protocol.js";
import { emitMockInfo, emitMockStatus } from "./mock.js";

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

// ---- session lifecycle ----

function startDatasetSession(dataset, deviceId) {
  const label = dataset.label || getField("datasetLabel") || "dataset";
  const session = initialDatasetSession();
  session.active = true;
  session.state = "Starting";
  session.phase = "Publishing START_DATASET";
  session.sessionId = dataset.session_id || crypto.randomUUID();
  session.label = label;
  session.deviceId = deviceId || state.info?.deviceId || "F001";
  session.target = Number(dataset.target_samples) || 0;
  session.startedAt = Date.now();
  session.fileName = datasetFileName(session.deviceId, label);
  session.outputName = session.fileName;
  session.outputPath = "Will save to app output/datasets";
  session.nullingFirst = dataset.run_nulling_first === true;
  session.lastEvent = `START_DATASET prepared for ${session.deviceId}`;
  state.dataset = session;
  renderDatasetSession();
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
  renderDatasetSession();
  maybeAutoSaveDataset();
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
    if (Number.isFinite(seq)) {
      state.dataset.phase = `Serial record ${seq} seen`;
    } else {
      state.dataset.phase = "Serial dataset record seen";
    }
    state.dataset.lastSampleAt = Date.now();
    state.dataset.lastEvent = `${nowText()} ${line}`;
    renderDatasetSession();
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
    addDatasetRecord(data, "mqtt");
    setDatasetState("Capturing", "MQTT dataset/data received", `MQTT data seq=${data.seq ?? state.dataset.rows.length}`);
    return;
  }
  if (kind === "status") {
    const sampleCount = Number(data.sample_count ?? data.samples ?? data.total ?? data.seq);
    if (Number.isFinite(sampleCount) && sampleCount >= 0) state.dataset.phase = `Status samples ${sampleCount}`;
    const remoteState = String(data.state || data.status || "").trim();
    if (remoteState) {
      if (state.dataset.active && state.dataset.rows.length === 0 && /^idle$/i.test(remoteState)) {
        state.dataset.state = "Waiting Data";
        state.dataset.phase = "GLD reports dataset idle. Check START_DATASET ACK, device ID/topic, and nulling profile.";
      } else {
        state.dataset.state = remoteState;
      }
    }
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
  const featureOrder = raw.feature_order || raw.featureOrder || telemetry.featureOrder || SENSOR_NAMES;
  const timestampMs = raw.timestamp_ms ?? raw.timestampMs ?? Date.now();
  return {
    timeIso: new Date(Number(timestampMs) > 100000000000 ? Number(timestampMs) : Date.now()).toISOString(),
    source,
    device_id: raw.device_id || raw.deviceId || state.dataset.deviceId || state.info?.deviceId || "",
    node_id: raw.node_id ?? raw.nodeId ?? state.status?.nodeId ?? state.info?.nodeId ?? "",
    mode: raw.mode || state.status?.mode || state.mode || "DATASET",
    seq: raw.seq ?? "",
    timestamp_ms: timestampMs,
    label: raw.label || state.dataset.label || getField("datasetLabel"),
    nulling_profile_id: raw.nulling_profile_id ?? raw.nullingProfileId ?? "",
    sensor_voltage: Array.from({ length: 8 }, (_, index) => Number.isFinite(Number(sensorVoltage[index])) ? Number(sensorVoltage[index]) : ""),
    sensor_gain: Array.from({ length: 8 }, (_, index) => sensorGain[index] ?? ""),
    feature_order: Array.from({ length: 8 }, (_, index) => featureOrder[index] || SENSOR_NAMES[index])
  };
}

function addDatasetRecord(raw, source) {
  const record = normalizeDatasetRecord(raw, source);
  const key = record.seq !== "" ? `${record.source}:${record.device_id}:${record.seq}` : `${record.source}:${record.timestamp_ms}:${state.dataset.rows.length}`;
  if (state.dataset.rowKeys.has(key)) return;
  state.dataset.rowKeys.add(key);
  state.dataset.rows.push(record);
  if (state.dataset.rows.length > 5000) {
    state.dataset.rows.splice(0, state.dataset.rows.length - 5000);
  }
  state.dataset.active = true;
  state.dataset.state = "Capturing";
  state.dataset.phase = state.dataset.target ? `Captured ${state.dataset.rows.length} of ${state.dataset.target}` : `Captured ${state.dataset.rows.length} rows`;
  state.dataset.lastSampleAt = Date.now();
  if (!state.dataset.startedAt) state.dataset.startedAt = Date.now();
  renderDatasetSession();
}

export function maybeCaptureDatasetTelemetry(status) {
  const mode = String(status.mode || state.mode || "").toLowerCase();
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
    if (Number.isFinite(count) && !remoteIdleWhileWaiting) state.dataset.phase = `Status samples ${count}`;
    state.dataset.lastEvent = `${nowText()} GLD dataset status updated`;
  }
  renderDatasetSession();
}

function datasetCsv() {
  const headers = [
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
    ...Array.from({ length: 8 }, (_, index) => `feature_${index + 1}`)
  ];
  const rows = state.dataset.rows.map((row) => [
    row.timeIso,
    state.dataset.sessionId,
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
    ...row.feature_order
  ]);
  return [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\n") + "\n";
}

export async function saveDatasetCsv() {
  if (!state.dataset.rows.length) {
    setDatasetState(state.dataset.state, "No rows to save", "DATASET_SAVE_SKIPPED no rows", true);
    return;
  }
  const filename = state.dataset.fileName || datasetFileName(state.dataset.deviceId, state.dataset.label);
  if (!state.bridgeAvailable) {
    downloadText(filename, datasetCsv(), "text/csv");
    state.dataset.outputName = filename;
    state.dataset.outputPath = "Downloaded by browser";
    state.dataset.saved = true;
    renderDatasetSession();
    return;
  }
  try {
    const result = await bridgeFetch("/api/dataset/save", {
      method: "POST",
      body: JSON.stringify({ filename, csv: datasetCsv() })
    });
    state.dataset.outputName = result.filename || filename;
    state.dataset.outputPath = result.path || "Saved";
    state.dataset.saved = true;
    state.dataset.lastEvent = `${nowText()} Dataset CSV saved`;
    renderDatasetSession();
  } catch (error) {
    setDatasetState("Error", "CSV save failed", `DATASET_SAVE_ERROR ${error.message}`, true);
  }
}

function maybeAutoSaveDataset() {
  if (!state.dataset.rows.length || state.dataset.saved) return;
  if (!state.bridgeAvailable) {
    state.dataset.outputPath = "Bridge unavailable - use Download CSV";
    renderDatasetSession();
    return;
  }
  saveDatasetCsv();
}

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
  renderDatasetSession();
}

function datasetHint(session) {
  if (session.error) return session.error;
  if (session.state === "Needs Nulling") {
    return "Dataset was not started because this GLD has no saved nulling profile. Open the Nulling tab, run nulling once, then start dataset again.";
  }
  if (session.state === "Nulling First") {
    return "Nulling-first is enabled. The app switched GLD to nulling mode and did not publish START_DATASET yet. Wait for PASS, then start dataset again with the option off.";
  }
  if (session.active && session.rows.length === 0) {
    return "No dataset samples yet. Confirm GLD is in dataset mode, device ID/topic root match, MQTT host is this PC, and START_DATASET was acknowledged.";
  }
  if (session.rows.length > 0 && session.active) {
    return "Dataset capture is receiving samples. Use Save CSV when done, or Stop Dataset to finish early.";
  }
  if (session.state === "Done") {
    return "Dataset session is complete. Save CSV or open the output folder to inspect the file.";
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
  const target = Number(session.target) || 0;
  const progressText = target > 0 ? `${session.rows.length} / ${target}` : `${session.rows.length} / unlimited`;
  elements.datasetProgressValue.textContent = progressText;
  const percent = target > 0 ? Math.max(0, Math.min(100, (session.rows.length / target) * 100)) : session.rows.length ? 100 : 0;
  elements.datasetProgressBar.style.width = `${percent}%`;
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
  if (!window.confirm("Apply WiFi/MQTT settings to GLD and reboot it?")) return;
  await sendCommand(`SET_APP_CONFIG_JSON ${JSON.stringify(payload)}`);
}

export async function publishDatasetCommand(command) {
  const deviceId = state.info?.deviceId || $("targetDeviceId").value.trim().toUpperCase();
  const dataset = command === "START_DATASET"
    ? {
        cmd: "START_DATASET",
        session_id: state.dataset.sessionId || crypto.randomUUID(),
        label: getField("datasetLabel"),
        target_samples: numberField("targetSamples"),
        sample_interval_ms: numberField("sampleIntervalMs"),
        max_duration_ms: numberField("maxDurationMs"),
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
