// Serial JSONL/legacy line parsing, boot diagnostics, Sensor Check
// rendering, alarm state, and command send/response-watch/poll plumbing.

import { $, elements, state, encoder, SENSOR_NAMES, SENSOR_MUX_CHANNELS, SENSOR_STATUS_NAMES, SERIAL_RESPONSE_TIMEOUT_MS, DEFAULT_POLL_INTERVAL_MS, CHART_COLORS } from "./state.js";
import { setText, setBadge, appendLog, getField, setField, wait, showAlert, saveUiSession } from "./ui.js";
import { syncDeviceSummary, renderFleetPanel } from "./fleet.js";
import { pruneHistory, drawChart, isSensorChartSeriesVisible, toggleSensorChartSeries } from "./chart.js";
import { renderNullingChannels, latestFeatureOrderForNulling, updateNullingMeta, appendNulling } from "./nulling.js";
import {
  updateDatasetFromStatus, maybeCaptureDatasetTelemetry, trackDatasetRuntimeLine, handleDatasetSerialLine
} from "./dataset.js";
import { handleMockCommand } from "./mock.js";
import { updateQcStatus, resetQcStatus, drawQcCharts, appendFullScaleSweep } from "./qc.js";
import { bridgeFetch, connectBridgeSerialOnly } from "./bridge-client.js";

// ---- generic parse helpers ----

const TCA_ONLINE_SPINNER = ["−", "\\", "|", "/"];
let tcaOnlineSpinnerIndex = 0;

export function parseJsonAfter(prefix, line) {
  if (!line.startsWith(prefix)) return null;
  const raw = line.slice(prefix.length).trim();
  return JSON.parse(raw);
}

export function tokenValue(line, key) {
  const match = new RegExp(`(?:^|\\s)${key}=([^\\s]+)`).exec(line);
  return match?.[1];
}

export function channelIndexFromLog(line) {
  const value = tokenValue(line, "ch") ?? tokenValue(line, "channel");
  if (value == null) return undefined;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 && parsed < 8 ? parsed : undefined;
}

// Fallback names for when telemetry.gasName hasn't arrived yet. Kept in
// sync with gldGasClassName() in firmware/gld/src/GldThresholdClassifier.cpp.
// The active CNN model (cnn_gas_datasheet.zip) only ever produces
// Clean_Air(0)/LPG(1)/CO2(6); the rest are the legacy threshold
// classifier's classes.
const GAS_CLASS_NAMES = {
  0: "Clean_Air",
  1: "LPG",
  2: "methane",
  3: "propane",
  4: "butane",
  6: "CO2",
  7: "H2",
};

export function formatGas(gasClass) {
  if (gasClass == null) return "n/a";
  return GAS_CLASS_NAMES[gasClass] ?? `class ${gasClass}`;
}

function textValue(value, fallback = "Unknown") {
  if (value === "unknown") return fallback;
  return value == null || value === "" ? fallback : String(value);
}

function formatSyncWord(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `0x${numeric.toString(16).toUpperCase().padStart(2, "0")}` : "0x12";
}

function syncLoraConfigFields(lora) {
  if (!lora) return;
  if (Number.isFinite(Number(lora.freqMHz))) setField("loraFreqMHz", Number(lora.freqMHz).toFixed(1));
  if (Number.isFinite(Number(lora.bwKHz))) setField("loraBwKHz", String(Number(lora.bwKHz)));
  if (Number.isFinite(Number(lora.sf))) setField("loraSf", Number(lora.sf));
  if (Number.isFinite(Number(lora.cr))) setField("loraCr", Number(lora.cr));
  if (Number.isFinite(Number(lora.syncWord))) setField("loraSyncWord", formatSyncWord(lora.syncWord));
  if (Number.isFinite(Number(lora.txPowerDbm))) setField("loraTxPowerDbm", Number(lora.txPowerDbm));
  if (Number.isFinite(Number(lora.preamble))) setField("loraPreamble", Number(lora.preamble));
  if (Number.isFinite(Number(lora.tcxoVoltage))) setField("loraTcxoVoltage", String(Number(lora.tcxoVoltage)));
  if (Number.isFinite(Number(lora.xtalVoltage))) setField("loraXtalVoltage", String(Number(lora.xtalVoltage)));
  const parts = [];
  if (Number.isFinite(Number(lora.freqMHz))) parts.push(`${Number(lora.freqMHz).toFixed(1)} MHz`);
  if (Number.isFinite(Number(lora.bwKHz))) parts.push(`${Number(lora.bwKHz)} kHz`);
  if (Number.isFinite(Number(lora.sf))) parts.push(`SF${Number(lora.sf)}`);
  if (Number.isFinite(Number(lora.cr))) parts.push(`CR${Number(lora.cr)}`);
  setText("loraConfigStatus", parts.length ? `Current STAR: ${parts.join(" / ")}. CH STAR must match.` : "Waiting for LoRa config.");
}

// ---- response watch ----

const MAX_CONSECUTIVE_SERIAL_TIMEOUTS = 2;
let consecutiveSerialTimeouts = 0;
let recoveryRequested = false;
let skippedPollLogged = false;
const serialCommandQueue = [];
let sensorPowerApplyPending = false;
let alarmModeApplyPending = false;
let alarmModeSelectionDirty = false;
let manualAlarmApplyPending = false;
let pendingSensorPowerConfirmation = null;
const SENSOR_POWER_CONFIRM_TIMEOUT_MS = 3000;

function serialCommandName(command) {
  return String(command || "").trim().split(/\s+/)[0] || "COMMAND";
}

export function clearSerialResponseWatch() {
  if (!state.pendingSerialRequest) return;
  clearTimeout(state.pendingSerialRequest.timer);
  state.pendingSerialRequest = null;
}

export function clearSerialCommandQueue() {
  serialCommandQueue.length = 0;
}

export function resetSerialLiveness() {
  consecutiveSerialTimeouts = 0;
  recoveryRequested = false;
  skippedPollLogged = false;
}

function expectedResponses(command) {
  const cmd = serialCommandName(command);
  if (cmd === "GET_INFO") return ["info"];
  if (cmd === "GET_STATUS") return ["status"];
  if (cmd === "GET_TELEMETRY") return ["telemetry"];
  if (cmd === "GET_QC_STATUS") return ["qc"];
  // This command intentionally keeps the serial handler busy until the
  // firmware has emitted its bounded completion marker.  An immediate ACK
  // means only that it started; it is not safe to resume the 500 ms poll yet.
  if (cmd === "RUN_CURRENT_STATE_CHECK") return ["current-state-done"];
  return [`ack:${cmd}`];
}

function responseTimeoutMs(command) {
  // The current-state diagnostic probes ADS plus eight TCA branches without
  // changing sensor power or DAC.  It may take longer than an ordinary poll
  // on a slow I2C retry, so never classify it as a dead serial port at 5 s.
  return serialCommandName(command) === "RUN_CURRENT_STATE_CHECK"
    ? Math.max(SERIAL_RESPONSE_TIMEOUT_MS, 15000)
    : SERIAL_RESPONSE_TIMEOUT_MS;
}

function flushQueuedSerialCommand() {
  if (state.pendingSerialRequest || !serialCommandQueue.length) return;
  const next = serialCommandQueue.shift();
  // Keep commands serialized: a response can only satisfy the request that
  // produced it, never a later poll or click.
  queueMicrotask(() => sendCommand(next));
}

function recordSerialResponse(kind, ackCommand = "") {
  const pending = state.pendingSerialRequest;
  if (!pending) return;
  const response = kind === "ack" ? `ack:${ackCommand}` : kind;
  if (!pending.expected.includes(response)) return;
  clearSerialResponseWatch();
  resetSerialLiveness();
  flushQueuedSerialCommand();
}

export function startSerialResponseWatch(command) {
  clearSerialResponseWatch();
  const cmd = serialCommandName(command);
  const startedAt = Date.now();
  const timeoutMs = responseTimeoutMs(command);
  const timer = setTimeout(() => {
    if (!state.pendingSerialRequest || state.pendingSerialRequest.startedAt !== startedAt) return;
    appendLog(`NO_RESPONSE ${cmd} after ${timeoutMs}ms`, "in");
    setBadge(elements.protocolLabel, `${cmd}: no response`, "warn");
    state.pendingSerialRequest = null;
    consecutiveSerialTimeouts += 1;
    if (consecutiveSerialTimeouts < MAX_CONSECUTIVE_SERIAL_TIMEOUTS) {
      // Do exactly one liveness probe instead of resuming a high-rate poll.
      // A late response resets the counter and cancels this probe.
      setTimeout(() => {
        if (!state.connected || state.pendingSerialRequest || consecutiveSerialTimeouts !== 1) return;
        appendLog("SERIAL_LIVENESS_PROBE APP_PING after first timeout", "in");
        sendCommand("APP_PING");
      }, 250);
      flushQueuedSerialCommand();
      return;
    }
    if (recoveryRequested) return;

    recoveryRequested = true;
    stopPolling();
    appendLog("SERIAL_UNRESPONSIVE polling stopped; controlled reconnect requested", "in");
    setBadge(elements.connectionBadge, "GLD unresponsive; recovering...", "warn");
    window.dispatchEvent(new CustomEvent("gld-serial-unresponsive", {
      detail: { slot: state.activeSlot, command: cmd }
    }));
  }, timeoutMs);
  state.pendingSerialRequest = { cmd, startedAt, timer, expected: expectedResponses(cmd) };
  return startedAt;
}

function clearSerialResponseWatchIfStartedAt(startedAt) {
  if (state.pendingSerialRequest?.startedAt === startedAt) clearSerialResponseWatch();
}

// ---- device snapshot ----

export function resetDeviceSnapshot() {
  state.info = null;
  state.status = null;
  state.mode = "unknown";
  setText("deviceId", "Unknown");
  setText("currentChAddress", "Unknown");
  setText("modeValue", "Unknown");
  setText("firmwareValue", "Unknown");
  setText("gasValue", "n/a");
  setText("confidenceValue", "-%");
  setText("powerMode", "Unknown");
  setText("batteryValue", "Unknown");
  setText("loraValue", "Unknown");
  renderDetectedBoardProfile(null, null);
  updateAlarmState(false);
  // Do not leave GLD2-only module-power controls visible while a board is
  // disconnected or a different board (for example GLD1) is being selected.
  renderSensorPowerControls(null);
  // A disconnected or newly selected device must never inherit enabled alarm
  // controls from the preceding status snapshot.
  renderManualAlarmControls(null);
  renderControlAvailability(null, null);
  renderSensorCheck();
  resetQcStatus();
  syncDeviceSummary();
}

