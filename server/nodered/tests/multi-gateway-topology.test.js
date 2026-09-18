"use strict";

const assert = require("assert");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const decoderPath = path.join(__dirname, "..", "functions", "pertamina-gld-decode.js");
const decoderSource = fs.readFileSync(decoderPath, "utf8");
const flowPath = path.join(__dirname, "..", "pertamina-gld-server.flow.json");

function crc16CcittFalse(bytes) {
  let crc = 0xFFFF;
  for (const byte of bytes) {
    crc ^= byte << 8;
    for (let bit = 0; bit < 8; bit++) {
      crc = (crc & 0x8000) ? ((crc << 1) ^ 0x1021) : (crc << 1);
      crc &= 0xFFFF;
    }
  }
  return crc;
}

function appFrameHex(typeFlags, srcId, dstId, seq, payload) {
  const body = Buffer.alloc(8 + payload.length);
  body[0] = 0xAA;
  body[1] = typeFlags;
  body.writeUInt16BE(srcId, 2);
  body.writeUInt16BE(dstId, 4);
  body[6] = seq;
  body[7] = payload.length;
  Buffer.from(payload).copy(body, 8);
  const crc = crc16CcittFalse(body);
  return Buffer.concat([body, Buffer.from([crc >> 8, crc & 0xFF])]).toString("hex");
}

function flowContext(store) {
  return {
    get: (name, storeName) => {
      if (store.throwNamedStore && storeName) throw new Error("unknown context store");
      return storeName
        ? store.contextStores && store.contextStores[storeName] && store.contextStores[storeName][name]
        : store[name];
    },
    set: (name, value, storeName) => {
      if (store.throwNamedStore && storeName) throw new Error("unknown context store");
      if (!storeName) {
        store[name] = value;
        return;
      }
      store.contextStores = store.contextStores || {};
      store.contextStores[storeName] = store.contextStores[storeName] || {};
      store.contextStores[storeName][name] = value;
    }
  };
}

function topologyState(store) {
  return store.contextStores && store.contextStores.pglTopologyFile &&
    store.contextStores.pglTopologyFile.pglTopology;
}

function runDecoder(payload, store) {
  const wrapped = `(function(msg, flow, global, env, node) {\n${decoderSource}\n})`;
  const fn = vm.runInNewContext(wrapped, { Buffer, console }, { filename: decoderPath });
  return fn(
    { payload, topic: "gld/gateway/topology" },
    flowContext(store),
    { get: (name) => ({ crypto, fs, path }[name]) },
    { get: () => undefined },
    { warn: () => {}, error: () => {} }
  );
}

function topologyEvent(gatewayId, clusterId, parentId, report = "ch-hello", extra = {}) {
  return Object.assign({
    kind: "ch-topology",
    report,
    gatewayId,
    clusterId,
    parentId
  }, extra);
}

const store = {};
runDecoder(topologyEvent(0x0002, 0x0010, 0x0002), store);
runDecoder(topologyEvent(0x0003, 0x0011, 0x0003), store);
runDecoder(topologyEvent(0x0002, 0x0012, 0x0000, "ch-config-request", { rssi: -70, snr: 8 }), store);
runDecoder(topologyEvent(0x0003, 0x0012, 0x0000, "ch-config-request", { rssi: -80, snr: 6 }), store);

const topology = topologyState(store);
assert(topology, "decoder must save topology in the named persistent store");
assert.equal(store.pglTopology, undefined, "default memory store must not receive topology state");

const preRestartStore = { throwNamedStore: true };
runDecoder(topologyEvent(0x0002, 0x0010, 0x0002), preRestartStore);
assert(preRestartStore.pglTopology, "pre-restart runtime must fall back to the memory store");
assert.deepEqual(Object.keys(topology.gateways).sort(), ["0x0002", "0x0003"]);
assert.deepEqual(topology.routes["0x0010"], ["0x0010"]);
assert.deepEqual(topology.routes["0x0011"], ["0x0011"]);
assert.equal(topology.routeGateways["0x0010"], "0x0002");
assert.equal(topology.routeGateways["0x0011"], "0x0003");
assert(topology.gatewayLinks["0x0012"]["0x0002"]);
assert(topology.gatewayLinks["0x0012"]["0x0003"]);

