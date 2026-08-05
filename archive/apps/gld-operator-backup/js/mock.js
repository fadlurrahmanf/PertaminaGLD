// Mock GLD simulator: fake telemetry/nulling/command responses so the UI
// can be exercised without hardware. Kept for feature parity; this
// rebuild's own verification uses real hardware per user instruction.

import { state, SENSOR_NAMES } from "./state.js";
import { getField, numberField } from "./ui.js";
import { handleLine, resetDeviceSnapshot } from "./serial-protocol.js";
import { updateConnectionUi } from "./bridge-client.js";

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

export function emitMockInfo() {
  const info = {
    deviceId: state.info?.deviceId || "F001",
    nodeId: 0xF001,
    targetChId: state.info?.targetChId || "0064",
    firmwareVersion: "0.8.13",
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
      serialDeviceId: true,
      serialChAddress: "SET_CH_ADDRESS_JSON chId"
    }
  };
  handleLine(`GLD_INFO_JSON ${JSON.stringify(info)}`);
}

export function emitMockStatus() {
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
      attemptCount: 0,
      thresholdV: state.mockNullingConfig?.thresholdV ?? 0.00001,
      minFinalV: state.mockNullingConfig?.minFinalV ?? 0
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
  const baseline = 0.294 + channel * 0.002;
  const threshold = Math.max(Math.abs(baseline) * 0.5, state.mockNullingConfig?.thresholdV ?? 0.00001);
  const target = baseline + threshold;
  const voltage = (baseline + stage * threshold * 0.35).toFixed(9);
  const delta = (Number(voltage) - baseline).toFixed(6);

  if (stage === 0) {
    handleLine(`NULLING_CH_START ch=${channel} sensor=${sensor}`);
  } else if (stage === 1) {
    handleLine(`NULLING_BASELINE_START ch=${channel} sensor=${sensor}`);
    handleLine(`NULLING_BASELINE_STEP ch=${channel} sensor=${sensor} sample=10 code=${baseCode} voltage=${voltage} valid=1`);
  } else if (stage === 2) {
    handleLine(`NULLING_EXP_START ch=${channel} sensor=${sensor} baseline=${baseline.toFixed(6)} threshold=${threshold.toFixed(6)} minThreshold=${state.mockNullingConfig?.thresholdV ?? 0.00001} ratio=0.500000 target=${target.toFixed(6)}`);
    handleLine(`NULLING_EXP_STEP ch=${channel} sensor=${sensor} low=${baseCode - 24} high=${baseCode + 24} code=${baseCode + 8} voltage=${voltage} delta=${delta} valid=1 write=1`);
    handleLine(`NULLING_EXP_RANGE ch=${channel} sensor=${sensor} low=${baseCode - 16} high=${baseCode + 16}`);
  } else if (stage === 3) {
    handleLine(`NULLING_BIN_START ch=${channel} sensor=${sensor}`);
    handleLine(`NULLING_BIN_STEP ch=${channel} sensor=${sensor} low=${baseCode - 16} high=${baseCode + 16} mid=${baseCode} voltage=${voltage} delta=${delta} valid=1 write=1`);
    handleLine(`NULLING_BIN_DONE ch=${channel} sensor=${sensor} selected=${baseCode}`);
  } else if (stage === 4) {
    handleLine(`NULLING_CONFIRM_START ch=${channel} sensor=${sensor} start=${baseCode - 5} end=${baseCode + 4} threshold=${threshold.toFixed(6)} target=${target.toFixed(6)} wide=0`);
    handleLine(`NULLING_CONFIRM_STEP ch=${channel} sensor=${sensor} code=${baseCode} voltage=${target.toFixed(9)} delta=${threshold.toFixed(6)} valid=1 aboveMin=1 crossed=1 write=1`);
    handleLine(`NULLING_CONFIRM_OK ch=${channel} sensor=${sensor} code=${baseCode} voltage=${target.toFixed(9)} delta=${threshold.toFixed(6)} threshold=${threshold.toFixed(6)} target=${target.toFixed(6)} mode=baseline_threshold_verified`);
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

export function handleMockCommand(command) {
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
  if (command.startsWith("SET_CH_ADDRESS_JSON ")) {
    const payload = safeJson(command.slice("SET_CH_ADDRESS_JSON ".length));
    if (payload?.chId) state.info = { ...(state.info || {}), targetChId: payload.chId };
    handleLine(`GLD_CMD_ACK_JSON ${JSON.stringify({ ...mockAck("SET_CH_ADDRESS", "ok", Boolean(payload?.reboot)), chId: payload?.chId })}`);
    emitMockInfo();
  }
  if (command.startsWith("SET_APP_CONFIG_JSON ")) {
    handleLine(`GLD_CMD_ACK_JSON ${JSON.stringify(mockAck("SET_APP_CONFIG", "ok", true))}`);
  }
  if (command.startsWith("SET_NULLING_CONFIG_JSON ")) {
    const payload = safeJson(command.slice("SET_NULLING_CONFIG_JSON ".length));
    state.mockNullingConfig = {
      thresholdV: payload?.thresholdV ?? state.mockNullingConfig?.thresholdV ?? 0.00001,
      minFinalV: payload?.minFinalV ?? state.mockNullingConfig?.minFinalV ?? 0
    };
    handleLine(`GLD_CMD_ACK_JSON ${JSON.stringify(mockAck("SET_NULLING_CONFIG", "ok", false))}`);
  }
}

export function toggleMock() {
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