function updateInfo(info) {
  setText("deviceId", info.deviceId);
  setText("currentChAddress", info.targetChId);
  setText("modeValue", info.mode);
  setText("firmwareValue", info.firmwareVersion || info.firmwareName);
  setBadge(elements.protocolLabel, info.protocolVersion || "app serial", "ok");
  renderDetectedBoardProfile(info, state.status);
  syncLoraConfigFields(info.starLora);
  syncDeviceSummary();
  if (info.appConfig) {
    setField("wifiSsid", info.appConfig.wifiSsid || getField("wifiSsid"));
    setField("mqttHost", info.appConfig.mqttHost || getField("mqttHost"));
    setField("mqttPort", info.appConfig.mqttPort || getField("mqttPort"));
    setField("mqttUser", info.appConfig.mqttUser || getField("mqttUser"));
    setField("topicRoot", info.appConfig.topicRoot || getField("topicRoot"));
  }
}

function updateStatus(status) {
  setText("deviceId", status.deviceId || state.info?.deviceId);
  if (status.targetChId) setText("currentChAddress", status.targetChId);
  setText("modeValue", status.mode);
  renderDetectedBoardProfile(status, status);

  const telemetry = status.telemetry || {};
  setText("gasValue", telemetry.gasName || formatGas(telemetry.gasClass));
  setText("confidenceValue", Number.isFinite(telemetry.confidence) ? `${telemetry.confidence}%` : "-%");

  const alarm = Boolean(telemetry.alarm || status.alarm);
  updateAlarmState(alarm);

  const power = status.power || {};
  setText("powerMode", power.mode);
  // batteryValid is false whenever the GLD is on external 24V/5V power (no
  // battery sensed) - batteryMv is then a sentinel (65535), not a real
  // reading, so show "-" instead of that raw number.
  const batteryText = power.batteryValid && Number.isFinite(power.batteryMv) ? `${power.batteryMv} mV` : "-";
  setText("batteryValue", batteryText);
  renderEnvironment(status.environment);
  renderSensorPowerControls(status.sensorPower || status.pcf8574);
  confirmSensorPowerState(status.sensorPower || status.pcf8574);
  renderManualAlarmControls(status.alarmControl);
  renderControlAvailability(status.sensorPower || status.pcf8574, status.alarmControl);

  const model = status.model || {};
  const bindingStatus = $("modelNullingBindingStatus");
  if (bindingStatus) {
    const bound = Number(model.boundNullingProfileId);
    const active = Number(model.activeNullingProfileId);
    bindingStatus.textContent = model.bindingValid && model.bindingModelMatches
      ? `Model bound to Nulling profile #${bound}; active profile #${active}.`
      : `Model binding is not approved for active Nulling profile #${Number.isFinite(active) ? active : "?"}; inference remains fail-closed.`;
  }

  const lora = status.lora || {};
  const loraOk = lora.lastTxOk === true || lora.beginState === 0;
  setText("loraValue", loraOk ? "OK" : Number.isFinite(lora.beginState) ? `state ${lora.beginState}` : "Unknown");
  syncLoraConfigFields(lora);
  syncDeviceSummary();
  updateDatasetFromStatus(status);
  updateNullingMeta();
  renderSensorCheck();
  renderNullingChannels();
}

function maybeAppendTelemetry(status) {
  const telemetry = status.telemetry;
  if (!telemetry || !telemetry.valid || !Array.isArray(telemetry.sensorVoltage)) return;

  // GET_STATUS can arrive more often than the GLD completes an ADS scan. The
  // firmware's sampleMs is the scan identity; never turn repeated replies for
  // that same scan into artificial chart/history samples.
  const sampleMs = Number(telemetry.sampleMs);
  const previous = state.history.at(-1);
  if (Number.isFinite(sampleMs) && previous?.sampleMs === sampleMs) return;

  const ts = Date.now();
  state.history.push({
    ts,
    sampleMs: Number.isFinite(sampleMs) ? sampleMs : null,
    deviceId: status.deviceId || state.info?.deviceId || "",
    mode: status.mode || state.mode,
    gasName: telemetry.gasName || formatGas(telemetry.gasClass),
    gasClass: telemetry.gasClass,
    confidence: telemetry.confidence,
    alarm: Boolean(telemetry.alarm),
    sensorVoltage: telemetry.sensorVoltage.slice(0, 8),
    sensorGain: Array.isArray(telemetry.sensorGain) ? telemetry.sensorGain.slice(0, 8) : [],
    sensorStatus: Array.isArray(telemetry.sensorStatus) ? telemetry.sensorStatus.slice(0, 8) : [],
    featureOrder: Array.isArray(telemetry.featureOrder) ? telemetry.featureOrder.slice(0, 8) : []
  });
  pruneHistory();
  updateTelemetryCollectionProgress();
  drawChart();
  drawQcCharts();
  maybeCaptureDatasetTelemetry(status);
}

// ---- alarm ----

export function updateAlarmState(alarm) {
  state.alarmActive = alarm;
  if (alarm && !state.alarmMuted) playAlarmBeep();
}

export function toggleAlarmMute() {
  state.alarmMuted = !state.alarmMuted;
  updateAlarmState(state.alarmActive);
}

function playAlarmBeep() {
  const now = Date.now();
  if (now - state.alarmLastBeep < 1800) return;
  state.alarmLastBeep = now;
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    const context = state.alarmAudioContext || new AudioContextClass();
    state.alarmAudioContext = context;
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = "square";
    oscillator.frequency.value = 880;
    gain.gain.setValueAtTime(0.0001, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.08, context.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.22);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.24);
  } catch (error) {
    appendLog(`ALARM_SOUND_ERROR ${error.message}`, "in");
  }
}

// ---- boot diagnostics ----

function bootTone(ok, known = true) {
  if (!known) return "idle";
  return ok ? "pass" : "fail";
}

function bootToneFromStatus(statusText) {
  const text = String(statusText || "").toUpperCase();
  if (text.includes("NOT OK") || text.includes("FAIL") || text.includes("BLOCKED")) return "fail";
  if (text.includes("OK") || text.includes("PASS") || text.includes("READY")) return "pass";
  return "active";
}

function bootTableKey(name) {
  const text = String(name || "").toUpperCase();
  if (text.includes("ADS")) return "ads";
  if (text.includes("TCA") || text.includes("I2C")) return "i2c";
  if (text.includes("MCP")) return "mcp";
  if (text.includes("DAC")) return "dac";
  if (text.includes("LORA") || text.includes("RADIO")) return "lora";
  if (text.includes("ML") || text.includes("MODEL")) return "ml";
  if (text.includes("MODE")) return "mode";
  if (text.includes("POWER")) return "power";
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "-") || "boot";
}

function setBootProbe(key, patch) {
  state.bootDiagnostics.probes[key] = {
    key,
    ...(state.bootDiagnostics.probes[key] || {}),
    ...patch,
    updatedAt: Date.now()
  };
}

function parsePairs(text) {
  const pairs = {};
  for (const match of String(text || "").matchAll(/([A-Za-z][A-Za-z0-9_]*)=([^ ]+)/g)) {
    pairs[match[1]] = match[2];
  }
  return pairs;
}

function optionalBool(value) {
  if (value === true || value === 1 || value === "1" || value === "true") return true;
  if (value === false || value === 0 || value === "0" || value === "false") return false;
  return undefined;
}

function boolArrayItem(values, index) {
  return Array.isArray(values) && index < values.length ? optionalBool(values[index]) : undefined;
}

function parseBootDiagnosticLine(line) {
  state.bootDiagnostics.lastLine = line;
  if (line === "[BOOT_IC_REPORT]") {
    state.bootDiagnostics.reportSeen = true;
    renderBootDiagnostics();
    return;
  }

  if (line.startsWith("|")) {
    const parts = line.split("|").map((part) => part.trim()).filter(Boolean);
    if (parts.length >= 4 && parts[0] !== "IC/Fungsi" && !parts[0].startsWith("-")) {
      const key = bootTableKey(parts[0]);
      state.bootDiagnostics.bootRows[key] = {
        key,
        label: parts[0],
        check: parts[1],
        status: parts[2],
        stage: parts[2],
        detail: parts.slice(3).join(" | "),
        tone: bootToneFromStatus(parts[2])
      };
      renderBootDiagnostics();
    }
    return;
  }

  const adsBegin = /^ADS_BEGIN_RESULT=(PASS|FAIL)/.exec(line);
  if (adsBegin) {
    setBootProbe("ads", {
      label: "ADS1256",
      stage: adsBegin[1] === "PASS" ? "OK" : "Fail",
      tone: adsBegin[1] === "PASS" ? "pass" : "fail",
      detail: adsBegin[1] === "PASS"
        ? "ADS SPI begin passed"
        : "ADS SPI begin failed; check ADS power, SPI pins, CS, DRDY, SYNC, and board profile"
    });
    renderBootDiagnostics();
    return;
  }

  if (line.startsWith("BOOT_PROBE_ADS=done")) {
    const pairs = parsePairs(line);
    const ok = pairs.adsReady === "1";
    setBootProbe("ads", {
      label: "ADS1256",
      stage: ok ? "OK" : "Fail",
      tone: bootTone(ok),
      detail: ok
        ? `DRDY ${pairs.drdy ?? "?"}, status ${pairs.status ?? "?"}, mux ${pairs.mux ?? "?"}, drate ${pairs.drate ?? "?"}`
        : `ADS not ready (${pairs.reason ?? "unknown"}); DRDY ${pairs.drdy ?? "?"}, pull ${pairs.pd ?? "?"}/${pairs.pu ?? "?"}, MISO pull ${pairs.misoPD ?? "?"}/${pairs.misoPU ?? "?"}, status ${pairs.status ?? "?"}. Check ADS power/reference/clock/SPI/CS/DRDY/SYNC`
    });
    renderBootDiagnostics();
    return;
  }

  if (line.startsWith("BOOT_PROBE_I2C=done")) {
    const pairs = parsePairs(line);
    const ok = pairs.tcaOk === "1";
    const mcp = pairs.mcpOkCount || "?/8";
    setBootProbe("i2c", {
      label: "I2C/TCA9548A",
      stage: ok ? "OK" : "Fail",
      tone: bootTone(ok),
      detail: ok
        ? `TCA OK, MCP ${mcp}`
        : `TCA not responding; check SDA/SCL, 3V3, GND, TCA address, or stuck I2C bus`
    });
    setBootProbe("mcp", {
      label: "MCP4725 Mux",
      stage: mcp === "8/8" ? "OK" : "Diagnostic",
      tone: mcp === "8/8" ? "pass" : "active",
      detail: mcp === "8/8"
        ? "MCP detected on all 8 TCA channels"
        : `Boot ACK diagnostic ${mcp}${pairs.mcpMask ? `, mask ${pairs.mcpMask}` : ""}; current DAC-control status decides operational readiness`
    });
    renderBootDiagnostics();
    return;
  }

  if (line.startsWith("BOOT_PROBE_MCP_CONTROL=done")) {
    const pairs = parsePairs(line);
    const ok = pairs.dacReady === "1" && pairs.writeOkCount === "8/8";
    setBootProbe("dac", {
      label: "DAC Control",
      stage: ok ? "OK" : "Fail",
      tone: bootTone(ok),
      detail: ok
        ? "DAC write low/high passed on all channels"
        : `DAC ready ${pairs.dacReady ?? "?"}, write ${pairs.writeOkCount ?? "?"}${pairs.writeMask ? `, mask ${pairs.writeMask}` : ""}; check DAC mux, MCP4725 control wiring, and external power`
    });
    renderBootDiagnostics();
    return;
  }

  const loraBegin = /^GLD_STAR_BEGIN_STATE=(-?\d+)/.exec(line);
  if (loraBegin) {
    const ok = Number(loraBegin[1]) === 0;
    setBootProbe("lora", {
      label: "LoRa",
      stage: ok ? "OK" : "Fail",
      tone: bootTone(ok),
      detail: ok ? "SX1262 begin passed" : `RadioLib state ${loraBegin[1]}; check LoRa SPI, CS, DIO1, RST, BUSY, TCXO/XTAL`
    });
    renderBootDiagnostics();
    return;
  }

  const mlInit = /^GLD_ML_INIT initialized=(\d+) outputSize=(-?\d+)/.exec(line);
  if (mlInit) {
    const ok = mlInit[1] === "1";
    setBootProbe("ml", {
      label: "ML Model",
      stage: ok ? "OK" : "Fail",
      tone: bootTone(ok),
      detail: ok ? `Output size ${mlInit[2]}` : "ML model did not initialize; check model data and PSRAM"
    });
    renderBootDiagnostics();
    return;
  }

  const sensorBlocked = /^BOOT_SENSOR_SAMPLE_BLOCKED reason=(.+)/.exec(line);
  if (sensorBlocked) {
    setBootProbe("sensor", {
      label: "Sensor Read",
      stage: "Blocked",
      tone: "fail",
      detail: `Sensor sample blocked: ${sensorBlocked[1]}`
    });
    renderBootDiagnostics();
  }
}

