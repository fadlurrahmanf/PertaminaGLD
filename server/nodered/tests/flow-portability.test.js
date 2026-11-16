"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

test("flow check accepts a CRLF checkout but rejects actual node changes", () => {
  const source = path.join(__dirname, "..");
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "pgl-flow-crlf-"));
  try {
    const funcs = path.join(dir, "functions");
    fs.mkdirSync(funcs);
    fs.copyFileSync(path.join(source, "apply-pertamina-gld-flow.js"), path.join(dir, "apply-pertamina-gld-flow.js"));
    for (const name of ["pertamina-gld-decode.js", "pertamina-gld-build-command.js"]) {
      const text = fs.readFileSync(path.join(source, "functions", name), "utf8").replace(/\r\n/g, "\n");
      fs.writeFileSync(path.join(funcs, name), text.replace(/\n/g, "\r\n"));
    }
    const flowFile = path.join(dir, "pertamina-gld-server.flow.json");
    const flowText = fs.readFileSync(path.join(source, "pertamina-gld-server.flow.json"), "utf8").replace(/\r\n/g, "\n");
    fs.writeFileSync(flowFile, flowText.replace(/\n/g, "\r\n"));
    const check = () => spawnSync(process.execPath, [path.join(dir, "apply-pertamina-gld-flow.js"), "--check"], { encoding: "utf8" });
    assert.equal(check().status, 0, "CRLF must not create false drift");
    const changed = JSON.parse(flowText);
    changed[0].label += " changed";
    fs.writeFileSync(flowFile, JSON.stringify(changed, null, 2));
    assert.notEqual(check().status, 0, "a real flow change must still be detected");
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
