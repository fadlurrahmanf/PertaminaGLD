const fs = require("fs");
const http = require("http");
const path = require("path");

const args = new Map();
for (let i = 2; i < process.argv.length; i++) {
  const arg = process.argv[i];
  if (arg.startsWith("--")) {
    const key = arg.slice(2);
    const next = process.argv[i + 1];
    if (!next || next.startsWith("--")) {
      args.set(key, true);
    } else {
      args.set(key, next);
      i++;
    }
  }
}

const repoDir = path.resolve(__dirname, "..", "..");
const scriptDir = __dirname;
const decodeFunction = fs.readFileSync(path.join(scriptDir, "functions", "pertamina-gld-decode.js"), "utf8");
const commandFunction = fs.readFileSync(path.join(scriptDir, "functions", "pertamina-gld-build-command.js"), "utf8");
const generatorVersion = "2.0.0";

const nodeRedUrl = args.get("node-red-url") || "http://127.0.0.1:1880";
const nodeRedUserDir = args.get("node-red-user-dir") || "C:\\Users\\asus\\.node-red";
const gatewayStatusUrl = args.get("gateway-status-url") || "http://192.168.4.1/api/status";
const gatewayBaseUrl = args.get("gateway-base-url") || "http://192.168.4.1";
const mqttHost = args.get("mqtt-host") || "127.0.0.1";
const mqttPort = String(args.get("mqtt-port") || "1884");
const mqttUser = args.get("mqtt-user") || process.env.MQTT_USER || "";
const mqttPassword = args.get("mqtt-password") || process.env.MQTT_PASS || "";
const generateOnly = args.has("generate-only");
const checkOnly = args.has("check");
const enableGatewayPoll = args.has("enable-gateway-poll");
const nodeRedToken = args.get("node-red-token") || process.env.NODE_RED_ADMIN_TOKEN || "";
const mqttTls = args.has("mqtt-tls");
const mqttTlsInsecure = args.has("mqtt-tls-insecure");
const mqttCaPath = String(args.get("mqtt-ca") || "");
const replayStatePath = String(args.get("replay-state-path") || path.join(nodeRedUserDir, "pertamina-gld-replay-state.json"));

function isLoopbackHost(host) {
  return ["127.0.0.1", "localhost", "::1"].includes(String(host).trim().toLowerCase());
}

if (!isLoopbackHost(mqttHost) && !mqttTls && !args.has("allow-insecure-mqtt")) {
  throw new Error("Remote MQTT requires --mqtt-tls; use --allow-insecure-mqtt only for an explicitly isolated bench network");
}
if ((mqttUser && !mqttPassword) || (!mqttUser && mqttPassword)) {
  throw new Error("MQTT username and password must be provided together");
}
if (!isLoopbackHost(mqttHost) && !mqttUser) {
  throw new Error("Remote MQTT requires explicit credentials");
}

function id(name) {
  return `pgl_${name}`;
}

const tab = id("tab");
const broker = id("mqtt_broker");

function nodeBase(type, name, extra) {
  return Object.assign({ id: id(name), type, z: tab }, extra);
}

