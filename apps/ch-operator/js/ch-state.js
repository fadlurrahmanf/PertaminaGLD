// Central mutable state, shared constants, and DOM handles for the CH
// (ClusterHead) operator. Other modules import `state` / `elements` and
// mutate the same references. Serial-only: there is no MQTT or WiFi here.

export const $ = (id) => document.getElementById(id);

// The GLD operator app enforces this: a CH address must never collide with
// the reserved root gateway id. Keep in sync with
// firmware/config/ChConfig.h (PGL_CH_ROOT_GATEWAY_ID).
export const RESERVED_GATEWAY_ID = "006F";

// Poll cadence for GET_STATUS / GET_NODES when polling is on. The CH cache
// report interval is 10 s, so there is no value polling much faster.
export const DEFAULT_POLL_INTERVAL_MS = 3000;
export const SERIAL_RESPONSE_TIMEOUT_MS = 5000;

// A GLD NodeCache entry older than this is stale (firmware
// NODE_STALE_AFTER_MS in firmware/config/ChConfig.h).
export const NODE_STALE_AFTER_MS = 300000;

export const BATT_HISTORY_MAX = 120;

export const state = {
  connected: false,
  bridgeAvailable: false,
  bridgeReconnecting: false,
  bridgeFeatures: {},
  bridgeSlots: {},
  eventSource: null,
  bridgeHealthTimer: null,
  activeSlot: 1,

  logs: [],
  logPaused: false,
  logPausedCount: 0,

  polling: false,
  pollTimer: null,

  pendingAck: null, // { cmd, resolve, reject, timer }

  // Live device snapshot, assembled from CH_* log lines and/or CH_*_JSON.
  info: { chId: "", rootGatewayId: "", firmwareVersion: "", protocolVersion: "", caps: "" },
  status: { state: "", stateReason: "", batteryMv: null, uptimeSec: null, parentId: "", parentRssi: null, parentSnr: null, meshDepth: null,
    // Approximate last-contact time with the active parent (hello ack or a
    // fresh CH_PARENT_SELECT), used only to estimate the firmware's own
    // PARENT_HEALTH_TIMEOUT_MS countdown - not the exact value the firmware
    // tracks internally, since that also updates on frames this app can't see.
    parentLastSeenAt: null },
  nodes: new Map(),   // key: nodeId hex -> { nodeId, seq, alarm, extPower, unsent, ageMs, seenAt, rssi, snr }
  parents: new Map(), // key: candidate id hex -> { id, parent, depth, rssi, snr, battMv, caps, seenAt }
  battHistory: [],
  // Transient CH_STAR_RX reading waiting to be attached to the node it
  // belongs to (see applyStarRx/applyCacheEntry in ch-protocol.js). Not
  // stored in the firmware's NodeCache - display-only, app-side.
  pendingStarSample: null,
  // CH_HELLO countdown to the parent, derived purely from log lines - the
  // app has no direct access to the firmware's own nextHelloDueMs.
  // intervalMs/jitterMs come from the boot-time CH_ACK_PROFILE line;
  // failureCount/threshold come from CH_HELLO_ACK_REPROBE once the CH has
  // ever missed a hello ack.
  // lastResult tracks the outcome of the most recent hello attempt:
  // "waiting" (sent, ack pending), "ack" (parent answered), or "failed"
  // (retries exhausted, will reprobe or has triggered failover).
  hello: { lastTxAt: null, nextDueAt: null, intervalMs: null, jitterMs: null, healthTimeoutMs: null,
    failureCount: 0, threshold: null, lastResult: null, lastResultAt: null },
  // CH_CONFIG_REQUEST (parent discovery) countdown. Only fires while JOINING
  // or PARENT_FAILOVER - once JOINED there is nothing left to search for.
  // lastResult mirrors the most recent CH_PARENT_SELECT outcome: "found"
  // (a parent was selected) or "no-candidate" (window closed, nobody heard).
  configSearch: { lastTxAt: null, nextDueAt: null, active: false, lastResult: null, lastResultAt: null, lastResultParent: null },
  // Last MSG_SERVER_PULL_REQUEST this CH observed (served or relayed). This
  // CH never originates one - only the Gateway does - so this is read-only
  // telemetry, not a command the operator can trigger from this app.
  // Shape: { phase: "processing"|"done", relayedOnly, requestId, status,
  //          dataStatus, records, responseSize, onwardQueued,
  //          requestedAt, respondedAt }
  lastPull: null,

  expertUnlocked: false,
  manifest: null,
  manifestFiles: new Map()
};

