import assert from "node:assert/strict";
import { gatewayIdFromRuntime, normalizeGatewayId, validateGatewayId } from "../js/gw-gateway-id.mjs";

assert.equal(normalizeGatewayId(" 0x000a "), "000A");
assert.equal(validateGatewayId("0001"), "0001");
assert.equal(validateGatewayId("0x000F"), "000F");
assert.equal(gatewayIdFromRuntime(2), "0002");
for (const invalid of ["", "1", "0000", "0010", "GGGG", "0001junk", null, true]) {
  assert.throws(() => validateGatewayId(invalid));
}

console.log("gateway-id.test.mjs: PASS");