const topologyJsonFunction = `function idHex(value) {
  const n = Number(value) & 0xFFFF;
  return "0x" + n.toString(16).toUpperCase().padStart(4, "0");
}

const gatewayIdHex = idHex(Number(env.get("PGL_GATEWAY_ID") || "0x006F"));
const topology = flow.get("pglTopology") || {
  gatewayIdHex,
  parents: {},
  discovery: {},
  gatewayLinks: {},
  hellos: {},
  routes: {},
  updatedAt: null
};
topology.gatewayIdHex = topology.gatewayIdHex || gatewayIdHex;
const directGatewayMinRssiDbm = Number(env.get("PGL_GATEWAY_DIRECT_PARENT_MIN_RSSI_DBM") || "-95");
const directGatewayMinSnrDb = Number(env.get("PGL_GATEWAY_DIRECT_PARENT_MIN_SNR_DB") || "5");
const topologyParentTtlMs = Number(env.get("PGL_TOPOLOGY_PARENT_TTL_MS") || "900000");
const topologyDiscoveryTtlMs = Number(env.get("PGL_TOPOLOGY_DISCOVERY_TTL_MS") || "420000");
const topologyGatewayLinkTtlMs = Number(env.get("PGL_TOPOLOGY_GATEWAY_LINK_TTL_MS") || "420000");

function hasNumber(value) {
  return value !== undefined && value !== null && value !== "" && Number.isFinite(Number(value));
}

function ageMsOf(entry, nowMs = Date.now()) {
  const t = Date.parse(entry && entry.receivedAt);
  return Number.isFinite(t) ? Math.max(0, nowMs - t) : Number.POSITIVE_INFINITY;
}

function pruneMapByTtl(map, ttlMs, nowMs = Date.now()) {
  for (const [key, entry] of Object.entries(map || {})) {
    if (ageMsOf(entry, nowMs) > ttlMs) {
      delete map[key];
    }
  }
}

function newestIso(...values) {
  const valid = values
    .filter(Boolean)
    .map((value) => ({ value, t: Date.parse(value) }))
    .filter((item) => Number.isFinite(item.t))
    .sort((a, b) => b.t - a.t);
  return valid.length > 0 ? valid[0].value : null;
}

topology.parents = topology.parents || {};
topology.discovery = topology.discovery || {};
topology.gatewayLinks = topology.gatewayLinks || {};
topology.hellos = topology.hellos || {};
topology.routes = topology.routes || {};
pruneMapByTtl(topology.parents, topologyParentTtlMs);
pruneMapByTtl(topology.discovery, topologyDiscoveryTtlMs);
pruneMapByTtl(topology.gatewayLinks, topologyGatewayLinkTtlMs);
pruneMapByTtl(topology.hellos, topologyParentTtlMs);
for (const clusterIdHex of Object.keys(topology.routes)) {
  if (!topology.parents[clusterIdHex]) {
    delete topology.routes[clusterIdHex];
  }
}
flow.set("pglTopology", topology);

const nodes = [{
  id: topology.gatewayIdHex,
  label: "GW",
  type: "gateway",
  parent: null,
  depth: 0,
  layer: 0,
  layerLabel: "Layer 0",
  route: [],
  status: "root"
}];

const edges = [];
const installedIds = new Set(Object.keys(topology.parents || {}));
const visibleIds = new Set([topology.gatewayIdHex]);
for (const [clusterIdHex, entry] of Object.entries(topology.parents || {})) {
  const route = Array.isArray((topology.routes || {})[clusterIdHex])
    ? topology.routes[clusterIdHex]
    : [];
  const live = (topology.discovery || {})[clusterIdHex] || null;
  const liveIsGatewayRequest = live &&
    live.report === "ch-config-request" &&
    (live.parentIdHex === "0x0000" || !live.parentIdHex);
  const liveRssi = live && hasNumber(live.rssi) ? Number(live.rssi) : undefined;
  const liveSnr = live && hasNumber(live.snr) ? Number(live.snr) : undefined;
  const liveBattery = live && hasNumber(live.batteryMv) && Number(live.batteryMv) !== 0xFFFF
    ? Number(live.batteryMv)
    : undefined;
  const gatewayLink = (topology.gatewayLinks || {})[clusterIdHex] || null;
  const gatewayRssi = gatewayLink && hasNumber(gatewayLink.rssi) ? Number(gatewayLink.rssi) : undefined;
  const gatewaySnr = gatewayLink && hasNumber(gatewayLink.snr) ? Number(gatewayLink.snr) : undefined;
  const hello = (topology.hellos || {})[clusterIdHex] || (entry.report === "ch-hello" ? entry : null);
  const lastSeenAgeSec = Math.round(ageMsOf(entry) / 1000);
  const lastHelloAgeSec = hello ? Math.round(ageMsOf(hello) / 1000) : undefined;
  const gatewayLinkAgeSec = gatewayLink ? Math.round(ageMsOf(gatewayLink) / 1000) : undefined;
  const parentIdHex = entry.parentIdHex || "0x0000";
  const parentAltIdHex = entry.parentAltIdHex || "0x0000";
  const routeIsInstalled = route.length > 0 &&
    (parentIdHex === topology.gatewayIdHex || parentIdHex === "0x0000" || installedIds.has(parentIdHex));
  const depth = routeIsInstalled ? route.length : null;
  const layer = depth;
  const layerLabel = hasNumber(layer) ? "Layer " + layer : "Discovery";
  const rssiSource = parentIdHex && parentIdHex !== "0x0000" ? parentIdHex : (entry.viaHopHex || topology.gatewayIdHex);
  const rssiTarget = clusterIdHex;
  const rssiLink = rssiSource + " -> " + rssiTarget;
  const displayRssi = !liveIsGatewayRequest && liveRssi !== undefined ? liveRssi : entry.rssi;
  const displaySnr = !liveIsGatewayRequest && liveSnr !== undefined ? liveSnr : entry.snr;
  const linkQualityLabel = displayRssi !== undefined || displaySnr !== undefined
    ? "RSSI to Parent: " + (displayRssi ?? "-") + " dBm, SNR " + (displaySnr ?? "-") + " dB"
    : "RSSI to Parent: belum ada";
  const gatewayQualityLabel = gatewayRssi !== undefined || gatewaySnr !== undefined
    ? "RSSI to Gateway: " + (gatewayRssi ?? "-") + " dBm, SNR " + (gatewaySnr ?? "-") + " dB"
    : "RSSI to Gateway: belum ada";
  const batteryMv = liveBattery !== undefined ? liveBattery : entry.batteryMv;
  const publicRoute = routeIsInstalled ? route : [];
  const pendingReason = routeIsInstalled
    ? null
    : (parentIdHex && parentIdHex !== "0x0000"
      ? "pending: waiting installed route via " + parentIdHex
      : "pending: waiting parent topology");
  nodes.push({
    id: clusterIdHex,
    label: "CH " + clusterIdHex,
    type: "ch",
    parent: parentIdHex,
    parentAlt: parentAltIdHex,
    depth,
    layer,
    layerLabel,
    route: publicRoute,
    routeText: routeIsInstalled ? topology.gatewayIdHex + " -> " + route.join(" -> ") : "installed route pending",
    requestPayload: routeIsInstalled ? { requestId: 1, hopList: route } : null,
    lastHop: routeIsInstalled ? route[route.length - 1] : clusterIdHex,
    report: entry.report,
    rssi: displayRssi,
    snr: displaySnr,
    rssiSource,
    rssiTarget,
    rssiLink,
    linkQualityLabel,
    gatewayRssi,
    gatewaySnr,
    gatewayQualityLabel,
    gatewayLinkUpdatedAt: gatewayLink ? gatewayLink.receivedAt : undefined,
    gatewayLinkAgeSec,
    lastHelloAgeSec,
    lastHelloUpdatedAt: hello ? hello.receivedAt : undefined,
    liveUpdatedAt: live ? live.receivedAt : undefined,
    lastSeenAgeSec,
    batteryMv,
    batteryLabel: batteryMv !== undefined && batteryMv !== null && Number(batteryMv) !== 0xFFFF
      ? "battery: " + batteryMv + " mV"
      : "battery: belum ada",
    pendingReason,
    updatedAt: entry.receivedAt || topology.updatedAt,
    status: routeIsInstalled ? "installed" : "pending"
  });
  visibleIds.add(clusterIdHex);
  if (routeIsInstalled && parentIdHex && parentIdHex !== "0x0000" && parentIdHex !== clusterIdHex) {
    edges.push({
      from: parentIdHex,
      to: clusterIdHex,
      label: parentIdHex + " -> " + clusterIdHex,
      role: "main",
      rssi: displayRssi,
      snr: displaySnr,
      linkQualityLabel
    });
  }
  if (routeIsInstalled && parentAltIdHex && parentAltIdHex !== "0x0000" &&
      parentAltIdHex !== clusterIdHex && parentAltIdHex !== parentIdHex) {
    edges.push({
      from: parentAltIdHex,
      to: clusterIdHex,
      label: parentAltIdHex + " -> " + clusterIdHex,
      role: "alternate",
      linkQualityLabel: "Alternative Parent"
    });
  }
}

for (const [clusterIdHex, event] of Object.entries(topology.discovery || {})) {
  if (visibleIds.has(clusterIdHex)) {
    continue;
  }
  const gatewayLink = (topology.gatewayLinks || {})[clusterIdHex] || null;
  const gatewayRssi = gatewayLink && hasNumber(gatewayLink.rssi) ? Number(gatewayLink.rssi) : undefined;
  const gatewaySnr = gatewayLink && hasNumber(gatewayLink.snr) ? Number(gatewayLink.snr) : undefined;
  const hello = (topology.hellos || {})[clusterIdHex] || null;
  const lastSeenAgeSec = Math.round(ageMsOf(event) / 1000);
  const lastHelloAgeSec = hello ? Math.round(ageMsOf(hello) / 1000) : undefined;
  const gatewayLinkAgeSec = gatewayLink ? Math.round(ageMsOf(gatewayLink) / 1000) : undefined;
  const gatewayQualityLabel = gatewayRssi !== undefined || gatewaySnr !== undefined
    ? "RSSI to Gateway: " + (gatewayRssi ?? "-") + " dBm, SNR " + (gatewaySnr ?? "-") + " dB"
    : "RSSI to Gateway: belum ada";
  const batteryMv = hasNumber(event.batteryMv) && Number(event.batteryMv) !== 0xFFFF
    ? Number(event.batteryMv)
    : undefined;
  const directGatewayCandidate = gatewayRssi !== undefined &&
    gatewaySnr !== undefined &&
    gatewayRssi >= directGatewayMinRssiDbm &&
    gatewaySnr >= directGatewayMinSnrDb;
  const pendingReason = directGatewayCandidate
    ? "pending: direct Gateway candidate is strong; waiting installed CH_HELLO/topology"
    : (gatewayRssi !== undefined || gatewaySnr !== undefined
      ? "pending: Gateway link RSSI " + (gatewayRssi ?? "-") + " dBm / SNR " + (gatewaySnr ?? "-") + " dB below direct threshold " + directGatewayMinRssiDbm + " dBm / " + directGatewayMinSnrDb + " dB; waiting CH parent response"
      : "pending: waiting CH_CONFIG response");
  nodes.push({
    id: clusterIdHex,
    label: "CH " + clusterIdHex,
    type: "ch",
    parent: directGatewayCandidate ? topology.gatewayIdHex : null,
    parentAlt: null,
    depth: null,
    layer: null,
    layerLabel: "Discovery",
    route: [],
    routeText: directGatewayCandidate ? topology.gatewayIdHex + " -> " + clusterIdHex + " (pending)" : "installed route pending",
    requestPayload: directGatewayCandidate ? { requestId: 1, hopList: [clusterIdHex] } : null,
    lastHop: clusterIdHex,
    report: event.report,
    rssi: directGatewayCandidate ? gatewayRssi : undefined,
    snr: directGatewayCandidate ? gatewaySnr : undefined,
    rssiSource: directGatewayCandidate ? topology.gatewayIdHex : null,
    rssiTarget: clusterIdHex,
    rssiLink: directGatewayCandidate ? topology.gatewayIdHex + " -> " + clusterIdHex : null,
    linkQualityLabel: directGatewayCandidate
      ? "RSSI to Parent: " + (gatewayRssi ?? "-") + " dBm, SNR " + (gatewaySnr ?? "-") + " dB"
      : "RSSI to Parent: belum ada",
    gatewayRssi,
    gatewaySnr,
    gatewayQualityLabel,
    gatewayLinkUpdatedAt: gatewayLink ? gatewayLink.receivedAt : undefined,
    gatewayLinkAgeSec,
    lastHelloAgeSec,
    lastHelloUpdatedAt: hello ? hello.receivedAt : undefined,
    liveUpdatedAt: event.receivedAt,
    lastSeenAgeSec,
    batteryMv,
    batteryLabel: batteryMv !== undefined && batteryMv !== null
      ? "battery: " + batteryMv + " mV"
      : "battery: belum ada",
    pendingReason,
    updatedAt: event.receivedAt,
    status: "discovery"
  });
  visibleIds.add(clusterIdHex);
}

const nodeById = new Map(nodes.map((node) => [node.id, node]));
function resolveVisualLayer(node, guard = 0) {
  if (!node || guard > 16) {
    return null;
  }
  if (node.type === "gateway") {
    return 0;
  }
  if (node.status === "installed" && Array.isArray(node.route) && node.route.length > 0) {
    return node.route.length;
  }
  if (node.parent && node.parent !== "0x0000" && node.parent !== node.id && nodeById.has(node.parent)) {
    const parentLayer = resolveVisualLayer(nodeById.get(node.parent), guard + 1);
    return parentLayer !== null ? parentLayer + 1 : null;
  }
  if (node.gatewayRssi !== undefined || node.gatewaySnr !== undefined) {
    return 1;
  }
  return null;
}

for (const node of nodes) {
  const visualLayer = resolveVisualLayer(node);
  if (visualLayer !== null) {
    node.layer = visualLayer;
    node.layerLabel = node.status === "installed" || node.type === "gateway"
      ? "Layer " + visualLayer
      : "Layer " + visualLayer + " pending";
    if (node.status === "installed") {
      node.depth = visualLayer;
    }
  }
}

const edgeKeys = new Set(edges.map((edge) => edge.role + ":" + edge.from + "->" + edge.to));
for (const node of nodes) {
  if (node.type !== "ch" || node.status === "installed") {
    continue;
  }
  if (node.parent && node.parent !== "0x0000" && node.parent !== node.id && nodeById.has(node.parent)) {
    const key = "pending:" + node.parent + "->" + node.id;
    if (!edgeKeys.has(key)) {
      edges.push({
        from: node.parent,
        to: node.id,
        label: node.parent + " -> " + node.id,
        role: "pending",
        rssi: node.rssi,
        snr: node.snr,
        linkQualityLabel: node.linkQualityLabel || "Pending Parent"
      });
      edgeKeys.add(key);
    }
  }
}

nodes.sort((a, b) => {
  const da = a.layer === null ? 99 : a.layer;
  const db = b.layer === null ? 99 : b.layer;
  if (da !== db) return da - db;
  return String(a.id).localeCompare(String(b.id));
});

const publicRoutes = {};
for (const node of nodes) {
  if (node.type === "ch" && node.status === "installed" && Array.isArray(node.route) && node.route.length > 0) {
    publicRoutes[node.id] = node.route;
  }
}

const gldRequestTimeoutMs = Number(env.get("PGL_GLD_REQUEST_TIMEOUT_MS") || "20000");
const gldDiscoveryRaw = flow.get("pglGldDiscovery") || {};
const gldDiscovery = {};
const nowMsGld = Date.now();
for (const [chIdHex, entry] of Object.entries(gldDiscoveryRaw)) {
  const requestedAtMs = Date.parse(entry.requestedAt || "");
  const requestedAgeSec = Number.isFinite(requestedAtMs) ? Math.round((nowMsGld - requestedAtMs) / 1000) : undefined;
  const statusDisplay = entry.status === "sent" && requestedAgeSec !== undefined && requestedAgeSec * 1000 > gldRequestTimeoutMs
    ? "timeout"
    : (entry.status || "idle");
  const devices = Object.values(entry.devices || {})
    .map((device) => {
      const lastSeenAtMs = Date.parse(device.lastSeenAt || "");
      return Object.assign({}, device, {
        lastSeenAgeSec: Number.isFinite(lastSeenAtMs) ? Math.round((nowMsGld - lastSeenAtMs) / 1000) : undefined
      });
    })
    .sort((a, b) => String(a.nodeIdHex).localeCompare(String(b.nodeIdHex)));
  gldDiscovery[chIdHex] = {
    ch: chIdHex,
    status: statusDisplay,
    requestId: entry.requestId,
    hopList: entry.hopList || [],
    requestedAt: entry.requestedAt || null,
    requestedAgeSec,
    respondedAt: entry.respondedAt || null,
    recordCount: entry.recordCount,
    chBatteryMv: entry.chBatteryMv,
    responseStatus: entry.responseStatus,
    deviceCount: devices.length,
    devices
  };
}

const latestGldAttachment = new Map();
for (const [chIdHex, entry] of Object.entries(gldDiscovery)) {
  if (!nodeById.has(chIdHex)) continue;
  for (const device of entry.devices || []) {
    const key = String(device.nodeIdHex || "");
    if (!key) continue;
    const seenMs = Date.parse(device.lastSeenAt || "") || 0;
    const current = latestGldAttachment.get(key);
    if (!current || seenMs > current.seenMs) {
      latestGldAttachment.set(key, { chIdHex, device, seenMs });
    }
  }
}

let gldNodeCount = 0;
for (const { chIdHex, device } of latestGldAttachment.values()) {
    const parentNode = nodeById.get(chIdHex);
    const topologyNodeId = "gld:" + chIdHex + ":" + device.nodeIdHex;
    const layer = Number.isFinite(Number(parentNode.layer)) ? Number(parentNode.layer) + 1 : null;
    const node = {
      id: topologyNodeId,
      type: "gld",
      label: "GLD " + device.nodeIdHex,
      parent: chIdHex,
      layer,
      layerLabel: layer === null ? "GLD" : "Layer " + layer + " / GLD",
      status: device.alarm ? "alarm" : "online",
      nodeIdHex: device.nodeIdHex,
      chIdHex,
      gasClass: device.gasClass,
      gasName: device.gasName,
      confidence: device.confidence,
      batteryMv: device.batteryMv,
      alarm: Boolean(device.alarm),
      externalPower: Boolean(device.externalPower),
      seq: device.seq,
      decryptOk: device.decryptOk,
      lastSeenAt: device.lastSeenAt,
      lastSeenAgeSec: device.lastSeenAgeSec
    };
    nodes.push(node);
    nodeById.set(topologyNodeId, node);
    edges.push({
      from: chIdHex,
      to: topologyNodeId,
      label: chIdHex + " -> " + device.nodeIdHex,
      role: "gld"
    });
    gldNodeCount++;
}

nodes.sort((a, b) => {
  const da = a.layer === null ? 99 : a.layer;
  const db = b.layer === null ? 99 : b.layer;
  if (da !== db) return da - db;
  return String(a.id).localeCompare(String(b.id));
});

msg.headers = { "content-type": "application/json; charset=utf-8" };
msg.payload = {
  ok: true,
  kind: "pgl-topology",
  updatedAt: topology.updatedAt,
  liveUpdatedAt: newestIso(topology.discoveryUpdatedAt, topology.updatedAt),
  topologyUpdatedAt: topology.updatedAt,
  resetAt: topology.resetAt || null,
  gatewayIdHex: topology.gatewayIdHex,
  nodeCount: nodes.length,
  edgeCount: edges.length,
  mainEdgeCount: edges.filter((edge) => edge.role === "main").length,
  alternateEdgeCount: edges.filter((edge) => edge.role === "alternate").length,
  pendingEdgeCount: edges.filter((edge) => edge.role === "pending").length,
  discoveryCount: Object.keys(topology.discovery || {}).length,
  gldNodeCount,
  nodes,
  edges,
  routes: publicRoutes,
  discovery: topology.discovery || {},
  gldDiscovery
};
return msg;`;

const topologyResetFunction = `function idHex(value) {
  const n = Number(value) & 0xFFFF;
  return "0x" + n.toString(16).toUpperCase().padStart(4, "0");
}

const gatewayIdHex = idHex(Number(env.get("PGL_GATEWAY_ID") || "0x006F"));
const resetAt = new Date().toISOString();
const topology = {
  gatewayIdHex,
  parents: {},
  discovery: {},
  gatewayLinks: {},
  hellos: {},
  routes: {},
  updatedAt: null,
  discoveryUpdatedAt: null,
  resetAt
};
flow.set("pglTopology", topology);
flow.set("pglGldDiscovery", {});
flow.set("pglGldRequestIndex", {});

msg.headers = { "content-type": "application/json; charset=utf-8" };
msg.payload = {
  ok: true,
  kind: "pgl-topology",
  reset: true,
  resetAt,
  updatedAt: null,
  liveUpdatedAt: null,
  topologyUpdatedAt: null,
  gatewayIdHex,
  nodeCount: 1,
  edgeCount: 0,
  mainEdgeCount: 0,
  alternateEdgeCount: 0,
  discoveryCount: 0,
  gldNodeCount: 0,
  nodes: [{
    id: gatewayIdHex,
    label: "GW",
    type: "gateway",
    parent: null,
    depth: 0,
    layer: 0,
    layerLabel: "Layer 0",
    route: [],
    status: "root"
  }],
  edges: [],
  routes: {},
  discovery: {},
  gatewayLinks: {},
  gldDiscovery: {}
};
return msg;`;

