// Decodes and renders the gateway's MQTT payloads. There is no serial
// command/ack protocol to parse here (see gw-state.js header) — everything
// below is driven by the JSON the gateway firmware publishes itself:
//   {root}/status   -> publishStatus()          (GatewayMqttMeshMain.cpp)
//   {root}/uplink    -> publishMeshFrame()
//   {root}/topology  -> publishTopologyReport()
// Field names mirror the firmware source directly (with a couple of
// defensive aliases) rather than any downstream Node-RED normalization.

import { elements, state, normalizeHexId, UPLINK_HISTORY_MAX, TOPOLOGY_HISTORY_MAX, COMMAND_LOG_MAX, STATUS_STALE_AFTER_MS } from "./gw-state.js";
import { setBadge } from "./gw-ui.js";

// firmware/shared/include/ProtocolConstants.h message type IDs.
const MSG_TYPE_NAMES = {
  0x10: "SENSOR_DATA",
  0x14: "NODE_DOWNLINK",
  0x30: "SERVER_PULL_REQUEST",
  0x31: "CLUSTER_DATA_RESPONSE",
  0x32: "SERVER_NODE_COMMAND",
  0x33: "CH_HELLO",
  0x34: "CH_CONFIG_REQUEST",
  0x35: "CH_CONFIG_RESPONSE",
  0x36: "CH_HELLO_ACK"
};

function msgTypeName(value) {
  if (value === undefined || value === null) return "—";
  const num = Number(value);
  const base = num & 0x3f;
  return MSG_TYPE_NAMES[base] || `0x${base.toString(16).toUpperCase().padStart(2, "0")}`;
}

function hexId(value) {
  if (value === undefined || value === null || value === "") return "—";
  if (typeof value === "string" && /^0x/i.test(value)) return normalizeHexId(value.replace(/^0x/i, ""));
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  return num.toString(16).toUpperCase().padStart(4, "0");
}

function fmtRssiSnr(rssi, snr) {
  const r = rssi === undefined || rssi === null ? "—" : `${rssi} dBm`;
  const s = snr === undefined || snr === null ? "—" : `${snr} dB`;
  return `${r} / ${s}`;
}

function nowIso() {
  return new Date().toLocaleTimeString();
}

// ---- Status ----------------------------------------------------------------

export function handleStatus(json) {
  if (!json) return;
  state.status = json;
  state.statusReceivedAt = Date.now();
  renderOverview();
}

export function renderOverview() {
  const s = state.status;
  const el = elements;
  if (!s) {
    el.ovStateHeadline.textContent = "no status yet";
    el.ovStateDetail.textContent = "Connect to the site MQTT broker and wait for the next status publish (every ~10 s).";
    setBadge(el.stateBadge, "—");
    return;
  }
  el.ovStateHeadline.textContent = s.state || "unknown";
  el.ovStateDetail.textContent = `gatewayId ${hexId(s.gatewayId)}`;
  el.ovGatewayId.textContent = hexId(s.gatewayId);
  el.ovFirmware.textContent = s.firmwareVersion || "—";
  el.ovProtocol.textContent = s.protocolVersion ?? "—";
  el.ovUptime.textContent = s.uptimeMs === undefined ? "—" : `${Math.round(Number(s.uptimeMs) / 1000)} s`;
  el.ovIp.textContent = s.ip || "—";
  el.ovWifi.textContent = s.wifi ? "up" : "down";
  el.ovMqtt.textContent = s.mqtt ? "up" : "down";
  el.ovMeshReady.textContent = s.meshReady ? "ready" : "not ready";
  el.ovQueueDepth.textContent = s.mqttQueueDepth ?? "—";
  el.ovQueueCapacity.textContent = s.mqttQueueCapacity ?? "—";
  el.ovQueueDropped.textContent = s.mqttQueueDropped ?? "0";
  el.ovQueuePublished.textContent = s.mqttQueuePublished ?? "—";
  el.ovWifiSsid.textContent = s.wifiSsid || "—";
  el.ovWifiRssi.textContent = s.wifiRssi === undefined ? "—" : `${s.wifiRssi} dBm`;
  el.ovWifiChannel.textContent = s.wifiChannel ?? "—";
  el.ovWifiMac.textContent = s.wifiMac || "—";
  el.ovMqttBroker.textContent = s.mqttHost ? `${s.mqttHost}:${s.mqttPort ?? 1884}` : "—";
  el.ovMqttState.textContent = s.mqttState ?? "—";
  el.ovMqttAuth.textContent = s.mqttAuthConfigured ? "configured" : "not configured";
  el.ovMqttSubscriptions.textContent = s.mqttSubscriptionsReady ? "ready" : "not ready";
  el.ovMqttTopicRoot.textContent = s.topicRoot || "—";
  el.ovMeshFrequency.textContent = s.meshFreqMhz === undefined ? "—" : `${s.meshFreqMhz} MHz`;
  el.ovMeshBandwidth.textContent = s.meshBandwidthKhz === undefined ? "—" : `${s.meshBandwidthKhz} kHz`;
  el.ovMeshModulation.textContent = s.meshSpreadingFactor === undefined ? "—" : `SF${s.meshSpreadingFactor} / CR 4/${s.meshCodingRate}`;
  el.ovMeshRadioDetail.textContent = s.meshSyncWord === undefined ? "—" : `0x${Number(s.meshSyncWord).toString(16).toUpperCase()} / ${s.meshTxPowerDbm} dBm / ${s.meshPreamble}`;

  setBadge(el.gatewayIdBadge, hexId(s.gatewayId));
  setBadge(el.gatewayMqttBadge, s.mqtt ? "connected" : "disconnected", s.mqtt ? "ok" : "warn");
  setBadge(el.stateBadge, s.state || "unknown", s.wifi && s.mqtt ? "ok" : "warn");
  setBadge(el.queueBadge, `${s.mqttQueueDepth ?? 0}q`, Number(s.mqttQueueDropped || 0) > 0 ? "warn" : "");
  tickStatusAge();
}

