import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { setupAccess } from "../js/gw-setup-flow.mjs";

assert.deepEqual(setupAccess({ serialConnected: false, wifiVerified: false, mqttConnected: false }), {
  wifiUnlocked: false,
  mqttUnlocked: false,
  mqttPanelEnabled: false
});
assert.equal(setupAccess({ serialConnected: true, wifiVerified: false }).wifiUnlocked, true);
assert.equal(setupAccess({ serialConnected: true, wifiVerified: false }).mqttUnlocked, false);
assert.equal(setupAccess({ serialConnected: true, wifiVerified: true }).mqttUnlocked, true);
assert.equal(setupAccess({ serialConnected: false, wifiVerified: true }).mqttUnlocked, false);
assert.equal(setupAccess({ serialConnected: false, wifiVerified: false, mqttConnected: true }).mqttPanelEnabled, true);

const here = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(resolve(here, "../index.html"), "utf8");
const serialAt = html.indexOf('id="serialSetupStep"');
const identityAt = html.indexOf('id="gatewayIdentitySetupStep"');
const wifiAt = html.indexOf('id="wifiSetupStep"');
const mqttAt = html.indexOf('id="mqttSetupStep"');
assert.ok(
  serialAt >= 0 && serialAt < identityAt && identityAt < wifiAt && wifiAt < mqttAt,
  "setup panels must be ordered COM -> Gateway identity -> Wi-Fi -> MQTT"
);
assert.match(html, /id="gatewayIdentitySetupStep" disabled/);
assert.match(html, /id="wifiSetupStep" disabled/);
assert.match(html, /id="mqttSetupStep" disabled/);

console.log("Gateway setup-flow contract: PASS");
