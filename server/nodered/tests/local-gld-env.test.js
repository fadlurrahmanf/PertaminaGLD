"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

test("Node-RED loads the private GLD key without embedding it in settings", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "pgl-local-env-"));
  try {
    const settings = path.join(dir, "settings.js");
    const envFile = path.join(dir, "private.env");
    const key = "0123456789ABCDEF0123456789ABCDEF";
    fs.writeFileSync(settings, "module.exports = { retained: true };\n");
    fs.writeFileSync(envFile, `GLD_KEY_ID=1\nGLD_AES128_KEY_HEX=${key}\n`);
    const setup = path.join(__dirname, "..", "configure-local-gld-env.js");
    const args = [setup, "--user-dir", dir, "--env-file", envFile];
    execFileSync(process.execPath, args);
    const first = fs.readFileSync(settings, "utf8");
    assert(!first.includes(key));
    execFileSync(process.execPath, args);
    assert.equal(fs.readFileSync(settings, "utf8"), first);
    const childEnv = { ...process.env };
    delete childEnv.GLD_KEY_ID;
    delete childEnv.GLD_AES128_KEY_HEX;
    const script = "const s=require(process.argv[1]); process.stdout.write(String(s.retained && process.env.GLD_KEY_ID==='1' && process.env.GLD_AES128_KEY_HEX===process.argv[2]));";
    assert.equal(execFileSync(process.execPath, ["-e", script, settings, key], { env: childEnv, encoding: "utf8" }), "true");
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
