"use strict";

const assert = require("assert");
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");
const vm = require("vm");

const decoderPath = path.join(__dirname, "..", "functions", "pertamina-gld-decode.js");
const decoderSource = fs.readFileSync(decoderPath, "utf8");
const key = Buffer.from("000102030405060708090A0B0C0D0E0F", "hex");
const nodeId = 0xF020;

function buildRecord(seq, nonceSeed) {
  const flags = 0;
  const keyId = 1;
  const nonce = Buffer.alloc(12);
  nonce.writeUInt32BE((0xA5A50000 | (nonceSeed & 0xFFFF)) >>> 0, 0);
  nonce.writeBigUInt64BE(BigInt(nonceSeed), 4);
  const plaintext = Buffer.from([0, 99, 0x0D, 0xAC]);
  const aad = Buffer.from([(nodeId >> 8) & 0xFF, nodeId & 0xFF, seq & 0xFF, flags, keyId]);
  const cipher = crypto.createCipheriv("aes-128-gcm", key, nonce, { authTagLength: 12 });
  cipher.setAAD(aad);
  const ciphertext = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  const payload = Buffer.concat([Buffer.from([keyId]), nonce, ciphertext, cipher.getAuthTag()]);
  return Buffer.concat([
    Buffer.from([(nodeId >> 8) & 0xFF, nodeId & 0xFF, seq & 0xFF, flags, payload.length]),
    payload
  ]).toString("hex").toUpperCase();
}

function createRunner(replayStatePath, initialFlowStore = {}) {
  const flowStore = initialFlowStore;
  const flow = {
    get: (name) => flowStore[name],
    set: (name, value) => { flowStore[name] = value; }
  };
  const globalContext = {
    get: (name) => ({ crypto, fs, path }[name])
  };
  const envValues = {
    GLD_KEY_ID: "1",
    GLD_AES128_KEY_HEX: key.toString("hex"),
    PGL_REPLAY_STATE_PATH: replayStatePath
  };
  const env = { get: (name) => envValues[name] };
  const node = { warn: () => {}, error: () => {} };
  const wrapped = `(function(msg, flow, global, env, node) {\n${decoderSource}\n})`;
  const sandbox = {
    Buffer, console, Date, JSON, Math, Number, String, Object, Array,
    Error, RegExp, parseInt, parseFloat
  };
  const fn = vm.runInNewContext(wrapped, sandbox, { filename: decoderPath });
  return {
    run(recordHex) {
      return fn({ payload: { recordHex }, topic: "gld/gateway/uplink" }, flow, globalContext, env, node);
    },
    flowStore
  };
}

function decoded(result) {
  return result && Array.isArray(result[2]) && result[2][0] && result[2][0].payload;
}

function replayError(result) {
  return result && Array.isArray(result[3]) && result[3][0] && result[3][0].payload;
}

const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "pgl-replay-policy-"));
const statePath = path.join(tempDir, "state.json");

try {
  const runner = createRunner(statePath);
  const seq226 = buildRecord(226, 1);
  const seq163 = buildRecord(163, 2);
  const seq163NewNonce = buildRecord(163, 3);
  const seq255 = buildRecord(255, 4);
  const seq0 = buildRecord(0, 5);

  assert.equal(decoded(runner.run(seq226)).replayStatus, "first-record");
  assert.equal(decoded(runner.run(seq163)).replayStatus, "new-record-lower-sequence-or-restart");
  assert.equal(decoded(runner.run(seq163NewNonce)).replayStatus, "new-record-same-sequence");
  assert.equal(decoded(runner.run(seq255)).replayStatus, "new-record-forward");
  assert.equal(decoded(runner.run(seq0)).replayStatus, "new-record-wrap");

  const exactReplay = replayError(runner.run(seq163));
  assert.equal(exactReplay.kind, "gld-replay-rejected");
  assert.equal(exactReplay.reason, "exact-encrypted-record-replay");

  const restartedRunner = createRunner(statePath);
  assert.equal(
    replayError(restartedRunner.run(seq226)).reason,
    "exact-encrypted-record-replay",
    "durable fingerprint must survive a Node-RED restart"
  );

  const legacyPath = path.join(tempDir, "legacy.json");
  fs.writeFileSync(legacyPath, JSON.stringify({
    "production:61472": { lastSeq: 226, bitmap: 1, updatedAt: Date.now() }
  }));
  const migratedRunner = createRunner(legacyPath);
  assert.equal(decoded(migratedRunner.run(buildRecord(163, 6))).replayStatus, "first-record");

  console.log("PASS Node-RED authenticated replay policy");
} finally {
  fs.rmSync(tempDir, { recursive: true, force: true });
}
