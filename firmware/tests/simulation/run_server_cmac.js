#!/usr/bin/env node
// Computes an AES-CMAC-128 (RFC 4493) tag using the REAL, unmodified
// aesCmac/aesBlock/leftShiftOne/xor16 functions embedded in
// server/nodered/apply-pertamina-gld-flow.js's build_node_command_auth
// (extracted verbatim below, not reimplemented), so the Python orchestrator
// can diff this against the tag produced by the real, compiled
// pgl::protocol::computeAesCmac128 (RFC 4493, mbedtls-backed) in
// host_protocol_sim.cpp for the identical key/message.
//
// Usage: node run_server_cmac.js <keyHex> <messageHex>
// Prints one JSON line: { tagHex: "..." }

"use strict";
const crypto = require("crypto");

// --- verbatim from server/nodered/apply-pertamina-gld-flow.js -------------
function xor16(a, b) {
  const out = Buffer.alloc(16);
  for (let i = 0; i < 16; i++) out[i] = a[i] ^ b[i];
  return out;
}

function leftShiftOne(block) {
  const out = Buffer.alloc(16);
  let carry = 0;
  for (let i = 15; i >= 0; i--) {
    const value = block[i];
    out[i] = ((value << 1) & 0xFF) | carry;
    carry = (value & 0x80) ? 1 : 0;
  }
  return out;
}

function aesBlock(cryptoModule, key, block) {
  const cipher = cryptoModule.createCipheriv("aes-128-ecb", key, null);
  cipher.setAutoPadding(false);
  return Buffer.concat([cipher.update(block), cipher.final()]);
}

function aesCmac(cryptoModule, key, message) {
  const zero = Buffer.alloc(16);
  const rb = 0x87;
  const l = aesBlock(cryptoModule, key, zero);
  const k1 = leftShiftOne(l);
  if (l[0] & 0x80) k1[15] ^= rb;
  const k2 = leftShiftOne(k1);
  if (k1[0] & 0x80) k2[15] ^= rb;

  const complete = message.length > 0 && message.length % 16 === 0;
  const blockCount = complete ? message.length / 16 : Math.floor(message.length / 16) + 1;
  let last = Buffer.alloc(16);
  const lastOffset = (blockCount - 1) * 16;
  if (complete) {
    last = xor16(message.subarray(lastOffset, lastOffset + 16), k1);
  } else {
    message.copy(last, 0, lastOffset);
    last[message.length - lastOffset] = 0x80;
    last = xor16(last, k2);
  }

  let x = Buffer.alloc(16);
  for (let i = 0; i < blockCount - 1; i++) {
    x = aesBlock(cryptoModule, key, xor16(x, message.subarray(i * 16, i * 16 + 16)));
  }
  return aesBlock(cryptoModule, key, xor16(x, last));
}
// --- end verbatim extract ---------------------------------------------------

function main() {
  const keyHex = process.argv[2];
  const messageHex = process.argv[3];
  if (!keyHex || !messageHex) {
    console.error("usage: node run_server_cmac.js <keyHex> <messageHex>");
    process.exit(2);
  }
  const key = Buffer.from(keyHex, "hex");
  const message = Buffer.from(messageHex, "hex");
  const tag = aesCmac(crypto, key, message);
  console.log(JSON.stringify({ ok: true, tagHex: tag.toString("hex").toUpperCase() }));
}

main();
