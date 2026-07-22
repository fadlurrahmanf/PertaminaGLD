import assert from "node:assert/strict";
import test from "node:test";

import { validateMeshLoraConfig } from "../js/gw-lora-config.mjs";

test("accepts the deployed Gateway MESH profile", () => {
  assert.deepEqual(validateMeshLoraConfig({
    freqMHz: "921", bwKHz: "125", sf: "9", cr: "5", syncWord: "52", txPowerDbm: "17"
  }), {
    freqMHz: 921, bwKHz: 125, sf: 9, cr: 5, syncWord: 52, txPowerDbm: 17, reboot: true
  });
});

test("rejects unsupported bandwidth and fractional integer fields", () => {
  assert.throws(() => validateMeshLoraConfig({
    freqMHz: 921, bwKHz: 100, sf: 9, cr: 5, syncWord: 52, txPowerDbm: 17
  }), /Bandwidth/);
  assert.throws(() => validateMeshLoraConfig({
    freqMHz: 921, bwKHz: 125, sf: 9.5, cr: 5, syncWord: 52, txPowerDbm: 17
  }), /SF/);
});

test("rejects every out-of-range field", () => {
  const base = { freqMHz: 921, bwKHz: 125, sf: 9, cr: 5, syncWord: 52, txPowerDbm: 17 };
  for (const invalid of [
    { freqMHz: 899 }, { freqMHz: 931 }, { sf: 4 }, { sf: 13 },
    { cr: 4 }, { cr: 9 }, { syncWord: -1 }, { syncWord: 256 },
    { txPowerDbm: -10 }, { txPowerDbm: 23 }
  ]) {
    assert.throws(() => validateMeshLoraConfig({ ...base, ...invalid }));
  }
});