function statusBootCard(key, label, stage, tone, detail) {
  return { key, label, stage, tone, detail };
}

function bootCardsFromCurrentState() {
  const boot = state.status?.bootHealth || {};
  const telemetry = state.status?.telemetry || {};
  const lora = state.status?.lora || {};
  const probes = state.bootDiagnostics.probes;
  const rows = state.bootDiagnostics.bootRows;

  const cards = [];
  const adsKnown = boot.adsReady === true || boot.adsReady === false;
  cards.push(probes.ads || rows.ads || statusBootCard(
    "ads",
    "ADS1256",
    adsKnown ? (boot.adsReady ? "OK" : "Fail") : "Unknown",
    bootTone(boot.adsReady === true, adsKnown),
    adsKnown
      ? (boot.adsReady
        ? `ADS ready; status 0x${Number(boot.adsStatus || 0).toString(16).padStart(2, "0")}`
        : `ADS not ready${boot.adsReason ? ` (${boot.adsReason})` : ""}; DRDY ${boot.adsDrdyLevel ?? "?"}, pull ${boot.adsDrdyPulldownLevel ?? "?"}/${boot.adsDrdyPullupLevel ?? "?"}, MISO pull ${boot.adsMisoPulldownLevel ?? "?"}/${boot.adsMisoPullupLevel ?? "?"}, status 0x${Number(boot.adsStatus || 0).toString(16).padStart(2, "0")}`)
      : "Waiting for ADS boot evidence"
  ));

  const mcpOkArray = Array.isArray(boot.mcpOk) ? boot.mcpOk : null;
  const mcpKnown = Number.isFinite(Number(boot.mcpOkCount)) || Boolean(mcpOkArray);
  const mcpCount = mcpOkArray ? mcpOkArray.filter((v) => optionalBool(v) === true).length : Number(boot.mcpOkCount);
  const mcpAllOk = Number.isFinite(mcpCount) && mcpCount >= 8;
  const mcpControlOkArray = boot.mcpControlTested === true && Array.isArray(boot.mcpControlOk) ? boot.mcpControlOk : null;
  const mcpControlKnown = boot.mcpControlTested === true || Boolean(mcpControlOkArray);
  const mcpControlCount = mcpControlOkArray ? mcpControlOkArray.filter((v) => optionalBool(v) === true).length : NaN;
  const mcpOperationalOk = mcpControlKnown && Number.isFinite(mcpControlCount) && mcpControlCount >= 8;
  const mcpStatusCard = statusBootCard(
    "mcp",
    "MCP4725 Mux",
    mcpOperationalOk ? "OK" : mcpKnown ? (mcpAllOk ? "OK" : `${Number.isFinite(mcpCount) ? mcpCount : "?"}/8`) : "Unknown",
    mcpOperationalOk ? "pass" : mcpKnown ? (mcpAllOk ? "pass" : "active") : "idle",
    mcpOperationalOk
      ? `DAC control passed ${mcpControlCount}/8; boot ACK diagnostic ${Number.isFinite(mcpCount) ? `${mcpCount}/8` : "unknown"}`
      : mcpKnown
        ? (mcpAllOk ? "MCP detected on all 8 TCA channels" : `Boot ACK diagnostic ${Number.isFinite(mcpCount) ? mcpCount : "?"}/8; DAC-control result is pending or failed`)
        : "Waiting for I2C boot evidence"
  );
  cards.push(mcpOperationalOk ? mcpStatusCard : (probes.mcp || rows.mcp || mcpStatusCard));

  const dacKnown = boot.dacReady === true || boot.dacReady === false || mcpControlKnown;
  const dacAllOk = mcpControlKnown ? Number.isFinite(mcpControlCount) && mcpControlCount >= 8 : boot.dacReady === true;
  cards.push(probes.dac || rows.dac || statusBootCard(
    "dac",
    "DAC Control",
    dacKnown ? (dacAllOk ? "OK" : "Fail") : "Unknown",
    bootTone(dacAllOk, dacKnown),
    mcpControlKnown
      ? (dacAllOk ? "DAC write passed on all channels" : `DAC ready ${boot.dacReady ? "yes" : "no"}; write passed ${mcpControlCount}/8`)
      : dacKnown ? (boot.dacReady ? "DAC ready" : "DAC not ready; check MCP4725/TCA/external power") : "Waiting for DAC evidence"
  ));

  const loraKnown = boot.radioReady === true || boot.radioReady === false || Number.isFinite(lora.beginState);
  const loraOk = boot.radioReady === true || lora.beginState === 0;
  cards.push(probes.lora || rows.lora || statusBootCard(
    "lora",
    "LoRa",
    loraKnown ? (loraOk ? "OK" : "Fail") : "Unknown",
    bootTone(loraOk, loraKnown),
    loraKnown ? (loraOk ? "Radio ready" : `Radio not ready${Number.isFinite(lora.beginState) ? `, state ${lora.beginState}` : ""}`) : "Waiting for LoRa evidence"
  ));

  const mlKnown = boot.mlReady === true || boot.mlReady === false;
  cards.push(probes.ml || rows.ml || statusBootCard(
    "ml",
    "ML Model",
    mlKnown ? (boot.mlReady ? "OK" : "Fail") : "Unknown",
    bootTone(boot.mlReady === true, mlKnown),
    mlKnown ? (boot.mlReady ? "ML ready" : "ML not ready; check model artifact and PSRAM") : "Waiting for ML evidence"
  ));

  const sensorOk = telemetry.valid === true
    && Array.isArray(telemetry.sensorStatus)
    && telemetry.sensorStatus.length >= 8
    && telemetry.sensorStatus.every((value) => Number(value) === 0);
  const sensorKnown = telemetry.valid === true || Boolean(probes.sensor) || boot.adsReady === false || (mcpKnown && !mcpAllOk);
  cards.push(probes.sensor || statusBootCard(
    "sensor",
    "Sensor Read",
    sensorKnown ? (sensorOk ? "OK" : "Blocked") : "Unknown",
    sensorKnown ? (sensorOk ? "pass" : "fail") : "idle",
    sensorKnown ? (sensorOk ? "All 8 sensor readings valid" : "Sensor readings blocked until ADS and MCP boot health are OK") : "Waiting for live telemetry"
  ));

  return cards;
}

function renderBootDiagnostics() {
  if (!elements.bootReportGrid || !elements.bootReportSummary) return;
  const cards = bootCardsFromCurrentState();
  const pass = cards.filter((card) => card.tone === "pass").length;
  const fail = cards.filter((card) => card.tone === "fail").length;
  const check = cards.filter((card) => card.tone === "active").length;
  elements.bootReportSummary.textContent = fail
    ? `${fail} boot ${fail === 1 ? "item" : "items"} not OK.`
    : pass === cards.length ? "All boot items look OK." : `${pass}/${cards.length} boot items OK${check ? `, ${check} need check` : ""}.`;
  elements.bootReportGrid.innerHTML = "";

  for (const item of cards) {
    const card = document.createElement("article");
    card.className = `channel-card ${item.tone}`.trim();
    const head = document.createElement("div");
    head.className = "channel-card-head";
    const title = document.createElement("strong");
    title.textContent = item.label;
    const key = document.createElement("span");
    key.textContent = item.key.toUpperCase();
    head.append(title, key);
    const stage = document.createElement("span");
    stage.className = "channel-stage";
    stage.textContent = item.stage;
    const detail = document.createElement("small");
    detail.textContent = item.detail;
    card.append(head, stage, detail);
    elements.bootReportGrid.append(card);
  }
}

// ---- sensor check ----

