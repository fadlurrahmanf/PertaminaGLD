const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "../js/serial-protocol.js"), "utf8");
const start = source.indexOf("function renderDetectedBoardProfile(");
const end = source.indexOf("\nfunction renderSensorPowerControls(", start);
assert(start >= 0 && end > start);
const element = { textContent: "", className: "", title: "" };
const state = { info: null };
const render = new Function("$", "state", `${source.slice(start, end)}; return renderDetectedBoardProfile;`)(
  () => element, state,
);

render({ boardProfile: "GLD ATEX MotherBoardGLDVer2" }, { sensorPower: { available: true } });
assert.equal(element.textContent, "Board: GLD ATEX · PCF8574");
render({ boardProfile: "GLD2 WROOM-1U-N16R8" }, { sensorPower: { available: true } });
assert.equal(element.textContent, "Board: GLD2 · PCF8574");
render({ boardProfile: "WROOM-1U-N16R8" }, {});
assert.equal(element.textContent, "Board: GLD1");
console.log("ATEX, GLD2 and GLD1 board labels: PASS");
