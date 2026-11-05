"use strict";
// Generate a synthetic, authenticated production-format uplink for an ISOLATED
// handover stack. No MQTT/HTTP/network access, filesystem writes or key output.
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const ROOT = path.resolve(__dirname, "..");
const IDS = Object.freeze({ node: 0x1FF0, cluster: 0x0FE0, gateway: 0x000F });
const hexId = (value) => `0x${value.toString(16).toUpperCase().padStart(4, "0")}`;

function requireValid(value) {
  if (!value) throw new Error("synthetic_crypto_configuration_invalid");
}

function crc16(bytes) {
  let crc = 0xFFFF;
  for (const value of bytes) {
    crc ^= value << 8;
    for (let bit = 0; bit < 8; bit++) crc = ((crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1) & 0xFFFF;
  }
  return crc;
}

function frame(record, seq) {
  const body = Buffer.alloc(8 + record.length);
  body[0] = 0xAA;
  body[1] = 0x90; // SENSOR_DATA0x10 + external-power flag0x80; no alarm.
  body.writeUInt16BE(IDS.cluster, 2); body.writeUInt16BE(IDS.gateway, 4);
  body[6] = seq; body[7] = record.length; record.copy(body, 8);
  const checksum = crc16(body);
  return Buffer.concat([body, Buffer.from([checksum >> 8, checksum & 0xFF])]);
}

function build(system) {
  requireValid(system && system.schemaVersion === 1 && system.serverEnv &&
    typeof system.serverEnv.GLD_AES128_KEY_HEX === "string" &&
    /^[0-9a-fA-F]{32}$/.test(system.serverEnv.GLD_AES128_KEY_HEX));
  const keyId = Number(system.serverEnv.GLD_KEY_ID);
  requireValid(Number.isInteger(keyId) && keyId > 0 && keyId <= 255);
  const key = Buffer.from(system.serverEnv.GLD_AES128_KEY_HEX, "hex");
  const nonce = crypto.randomBytes(12);
  const seq = crypto.randomBytes(1)[0];
  const flags = 0x10; // NodeCache external-power flag, clear alarm.
  const plaintext = Buffer.from([0, 97, 0x0E, 0x74]); // clearGas97%,3700mV.
  const aad = Buffer.from([IDS.node >> 8, IDS.node & 0xFF, seq, flags, keyId]);
  const cipher = crypto.createCipheriv("aes-128-gcm", key, nonce, { authTagLength: 12 });
  cipher.setAAD(aad);
  const ciphertext = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  const encrypted = Buffer.concat([Buffer.from([keyId]), nonce, ciphertext, cipher.getAuthTag()]);
  const record = Buffer.concat([Buffer.from([IDS.node >> 8, IDS.node & 0xFF, seq, flags, encrypted.length]), encrypted]);
  const frameHex = frame(record, seq).toString("hex").toUpperCase();
  // Plaintext values below are synthetic test expectations, not captured GLD data.
  return {
    synthetic: true,
    target: "isolated_handover_stack_only",
    messages: [
      { topic: "gld/gateway/topology", payload: {
        kind: "ch-topology", report: "ch-hello", gatewayId: IDS.gateway,
        clusterId: IDS.cluster, parentId: IDS.gateway, meshDepth: 1,
        rssi: -55, snr: 9, batteryMv: 3800
      } },
      { topic: "gld/gateway/uplink", payload: { gatewayId: IDS.gateway, frameHex } }
    ],
    expected: {
      nodeId: IDS.node, nodeIdHex: hexId(IDS.node), chIdHex: hexId(IDS.cluster),
      gatewayIdHex: hexId(IDS.gateway), gasClass: 0, gasName: "clearGas", confidence: 97,
      batteryMv: 3700, alarm: false, externalPower: true, seq, decryptOk: true,
      decodedTopic: "gld/server/decoded", ingressClass: "production"
    },
    verifyHttp: {
      method: "GET", path: "/pertamina-gld/topology",
      nodeSelector: { type: "gld", nodeIdHex: hexId(IDS.node), chIdHex: hexId(IDS.cluster) },
      requiredNodeFields: ["decryptOk", "gasClass", "confidence", "batteryMv", "seq", "externalPower"],
      requiredGateway: hexId(IDS.gateway)
    },
    protocol: { cipher: "AES-128-GCM", nonceBytes: 12, tagBytes: 12, plaintextBytes: 4,
      encryptedPayloadBytes: 29, recordBytes: 34, frameBytes: 44 }
  };
}

function runner(system) {
  const decoderPath = path.join(ROOT, "server/nodered/functions/pertamina-gld-decode.js");
  const source = fs.readFileSync(decoderPath, "utf8");
  const store = {};
  const flow = {
    get: (name, storage) => store[`${storage || "memory"}:${name}`],
    set: (name, value, storage) => { store[`${storage || "memory"}:${name}`] = value; }
  };
  const env = { get: (name) => ["GLD_AES128_KEY_HEX", "GLD_KEY_ID"].includes(name) ? system.serverEnv[name] : undefined };
  const fn = vm.runInNewContext(`(function(msg,flow,global,env,node){\n${source}\n})`, { Buffer, console }, { filename: decoderPath });
  return { run: (message) => fn(message, flow, { get: (name) => name === "crypto" ? crypto : undefined }, env,
    { warn: () => {}, error: () => {} }), flow, env };
}

function decoded(result) {
  return result && Array.isArray(result[2]) && result[2][0] && result[2][0].payload;
}

function selfTest() {
  // Test-vector key only. This mode never reads the handover system.json.
  const system = { schemaVersion: 1, serverEnv: { GLD_AES128_KEY_HEX: "000102030405060708090A0B0C0D0E0F", GLD_KEY_ID: "1" } };
  const packet = build(system);
  const canonical = runner(system);
  canonical.run(packet.messages[0]);
  const event = decoded(canonical.run(packet.messages[1]));
  assert(event && event.decryptOk && event.ok && event.ingressClass === "production");
  for (const key of ["nodeId", "nodeIdHex", "gasClass", "gasName", "confidence", "batteryMv", "seq", "alarm", "externalPower"]) {
    assert.deepEqual(event[key], packet.expected[key]);
  }
  assert.equal(event.outer.gatewayIdHex, packet.expected.gatewayIdHex);
  const generatedFlow = JSON.parse(fs.readFileSync(path.join(ROOT, "server/nodered/pertamina-gld-server.flow.json"), "utf8"));
  const topologyNode = generatedFlow.find((node) => node.id === "pgl_topology_json");
  const topologyFunction = vm.runInNewContext(`(function(msg,flow,env){\n${topologyNode.func}\n})`, { console });
  const topology = topologyFunction({}, canonical.flow, canonical.env).payload;
  const node = topology.nodes.find((item) => item.type === "gld" && item.nodeIdHex === packet.expected.nodeIdHex);
  assert(node && node.chIdHex === packet.expected.chIdHex && node.decryptOk);
  for (const key of packet.verifyHttp.requiredNodeFields) assert.deepEqual(node[key], packet.expected[key]);
  assert(topology.gatewayIds.includes(packet.expected.gatewayIdHex));
  const replay = canonical.run(packet.messages[1]);
  assert(!decoded(replay) && replay[3] && replay[3].length, "Exact replay must not be decoded twice");
  const altered = JSON.parse(JSON.stringify(packet.messages[1]));
  const bytes = Buffer.from(altered.payload.frameHex, "hex");
  bytes[26] ^= 1; // Alter ciphertext and repair CRC so AES authentication must reject.
  const checksum = crc16(bytes.subarray(0, -2)); bytes.writeUInt16BE(checksum, bytes.length - 2);
  altered.payload.frameHex = bytes.toString("hex");
  assert(!decoded(runner(system).run(altered)), "Tampered ciphertext must not authenticate");
  const badSystem = { schemaVersion: 1, serverEnv: { GLD_AES128_KEY_HEX: "F".repeat(32), GLD_KEY_ID: "1" } };
  assert(!decoded(runner(badSystem).run(packet.messages[1])), "Wrong AES key must not authenticate");
  const encoded = JSON.stringify(packet);
  assert(!encoded.toUpperCase().includes(system.serverEnv.GLD_AES128_KEY_HEX.toUpperCase()));
  return { ok: true, syntheticOnly: true, canonicalDecoder: true, canonicalTopology: true,
    replayRejected: true, tamperRejected: true, wrongKeyRejected: true, servicesContacted: false };
}

function main(args) {
  try {
    if (args.length === 1 && args[0] === "--self-test") {
      process.stdout.write(JSON.stringify(selfTest()) + "\n"); return 0;
    }
    requireValid(args.length === 1);
    const input = path.resolve(args[0]);
    requireValid(fs.statSync(input).isFile() && fs.statSync(input).size < 2 * 1024 * 1024);
    const system = JSON.parse(fs.readFileSync(input, "utf8").replace(/^\uFEFF/, ""));
    process.stdout.write(JSON.stringify(build(system)) + "\n"); return 0;
  } catch (_) {
    // Never stringify a parser error, source path, private field or key value.
    process.stdout.write(JSON.stringify({ ok: false, code: "synthetic_crypto_smoke_failed", servicesContacted: false }) + "\n"); return 1;
  }
}

module.exports = { build, selfTest, crc16 };
if (require.main === module) process.exitCode = main(process.argv.slice(2));