export function sensorPresenceFromStatus(status = state.status) {
  const telemetry = status?.telemetry || {};
  const boot = status?.bootHealth || {};
  const featureOrder = Array.isArray(telemetry.featureOrder) && telemetry.featureOrder.length
    ? telemetry.featureOrder
    : latestFeatureOrderForNulling();
  const voltages = Array.isArray(telemetry.sensorVoltage) ? telemetry.sensorVoltage : [];
  const gains = Array.isArray(telemetry.sensorGain) ? telemetry.sensorGain : [];
  const statuses = Array.isArray(telemetry.sensorStatus) ? telemetry.sensorStatus : [];
  const explicit = boot.sensorPresent || boot.mqPresent || boot.sensorInstalled || status?.sensorPresent;
  const health = boot.sensorHealth || boot.mqHealth || status?.sensorHealth;
  const adsReady = boot.adsReady === true;
  const adsKnown = boot.adsReady === true || boot.adsReady === false;
  const mcpOkCount = Number(boot.mcpOkCount);
  const mcpOkArray = Array.isArray(boot.mcpOk) ? boot.mcpOk : null;
  const mcpAddrMaskArray = Array.isArray(boot.mcpAddrMask) ? boot.mcpAddrMask : null;
  const mcpControlOkArray = boot.mcpControlTested === true && Array.isArray(boot.mcpControlOk)
    ? boot.mcpControlOk
    : null;

  return Array.from({ length: 8 }, (_, index) => {
    const sensor = featureOrder[index] || SENSOR_NAMES[index] || `CH${index + 1}`;
    const muxChannel = SENSOR_MUX_CHANNELS[index] ?? "?";
    const voltage = voltages[index];
    const gain = gains[index];
    const explicitValue = Array.isArray(explicit) ? explicit[index] : undefined;
    const healthValue = Array.isArray(health) ? health[index] : undefined;
    const adsStatus = statuses[index];
    const mcpOk = boolArrayItem(mcpOkArray, index);
    const mcpAddrMask = Array.isArray(mcpAddrMaskArray) ? Number(mcpAddrMaskArray[index]) : NaN;
    const mcpControlOk = boolArrayItem(mcpControlOkArray, index);
    const adsStatusNumber = Number(adsStatus);
    const adsStatusName = SENSOR_STATUS_NAMES[adsStatusNumber] || (adsStatus == null ? "" : `Status ${adsStatus}`);
    const voltageNumber = Number(voltage);
    const hasVoltage = Number.isFinite(voltageNumber);
    const hasGain = gain != null && gain !== "";
    let showReading = telemetry.valid === true;

    let stage = "Unknown";
    let tone = "idle";
    let detail = "Waiting for GET_STATUS telemetry";

    if (explicitValue === false || explicitValue === 0 || healthValue === "missing") {
      stage = "Missing";
      tone = "fail";
      detail = "Firmware reports sensor not installed";
      showReading = false;
    } else if (healthValue === "fault" || healthValue === "error") {
      stage = "Fault";
      tone = "fail";
      detail = "Firmware reports sensor fault";
      showReading = false;
    } else if (state.status?.sensorPower?.available === true && state.status.sensorPower?.ready === true &&
               state.status.sensorPower?.channels?.[index] === false) {
      stage = "Power Off";
      tone = "active";
      detail = "Module sensor sedang OFF; current-state check tidak mengubah EN";
      showReading = false;
    } else if (mcpControlOk === true && mcpOk === false) {
      stage = telemetry.valid === true && adsStatusNumber === 0 ? "Present" : "DAC Verified";
      tone = telemetry.valid === true && adsStatusNumber === 0 ? "pass" : "active";
      detail = `DAC control verified; boot ACK diagnostic has no 0x60 on TCA mux ${muxChannel}`;
      showReading = telemetry.valid === true && adsStatusNumber === 0 && (hasVoltage || hasGain);
    } else if (mcpOk === false) {
      stage = "MCP Not OK";
      tone = "fail";
      detail = Number.isFinite(mcpAddrMask) && mcpAddrMask > 0
        ? `MCP4725 not at 0x60 on TCA mux ${muxChannel}; addr mask 0x${mcpAddrMask.toString(16).padStart(2, "0")}`
        : `No MCP4725 ACK on TCA mux ${muxChannel}`;
      showReading = false;
    } else if (mcpControlOk === false) {
      stage = "DAC Fault";
      tone = "fail";
      detail = `MCP4725 ACK/write failed on TCA mux ${muxChannel}`;
      showReading = false;
    } else if (adsKnown && !adsReady) {
      stage = "ADS Blocked";
      tone = "active";
      detail = `MCP path ${mcpOk === true ? "OK" : "unknown"}; waiting for ADS1256 ready`;
      showReading = false;
    } else if (telemetry.valid === true && adsStatusNumber === 0) {
      stage = "Present";
      tone = "pass";
      detail = "ADS1256 status OK";
      showReading = hasVoltage || hasGain;
    } else if (telemetry.valid === true && adsStatusNumber === 1) {
      stage = "Not Ready";
      tone = "active";
      detail = "ADS1256 channel not ready";
      showReading = false;
    } else if (telemetry.valid === true && adsStatusNumber === 2) {
      stage = "Fault";
      tone = "fail";
      detail = "ADS1256 DRDY timeout";
      showReading = false;
    } else if (telemetry.valid === true && adsStatusNumber === 3) {
      stage = "Fault";
      tone = "fail";
      detail = "Invalid ADS1256 channel";
      showReading = false;
    } else if (explicitValue === true || explicitValue === 1 || healthValue === "ok" || healthValue === "present") {
      stage = "Present";
      tone = "pass";
      detail = "Firmware reports sensor present";
      showReading = hasVoltage || hasGain;
    } else if (telemetry.valid === true && hasVoltage && hasGain && adsReady) {
      stage = "Present";
      tone = "pass";
      detail = "Voltage and gain are readable";
    } else if (telemetry.valid === true && hasVoltage && !adsReady) {
      stage = "Read Only";
      tone = "active";
      detail = "Voltage seen, ADS health not ready";
    } else if (!mcpOkArray && Number.isFinite(mcpOkCount) && mcpOkCount < index + 1) {
      stage = "Check";
      tone = "active";
      detail = "MCP ready count is below this channel";
    }

    const adsEvidence = telemetry.valid === true
      ? `ADS AIN${index}: ${adsStatusName || "status tidak tersedia"}`
      : `ADS AIN${index}: belum ada telemetry`;
    const mcpBootEvidence = mcpOk === true
      ? "boot ACK 0x60"
      : mcpOk === false ? "boot tidak ACK 0x60" : "boot ACK tidak tersedia";
    const mcpControlEvidence = mcpControlOk === true
      ? "DAC control OK"
      : mcpControlOk === false ? "DAC control gagal" : "DAC control belum diuji";

    return {
      index,
      sensor,
      stage,
      tone,
      detail: adsStatusName && telemetry.valid === true ? `${detail} (${adsStatusName})` : detail,
      adsEvidence,
      mcpEvidence: `MCP/TCA mux ${muxChannel}: ${mcpBootEvidence}; ${mcpControlEvidence}`,
      voltage: showReading && hasVoltage ? voltageNumber.toFixed(6) : "",
      gain: showReading && hasGain ? String(gain) : ""
    };
  });
}

export function renderSensorCheck() {
  const channels = sensorPresenceFromStatus();
  const present = channels.filter((channel) => channel.tone === "pass").length;
  const fail = channels.filter((channel) => channel.tone === "fail").length;
  const check = channels.filter((channel) => channel.tone === "active").length;
  const boot = state.status?.bootHealth || {};
  const telemetry = state.status?.telemetry || {};

  elements.sensorCheckSummary.textContent = fail
    ? `${fail} MQ sensor ${fail === 1 ? "channel needs" : "channels need"} attention.`
    : present === 8 ? "All 8 MQ sensor channels look present." : `${present}/8 MQ sensor channels confirmed.`;
  const adsReason = boot.adsReason ? ` (${boot.adsReason})` : "";
  const mcpControlCount = boot.mcpControlTested === true && Array.isArray(boot.mcpControlOk)
    ? boot.mcpControlOk.filter((value) => optionalBool(value) === true).length
    : NaN;
  const mcpControlText = Number.isFinite(mcpControlCount) ? `DAC control ${mcpControlCount}/8` : "DAC control unknown";
  const mcpBootText = Number.isFinite(boot.mcpOkCount) ? `boot ACK ${boot.mcpOkCount}/8` : "boot ACK unknown";
  elements.sensorCheckMeta.textContent = `ADS: ${boot.adsReady === true ? "Ready" : boot.adsReady === false ? `Not ready${adsReason}` : "Unknown"} - MCP: ${mcpControlText} (${mcpBootText}) - Latest telemetry: ${telemetry.valid ? "valid" : "none"}${check ? ` - Check ${check}` : ""}`;
  renderBootDiagnostics();
  elements.sensorCheckChannels.innerHTML = "";

  for (const channel of channels) {
    const card = document.createElement("article");
    card.className = `channel-card ${channel.tone}`.trim();

    const head = document.createElement("div");
    head.className = "channel-card-head";
    const title = document.createElement("strong");
    title.textContent = `CH${channel.index + 1}`;
    const sensor = document.createElement("span");
    sensor.textContent = channel.sensor;
    head.append(title, sensor);

    const stage = document.createElement("span");
    stage.className = "channel-stage";
    stage.textContent = channel.stage;

    const detail = document.createElement("small");
    detail.textContent = channel.detail;

    const extra = document.createElement("small");
    extra.textContent = [channel.voltage ? `V ${channel.voltage}` : "", channel.gain ? `gain ${channel.gain}` : ""].filter(Boolean).join(" - ") || "No live reading";

    const ads = document.createElement("small");
    ads.textContent = channel.adsEvidence;
    const mcp = document.createElement("small");
    mcp.textContent = channel.mcpEvidence;

    card.append(head, stage, ads, mcp, detail, extra);
    elements.sensorCheckChannels.append(card);
  }

  renderSensorChannels(channels);
}

// PGA gain steps the ADS1256 reader actually cycles through (see
// PGA_VALUE_TABLE in firmware/gld/src/GldAds1256Reader.cpp) - the value the
// GLD reports in telemetry.sensorGain is already one of these, not an index.
const GAIN_STEPS = [1, 2, 4, 8, 16, 32, 64];
const SENSOR_TREND_WINDOW_MS = 60 * 1000;
const SENSOR_TREND_MIN_SPAN_MS = 5 * 1000;
const SENSOR_STABILITY_BASELINE_WINDOW_MS = 10 * 60 * 1000;
const SENSOR_STABILITY_MIN_WINDOWS = 5;
const SENSOR_STABILITY_MIN_DRIFT_MV_PER_MIN = 0.5;
const SENSOR_STABILITY_MIN_RANGE_MV = 0.5;
const SENSOR_STABILITY_BASELINE_MULTIPLIER = 2;
const SESSION_MCP_CODE_MIN = 0;
const SESSION_MCP_CODE_MAX = 4095;
const sessionMcpExpanded = new Set();
const sessionMcpOverrides = new Map();
const sessionMcpApplying = new Set();

export function updateTelemetryCollectionProgress() {
  if (!elements.telemetryMinuteProgress || !elements.telemetryBaselineProgress) return;
  const completeSamples = state.history.filter((sample) => (
    Array.isArray(sample.sensorVoltage)
    && sample.sensorVoltage.length >= 8
    && sample.sensorVoltage.every((value) => Number.isFinite(Number(value)))
  ));
  const elapsedMs = completeSamples.length > 1
    ? completeSamples[completeSamples.length - 1].ts - completeSamples[0].ts
    : 0;
  const minutePercent = Math.min(100, Math.floor((elapsedMs / SENSOR_TREND_WINDOW_MS) * 100));
  const baselineDurationMs = SENSOR_TREND_WINDOW_MS * (SENSOR_STABILITY_MIN_WINDOWS + 1);
  const baselinePercent = Math.min(100, Math.floor((elapsedMs / baselineDurationMs) * 100));

  elements.telemetryMinuteProgress.value = minutePercent;
  elements.telemetryMinuteProgressValue.textContent = `${minutePercent}%`;
  elements.telemetryBaselineProgress.value = baselinePercent;
  elements.telemetryBaselineProgressValue.textContent = `${baselinePercent}%`;
}