const topologyDeleteFunction = `function idHexValue(value) {
  const raw = String(value || "").trim();
  const n = raw.toLowerCase().startsWith("0x") ? parseInt(raw, 16) : Number(raw);
  if (!Number.isFinite(n)) return null;
  return "0x" + (n & 0xFFFF).toString(16).toUpperCase().padStart(4, "0");
}

const clusterIdHex = idHexValue((msg.req && msg.req.query && msg.req.query.ch) || (msg.payload && (msg.payload.ch || msg.payload.clusterId)));
if (!clusterIdHex) {
  msg.statusCode = 400;
  msg.payload = { ok: false, reason: "invalid-ch-id" };
  return msg;
}

const topology = flow.get("pglTopology") || {};
topology.parents = topology.parents || {};
topology.discovery = topology.discovery || {};
topology.gatewayLinks = topology.gatewayLinks || {};
topology.hellos = topology.hellos || {};
topology.routes = topology.routes || {};

delete topology.parents[clusterIdHex];
delete topology.discovery[clusterIdHex];
delete topology.gatewayLinks[clusterIdHex];
delete topology.hellos[clusterIdHex];
delete topology.routes[clusterIdHex];
for (const [key, route] of Object.entries(topology.routes)) {
  if (Array.isArray(route) && route.includes(clusterIdHex)) {
    delete topology.routes[key];
  }
}
topology.updatedAt = new Date().toISOString();
topology.discoveryUpdatedAt = topology.updatedAt;
flow.set("pglTopology", topology);

msg.headers = { "content-type": "application/json; charset=utf-8" };
msg.payload = { ok: true, deleted: clusterIdHex, kind: "pgl-topology-delete", updatedAt: topology.updatedAt };
return msg;`;

const topologyRequestFunction = `function idHexValue(value) {
  const raw = String(value || "").trim();
  const n = raw.toLowerCase().startsWith("0x") ? parseInt(raw, 16) : Number(raw);
  if (!Number.isFinite(n)) return null;
  return "0x" + (n & 0xFFFF).toString(16).toUpperCase().padStart(4, "0");
}

const clusterIdHex = idHexValue((msg.req && msg.req.query && msg.req.query.ch) || (msg.payload && (msg.payload.ch || msg.payload.clusterId)));
if (!clusterIdHex) {
  msg.statusCode = 400;
  msg.payload = { ok: false, reason: "invalid-ch-id" };
  return [null, msg];
}

const topology = flow.get("pglTopology") || {};
let route = topology.routes && Array.isArray(topology.routes[clusterIdHex]) ? topology.routes[clusterIdHex] : [];
if (route.length === 0) {
  const directGatewayMinRssiDbm = Number(env.get("PGL_GATEWAY_DIRECT_PARENT_MIN_RSSI_DBM") || "-95");
  const directGatewayMinSnrDb = Number(env.get("PGL_GATEWAY_DIRECT_PARENT_MIN_SNR_DB") || "5");
  const gatewayLink = (topology.gatewayLinks || {})[clusterIdHex];
  const isDirectCandidate = gatewayLink &&
    Number.isFinite(Number(gatewayLink.rssi)) &&
    Number.isFinite(Number(gatewayLink.snr)) &&
    Number(gatewayLink.rssi) >= directGatewayMinRssiDbm &&
    Number(gatewayLink.snr) >= directGatewayMinSnrDb;
  if (isDirectCandidate) {
    route = [clusterIdHex];
  }
}
if (route.length === 0) {
  msg.statusCode = 409;
  msg.payload = { ok: false, reason: "route-not-installed", ch: clusterIdHex };
  return [null, msg];
}

const requestCorrelationTtlMs = Number(env.get("PGL_GLD_REQUEST_CORRELATION_TTL_MS") || "120000");
const requestIndex = flow.get("pglGldRequestIndex") || {};
const requestNowMs = Date.now();
for (const [key, entry] of Object.entries(requestIndex)) {
  const requestedAtMs = Date.parse(entry && entry.requestedAt || "");
  if (Number.isFinite(requestedAtMs) && requestNowMs - requestedAtMs > requestCorrelationTtlMs) delete requestIndex[key];
}
let requestId = (requestNowMs & 0xFFFF) || 1;
let requestIdAvailable = false;
for (let guard = 0; guard < 0xFFFF; guard++) {
  if (requestId !== 0 && !requestIndex[String(requestId)]) {
    requestIdAvailable = true;
    break;
  }
  requestId = (requestId + 1) & 0xFFFF;
  if (requestId === 0) requestId = 1;
}
if (!requestIdAvailable) {
  msg.statusCode = 503;
  msg.payload = { ok: false, reason: "request-id-pool-exhausted", ch: clusterIdHex };
  return [null, msg];
}
const requestedAt = new Date(requestNowMs).toISOString();
const command = {
  requestId,
  hopList: route
};
requestIndex[String(requestId)] = {
  requestId,
  targetChIdHex: clusterIdHex,
  hopList: route,
  requestedAt
};
flow.set("pglGldRequestIndex", requestIndex);
const mqttMsg = {
  topic: "gld/gateway/cmd/pull",
  payload: command
};

const gldDiscovery = flow.get("pglGldDiscovery") || {};
const existingGldEntry = gldDiscovery[clusterIdHex] || {};
gldDiscovery[clusterIdHex] = {
  status: "sent",
  requestId,
  hopList: route,
  requestedAt,
  respondedAt: existingGldEntry.respondedAt || null,
  recordCount: existingGldEntry.recordCount,
  chBatteryMv: existingGldEntry.chBatteryMv,
  responseStatus: existingGldEntry.responseStatus,
  devices: existingGldEntry.devices || {}
};
flow.set("pglGldDiscovery", gldDiscovery);

msg.headers = { "content-type": "application/json; charset=utf-8" };
msg.payload = { ok: true, kind: "pgl-topology-request", ch: clusterIdHex, requestId, hopList: route };
return [mqttMsg, msg];`;