export const elements = {};

// Resolve every id referenced by the app once, at import time.
const ELEMENT_IDS = [
  "connectionBadge", "bridgeBadge", "portBadge", "chIdBadge", "stateBadge", "parentBadge", "battBadge",
  "settingsBtn", "portSetupBtn", "themeToggleBtn",
  "banner", "bannerText", "bannerDismiss",
  "refreshOverviewBtn", "pollToggleBtn",
  "ovStateHeadline", "ovStateDetail", "ovBatt", "ovUptime", "ovNodeCount", "ovNodeUnsent",
  "ovChId", "ovRootGw", "ovFirmware", "ovProtocol", "ovCaps",
  "ovHelloLast", "ovHelloCountdown", "ovHelloFailures", "ovConfigLast", "ovConfigCountdown",
  "ovParent", "ovParentRssi", "ovParentSnr", "ovDepth", "battChart",
  "starBeginStatus", "starFreqValue", "starBwSfCr", "starSyncValue",
  "meshBeginStatus", "meshFreqValue", "meshBwSfCr", "meshSyncValue",
  "ovPullRequested", "ovPullData", "pullStep1", "pullStep2", "pullStep3", "pullStep3Label",
  "refreshNodesBtn", "nodesBody",
  "sendHelloBtn", "clearParentBtn", "forceFailoverBtn", "parentsBody",
  "pullSeenAt", "pullRequestId", "pullStatus", "pullDataStatus", "pullRecords", "pullOnwardQueued",
  "pauseLogBtn", "downloadLogBtn", "saveLogBtn", "clearLogBtn", "serialLog",
  "lockBtn", "expertLockNote", "expertInput", "expertSendBtn",
  "fwTargetId", "fwPickBtn", "fwUploadBtn", "fwStatus",
  "setupBackdrop", "setupPanel", "closeSetupBtn", "baudInput", "portSelect",
  "manualPortInput", "useManualPortBtn", "portDetail", "refreshPortsBtn", "connectBtn", "disconnectBtn",
  "settingsBackdrop", "settingsPanel", "closeSettingsBtn",
  "setChId", "setRootGw", "applyChIdBtn", "applyRootGwBtn",
  "starFreq", "starBw", "starSf", "starCr", "starSync", "starTx", "applyStarLoraBtn",
  "meshFreq", "meshBw", "meshSf", "meshCr", "meshSync", "meshTx", "applyMeshLoraBtn",
  "settingsRestartBtn", "settingsDebugOnBtn", "settingsDebugOffBtn"
];

for (const id of ELEMENT_IDS) elements[id] = $(id);

export const decoder = new TextDecoder();

// Validate a 4-hex CH/gateway address the way the GLD operator does.
export function normalizeHexId(value) {
  return String(value || "").trim().toUpperCase();
}

export function validateChAddress(value) {
  const id = normalizeHexId(value);
  if (!/^[0-9A-F]{4}$/.test(id)) return { ok: false, message: "must be exactly 4 hex digits" };
  if (id === "0000" || id === "FFFF") return { ok: false, message: "0000 and FFFF are reserved" };
  if (id === RESERVED_GATEWAY_ID) return { ok: false, message: `${RESERVED_GATEWAY_ID} is the reserved root gateway id` };
  return { ok: true, id };
}