function updateLightweightTelemetry(message) {
  // Preserve the last complete snapshot: a lightweight poll intentionally has
  // no power, boot, LoRa, nulling, or NVS fields to avoid serial overhead.
  const telemetryPower = message.sensorPower;
  const telemetryPowerComplete = telemetryPower?.available !== true || (
    Array.isArray(telemetryPower?.channels) && telemetryPower.channels.length === 8 &&
    Array.isArray(telemetryPower?.enChannels) && telemetryPower.enChannels.length === 8
  );
  const status = {
    ...(state.status || {}),
    deviceId: message.deviceId || state.status?.deviceId || state.info?.deviceId,
    mode: message.mode || state.mode,
    uptimeMs: message.uptimeMs,
    alarmLatched: message.alarmLatched ?? state.status?.alarmLatched,
    model: { ...(state.status?.model || {}), ...(message.model || {}) },
    environment: message.environment || state.status?.environment,
    // A truncated serial JSON line used to contain outputMask plus only the
    // first six channel entries. Never let such partial data replace a prior
    // complete GET_STATUS snapshot and falsely render MQ6/MQ2 as OFF.
    sensorPower: telemetryPowerComplete ? telemetryPower : state.status?.sensorPower,
    telemetry: message.telemetry
  };
  state.status = status;
  state.mode = status.mode || state.mode;
  updateStatus(status);
  maybeAppendTelemetry(status);
}

function renderEnvironment(environment) {
  const readout = $("environmentReadout");
  const temperature = $("environmentTemperature");
  const humidity = $("environmentHumidity");
  const tcaIndicators = [$("environmentTca"), $("nullingTcaIndicator")].filter(Boolean);
  if (!readout || !temperature || !humidity) return;

  const available = environment?.available === true;
  const detected = environment?.detected === true;
  const valid = environment?.valid === true;
  const tempC = Number(environment?.temperatureC);
  const rh = Number(environment?.relativeHumidityPct);
  const sampleAgeMs = Number(environment?.sampleAgeMs);
  const hasReading = available && detected && valid && Number.isFinite(tempC) && Number.isFinite(rh);

  readout.classList.toggle("is-ready", hasReading);
  readout.classList.toggle("is-waiting", available && !hasReading);
  if (hasReading) {
    const age = Number.isFinite(sampleAgeMs) && sampleAgeMs >= 0 ? ` · ${sampleAgeMs} ms` : "";
    temperature.textContent = `Suhu ${tempC.toFixed(1)} °C${age}`;
    humidity.textContent = `RH ${rh.toFixed(1)} %`;
  } else if (available && !detected) {
    temperature.textContent = "Suhu sensor tidak terdeteksi";
    humidity.textContent = "RH —";
  } else {
    temperature.textContent = "Suhu —";
    humidity.textContent = available ? "RH membaca…" : "RH —";
  }

  const tcaStatus = environment?.tca9548a;
  const tcaAddress = tcaStatus?.address || "0x71";
  const tcaDetected = tcaStatus?.detected === true;
  const tcaKnown = typeof tcaStatus?.detected === "boolean";
  const tcaAgeMs = Number(tcaStatus?.sampleAgeMs);
  const tcaFresh = Number.isFinite(tcaAgeMs) && tcaAgeMs >= 0 && tcaAgeMs <= 1500;
  const tcaOnline = tcaKnown && tcaDetected && tcaFresh;
  const tcaSpinner = tcaOnline ? TCA_ONLINE_SPINNER[tcaOnlineSpinnerIndex++ % TCA_ONLINE_SPINNER.length] : "";
  for (const tca of tcaIndicators) {
    tca.classList.toggle("is-online", tcaOnline);
    tca.classList.toggle("is-offline", tcaKnown && (!tcaDetected || !tcaFresh));
    tca.classList.toggle("is-unknown", !tcaKnown);
    const tcaLabel = tca.querySelector("span:last-child");
    if (tcaLabel) {
      tcaLabel.textContent = !tcaKnown
        ? `TCA9548A · ${tcaAddress}: menunggu telemetry firmware`
        : tcaOnline
          ? `TCA9548A · ${tcaAddress}: online · ${tcaSpinner}`
          : !tcaDetected
            ? `TCA9548A · ${tcaAddress}: tidak ACK`
            : `TCA9548A · ${tcaAddress}: status ACK basi`;
    }
  }
}

function renderDetectedBoardProfile(snapshot, status) {
  const badge = $("detectedBoardProfile");
  if (!badge) return;

  const boardProfile = String(snapshot?.boardProfile || state.info?.boardProfile || "");
  const sensorPower = status?.sensorPower || status?.pcf8574;
  const hasPcf = sensorPower?.available === true;
  const profileKnown = boardProfile.length > 0;
  const isGld2 = hasPcf || /GLD2/i.test(boardProfile);

  badge.textContent = !profileKnown && !hasPcf
    ? "Board: menunggu"
    : isGld2
      ? "Board: GLD2 · PCF8574"
      : "Board: GLD1";
  badge.className = `tag sensor-board-profile ${isGld2 || profileKnown ? "tag--ok" : "tag--warn"}`;
  badge.title = profileKnown
    ? `Profil firmware: ${boardProfile}`
    : isGld2
      ? "Terdeteksi dari capability PCF8574 pada firmware."
      : "Menunggu profil board dari firmware.";
}

function renderSensorPowerControls(sensorPower) {
  const status = $("sensorPowerStatus");
  if (!status) return;

  const available = sensorPower?.available === true;
  const ready = sensorPower?.ready === true;
  const outputs = Number(sensorPower?.outputMask ?? sensorPower?.outputs);
  const channels = Array.isArray(sensorPower?.channels) ? sensorPower.channels : null;
  const enChannels = Array.isArray(sensorPower?.enChannels) ? sensorPower.enChannels : null;
  const validOutputs = Number.isInteger(outputs) && outputs >= 0 && outputs <= 0xFF;
  // Module-power switching is a GLD2 hardware capability (PCF8574 driving
  // EN0–EN7), not a degraded GLD1 feature. Keep the Running flow clean on
  // GLD1: no inactive ON/OFF controls or PCF warning. They appear only after
  // the connected firmware positively reports this capability.
  for (const id of ["sensorPowerAllOnBtn", "sensorPowerAllOffBtn", "sensorPowerStatus"]) {
    const element = $(id);
    if (element) element.hidden = !available;
  }
  $("sensorPowerAllOnBtn").disabled = sensorPowerApplyPending || !available || !ready;
  $("sensorPowerAllOffBtn").disabled = sensorPowerApplyPending || !available || !ready;
  status.textContent = !available
    ? "Kontrol ini hanya tersedia pada board profile GLD2 (PCF8574 EN0–EN7)."
    : !ready
      ? "PCF8574 tidak merespons; perubahan power diblokir. Periksa I2C dan supply 3V3."
      : "Status ini adalah perintah PCF8574 yang tersinkron setelah setiap perubahan EN; bukan pembuktian tegangan +5 V fisik pada modul.";

}

function renderControlAvailability(sensorPower, alarmControl) {
  const indicator = $("controlAvailability");
  if (!indicator) return;

  const sensorPowerAvailable = sensorPower?.available === true;
  const sensorPowerReady = sensorPower?.ready === true;
  const alarm = alarmControlContract(alarmControl);
  const profile = String(state.info?.boardProfile || "");
  const board = sensorPowerAvailable || /GLD2/i.test(profile)
    ? "GLD2"
    : profile ? "GLD1" : "Board";
  const parts = [board];
  if (sensorPowerAvailable) {
    parts.push(sensorPowerReady ? "Daya: PCF siap" : "Daya: PCF tidak siap");
  }
  parts.push(!alarm.available
    ? "Alarm: menunggu"
    : alarm.legacyManualOnly
      ? "Alarm: LEGACY MANUAL"
      : `Alarm: ${alarm.mode === "manual" ? "MANUAL TEST" : "AUTO"}`);
  indicator.textContent = parts.join(" · ");
  indicator.className = `tag ${alarm.available && (!sensorPowerAvailable || sensorPowerReady) ? "tag--ok" : "tag--warn"}`;
}

function alarmControlContract(alarmControl) {
  const hasExplicitMode = alarmControl?.mode === "auto" || alarmControl?.mode === "manual";
  // GLD2 firmware before the AUTO/MANUAL contract reported only
  // {manualOnly:true, manualCommanded:<bool>}. Keep its already-implemented
  // SET_MANUAL_ALARM_JSON path usable, but never infer support for the newer
  // SET_ALARM_MODE_JSON command from manualOnly alone.
  const legacyManualOnly = !hasExplicitMode && alarmControl?.manualOnly === true;
  const available = alarmControl?.available === true ||
    (legacyManualOnly && alarmControl?.available !== false);
  const mode = hasExplicitMode
    ? alarmControl.mode
    : legacyManualOnly ? "manual" : "auto";
  const manualOutputAllowed = available && (legacyManualOnly || mode === "manual");
  return { hasExplicitMode, legacyManualOnly, available, mode, manualOutputAllowed };
}

function renderManualAlarmControls(alarmControl) {
  const on = $("manualAlarmOnBtn");
  const off = $("manualAlarmOffBtn");
  const modeSelect = $("alarmModeSelect");
  const modeApply = $("alarmModeApplyBtn");
  const status = $("alarmControlStatus");
  if (!on || !off || !modeSelect || !modeApply) return;

  const contract = alarmControlContract(alarmControl);
  const { hasExplicitMode, legacyManualOnly, available, mode, manualOutputAllowed } = contract;
  const commanded = alarmControl?.manualCommanded === true;
  const inferenceAlarm = alarmControl?.inferenceAlarm === true;
  const outputDescription = alarmControl?.outputDrive === "active_low_lamp_buzzer_led"
    ? "lampu/buzzer/LED GLD1"
    : "24 V steady GLD2";
  const physicalCommanded = legacyManualOnly
    ? commanded
    : alarmControl?.physicalCommanded === true;
  if (modeSelect.dataset.alarmModeChangeWired !== "1") {
    modeSelect.addEventListener("change", () => {
      alarmModeSelectionDirty = true;
    });
    modeSelect.dataset.alarmModeChangeWired = "1";
  }
  // A 500 ms status poll must not undo the operator's new selection before
  // Apply Mode is clicked. Clear the dirty flag only after firmware reports
  // that exact selection back as authoritative status.
  if (legacyManualOnly) {
    // A dirty selection can belong to a different/newer device. The legacy
    // device has no mode command, so force the read-only display to MANUAL.
    alarmModeSelectionDirty = false;
  } else if (alarmModeSelectionDirty && modeSelect.value === mode) {
    alarmModeSelectionDirty = false;
  }
  if (!alarmModeApplyPending && !alarmModeSelectionDirty) modeSelect.value = mode;
  modeSelect.disabled = alarmModeApplyPending || !available || !hasExplicitMode;
  modeApply.disabled = alarmModeApplyPending || !available || !hasExplicitMode;
  on.disabled = manualAlarmApplyPending || alarmModeApplyPending || !manualOutputAllowed;
  off.disabled = manualAlarmApplyPending || alarmModeApplyPending || !manualOutputAllowed;
  const modeUpgradeTitle = legacyManualOnly
    ? "Firmware lama: upgrade firmware untuk memilih AUTO/MANUAL. Kontrol manual ON/OFF tetap tersedia."
    : "";
  modeSelect.title = modeUpgradeTitle;
  modeApply.title = modeUpgradeTitle;
  if (status) {
    status.textContent = !available
      ? "Firmware belum melaporkan kontrol mode alarm."
      : legacyManualOnly
        ? `Firmware lama terdeteksi: mode terkunci MANUAL dan tombol ON/OFF lama tetap dapat dipakai. Upgrade firmware untuk kontrol AUTO/MANUAL; perintah mode baru tidak akan dikirim. Test output=${commanded ? "ON" : "OFF"}.`
      : mode === "auto"
      ? `AUTO (default setiap boot): inferensi valid mengendalikan output fisik. Inferensi=${inferenceAlarm ? "ALARM" : "clear"}; ${outputDescription}=${physicalCommanded ? "ON" : "OFF"}.`
        : `MANUAL TEST sementara: hanya aktif selama sesi ini dan reboot mengembalikan AUTO. Inferensi tetap dilaporkan (${inferenceAlarm ? "ALARM" : "clear"}) tetapi tidak mengendalikan output fisik. ${outputDescription} test=${commanded ? "ON" : "OFF"}.`;
  }
}

