const $ = (id) => document.getElementById(id);

const DEFAULT_BRIDGE_ORIGIN = "http://127.0.0.1:5173";

function bridgeUrl(path) {
  const onBridgeOrigin = location.protocol.startsWith("http")
    && location.hostname === "127.0.0.1"
    && location.port === "5173";
  return onBridgeOrigin ? path : `${DEFAULT_BRIDGE_ORIGIN}${path}`;
}

const CHART_COLORS = [
  "#2dd47f",
  "#58a6ff",
  "#d9a441",
  "#ec5a5a",
  "#67d7cf",
  "#b08cff",
  "#f07f45",
  "#d6e870"
];

const SENSOR_NAMES = ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"];
const SENSOR_MUX_CHANNELS = [7, 6, 5, 4, 3, 2, 1, 0];
const SENSOR_STATUS_NAMES = {
  0: "Ok",
  1: "NotReady",
  2: "DrdyTimeout",
  3: "InvalidChannel"
};
const SERIAL_RESPONSE_TIMEOUT_MS = 5000;

function initialDatasetSession() {
  return {
    active: false,
    state: "Idle",
    phase: "No active session",
    label: "",
    deviceId: "",
    target: 0,
    startedAt: null,
    endedAt: null,
    lastSampleAt: null,
    rows: [],
    rowKeys: new Set(),
    outputName: "Not saved",
    outputPath: "Waiting for session",
    fileName: "",
    saved: false,
    nullingFirst: false,
    lastEvent: "No dataset command sent.",
    error: ""
  };
}

const state = {
  port: null,
  reader: null,
  writer: null,
  connected: false,
  mock: false,
  mockTimer: null,
  pollTimer: null,
  polling: false,
  bridgeAvailable: false,
  bridgeFeatures: {},
  eventSource: null,
  buffer: "",
  logs: [],
  pendingSerialRequest: null,
  dataset: initialDatasetSession(),
  nullingLogs: [],
  bootDiagnostics: {
    reportSeen: false,
    bootRows: {},
    probes: {},
    lastLine: ""
  },
  mockNullingStep: 0,
  history: [],
  info: null,
  status: null,
  alarmActive: false,
  alarmMuted: false,
  alarmAudioContext: null,
  alarmLastBeep: 0,
  mode: "unknown",
  expertUnlocked: false,
  manifest: null
};

const encoder = new TextEncoder();
const decoder = new TextDecoder();

const elements = {
  alarmBadge: $("alarmBadge"),
  alarmMuteBtn: $("alarmMuteBtn"),
  portSetupBtn: $("portSetupBtn"),
  closeSetupBtn: $("closeSetupBtn"),
  setupPanel: $("setupPanel"),
  connectBtn: $("connectBtn"),
  disconnectBtn: $("disconnectBtn"),
  mockBtn: $("mockBtn"),
  connectionBadge: $("connectionBadge"),
  portLabel: $("portLabel"),
  protocolLabel: $("protocolLabel"),
  portSelect: $("portSelect"),
  manualPortInput: $("manualPortInput"),
  useManualPortBtn: $("useManualPortBtn"),
  portDetail: $("portDetail"),
  refreshPortsBtn: $("refreshPortsBtn"),
  refreshLoopBtn: $("refreshLoopBtn"),
  rangeSelect: $("rangeSelect"),
  sensorChart: $("sensorChart"),
  legend: $("legend"),
  serialLog: $("serialLog"),
  datasetStateValue: $("datasetStateValue"),
  datasetPhaseValue: $("datasetPhaseValue"),
  datasetProgressValue: $("datasetProgressValue"),
  datasetElapsedValue: $("datasetElapsedValue"),
  datasetRowsValue: $("datasetRowsValue"),
  datasetLastSampleValue: $("datasetLastSampleValue"),
  datasetOutputName: $("datasetOutputName"),
  datasetOutputPath: $("datasetOutputPath"),
  datasetProgressBar: $("datasetProgressBar"),
  datasetLastEvent: $("datasetLastEvent"),
  datasetHint: $("datasetHint"),
  datasetNullingFirst: $("datasetNullingFirst"),
  datasetRowsBody: $("datasetRowsBody"),
  nullingLog: $("nullingLog"),
  nullingSummary: $("nullingSummary"),
  nullingMeta: $("nullingMeta"),
  nullingChannels: $("nullingChannels"),
  sensorCheckSummary: $("sensorCheckSummary"),
  sensorCheckMeta: $("sensorCheckMeta"),
  bootReportSummary: $("bootReportSummary"),
  bootReportGrid: $("bootReportGrid"),
  sensorCheckChannels: $("sensorCheckChannels"),
  topDeviceStatus: $("topDeviceStatus"),
  topModeStatus: $("topModeStatus"),
  topGasStatus: $("topGasStatus"),
  topConfidenceStatus: $("topConfidenceStatus"),
  sideDeviceSummary: $("sideDeviceSummary"),
  sidePortSummary: $("sidePortSummary")
};

function nowText() {
  return new Date().toLocaleTimeString("en-GB", { hour12: false });
}

function setBadge(el, text, kind = "") {
  el.textContent = text;
  el.className = `badge ${kind}`.trim();
}

function setText(id, value) {
  const element = $(id);
  if (!element) return;
  element.textContent = value == null || value === "" ? "Unknown" : String(value);
}

