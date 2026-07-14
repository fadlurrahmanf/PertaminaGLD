// Serial JSONL/legacy line parsing, boot diagnostics, Sensor Check
// rendering, alarm state, and command send/response-watch/poll plumbing.

import { $, elements, state, encoder, SENSOR_NAMES, SENSOR_MUX_CHANNELS, SENSOR_STATUS_NAMES, SERIAL_RESPONSE_TIMEOUT_MS } from "./state.js";
import { setText, setBadge, appendLog, getField, setField, wait } from "./ui.js";
import { syncDeviceSummary, renderFleetPanel } from "./fleet.js";
import { pruneHistory, drawChart } from "./chart.js";
import { renderNullingChannels, latestFeatureOrderForNulling, updateNullingMeta, appendNulling } from "./nulling.js";
import {
  updateDatasetFromStatus, maybeCaptureDatasetTelemetry, trackDatasetRuntimeLine, handleDatasetSerialLine
} from "./dataset.js";
import { handleMockCommand } from "./mock.js";
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

export function formatGas(gasClass) {
  if (gasClass === 0) return "clearGas";
  if (gasClass == null) return "n/a";
  return `class ${gasClass}`;
}

function textValue(value, fallback = "Unknown") {
  if (value === "unknown") return fallback;
  return value == null || value === "" ? fallback : String(value);
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
  setText("modeValue", "Unknown");
  setText("firmwareValue", "Unknown");
  setText("gasValue", "n/a");
  setText("confidenceValue", "-%");
  setText("powerMode", "Unknown");
  setText("externalPower", "Unknown");
  setText("batteryValue", "Unknown");
  setText("batteryValueMirror", "Unknown");
  setText("loraValue", "Unknown");
  setText("adsHealth", "Unknown");
  setText("mcpHealth", "Unknown");
  setText("dacHealth", "Unknown");
  setText("mlHealth", "Unknown");
  updateAlarmState(false);
  renderSensorCheck();
  syncDeviceSummary();
}

function updateInfo(info) {
  setText("deviceId", info.deviceId);
  setText("modeValue", info.mode);
  setText("firmwareValue", info.firmwareVersion || info.firmwareName);
  setBadge(elements.protocolLabel, info.protocolVersion || "app serial", "ok");
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
  setText("modeValue", status.mode);

  const telemetry = status.telemetry || {};
  setText("gasValue", telemetry.gasName || formatGas(telemetry.gasClass));
  setText("confidenceValue", Number.isFinite(telemetry.confidence) ? `${telemetry.confidence}%` : "-%");

  const alarm = Boolean(telemetry.alarm || status.alarm);
  updateAlarmState(alarm);

  const power = status.power || {};
  setText("powerMode", power.mode);
  setText("externalPower", power.externalPower === true ? "Yes" : power.externalPower === false ? "No" : "Unknown");
  const batteryText = Number.isFinite(power.batteryMv) ? `${power.batteryMv} mV` : "Unknown";
  setText("batteryValue", batteryText);
  setText("batteryValueMirror", batteryText);

  const boot = status.bootHealth || {};
  setText("adsHealth", boot.adsReady === true ? "Ready" : "Not ready");
  setText("mcpHealth", Number.isFinite(boot.mcpOkCount) ? `${boot.mcpOkCount}/8` : "Unknown");
  setText("dacHealth", boot.dacReady === true ? "Ready" : "Not ready");
  setText("mlHealth", boot.mlReady === true ? "Ready" : "Not ready");

  const lora = status.lora || {};
  const loraOk = lora.lastTxOk === true || lora.beginState === 0;
  setText("loraValue", loraOk ? "OK" : Number.isFinite(lora.beginState) ? `state ${lora.beginState}` : "Unknown");
  syncDeviceSummary();
  updateDatasetFromStatus(status);
  updateNullingMeta();
  renderSensorCheck();
  renderNullingChannels();
}

function maybeAppendTelemetry(status) {
  const telemetry = status.telemetry;
  if (!telemetry || !telemetry.valid || !Array.isArray(telemetry.sensorVoltage)) return;

  const ts = Date.now();
  state.history.push({
    ts,
    deviceId: status.deviceId || state.info?.deviceId || "",
    mode: status.mode || state.mode,
    gasName: telemetry.gasName || formatGas(telemetry.gasClass),
    gasClass: telemetry.gasClass,
    confidence: telemetry.confidence,
    alarm: Boolean(telemetry.alarm),
    sensorVoltage: telemetry.sensorVoltage.slice(0, 8),
    sensorGain: Array.isArray(telemetry.sensorGain) ? telemetry.sensorGain.slice(0, 8) : [],
    featureOrder: Array.isArray(telemetry.featureOrder) ? telemetry.featureOrder.slice(0, 8) : []
  });
  pruneHistory();
  drawChart();
  maybeCaptureDatasetTelemetry(status);
}

// ---- alarm ----

export function updateAlarmState(alarm) {
  state.alarmActive = alarm;
  setBadge(elements.alarmBadge, alarm ? (state.alarmMuted ? "Alarm muted" : "Active alarm") : "No active alarms", alarm ? "alarm" : "ok");
  elements.alarmMuteBtn.textContent = state.alarmMuted ? "Unmute Alarm" : "Mute Alarm";
  elements.alarmMuteBtn.disabled = !alarm && !state.alarmMuted;
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
    elements.topGasStatus.textContent = gas[1];
    elements.topConfidenceStatus.textContent = `${gas[2]}%`;
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

    const ack = parseJsonAfter("GLD_CMD_ACK_JSON", line);
    if (ack) {
      clearSerialResponseWatch();
      if (ack.mode) state.mode = ack.mode;
      if (ack.deviceId) setText("deviceId", ack.deviceId);
      if (ack.cmd === "SET_DEVICE_ID" && ack.status === "ok") setText("deviceId", ack.deviceId);
      setBadge(elements.protocolLabel, `${ack.cmd}: ${ack.status}`, ack.status === "ok" ? "ok" : "warn");
      syncDeviceSummary();
      return;
    }
  } catch (error) {
    appendLog(`PARSER_ERROR ${error.message}`, "in");
  }

  if (line.startsWith("DATASET_")) {
    handleDatasetSerialLine(line);
  } else if (line.startsWith("NULLING_")) {
    appendNulling(line);
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

// ---- polling ----

export function togglePolling() {
  if (state.polling) {
    stopPolling();
  } else {
    if (!state.mock && !state.connected) {
      appendLog("POLL_SKIPPED serial not connected", "in");
      return;
    }
    state.polling = true;
    elements.refreshLoopBtn.textContent = "Stop Poll";
    state.pollTimer = setInterval(() => sendCommand("GET_STATUS"), 1000);
    sendCommand("GET_STATUS");
  }
}

export function stopPolling() {
  state.polling = false;
  elements.refreshLoopBtn.textContent = "Poll 1s";
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = null;
}
