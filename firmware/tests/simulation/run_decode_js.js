#!/usr/bin/env node
// Executes the REAL, unmodified production server-side decoder
// (server/nodered/functions/pertamina-gld-decode.js) outside of Node-RED, by
// providing a minimal shim for the Node-RED function-node globals it expects
// (msg, flow, global, env). This is not a reimplementation of the decode
// logic - it is the actual file Node-RED loads into the "decode Gateway/GLD
// contract" function node, executed as-is.
//
// Usage: node run_decode_js.js <frameHex> [gasClass] [confidence] [batteryMv]
// Prints one JSON line: the decoded event object (or an error object).

"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const DECODE_FILE = path.join(__dirname, "..", "..", "..", "server", "nodered", "functions", "pertamina-gld-decode.js");

// Must match the AES key configured in host_protocol_sim.cpp's AES_KEY[16]
// and firmware/gld/src/GldSelfTestConfig.h's selftest key (keyId=1).
const ENV = {
  GLD_KEY_ID: "1",
  GLD_AES128_KEY_HEX: "000102030405060708090A0B0C0D0E0F",
  PGL_GATEWAY_ID: "0x006F",
};

function runDecode(payload, topic) {
  const source = fs.readFileSync(DECODE_FILE, "utf8");
  const flowStore = {};
  const msg = { payload, topic, req: undefined, res: undefined };
  const flow = {
    get: (key) => flowStore[key],
    set: (key, value) => {
      flowStore[key] = value;
    },
  };
  const global_ = {
    get: (key) => (key === "crypto" ? require("crypto") : undefined),
  };
  const env = { get: (key) => ENV[key] };
  const node = { warn: () => {}, error: () => {} };

  // Node-RED wraps a function node's body in a function with these names in
  // scope and calls it per message; this reproduces that minimally. The
  // sandbox needs Node's own Buffer/console/etc. explicitly - a fresh vm
  // context does not inherit them.
  const wrapped = `(function(msg, flow, global, env, node) {\n${source}\n})`;
  const sandbox = { Buffer, console, Date, JSON, Math, Number, String, Object, Array, Error, RegExp, parseInt, parseFloat };
  const fn = vm.runInNewContext(wrapped, sandbox, { filename: DECODE_FILE });
  return fn(msg, flow, global_, env, node);
}

function main() {
  const frameHex = process.argv[2];
  if (!frameHex) {
    console.error("usage: node run_decode_js.js <frameHex>");
    process.exit(2);
  }

  try {
    const result = runDecode({ frameHex }, "gld/gateway/uplink");
    // decode.js returns [statusMsg|null, eventMsgs|null, decodedMsgs|null, errMsg|null]
    const [, , decodedMsgs, errMsg] = result || [];
    if (errMsg && errMsg.payload) {
      console.log(JSON.stringify({ ok: false, error: errMsg.payload }));
      return;
    }
    if (Array.isArray(decodedMsgs) && decodedMsgs.length > 0) {
      console.log(JSON.stringify({ ok: true, event: decodedMsgs[0].payload }));
      return;
    }
    console.log(JSON.stringify({ ok: false, error: "decode.js returned no decoded event and no error - unexpected shape", raw: result }));
  } catch (err) {
    console.log(JSON.stringify({ ok: false, error: `exception: ${err.message}` }));
  }
}

main();