const topologyViewFunction = `msg.headers = { "content-type": "text/html; charset=utf-8" };
msg.payload = \`<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pertamina GLD Topology</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #101214;
      --panel: #171b20;
      --line: #6b7280;
      --text: #f3f4f6;
      --muted: #9ca3af;
      --gw: #10b981;
      --ch: #38bdf8;
      --warn: #f59e0b;
      --mainLink: #38bdf8;
      --altLink: #f59e0b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 16px 20px;
      border-bottom: 1px solid #2b3036;
      background: #0f1115;
    }
    h1 { margin: 0; font-size: 20px; font-weight: 650; }
    .meta { color: var(--muted); font-size: 13px; text-align: right; }
    main { padding: 18px; }
    .canvas {
      position: relative;
      min-height: 560px;
      border: 1px solid #2b3036;
      background: radial-gradient(circle at 50% 0%, #192028 0, #12161b 45%, #101214 100%);
      overflow: auto;
    }
    svg {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;
    }
    .node {
      position: absolute;
      width: 240px;
      min-height: 210px;
      padding: 12px;
      border: 1px solid var(--node-border, #334155);
      border-left: 5px solid var(--node-accent, var(--node-border, #334155));
      border-radius: 8px;
      background: linear-gradient(180deg, var(--node-bg, var(--panel)) 0%, var(--panel) 72%);
      box-shadow: 0 10px 26px rgba(0,0,0,.26);
      cursor: grab;
      touch-action: none;
      user-select: none;
    }
    .node.dragging {
      cursor: grabbing;
      z-index: 5;
      box-shadow: 0 16px 36px rgba(0,0,0,.42);
    }
    .node.updated {
      animation: chUpdateFlash 1.8s ease-out 1;
    }
    .node.gateway {
      --node-border: var(--gw);
      --node-accent: var(--gw);
      --node-bg: #12231f;
      --layer-pill-bg: rgba(16,185,129,.18);
    }
    .node.ch {
      --node-border: var(--ch);
      --node-accent: var(--ch);
      --node-bg: #10202a;
      --layer-pill-bg: rgba(56,189,248,.16);
    }
    .node.gld {
      --node-border: #a78bfa;
      --node-accent: #a78bfa;
      --node-bg: #1b172b;
      --layer-pill-bg: rgba(167,139,250,.17);
      min-height: 190px;
    }
    .node.gld.alarm {
      --node-border: #ef4444;
      --node-accent: #ef4444;
      --node-bg: #2a1414;
    }
    .node.pending {
      outline: 1px solid rgba(245,158,11,.85);
      outline-offset: 1px;
    }
    @keyframes chUpdateFlash {
      0% {
        border-color: #fde047;
        background: #2a2615;
        box-shadow: 0 0 0 0 rgba(253,224,71,.95), 0 10px 26px rgba(0,0,0,.26);
      }
      35% {
        border-color: #facc15;
        background: #252319;
        box-shadow: 0 0 0 8px rgba(253,224,71,.24), 0 16px 34px rgba(0,0,0,.34);
      }
      100% {
        border-color: var(--node-border, var(--ch));
        background: linear-gradient(180deg, var(--node-bg, var(--panel)) 0%, var(--panel) 72%);
        box-shadow: 0 0 0 18px rgba(253,224,71,0), 0 10px 26px rgba(0,0,0,.26);
      }
    }
    .title { font-size: 16px; font-weight: 700; margin-bottom: 8px; }
    .row { color: var(--muted); font-size: 12px; line-height: 1.45; white-space: normal; overflow: visible; overflow-wrap: anywhere; }
    .layer {
      display: inline-block;
      margin-bottom: 7px;
      padding: 2px 7px;
      border: 1px solid #475569;
      border-radius: 999px;
      color: #e5e7eb;
      background: var(--layer-pill-bg, transparent);
      font-size: 11px;
      line-height: 1.35;
    }
    .route {
      margin-top: 8px;
      color: #d1d5db;
      font-size: 12px;
      line-height: 1.35;
      white-space: normal;
    }
    .toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      gap: 12px;
    }
    .legend {
      display: flex;
      align-items: center;
      gap: 14px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 12px;
    }
    .legend-item {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .legend-line {
      width: 28px;
      height: 0;
      border-top: 3px solid var(--mainLink);
    }
    .legend-line.alt {
      border-top-color: var(--altLink);
      border-top-style: dashed;
    }
    .legend-line.pending {
      border-top-color: var(--warn);
      border-top-style: dotted;
    }
    .legend-line.gld { border-top-color: #a78bfa; }
    button {
      border: 1px solid #475569;
      background: #1f2937;
      color: var(--text);
      border-radius: 6px;
      padding: 8px 12px;
      cursor: pointer;
    }
    button:hover { background: #263244; }
    button:disabled { cursor: wait; opacity: .65; }
    button.danger {
      border-color: #7f1d1d;
      background: #3b1717;
      color: #fecaca;
    }
    button.danger:hover { background: #4c1d1d; }
    .table-actions {
      display: flex;
      gap: 6px;
      flex-wrap: nowrap;
    }
    .table-action {
      width: auto;
      min-width: 58px;
      padding: 5px 8px;
      border-radius: 6px;
      font-size: 11px;
      line-height: 1;
    }
    .table-action.delete {
      color: #fecaca;
      border-color: rgba(248,113,113,.55);
      background: rgba(127,29,29,.18);
    }
    .table-action:disabled {
      opacity: .42;
      cursor: not-allowed;
    }
    .actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .status { color: var(--muted); font-size: 13px; }
    .empty {
      padding: 28px;
      color: var(--muted);
      text-align: center;
    }
    .pending-section {
      margin-top: 14px;
      border: 1px solid #2b3036;
      background: #11161c;
      overflow: hidden;
    }
    .pending-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 12px 14px;
      border-bottom: 1px solid #2b3036;
    }
    .pending-header h2 {
      margin: 0;
      font-size: 15px;
      font-weight: 650;
    }
    .pending-count {
      color: var(--muted);
      font-size: 12px;
    }
    .pending-table-wrap {
      overflow-x: auto;
    }
    .pending-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      min-width: 760px;
    }
    .pending-table th,
    .pending-table td {
      padding: 9px 12px;
      border-bottom: 1px solid #252b33;
      text-align: left;
      vertical-align: top;
    }
    .pending-table th {
      color: #d1d5db;
      background: #151b22;
      font-weight: 650;
    }
    .pending-table td {
      color: var(--muted);
    }
    .pending-table tr:last-child td {
      border-bottom: 0;
    }
    .pending-empty {
      padding: 13px 14px;
      color: var(--muted);
      font-size: 12px;
    }
    .card-actions {
      margin-top: 8px;
      display: flex;
      justify-content: flex-end;
    }
    .card-actions button {
      padding: 4px 10px;
      font-size: 11px;
    }
    .gld-section {
      margin-top: 14px;
      display: grid;
      grid-template-columns: minmax(260px, 1fr) minmax(420px, 2fr);
      gap: 14px;
    }
    @media (max-width: 960px) {
      .gld-section { grid-template-columns: 1fr; }
    }
    .gld-panel {
      border: 1px solid #2b3036;
      background: #11161c;
      overflow: hidden;
    }
    .gld-panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 12px 14px;
      border-bottom: 1px solid #2b3036;
    }
    .gld-panel-header h2 {
      margin: 0;
      font-size: 15px;
      font-weight: 650;
    }
    .gld-request-list {
      padding: 10px 14px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      max-height: 420px;
      overflow-y: auto;
    }
    .gld-request-item {
      border: 1px solid #252b33;
      border-radius: 8px;
      padding: 10px 12px;
      background: #151b22;
    }
    .gld-request-item .row1 {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      margin-bottom: 6px;
    }
    .gld-request-item .ch-id { font-weight: 650; font-size: 13px; }
    .gld-request-item .meta { color: var(--muted); font-size: 11px; line-height: 1.5; }
    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 3px 9px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 650;
      border: 1px solid transparent;
      white-space: nowrap;
    }
    .status-badge.sent {
      color: #93c5fd;
      background: rgba(59,130,246,.16);
      border-color: rgba(59,130,246,.4);
    }
    .status-badge.received {
      color: #86efac;
      background: rgba(34,197,94,.16);
      border-color: rgba(34,197,94,.4);
    }
    .status-badge.timeout {
      color: #fca5a5;
      background: rgba(239,68,68,.16);
      border-color: rgba(239,68,68,.4);
    }
    .status-badge.unsolicited,
    .status-badge.idle {
      color: var(--muted);
      background: rgba(148,163,184,.12);
      border-color: rgba(148,163,184,.3);
    }
    .spinner {
      width: 9px;
      height: 9px;
      border-radius: 50%;
      border: 2px solid rgba(147,197,253,.35);
      border-top-color: #93c5fd;
      animation: gldSpin .8s linear infinite;
    }
    @keyframes gldSpin {
      to { transform: rotate(360deg); }
    }
    .gld-empty {
      padding: 13px 14px;
      color: var(--muted);
      font-size: 12px;
    }
    .gld-table-wrap { overflow-x: auto; }
    .gld-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      min-width: 760px;
    }
    .gld-table th,
    .gld-table td {
      padding: 9px 12px;
      border-bottom: 1px solid #252b33;
      text-align: left;
      vertical-align: top;
    }
    .gld-table th {
      color: #d1d5db;
      background: #151b22;
      font-weight: 650;
    }
    .gld-table td { color: var(--muted); }
    .gld-table tr:last-child td { border-bottom: 0; }
    .gld-table .payload-hex {
      font-family: "Consolas", "Menlo", monospace;
      font-size: 11px;
      color: #9ca3af;
      max-width: 240px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      display: inline-block;
      vertical-align: bottom;
    }
    .gld-table .alarm-yes { color: #fca5a5; font-weight: 650; }
  </style>
</head>
<body>
  <header>
    <h1>Pertamina GLD Topology</h1>
    <div class="meta">
      <div id="summary">loading...</div>
      <div>Auto refresh 1 detik</div>
    </div>
  </header>
  <main>
    <div class="toolbar">
      <div class="status" id="status">Mengambil topology...</div>
      <div class="legend">
        <span class="legend-item"><span class="legend-line"></span>Main Parent</span>
        <span class="legend-item"><span class="legend-line alt"></span>Alternative Parent</span>
        <span class="legend-item"><span class="legend-line pending"></span>Pending Parent</span>
        <span class="legend-item"><span class="legend-line gld"></span>CH ke GLD</span>
      </div>
      <div class="actions">
        <button id="refresh">Refresh</button>
        <button id="resetLayout">Reset Layout</button>
        <button id="resetRouting" class="danger">Reset Routing</button>
      </div>
    </div>
    <div class="canvas" id="canvas">
      <svg id="links"></svg>
      <div id="nodes"></div>
    </div>
    <section class="pending-section">
      <div class="pending-header">
        <h2>Status CH</h2>
        <div class="pending-count" id="pendingCount">0 item</div>
      </div>
      <div id="pendingDetails"></div>
    </section>
    <section class="gld-section">
      <div class="gld-panel">
        <div class="gld-panel-header">
          <h2>Request GLD Discovery</h2>
          <div class="pending-count" id="gldRequestCount">0 request</div>
        </div>
        <div id="gldRequestList" class="gld-request-list"></div>
      </div>
      <div class="gld-panel">
        <div class="gld-panel-header">
          <h2>GLD Terdiscover</h2>
          <div class="pending-count" id="gldDeviceCount">0 GLD</div>
        </div>
        <div id="gldDeviceDetails"></div>
      </div>
    </section>
  </main>
  <script>
    const canvas = document.getElementById("canvas");
    const nodesEl = document.getElementById("nodes");
    const linksEl = document.getElementById("links");
    const statusEl = document.getElementById("status");
    const summaryEl = document.getElementById("summary");
    const pendingDetailsEl = document.getElementById("pendingDetails");
    const pendingCountEl = document.getElementById("pendingCount");
    const gldRequestListEl = document.getElementById("gldRequestList");
    const gldRequestCountEl = document.getElementById("gldRequestCount");
    const gldDeviceDetailsEl = document.getElementById("gldDeviceDetails");
    const gldDeviceCountEl = document.getElementById("gldDeviceCount");
    const resetButton = document.getElementById("resetRouting");
    const resetLayoutButton = document.getElementById("resetLayout");
    const nodeSignals = new Map();
    const layoutStorageKey = "pertamina-gld-topology-layout-v1";
    const nodeW = 240;
    let currentEdges = [];
    let currentPositions = {};
    let dragActive = false;
    let hasRendered = false;

    function loadManualLayout() {
      try {
        const saved = JSON.parse(localStorage.getItem(layoutStorageKey) || "{}");
        return saved && typeof saved === "object" ? saved : {};
      } catch (err) {
        return {};
      }
    }

    function saveManualLayout(layout) {
      localStorage.setItem(layoutStorageKey, JSON.stringify(layout));
    }

    function clamp(value, min, max) {
      return Math.min(Math.max(value, min), max);
    }

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[char]));
    }

    function pendingExplanation(node) {
      const reason = String(node.pendingReason || "").toLowerCase();
      if (reason.includes("waiting installed route via")) {
        const via = String(node.pendingReason || "").split("via ").pop() || node.parent || "-";
        return "Menunggu route parent " + via + " terpasang dulu. Biasanya selesai setelah parent mengirim CH_HELLO/topology yang valid ke server.";
      }
      if (reason.includes("direct gateway candidate is strong")) {
        return "Gateway sudah terdengar cukup kuat. Server menunggu CH_HELLO/topology dari CH supaya route resmi bisa dipasang.";
      }
      if (reason.includes("below direct threshold")) {
        return "Link langsung ke Gateway belum memenuhi threshold. CH sedang menunggu response parent/CH lain dari proses CH_CONFIG.";
      }
      if (reason.includes("waiting ch_config response")) {
        return "Menunggu CH_CONFIG_RESPONSE dari Gateway atau parent CH agar kandidat route bisa dipilih.";
      }
      if (reason.includes("waiting parent topology")) {
        return "Menunggu topology parent masuk ke server supaya jalur sampai Gateway bisa dihitung.";
      }
      return node.pendingReason || "Menunggu event routing berikutnya dari CH_CONFIG atau CH_HELLO/topology.";
    }

    function ageLabel(seconds) {
      if (seconds === undefined || seconds === null || !Number.isFinite(Number(seconds))) return "-";
      const sec = Math.max(0, Math.round(Number(seconds)));
      if (sec < 60) return sec + "s ago";
      const min = Math.floor(sec / 60);
      const rem = sec % 60;
      if (min < 60) return min + "m" + (rem ? " " + rem + "s" : "") + " ago";
      const hour = Math.floor(min / 60);
      const minRem = min % 60;
      return hour + "h" + (minRem ? " " + minRem + "m" : "") + " ago";
    }

    function expectedNextEvent(node) {
      if (node.status === "installed") {
        if (node.lastHelloAgeSec !== undefined) {
          const remaining = Math.max(0, 300 - Math.round(Number(node.lastHelloAgeSec)));
          return remaining > 0
            ? "Menunggu CH_HELLO periodik berikutnya sekitar " + remaining + "s lagi."
            : "CH_HELLO periodik sudah waktunya masuk; menunggu update berikutnya dari CH.";
        }
        return "Route sudah installed; menunggu CH_HELLO berikutnya untuk mengisi umur hello.";
      }
      const reason = String(node.pendingReason || "").toLowerCase();
      if (reason.includes("direct gateway candidate is strong")) {
        return "Menunggu CH_HELLO pertama dari CH supaya route resmi dipasang.";
      }
      if (reason.includes("waiting installed route via")) {
        const via = String(node.pendingReason || "").split("via ").pop() || node.parent || "-";
        return "Menunggu parent " + via + " installed dulu, lalu CH_HELLO dari CH ini.";
      }
      if (reason.includes("below direct threshold")) {
        return "Menunggu CH_CONFIG_RESPONSE dari parent CH yang lebih layak.";
      }
      if (reason.includes("waiting ch_config response")) {
        return "Menunggu CH_CONFIG_RESPONSE dari GW atau parent CH.";
      }
      if (reason.includes("waiting parent topology")) {
        return "Menunggu topology parent masuk ke server.";
      }
      return "Menunggu event CH_CONFIG atau CH_HELLO berikutnya.";
    }

    function renderPendingTable(nodes) {
      const chNodes = nodes.filter((node) => node.type === "ch");
      const pendingNodes = chNodes.filter((node) => node.status !== "installed" || node.pendingReason);
      pendingCountEl.textContent = pendingNodes.length + " pending / " + chNodes.length + " CH";
      if (chNodes.length === 0) {
        pendingDetailsEl.innerHTML = '<div class="pending-empty">Belum ada CH.</div>';
        return;
      }
      pendingDetailsEl.innerHTML =
        '<div class="pending-table-wrap">' +
        '<table class="pending-table">' +
        '<thead><tr>' +
        '<th>CH</th><th>Status</th><th>Parent</th><th>Route</th><th>Last CH_HELLO</th><th>Expected Next Event</th><th>Aksi</th><th>Update</th>' +
        '</tr></thead><tbody>' +
        chNodes.map((node) =>
          '<tr>' +
          '<td>' + escapeHtml(node.label || node.id || "-") + '</td>' +
          '<td>' + escapeHtml(node.status || "-") + '</td>' +
          '<td>' + escapeHtml(node.parent || "-") + '</td>' +
          '<td>' + escapeHtml(node.routeText || "-") + '</td>' +
          '<td>' + escapeHtml(ageLabel(node.lastHelloAgeSec)) + '</td>' +
          '<td>' + escapeHtml(expectedNextEvent(node)) + '</td>' +
          '<td><div class="table-actions">' +
          '<button class="table-action" data-action="request" data-node-id="' + escapeHtml(node.id || "") + '"' + (node.requestPayload ? "" : " disabled") + '>Request</button>' +
          '<button class="table-action delete" data-action="delete" data-node-id="' + escapeHtml(node.id || "") + '">Hapus</button>' +
          '</div></td>' +
          '<td>' + escapeHtml(ageLabel(node.lastSeenAgeSec) !== "-" ? ageLabel(node.lastSeenAgeSec) : (node.updatedAt || "-")) + '</td>' +
          '</tr>'
        ).join("") +
        '</tbody></table></div>';
    }

    function layerStyleFor(node) {
      const fallback = { border: "#64748b", bg: "#171b24", pill: "rgba(148,163,184,.16)" };
      const red = { border: "#ef4444", bg: "#2a1414", pill: "rgba(239,68,68,.18)" };
      const palette = {
        0: { border: "#10b981", bg: "#12231f", pill: "rgba(16,185,129,.18)" },
        1: { border: "#38bdf8", bg: "#10202a", pill: "rgba(56,189,248,.16)" },
        2: { border: "#a78bfa", bg: "#1b172b", pill: "rgba(167,139,250,.17)" },
        3: { border: "#f59e0b", bg: "#2a1f10", pill: "rgba(245,158,11,.17)" },
        4: { border: "#fb7185", bg: "#2a151b", pill: "rgba(251,113,133,.16)" },
        5: { border: "#22c55e", bg: "#102317", pill: "rgba(34,197,94,.15)" },
        6: { border: "#06b6d4", bg: "#10232a", pill: "rgba(6,182,212,.16)" },
        7: { border: "#84cc16", bg: "#1a230f", pill: "rgba(132,204,22,.16)" },
        8: { border: "#f97316", bg: "#2a1a10", pill: "rgba(249,115,22,.17)" },
        9: { border: "#6366f1", bg: "#17172b", pill: "rgba(99,102,241,.17)" }
      };
      const layer = Number.isFinite(Number(node.layer)) ? Math.trunc(Number(node.layer)) : null;
      if (layer === null) return fallback;
      if (layer >= 10) return red;
      return palette[layer] || fallback;
    }

    function applyLayerStyle(div, node) {
      const style = layerStyleFor(node);
      div.style.setProperty("--node-border", style.border);
      div.style.setProperty("--node-accent", style.border);
      div.style.setProperty("--node-bg", style.bg);
      div.style.setProperty("--layer-pill-bg", style.pill);
    }

    function updateCanvasHeight() {
      const maxY = Object.values(currentPositions).reduce((acc, pos) => Math.max(acc, pos.y + (pos.h || 260)), 560);
      canvas.style.minHeight = Math.max(560, maxY + 24) + "px";
    }

    function measureNodePositions() {
      for (const div of nodesEl.querySelectorAll(".node[data-node-id]")) {
        const nodeId = div.dataset.nodeId;
        const pos = currentPositions[nodeId];
        if (!pos) continue;
        pos.w = div.offsetWidth || nodeW;
        pos.h = div.offsetHeight || 210;
        pos.cx = pos.x + pos.w / 2;
      }
    }

    function edgeAnchors(a, b) {
      const aW = a.w || nodeW;
      const bW = b.w || nodeW;
      const aH = a.h || 210;
      const bH = b.h || 210;
      const aCenterY = a.y + aH / 2;
      const bCenterY = b.y + bH / 2;
      if (aCenterY <= bCenterY) {
        return {
          x1: a.x + aW / 2,
          y1: a.y + aH,
          x2: b.x + bW / 2,
          y2: b.y
        };
      }
      return {
        x1: a.x + aW / 2,
        y1: a.y,
        x2: b.x + bW / 2,
        y2: b.y + bH
      };
    }

    function renderLinks() {
      measureNodePositions();
      linksEl.innerHTML = "";
      for (const edge of currentEdges) {
        const a = currentPositions[edge.from];
        const b = currentPositions[edge.to];
        if (!a || !b) continue;
        const anchor = edgeAnchors(a, b);
        const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
        line.setAttribute("x1", anchor.x1);
        line.setAttribute("y1", anchor.y1);
        line.setAttribute("x2", anchor.x2);
        line.setAttribute("y2", anchor.y2);
        line.setAttribute("stroke", edge.role === "gld" ? "#a78bfa" : (edge.role === "alternate" ? "#f59e0b" : (edge.role === "pending" ? "#f59e0b" : "#38bdf8")));
        line.setAttribute("stroke-width", edge.role === "main" ? "3" : "2");
        if (edge.role === "alternate") {
          line.setAttribute("stroke-dasharray", "7 7");
        } else if (edge.role === "pending") {
          line.setAttribute("stroke-dasharray", "3 7");
        }
        linksEl.appendChild(line);
      }
    }

    function attachDrag(div, nodeId) {
      let startX = 0;
      let startY = 0;
      let pointerStartX = 0;
      let pointerStartY = 0;
      div.addEventListener("pointerdown", (event) => {
        if (event.button !== undefined && event.button !== 0) return;
        if (event.target.closest("button")) return;
        const pos = currentPositions[nodeId];
        if (!pos) return;
        event.preventDefault();
        dragActive = true;
        div.classList.add("dragging");
        div.setPointerCapture(event.pointerId);
        startX = pos.x;
        startY = pos.y;
        pointerStartX = event.clientX;
        pointerStartY = event.clientY;
      });
      div.addEventListener("pointermove", (event) => {
        if (!div.classList.contains("dragging")) return;
        const width = Math.max(canvas.clientWidth, 760);
        const nextX = clamp(startX + event.clientX - pointerStartX, 16, Math.max(16, width - nodeW - 16));
        const nextY = Math.max(16, startY + event.clientY - pointerStartY);
        currentPositions[nodeId] = {
          x: nextX,
          y: nextY,
          w: currentPositions[nodeId].w || div.offsetWidth || nodeW,
          h: currentPositions[nodeId].h || div.offsetHeight || 210,
          cx: nextX + (currentPositions[nodeId].w || div.offsetWidth || nodeW) / 2
        };
        div.style.left = nextX + "px";
        div.style.top = nextY + "px";
        updateCanvasHeight();
        renderLinks();
      });
      const finishDrag = (event) => {
        if (!div.classList.contains("dragging")) return;
        div.classList.remove("dragging");
        try {
          div.releasePointerCapture(event.pointerId);
        } catch (err) {}
        const layout = loadManualLayout();
        const pos = currentPositions[nodeId];
        if (pos) {
          layout[nodeId] = { x: Math.round(pos.x), y: Math.round(pos.y) };
          saveManualLayout(layout);
        }
        dragActive = false;
      };
      div.addEventListener("pointerup", finishDrag);
      div.addEventListener("pointercancel", finishDrag);
    }

    function groupByDepth(nodes) {
      const groups = new Map();
      const finiteLayers = nodes
        .map((node) => node.layer !== null && node.layer !== undefined && Number.isFinite(Number(node.layer)) ? Number(node.layer) : null)
        .filter((layer) => layer !== null);
      const fallbackLayer = finiteLayers.length > 0 ? Math.max(...finiteLayers) + 1 : 1;
      for (const node of nodes) {
        const layer = node.layer !== null && node.layer !== undefined && Number.isFinite(Number(node.layer)) ? Number(node.layer) : fallbackLayer;
        if (!groups.has(layer)) groups.set(layer, []);
        groups.get(layer).push(node);
      }
      return [...groups.entries()].sort((a, b) => a[0] - b[0]);
    }

    function gldStatusLabel(status) {
      switch (status) {
        case "sent": return "Mengirim / menunggu respon";
        case "received": return "Diterima";
        case "timeout": return "Timeout, tidak ada respon";
        case "unsolicited": return "Data masuk tanpa request";
        default: return status || "-";
      }
    }

    function renderGldRequests(gldDiscovery) {
      const entries = Object.values(gldDiscovery || {}).sort((a, b) => {
        const ta = Date.parse(a.requestedAt || a.respondedAt || 0) || 0;
        const tb = Date.parse(b.requestedAt || b.respondedAt || 0) || 0;
        return tb - ta;
      });
      gldRequestCountEl.textContent = entries.length + " CH";
      if (entries.length === 0) {
        gldRequestListEl.innerHTML = '<div class="gld-empty">Belum ada request GLD dikirim.</div>';
        return;
      }
      gldRequestListEl.innerHTML = entries.map((entry) => {
        const status = entry.status || "idle";
        const spinner = status === "sent" ? '<span class="spinner"></span>' : "";
        return '<div class="gld-request-item">' +
          '<div class="row1"><span class="ch-id">' + escapeHtml(entry.ch) + '</span>' +
          '<span class="status-badge ' + escapeHtml(status) + '">' + spinner + escapeHtml(gldStatusLabel(status)) + '</span></div>' +
          '<div class="meta">Request ID: ' + escapeHtml(entry.requestId ?? "-") + ' | Hop: ' + escapeHtml((entry.hopList || []).join(" -> ") || "-") + '</div>' +
          '<div class="meta">Dikirim: ' + escapeHtml(entry.requestedAt ? ageLabel(entry.requestedAgeSec) : "-") + '</div>' +
          '<div class="meta">Direspon: ' + escapeHtml(entry.respondedAt || "-") + (entry.recordCount !== undefined ? " | " + entry.recordCount + " record" : "") + '</div>' +
          '</div>';
      }).join("");
    }

    function renderGldDevices(gldDiscovery) {
      const latestByNodeId = new Map();
      for (const entry of Object.values(gldDiscovery || {})) {
        for (const device of entry.devices || []) {
          const row = Object.assign({ ch: entry.ch }, device);
          const nodeIdHex = String(device.nodeIdHex || "");
          if (!nodeIdHex) continue;
          const current = latestByNodeId.get(nodeIdHex);
          const rowSeenMs = Date.parse(row.lastSeenAt || 0) || 0;
          const currentSeenMs = current ? (Date.parse(current.lastSeenAt || 0) || 0) : -1;
          if (!current || rowSeenMs > currentSeenMs) latestByNodeId.set(nodeIdHex, row);
        }
      }
      const rows = [...latestByNodeId.values()];
      rows.sort((a, b) => (Date.parse(b.lastSeenAt || 0) || 0) - (Date.parse(a.lastSeenAt || 0) || 0));
      gldDeviceCountEl.textContent = rows.length + " GLD";
      if (rows.length === 0) {
        gldDeviceDetailsEl.innerHTML = '<div class="gld-empty">Belum ada GLD yang terdiscover.</div>';
        return;
      }
      gldDeviceDetailsEl.innerHTML =
        '<div class="gld-table-wrap"><table class="gld-table"><thead><tr>' +
        '<th>CH</th><th>GLD</th><th>Gas</th><th>Confidence</th><th>Battery</th><th>Alarm</th><th>Last Seen</th><th>Decoded Payload</th>' +
        '</tr></thead><tbody>' +
        rows.map((device) => {
          const decodedSummary = device.decryptOk === false
            ? "gagal decode"
            : (device.gasName || "-") + " | conf " + (device.confidence ?? "-") + "%";
          return '<tr>' +
            '<td>' + escapeHtml(device.ch) + '</td>' +
            '<td>' + escapeHtml(device.nodeIdHex) + '</td>' +
            '<td>' + escapeHtml(device.gasName || "-") + '</td>' +
            '<td>' + escapeHtml(device.confidence ?? "-") + '%</td>' +
            '<td>' + escapeHtml(device.batteryMv !== undefined && device.batteryMv !== null ? device.batteryMv + " mV" : "-") + '</td>' +
            '<td>' + (device.alarm ? '<span class="alarm-yes">YA</span>' : "tidak") + '</td>' +
            '<td>' + escapeHtml(ageLabel(device.lastSeenAgeSec)) + '</td>' +
            '<td><span class="payload-hex" title="' + escapeHtml(decodedSummary + " | " + (device.plaintextHex || "-")) + '">' + escapeHtml(decodedSummary) + '</span></td>' +
            '</tr>';
        }).join("") +
        '</tbody></table></div>';
    }

    function draw(data) {
      nodesEl.innerHTML = "";
      linksEl.innerHTML = "";
      const nodes = data.nodes || [];
      const edges = data.edges || [];
      const manualLayout = loadManualLayout();
      currentEdges = edges;
      currentPositions = {};
      summaryEl.textContent = data.nodeCount + " node (" + (data.gldNodeCount || 0) + " GLD), " + (data.mainEdgeCount ?? data.edgeCount) + " main link, " + (data.alternateEdgeCount || 0) + " alt link, " + (data.pendingEdgeCount || 0) + " pending link, " + (data.discoveryCount || 0) + " discovery";
      statusEl.textContent = "Topology: " + (data.topologyUpdatedAt || data.updatedAt || "belum ada topology event") +
        " | Live: " + (data.liveUpdatedAt || "belum ada live event");
      if (data.resetAt && nodes.length <= 1) {
        statusEl.textContent = "Routing reset: " + data.resetAt + " | Menunggu update routing berikutnya";
      }
      if (nodes.length <= 1) {
        nodesEl.innerHTML = '<div class="empty">Belum ada CH route. Tunggu CH_CONFIG/CH_HELLO masuk dari Gateway.</div>';
      }
      renderPendingTable(nodes);
      renderGldRequests(data.gldDiscovery);
      renderGldDevices(data.gldDiscovery);

      const groups = groupByDepth(nodes);
      const width = Math.max(canvas.clientWidth, 760);
      const rowGap = 360;
      const top = 56;
      for (const [layer, items] of groups) {
        items.sort((a, b) => String(a.id).localeCompare(String(b.id)));
        const totalW = items.length * nodeW + Math.max(0, items.length - 1) * 44;
        const startX = Math.max(24, (width - totalW) / 2);
        items.forEach((node, index) => {
          const autoX = startX + index * (nodeW + 44);
          const autoY = top + layer * rowGap;
          const saved = manualLayout[node.id];
          const x = saved && Number.isFinite(Number(saved.x))
            ? clamp(Number(saved.x), 16, Math.max(16, width - nodeW - 16))
            : autoX;
          const y = saved && Number.isFinite(Number(saved.y)) ? Math.max(16, Number(saved.y)) : autoY;
          currentPositions[node.id] = { x, y, w: nodeW, h: 210, cx: x + nodeW / 2 };
          const div = document.createElement("div");
          div.dataset.nodeId = node.id;
          const signal = [
            node.liveUpdatedAt || "",
            node.updatedAt || "",
            node.parent || "",
            node.parentAlt || "",
            node.depth ?? "",
            node.routeText || ""
          ].join("|");
          const previousSignal = nodeSignals.get(node.id);
          const shouldFlash = hasRendered && node.type === "ch" && previousSignal !== undefined && previousSignal !== signal;
          nodeSignals.set(node.id, signal);
          div.className = "node " + node.type + " " + node.status + (shouldFlash ? " updated" : "");
          if (node.type !== "gld") applyLayerStyle(div, node);
          div.style.left = x + "px";
          div.style.top = y + "px";
          const metric = node.type === "gateway"
            ? "root"
            : (node.type === "gld"
              ? "terdiscover di " + (node.chIdHex || node.parent || "-")
              : (node.linkQualityLabel || ("RSSI to Parent: " + (node.rssi ?? "-") + " dBm, SNR " + (node.snr ?? "-") + " dB")));

          const gatewayMetric = node.type === "gateway"
            ? ""
            : (node.gatewayQualityLabel || "RSSI to Gateway: belum ada");
          const ageMetric = node.type === "gateway"
            ? ""
            : ("last update: " + (node.lastSeenAgeSec !== undefined ? node.lastSeenAgeSec + "s ago" : "belum ada"));
          div.innerHTML = node.type === "gld"
            ? '<div class="title">' + escapeHtml(node.label || "-") + '</div>' +
              '<div class="layer">' + escapeHtml(node.layerLabel || "GLD") + '</div>' +
              '<div class="row">CH: ' + escapeHtml(node.chIdHex || node.parent || "-") + '</div>' +
              '<div class="row">gas: ' + escapeHtml(node.gasName || "-") + ' (class ' + escapeHtml(node.gasClass ?? "-") + ')</div>' +
              '<div class="row">confidence: ' + escapeHtml(node.confidence ?? "-") + '%</div>' +
              '<div class="row">battery: ' + escapeHtml(node.batteryMv !== undefined && node.batteryMv !== null ? node.batteryMv + " mV" : "-") + '</div>' +
              '<div class="row">power: ' + (node.externalPower ? "external" : "battery") + '</div>' +
              '<div class="row">alarm: ' + (node.alarm ? "YA" : "tidak") + '</div>' +
              '<div class="row">seq: ' + escapeHtml(node.seq ?? "-") + ' | decode: ' + (node.decryptOk === false ? "gagal" : "OK") + '</div>' +
              '<div class="row">last seen: ' + escapeHtml(ageLabel(node.lastSeenAgeSec)) + '</div>'
            :
            '<div class="title">' + escapeHtml(node.label || "-") + '</div>' +
            '<div class="layer">' + escapeHtml(node.layerLabel || ("Layer " + (node.layer ?? "?"))) + '</div>' +
            '<div class="row">parent: ' + escapeHtml(node.parent || "-") + '</div>' +
            '<div class="row">alt parent: ' + escapeHtml(node.parentAlt && node.parentAlt !== "0x0000" ? node.parentAlt : "-") + '</div>' +
            '<div class="row">route depth: ' + escapeHtml(node.depth ?? "-") + '</div>' +
            '<div class="row">' + escapeHtml(node.batteryLabel || "battery: belum ada") + '</div>' +
            '<div class="row" title="' + escapeHtml(metric) + '">' + escapeHtml(metric) + '</div>' +
            '<div class="row" title="' + escapeHtml(gatewayMetric) + '">' + escapeHtml(gatewayMetric) + '</div>' +
            '<div class="row" title="' + escapeHtml(ageMetric) + '">' + escapeHtml(ageMetric) + '</div>' +
            '<div class="row">status: ' + escapeHtml(node.status || "-") + '</div>' +
            '<div class="route">' + escapeHtml(node.routeText || "") + '</div>' +
            (node.type === "ch"
              ? '<div class="card-actions"><button class="table-action" data-action="request" data-node-id="' + escapeHtml(node.id || "") + '"' + (node.requestPayload ? "" : " disabled") + '>Request GLD</button></div>'
              : "");
          attachDrag(div, node.id);
          nodesEl.appendChild(div);
        });
      }

      canvas.style.minHeight = Math.max(560, top + (groups.length + 1) * rowGap) + "px";
      updateCanvasHeight();
      renderLinks();
      hasRendered = true;
    }

    async function refresh() {
      if (dragActive) return;
      try {
        const res = await fetch("/pertamina-gld/topology", { cache: "no-store" });
        const data = await res.json();
        draw(data);
      } catch (err) {
        statusEl.textContent = "Topology fetch failed: " + err.message;
      }
    }
    async function resetRouting() {
      try {
        resetButton.disabled = true;
        const res = await fetch("/pertamina-gld/topology/reset", { method: "POST", cache: "no-store" });
        const data = await res.json();
        nodeSignals.clear();
        hasRendered = false;
        draw(data);
      } catch (err) {
        statusEl.textContent = "Topology reset failed: " + err.message;
      } finally {
        resetButton.disabled = false;
      }
    }
    async function requestNode(nodeId, button) {
      if (!nodeId) return;
      try {
        if (button) button.disabled = true;
        const res = await fetch("/pertamina-gld/topology/request?ch=" + encodeURIComponent(nodeId), { method: "POST", cache: "no-store" });
        const data = await res.json();
        if (!res.ok || !data.ok) {
          statusEl.textContent = "Request gagal: " + (data.reason || res.status);
          return;
        }
        statusEl.textContent = "Request dikirim ke " + nodeId + " via " + (Array.isArray(data.hopList) ? data.hopList.join(" -> ") : "-");
      } catch (err) {
        statusEl.textContent = "Request gagal: " + err.message;
      } finally {
        if (button) button.disabled = false;
      }
    }
    async function deleteNode(nodeId, button) {
      if (!nodeId) return;
      try {
        if (button) button.disabled = true;
        const res = await fetch("/pertamina-gld/topology/delete?ch=" + encodeURIComponent(nodeId), { method: "POST", cache: "no-store" });
        const data = await res.json();
        if (!res.ok || !data.ok) {
          statusEl.textContent = "Hapus gagal: " + (data.reason || res.status);
          return;
        }
        nodeSignals.delete(nodeId);
        hasRendered = false;
        await refresh();
      } catch (err) {
        statusEl.textContent = "Hapus gagal: " + err.message;
      } finally {
        if (button) button.disabled = false;
      }
    }
    document.getElementById("refresh").addEventListener("click", refresh);
    nodesEl.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action][data-node-id]");
      if (!button) return;
      if (button.dataset.action === "request") {
        requestNode(button.dataset.nodeId, button);
      }
    });
    pendingDetailsEl.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action][data-node-id]");
      if (!button) return;
      const nodeId = button.dataset.nodeId;
      if (button.dataset.action === "request") {
        requestNode(nodeId, button);
      } else if (button.dataset.action === "delete") {
        deleteNode(nodeId, button);
      }
    });
    resetLayoutButton.addEventListener("click", () => {
      localStorage.removeItem(layoutStorageKey);
      refresh();
    });
    resetButton.addEventListener("click", resetRouting);
    refresh();
    setInterval(refresh, 1000);
  </script>
</body>
</html>\`;
return msg;`;

