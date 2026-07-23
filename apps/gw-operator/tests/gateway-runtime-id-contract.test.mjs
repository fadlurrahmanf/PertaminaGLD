import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const read = (path) => readFileSync(resolve(here, path), "utf8");
const bridge = read("../js/gw-bridge.js");
const main = read("../js/gw-main.js");
const html = read("../index.html");

assert.match(bridge, /line: "GET_GATEWAY_ADDRESS"/);
assert.match(bridge, /waitForAck\("SET_GATEWAY_ADDRESS_JSON"/);
assert.match(bridge, /line: `SET_GATEWAY_ADDRESS_JSON /);
assert.match(bridge, /GW_GATEWAY_ADDRESS_JSON /);
assert.match(main, /reconnectSerialAfterGatewayReboot\(\)/);
assert.match(main, /readback mismatch:/);
assert.match(main, /gatewayId: `0x\$\{state\.gatewayId\}`/);
for (const id of ["gatewayCurrentId", "gatewayIdInput", "gatewayIdLoadBtn", "gatewayIdApplyBtn", "gatewayIdStatus"]) {
  assert.match(html, new RegExp(`id="${id}"`));
}

console.log("gateway-runtime-id-contract.test.mjs: PASS");
