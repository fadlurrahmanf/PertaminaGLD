"use strict";

const assert = require("assert");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const decoderPath = path.join(__dirname, "..", "functions", "pertamina-gld-decode.js");
const decoderSource = fs.readFileSync(decoderPath, "utf8");
const flowPath = path.join(__dirname, "..", "pertamina-gld-server.flow.json");

function flowContext(store) {
  return {
    get: (name) => store[name],
    set: (name, value) => { store[name] = value; }
  };
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

const topology = store.pglTopology;
assert.deepEqual(Object.keys(topology.gateways).sort(), ["0x0002", "0x0003"]);
assert.deepEqual(topology.routes["0x0010"], ["0x0010"]);
assert.deepEqual(topology.routes["0x0011"], ["0x0011"]);
assert.equal(topology.routeGateways["0x0010"], "0x0002");
assert.equal(topology.routeGateways["0x0011"], "0x0003");
assert(topology.gatewayLinks["0x0012"]["0x0002"]);
assert(topology.gatewayLinks["0x0012"]["0x0003"]);

const wrongDirectRoot = runDecoder(topologyEvent(0x0002, 0x0013, 0x0003), store);
assert.match(wrongDirectRoot[3].payload.detail, /does not match ingress/);
assert.equal(store.pglTopology.parents["0x0013"], undefined);
const wrongParentRoot = runDecoder(topologyEvent(0x0003, 0x0014, 0x0010), store);
assert.match(wrongParentRoot[3].payload.detail, /belongs to 0x0002/);
assert.equal(store.pglTopology.parents["0x0014"], undefined);
const wrongAlternateRole = runDecoder(topologyEvent(0x0002, 0x0015, 0x0002, "ch-hello", { parentAltId: 0x1001 }), store);
assert.match(wrongAlternateRole[3].payload.detail, /alternate parent ID/);
assert.equal(store.pglTopology.parents["0x0015"], undefined);

for (const badGateway of [0x0000, 0x0010, 0xFF00, 0xFFFF, 0x10001, "0x0002junk"]) {
  const result = runDecoder(topologyEvent(badGateway, 0x0013, badGateway), {});
  assert.match(result[3].payload.detail, /topology gateway ID/);
}
for (const badCluster of [0x000F, 0x1000, 0x1001, 0xFF00]) {
  const result = runDecoder(topologyEvent(0x0002, badCluster, 0x0002), {});
  assert.match(result[3].payload.detail, /topology cluster ID/);
}

const generatedFlow = JSON.parse(fs.readFileSync(flowPath, "utf8"));
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

console.log("PASS multi-Gateway topology roots and role boundaries");