const nodes = [
  {
    id: tab,
    type: "tab",
    label: "Pertamina GLD Server",
    disabled: false,
    info: `Generated by apply-pertamina-gld-flow.js v${generatorVersion}`,
    env: [
      { name: "GATEWAY_STATUS_URL", value: gatewayStatusUrl, type: "str" },
      { name: "GATEWAY_BASE_URL", value: gatewayBaseUrl, type: "str" },
      { name: "PGL_GATEWAY_ID", value: "0x006F", type: "str" },
      { name: "PGL_REPLAY_STATE_PATH", value: replayStatePath, type: "str" }
    ]
  },
  nodeBase("inject", "poll_gateway", {
    name: "poll Gateway /api/status",
    props: [{ p: "payload" }, { p: "topic", vt: "str" }],
    repeat: enableGatewayPoll ? "5" : "",
    crontab: "",
    once: enableGatewayPoll,
    onceDelay: "2",
    topic: "gateway/status/poll",
    payload: "",
    payloadType: "date",
    x: 180,
    y: 100,
    wires: [[id("http_gateway_status")]]
  }),
  nodeBase("http request", "http_gateway_status", {
    name: "GET Gateway status",
    method: "GET",
    ret: "obj",
    paytoqs: "ignore",
    url: gatewayStatusUrl,
    tls: "",
    persist: false,
    proxy: "",
    insecureHTTPParser: false,
    authType: "",
    x: 420,
    y: 100,
    wires: [[id("decode")]]
  }),
  nodeBase("http in", "http_decode_in", {
    name: "POST /pertamina-gld/decode",
    url: "/pertamina-gld/decode",
    method: "post",
    upload: false,
    swaggerDoc: "",
    x: 190,
    y: 240,
    wires: [[id("decode")]]
  }),
  nodeBase("mqtt in", "mqtt_uplink", {
    name: "MQTT Gateway uplink",
    topic: "gld/gateway/uplink",
    qos: "0",
    datatype: "auto-detect",
    broker,
    nl: false,
    rap: true,
    rh: 0,
    inputs: 0,
    x: 180,
    y: 300,
    wires: [[id("decode")]]
  }),
  nodeBase("mqtt in", "mqtt_topology", {
    name: "MQTT Gateway topology",
    topic: "gld/gateway/topology",
    qos: "0",
    datatype: "auto-detect",
    broker,
    nl: false,
    rap: true,
    rh: 0,
    inputs: 0,
    x: 180,
    y: 330,
    wires: [[id("decode")]]
  }),
  nodeBase("mqtt in", "mqtt_raw", {
    name: "MQTT Gateway raw",
    topic: "gld/gateway/raw",
    qos: "0",
    datatype: "auto-detect",
    broker,
    nl: false,
    rap: true,
    rh: 0,
    inputs: 0,
    x: 180,
    y: 380,
    wires: [[id("decode")]]
  }),
  nodeBase("mqtt in", "mqtt_pertamina_uplink", {
    name: "MQTT Pertamina uplink",
    topic: "pertamina/gld/uplink",
    qos: "0",
    datatype: "auto-detect",
    broker,
    nl: false,
    rap: true,
    rh: 0,
    inputs: 0,
    x: 190,
    y: 440,
    wires: [[id("decode")]]
  }),
  nodeBase("function", "decode", {
    name: "decode Gateway/GLD contract",
    func: decodeFunction,
    outputs: 4,
    timeout: 0,
    noerr: 0,
    initialize: "",
    finalize: "",
    libs: [{ var: "fs", module: "fs" }, { var: "path", module: "path" }],
    x: 700,
    y: 140,
    wires: [
      [id("mqtt_status"), id("debug_status")],
      [id("mqtt_events"), id("debug_events"), id("compact_topology_debug")],
      [id("mqtt_decoded"), id("compact_decoded_debug"), id("http_decode_ok")],
      [id("mqtt_error"), id("debug_error"), id("http_decode_error")]
    ]
  }),
  nodeBase("function", "http_decode_ok", {
    name: "HTTP decode OK",
    func: "if (!msg.req || !msg.res) {\n    return null;\n}\nmsg.statusCode = 200;\nreturn msg;",
    outputs: 1,
    timeout: 0,
    noerr: 0,
    initialize: "",
    finalize: "",
    libs: [],
    x: 1220,
    y: 340,
    wires: [[id("http_decode_response")]]
  }),
  nodeBase("function", "http_decode_error", {
    name: "HTTP decode error",
    func: "if (!msg.req || !msg.res) {\n    return null;\n}\nmsg.statusCode = 400;\nreturn msg;",
    outputs: 1,
    timeout: 0,
    noerr: 0,
    initialize: "",
    finalize: "",
    libs: [],
    x: 1220,
    y: 400,
    wires: [[id("http_decode_response")]]
  }),
  nodeBase("http response", "http_decode_response", {
    name: "HTTP decode response",
    statusCode: "",
    headers: {},
    x: 1460,
    y: 370,
    wires: []
  }),
  nodeBase("http in", "http_topology_json_in", {
    name: "GET /pertamina-gld/topology",
    url: "/pertamina-gld/topology",
    method: "get",
    upload: false,
    swaggerDoc: "",
    x: 190,
    y: 500,
    wires: [[id("topology_json")]]
  }),
  nodeBase("function", "topology_json", {
    name: "build topology JSON",
    func: topologyJsonFunction,
    outputs: 1,
    timeout: 0,
    noerr: 0,
    initialize: "",
    finalize: "",
    libs: [],
    x: 460,
    y: 500,
    wires: [[id("http_topology_response")]]
  }),
  nodeBase("http in", "http_topology_reset_in", {
    name: "POST /pertamina-gld/topology/reset",
    url: "/pertamina-gld/topology/reset",
    method: "post",
    upload: false,
    swaggerDoc: "",
    x: 220,
    y: 600,
    wires: [[id("topology_reset")]]
  }),
  nodeBase("function", "topology_reset", {
    name: "reset topology state",
    func: topologyResetFunction,
    outputs: 1,
    timeout: 0,
    noerr: 0,
    initialize: "",
    finalize: "",
    libs: [],
    x: 470,
    y: 600,
    wires: [[id("http_topology_response")]]
  }),
  nodeBase("http in", "http_topology_request_in", {
    name: "POST /pertamina-gld/topology/request",
    url: "/pertamina-gld/topology/request",
    method: "post",
    upload: false,
    swaggerDoc: "",
    x: 230,
    y: 650,
    wires: [[id("topology_request")]]
  }),
  nodeBase("function", "topology_request", {
    name: "request CH pull route",
    func: topologyRequestFunction,
    outputs: 2,
    timeout: 0,
    noerr: 0,
    initialize: "",
    finalize: "",
    libs: [],
    x: 500,
    y: 650,
    wires: [[id("mqtt_out_pull_command"), id("debug_mqtt_command")], [id("http_topology_response")]]
  }),
  nodeBase("http in", "http_topology_delete_in", {
    name: "POST /pertamina-gld/topology/delete",
    url: "/pertamina-gld/topology/delete",
    method: "post",
    upload: false,
    swaggerDoc: "",
    x: 220,
    y: 700,
    wires: [[id("topology_delete")]]
  }),
  nodeBase("function", "topology_delete", {
    name: "delete CH topology state",
    func: topologyDeleteFunction,
    outputs: 1,
    timeout: 0,
    noerr: 0,
    initialize: "",
    finalize: "",
    libs: [],
    x: 500,
    y: 700,
    wires: [[id("http_topology_response")]]
  }),
  nodeBase("http in", "http_topology_view_in", {
    name: "GET /pertamina-gld/topology/view",
    url: "/pertamina-gld/topology/view",
    method: "get",
    upload: false,
    swaggerDoc: "",
    x: 210,
    y: 550,
    wires: [[id("topology_view")]]
  }),
  nodeBase("function", "topology_view", {
    name: "render topology view",
    func: topologyViewFunction,
    outputs: 1,
    timeout: 0,
    noerr: 0,
    initialize: "",
    finalize: "",
    libs: [],
    x: 460,
    y: 550,
    wires: [[id("http_topology_response")]]
  }),
  nodeBase("http response", "http_topology_response", {
    name: "HTTP topology response",
    statusCode: "",
    headers: {},
    x: 760,
    y: 550,
    wires: []
  }),
  nodeBase("catch", "decode_catch", {
    name: "catch decode errors",
    scope: [id("decode"), id("http_decode_ok"), id("http_decode_error")],
    uncaught: false,
    x: 700,
    y: 460,
    wires: [[id("decode_catch_response"), id("debug_error")]]
  }),
  nodeBase("function", "decode_catch_response", {
    name: "HTTP catch response",
    func: "msg.statusCode = 500;\nmsg.payload = { ok:false, kind:'pertamina-gld-error', reason:'node-red-function-error', detail: msg.error ? msg.error.message : 'unknown error' };\nreturn msg;",
    outputs: 1,
    timeout: 0,
    noerr: 0,
    initialize: "",
    finalize: "",
    libs: [],
    x: 970,
    y: 460,
    wires: [[id("http_decode_response")]]
  }),
  nodeBase("mqtt out", "mqtt_status", {
    name: "MQTT gateway status",
    topic: "gld/gateway/status",
    qos: "0",
    retain: "",
    respTopic: "",
    contentType: "application/json",
    userProps: "",
    correl: "",
    expiry: "",
    broker,
    x: 990,
    y: 80,
    wires: []
  }),
  nodeBase("mqtt out", "mqtt_events", {
    name: "MQTT gateway events",
    topic: "gld/gateway/events",
    qos: "0",
    retain: "",
    respTopic: "",
    contentType: "application/json",
    userProps: "",
    correl: "",
    expiry: "",
    broker,
    x: 990,
    y: 120,
    wires: []
  }),
  nodeBase("mqtt out", "mqtt_decoded", {
    name: "MQTT decoded/alarm",
    topic: "",
    qos: "0",
    retain: "",
    respTopic: "",
    contentType: "application/json",
    userProps: "",
    correl: "",
    expiry: "",
    broker,
    x: 990,
    y: 160,
    wires: []
  }),
  nodeBase("function", "compact_decoded_debug", {
    name: "compact decoded debug",
    func: `const p = msg.payload || {};
const outer = p.outer || {};
const response = outer.response || {};
const msgTypeHex = outer.msgType !== undefined ? "0x" + Number(outer.msgType).toString(16).toUpperCase().padStart(2, "0") : undefined;
const ownerChIdHex = outer.response ? outer.responseTargetChIdHex : outer.srcIdHex;
const route = outer.srcIdHex && outer.dstIdHex ? outer.srcIdHex + " -> " + outer.dstIdHex : undefined;
const responseText = msgTypeHex
  ? msgTypeHex + " owner=" + (ownerChIdHex || "?") + " via=" + (outer.srcIdHex || "?") + " -> " + (outer.dstIdHex || "?") + " req=" + (response.requestId ?? "-") + " status=" + (response.status ?? "-") + " records=" + (response.recordCount ?? 0)
  : undefined;
const gasText = p.gasName
  ? p.gasName + " class=" + p.gasClass + " conf=" + p.confidence + "% batt=" + (p.batteryMv ?? "-") + "mV"
  : "no GLD record";
msg.payload = {
  summary: "GLD " + (p.nodeIdHex || "-") + " | CH=" + (ownerChIdHex || "-") + " | req=" + (response.requestId ?? "-") + " | " + gasText,
  response: responseText,
  route,
  nodeIdHex: p.nodeIdHex,
  ownerChIdHex,
  transportSrcIdHex: outer.srcIdHex,
  responseCorrelation: outer.responseCorrelation,
  requestId: response.requestId,
  gasName: p.gasName,
  confidence: p.confidence,
  alarm: p.alarm,
  batteryMv: p.batteryMv,
  decryptOk: p.decryptOk,
  responsePayloadHex: outer.payloadHex
};
return msg;`,
    outputs: 1,
    timeout: 0,
    noerr: 0,
    initialize: "",
    finalize: "",
    libs: [],
    x: 990,
    y: 340,
    wires: [[id("debug_decoded")]]
  }),
  nodeBase("function", "compact_topology_debug", {
    name: "compact topology debug",
    func: `const p = msg.payload || {};
if (p.kind !== "ch-topology") {
  return null;
}

const hopList = Array.isArray(p.hopList) ? p.hopList : [];
const lastHop = hopList.length > 0 ? hopList[hopList.length - 1] : p.clusterIdHex;
const routeText = hopList.length > 0 ? p.gatewayIdHex + " -> " + hopList.join(" -> ") : "route pending";
const layer = hopList.length > 0 ? hopList.length : undefined;
const isConfigRequest = p.report === "ch-config-request" && (p.parentIdHex === "0x0000" || !p.parentIdHex);
const linkText = isConfigRequest
  ? "CH " + (p.ch || p.clusterIdHex || "-") + " request heard by " + (p.gatewayIdHex || "GW")
  : "CH " + (p.ch || p.clusterIdHex || "-") + " parent " + (p.parent || p.parentIdHex || "-");
const rssiSource = isConfigRequest ? (p.gatewayIdHex || "GW") : (p.parentIdHex || p.parent || p.viaHopHex || p.gatewayIdHex || "-");
const rssiTarget = p.clusterIdHex || p.ch || "-";
const rssiLabel = isConfigRequest ? "RSSI to Gateway" : "RSSI";
const receivedAtMs = Date.parse(p.receivedAt || "");
const ageSec = Number.isFinite(receivedAtMs) ? Math.max(0, Math.round((Date.now() - receivedAtMs) / 1000)) : undefined;
const ttlSec = p.discoveryOnly || isConfigRequest
  ? Math.round(Number(env.get("PGL_TOPOLOGY_DISCOVERY_TTL_MS") || "420000") / 1000)
  : Math.round(Number(env.get("PGL_TOPOLOGY_PARENT_TTL_MS") || "900000") / 1000);
const stale = ageSec !== undefined && ageSec > ttlSec;
const stateLabel = stale
  ? "STALE " + (p.discoveryOnly || isConfigRequest ? "DISCOVERY" : "INSTALLED")
  : (p.discoveryOnly || isConfigRequest ? "DISCOVERY CANDIDATE" : "INSTALLED");
const debugDiscovery = String(env.get("PGL_TOPOLOGY_DEBUG_DISCOVERY") || "").trim() === "1";
if ((p.discoveryOnly || isConfigRequest) && !debugDiscovery) {
  return null;
}
const routeSource = hopList.length > 0 && (p.discoveryOnly || isConfigRequest)
  ? "retained current installed route; TTL checked"
  : (hopList.length > 0 ? "installed route" : "no installed route");
msg.payload = {
  summary: stateLabel + " | " + (p.routeStatus || "CH route updated") + " | " + linkText,
  layer: layer !== undefined ? "Layer " + layer : undefined,
  route: routeText,
  routeSource,
  pull: hopList.length > 0 ? JSON.stringify({ requestId: 1, hopList }) : undefined,
  report: p.report,
  discoveryOnly: p.discoveryOnly ? true : undefined,
  stale: stale ? true : undefined,
  ageSec,
  ttlSec,
  ch: p.clusterIdHex,
  parent: isConfigRequest ? undefined : p.parentIdHex,
  rssiSnr: (p.rssi !== undefined || p.snr !== undefined) ? rssiLabel + " " + rssiSource + " -> " + rssiTarget + ": " + (p.rssi ?? "-") + " dBm, SNR " + (p.snr ?? "-") + " dB" : undefined,
  hopList,
  lastHop,
  updatedAt: p.receivedAt
};
return msg;`,
    outputs: 1,
    timeout: 0,
    noerr: 0,
    initialize: "",
    finalize: "",
    libs: [],
    x: 990,
    y: 300,
    wires: [[id("debug_topology")]]
  }),
  nodeBase("mqtt out", "mqtt_error", {
    name: "MQTT errors",
    topic: "gld/gateway/error",
    qos: "0",
    retain: "",
    respTopic: "",
    contentType: "application/json",
    userProps: "",
    correl: "",
    expiry: "",
    broker,
    x: 990,
    y: 200,
    wires: []
  }),
  nodeBase("debug", "debug_status", {
    name: "[STATUS] gateway alive",
    active: false,
    tosidebar: true,
    console: false,
    tostatus: true,
    complete: "payload",
    targetType: "msg",
    statusVal: "payload.kind",
    statusType: "msg",
    x: 970,
    y: 260,
    wires: []
  }),
  nodeBase("debug", "debug_events", {
    name: "[EVENT] gateway envelope",
    active: false,
    tosidebar: true,
    console: false,
    tostatus: true,
    complete: "payload",
    targetType: "msg",
    statusVal: "payload.kind",
    statusType: "msg",
    x: 970,
    y: 300,
    wires: []
  }),
  nodeBase("debug", "debug_decoded", {
    name: "[DECODED FINAL] GLD server data",
    active: true,
    tosidebar: true,
    console: false,
    tostatus: true,
    complete: "payload",
    targetType: "msg",
    statusVal: "payload.summary",
    statusType: "msg",
    x: 1240,
    y: 340,
    wires: []
  }),
  nodeBase("debug", "debug_topology", {
    name: "[TOPOLOGY] CH route",
    active: true,
    tosidebar: true,
    console: false,
    tostatus: true,
    complete: "payload",
    targetType: "msg",
    statusVal: "payload.summary",
    statusType: "msg",
    x: 1240,
    y: 300,
    wires: []
  }),
  nodeBase("debug", "debug_error", {
    name: "[ERROR] decode/server",
    active: true,
    tosidebar: true,
    console: false,
    tostatus: true,
    complete: "payload",
    targetType: "msg",
    statusVal: "payload.reason",
    statusType: "msg",
    x: 970,
    y: 380,
    wires: []
  }),
  nodeBase("mqtt in", "mqtt_cmd_pull", {
    name: "HTTP debug cmd pull",
    topic: "gld/gateway/debug/http-pull",
    qos: "0",
    datatype: "json",
    broker,
    nl: false,
    rap: true,
    rh: 0,
    inputs: 0,
    x: 170,
    y: 500,
    wires: [[id("build_pull")]]
  }),
  nodeBase("function", "build_pull", {
    name: "build /api/pull POST",
    func: `const base = env.get('GATEWAY_BASE_URL') || '${gatewayBaseUrl}';
const p = msg.payload || {};
const hopList = Array.isArray(p.hopList) ? p.hopList : (Array.isArray(p.hop_list) ? p.hop_list : [p.cluster || p.clusterId || '0x0064']);
const cluster = hopList[hopList.length - 1] || '0x0064';
msg.method = 'POST';
msg.url = \`\${base}/api/pull?cluster=\${encodeURIComponent(cluster)}\`;
msg.payload = '';
return msg;`,
    outputs: 1,
    timeout: 0,
    noerr: 0,
    initialize: "",
    finalize: "",
    libs: [],
    x: 420,
    y: 500,
    wires: [[id("http_command"), id("debug_command")]]
  }),
  nodeBase("mqtt in", "mqtt_cmd_node", {
    name: "HTTP debug cmd node",
    topic: "gld/gateway/debug/http-node",
    qos: "0",
    datatype: "json",
    broker,
    nl: false,
    rap: true,
    rh: 0,
    inputs: 0,
    x: 170,
    y: 560,
    wires: [[id("build_node_command")]]
  }),
  nodeBase("function", "build_node_command", {
    name: "build /api/command POST",
    func: `const base = env.get('GATEWAY_BASE_URL') || '${gatewayBaseUrl}';
const p = msg.payload || {};
const cluster = p.cluster || p.clusterId || '0x0064';
const nodeIdParam = p.node || p.nodeId || '0xF001';
const id = p.id || p.commandId || 1;
const ttl = p.ttl || p.ttlSec || 600;
const hex = p.hex || '';
msg.method = 'POST';
msg.url = \`\${base}/api/command?cluster=\${encodeURIComponent(cluster)}&node=\${encodeURIComponent(nodeIdParam)}&id=\${encodeURIComponent(id)}&ttl=\${encodeURIComponent(ttl)}&hex=\${encodeURIComponent(hex)}\`;
msg.payload = '';
return msg;`,
    outputs: 1,
    timeout: 0,
    noerr: 0,
    initialize: "",
    finalize: "",
    libs: [],
    x: 430,
    y: 560,
    wires: [[id("http_command"), id("debug_command")]]
  }),
  nodeBase("http request", "http_command", {
    name: "POST Gateway command",
    method: "use",
    ret: "obj",
    paytoqs: "ignore",
    url: "",
    tls: "",
    persist: false,
    proxy: "",
    insecureHTTPParser: false,
    authType: "",
    x: 720,
    y: 530,
    wires: [[id("debug_command_response")]]
  }),
  nodeBase("debug", "debug_command", {
    name: "[CMD] HTTP bridge request",
    active: false,
    tosidebar: true,
    console: false,
    tostatus: true,
    complete: "url",
    targetType: "msg",
    statusVal: "url",
    statusType: "msg",
    x: 720,
    y: 610,
    wires: []
  }),
  nodeBase("debug", "debug_command_response", {
    name: "[CMD] HTTP bridge response",
    active: false,
    tosidebar: true,
    console: false,
    tostatus: true,
    complete: "payload",
    targetType: "msg",
    statusVal: "statusCode",
    statusType: "msg",
    x: 990,
    y: 530,
    wires: []
  }),
  nodeBase("inject", "inject_pull_ch", {
    name: "Inject SERVER_PULL_REQUEST hopList",
    props: [{ p: "payload" }, { p: "topic", vt: "str" }],
    repeat: "",
    crontab: "",
    once: false,
    onceDelay: "0.1",
    topic: "gld/gateway/cmd/pull",
    payload: JSON.stringify({ requestId: 1, hopList: ["0x0064", "0x0065", "0x0066"] }),
    payloadType: "json",
    x: 220,
    y: 700,
    wires: [[id("resolve_pull_route")]]
  }),
  nodeBase("function", "resolve_pull_route", {
    name: "normalize pull hopList",
    func: `function idHex(value) {
  const raw = String(value || '').trim();
  const n = raw.toLowerCase().startsWith('0x') ? parseInt(raw, 16) : Number(raw);
  if (!Number.isFinite(n)) return null;
  return '0x' + (n & 0xFFFF).toString(16).toUpperCase().padStart(4, '0');
}

const p = msg.payload || {};
const rawHopList = Array.isArray(p.hopList) ? p.hopList : (Array.isArray(p.hop_list) ? p.hop_list : null);
if (!rawHopList || rawHopList.length === 0) {
  node.warn('pull command requires hopList; last hop is the target CH');
  return null;
}

const hopList = rawHopList.map(idHex);
if (hopList.some((hop) => hop === null)) {
  node.warn('pull command has invalid hopList entry');
  return null;
}

const requestId = Number(p.requestId || p.request_id || 1) & 0xFFFF;
const requestedAt = new Date().toISOString();
const requestIndex = flow.get('pglGldRequestIndex') || {};
requestIndex[String(requestId)] = {
  requestId,
  targetChIdHex: hopList[hopList.length - 1],
  hopList,
  requestedAt
};
flow.set('pglGldRequestIndex', requestIndex);

msg.payload = {
  requestId,
  hopList
};
return msg;`,
    outputs: 1,
    timeout: 0,
    noerr: 0,
    initialize: "",
    finalize: "",
    libs: [],
    x: 500,
    y: 700,
    wires: [[id("mqtt_out_pull_command"), id("debug_mqtt_command")]]
  }),
  nodeBase("mqtt out", "mqtt_out_pull_command", {
    name: "MQTT publish pull request",
    topic: "gld/gateway/cmd/pull",
    qos: "0",
    retain: "",
    respTopic: "",
    contentType: "application/json",
    userProps: "",
    correl: "",
    expiry: "",
    broker,
    x: 800,
    y: 700,
    wires: []
  }),
  nodeBase("mqtt in", "mqtt_server_node_command", {
    name: "MQTT high-level node command",
    topic: "gld/server/cmd/node",
    qos: "0",
    datatype: "json",
    broker,
    nl: false,
    rap: true,
    rh: 0,
    inputs: 0,
    x: 200,
    y: 740,
    wires: [[id("build_node_command_auth")]]
  }),
  nodeBase("inject", "inject_node_command", {
    name: "Inject GLD SET_MODE dataset",
    props: [{ p: "payload" }, { p: "topic", vt: "str" }],
    repeat: "",
    crontab: "",
    once: false,
    onceDelay: "0.1",
    topic: "gld/server/cmd/node",
    payload: JSON.stringify({ cluster: "0x0064", node: "0xF001", id: 1, ttl: 600, mode: "dataset" }),
    payloadType: "json",
    x: 200,
    y: 800,
    wires: [[id("mark_trusted_node_command")]]
  }),
  nodeBase("function", "mark_trusted_node_command", {
    name: "mark local node command",
    func: "msg._pglTrustedLocal = true; return msg;",
    outputs: 1,
    timeout: 0,
    noerr: 0,
    initialize: "",
    finalize: "",
    libs: [{ var: "fs", module: "fs" }, { var: "path", module: "path" }],
    x: 450,
    y: 800,
    wires: [[id("build_node_command_auth")]]
  }),
  nodeBase("function", "build_node_command_auth", {
    name: "build authenticated node command",
    func: commandFunction,
    outputs: 1,
    timeout: 0,
    noerr: 0,
    initialize: "",
    finalize: "",
    libs: [],
    x: 520,
    y: 780,
    wires: [[id("mqtt_out_node_command"), id("debug_mqtt_command")]]
  }),
  nodeBase("mqtt out", "mqtt_out_node_command", {
    name: "MQTT publish node command",
    topic: "gld/gateway/cmd/node",
    qos: "0",
    retain: "",
    respTopic: "",
    contentType: "application/json",
    userProps: "",
    correl: "",
    expiry: "",
    broker,
    x: 820,
    y: 780,
    wires: []
  }),
  nodeBase("debug", "debug_mqtt_command", {
    name: "[CMD] MQTT command inject",
    active: true,
    tosidebar: true,
    console: false,
    tostatus: true,
    complete: "payload",
    targetType: "msg",
    statusVal: "topic",
    statusType: "msg",
    x: 560,
    y: 820,
    wires: []
  }),
  {
    id: broker,
    type: "mqtt-broker",
    name: "Pertamina GLD MQTT",
    broker: mqttHost,
    port: mqttPort,
    clientid: "node-red-pertamina-gld",
    autoConnect: true,
    usetls: mqttTls,
    tls: mqttTls ? id("mqtt_tls") : "",
    protocolVersion: "4",
    keepalive: "60",
    cleansession: true,
    birthTopic: "",
    birthQos: "0",
    birthPayload: "",
    birthMsg: {},
    closeTopic: "",
    closeQos: "0",
    closePayload: "",
    closeMsg: {},
    willTopic: "",
    willQos: "0",
    willPayload: "",
    willMsg: {},
    userProps: "",
    sessionExpiry: ""
  },
  ...(mqttTls ? [{
    id: id("mqtt_tls"),
    type: "tls-config",
    name: "Pertamina GLD MQTT TLS",
    cert: "",
    key: "",
    ca: mqttCaPath,
    certname: "",
    keyname: "",
    caname: mqttCaPath ? path.basename(mqttCaPath) : "",
    servername: mqttHost,
    verifyservercert: !mqttTlsInsecure,
    alpnprotocol: ""
  }] : [])
];

