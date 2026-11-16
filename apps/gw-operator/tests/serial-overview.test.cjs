const assert = require("node:assert/strict");
const { test } = require("node:test");

test("serial status and mesh configuration populate only reported values", async () => {
  const { mergeSerialOverview } = await import("../js/gw-serial-overview.mjs");
  const mesh = mergeSerialOverview(null, 'GW_MESH_LORA_JSON {"freqMHz":921,"bwKHz":125,"sf":9,"cr":5,"syncWord":52,"txPowerDbm":17}');
  const result = mergeSerialOverview(mesh, 'GW_STATUS_JSON {"gatewayId":"0x0001","firmwareVersion":"0.2.0","meshReady":true,"wifi":true,"mqtt":false}');
  assert.equal(result.meshFreqMhz, 921);
  assert.equal(result.gatewayId, "0x0001");
  assert.equal(result.mqtt, false);
  assert.equal(result.mqttQueueDepth, undefined);
  assert.equal(mergeSerialOverview(result, "GW_STATUS_JSON broken"), null);
  const other = mergeSerialOverview(result, 'GW_STATUS_JSON {"gatewayId":"0x0002","mqtt":true}');
  assert.equal(other.meshFreqMhz, undefined);
  assert.equal(other.gatewayId, "0x0002");
});
