// Central mutable state + shared constants. Other modules import `state`
// and `elements` and mutate them directly (both are plain objects, so the
// same reference is shared across every module that imports them).

export const $ = (id) => document.getElementById(id);

export const CHART_COLORS = [
  "#ffa400",
  "#4fd8e0",
  "#ff8a3d",
  "#8fd6ff",
  "#c9a4ff",
  "#ffd166",
  "#6bd47a",
  "#ff6b6b"
];

export const SENSOR_NAMES = ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"];

export const DATASET_WIZARD_LABELS = ["Switch Mode", "Confirm Config", "Start", "Capturing", "Stop", "Save"];
export const SENSOR_MUX_CHANNELS = [7, 6, 5, 0, 1, 2, 3, 4];
export const SENSOR_STATUS_NAMES = {
  0: "Ok",
  1: "NotReady",
  2: "DrdyTimeout",
  3: "InvalidChannel"
};

// Default poll interval matches the firmware's own sensor scan cadence
// (GLD_SCAN_INTERVAL_MS in firmware/config/GldConfig.h), not an arbitrary
// round number - polling faster than the GLD actually samples just repeats
// stale GET_STATUS replies.
export const DEFAULT_POLL_INTERVAL_MS = 500;

export let SERIAL_RESPONSE_TIMEOUT_MS = 5000;
export let DATASET_RUNTIME_READY_TIMEOUT_MS = 40000;
export let DATASET_WAITING_STUCK_MS = 7000;
const TIMEOUTS_STORAGE_KEY = "gldOperatorWeb.timeouts";

export function loadTimeoutOverrides() {
  try {
    const saved = JSON.parse(localStorage.getItem(TIMEOUTS_STORAGE_KEY) || "{}");
    if (Number.isFinite(saved.serialResponseMs) && saved.serialResponseMs > 0) SERIAL_RESPONSE_TIMEOUT_MS = saved.serialResponseMs;
    if (Number.isFinite(saved.datasetReadyMs) && saved.datasetReadyMs > 0) DATASET_RUNTIME_READY_TIMEOUT_MS = saved.datasetReadyMs;
    if (Number.isFinite(saved.datasetStuckMs) && saved.datasetStuckMs > 0) DATASET_WAITING_STUCK_MS = saved.datasetStuckMs;
  } catch {}
}

export function applyTimeoutOverrides(serialResponseMs, datasetReadyMs, datasetStuckMs) {
  if (serialResponseMs > 0) SERIAL_RESPONSE_TIMEOUT_MS = serialResponseMs;
  if (datasetReadyMs > 0) DATASET_RUNTIME_READY_TIMEOUT_MS = datasetReadyMs;
  if (datasetStuckMs > 0) DATASET_WAITING_STUCK_MS = datasetStuckMs;
  localStorage.setItem(TIMEOUTS_STORAGE_KEY, JSON.stringify({ serialResponseMs, datasetReadyMs, datasetStuckMs }));
}

export function initialDatasetSession() {
  return {
    active: false,
    state: "Idle",
    phase: "No active session",
    sessionId: "",
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
    configConfirmed: false,
    saved: false,
    nullingFirst: false,
    lastEvent: "No dataset command sent.",
    error: ""
  };
}

export const MAX_FLEET_SLOTS = 8;

export function makeFleetSlot(slot) {
  return { slot, port: "", deviceId: "", mode: "unknown", gas: "n/a", alarm: false, connected: false };
}

export function ensureFleetSlot(slot) {
  if (!state.fleet[slot]) state.fleet[slot] = makeFleetSlot(slot);
  return state.fleet[slot];
}

export const state = {
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
  bridgeSlots: {},
  eventSource: null,
  buffer: "",
  logs: [],
  logPaused: false,
  logPausedCount: 0,
  pendingSerialRequest: null,
  datasetRuntime: {
    mode: false,
    ready: false,
    mqtt: false
  },
  datasetReadyWaiters: [],
  // Dataset capture is delivered over MQTT, so Apply GLD Settings (WiFi/MQTT)
  // must succeed at least once this session before Confirm Config unlocks -
  // this is not part of initialDatasetSession() because it should survive
  // Clear Session (re-applying WiFi/MQTT on every take would be tedious).
  datasetGldConfigApplied: false,
  dataset: initialDatasetSession(),
  datasetWizard: ["pending", "pending", "pending", "pending", "pending", "pending"],
  nullingLogs: [],
  nullingExpandedChannels: new Set(),
  bootDiagnostics: {
    reportSeen: false,
    bootRows: {},
    probes: {},
    lastLine: ""
  },
  mockNullingStep: 0,
  qc: {
    channels: Array.from({ length: 8 }, (_, index) => ({
      channel: index, sensor: SENSOR_NAMES[index], nullingOk: false, tested: false, pass: false, timestamp: ""
    })),
    activeTab: "all",
    activeGroup: "mq",
    latchOn: false,
    tplAutoInject: false
  },
  history: [],
  info: null,
  status: null,
  alarmActive: false,
  alarmMuted: false,
  alarmAudioContext: null,
  alarmLastBeep: 0,
  mode: "unknown",
  pendingMqttMode: "",
  expertUnlocked: false,
  manifest: null,
  manifestPackageFiles: new Map(),
  bridgeHealthTimer: null,
  bridgeReconnecting: false,
  activeSlot: 1,
  fleet: {}
};
state.fleet[1] = makeFleetSlot(1);

export const encoder = new TextEncoder();
export const decoder = new TextDecoder();

export const elements = {
  portSetupBtn: $("portSetupBtn"),
  closeSetupBtn: $("closeSetupBtn"),
  setupPanel: $("setupPanel"),
  connectBtn: $("connectBtn"),
  disconnectBtn: $("disconnectBtn"),
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
  sensorChannelsLeft: $("sensorChannelsLeft"),
  sensorChannelsRight: $("sensorChannelsRight"),
  datasetChart: $("datasetChart"),
  datasetRangeSelect: $("datasetRangeSelect"),
  datasetLegend: $("datasetLegend"),
  datasetWizard: $("datasetWizard"),
  topDeviceStatus: $("topDeviceStatus"),
  topModeStatus: $("topModeStatus"),
  sideDeviceSummary: $("sideDeviceSummary"),
  sidePortSummary: $("sidePortSummary"),
  bridgeBadge: $("bridgeBadge"),
  globalBanner: $("globalBanner"),
  globalBannerText: $("globalBannerText"),
  globalBannerDismiss: $("globalBannerDismiss"),
  firmwareLockStatus: $("firmwareLockStatus"),
  firmwarePortStatus: $("firmwarePortStatus"),
  checkPortLockBtn: $("checkPortLockBtn"),
  testMqttBtn: $("testMqttBtn"),
  mqttTestStatus: $("mqttTestStatus"),
  runNullingNowBtn: $("runNullingNowBtn"),
  fleetCountBadge: $("fleetCountBadge"),
  fleetExtra: $("fleetExtra"),
  addSlotBtn: $("addSlotBtn"),
  activeSlotLabel: $("activeSlotLabel"),
  qcSubnavTrack: $("qcSubnavTrack"),
  qcPanels: $("qcPanels")
};
