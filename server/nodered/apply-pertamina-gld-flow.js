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

const nodeRedUrl = args.get("node-red-url") || "http://127.0.0.1:1880";
const nodeRedUserDir = args.get("node-red-user-dir") || "C:\\Users\\asus\\.node-red";
const gatewayStatusUrl = args.get("gateway-status-url") || "http://192.168.4.1/api/status";
const gatewayBaseUrl = args.get("gateway-base-url") || "http://192.168.4.1";
const mqttHost = args.get("mqtt-host") || "127.0.0.1";
const mqttPort = String(args.get("mqtt-port") || "1884");
const mqttUser = args.get("mqtt-user") || process.env.MQTT_USER || "";
const mqttPassword = args.get("mqtt-password") || process.env.MQTT_PASS || "";
const generateOnly = args.has("generate-only");
const enableGatewayPoll = args.has("enable-gateway-poll");

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
  routes: {},
  updatedAt: null
};
topology.gatewayIdHex = topology.gatewayIdHex || gatewayIdHex;
const directGatewayMinRssiDbm = Number(env.get("PGL_GATEWAY_DIRECT_PARENT_MIN_RSSI_DBM") || "-95");
const directGatewayMinSnrDb = Number(env.get("PGL_GATEWAY_DIRECT_PARENT_MIN_SNR_DB") || "5");
const topologyParentTtlMs = Number(env.get("PGL_TOPOLOGY_PARENT_TTL_MS") || "900000");
const topologyDiscoveryTtlMs = Number(env.get("PGL_TOPOLOGY_DISCOVERY_TTL_MS") || "90000");
const topologyGatewayLinkTtlMs = Number(env.get("PGL_TOPOLOGY_GATEWAY_LINK_TTL_MS") || "90000");

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
topology.routes = topology.routes || {};
pruneMapByTtl(topology.parents, topologyParentTtlMs);
pruneMapByTtl(topology.discovery, topologyDiscoveryTtlMs);
pruneMapByTtl(topology.gatewayLinks, topologyGatewayLinkTtlMs);
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
  const lastSeenAgeSec = Math.round(ageMsOf(entry) / 1000);
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
  const lastSeenAgeSec = Math.round(ageMsOf(event) / 1000);
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
    requestPayload: null,
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
  nodes,
  edges,
  routes: publicRoutes,
  discovery: topology.discovery || {}
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
  routes: {},
  updatedAt: null,
  discoveryUpdatedAt: null,
  resetAt
};
flow.set("pglTopology", topology);

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
  gatewayLinks: {}
};
return msg;`;

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
      border: 1px solid #334155;
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 10px 26px rgba(0,0,0,.26);
    }
    .node.updated {
      animation: chUpdateFlash 1.8s ease-out 1;
    }
    .node.gateway { border-color: var(--gw); }
    .node.ch { border-color: var(--ch); }
    .node.pending { border-color: var(--warn); }
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
        border-color: var(--ch);
        background: var(--panel);
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
  </style>
</head>
<body>
  <header>
    <h1>Pertamina GLD Topology</h1>
    <div class="meta">
      <div id="summary">loading...</div>
      <div>Auto refresh 3 detik</div>
    </div>
  </header>
  <main>
    <div class="toolbar">
      <div class="status" id="status">Mengambil topology...</div>
      <div class="legend">
        <span class="legend-item"><span class="legend-line"></span>Main Parent</span>
        <span class="legend-item"><span class="legend-line alt"></span>Alternative Parent</span>
        <span class="legend-item"><span class="legend-line pending"></span>Pending Parent</span>
      </div>
      <div class="actions">
        <button id="refresh">Refresh</button>
        <button id="resetRouting" class="danger">Reset Routing</button>
      </div>
    </div>
    <div class="canvas" id="canvas">
      <svg id="links"></svg>
      <div id="nodes"></div>
    </div>
  </main>
  <script>
    const canvas = document.getElementById("canvas");
    const nodesEl = document.getElementById("nodes");
    const linksEl = document.getElementById("links");
    const statusEl = document.getElementById("status");
    const summaryEl = document.getElementById("summary");
    const resetButton = document.getElementById("resetRouting");
    const nodeSignals = new Map();
    let hasRendered = false;

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

    function draw(data) {
      nodesEl.innerHTML = "";
      linksEl.innerHTML = "";
      const nodes = data.nodes || [];
      const edges = data.edges || [];
      summaryEl.textContent = data.nodeCount + " node, " + (data.mainEdgeCount ?? data.edgeCount) + " main link, " + (data.alternateEdgeCount || 0) + " alt link, " + (data.pendingEdgeCount || 0) + " pending link, " + (data.discoveryCount || 0) + " discovery";
      statusEl.textContent = "Topology: " + (data.topologyUpdatedAt || data.updatedAt || "belum ada topology event") +
        " | Live: " + (data.liveUpdatedAt || "belum ada live event");
      if (data.resetAt && nodes.length <= 1) {
        statusEl.textContent = "Routing reset: " + data.resetAt + " | Menunggu update routing berikutnya";
      }
      if (nodes.length <= 1) {
        nodesEl.innerHTML = '<div class="empty">Belum ada CH route. Tunggu CH_CONFIG/CH_HELLO masuk dari Gateway.</div>';
      }

      const positions = {};
      const groups = groupByDepth(nodes);
      const width = Math.max(canvas.clientWidth, 760);
      const nodeW = 240;
      const rowGap = 270;
      const top = 56;
      for (const [layer, items] of groups) {
        items.sort((a, b) => String(a.id).localeCompare(String(b.id)));
        const totalW = items.length * nodeW + Math.max(0, items.length - 1) * 44;
        const startX = Math.max(24, (width - totalW) / 2);
        items.forEach((node, index) => {
          const x = startX + index * (nodeW + 44);
          const y = top + layer * rowGap;
          positions[node.id] = { x, y, cx: x + nodeW / 2, cy: y + 47 };
          const div = document.createElement("div");
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
          div.style.left = x + "px";
          div.style.top = y + "px";
          const metric = node.type === "gateway"
            ? "root"
            : (node.linkQualityLabel || ("RSSI to Parent: " + (node.rssi ?? "-") + " dBm, SNR " + (node.snr ?? "-") + " dB"));
          const gatewayMetric = node.type === "gateway"
            ? ""
            : (node.gatewayQualityLabel || "RSSI to Gateway: belum ada");
          const ageMetric = node.type === "gateway"
            ? ""
            : ("last update: " + (node.lastSeenAgeSec !== undefined ? node.lastSeenAgeSec + "s ago" : "belum ada"));
          div.innerHTML =
            '<div class="title">' + node.label + '</div>' +
            '<div class="layer">' + (node.layerLabel || ("Layer " + (node.layer ?? "?"))) + '</div>' +
            '<div class="row">parent: ' + (node.parent || "-") + '</div>' +
            '<div class="row">alt parent: ' + (node.parentAlt && node.parentAlt !== "0x0000" ? node.parentAlt : "-") + '</div>' +
            '<div class="row">route depth: ' + (node.depth ?? "-") + '</div>' +
            '<div class="row">' + (node.batteryLabel || "battery: belum ada") + '</div>' +
            '<div class="row" title="' + metric + '">' + metric + '</div>' +
            '<div class="row" title="' + gatewayMetric + '">' + gatewayMetric + '</div>' +
            '<div class="row" title="' + ageMetric + '">' + ageMetric + '</div>' +
            (node.pendingReason ? '<div class="row" title="' + node.pendingReason + '">' + node.pendingReason + '</div>' : '') +
            '<div class="row">status: ' + node.status + '</div>' +
            '<div class="route">' + (node.routeText || "") + '</div>';
          nodesEl.appendChild(div);
        });
      }

      canvas.style.minHeight = Math.max(560, top + (groups.length + 1) * rowGap) + "px";
      for (const edge of edges) {
        const a = positions[edge.from];
        const b = positions[edge.to];
        if (!a || !b) continue;
        const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
        line.setAttribute("x1", a.cx);
        line.setAttribute("y1", a.cy + 47);
        line.setAttribute("x2", b.cx);
        line.setAttribute("y2", b.cy - 47);
        line.setAttribute("stroke", edge.role === "alternate" ? "#f59e0b" : (edge.role === "pending" ? "#f59e0b" : "#38bdf8"));
        line.setAttribute("stroke-width", edge.role === "main" ? "3" : "2");
        if (edge.role === "alternate") {
          line.setAttribute("stroke-dasharray", "7 7");
        } else if (edge.role === "pending") {
          line.setAttribute("stroke-dasharray", "3 7");
        }
        linksEl.appendChild(line);
      }
      hasRendered = true;
    }

    async function refresh() {
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
    document.getElementById("refresh").addEventListener("click", refresh);
    resetButton.addEventListener("click", resetRouting);
    refresh();
    setInterval(refresh, 3000);
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
    info: "Generated by D:\\PertaminaGLD\\server\\nodered\\apply-pertamina-gld-flow.js",
    env: [
      { name: "GATEWAY_STATUS_URL", value: gatewayStatusUrl, type: "str" },
      { name: "GATEWAY_BASE_URL", value: gatewayBaseUrl, type: "str" },
      { name: "PGL_GATEWAY_ID", value: "0x006F", type: "str" }
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
  nodeBase("inject", "test_vector", {
    name: "GLD AES-GCM test vector",
    props: [{ p: "payload" }, { p: "topic", vt: "str" }],
    repeat: "",
    crontab: "",
    once: false,
    onceDelay: "0.1",
    topic: "gld/test/vector",
    payload: JSON.stringify({
      recordHex: "F0012A111D01101112131415161718191A1BC57E0DDBF88ABEC591E9F5BFAD982A6C"
    }),
    payloadType: "json",
    x: 190,
    y: 180,
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
    libs: [],
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
const route = outer.srcIdHex && outer.dstIdHex ? outer.srcIdHex + " -> " + outer.dstIdHex : undefined;
const responseText = msgTypeHex
  ? msgTypeHex + " " + (outer.srcIdHex || "?") + " -> " + (outer.dstIdHex || "?") + " req=" + (response.requestId ?? "-") + " status=" + (response.status ?? "-") + " records=" + (response.recordCount ?? 0)
  : undefined;
const gasText = p.gasName
  ? p.gasName + " class=" + p.gasClass + " conf=" + p.confidence + "% batt=" + (p.batteryMv ?? "-") + "mV"
  : "no GLD record";
msg.payload = {
  summary: "GLD " + (p.nodeIdHex || "-") + " | req=" + (response.requestId ?? "-") + " | " + gasText,
  response: responseText,
  route,
  nodeIdHex: p.nodeIdHex,
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
  ? Math.round(Number(env.get("PGL_TOPOLOGY_DISCOVERY_TTL_MS") || "90000") / 1000)
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

msg.payload = {
  requestId: Number(p.requestId || p.request_id || 1),
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
  nodeBase("inject", "inject_node_command", {
    name: "Inject GLD command placeholder",
    props: [{ p: "payload" }, { p: "topic", vt: "str" }],
    repeat: "",
    crontab: "",
    once: false,
    onceDelay: "0.1",
    topic: "gld/gateway/cmd/node",
    payload: JSON.stringify({ cluster: "0x0064", node: "0xF001", id: 1, ttl: 600, hex: "0102" }),
    payloadType: "json",
    x: 200,
    y: 760,
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
    x: 560,
    y: 760,
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
    id: id("aedes_broker"),
    type: "aedes broker",
    z: tab,
    name: "Pertamina GLD Aedes",
    mqtt_port: Number(mqttPort),
    mqtt_ws_bind: "port",
    mqtt_ws_port: "",
    mqtt_ws_path: "",
    cert: "",
    key: "",
    certname: "",
    keyname: "",
    persistence_bind: "memory",
    dburl: "",
    usetls: false,
    x: 180,
    y: 860,
    wires: [[], []]
  },
  {
    id: broker,
    type: "mqtt-broker",
    name: "Pertamina GLD MQTT",
    broker: mqttHost,
    port: mqttPort,
    clientid: "node-red-pertamina-gld",
    autoConnect: true,
    usetls: false,
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
  }
];

const flowPath = path.join(scriptDir, "pertamina-gld-server.flow.json");
fs.writeFileSync(flowPath, JSON.stringify(nodes, null, 2));

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

  const current = await requestJson("GET", `${nodeRedUrl}/flows`);
  const currentFlows = Array.isArray(current) ? current : (current.flows || current.value || []);
  const kept = currentFlows.filter((node) => {
    const nodeId = String(node.id || "");
    return !(nodeId.startsWith("pgl_") || nodeId === broker);
  });
  const merged = kept.concat(nodes);

  let response;
  if (Array.isArray(current)) {
    response = await requestJson("POST", `${nodeRedUrl}/flows`, merged, { "Node-RED-Deployment-Type": "full" });
  } else {
    const body = {
      rev: current.rev,
      flows: merged,
      credentials: {}
    };
    if (mqttUser && mqttPassword) {
      body.credentials[broker] = { user: mqttUser, password: mqttPassword };
    }
    response = await requestJson("POST", `${nodeRedUrl}/flows`, body, { "Node-RED-Deployment-Type": "full" });
  }

  console.log(JSON.stringify({
    applied: true,
    nodeRedUrl,
    flowPath,
    backupDir,
    addedNodes: nodes.length,
    totalNodes: merged.length,
    apiShape: Array.isArray(current) ? "array" : "envelope",
    mqttCredentialsApplied: Boolean(!Array.isArray(current) && mqttUser && mqttPassword),
    response
  }));
})().catch((err) => {
  console.error(JSON.stringify({ applied: false, error: err.message }));
  process.exit(1);
});
