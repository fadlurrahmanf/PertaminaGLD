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

function buildRecord(nodeId, seq, nonceSeed) {
  const flags = 0;
  const keyId = 1;
  const nonce = Buffer.alloc(12);
  nonce.writeBigUInt64BE(BigInt(nonceSeed), 4);
  const plaintext = Buffer.from([0, 99, 0x0D, 0x5E]);
  const aad = Buffer.from([(nodeId >> 8) & 0xFF, nodeId & 0xFF, seq, flags, keyId]);
  const cipher = crypto.createCipheriv("aes-128-gcm", key, nonce, { authTagLength: 12 });
  cipher.setAAD(aad);
  const ciphertext = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  const payload = Buffer.concat([Buffer.from([keyId]), nonce, ciphertext, cipher.getAuthTag()]);
  return Buffer.concat([
    Buffer.from([(nodeId >> 8) & 0xFF, nodeId & 0xFF, seq, flags, payload.length]),
    payload
  ]);
}

function buildResponseFrame({ requestId, transportSrc, gatewayId, record }) {
  const responsePayload = Buffer.concat([
    Buffer.from([(requestId >> 8) & 0xFF, requestId & 0xFF, 0, 0x10, 0x00, 1]),
    record
  ]);
  const body = Buffer.concat([
    Buffer.from([
      0xAA,
      0x31,
      (transportSrc >> 8) & 0xFF,
      transportSrc & 0xFF,
      (gatewayId >> 8) & 0xFF,
      gatewayId & 0xFF,
      7,
      responsePayload.length
    ]),
    responsePayload
  ]);
  const crc = crc16CcittFalse(body);
  return Buffer.concat([body, Buffer.from([(crc >> 8) & 0xFF, crc & 0xFF])]).toString("hex").toUpperCase();
}

function runDecoder(recordHex, flowStore, replayStatePath, wrapperGatewayId) {
  const flow = {
    get: (name) => flowStore[name],
    set: (name, value) => { flowStore[name] = value; }
  };
  const globalContext = { get: (name) => ({ crypto, fs, path }[name]) };
  const envValues = {
    GLD_KEY_ID: "1",
    GLD_AES128_KEY_HEX: key.toString("hex"),
    PGL_REPLAY_STATE_PATH: replayStatePath,
    PGL_GLD_REQUEST_CORRELATION_TTL_MS: "120000"
  };
  const wrapped = `(function(msg, flow, global, env, node) {\n${decoderSource}\n})`;
  const fn = vm.runInNewContext(wrapped, {
    Buffer, console, Date, JSON, Math, Number, String, Object, Array,
    Error, RegExp, parseInt, parseFloat
  }, { filename: decoderPath });
  return fn(
    { payload: { recordHex, gatewayId: wrapperGatewayId }, topic: "gld/gateway/uplink" },
    flow,
    globalContext,
    { get: (name) => envValues[name] },
    { warn: () => {}, error: () => {} }
  );
}

const requestId = 12815;
const requestedAt = new Date().toISOString();
const flowStore = {
  pglGldRequestIndex: {
    [requestId]: {
      requestId,
      targetChIdHex: "0x0068",
      gatewayIdHex: "0x0001",
      hopList: ["0x0069", "0x0068"],
      requestedAt
    }
  },
  pglGldDiscovery: {
    "0x0068": { status: "sent", requestId, gatewayIdHex: "0x0001", hopList: ["0x0069", "0x0068"], requestedAt, devices: {} },
    "0x0069": { status: "idle", devices: {} }
  }
};
const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "pgl-request-correlation-"));