function sensorPowerChannelState(channel) {
  const sensorPower = state.status?.sensorPower || state.status?.pcf8574;
  const available = sensorPower?.available === true;
  const ready = sensorPower?.ready === true;
  const outputs = Number(sensorPower?.outputMask ?? sensorPower?.outputs);
  const en = Number(sensorPower?.enChannels?.[channel]);
  const directState = sensorPower?.channels?.[channel];
  // outputMask is the one PCF byte received from firmware.  It is the
  // authoritative command state; channels[] is a display convenience derived
  // from that same mask. Prefer the mask so an old/stale channels[] array can
  // never show a card OFF while the live mask is 0xFF.
  const hasMaskMapping = Number.isInteger(outputs) && outputs >= 0 && outputs <= 0xFF &&
    Number.isInteger(en) && en >= 0 && en < 8;
  const on = hasMaskMapping
    ? Boolean(outputs & (1 << en))
    : directState === true;
  return { available, ready, en, on, applying: sensorPowerApplyPending };
}

function sensorPowerMatchesExpected(sensorPower, expected) {
  if (sensorPower?.available !== true || sensorPower?.ready !== true) return false;
  return Object.entries(expected).every(([channel, enabled]) => {
    const index = Number(channel);
    const outputs = Number(sensorPower?.outputMask ?? sensorPower?.outputs);
    const en = Number(sensorPower?.enChannels?.[index]);
    const hasMaskMapping = Number.isInteger(outputs) && outputs >= 0 && outputs <= 0xFF &&
      Number.isInteger(en) && en >= 0 && en < 8;
    const actual = hasMaskMapping
      ? Boolean(outputs & (1 << en))
      : sensorPower?.channels?.[index] === true;
    return actual === enabled;
  });
}

function confirmSensorPowerState(sensorPower) {
  const pending = pendingSensorPowerConfirmation;
  if (!pending || !sensorPowerMatchesExpected(sensorPower, pending.expected)) return;
  clearTimeout(pending.timer);
  pendingSensorPowerConfirmation = null;
  pending.resolve(sensorPower);
}

function waitForSensorPowerConfirmation(expected) {
  return new Promise((resolve, reject) => {
    if (pendingSensorPowerConfirmation) {
      clearTimeout(pendingSensorPowerConfirmation.timer);
      pendingSensorPowerConfirmation.reject(new Error("sensor power action superseded"));
    }
    const timer = setTimeout(() => {
      if (pendingSensorPowerConfirmation?.reject !== reject) return;
      pendingSensorPowerConfirmation = null;
      reject(new Error("status power modul belum berubah"));
    }, SENSOR_POWER_CONFIRM_TIMEOUT_MS);
    pendingSensorPowerConfirmation = { expected, resolve, reject, timer };
    confirmSensorPowerState(state.status?.sensorPower || state.status?.pcf8574);
  });
}

export async function setSensorPowerAndWait(channel, enabled) {
  const all = channel === "all";
  const expected = all
    ? Object.fromEntries(Array.from({ length: 8 }, (_, index) => [index, enabled]))
    : { [Number(channel)]: enabled };
  sensorPowerApplyPending = true;
  document.querySelectorAll("[data-sensor-power-channel], #sensorPowerAllOnBtn, #sensorPowerAllOffBtn")
    .forEach((button) => { button.disabled = true; });
  try {
    const confirmation = waitForSensorPowerConfirmation(expected);
    const payload = all
      ? `SET_SENSOR_POWER_JSON {"all":true,"enabled":${enabled}}`
      : `SET_SENSOR_POWER_JSON {"channel":${Number(channel)},"enabled":${enabled}}`;
    const ack = await sendCommandAndWaitAck(payload, "SET_SENSOR_POWER");
    if (ack.status !== "ok") throw new Error(ack.message || ack.status || "perintah ditolak");
    // Firmware emits GLD_STATUS_JSON after the ACK. GET_STATUS is queued as a
    // fallback so the button never re-enables based on an unconfirmed command.
    sendCommand("GET_STATUS");
    return await confirmation;
  } finally {
    sensorPowerApplyPending = false;
    if (pendingSensorPowerConfirmation) {
      clearTimeout(pendingSensorPowerConfirmation.timer);
      pendingSensorPowerConfirmation = null;
    }
    renderSensorPowerControls(state.status?.sensorPower || state.status?.pcf8574);
  }
}

export async function setManualAlarmAndWait(enabled) {
  const contract = alarmControlContract(state.status?.alarmControl);
  if (!contract.manualOutputAllowed) {
    throw new Error("kontrol output manual tidak tersedia pada status firmware saat ini");
  }
  manualAlarmApplyPending = true;
  renderManualAlarmControls(state.status?.alarmControl);
  try {
    const ack = await sendCommandAndWaitAck(
      `SET_MANUAL_ALARM_JSON {"enabled":${enabled}}`,
      "SET_MANUAL_ALARM"
    );
    if (ack.status !== "ok") throw new Error(ack.message || ack.status || "perintah ditolak");
    sendCommand("GET_STATUS");
  } finally {
    manualAlarmApplyPending = false;
    renderManualAlarmControls(state.status?.alarmControl);
  }
}

export async function setAlarmModeAndWait(mode) {
  const contract = alarmControlContract(state.status?.alarmControl);
  if (!contract.hasExplicitMode) {
    throw new Error("firmware lama tidak mendukung pemilihan mode; upgrade firmware terlebih dahulu");
  }
  if (!contract.available) throw new Error("kontrol mode alarm tidak tersedia pada status firmware saat ini");
  const normalized = mode === "manual" ? "manual" : "auto";
  alarmModeApplyPending = true;
  renderManualAlarmControls(state.status?.alarmControl);
  try {
    const ack = await sendCommandAndWaitAck(
      `SET_ALARM_MODE_JSON {"mode":"${normalized}"}`,
      "SET_ALARM_MODE"
    );
    if (ack.status !== "ok") throw new Error(ack.message || ack.status || "perintah ditolak");
    sendCommand("GET_STATUS");
  } finally {
    alarmModeApplyPending = false;
    renderManualAlarmControls(state.status?.alarmControl);
  }
}

function sensorWindowSamples(index) {
  const cutoff = Date.now() - SENSOR_TREND_WINDOW_MS;
  return state.history.filter((sample) => sample.ts >= cutoff && Number.isFinite(Number(sample.sensorVoltage?.[index])));
}

function sensorWindowMetrics(samples, index) {
  if (samples.length < 2) return null;

  const first = samples[0];
  const last = samples[samples.length - 1];
  const elapsedMs = last.ts - first.ts;
  if (elapsedMs < SENSOR_TREND_MIN_SPAN_MS) return null;

  const millivoltsPerMinute = ((Number(last.sensorVoltage[index]) - Number(first.sensorVoltage[index])) / elapsedMs) * 60 * 1000 * 1000;
  const valuesMv = samples.map((sample) => Number(sample.sensorVoltage[index]) * 1000);
  const lowMv = Math.min(...valuesMv);
  const highMv = Math.max(...valuesMv);
  if (!Number.isFinite(millivoltsPerMinute) || !Number.isFinite(lowMv) || !Number.isFinite(highMv)) return null;
  return { millivoltsPerMinute, lowMv, highMv, rangeMv: highMv - lowMv };
}

function lowerQuartile(values) {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!sorted.length) return null;
  return sorted[Math.floor((sorted.length - 1) * 0.25)];
}