export function tickStatusAge() {
  const el = elements.ovStatusAge;
  if (!el) return;
  if (!state.statusReceivedAt) {
    el.textContent = "no status yet";
    return;
  }
  const ageMs = Date.now() - state.statusReceivedAt;
  el.textContent = `${Math.round(ageMs / 1000)}s ago`;
  el.classList.toggle("warn", ageMs > STATUS_STALE_AFTER_MS);
}

// ---- Uplinks -----------------------------------------------------------

export function handleUplink(json, rawPayload) {
  const entry = json || { raw: rawPayload, parseStatus: "unparsed" };
  entry._receivedAt = Date.now();
  state.uplinks.unshift(entry);
  if (state.uplinks.length > UPLINK_HISTORY_MAX) state.uplinks.length = UPLINK_HISTORY_MAX;
  renderUplinks();
  if (entry.topology) handleTopologyEvent(entry.topology, entry);
}

export function renderUplinks() {
  const body = elements.uplinksBody;
  if (!body) return;
  if (!state.uplinks.length) {
    body.innerHTML = `<tr><td class="empty" colspan="8">No uplinks yet. Connect to the MQTT broker and wait for a mesh frame.</td></tr>`;
    return;
  }
  body.innerHTML = state.uplinks
    .map((u) => {
      const time = new Date(u._receivedAt).toLocaleTimeString();
      const ok = String(u.parseStatus || "").toLowerCase() === "ok" || u.parseStatus === undefined;
      return `<tr class="${ok ? "" : "stale"}">
        <td>${time}</td>
        <td>${msgTypeName(u.msgType ?? u.typeFlags)}</td>
        <td>${hexId(u.srcId)}</td>
        <td>${hexId(u.dstId)}</td>
        <td>${u.seq ?? "—"}</td>
        <td>${u.payloadLen ?? "—"}</td>
        <td>${fmtRssiSnr(u.rssi, u.snr)}</td>
        <td>${u.parseStatus || (ok ? "ok" : "—")}</td>
      </tr>`;
    })
    .join("");
}

export function clearUplinks() {
  state.uplinks = [];
  renderUplinks();
}

// ---- Topology ------------------------------------------------------------

// firmware/shared/include/ProtocolConstants.h CH_CONFIG_CAP_* bits.
const CAP_BITS = [
  [0x01, "ROUTE_TO_ROOT"],
  [0x02, "HELLO_ACK_V1"],
  [0x04, "ALARM_ACK_NODE_ID_V1"],
  [0x08, "NODE_COMMAND_ROUTE_V1"]
];