const flowPath = path.join(scriptDir, "pertamina-gld-server.flow.json");
const renderedFlow = JSON.stringify(nodes, null, 2);
if (checkOnly) {
  const currentFlow = fs.existsSync(flowPath) ? fs.readFileSync(flowPath, "utf8") : "";
  if (currentFlow !== renderedFlow) {
    console.error(JSON.stringify({ generated: false, drift: true, flowPath }));
    process.exit(1);
  }
  console.log(JSON.stringify({ generated: false, drift: false, flowPath, nodes: nodes.length }));
  process.exit(0);
}
fs.writeFileSync(flowPath, renderedFlow);

if (generateOnly) {
  console.log(JSON.stringify({ generated: true, flowPath, nodes: nodes.length }));
  process.exit(0);
}

function requestJson(method, url, body, headers = {}) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const data = body === undefined ? undefined : JSON.stringify(body);
    const req = http.request({
      method,
      hostname: parsed.hostname,
      port: parsed.port || 80,
      path: parsed.pathname + parsed.search,
      headers: Object.assign({
        "Content-Type": "application/json",
        "Content-Length": data ? Buffer.byteLength(data) : 0
      }, headers)
    }, (res) => {
      let chunks = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => { chunks += chunk; });
      res.on("end", () => {
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(`HTTP ${res.statusCode}: ${chunks}`));
          return;
        }
        try {
          resolve(chunks ? JSON.parse(chunks) : {});
        } catch (_) {
          resolve(chunks);
        }
      });
    });
    req.on("error", reject);
    if (data) req.write(data);
    req.end();
  });
}