function sensorStability(index, currentMetrics) {
  if (!currentMetrics) return { stable: false, learning: true, title: "Mengumpulkan data tren satu menit" };

  const now = Date.now();
  const baselineEnd = now - SENSOR_TREND_WINDOW_MS;
  const baselineStart = baselineEnd - SENSOR_STABILITY_BASELINE_WINDOW_MS;
  const completedWindows = [];
  for (let start = baselineStart; start + SENSOR_TREND_WINDOW_MS <= baselineEnd; start += SENSOR_TREND_WINDOW_MS) {
    const samples = state.history.filter((sample) => (
      sample.ts >= start && sample.ts < start + SENSOR_TREND_WINDOW_MS && Number.isFinite(Number(sample.sensorVoltage?.[index]))
    ));
    const metrics = sensorWindowMetrics(samples, index);
    if (metrics) completedWindows.push(metrics);
  }
  if (completedWindows.length < SENSOR_STABILITY_MIN_WINDOWS) {
    return { stable: false, learning: true, title: `Mempelajari baseline ${completedWindows.length}/${SENSOR_STABILITY_MIN_WINDOWS} menit` };
  }

  const driftLimit = Math.max(
    SENSOR_STABILITY_MIN_DRIFT_MV_PER_MIN,
    lowerQuartile(completedWindows.map((metrics) => Math.abs(metrics.millivoltsPerMinute))) * SENSOR_STABILITY_BASELINE_MULTIPLIER,
  );
  const rangeLimit = Math.max(
    SENSOR_STABILITY_MIN_RANGE_MV,
    lowerQuartile(completedWindows.map((metrics) => metrics.rangeMv)) * SENSOR_STABILITY_BASELINE_MULTIPLIER,
  );
  const stable = Math.abs(currentMetrics.millivoltsPerMinute) <= driftLimit && currentMetrics.rangeMv <= rangeLimit;
  const format = new Intl.NumberFormat("id-ID", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return {
    stable,
    learning: false,
    title: `Stabil jika |drift| ≤ ${format.format(driftLimit)} mV/menit dan Δ 1m ≤ ${format.format(rangeLimit)} mV`,
  };
}

function sensorTrendPerMinute(metrics) {
  if (!metrics) return { tone: "collecting", text: "collecting trend" };
  const { millivoltsPerMinute } = metrics;
  const magnitude = new Intl.NumberFormat("id-ID", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    .format(Math.abs(millivoltsPerMinute));
  if (Math.abs(millivoltsPerMinute) < 0.01) {
    return { tone: "flat", text: `→ ${magnitude} mV/menit` };
  }
  return millivoltsPerMinute > 0
    ? { tone: "up", text: `↑ +${magnitude} mV/menit` }
    : { tone: "down", text: `↓ −${magnitude} mV/menit` };
}

function sensorRangeOneMinute(index) {
  const samples = sensorWindowSamples(index);
  const metrics = sensorWindowMetrics(samples, index);
  if (!metrics) {
    return { text: "Δ 1m: menunggu data", title: "Rentang low sampai high pada data satu menit terakhir" };
  }

  const format = new Intl.NumberFormat("id-ID", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return {
    text: `Δ 1m: ${format.format(metrics.rangeMv)} mV`,
    title: `Rentang 1 menit: ${format.format(metrics.lowMv)} sampai ${format.format(metrics.highMv)} mV`,
  };
}

function activeSessionMcpCode(index) {
  const override = Number(sessionMcpOverrides.get(index));
  if (Number.isInteger(override)) return override;
  const runtime = Number(state.status?.runtimeMcpCode?.[index]);
  if (Number.isInteger(runtime)) return runtime;
  const saved = Number(state.qc?.nullingProfile?.dacCode?.[index]);
  return Number.isInteger(saved) ? saved : null;
}

async function applySessionMcpCode(index, code) {
  if (sessionMcpApplying.has(index)) return;
  const bounded = Math.min(SESSION_MCP_CODE_MAX, Math.max(SESSION_MCP_CODE_MIN, code));
  sessionMcpApplying.add(index);
  renderSensorChannels(sensorPresenceFromStatus());
  try {
    const ack = await sendCommandAndWaitAck(
      `SET_SESSION_MCP_JSON ${JSON.stringify({ channel: index, code: bounded })}`,
      "SET_SESSION_MCP",
    );
    if (ack.status !== "ok") throw new Error(ack.message || ack.status || "device rejected MCP change");
    sessionMcpOverrides.set(index, Number.isInteger(Number(ack.code)) ? Number(ack.code) : bounded);
    await sendCommand("GET_STATUS");
  } catch (error) {
    appendLog(`SESSION_MCP_APPLY_ERROR ch=${index} code=${bounded} reason=${error.message}`, "in");
  } finally {
    sessionMcpApplying.delete(index);
    renderSensorChannels(sensorPresenceFromStatus());
  }
}

function buildSessionMcpControl(channel) {
  const code = activeSessionMcpCode(channel.index);
  const expanded = sessionMcpExpanded.has(channel.index);
  const applying = sessionMcpApplying.has(channel.index);
  const wrap = document.createElement("div");
  wrap.className = "sensor-range-row";

  const rangeEl = document.createElement("span");
  rangeEl.className = "sensor-range";
  const range = sensorRangeOneMinute(channel.index);
  rangeEl.textContent = range.text;
  rangeEl.title = range.title;

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "mcp-adjust-toggle";
  toggle.textContent = expanded ? "⌃" : "⌄";
  toggle.title = "Tampilkan kontrol MCP sesi";
  toggle.setAttribute("aria-expanded", String(expanded));
  toggle.addEventListener("click", () => {
    if (expanded) sessionMcpExpanded.delete(channel.index);
    else sessionMcpExpanded.add(channel.index);
    renderSensorChannels(sensorPresenceFromStatus());
  });
  wrap.append(rangeEl, toggle);

  if (!expanded) return [wrap];

  const adjuster = document.createElement("div");
  adjuster.className = "mcp-session-adjuster";
  adjuster.title = "Perubahan MCP ini langsung diterapkan ke DAC untuk sesi berjalan dan tidak disimpan ke profil Nulling atau NVS.";
  const decrement = document.createElement("button");
  decrement.type = "button";
  decrement.textContent = "−";
  decrement.disabled = applying || !Number.isInteger(code) || code <= SESSION_MCP_CODE_MIN || state.mode !== "inference";
  decrement.addEventListener("click", () => applySessionMcpCode(channel.index, code - 1));
  const value = document.createElement("output");
  value.textContent = Number.isInteger(code) ? String(code) : "?";
  const increment = document.createElement("button");
  increment.type = "button";
  increment.textContent = "+";
  increment.disabled = applying || !Number.isInteger(code) || code >= SESSION_MCP_CODE_MAX || state.mode !== "inference";
  increment.addEventListener("click", () => applySessionMcpCode(channel.index, code + 1));
  adjuster.append(decrement, value, increment);
  return [wrap, adjuster];
}

// Live per-channel voltage + gain readout for the Running tab: one card per
// sensor with its current voltage and a 7-step gain ladder highlighting the
// PGA gain currently in effect for that channel.
function buildSensorChannelCard(channel) {
  const metrics = sensorWindowMetrics(sensorWindowSamples(channel.index), channel.index);
  const stability = sensorStability(channel.index, metrics);
  const trend = sensorTrendPerMinute(metrics);
  const card = document.createElement("article");
  card.className = `channel-card${stability.stable ? " stable" : ""}`;
  card.title = stability.title;

  const head = document.createElement("div");
  head.className = "channel-card-head";
  const titleWrap = document.createElement("span");
  titleWrap.className = "channel-card-title";
  const swatch = document.createElement("i");
  swatch.className = "legend-swatch";
  swatch.style.background = CHART_COLORS[channel.index];
  const seriesVisible = isSensorChartSeriesVisible(channel.index);
  const title = document.createElement("button");
  title.type = "button";
  title.className = `chart-series-toggle${seriesVisible ? "" : " is-hidden"}`;
  title.textContent = channel.sensor;
  title.title = seriesVisible
    ? `Sembunyikan seri ${channel.sensor} dari grafik Running`
    : `Tampilkan seri ${channel.sensor} pada grafik Running`;
  title.setAttribute("aria-pressed", String(seriesVisible));
  title.setAttribute("aria-label", title.title);
  title.addEventListener("click", () => {
    toggleSensorChartSeries(channel.index);
    renderSensorChannels(sensorPresenceFromStatus());
  });
  const trendEl = document.createElement("span");
  trendEl.className = `sensor-trend ${trend.tone}`;
  trendEl.textContent = trend.text;
  trendEl.title = "Perubahan tegangan dari data satu menit terakhir, dinormalisasi per menit";
  titleWrap.append(swatch, title, trendEl);
  const key = document.createElement("span");
  key.textContent = `CH${channel.index + 1}`;
  head.append(titleWrap, key);

  const sensorPower = sensorPowerChannelState(channel.index);
  if (sensorPower.available) {
    const powerToggle = document.createElement("button");
    powerToggle.type = "button";
    powerToggle.className = `sensor-power-card-toggle ${sensorPower.on ? "is-on" : "is-off"}`;
    powerToggle.disabled = sensorPower.applying || !sensorPower.ready;
    powerToggle.dataset.sensorPowerChannel = String(channel.index);
    powerToggle.dataset.sensorPowerEnabled = sensorPower.on ? "false" : "true";
    powerToggle.textContent = sensorPower.on ? "CMD ON" : "CMD OFF";
    powerToggle.title = `${channel.sensor} · EN${Number.isInteger(sensorPower.en) ? sensorPower.en : "?"}: ${sensorPower.on ? "matikan" : "nyalakan"} perintah power modul`;
    powerToggle.setAttribute("aria-label", powerToggle.title);
    card.append(powerToggle);
  }

  const voltageEl = document.createElement("span");
  voltageEl.className = "channel-stage";
  // Raw reading straight from telemetry, not the toFixed(6) copy Sensor
  // Check uses - shows every digit the GLD actually reported, no rounding.
  const rawVoltage = state.status?.telemetry?.sensorVoltage?.[channel.index];
  const voltageNumber = Number(rawVoltage);
  voltageEl.textContent = Number.isFinite(voltageNumber) ? `${voltageNumber} V` : "- V";

  const telemetryDac = Number(state.status?.telemetry?.dacCodeApplied?.[channel.index]);
  const runtimeDac = Number(state.status?.runtimeMcpCode?.[channel.index]);
  const appliedDac = Number.isInteger(telemetryDac) ? telemetryDac
    : Number.isInteger(runtimeDac) ? runtimeDac : null;
  const telemetryVerified = state.status?.telemetry?.dacVerified?.[channel.index];
  const runtimeVerified = state.status?.runtimeMcpVerified?.[channel.index];
  const dacVerified = telemetryVerified === true || runtimeVerified === true;
  const dacEvidence = document.createElement("span");
  dacEvidence.className = "sensor-range";
  dacEvidence.textContent = Number.isInteger(appliedDac)
    ? `DAC ${appliedDac} · MCP ${dacVerified ? "terverifikasi" : "belum terverifikasi"}`
    : "DAC belum diterapkan";
  dacEvidence.title = dacVerified
    ? "Kode ini dibaca kembali dari register volatile MCP4725 pada TCA channel yang sama sebelum telemetry Inference dipakai."
    : "Tidak ada readback MCP4725 yang cocok untuk kode DAC ini; angka telemetry tidak boleh dianggap terikat ke DAC.";

  const sessionMcpControl = buildSessionMcpControl(channel);

  // The analysis table reads the current raw telemetry gain. Do the same here
  // instead of using the presence-card display value, which is intentionally
  // blank while a channel is otherwise marked not-ready.
  const rawGain = state.status?.telemetry?.sensorGain?.[channel.index];
  const reportedGain = Number(rawGain);
  const gainValue = GAIN_STEPS.includes(reportedGain) ? reportedGain : null;
  const ladder = document.createElement("div");
  ladder.className = "gain-ladder";
  for (const step of GAIN_STEPS) {
    const block = document.createElement("span");
    block.className = `gain-block${step === gainValue ? " active" : ""}`;
    block.textContent = String(step);
    ladder.append(block);
  }

  card.append(head, voltageEl, dacEvidence, ...sessionMcpControl, ladder);
  return card;
}

// CH1-CH4 stack to the left of the chart, CH5-CH8 to the right, so the
// chart itself stays the visual center of the Running tab.
function renderSensorChannels(channels) {
  if (!elements.sensorChannelsLeft || !elements.sensorChannelsRight) return;
  elements.sensorChannelsLeft.innerHTML = "";
  elements.sensorChannelsRight.innerHTML = "";

  channels.forEach((channel, index) => {
    const card = buildSensorChannelCard(channel);
    (index < 4 ? elements.sensorChannelsLeft : elements.sensorChannelsRight).append(card);
  });
}

// ---- line dispatch ----

function parseLegacyLine(line) {
  const mode = /^GLD_MODE=(\w+)/.exec(line)?.[1];
  if (mode) {
    state.mode = mode;
    setText("modeValue", mode);
    syncDeviceSummary();
  }
  const gas = /GLD_ML_RESULT .*gasClass=(\w+) confidence=(\d+)/.exec(line);
  if (gas) {
    setText("gasValue", gas[1]);
    setText("confidenceValue", `${gas[2]}%`);
  }
}

export function handleLine(rawLine) {
  const line = rawLine.trim();
  if (!line) return;
  appendLog(line, "in");
  trackDatasetRuntimeLine(line);
  parseBootDiagnosticLine(line);

  try {
    const info = parseJsonAfter("GLD_INFO_JSON", line);
    if (info) {
      recordSerialResponse("info");
      state.info = info;
      state.mode = info.mode || state.mode;
      updateInfo(info);
      return;
    }

    const status = parseJsonAfter("GLD_STATUS_JSON", line);
    if (status) {
      recordSerialResponse("status");
      state.status = status;
      state.mode = status.mode || state.mode;
      updateStatus(status);
      maybeAppendTelemetry(status);
      return;
    }

    const telemetry = parseJsonAfter("GLD_TELEMETRY_JSON", line);
    if (telemetry) {
      recordSerialResponse("telemetry");
      updateLightweightTelemetry(telemetry);
      return;
    }

    const qcStatus = parseJsonAfter("GLD_QC_STATUS_JSON", line);
    if (qcStatus) {
      recordSerialResponse("qc");
      updateQcStatus(qcStatus);
      return;
    }

    const ack = parseJsonAfter("GLD_CMD_ACK_JSON", line);
    if (ack) {
      recordSerialResponse("ack", ack.cmd);
      if (ack.mode) state.mode = ack.mode;
      if (ack.deviceId) setText("deviceId", ack.deviceId);
      if (ack.cmd === "SET_DEVICE_ID" && ack.status === "ok") setText("deviceId", ack.deviceId);
      if (ack.chId) setText("currentChAddress", ack.chId);
      setBadge(elements.protocolLabel, `${ack.cmd}: ${ack.status}`, ack.status === "ok" ? "ok" : "warn");
      syncDeviceSummary();
      if (state.pendingAckWait && state.pendingAckWait.cmd === ack.cmd) {
        const { resolve } = state.pendingAckWait;
        state.pendingAckWait = null;
        resolve(ack);
      }
      return;
    }
  } catch (error) {
    appendLog(`PARSER_ERROR ${error.message}`, "in");
  }

  if (line.startsWith("RUN_CURRENT_STATE_CHECK_DONE")) {
    recordSerialResponse("current-state-done");
    return;
  }

  if (line.startsWith("DATASET_")) {
    handleDatasetSerialLine(line);
  } else if (line.startsWith("NULLING_")) {
    appendNulling(line);
    // NULLING_RUNTIME_RESULT is emitted after the service has either saved a
    // complete profile or deliberately retained the prior one. Refresh the
    // NVS snapshot so cards never treat a transient candidate as saved.
    if (line.startsWith("NULLING_RUNTIME_RESULT")) sendCommand("GET_QC_STATUS");
  } else if (line.startsWith("FULLSCALE_")) {
    appendFullScaleSweep(line);
  } else {
    parseLegacyLine(line);
  }
}

// ---- mode/command helpers ----

function parseSetModeCommand(command) {
  const match = /^SET_MODE\s+([A-Za-z0-9_-]+)$/i.exec(String(command || "").trim());
  return match ? match[1].toLowerCase() : "";
}

function currentKnownMode() {
  return String(state.status?.mode || state.info?.mode || state.mode || "").toLowerCase();
}

async function publishMqttModeFallback(command, reason) {
  const mode = parseSetModeCommand(command);
  if (!mode || !state.bridgeAvailable || state.mock) return false;
  const knownMode = currentKnownMode();
  const shouldAttempt = knownMode === "dataset" || (mode === "inference" && (!knownMode || knownMode === "unknown"));
  if (!shouldAttempt) return false;

  const deviceId = state.info?.deviceId || $("targetDeviceId").value.trim().toUpperCase();
  if (!deviceId) return false;

  try {
    await bridgeFetch("/api/mqtt/dataset", {
      method: "POST",
      body: JSON.stringify({
        command: "SET_MODE",
        mode,
        deviceId,
        slot: state.activeSlot,
        host: getField("mqttHost"),
        port: Number($("mqttPort").value),
        username: getField("mqttUser"),
        password: $("mqttPass").value,
        topicRoot: getField("topicRoot")
      })
    });
    state.pendingMqttMode = mode;
    appendLog(`MQTT_SET_MODE_SENT mode=${mode} reason=${reason}`, "in");
    setBadge(elements.connectionBadge, "mqtt mode sent", "ok");
    return true;
  } catch (error) {
    appendLog(`MQTT_SET_MODE_ERROR ${error.message}`, "in");
    return false;
  }
}

export async function sendCommand(command) {
  const line = command.endsWith("\n") ? command : `${command}\n`;
  const trimmedLine = line.trimEnd();

  if (state.mock) {
    appendLog(trimmedLine, "out");
    handleMockCommand(line.trim());
    return;
  }

  if (state.pendingSerialRequest) {
    serialCommandQueue.push(line);
    appendLog(`SEND_QUEUED waiting for ${state.pendingSerialRequest.cmd}: ${trimmedLine}`, "in");
    return;
  }

  if (state.bridgeAvailable) {
    if (!state.connected) {
      try {
        const connected = await connectBridgeSerialOnly();
        if (!connected) {
          if (await publishMqttModeFallback(trimmedLine, "serial not connected")) return;
          appendLog(`SEND_SKIPPED serial not connected: ${trimmedLine}`, "in");
          return;
        }
        await wait(120);
      } catch (error) {
        if (await publishMqttModeFallback(trimmedLine, "serial connect failed")) return;
        appendLog(`SEND_ERROR connect failed: ${error.message}`, "in");
        setBadge(elements.connectionBadge, "serial error", "error");
        return;
      }
    }
    const watchStartedAt = startSerialResponseWatch(line);
    try {
      const result = await bridgeFetch("/api/serial/write", {
        method: "POST",
        body: JSON.stringify({ line: trimmedLine, slot: state.activeSlot })
      });
      if (!result?.ok) {
        clearSerialResponseWatchIfStartedAt(watchStartedAt);
        appendLog(`SEND_ERROR bridge rejected: ${trimmedLine}`, "in");
      }
    } catch (error) {
      clearSerialResponseWatchIfStartedAt(watchStartedAt);
      if (await publishMqttModeFallback(trimmedLine, "serial write failed")) return;
      appendLog(`SEND_ERROR ${error.message}`, "in");
    }
    return;
  }

  appendLog(trimmedLine, "out");

  if (!state.connected || !state.writer) {
    appendLog("SEND_SKIPPED serial not connected", "in");
    return;
  }
  const watchStartedAt = startSerialResponseWatch(line);
  try {
    await state.writer.write(encoder.encode(line));
  } catch (error) {
    clearSerialResponseWatchIfStartedAt(watchStartedAt);
    throw error;
  }
}

// Sends a command, waits for its ack, and pops up the app's own centered
// modal with the outcome so an Apply button always tells the operator
// whether it actually landed on the device (accepted, rejected by firmware
// validation, or no response at all) instead of leaving that only in the
// scrolling log.
export async function applyAndAlert(command, ackCmd, actionLabel) {
  try {
    const ack = await sendCommandAndWaitAck(command, ackCmd);
    if (ack.status === "ok") {
      await showAlert(`${actionLabel}: berhasil diterapkan.${ack.message ? `\n${ack.message}` : ""}`, "ok", actionLabel);
    } else {
      await showAlert(`${actionLabel}: DITOLAK oleh perangkat.\n${ack.message || ack.status}`, "error", actionLabel);
    }
    return ack;
  } catch (error) {
    await showAlert(`${actionLabel}: GAGAL - ${error.message}`, "error", actionLabel);
    return null;
  }
}

// Sends a command and waits for the matching GLD_CMD_ACK_JSON (matched by
// ack.cmd) so callers can show a definitive success/failure popup instead of
// firing the command and hoping it landed.
export function sendCommandAndWaitAck(command, ackCmd, timeoutMs = SERIAL_RESPONSE_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    if (state.pendingAckWait) state.pendingAckWait = null;
    const timer = setTimeout(() => {
      if (state.pendingAckWait?.reject === reject) {
        state.pendingAckWait = null;
        reject(new Error(`no response for ${ackCmd} after ${timeoutMs}ms`));
      }
    }, timeoutMs);
    state.pendingAckWait = {
      cmd: ackCmd,
      resolve: (ack) => { clearTimeout(timer); resolve(ack); },
      reject
    };
    Promise.resolve(sendCommand(command)).catch((error) => {
      if (state.pendingAckWait?.reject === reject) {
        clearTimeout(timer);
        state.pendingAckWait = null;
        reject(error);
      }
    });
  });
}

// ---- polling ----

export function pollIntervalMs() {
  const raw = Number($("pollIntervalMs")?.value);
  return Number.isFinite(raw) && raw >= 200 ? raw : DEFAULT_POLL_INTERVAL_MS;
}

// Poll is mirrored on both the Running and Dataset tabs (same shared
// state.polling/pollTimer) so either button reflects and controls the same
// recording loop - update every button with this class, not just one.
function setPollButtonLabel(text) {
  document.querySelectorAll(".poll-btn").forEach((button) => {
    button.textContent = text;
  });
}

function telemetryPollCommand() {
  return state.info?.capabilities?.lightweightTelemetry === "GET_TELEMETRY"
    ? "GET_TELEMETRY"
    : null;
}

function pollTelemetryOnce() {
  if (state.pendingSerialRequest) {
    if (!skippedPollLogged) {
      appendLog("POLL_SKIPPED waiting for previous serial response", "in");
      skippedPollLogged = true;
    }
    return;
  }

  const command = telemetryPollCommand();
  if (!command) {
    if (!skippedPollLogged) {
      appendLog("POLL_WAITING GET_INFO capability; full GET_STATUS is not repeated", "in");
      skippedPollLogged = true;
    }
    return;
  }
  skippedPollLogged = false;
  sendCommand(command);
}

export function togglePolling() {
  if (state.polling) {
    stopPolling();
  } else {
    if (!state.mock && !state.connected) {
      appendLog("POLL_SKIPPED serial not connected", "in");
      return;
    }
    const intervalMs = pollIntervalMs();
    state.polling = true;
    setPollButtonLabel(`Stop Poll (${intervalMs}ms)`);
    state.pollTimer = setInterval(pollTelemetryOnce, intervalMs);
    pollTelemetryOnce();
  }
  saveUiSession({ polling: state.polling });
}

export function stopPolling() {
  state.polling = false;
  setPollButtonLabel(`Poll ${pollIntervalMs()}ms`);
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = null;
  saveUiSession({ polling: false });
}
