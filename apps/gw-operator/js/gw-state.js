// Central mutable state, shared constants, and DOM handles for the Gateway
// operator. Other modules import `state` / `elements` and mutate the same
// references. The Gateway exposes a small serial provisioning surface for
// staged Wi-Fi/MQTT setup; operational data still flows over MQTT.

export const $ = (id) => document.getElementById(id);

// Build default. Current firmware can persist a different 0001-000F identity
// in NVS through SET_GATEWAY_ADDRESS_JSON.
export const DEFAULT_GATEWAY_ID = "0001";

export const UPLINK_HISTORY_MAX = 300;
export const TOPOLOGY_HISTORY_MAX = 300;
export const COMMAND_LOG_MAX = 200;

// firmware/config/GwConfig.h STATUS_INTERVAL_MS - a status message should
// arrive roughly this often once the gateway is on air.
export const STATUS_INTERVAL_MS = 10000;
export const STATUS_STALE_AFTER_MS = 30000;

export const state = {
  bridgeAvailable: false,
  bridgeReconnecting: false,
  bridgeFeatures: {},
  eventSource: null,
  bridgeHealthTimer: null,
  activeSlot: 1,

  logs: [],
  logPaused: false,
  logPausedCount: 0,
  serialConnected: false,
  wifiVerified: false,
  wifiIp: "",
  meshLoraDirty: false,
  gatewayId: DEFAULT_GATEWAY_ID,

  mqttConnected: false,
  mqttConfig: { host: "", port: 1884, username: "", password: "", topicRoot: "gld/gateway" },

  // Latest {kind:"gateway-status", gatewayId, state, wifi, mqtt, meshReady,
  // mqttQueueDepth, mqttQueueDropped, mqttQueuePublished, ip} payload.
  status: null,
  statusReceivedAt: null,

  // Newest-first ring buffer of decoded gateway uplink JSON payloads.
  uplinks: [],
  // Newest-first ring buffer of decoded topology events (CH_HELLO /
  // CH_CONFIG_REQUEST / CH_CONFIG_RESPONSE).
  topologyEvents: [],
  // Latest known state per CH, keyed by chId hex string, derived from
  // topologyEvents: { chId, parentId, batteryMv, rssi, snr, reportType, seenAt }.
  topologyNodes: new Map(),

  // Sent pull/node downlink commands, newest first, for the Commands tab log.
  commandLog: [],

  expertUnlocked: false,
  manifest: null,
  manifestFiles: new Map()
};

export const elements = {};

const ELEMENT_IDS = [
  "connectionBadge", "bridgeBadge", "mqttBadge", "gatewayMqttBadge", "gatewayIdBadge", "stateBadge", "queueBadge",
  "brokerSetupBtn", "themeToggleBtn",
  "banner", "bannerText", "bannerDismiss",

  // Overview
  "ovStateHeadline", "ovStateDetail", "ovGatewayId", "ovFirmware", "ovProtocol", "ovUptime", "ovIp", "ovWifi", "ovMqtt", "ovMeshReady",
  "ovQueueDepth", "ovQueueCapacity", "ovQueueDropped", "ovQueuePublished", "ovStatusAge",
  "ovWifiSsid", "ovWifiRssi", "ovWifiChannel", "ovWifiMac",
  "ovMqttBroker", "ovMqttState", "ovMqttAuth", "ovMqttSubscriptions", "ovMqttTopicRoot",
  "ovMeshFrequency", "ovMeshBandwidth", "ovMeshModulation", "ovMeshRadioDetail", "refreshOverviewBtn",

  // Uplinks
  "uplinksBody", "clearUplinksBtn",

  // Topology
  "topologyNodesBody", "topologyEventsBody", "clearTopologyBtn",

  // Commands
  "pullHopList", "pullCluster", "pullRequestId", "sendPullBtn",
  "nodeCluster", "nodeId", "nodeTtl", "nodeHex", "nodeHopList", "sendNodeBtn",
  "commandLogBody", "clearCommandLogBtn",

  // Boot log
  "pauseLogBtn", "downloadLogBtn", "saveLogBtn", "clearLogBtn", "bootLog",

  // Firmware
  "fwEnvSelect", "fwTargetId", "fwPickBtn", "fwUploadBtn", "fwStatus", "lockBtn", "expertLockNote",

  // Broker Setup drawer
  "setupBackdrop", "setupPanel", "closeSetupBtn",
  "serialSetupStep", "gatewayIdentitySetupStep", "wifiSetupStep", "mqttSetupStep", "mqttLockNote", "meshLoraSetupStep",
  "gatewayCurrentId", "gatewayIdInput", "gatewayIdLoadBtn", "gatewayIdApplyBtn", "gatewayIdStatus",
  "mqttHost", "mqttPort", "mqttUsername", "mqttPassword", "mqttTopicRoot",
  "mqttConnectBtn", "mqttDisconnectBtn", "mqttTestBtn", "mqttSetupDetail", "useThisPcBtn",
  "gwWifiSsid", "gwWifiPassword", "gwUseThisWifiBtn",
  "gwApplyWifiBtn", "gwTestWifiBtn", "gwApplyWifiStatus",
  "gwApplyMqttBtn", "gwApplyMqttStatus",
  "meshSetFreq", "meshSetBw", "meshSetSf", "meshSetCr", "meshSetSync", "meshSetTx",
  "meshLoadBtn", "meshApplyBtn", "meshApplyStatus",
  "baudInput", "portSelect", "manualPortInput", "useManualPortBtn", "portDetail",
  "refreshPortsBtn", "connectSerialBtn", "disconnectSerialBtn"
];

for (const id of ELEMENT_IDS) elements[id] = $(id);

export function normalizeHexId(value) {
  return String(value ?? "").trim().toUpperCase();
}

export function isHexId(value) {
  return /^[0-9A-F]{1,4}$/.test(normalizeHexId(value));
}