function backupIfExists(file, backupDir, timestamp) {
  if (!fs.existsSync(file)) return;
  fs.copyFileSync(file, path.join(backupDir, `${path.basename(file)}.${timestamp}.bak`));
}

(async () => {
  const timestamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "").replace("T", "_");
  const backupDir = path.join(nodeRedUserDir, "pertamina-gld-backups");
  fs.mkdirSync(backupDir, { recursive: true });
  for (const name of ["flows.json", "flows_cred.json", "settings.js", "package.json", "package-lock.json", ".config.runtime.json"]) {
    backupIfExists(path.join(nodeRedUserDir, name), backupDir, timestamp);
  }

  const adminHeaders = { "Node-RED-API-Version": "v2" };
  if (nodeRedToken) adminHeaders.Authorization = `Bearer ${nodeRedToken}`;
  const current = await requestJson("GET", `${nodeRedUrl}/flows`, undefined, adminHeaders);
  if (!current || Array.isArray(current) || !current.rev || !Array.isArray(current.flows)) {
    throw new Error("Node-RED /flows must return the v2 envelope with rev and flows");
  }
  const currentFlows = current.flows;
  const replacedTabIds = new Set(currentFlows
    .filter((node) => node.type === "tab" && node.label === "Pertamina GLD Server")
    .map((node) => String(node.id || "")));
  const kept = currentFlows.filter((node) => {
    const nodeId = String(node.id || "");
    const parentTabId = String(node.z || "");
    return !(nodeId.startsWith("pgl_") || nodeId === broker ||
      replacedTabIds.has(nodeId) || replacedTabIds.has(parentTabId));
  });
  const merged = kept.concat(nodes);

  const deploymentFlows = merged.map((node) => Object.assign({}, node));
  if (mqttUser && mqttPassword) {
    const brokerNode = deploymentFlows.find((node) => node.id === broker);
    if (!brokerNode) throw new Error("generated MQTT broker node is missing");
    brokerNode.credentials = { user: mqttUser, password: mqttPassword };
  }
  const body = { rev: current.rev, flows: deploymentFlows };
  const response = await requestJson("POST", `${nodeRedUrl}/flows`, body, Object.assign({}, adminHeaders, {
    "Node-RED-Deployment-Type": "full"
  }));

  console.log(JSON.stringify({
    applied: true,
    nodeRedUrl,
    flowPath,
    backupDir,
    addedNodes: nodes.length,
    totalNodes: merged.length,
    apiShape: "v2-envelope",
    mqttCredentialsApplied: Boolean(mqttUser && mqttPassword),
    response
  }));
})().catch((err) => {
  console.error(JSON.stringify({ applied: false, error: err.message }));
  process.exit(1);
});
