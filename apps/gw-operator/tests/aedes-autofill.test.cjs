const assert = require("node:assert/strict");
const { test } = require("node:test");

test("fills a tested local profile without clearing manual settings when absent", async () => {
  const { applyLocalBrokerProfile } = await import("../js/gw-aedes-autofill.mjs");
  const fields = Object.fromEntries(["mqttPort", "mqttUsername", "mqttPassword", "mqttTopicRoot"].map(k => [k, { value: "manual" }]));
  assert.equal(applyLocalBrokerProfile(fields, { available: false }), false);
  assert.equal(fields.mqttPassword.value, "manual");
  assert.equal(applyLocalBrokerProfile(fields, { available: true, port: 1885, username: "sample", password: "secret", topicRoot: "gld/gateway" }), true);
  assert.equal(fields.mqttPort.value, 1885);
  assert.equal(fields.mqttUsername.value, "sample");
  assert.equal(fields.mqttPassword.value, "secret");
  assert.equal(fields.mqttTopicRoot.value, "gld/gateway");
});