function decodeCaps(flags) {
  if (flags === undefined || flags === null) return "—";
  const n = Number(flags);
  const names = CAP_BITS.filter(([bit]) => (n & bit) !== 0).map(([, name]) => name);
  return names.length ? names.join(", ") : "none";
}

export function handleTopologyEvent(json, uplinkContext) {
  const entry = { ...(json || {}), _receivedAt: Date.now() };
  if (uplinkContext) {
    entry.rssi = entry.rssi ?? uplinkContext.rssi;
    entry.snr = entry.snr ?? uplinkContext.snr;
  }
  state.topologyEvents.unshift(entry);
  if (state.topologyEvents.length > TOPOLOGY_HISTORY_MAX) state.topologyEvents.length = TOPOLOGY_HISTORY_MAX;

  const chId = hexId(entry.chId ?? entry.edgeFrom ?? entry.srcId);
  if (chId && chId !== "—") {
    state.topologyNodes.set(chId, {
      chId,
      parentId: hexId(entry.parentId ?? entry.edgeTo),
      batteryMv: entry.batteryMv,
      rssi: entry.rssi,
      snr: entry.snr,
      reportType: entry.reportType || msgTypeName(entry.msgType),
      caps: entry.routeFlags ?? entry.capabilityFlags,
      seenAt: entry._receivedAt
    });
  }
  renderTopology();
}

export function renderTopology() {
  renderTopologyNodes();
  renderTopologyEvents();
}

function renderTopologyNodes() {
  const body = elements.topologyNodesBody;
  if (!body) return;
  const rows = Array.from(state.topologyNodes.values()).sort((a, b) => b.seenAt - a.seenAt);
  if (!rows.length) {
    body.innerHTML = `<tr><td class="empty" colspan="7">No CH topology events observed yet.</td></tr>`;
    return;
  }
  body.innerHTML = rows
    .map((n) => {
      const ageMs = Date.now() - n.seenAt;
      const stale = ageMs > 300000;
      return `<tr class="${stale ? "stale" : ""}">
        <td>${n.chId}</td>
        <td>${n.parentId}</td>
        <td>${n.batteryMv ?? "—"}</td>
        <td>${fmtRssiSnr(n.rssi, n.snr)}</td>
        <td>${n.reportType || "—"}</td>
        <td>${decodeCaps(n.caps)}</td>
        <td>${Math.round(ageMs / 1000)}s ago</td>
      </tr>`;
    })
    .join("");
}

function renderTopologyEvents() {
  const body = elements.topologyEventsBody;
  if (!body) return;
  if (!state.topologyEvents.length) {
    body.innerHTML = `<tr><td class="empty" colspan="6">No topology events yet.</td></tr>`;
    return;
  }
  body.innerHTML = state.topologyEvents
    .map((e) => `<tr>
        <td>${new Date(e._receivedAt).toLocaleTimeString()}</td>
        <td>${e.reportType || msgTypeName(e.msgType)}</td>
        <td>${hexId(e.chId ?? e.edgeFrom)}</td>
        <td>${hexId(e.parentId ?? e.edgeTo)}</td>
        <td>${e.batteryMv ?? "—"}</td>
        <td>${fmtRssiSnr(e.rssi, e.snr)}</td>
      </tr>`)
    .join("");
}

export function clearTopology() {
  state.topologyEvents = [];
  state.topologyNodes.clear();
  renderTopology();
}

// ---- Command log -----------------------------------------------------------

export function logCommand(kind, topic, payload) {
  state.commandLog.unshift({ kind, topic, payload, at: Date.now() });
  if (state.commandLog.length > COMMAND_LOG_MAX) state.commandLog.length = COMMAND_LOG_MAX;
  renderCommandLog();
}

export function renderCommandLog() {
  const body = elements.commandLogBody;
  if (!body) return;
  if (!state.commandLog.length) {
    body.innerHTML = `<tr><td class="empty" colspan="4">No commands sent yet.</td></tr>`;
    return;
  }
  body.innerHTML = state.commandLog
    .map((c) => `<tr>
        <td>${new Date(c.at).toLocaleTimeString()}</td>
        <td>${c.kind}</td>
        <td>${c.topic}</td>
        <td>${JSON.stringify(c.payload)}</td>
      </tr>`)
    .join("");
}

export function clearCommandLog() {
  state.commandLog = [];
  renderCommandLog();
}

export { hexId, msgTypeName, nowIso };