function resetDeviceSnapshot() {
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

function textValue(value, fallback = "Unknown") {
  if (value === "unknown") return fallback;
  return value == null || value === "" ? fallback : String(value);
}

function syncDeviceSummary() {
  const deviceId = textValue(state.status?.deviceId || state.info?.deviceId);
  const mode = textValue(state.status?.mode || state.info?.mode || state.mode);
  const telemetry = state.status?.telemetry || {};
  const gas = textValue(telemetry.gasName || formatGas(telemetry.gasClass), "n/a");
  const confidence = Number.isFinite(telemetry.confidence) ? `${telemetry.confidence}%` : "-%";
  const port = state.mock ? "mock" : elements.portSelect.value || (state.connected ? "selected" : "No port selected");

  elements.topDeviceStatus.textContent = deviceId;
  elements.topModeStatus.textContent = mode;
  elements.topGasStatus.textContent = gas;
  elements.topConfidenceStatus.textContent = confidence;
  elements.sideDeviceSummary.textContent = deviceId;
  elements.sidePortSummary.textContent = port;
}

function appendLog(line, direction = "in") {
  const prefix = direction === "out" ? ">>" : "<<";
  const entry = `${nowText()} ${prefix} ${line}`;
  state.logs.push(entry);
  if (state.logs.length > 3000) state.logs.splice(0, state.logs.length - 3000);
  elements.serialLog.textContent = state.logs.join("\n");
  elements.serialLog.scrollTop = elements.serialLog.scrollHeight;
}

function serialCommandName(command) {
  return String(command || "").trim().split(/\s+/)[0] || "COMMAND";
}

function clearSerialResponseWatch() {
  if (!state.pendingSerialRequest) return;
  clearTimeout(state.pendingSerialRequest.timer);
  state.pendingSerialRequest = null;
}

function startSerialResponseWatch(command) {
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

function appendNulling(line) {
  if (line.startsWith("NULLING_SERVICE_START")) {
    state.nullingLogs = [];
  }
  state.nullingLogs.push(line);
  if (state.nullingLogs.length > 1200) state.nullingLogs.splice(0, state.nullingLogs.length - 1200);
  elements.nullingLog.textContent = state.nullingLogs.join("\n");
  elements.nullingLog.scrollTop = elements.nullingLog.scrollHeight;
  elements.nullingSummary.textContent = summarizeNulling(line);
  renderNullingChannels();
}

function summarizeNulling(line) {
  const ch = /ch=(\d+)/.exec(line)?.[1];
  if (line.includes("SERVICE_START")) return "Nulling service started.";
  if (line.includes("BASELINE")) return ch ? `Channel ${Number(ch) + 1} baseline scan.` : "Baseline scan.";
  if (line.includes("EXP_")) return ch ? `Channel ${Number(ch) + 1} exponential range search.` : "Exponential range search.";
  if (line.includes("BIN_")) return ch ? `Channel ${Number(ch) + 1} binary search.` : "Binary search.";
  if (line.includes("CONFIRM")) return ch ? `Channel ${Number(ch) + 1} confirmation.` : "Confirmation.";
  if (line.includes("SERVICE_DONE")) return line.includes("status=Ok") ? "Nulling complete: PASS." : line;
  if (line.includes("RUNTIME_RESULT")) return line.replaceAll("_", " ");
  return line;
}

function parseJsonAfter(prefix, line) {
  if (!line.startsWith(prefix)) return null;
  const raw = line.slice(prefix.length).trim();
  return JSON.parse(raw);
}

function tokenValue(line, key) {
  const match = new RegExp(`(?:^|\\s)${key}=([^\\s]+)`).exec(line);
  return match?.[1];
}

function channelIndexFromLog(line) {
  const value = tokenValue(line, "ch") ?? tokenValue(line, "channel");
  if (value == null) return undefined;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 && parsed < 8 ? parsed : undefined;
}

function nullingDetail(line) {
  if (line.startsWith("NULLING_CH_START")) return "Channel started";
  if (line.startsWith("NULLING_BASELINE_START")) return "Searching baseline";
  if (line.startsWith("NULLING_EXP_START")) return "Finding exponential range";
  if (line.startsWith("NULLING_EXP_RANGE")) return "Range locked";
  if (line.startsWith("NULLING_BIN_START")) return "Binary search started";
  if (line.startsWith("NULLING_BIN_DONE")) return "Binary selected";
  if (line.startsWith("NULLING_CONFIRM_START")) return "Confirmation window";
  if (line.startsWith("NULLING_CONFIRM_OK")) return "Confirmation OK";
  if (line.startsWith("NULLING_CH_OK")) return "Channel OK";
  if (line.startsWith("NULLING_CH_FAIL")) return tokenValue(line, "message") || "Channel failed";

  const delta = tokenValue(line, "delta");
  const low = tokenValue(line, "low");
  const high = tokenValue(line, "high");
  const valid = tokenValue(line, "valid");
  const sample = tokenValue(line, "sample");
  const parts = [
    sample ? `sample ${sample}` : undefined,
    low && high ? `range ${low}-${high}` : undefined,
    delta ? `delta ${delta}` : undefined,
    valid ? `valid ${valid}` : undefined
  ].filter(Boolean);
  if (parts.length) return parts.join(" - ");
  return line.replace(/^NULLING_[A-Z_]+=?\s*/, "").slice(0, 72);
}

function latestFeatureOrderForNulling() {
  const statusOrder = state.status?.telemetry?.featureOrder;
  const historyOrder = state.history.length ? state.history[state.history.length - 1].featureOrder : [];
  return Array.isArray(statusOrder) && statusOrder.length ? statusOrder : historyOrder.length ? historyOrder : SENSOR_NAMES;
}

function nullingChannelsFromLogs(logs, featureOrder = SENSOR_NAMES) {
  const channels = Array.from({ length: 8 }, (_, index) => ({
    index,
    sensor: featureOrder[index] || SENSOR_NAMES[index] || `CH${index + 1}`,
    stage: "Waiting",
    tone: "idle",
    detail: "No nulling data",
    dac: "",
    baseline: "",
    after: ""
  }));

  for (const line of logs) {
    const index = channelIndexFromLog(line);
    if (index === undefined) continue;
    const channel = channels[index];
    channel.sensor = tokenValue(line, "sensor") ?? channel.sensor;
    channel.detail = nullingDetail(line);

    if (line.startsWith("NULLING_CH_START")) {
      channel.stage = "Start";
      channel.tone = "active";
    } else if (line.startsWith("NULLING_BASELINE_")) {
      channel.stage = "Baseline";
      channel.tone = "active";
    } else if (line.startsWith("NULLING_EXP_")) {
      channel.stage = "Exponential";
      channel.tone = "active";
    } else if (line.startsWith("NULLING_BIN_")) {
      channel.stage = "Binary";
      channel.tone = "active";
    } else if (line.startsWith("NULLING_CONFIRM_")) {
      channel.stage = "Confirm";
      channel.tone = "active";
    }

    const status = tokenValue(line, "status")?.toUpperCase();
    if (line.startsWith("NULLING_CH_OK") || status === "PASS" || status === "OK") {
      channel.stage = "Done";
      channel.tone = "pass";
    } else if (line.startsWith("NULLING_CH_FAIL") || status === "FAIL" || status === "ERROR") {
      channel.stage = "Failed";
      channel.tone = "fail";
    }

    channel.dac = tokenValue(line, "dac") ?? tokenValue(line, "selected") ?? tokenValue(line, "code") ?? channel.dac;
    channel.baseline = tokenValue(line, "baseline") ?? channel.baseline;
    channel.after = tokenValue(line, "after") ?? tokenValue(line, "voltage") ?? channel.after;
  }

  return channels;
}

function renderNullingChannels() {
  const featureOrder = latestFeatureOrderForNulling();
  const channels = nullingChannelsFromLogs(state.nullingLogs, featureOrder);
  elements.nullingChannels.innerHTML = "";
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

    card.append(head, stage, detail);
    const extra = [channel.dac ? `DAC ${channel.dac}` : "", channel.baseline ? `base ${channel.baseline}` : "", channel.after ? `after ${channel.after}` : ""].filter(Boolean);
    if (extra.length) {
      const extraLine = document.createElement("small");
      extraLine.textContent = extra.join(" - ");
      card.append(extraLine);
    }
    elements.nullingChannels.append(card);
  }
}

function sensorPresenceFromStatus(status = state.status) {
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
        label: parts[0],
        check: parts[1],
        status: parts[2],
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

  const mcpCount = Number(boot.mcpOkCount);
  const mcpKnown = Number.isFinite(mcpCount);
  cards.push(probes.i2c || rows.i2c || statusBootCard(
    "i2c",
    "I2C/TCA9548A",
    mcpKnown && mcpCount > 0 ? "OK" : mcpKnown ? "Check" : "Unknown",
    mcpKnown && mcpCount > 0 ? "pass" : mcpKnown ? "active" : "idle",
    mcpKnown && mcpCount > 0 ? "At least one muxed device responded" : "Waiting for TCA/I2C boot evidence"
  ));
  const mcpAllOk = mcpKnown && mcpCount === 8;
  cards.push(probes.mcp || rows.mcp || statusBootCard(
    "mcp",
    "MCP4725 Mux",
    mcpKnown ? `${mcpCount}/8` : "Unknown",
    mcpKnown ? (mcpAllOk ? "pass" : "fail") : "idle",
    mcpKnown ? `MCP detected ${mcpCount}/8; failed channels are marked below${Array.isArray(boot.mcpAddrMask) ? " with address masks" : ""}` : "Waiting for MCP channel evidence"
  ));

  const mcpControlCount = Number(boot.mcpControlOkCount);
  const mcpControlKnown = Number.isFinite(mcpControlCount);
  const dacKnown = boot.dacReady === true || boot.dacReady === false;
  const dacAllOk = boot.dacReady === true && (!mcpControlKnown || mcpControlCount === 8);
  cards.push(probes.dac || rows.dac || statusBootCard(
    "dac",
    "DAC Control",
    mcpControlKnown ? `${mcpControlCount}/8` : dacKnown ? (boot.dacReady ? "OK" : "Fail") : "Unknown",
    mcpControlKnown ? (dacAllOk ? "pass" : "fail") : bootTone(boot.dacReady === true, dacKnown),
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

function renderSensorCheck() {
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

function updateNullingMeta() {
  const nulling = state.status?.nulling || {};
  const retry = nulling.retryArmed === true ? "yes" : "no";
  const attempts = Number.isFinite(nulling.attemptCount) ? nulling.attemptCount : 0;
  const suffix = nulling.done === true ? " - Done" : nulling.running === true ? " - Running" : "";
  elements.nullingMeta.textContent = `Retry armed: ${retry} - Attempts: ${attempts}${suffix}`;
}

function handleLine(rawLine) {
  const line = rawLine.trim();
  if (!line) return;
  appendLog(line, "in");
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

function formatGas(gasClass) {
  if (gasClass === 0) return "clearGas";
  if (gasClass == null) return "n/a";
  return `class ${gasClass}`;
}

function updateAlarmState(alarm) {
  state.alarmActive = alarm;
  setBadge(elements.alarmBadge, alarm ? (state.alarmMuted ? "Alarm muted" : "Active alarm") : "No active alarms", alarm ? "alarm" : "ok");
  elements.alarmMuteBtn.textContent = state.alarmMuted ? "Unmute Alarm" : "Mute Alarm";
  elements.alarmMuteBtn.disabled = !alarm && !state.alarmMuted;
  if (alarm && !state.alarmMuted) playAlarmBeep();
}

function toggleAlarmMute() {
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

function startDatasetSession(dataset, deviceId) {
  const label = dataset.label || getField("datasetLabel") || "dataset";
  const session = initialDatasetSession();
  session.active = true;
  session.state = "Starting";
  session.phase = "Publishing START_DATASET";
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

function setDatasetState(nextState, phase, eventText, isError = false) {
  state.dataset.state = nextState || state.dataset.state;
  if (phase) state.dataset.phase = phase;
  if (eventText) state.dataset.lastEvent = `${nowText()} ${eventText}`;
  if (isError) state.dataset.error = eventText || nextState;
  renderDatasetSession();
}

function markDatasetDone(reason) {
  if (!state.dataset.endedAt) state.dataset.endedAt = Date.now();
  state.dataset.active = false;
  state.dataset.state = "Done";
  state.dataset.phase = reason || "Capture complete";
  state.dataset.lastEvent = `${nowText()} ${reason || "Dataset complete"}`;
  renderDatasetSession();
  maybeAutoSaveDataset();
}

function handleDatasetSerialLine(line) {
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

function handleDatasetMqttEvent(payload) {
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
    const phase = noProfile
      ? "No nulling profile in GLD. Run nulling once, then start dataset again."
      : ok ? "GLD acknowledged dataset command" : "GLD command response";
    setDatasetState(ok ? "Command ACK" : noProfile ? "Needs Nulling" : "Command response", phase, `MQTT ack ${cmd} ${result}`, !ok && rejected);
    return;
  }
  state.dataset.lastEvent = `${nowText()} MQTT ${kind} ${text}`;
  renderDatasetSession();
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

function maybeCaptureDatasetTelemetry(status) {
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

function updateDatasetFromStatus(status) {
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

function datasetFileName(deviceId, label) {
  const safeDevice = safeFilePart(deviceId || "GLD");
  const safeLabel = safeFilePart(label || "dataset");
  return `${safeDevice}_${safeLabel}_${stamp()}.csv`;
}

function safeFilePart(value) {
  return String(value).trim().replace(/[^A-Za-z0-9_.-]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40) || "dataset";
}

async function saveDatasetCsv() {
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

function downloadDatasetCsv() {
  if (!state.dataset.rows.length) {
    setDatasetState(state.dataset.state, "No rows to download", "DATASET_DOWNLOAD_SKIPPED no rows", true);
    return;
  }
  const filename = state.dataset.fileName || datasetFileName(state.dataset.deviceId, state.dataset.label);
  downloadText(filename, datasetCsv(), "text/csv");
}

async function openDatasetFolder() {
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

function clearDatasetSession() {
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

function refreshDatasetWaitingState() {
  const session = state.dataset;
  if (!session.startedAt) {
    renderDatasetSession();
    return;
  }
  const ageMs = Date.now() - session.startedAt;
  const passiveStates = /^(Starting|Command Sent|Command ACK|Monitor Ready|Ready|Dataset Mode|idle)$/i;
  if (session.active && session.rows.length === 0 && ageMs > 7000 && passiveStates.test(session.state)) {
    session.state = "Waiting Data";
    session.phase = "No samples yet. Check GLD mode, MQTT topic/device ID, and nulling profile.";
  }
  renderDatasetSession();
}

function renderDatasetSession() {
  const session = state.dataset;
  elements.datasetStateValue.textContent = session.state;
  elements.datasetPhaseValue.textContent = session.phase;
  elements.datasetRowsValue.textContent = String(session.rows.length);
  elements.datasetLastEvent.textContent = session.lastEvent;
  elements.datasetOutputName.textContent = session.outputName;
  elements.datasetOutputPath.textContent = session.outputPath;
  elements.datasetHint.textContent = datasetHint(session);
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

function pruneHistory() {
  const rangeMs = Number(elements.rangeSelect.value) * 1000;
  const cutoff = Date.now() - rangeMs;
  while (state.history.length && state.history[0].ts < cutoff) state.history.shift();
}

function drawChart() {
  const canvas = elements.sensorChart;
  const parent = canvas.parentElement;
  const dpr = window.devicePixelRatio || 1;
  const cssWidth = Math.max(320, parent.clientWidth);
  const cssHeight = Math.max(280, Math.min(420, Math.round(window.innerHeight * 0.48)));
  canvas.width = Math.round(cssWidth * dpr);
  canvas.height = Math.round(cssHeight * dpr);
  canvas.style.height = `${cssHeight}px`;

  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssWidth, cssHeight);
  ctx.fillStyle = "#0a100f";
  ctx.fillRect(0, 0, cssWidth, cssHeight);

  const pad = { left: 58, right: 18, top: 18, bottom: 34 };
  const width = cssWidth - pad.left - pad.right;
  const height = cssHeight - pad.top - pad.bottom;
  const now = Date.now();
  const rangeMs = Number(elements.rangeSelect.value) * 1000;
  const visible = state.history.filter((point) => point.ts >= now - rangeMs);

  drawGrid(ctx, pad, width, height);

  if (!visible.length) {
    ctx.fillStyle = "#98a7a0";
    ctx.font = "13px system-ui";
    ctx.fillText("Waiting for telemetry", pad.left + 12, pad.top + 24);
    renderLegend([]);
    return;
  }

  let min = Infinity;
  let max = -Infinity;
  for (const point of visible) {
    for (const value of point.sensorVoltage) {
      if (Number.isFinite(value)) {
        min = Math.min(min, value);
        max = Math.max(max, value);
      }
    }
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    min = -0.01;
    max = 0.01;
  }
  if (Math.abs(max - min) < 0.00001) {
    max += 0.001;
    min -= 0.001;
  }
  const margin = (max - min) * 0.12;
  min -= margin;
  max += margin;

  ctx.fillStyle = "#98a7a0";
  ctx.font = "12px system-ui";
  ctx.fillText(max.toFixed(4), 8, pad.top + 5);
  ctx.fillText(min.toFixed(4), 8, pad.top + height);

  const labels = latestFeatureOrder(visible);
  for (let ch = 0; ch < 8; ch += 1) {
    ctx.beginPath();
    ctx.lineWidth = 1.8;
    ctx.strokeStyle = CHART_COLORS[ch];
    let started = false;
    for (const point of visible) {
      const value = point.sensorVoltage[ch];
      if (!Number.isFinite(value)) continue;
      const x = pad.left + ((point.ts - (now - rangeMs)) / rangeMs) * width;
      const y = pad.top + (1 - (value - min) / (max - min)) * height;
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.stroke();
  }
  renderLegend(labels);
}

function drawGrid(ctx, pad, width, height) {
  ctx.strokeStyle = "#23332e";
  ctx.lineWidth = 1;
  ctx.strokeRect(pad.left, pad.top, width, height);
  ctx.beginPath();
  for (let i = 1; i < 4; i += 1) {
    const y = pad.top + (height / 4) * i;
    ctx.moveTo(pad.left, y);
    ctx.lineTo(pad.left + width, y);
  }
  for (let i = 1; i < 5; i += 1) {
    const x = pad.left + (width / 5) * i;
    ctx.moveTo(x, pad.top);
    ctx.lineTo(x, pad.top + height);
  }
  ctx.stroke();
}

function latestFeatureOrder(points) {
  for (let i = points.length - 1; i >= 0; i -= 1) {
    if (points[i].featureOrder.length) return points[i].featureOrder;
  }
  return ["CH1", "CH2", "CH3", "CH4", "CH5", "CH6", "CH7", "CH8"];
}

function renderLegend(labels) {
  elements.legend.innerHTML = "";
  const list = labels.length ? labels : ["CH1", "CH2", "CH3", "CH4", "CH5", "CH6", "CH7", "CH8"];
  list.slice(0, 8).forEach((label, index) => {
    const item = document.createElement("span");
    const swatch = document.createElement("i");
    swatch.className = "swatch";
    swatch.style.background = CHART_COLORS[index];
    item.append(swatch, document.createTextNode(label || `CH${index + 1}`));
    elements.legend.appendChild(item);
  });
}

async function connectSerial() {
  if (state.bridgeAvailable) {
    try {
      const connected = await connectBridgeSerialOnly({ resetSnapshot: true, openSetupOnMissingPort: true });
      if (!connected) return;
      await wait(180);
      await sendCommand("APP_PING");
      await wait(120);
      await sendCommand("GET_INFO");
      await wait(120);
      await sendCommand("GET_STATUS");
      setSetupOpen(false);
    } catch (error) {
      appendLog(`CONNECT_ERROR ${error.message}`, "in");
      setBadge(elements.connectionBadge, "error", "error");
    }
    return;
  }

  if (!("serial" in navigator)) {
    setBadge(elements.connectionBadge, "Web Serial unavailable", "error");
    appendLog("Browser does not expose Web Serial. Use Chrome or Edge over localhost/HTTPS.", "in");
    return;
  }
  try {
    const ports = await navigator.serial.getPorts();
    state.port = ports[0] || await navigator.serial.requestPort();
    await state.port.open({ baudRate: 115200, bufferSize: 4096 });
    state.writer = state.port.writable.getWriter();
    state.connected = true;
    updateConnectionUi("connected", "ok");
    readLoop();
    await sendCommand("APP_PING");
    await wait(120);
    await sendCommand("GET_INFO");
    await wait(120);
    await sendCommand("GET_STATUS");
    setSetupOpen(false);
  } catch (error) {
    setBadge(elements.connectionBadge, "error", "error");
    appendLog(`CONNECT_ERROR ${error.message}`, "in");
  }
}

async function connectBridgeSerialOnly({ resetSnapshot = false, openSetupOnMissingPort = false } = {}) {
  const port = elements.portSelect.value;
  if (!port) {
    if (openSetupOnMissingPort) setSetupOpen(true);
    appendLog("CONNECT_SKIPPED select a COM port first", "in");
    return false;
  }
  if (resetSnapshot) {
    resetDeviceSnapshot();
  }
  await bridgeFetch("/api/serial/connect", {
    method: "POST",
    body: JSON.stringify({ port, baud: 115200 })
  });
  state.connected = true;
  updateConnectionUi("connected", "ok");
  return true;
}

async function readLoop() {
  try {
    state.reader = state.port.readable.getReader();
    while (state.connected) {
      const { value, done } = await state.reader.read();
      if (done) break;
      if (value) processChunk(decoder.decode(value, { stream: true }));
    }
  } catch (error) {
    if (state.connected) appendLog(`READ_ERROR ${error.message}`, "in");
  } finally {
    if (state.reader) {
      try { state.reader.releaseLock(); } catch {}
      state.reader = null;
    }
  }
}

function processChunk(text) {
  state.buffer += text;
  const parts = state.buffer.split(/\r?\n/);
  state.buffer = parts.pop() || "";
  parts.forEach(handleLine);
}

async function disconnectSerial() {
  clearSerialResponseWatch();
  stopPolling();
  if (state.bridgeAvailable) {
    await bridgeFetch("/api/serial/disconnect", { method: "POST", body: "{}" }).catch((error) => {
      appendLog(`DISCONNECT_ERROR ${error.message}`, "in");
    });
    state.connected = false;
    updateConnectionUi("bridge ready", "ok");
    return;
  }

  state.connected = false;
  try {
    if (state.reader) await state.reader.cancel();
  } catch {}
  try {
    if (state.writer) state.writer.releaseLock();
  } catch {}
  state.writer = null;
  try {
    if (state.port) await state.port.close();
  } catch {}
  state.port = null;
  updateConnectionUi("disconnected", "");
}

async function sendCommand(command) {
  const line = command.endsWith("\n") ? command : `${command}\n`;

  if (state.mock) {
    appendLog(line.trimEnd(), "out");
    handleMockCommand(line.trim());
    return;
  }

  if (state.bridgeAvailable) {
    if (!state.connected) {
      try {
        const connected = await connectBridgeSerialOnly();
        if (!connected) {
          appendLog(`SEND_SKIPPED serial not connected: ${line.trimEnd()}`, "in");
          return;
        }
        await wait(120);
      } catch (error) {
        appendLog(`SEND_ERROR connect failed: ${error.message}`, "in");
        setBadge(elements.connectionBadge, "serial error", "error");
        return;
      }
    }
    try {
      const result = await bridgeFetch("/api/serial/write", {
        method: "POST",
        body: JSON.stringify({ line: line.trimEnd() })
      });
      if (result?.ok) startSerialResponseWatch(line);
    } catch (error) {
      appendLog(`SEND_ERROR ${error.message}`, "in");
    }
    return;
  }

  appendLog(line.trimEnd(), "out");

  if (!state.connected || !state.writer) {
    appendLog("SEND_SKIPPED serial not connected", "in");
    return;
  }
  await state.writer.write(encoder.encode(line));
  startSerialResponseWatch(line);
}

function updateConnectionUi(text, kind) {
  setBadge(elements.connectionBadge, text, kind);
  elements.connectBtn.disabled = state.connected || state.mock;
  elements.disconnectBtn.disabled = !state.connected && !state.mock;
  if (state.mock) {
    elements.portLabel.textContent = "mock";
    elements.portDetail.textContent = "Mock GLD telemetry source.";
    elements.sidePortSummary.textContent = "mock";
  } else if (state.bridgeAvailable) {
    elements.portLabel.textContent = elements.portSelect.value || "bridge";
    updateSelectedPortDetail();
  } else {
    elements.portLabel.textContent = state.connected ? "selected" : "browser selected";
    elements.portDetail.textContent = state.connected ? "Browser-selected serial port." : "No serial port selected.";
    elements.sidePortSummary.textContent = state.connected ? "browser serial" : "No port selected";
  }
  syncDeviceSummary();
}

function updateSelectedPortDetail() {
  const option = elements.portSelect.selectedOptions[0];
  if (!option || !option.value) {
    elements.portDetail.textContent = state.bridgeAvailable ? "No serial port selected." : "Bridge not connected.";
    elements.portLabel.textContent = state.bridgeAvailable ? "bridge" : "browser selected";
    elements.sidePortSummary.textContent = "No port selected";
    return;
  }
  const parts = [option.value];
  if (option.dataset.manual === "true") parts.push("manual override");
  if (option.dataset.description) parts.push(option.dataset.description);
  if (option.dataset.manufacturer) parts.push(option.dataset.manufacturer);
  elements.portDetail.textContent = parts.join(" - ");
  elements.portLabel.textContent = option.value;
  elements.sidePortSummary.textContent = option.value;
}

function normalizePortName(value) {
  return String(value || "").trim().toUpperCase();
}

function ensureManualPortOption(select = true) {
  const manual = normalizePortName(elements.manualPortInput.value);
  if (!/^COM\d+$/i.test(manual)) {
    appendLog(`MANUAL_PORT_REJECTED invalid COM port: ${elements.manualPortInput.value}`, "in");
    return "";
  }
  let option = Array.from(elements.portSelect.options).find((item) => item.value.toUpperCase() === manual);
  if (!option) {
    option = new Option(`${manual} (manual)`, manual);
    option.dataset.manual = "true";
    elements.portSelect.append(option);
  }
  if (select) {
    elements.portSelect.value = manual;
    updateSelectedPortDetail();
    appendLog(`MANUAL_PORT_SELECTED ${manual}`, "in");
  }
  return manual;
}

function setSetupOpen(open) {
  elements.setupPanel.classList.toggle("open", open);
  elements.setupPanel.setAttribute("aria-hidden", open ? "false" : "true");
}

function switchTab(tabId) {
  document.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tabId);
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === tabId);
  });
  drawChart();
}

function getField(id) {
  return $(id).value.trim();
}

function setField(id, value) {
  if (value != null && value !== "") $(id).value = value;
}

function numberField(id) {
  return Number($(id).value);
}

async function applyGldSettings() {
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

async function injectDeviceId() {
  const deviceId = getField("targetDeviceId").toUpperCase();
  if (!/^[0-9A-F]{4}$/.test(deviceId) || deviceId === "0000") {
    appendLog("ID_REJECTED target ID must be 4 non-zero hex chars, for example F001", "in");
    return;
  }
  if (!window.confirm(`Inject GLD ID ${deviceId} and reboot?`)) return;
  await sendCommand(`SET_DEVICE_ID_JSON ${JSON.stringify({ deviceId, reboot: true })}`);
}

async function publishDatasetCommand(command) {
  const deviceId = state.info?.deviceId || $("targetDeviceId").value.trim().toUpperCase();
  const dataset = command === "START_DATASET"
    ? {
        cmd: "START_DATASET",
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
      setDatasetState("Switching Mode", "Sending SET_MODE dataset before MQTT START_DATASET", "SET_MODE dataset before START_DATASET");
      await sendCommand("SET_MODE dataset");
      await wait(2500);
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

async function uploadFirmware() {
  if (!state.bridgeAvailable) {
    appendLog("UPLOAD_SKIPPED local bridge is required for firmware upload", "in");
    return;
  }
  const port = elements.portSelect.value;
  const env = getField("firmwareEnv") || "gld";
  const targetDeviceId = getField("targetDeviceId").toUpperCase();
  if (!port) {
    appendLog("UPLOAD_SKIPPED select a COM port first", "in");
    return;
  }
  const manifestWarning = validateManifestForUpload(state.manifest, env, targetDeviceId);
  if (manifestWarning) {
    appendLog(`UPLOAD_SKIPPED ${manifestWarning}`, "in");
    switchTab("firmware");
    return;
  }
  if (!window.confirm(`Upload PlatformIO env ${env} to ${port}?`)) return;
  try {
    await bridgeFetch("/api/firmware/upload", {
      method: "POST",
      body: JSON.stringify({ env, port, targetDeviceId, manifest: state.manifest })
    });
    switchTab("log");
  } catch (error) {
    appendLog(`UPLOAD_ERROR ${error.message}`, "in");
  }
}

async function useLocalhost() {
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

function saveForm() {
  const ids = ["datasetLabel", "targetSamples", "sampleIntervalMs", "maxDurationMs", "fanOnMs", "postFanSettleMs", "wifiSsid", "mqttHost", "mqttPort", "mqttUser", "topicRoot", "firmwareEnv", "targetDeviceId", "manualPortInput"];
  const data = Object.fromEntries(ids.map((id) => [id, $(id).value]));
  localStorage.setItem("gldOperatorWeb.form", JSON.stringify(data));
}

function loadForm() {
  try {
    const data = JSON.parse(localStorage.getItem("gldOperatorWeb.form") || "{}");
    Object.entries(data).forEach(([id, value]) => {
      if ($(id)) $(id).value = value;
    });
  } catch {}
}

function downloadText(filename, text, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function exportLog() {
  downloadText(`GLD_serial_${stamp()}.log`, `${state.logs.join("\n")}\n`);
}

function exportCsv() {
  const headers = [
    "timeIso",
    "deviceId",
    "mode",
    "gasName",
    "gasClass",
    "confidence",
    "alarm",
    ...SENSOR_NAMES
  ];
  const rows = state.history.map((point) => [
    new Date(point.ts).toISOString(),
    point.deviceId,
    point.mode,
    point.gasName,
    point.gasClass ?? "",
    point.confidence ?? "",
    point.alarm ? 1 : 0,
    ...Array.from({ length: 8 }, (_, index) => point.sensorVoltage[index] ?? "")
  ]);
  const csv = [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\n");
  downloadText(`GLD_telemetry_${stamp()}.csv`, `${csv}\n`, "text/csv");
}

function csvCell(value) {
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function stamp() {
  return new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "");
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function bridgeFetch(path, options = {}) {
  const response = await fetch(bridgeUrl(path), {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `${response.status} ${response.statusText}`);
  return payload;
}

async function initBridge() {
  try {
    const health = await bridgeFetch("/api/health");
    state.bridgeAvailable = Boolean(health.ok);
    state.bridgeFeatures = health.features || {};
    setBadge(elements.connectionBadge, "bridge ready", "ok");
    setText("protocolLabel", "bridge");
    elements.protocolLabel.title = `bridge ${health.version}`;
    startBridgeEvents();
    await refreshPorts(true);
    await initDatasetOutputDir();
    if (!state.bridgeFeatures.mqtt) {
      appendLog(`MQTT bridge unavailable: ${health.errors?.mqtt || "paho-mqtt not installed"}`, "in");
    }
  } catch {
    state.bridgeAvailable = false;
    if (!("serial" in navigator)) {
      setBadge(elements.connectionBadge, "Web Serial unavailable", "warn");
    }
  }
}

async function initDatasetOutputDir() {
  try {
    const result = await bridgeFetch("/api/dataset/output-dir");
    if (result.path && state.dataset.outputPath === "Waiting for session") {
      state.dataset.outputPath = result.path;
      renderDatasetSession();
    }
  } catch (error) {
    appendLog(`DATASET_OUTPUT_DIR_ERROR ${error.message}`, "in");
  }
}

function startBridgeEvents() {
  if (state.eventSource) state.eventSource.close();
  const source = new EventSource(bridgeUrl("/api/events"));
  source.onerror = () => {
    if (!state.bridgeAvailable) return;
    setBadge(elements.connectionBadge, "bridge event lost", "warn");
  };
  source.addEventListener("serial_line", (event) => {
    if (state.mock) return;
    const payload = JSON.parse(event.data);
    handleLine(payload.line);
  });
  source.addEventListener("serial_tx", (event) => {
    const payload = JSON.parse(event.data);
    appendLog(payload.line, "out");
  });
  source.addEventListener("serial_status", (event) => {
    const payload = JSON.parse(event.data);
    state.connected = Boolean(payload.connected);
    if (!payload.connected) clearSerialResponseWatch();
    updateConnectionUi(payload.connected ? "connected" : "bridge ready", payload.connected ? "ok" : "ok");
    if (payload.port) elements.portLabel.textContent = payload.port;
  });
  source.addEventListener("serial_error", (event) => {
    const payload = JSON.parse(event.data);
    clearSerialResponseWatch();
    state.connected = false;
    appendLog(`SERIAL_ERROR ${payload.message}`, "in");
    setBadge(elements.connectionBadge, "serial error", "error");
    updateConnectionUi("serial error", "error");
  });
  source.addEventListener("upload_start", (event) => {
    const payload = JSON.parse(event.data);
    appendLog(`UPLOAD_START ${payload.cmd}`, "in");
    switchTab("log");
  });
  source.addEventListener("upload_line", (event) => {
    const payload = JSON.parse(event.data);
    appendLog(payload.line, "in");
  });
  source.addEventListener("upload_done", (event) => {
    const payload = JSON.parse(event.data);
    appendLog(`UPLOAD_DONE code=${payload.code}`, "in");
  });
  source.addEventListener("upload_error", (event) => {
    const payload = JSON.parse(event.data);
    appendLog(`UPLOAD_ERROR ${payload.message}`, "in");
  });
  source.addEventListener("mqtt_publish", (event) => {
    const payload = JSON.parse(event.data);
    appendLog(`MQTT_PUBLISH ${payload.topic} ${payload.payload}`, "in");
  });
  source.addEventListener("dataset_monitor", (event) => {
    const payload = JSON.parse(event.data);
    if (payload.status === "started") {
      setDatasetState(state.dataset.state === "Idle" ? "Monitor Ready" : state.dataset.state, "MQTT dataset monitor started", `Dataset monitor ${payload.host}:${payload.port}`);
    } else if (payload.status === "subscribed") {
      setDatasetState(state.dataset.state, "Subscribed to dataset MQTT topics", `Subscribed ${payload.topics?.length || 0} dataset topics`);
    }
  });
  source.addEventListener("dataset_mqtt", (event) => {
    const payload = JSON.parse(event.data);
    appendLog(`DATASET_MQTT ${payload.topic} ${payload.payload}`, "in");
    handleDatasetMqttEvent(payload);
  });
  source.addEventListener("dataset_saved", (event) => {
    const payload = JSON.parse(event.data);
    state.dataset.outputName = payload.filename || state.dataset.outputName;
    state.dataset.outputPath = payload.path || state.dataset.outputPath;
    state.dataset.saved = true;
    renderDatasetSession();
  });
  state.eventSource = source;
}

async function refreshPorts(bridgeAlreadyChecked = false) {
  const oldText = elements.refreshPortsBtn.textContent;
  elements.refreshPortsBtn.textContent = "Scanning";
  elements.refreshPortsBtn.disabled = true;
  if (!state.bridgeAvailable && !bridgeAlreadyChecked) {
    await initBridge();
  }
  if (!state.bridgeAvailable) {
    appendLog(`PORT_SCAN_SKIPPED bridge is not reachable at ${DEFAULT_BRIDGE_ORIGIN}`, "in");
    elements.refreshPortsBtn.textContent = oldText;
    elements.refreshPortsBtn.disabled = false;
    return;
  }
  try {
    const result = await bridgeFetch("/api/ports");
    elements.portSelect.innerHTML = "";
    const ports = result.ports || [];
    if (!ports.length) {
      elements.portSelect.append(new Option("No serial ports", ""));
      ensureManualPortOption(false);
      updateSelectedPortDetail();
      return;
    }
    for (const port of ports) {
      const option = new Option(port.path, port.path);
      option.dataset.description = port.description || "";
      option.dataset.manufacturer = port.manufacturer || "";
      elements.portSelect.append(option);
    }
    const manual = ensureManualPortOption(false);
    const preferred = ports.find((port) => port.path === "COM10")
      || (manual ? { path: manual } : null)
      || ports[0];
    elements.portSelect.value = preferred.path;
    elements.portLabel.textContent = preferred.path;
    updateSelectedPortDetail();
    const scanned = ports.map((port) => port.path).join(", ");
    appendLog(`PORT_SCAN_OK ${scanned}${manual && !ports.some((port) => port.path.toUpperCase() === manual) ? ` manual=${manual}` : ""}`, "in");
  } catch (error) {
    appendLog(`PORT_SCAN_ERROR ${error.message}`, "in");
  } finally {
    elements.refreshPortsBtn.textContent = oldText;
    elements.refreshPortsBtn.disabled = false;
  }
}

function togglePolling() {
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

function stopPolling() {
  state.polling = false;
  elements.refreshLoopBtn.textContent = "Poll 1s";
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = null;
}

function toggleMock() {
  if (state.mock) {
    clearInterval(state.mockTimer);
    state.mockTimer = null;
    state.mock = false;
    state.connected = false;
    resetDeviceSnapshot();
    updateConnectionUi("disconnected", "");
    return;
  }
  state.mock = true;
  state.connected = false;
  updateConnectionUi("mock", "ok");
  emitMockInfo();
  state.mockTimer = setInterval(emitMockStatus, 1000);
}

function handleMockCommand(command) {
  if (command === "GET_INFO" || command === "APP_PING") emitMockInfo();
  if (command === "GET_STATUS" || command === "RUN_BOOT_CHECK") emitMockStatus();
  if (command.startsWith("SET_MODE ")) {
    state.mode = command.slice("SET_MODE ".length);
    handleLine(`GLD_CMD_ACK_JSON ${JSON.stringify(mockAck("SET_MODE", "ok", true))}`);
    emitMockInfo();
    if (state.mode === "nulling") startMockNulling();
  }
  if (command.startsWith("SET_DEVICE_ID_JSON ")) {
    const payload = safeJson(command.slice("SET_DEVICE_ID_JSON ".length));
    if (payload?.deviceId) state.info = { ...(state.info || {}), deviceId: payload.deviceId };
    handleLine(`GLD_CMD_ACK_JSON ${JSON.stringify(mockAck("SET_DEVICE_ID", "ok", Boolean(payload?.reboot)))}`);
    emitMockInfo();
  }
  if (command.startsWith("SET_APP_CONFIG_JSON ")) {
    handleLine(`GLD_CMD_ACK_JSON ${JSON.stringify(mockAck("SET_APP_CONFIG", "ok", true))}`);
  }
}

function safeJson(text) {
  try { return JSON.parse(text); } catch { return null; }
}

function mockAck(cmd, status, rebootExpected) {
  return {
    deviceId: state.info?.deviceId || "F001",
    nodeId: 0xF001,
    cmd,
    status,
    message: "mock",
    rebootExpected,
    mode: state.mode === "unknown" ? "inference" : state.mode,
    uptimeMs: Math.floor(performance.now())
  };
}

function emitMockInfo() {
  const info = {
    deviceId: state.info?.deviceId || "F001",
    nodeId: 0xF001,
    firmwareVersion: "0.8.12",
    protocolVersion: "0.1.0",
    boardProfile: "GLDW-WROOM-1U-N16R8",
    mode: state.mode === "unknown" ? "inference" : state.mode,
    baud: 115200,
    appConfig: {
      wifiSsid: getField("wifiSsid"),
      mqttHost: getField("mqttHost"),
      mqttPort: numberField("mqttPort"),
      mqttUser: getField("mqttUser"),
      topicRoot: getField("topicRoot")
    },
    capabilities: {
      appPing: true,
      getInfo: true,
      getStatus: true,
      serialAppConfig: true,
      serialDeviceId: true
    }
  };
  handleLine(`GLD_INFO_JSON ${JSON.stringify(info)}`);
}

function emitMockStatus() {
  const t = Date.now() / 1000;
  const voltage = Array.from({ length: 8 }, (_, index) => {
    return 0.08 * Math.sin(t * (0.35 + index * 0.04) + index) + index * 0.012;
  });
  const alarm = Math.random() > 0.98;
  const status = {
    deviceId: state.info?.deviceId || "F001",
    nodeId: 0xF001,
    mode: state.mode === "unknown" ? "inference" : state.mode,
    power: { mode: "24v", externalPower: true, batteryMv: 3560, batteryValid: true },
    bootHealth: { adsReady: true, mcpOkCount: 8, dacReady: true, mlReady: true },
    lora: { beginState: 0, lastTxOk: true },
    nulling: {
      running: state.mode === "nulling" && state.mockNullingStep < 48,
      done: state.mockNullingStep >= 48,
      retryArmed: false,
      attemptCount: 0
    },
    telemetry: {
      valid: true,
      gasClass: 0,
      gasName: alarm ? "methane" : "clearGas",
      confidence: alarm ? 87 : 99,
      alarm,
      sensorVoltage: voltage,
      sensorGain: [64, 64, 64, 64, 64, 32, 64, 64],
      sensorStatus: [0, 0, 0, 0, 0, 0, 0, 0],
      featureOrder: ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"]
    }
  };
  handleLine(`GLD_STATUS_JSON ${JSON.stringify(status)}`);
  if (state.mode === "nulling") emitMockNullingProgress();
}

function startMockNulling() {
  state.mockNullingStep = 0;
  handleLine("NULLING_SERVICE_START profileId=1 retryArmed=0 attempts=0");
}

function emitMockNullingProgress() {
  if (state.mockNullingStep >= 48) return;
  const channel = Math.floor(state.mockNullingStep / 6);
  const stage = state.mockNullingStep % 6;
  const sensor = SENSOR_NAMES[channel] || `MQ${channel + 1}`;
  const baseCode = 132 + channel * 4;
  const voltage = (0.294 + channel * 0.002 + stage * 0.0007).toFixed(9);
  const delta = (0.00008 + stage * 0.00001).toFixed(6);

  if (stage === 0) {
    handleLine(`NULLING_CH_START ch=${channel} sensor=${sensor}`);
  } else if (stage === 1) {
    handleLine(`NULLING_BASELINE_START ch=${channel} sensor=${sensor}`);
    handleLine(`NULLING_BASELINE_STEP ch=${channel} sensor=${sensor} sample=10 code=${baseCode} voltage=${voltage} valid=1`);
  } else if (stage === 2) {
    handleLine(`NULLING_EXP_START ch=${channel} sensor=${sensor}`);
    handleLine(`NULLING_EXP_STEP ch=${channel} sensor=${sensor} low=${baseCode - 24} high=${baseCode + 24} code=${baseCode + 8} voltage=${voltage} delta=${delta} valid=1 write=1`);
    handleLine(`NULLING_EXP_RANGE ch=${channel} sensor=${sensor} low=${baseCode - 16} high=${baseCode + 16}`);
  } else if (stage === 3) {
    handleLine(`NULLING_BIN_START ch=${channel} sensor=${sensor}`);
    handleLine(`NULLING_BIN_STEP ch=${channel} sensor=${sensor} low=${baseCode - 16} high=${baseCode + 16} mid=${baseCode} voltage=${voltage} delta=${delta} valid=1 write=1`);
    handleLine(`NULLING_BIN_DONE ch=${channel} sensor=${sensor} selected=${baseCode}`);
  } else if (stage === 4) {
    handleLine(`NULLING_CONFIRM_START ch=${channel} sensor=${sensor} start=${baseCode - 5} end=${baseCode + 4}`);
    handleLine(`NULLING_CONFIRM_STEP ch=${channel} sensor=${sensor} code=${baseCode} voltage=${voltage} delta=${delta} valid=1 positive=1 write=1`);
    handleLine(`NULLING_CONFIRM_OK ch=${channel} sensor=${sensor} code=${baseCode}`);
  } else {
    handleLine(`NULLING_CH_OK ch=${channel} sensor=${sensor} dac=${baseCode} baseline=${(Number(voltage) - 0.0009).toFixed(6)} after=${voltage}`);
  }

  state.mockNullingStep += 1;
  if (state.mockNullingStep >= 48) {
    handleLine("NULLING_SERVICE_DONE status=Ok successCount=8/8");
    handleLine("NULLING_RUN_DONE status=Ok successCount=8");
    handleLine("NULLING_RUNTIME_RESULT=PASS");
    handleLine("NULLING_AUTO_MODE_SWITCH target=running mode=inference profileId=1 delayMs=800");
    state.mode = "inference";
    emitMockInfo();
  }
}

async function loadManifestFile(file) {
  if (!file) return;
  const text = await file.text();
  try {
    const manifest = JSON.parse(text);
    state.manifest = manifest;
    $("packageDeviceId").value = manifest.deviceId || "";
    if (manifest.env || manifest.environment) $("firmwareEnv").value = manifest.env || manifest.environment;
    $("manifestPreview").textContent = JSON.stringify(manifest, null, 2);
  } catch (error) {
    state.manifest = null;
    $("manifestPreview").textContent = `Invalid manifest: ${error.message}`;
  }
}

function validateManifestForUpload(manifest, env, targetDeviceId) {
  if (!manifest) return "";
  const manifestEnv = manifest.env || manifest.environment;
  if (manifestEnv && manifestEnv !== env) return `manifest env ${manifestEnv} does not match selected env ${env}`;
  const packageDeviceId = String(manifest.deviceId || "").toUpperCase();
  if (packageDeviceId && packageDeviceId !== "F000" && packageDeviceId !== targetDeviceId) {
    return `manifest deviceId ${packageDeviceId} does not match target ID ${targetDeviceId}`;
  }
  const chip = manifest.chipFamily || manifest.chip;
  if (chip && !/esp32s3/i.test(String(chip))) return `manifest chip ${chip} is not ESP32-S3`;
  return "";
}

function setupEvents() {
  elements.portSetupBtn.addEventListener("click", () => {
    setSetupOpen(true);
    if (state.bridgeAvailable) refreshPorts(true);
  });
  elements.closeSetupBtn.addEventListener("click", () => setSetupOpen(false));
  document.querySelectorAll("[data-close-setup]").forEach((node) => {
    node.addEventListener("click", () => setSetupOpen(false));
  });
  elements.connectBtn.addEventListener("click", connectSerial);
  elements.disconnectBtn.addEventListener("click", () => state.mock ? toggleMock() : disconnectSerial());
  elements.alarmMuteBtn.addEventListener("click", toggleAlarmMute);
  elements.mockBtn.addEventListener("click", toggleMock);
  elements.refreshPortsBtn.addEventListener("click", refreshPorts);
  elements.useManualPortBtn.addEventListener("click", () => ensureManualPortOption(true));
  elements.manualPortInput.addEventListener("change", saveForm);
  elements.portSelect.addEventListener("change", updateSelectedPortDetail);
  elements.refreshLoopBtn.addEventListener("click", togglePolling);
  elements.rangeSelect.addEventListener("change", () => {
    pruneHistory();
    drawChart();
  });
  $("clearChartBtn").addEventListener("click", () => {
    state.history = [];
    drawChart();
  });
  $("exportCsvBtn").addEventListener("click", exportCsv);
  $("downloadLogBtn").addEventListener("click", exportLog);
  $("clearLogBtn").addEventListener("click", () => {
    state.logs = [];
    elements.serialLog.textContent = "";
  });
  $("clearNullingBtn").addEventListener("click", () => {
    state.nullingLogs = [];
    elements.nullingLog.textContent = "";
    elements.nullingSummary.textContent = "No nulling activity.";
    updateNullingMeta();
    renderNullingChannels();
  });
  $("refreshSensorCheckBtn").addEventListener("click", () => sendCommand("GET_STATUS"));
  $("clearSensorCheckBtn").addEventListener("click", () => {
    state.status = null;
    state.bootDiagnostics = {
      reportSeen: false,
      bootRows: {},
      probes: {},
      lastLine: ""
    };
    renderSensorCheck();
  });
  $("applyConfigBtn").addEventListener("click", applyGldSettings);
  $("switchDatasetBtn").addEventListener("click", () => sendCommand("SET_MODE dataset"));
  $("startDatasetBtn").addEventListener("click", () => publishDatasetCommand("START_DATASET"));
  $("stopDatasetBtn").addEventListener("click", () => publishDatasetCommand("STOP_DATASET"));
  $("saveDatasetCsvBtn").addEventListener("click", saveDatasetCsv);
  $("downloadDatasetCsvBtn").addEventListener("click", downloadDatasetCsv);
  $("openDatasetFolderBtn").addEventListener("click", openDatasetFolder);
  $("clearDatasetSessionBtn").addEventListener("click", clearDatasetSession);
  $("useThisPcBtn").addEventListener("click", useLocalhost);
  $("unlockExpertBtn").addEventListener("click", () => {
    state.expertUnlocked = true;
    $("rawCommand").disabled = false;
    $("sendRawBtn").disabled = false;
    $("unlockExpertBtn").disabled = true;
  });
  $("sendRawBtn").addEventListener("click", () => {
    const command = $("rawCommand").value.trim();
    if (command) sendCommand(command);
  });
  $("rawCommand").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !$("sendRawBtn").disabled) $("sendRawBtn").click();
  });
  $("loadManifestBtn").addEventListener("click", () => $("manifestFile").click());
  $("manifestFile").addEventListener("change", (event) => loadManifestFile(event.target.files[0]));
  $("uploadFirmwareBtn").addEventListener("click", uploadFirmware);
  $("injectIdBtn").addEventListener("click", injectDeviceId);

  document.querySelectorAll("[data-command]").forEach((button) => {
    button.addEventListener("click", () => sendCommand(button.dataset.command));
  });
  document.querySelectorAll("[data-mode]").forEach((button) => {
    button.addEventListener("click", () => sendCommand(`SET_MODE ${button.dataset.mode}`));
  });
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => switchTab(button.dataset.tab));
  });
  document.querySelectorAll("input").forEach((input) => {
    if (input.id !== "datasetNullingFirst") input.addEventListener("change", saveForm);
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setSetupOpen(false);
  });
  window.addEventListener("resize", drawChart);
}

async function bootstrap() {
  loadForm();
  setupEvents();
  renderLegend([]);
  renderDatasetSession();
  setInterval(refreshDatasetWaitingState, 1000);
  updateNullingMeta();
  renderNullingChannels();
  renderSensorCheck();
  drawChart();
  updateAlarmState(false);
  syncDeviceSummary();
  await initBridge();
  if (!window.isSecureContext) {
    appendLog("WEB_SERIAL_NOTE Serve this page from http://127.0.0.1 or HTTPS for Web Serial.", "in");
  }
  if (!state.bridgeAvailable && !("serial" in navigator)) {
    setBadge(elements.connectionBadge, "Web Serial unavailable", "warn");
  }
}

bootstrap();