const wrongDirectRoot = runDecoder(topologyEvent(0x0002, 0x0013, 0x0003), store);
assert.match(wrongDirectRoot[3].payload.detail, /does not match ingress/);
assert.equal(topologyState(store).parents["0x0013"], undefined);
const wrongParentRoot = runDecoder(topologyEvent(0x0003, 0x0014, 0x0010), store);
assert.match(wrongParentRoot[3].payload.detail, /belongs to 0x0002/);
assert.equal(topologyState(store).parents["0x0014"], undefined);
const wrongAlternateRole = runDecoder(topologyEvent(0x0002, 0x0015, 0x0002, "ch-hello", { parentAltId: 0x1001 }), store);
assert.match(wrongAlternateRole[3].payload.detail, /alternate parent ID/);
assert.equal(topologyState(store).parents["0x0015"], undefined);

for (const badGateway of [0x0000, 0x0010, 0xFF00, 0xFFFF, 0x10001, "0x0002junk"]) {
  const result = runDecoder(topologyEvent(badGateway, 0x0013, badGateway), {});
  assert.match(result[3].payload.detail, /topology gateway ID/);
}
for (const badCluster of [0x000F, 0x1000, 0x1001, 0xFF00]) {
  const result = runDecoder(topologyEvent(0x0002, badCluster, 0x0002), {});
  assert.match(result[3].payload.detail, /topology cluster ID/);
}

const generatedFlow = JSON.parse(fs.readFileSync(flowPath, "utf8"));
const decodeNode = generatedFlow.find((node) => node.id === "pgl_decode");
assert(decodeNode, "generated decoder function must exist");
assert(decodeNode.libs.some((entry) => entry.var === "crypto" && entry.module === "crypto"),
  "production decoder must receive the Node.js crypto module");
const commandNode = generatedFlow.find((node) => node.id === "pgl_build_node_command_auth");
assert(commandNode, "generated authenticated-command function must exist");
assert(commandNode.libs.some((entry) => entry.var === "crypto" && entry.module === "crypto"),
  "authenticated-command builder must receive the Node.js crypto module");
const topologyNode = generatedFlow.find((node) => node.type === "function" && node.name === "build topology JSON");
assert(topologyNode, "generated topology JSON function must exist");
const topologyFn = vm.runInNewContext(`(function(msg, flow, env) {\n${topologyNode.func}\n})`, { console });
const resultMsg = topologyFn(
  {},
  flowContext(store),
  { get: () => undefined }
);

assert.deepEqual(Array.from(resultMsg.payload.gatewayIds), ["0x0002", "0x0003"]);
assert.equal(resultMsg.payload.gatewayIdHex, null, "singleton compatibility field must be null with multiple roots");
assert.equal(resultMsg.payload.nodes.filter((node) => node.type === "gateway").length, 2);
assert(resultMsg.payload.edges.some((edge) => edge.from === "0x0002" && edge.to === "0x0010" && edge.role === "main"));
assert(resultMsg.payload.edges.some((edge) => edge.from === "0x0003" && edge.to === "0x0011" && edge.role === "main"));
assert.equal(resultMsg.payload.nodes.find((node) => node.id === "0x0010").requestPayload.gatewayId, "0x0002");
assert.equal(resultMsg.payload.nodes.find((node) => node.id === "0x0011").requestPayload.gatewayId, "0x0003");

function buildGldAvailabilityView(entry) {
  const state = {};
  runDecoder(topologyEvent(0x0002, 0x0012, 0x0002), state);
  state.pglGldDiscovery = { "0x0012": entry };
  return topologyFn({}, flowContext(state), { get: () => undefined }).payload;
}

const oldAlarmAt = new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString();
const alarmDevice = {
  nodeIdHex: "0x1002",
  gasClass: 2,
  gasName: "LPG",
  confidence: 99,
  batteryMv: 3700,
  alarm: true,
  seq: 42,
  decryptOk: true,
  lastSeenAt: oldAlarmAt
};
const silentAlarmView = buildGldAvailabilityView({
  status: "unsolicited",
  devices: { "0x1002": alarmDevice }
});
const silentAlarmNode = silentAlarmView.nodes.find((node) => node.type === "gld");
assert.equal(silentAlarmNode.status, "alarm",
  "GLD silence alone must never infer offline for request/event-driven telemetry");
