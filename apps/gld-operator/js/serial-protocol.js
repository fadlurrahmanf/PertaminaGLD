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

function serialCommandName(command) {
  return String(command || "").trim().split(/\s+/)[0] || "COMMAND";
}

export function clearSerialResponseWatch() {
  if (!state.pendingSerialRequest) return;
  clearTimeout(state.pendingSerialRequest.timer);
  state.pendingSerialRequest = null;
}

export function startSerialResponseWatch(command) {
  clearSerialResponseWatch();
  const cmd = serialCommandName(command);
  const startedAt = Date.now();
  const timer = setTimeout(() => {
    if (!state.pendingSerialRequest || state.pendingSerialRequest.startedAt !== startedAt) return;
    appendLog(`NO_RESPONSE ${cmd} after ${SERIAL_RESPONSE_TIMEOUT_MS}ms`, "in");
    setBadge(elements.protocolLabel, `${cmd}: no response`, "warn");
    state.pendingSerialRequest = null;
  }, SERIAL_RESPONSE_TIMEOUT_MS);
  state.pendingSerialRequest = { cmd, startedAt, timer };
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
  updateAlarmState(false);
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
      stage: mcp === "8/8" ? "OK" : mcp,
      tone: mcp === "8/8" ? "pass" : "fail",
      detail: `MCP detected ${mcp}${pairs.mcpMask ? `, mask ${pairs.mcpMask}` : ""}; check TCA channels and MCP4725 power/address if below 8/8`
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
  cards.push(probes.mcp || rows.mcp || statusBootCard(
    "mcp",
    "MCP4725 Mux",
    mcpKnown ? (mcpAllOk ? "OK" : `${Number.isFinite(mcpCount) ? mcpCount : "?"}/8`) : "Unknown",
    mcpKnown ? (mcpAllOk ? "pass" : "fail") : "idle",
    mcpKnown
      ? (mcpAllOk ? "MCP detected on all 8 TCA channels" : `MCP detected ${Number.isFinite(mcpCount) ? mcpCount : "?"}/8; check TCA channels and MCP4725 power/address`)
      : "Waiting for I2C boot evidence"
  ));

  const mcpControlOkArray = boot.mcpControlTested === true && Array.isArray(boot.mcpControlOk) ? boot.mcpControlOk : null;
  const mcpControlKnown = boot.mcpControlTested === true || Boolean(mcpControlOkArray);
  const mcpControlCount = mcpControlOkArray ? mcpControlOkArray.filter((v) => optionalBool(v) === true).length : NaN;
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

    return {
      index,
      sensor,
      stage,
      tone,
      detail: adsStatusName && telemetry.valid === true ? `${detail} (${adsStatusName})` : detail,
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
  elements.sensorCheckMeta.textContent = `ADS: ${boot.adsReady === true ? "Ready" : boot.adsReady === false ? `Not ready${adsReason}` : "Unknown"} - MCP: ${Number.isFinite(boot.mcpOkCount) ? `${boot.mcpOkCount}/8` : "Unknown"} - Latest telemetry: ${telemetry.valid ? "valid" : "none"}${check ? ` - Check ${check}` : ""}`;
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

    card.append(head, stage, detail, extra);
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
  const status = {
    ...(state.status || {}),
    deviceId: message.deviceId || state.status?.deviceId || state.info?.deviceId,
    mode: message.mode || state.mode,
    uptimeMs: message.uptimeMs,
    alarmLatched: message.alarmLatched ?? state.status?.alarmLatched,
    model: { ...(state.status?.model || {}), ...(message.model || {}) },
    telemetry: message.telemetry
  };
  state.status = status;
  state.mode = status.mode || state.mode;
  updateStatus(status);
  maybeAppendTelemetry(status);
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

  const voltageEl = document.createElement("span");
  voltageEl.className = "channel-stage";
  // Raw reading straight from telemetry, not the toFixed(6) copy Sensor
  // Check uses - shows every digit the GLD actually reported, no rounding.
  const rawVoltage = state.status?.telemetry?.sensorVoltage?.[channel.index];
  const voltageNumber = Number(rawVoltage);
  voltageEl.textContent = Number.isFinite(voltageNumber) ? `${voltageNumber} V` : "- V";

  const sessionMcpControl = buildSessionMcpControl(channel);

  const gainValue = channel.gain !== "" ? Number(channel.gain) : null;
  const ladder = document.createElement("div");
  ladder.className = "gain-ladder";
  for (const step of GAIN_STEPS) {
    const block = document.createElement("span");
    block.className = `gain-block${step === gainValue ? " active" : ""}`;
    block.textContent = String(step);
    ladder.append(block);
  }

  card.append(head, voltageEl, ...sessionMcpControl, ladder);
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
      clearSerialResponseWatch();
      state.info = info;
      state.mode = info.mode || state.mode;
      updateInfo(info);
      return;
    }

    const status = parseJsonAfter("GLD_STATUS_JSON", line);
    if (status) {
      clearSerialResponseWatch();
      state.status = status;
      state.mode = status.mode || state.mode;
      updateStatus(status);
      maybeAppendTelemetry(status);
      return;
    }

    const telemetry = parseJsonAfter("GLD_TELEMETRY_JSON", line);
    if (telemetry) {
      clearSerialResponseWatch();
      updateLightweightTelemetry(telemetry);
      return;
    }

    const qcStatus = parseJsonAfter("GLD_QC_STATUS_JSON", line);
    if (qcStatus) {
      clearSerialResponseWatch();
      updateQcStatus(qcStatus);
      return;
    }

    const ack = parseJsonAfter("GLD_CMD_ACK_JSON", line);
    if (ack) {
      clearSerialResponseWatch();
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
    try {
      const result = await bridgeFetch("/api/serial/write", {
        method: "POST",
        body: JSON.stringify({ line: trimmedLine, slot: state.activeSlot })
      });
      if (result?.ok) startSerialResponseWatch(line);
    } catch (error) {
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
  await state.writer.write(encoder.encode(line));
  startSerialResponseWatch(line);
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
    : "GET_STATUS";
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
    state.pollTimer = setInterval(() => sendCommand(telemetryPollCommand()), intervalMs);
    sendCommand(telemetryPollCommand());
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
