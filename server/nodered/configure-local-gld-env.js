#!/usr/bin/env node
"use strict";

// Provision the existing Node-RED settings file to read only the GLD key and
// key ID from a private, ignored env file. No key value is copied into flows.
const fs = require("fs");
const os = require("os");
const path = require("path");

function option(name, fallback) {
  const index = process.argv.indexOf(name);
  if (index < 0) return fallback;
  const value = process.argv[index + 1];
  if (!value || value.startsWith("--")) throw new Error(`Missing value for ${name}`);
  return value;
}

try {
  const envPath = path.resolve(option("--env-file", path.join(__dirname, ".env")));
  const userDir = path.resolve(option("--user-dir", path.join(os.homedir(), ".node-red")));
  const settingsPath = path.join(userDir, "settings.js");
  const privateEnv = fs.readFileSync(envPath, "utf8");
  const values = {};
  for (const line of privateEnv.split(/\r?\n/)) {
    const match = line.match(/^\s*(GLD_KEY_ID|GLD_AES128_KEY_HEX)\s*=\s*(.*?)\s*$/);
    if (match) values[match[1]] = match[2].replace(/^(['"])(.*)\1$/, "$2");
  }
  if (!/^[0-9A-Fa-f]{32}$/.test(values.GLD_AES128_KEY_HEX || "") || !/^\d+$/.test(values.GLD_KEY_ID || "") || Number(values.GLD_KEY_ID) > 255) {
    throw new Error("Private env must contain a 32-character GLD_AES128_KEY_HEX and numeric GLD_KEY_ID");
  }
  const original = fs.readFileSync(settingsPath, "utf8");
  if (original.includes("PGL_LOCAL_GLD_ENV_BOOTSTRAP")) {
    const normalize = (value) => value.replace(/\\+/g, "/").toLowerCase();
    if (!normalize(original).includes(normalize(envPath))) {
      throw new Error("Existing GLD key bootstrap refers to a different path; review settings.js before changing it");
    }
    console.log("Node-RED local GLD key bootstrap already exists; settings unchanged.");
    process.exit(0);
  }
  const block = `// PGL_LOCAL_GLD_ENV_BOOTSTRAP: read only decoder keys from the private local file.\n(() => {\n    const fs = require('fs');\n    const file = ${JSON.stringify(envPath)};\n    if (!fs.existsSync(file)) return;\n    for (const line of fs.readFileSync(file, 'utf8').split(/\\r?\\n/)) {\n        const match = line.match(/^\\s*(GLD_KEY_ID|GLD_AES128_KEY_HEX)\\s*=\\s*(.*?)\\s*$/);\n        if (match && !process.env[match[1]]) process.env[match[1]] = match[2].replace(/^(['"])(.*)\\1$/, '$2');\n    }\n})();\n\n`;
  const backup = path.join(userDir, `settings.js.pgl-backup-${Date.now()}`);
  fs.copyFileSync(settingsPath, backup, fs.constants.COPYFILE_EXCL);
  const temp = path.join(userDir, `settings.js.pgl-${process.pid}.tmp`);
  try {
    fs.writeFileSync(temp, block + original, { encoding: "utf8", mode: 0o600, flag: "wx" });
    fs.renameSync(temp, settingsPath);
  } finally {
    if (fs.existsSync(temp)) fs.unlinkSync(temp);
  }
  console.log("Node-RED settings updated; restart Node-RED to load the local GLD key.");
} catch (error) {
  console.error(`Local GLD key setup failed: ${error.message}`);
  process.exitCode = 1;
}