assert.equal(silentAlarmNode.currentAlarmActive, true);

const unavailableAt = new Date().toISOString();
const unavailableView = buildGldAvailabilityView({
  status: "received",
  requestId: 22001,
  requestedAt: new Date(Date.now() - 1000).toISOString(),
  respondedAt: unavailableAt,
  responseStatus: 2,
  recordCount: 0,
  devices: { "0x1002": alarmDevice }
});
const unavailableNode = unavailableView.nodes.find((node) => node.type === "gld");
assert.equal(unavailableNode.status, "unavailable");
assert.equal(unavailableNode.availabilityReason, "DATA_NOT_AVAIL");
assert.equal(unavailableNode.currentAlarmActive, false);
assert.equal(unavailableNode.lastKnownAlarm, true,
  "unavailable state must retain the last alarm as historical evidence");

const newerAlarmAt = new Date().toISOString();
const recoveredView = buildGldAvailabilityView({
  status: "received",
  requestId: 22002,
  requestedAt: new Date(Date.now() - 120000).toISOString(),
  respondedAt: new Date(Date.now() - 60000).toISOString(),
  responseStatus: 2,
  recordCount: 0,
  devices: { "0x1002": Object.assign({}, alarmDevice, { lastSeenAt: newerAlarmAt }) }
});
const recoveredNode = recoveredView.nodes.find((node) => node.type === "gld");
assert.equal(recoveredNode.status, "alarm",
  "a newer GLD event must override an older DATA_NOT_AVAIL response");
assert.equal(recoveredNode.currentAlarmActive, true);

const timeoutRequestedAt = new Date(Date.now() - 30000).toISOString();
const timeoutView = buildGldAvailabilityView({
  status: "sent",
  requestId: 22003,
  requestedAt: timeoutRequestedAt,
  devices: {
    "0x1002": Object.assign({}, alarmDevice, {
      lastSeenAt: new Date(Date.now() - 60000).toISOString()
    })
  }
});
const timeoutNode = timeoutView.nodes.find((node) => node.type === "gld");
assert.equal(timeoutView.gldDiscovery["0x0012"].status, "timeout");
assert.equal(timeoutNode.status, "unconfirmed");
assert.equal(timeoutNode.availabilityReason, "REQUEST_TIMEOUT");
assert.equal(timeoutNode.currentAlarmActive, false);
assert.equal(timeoutNode.lastKnownAlarm, true);

for (const responseStatus of [1, 4, 5]) {
  const neutralResponseView = buildGldAvailabilityView({
    status: "received",
    requestId: 22100 + responseStatus,
    requestedAt: new Date(Date.now() - 1000).toISOString(),
    respondedAt: new Date().toISOString(),
    responseStatus,
    recordCount: 0,
    devices: { "0x1002": alarmDevice }
  });
  assert.equal(neutralResponseView.nodes.find((node) => node.type === "gld").status, "alarm",
    `response status ${responseStatus} must not claim the GLD is unavailable`);
}

const contradictoryUnavailableView = buildGldAvailabilityView({
  status: "received",
  requestId: 22004,
  requestedAt: new Date(Date.now() - 1000).toISOString(),
  respondedAt: new Date().toISOString(),
  responseStatus: 2,
  recordCount: 1,
  devices: { "0x1002": alarmDevice }
});
assert.equal(contradictoryUnavailableView.nodes.find((node) => node.type === "gld").status, "alarm",
  "contradictory DATA_NOT_AVAIL with records must not override device evidence");