try {
  const frame = buildResponseFrame({
    requestId,
    transportSrc: 0x0069,
    gatewayId: 0x0001,
    record: buildRecord(0xF020, 72, 1)
  });
  const result = runDecoder(frame, flowStore, path.join(tempDir, "replay.json"));
  const decoded = result[2][0].payload;

  assert.equal(decoded.outer.srcIdHex, "0x0069", "transport ingress must remain observable");
  assert.equal(decoded.outer.responseTargetChIdHex, "0x0068", "request target is the logical response owner");
  assert.equal(decoded.outer.responseCorrelation, "request-index");
  assert(flowStore.pglGldDiscovery["0x0068"].devices["0xF020"]);
  assert.equal(flowStore.pglGldDiscovery["0x0068"].status, "received");
  assert.equal(flowStore.pglGldDiscovery["0x0069"].devices["0xF020"], undefined);

  const directStore = {
    pglGldRequestIndex: {
      12816: { requestId: 12816, targetChIdHex: "0x0068", gatewayIdHex: "0x0001", hopList: ["0x0068"], requestedAt }
    },
    pglGldDiscovery: {
      "0x0068": { status: "sent", requestId: 12816, gatewayIdHex: "0x0001", hopList: ["0x0068"], requestedAt, devices: {} }
    }
  };
  const direct = runDecoder(buildResponseFrame({
    requestId: 12816,
    transportSrc: 0x0068,
    gatewayId: 0x0001,
    record: buildRecord(0xF020, 73, 2)
  }), directStore, path.join(tempDir, "direct-replay.json"));
  assert.equal(direct[2][0].payload.outer.responseTargetChIdHex, "0x0068");

  const unknownStore = { pglGldRequestIndex: {}, pglGldDiscovery: { "0x0069": { devices: {} } } };
  const unknown = runDecoder(buildResponseFrame({
    requestId: 32000,
    transportSrc: 0x0069,
    gatewayId: 0x0001,
    record: buildRecord(0xF020, 74, 3)
  }), unknownStore, path.join(tempDir, "unknown-replay.json"));
  assert.equal(unknown[2][0].payload.outer.responseTargetChIdHex, undefined);
  assert.equal(unknown[2][0].payload.outer.responseCorrelation, "unknown-request-id");
  assert.equal(unknownStore.pglGldDiscovery["0x0069"].devices["0xF020"], undefined);

  const lateAt = new Date(Date.now() - 30000).toISOString();
  const lateStore = {
    pglGldRequestIndex: {
      12817: { requestId: 12817, targetChIdHex: "0x0068", gatewayIdHex: "0x0001", hopList: ["0x0069", "0x0068"], requestedAt: lateAt }
    },
    pglGldDiscovery: {
      "0x0068": { status: "sent", requestId: 12817, gatewayIdHex: "0x0001", hopList: ["0x0069", "0x0068"], requestedAt: lateAt, devices: {} }
    }
  };
  const late = runDecoder(buildResponseFrame({
    requestId: 12817,
    transportSrc: 0x0069,
    gatewayId: 0x0001,
    record: buildRecord(0xF020, 75, 4)
  }), lateStore, path.join(tempDir, "late-replay.json"));
  assert.equal(late[2][0].payload.outer.responseTargetChIdHex, undefined);
  assert.equal(late[2][0].payload.outer.responseCorrelation, "late-response");
  assert.equal(lateStore.pglGldDiscovery["0x0068"].devices["0xF020"], undefined);

  const mismatchStore = {
    pglGldRequestIndex: {
      12818: { requestId: 12818, targetChIdHex: "0x0068", gatewayIdHex: "0x0001", hopList: ["0x0067", "0x0068"], requestedAt }
    },
    pglGldDiscovery: {
      "0x0068": { status: "sent", requestId: 12818, gatewayIdHex: "0x0001", hopList: ["0x0067", "0x0068"], requestedAt, devices: {} }
    }
  };
  const mismatch = runDecoder(buildResponseFrame({
    requestId: 12818,
    transportSrc: 0x0069,
    gatewayId: 0x0001,
    record: buildRecord(0xF020, 76, 5)
  }), mismatchStore, path.join(tempDir, "mismatch-replay.json"));
  assert.equal(mismatch[2][0].payload.outer.responseTargetChIdHex, undefined);
  assert.equal(mismatch[2][0].payload.outer.responseCorrelation, "ingress-route-mismatch");
  assert.equal(mismatchStore.pglGldDiscovery["0x0068"].devices["0xF020"], undefined);

  for (const gatewayId of [0x0002, 0x000F]) {
    const boundaryRequestId = 13000 + gatewayId;
    const gatewayIdHex = `0x${gatewayId.toString(16).toUpperCase().padStart(4, "0")}`;
    const store = {
      pglGldRequestIndex: {
        [boundaryRequestId]: { requestId: boundaryRequestId, targetChIdHex: "0x0068", gatewayIdHex, hopList: ["0x0068"], requestedAt }
      },
      pglGldDiscovery: {
        "0x0068": { status: "sent", requestId: boundaryRequestId, gatewayIdHex, hopList: ["0x0068"], requestedAt, devices: {} }
      }
    };
    const accepted = runDecoder(buildResponseFrame({
      requestId: boundaryRequestId,
      transportSrc: 0x0068,
      gatewayId,
      record: buildRecord(0x1001, gatewayId, 100 + gatewayId)
    }), store, path.join(tempDir, `gateway-${gatewayId}.json`), gatewayId);
    assert.equal(accepted[2][0].payload.outer.gatewayIdHex, gatewayIdHex);
    assert(store.pglGldDiscovery["0x0068"].devices["0x1001"]);
  }

  for (const invalidDestination of [0x0000, 0x0010, 0x1001, 0xFEFF, 0xFF00, 0xFFFF]) {
    const rejected = runDecoder(buildResponseFrame({
      requestId: 14000,
      transportSrc: 0x0068,
      gatewayId: invalidDestination,
      record: buildRecord(0x1001, 90, 200 + invalidDestination)
    }), { pglGldRequestIndex: {}, pglGldDiscovery: {} }, path.join(tempDir, `invalid-${invalidDestination}.json`));
    assert.match(rejected[3].payload.detail, /is not a Gateway ID/);
  }

  const wrapperMismatch = runDecoder(buildResponseFrame({
    requestId: 15000,
    transportSrc: 0x0068,
    gatewayId: 0x0002,
    record: buildRecord(0x1001, 91, 300)
  }), { pglGldRequestIndex: {}, pglGldDiscovery: {} }, path.join(tempDir, "wrapper-mismatch.json"), 0x0003);
  assert.match(wrapperMismatch[3].payload.detail, /wrapper\/frame gateway mismatch/);

  const invalidGld = runDecoder(buildResponseFrame({
    requestId: 15001,
    transportSrc: 0x0068,
    gatewayId: 0x0002,
    record: buildRecord(0x1000, 92, 301)
  }), {
    pglGldRequestIndex: { 15001: { requestId: 15001, targetChIdHex: "0x0068", gatewayIdHex: "0x0002", hopList: ["0x0068"], requestedAt } },
    pglGldDiscovery: { "0x0068": { requestId: 15001, gatewayIdHex: "0x0002", hopList: ["0x0068"], requestedAt, devices: {} } }
  }, path.join(tempDir, "invalid-gld.json"), 0x0002);
  assert.match(invalidGld[3][0].payload.reason, /expected GLD/);

  console.log("PASS routed GLD response request correlation");
} finally {
  fs.rmSync(tempDir, { recursive: true, force: true });
}