const parentMetricStore = {};
runDecoder(topologyEvent(0x0002, 0x0010, 0x0002, "ch-hello", {
  srcId: 0x0010,
  parentLinkMetricSupported: true,
  parentLinkMetricValid: true,
  parentRxRssiDbm: -74,
  parentRxSnrDb: 10,
  parentLinkAgeSec: 2,
  gatewayIngressRssiDbm: -82,
  gatewayIngressSnrDb: 8
}), parentMetricStore);
runDecoder(topologyEvent(0x0002, 0x0011, 0x0010, "ch-hello", {
  srcId: 0x0010,
  parentLinkMetricSupported: true,
  parentLinkMetricValid: true,
  parentRxRssiDbm: -81,
  parentRxSnrDb: 9,
  parentLinkAgeSec: 3,
  gatewayIngressRssiDbm: -88,
  gatewayIngressSnrDb: 7
}), parentMetricStore);
const metricView = topologyFn({}, flowContext(parentMetricStore), { get: () => undefined });
const ch11Metric = metricView.payload.nodes.find((node) => node.id === "0x0011");
const ch10Ch11Edge = metricView.payload.edges.find((edge) => edge.from === "0x0010" && edge.to === "0x0011");
assert.equal(ch11Metric.parentRssi, -81, "CH11 card must show CH10 -> CH11 RSSI measured by CH11");
assert.equal(ch11Metric.gatewayRssi, -88, "Gateway ingress RSSI must remain a separate metric");
assert.equal(ch11Metric.gatewayIngressHopIdHex, "0x0010", "topology srcId must be retained as ingress hop");
assert.match(ch11Metric.linkQualityLabel, /RSSI Parent → CH.*-81 dBm/);
assert.match(ch11Metric.gatewayQualityLabel, /Gateway RX dari 0x0010.*-88 dBm/);
assert.equal(ch10Ch11Edge.rssi, -81, "parent edge must never reuse Gateway ingress RSSI");
assert.equal(ch10Ch11Edge.metricDirection, "parent-to-child");

const rawMetricStore = {};
const rawHelloPayload = Buffer.from([
  0x00, 0x11, 0x00, 0x10, 0x10, 0xE1, 0x00, 0x64, 0x02, 0x00, 0x00,
  0x02, 0x03, 0xFF, 0xAF, 0x09, 0x00, 0x03
]);
runDecoder({
  gatewayId: 0x0002,
  frameHex: appFrameHex(0x33, 0x0010, 0x0002, 7, rawHelloPayload),
  rssi: -88,
  snr: 7
}, rawMetricStore);
const rawCh11 = topologyState(rawMetricStore).parents["0x0011"];
assert.equal(rawCh11.parentRxRssiDbm, -81, "signed parent RSSI must decode from CH_HELLO extension");
assert.equal(rawCh11.parentRxSnrDb, 9);
assert.equal(rawCh11.parentLinkAgeSec, 3);
assert.equal(rawCh11.ingressHopIdHex, "0x0010");
assert.equal(rawCh11.gatewayIngressRssiDbm, -88);

const requestNode = generatedFlow.find((node) => node.type === "function" && node.name === "request CH pull route");
assert(requestNode, "generated targeted request function must exist");
const requestFn = vm.runInNewContext(`(function(msg, flow, env) {\n${requestNode.func}\n})`, { console });
for (const [ch, expectedGateway] of [["0x0010", "0x0002"], ["0x0011", "0x0003"]]) {
  const [mqttMsg, httpMsg] = requestFn(
    { req: { query: { ch } } },
    flowContext(store),
    { get: () => undefined }
  );
  assert.equal(mqttMsg.payload.gatewayId, expectedGateway);
  assert.equal(httpMsg.payload.gatewayId, expectedGateway);
  assert.equal(store.pglGldRequestIndex[String(httpMsg.payload.requestId)].gatewayIdHex, expectedGateway);
}

const [, invalidRequest] = requestFn(
  { req: { query: { ch: "0x10001" } } },
  flowContext(store),
  { get: () => undefined }
);
assert.equal(invalidRequest.statusCode, 400);
assert.equal(invalidRequest.payload.reason, "invalid-ch-id");

const staleStore = {
  contextStores: {
    pglTopologyFile: {
      pglTopology: JSON.parse(JSON.stringify(topologyState(store)))
    }
  }
};
topologyState(staleStore).gateways["0x0002"].receivedAt = new Date(Date.now() - 151000).toISOString();
const staleGatewayView = topologyFn(
  {},
  flowContext(staleStore),
  { get: () => undefined }
);
const staleGatewayNode = staleGatewayView.payload.nodes.find((node) => node.id === "0x0010");
assert.equal(staleGatewayNode.status, "gateway-offline");
assert.equal(staleGatewayNode.requestPayload, null);
const [staleMqtt, staleRequest] = requestFn(
  { req: { query: { ch: "0x0010" } } },
  flowContext(staleStore),
  { get: () => undefined }
);
assert.equal(staleMqtt, null, "stale Gateway must not receive an MQTT request");
assert.equal(staleRequest.statusCode, 503);
assert.equal(staleRequest.payload.reason, "gateway-offline-or-stale");
assert.equal(staleRequest.payload.gatewayId, "0x0002");
assert.equal(staleStore.pglGldRequestIndex, undefined, "stale Gateway must not mutate correlation state");
assert.equal(staleStore.pglGldDiscovery, undefined, "stale Gateway must not mutate discovery state");

const staleRouteStore = {
  contextStores: {
    pglTopologyFile: {
      pglTopology: JSON.parse(JSON.stringify(topologyState(store)))
    }
  }
};
topologyState(staleRouteStore).parents["0x0010"].receivedAt = new Date(Date.now() - 421000).toISOString();
const staleRouteView = topologyFn(
  {},
  flowContext(staleRouteStore),
  { get: () => undefined }
);
const staleRouteNode = staleRouteView.payload.nodes.find((node) => node.id === "0x0010");
assert.equal(staleRouteNode.status, "offline");
assert.equal(staleRouteNode.requestPayload, null);
const [staleRouteMqtt, staleRouteRequest] = requestFn(
  { req: { query: { ch: "0x0010" } } },
  flowContext(staleRouteStore),
  { get: () => undefined }
);
assert.equal(staleRouteMqtt, null, "stale CH route must not receive an MQTT request");
assert.equal(staleRouteRequest.statusCode, 409);
assert.equal(staleRouteRequest.payload.reason, "route-stale");
assert.equal(staleRouteRequest.payload.staleHop, "0x0010");
assert.equal(staleRouteStore.pglGldRequestIndex, undefined, "stale route must not mutate correlation state");
assert.equal(staleRouteStore.pglGldDiscovery, undefined, "stale route must not mutate discovery state");

const freshBoundaryStore = {
  contextStores: {
    pglTopologyFile: {
      pglTopology: JSON.parse(JSON.stringify(topologyState(store)))
    }
  }
};
topologyState(freshBoundaryStore).parents["0x0010"].receivedAt = new Date(Date.now() - 419000).toISOString();
const [freshBoundaryMqtt] = requestFn(
  { req: { query: { ch: "0x0010" } } },
  flowContext(freshBoundaryStore),
  { get: () => undefined }
);
assert(freshBoundaryMqtt, "CH route just inside the freshness boundary must remain requestable");

const chainStore = {};
runDecoder(topologyEvent(0x0002, 0x0010, 0x0002), chainStore);
runDecoder(topologyEvent(0x0002, 0x0011, 0x0010), chainStore);
topologyState(chainStore).parents["0x0010"].receivedAt = new Date(Date.now() - 421000).toISOString();
const [staleParentMqtt, staleParentRequest] = requestFn(
  { req: { query: { ch: "0x0011" } } },
  flowContext(chainStore),
  { get: () => undefined }
);
assert.equal(staleParentMqtt, null, "fresh target behind a stale intermediate CH must be rejected");
assert.equal(staleParentRequest.payload.reason, "route-stale");
assert.equal(staleParentRequest.payload.staleHop, "0x0010");

const futureRouteStore = {
  contextStores: {
    pglTopologyFile: {
      pglTopology: JSON.parse(JSON.stringify(topologyState(store)))
    }
  }
};
topologyState(futureRouteStore).parents["0x0010"].receivedAt = new Date(Date.now() + 120000).toISOString();
const [futureRouteMqtt, futureRouteRequest] = requestFn(
  { req: { query: { ch: "0x0010" } } },
  flowContext(futureRouteStore),
  { get: () => undefined }
);
assert.equal(futureRouteMqtt, null, "route timestamp beyond clock skew allowance must be rejected");
assert.equal(futureRouteRequest.payload.reason, "route-stale");

console.log("PASS multi-Gateway topology roots and role boundaries");
