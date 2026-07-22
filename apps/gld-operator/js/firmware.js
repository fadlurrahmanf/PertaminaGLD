// Firmware tab: manifest load/validate, PlatformIO upload with COM-lock
// preflight, and device ID injection.

import { $, elements, state } from "./state.js";
import { appendLog, getField, switchTab, showBanner, showConfirm } from "./ui.js";
import { bridgeFetch } from "./bridge-client.js";
import { applyAndAlert, sendCommand } from "./serial-protocol.js";
import { requireUnlock } from "./security.js";

export async function loadManifestFile(fileList) {
  const files = Array.from(fileList || []);
  if (!files.length) return;
  const manifestFile = files.find((file) => file.name === "manifest.json");
  if (!manifestFile) {
    state.manifest = null;
    state.manifestPackageFiles = new Map();
    $("manifestPreview").textContent = "Invalid package: manifest.json is missing.";
    return;
  }
  const text = await manifestFile.text();
  try {
    const manifest = JSON.parse(text);
    const binaries = new Map();
    for (const file of files) {
      if (file === manifestFile || file.name === "manifest.sha256") continue;
      if (binaries.has(file.name)) throw new Error(`duplicate package filename ${file.name}`);
      binaries.set(file.name, file);
    }
    state.manifest = manifest;
    state.manifestPackageFiles = binaries;
    $("packageDeviceId").value = manifest.deviceId || "";
    if (manifest.environment) $("firmwareEnv").value = manifest.environment;
    $("manifestPreview").textContent = JSON.stringify(manifest, null, 2);
  } catch (error) {
    state.manifest = null;
    state.manifestPackageFiles = new Map();
    $("manifestPreview").textContent = `Invalid manifest: ${error.message}`;
  }
}

function validateManifestForUpload(manifest, env, targetDeviceId) {
  if (!manifest) return "Select a complete schema-v2 firmware package directory first";
  if (manifest.schemaVersion !== 2 || manifest.packageType !== "pertamina-gld-prebuilt-firmware") return "firmware package must use the trusted schema-v2 format";
  const manifestEnv = manifest.environment;
  if (manifestEnv !== env) return `manifest environment ${manifestEnv} does not match selected env ${env}`;
  const packageDeviceId = String(manifest.deviceId || "").toUpperCase();
  if (packageDeviceId !== targetDeviceId) {
    return `manifest deviceId ${packageDeviceId} does not match target ID ${targetDeviceId}`;
  }
  if (String(manifest.chip || "").toLowerCase() !== "esp32s3") return `manifest chip ${manifest.chip} is not ESP32-S3`;
  if (!Array.isArray(manifest.flashFiles) || !manifest.flashFiles.length) return "manifest flashFiles is missing";
  for (const item of manifest.flashFiles) {
    if (!item || typeof item.path !== "string" || !state.manifestPackageFiles.has(item.path)) {
      return `package binary ${item?.path || "(unknown)"} is missing`;
    }
  }
  return "";
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

async function readPackageFiles(manifest) {
  const encoded = {};
  for (const item of manifest.flashFiles) {
    const file = state.manifestPackageFiles.get(item.path);
    if (!file) throw new Error(`package binary ${item.path} is missing`);
    encoded[item.path] = arrayBufferToBase64(await file.arrayBuffer());
  }
  return encoded;
}

export async function checkPortLock() {
  const port = elements.portSelect.value || getField("manualPortInput");
  if (!port) {
    elements.firmwarePortStatus.textContent = "Select a COM port first.";
    return;
  }
  try {
    const result = await bridgeFetch(`/api/serial/port-status?port=${encodeURIComponent(port)}`);
    elements.firmwarePortStatus.textContent = result.free
      ? `${port}: free - ${result.message}`
      : `${port}: BUSY - ${result.message}`;
    return result;
  } catch (error) {
    elements.firmwarePortStatus.textContent = `Port check failed: ${error.message}`;
    return { free: false, message: error.message };
  }
}

export async function uploadFirmware() {
  if (!(await requireUnlock())) return;
  if (!state.bridgeAvailable) {
    appendLog("UPLOAD_SKIPPED local bridge is required for firmware upload", "in");
    showBanner("Firmware upload requires the local bridge to be running.", "warn");
    return;
  }
  const port = elements.portSelect.value;
  const env = getField("firmwareEnv") || "gld";
  const targetDeviceId = getField("targetDeviceId").toUpperCase();
  if (!port) {
    appendLog("UPLOAD_SKIPPED select a COM port first", "in");
    return;
  }
  const manifestWarning = validateManifestForUpload(state.manifest, env, targetDeviceId);
  if (manifestWarning) {
    appendLog(`UPLOAD_SKIPPED ${manifestWarning}`, "in");
    switchTab("expert");
    return;
  }
  const lock = await checkPortLock();
  if (lock && !lock.free) {
    const proceed = await showConfirm(
      `${port} looks busy (${lock.message}). Upload will disconnect this app's serial session and retry once, `
      + "but if PlatformIO still reports the chip not responding, close other serial monitors and replug the GLD USB. Continue anyway?",
      "warn", "COM Port Busy"
    );
    if (!proceed) return;
  }
  if (!(await showConfirm(`Upload PlatformIO env ${env} to ${port}?`, "warn", "Confirm Firmware Upload"))) return;
  try {
    const packageFiles = await readPackageFiles(state.manifest);
    await bridgeFetch("/api/firmware/upload", {
      method: "POST",
      body: JSON.stringify({ env, port, targetDeviceId, manifest: state.manifest, packageFiles, slot: state.activeSlot })
    });
    switchTab("log");
  } catch (error) {
    appendLog(`UPLOAD_ERROR ${error.message}`, "in");
    showBanner(`Firmware upload failed: ${error.message}`, "error");
  }
}

export async function injectDeviceId() {
  if (!(await requireUnlock())) return;
  const deviceId = getField("targetDeviceId").toUpperCase();
  if (!/^[0-9A-F]{4}$/.test(deviceId) || deviceId === "0000") {
    appendLog("ID_REJECTED target ID must be 4 non-zero hex chars, for example F001", "in");
    return;
  }
  if (!(await showConfirm(`Inject GLD ID ${deviceId} and reboot?`, "warn", "Inject GLD ID"))) return;
  await applyAndAlert(`SET_DEVICE_ID_JSON ${JSON.stringify({ deviceId, reboot: true })}`, "SET_DEVICE_ID", "Inject GLD ID");
}

// Node addresses reserved outside the GLD ID space; must stay in sync with
// firmware/config/ChConfig.h (PGL_CH_ROOT_GATEWAY_ID) and GldUnifiedMain.cpp
// (GLD_RESERVED_GATEWAY_ID).
const RESERVED_GATEWAY_ID = "006F";

export function validateChAddress(chId, targetDeviceId) {
  if (!/^[0-9A-F]{4}$/.test(chId)) return "CH address must be 4 hex chars, for example 0064";
  if (chId === "0000" || chId === "FFFF") return "CH address cannot be 0000 or FFFF";
  if (chId === RESERVED_GATEWAY_ID) return `CH address cannot be the Gateway ID (${RESERVED_GATEWAY_ID})`;
  if (targetDeviceId && chId === targetDeviceId) return "CH address cannot equal the GLD's own ID";
  return "";
}

export async function injectChAddress() {
  if (!(await requireUnlock())) return;
  const chId = getField("targetChAddress").toUpperCase();
  const targetDeviceId = getField("targetDeviceId").toUpperCase();
  const error = validateChAddress(chId, targetDeviceId);
  if (error) {
    appendLog(`CH_ADDRESS_REJECTED ${error}`, "in");
    return;
  }
  if (!(await showConfirm(`Apply CH address ${chId} and reboot?`, "warn", "Apply CH Address"))) return;
  await applyAndAlert(`SET_CH_ADDRESS_JSON ${JSON.stringify({ chId, reboot: true })}`, "SET_CH_ADDRESS", "Apply CH Address");
}

function parseSyncWord(raw) {
  const text = String(raw || "").trim();
  if (!text) return NaN;
  const base = /^0x/i.test(text) || /[a-f]/i.test(text) ? 16 : 10;
  return Number.parseInt(text.replace(/^0x/i, ""), base);
}

function validateLoraPayload(payload) {
  if (!(payload.freqMHz >= 920 && payload.freqMHz <= 923)) return "Frequency must be 920.0..923.0 MHz";
  if (![7.8, 10.4, 15.6, 20.8, 31.25, 41.7, 62.5, 125, 250, 500].includes(payload.bwKHz)) return "Bandwidth is not supported by SX1262";
  if (!(payload.sf >= 5 && payload.sf <= 12)) return "Spreading Factor must be 5..12";
  if (!(payload.cr >= 5 && payload.cr <= 8)) return "Coding Rate must be 5..8";
  if (!(payload.syncWord >= 0 && payload.syncWord <= 255)) return "Sync Word must be 0..255 or 0x00..0xFF";
  if (!(payload.txPowerDbm >= -9 && payload.txPowerDbm <= 22)) return "TX power must be -9..22 dBm";
  if (!(payload.preamble >= 6 && payload.preamble <= 65535)) return "Preamble must be 6..65535";
  const allowedTcxo = [0, 1.6, 1.7, 1.8, 2.2, 2.4, 2.7, 3.0, 3.3];
  if (!allowedTcxo.includes(payload.tcxoVoltage)) return "TCXO voltage is not supported";
  if (!allowedTcxo.includes(payload.xtalVoltage)) return "XTAL fallback voltage is not supported";
  return "";
}

export async function applyLoraConfig() {
  const payload = {
    freqMHz: Number($("loraFreqMHz").value),
    bwKHz: Number($("loraBwKHz").value),
    sf: Number($("loraSf").value),
    cr: Number($("loraCr").value),
    syncWord: parseSyncWord($("loraSyncWord").value),
    txPowerDbm: Number($("loraTxPowerDbm").value),
    preamble: Number($("loraPreamble").value),
    tcxoVoltage: Number($("loraTcxoVoltage").value),
    xtalVoltage: Number($("loraXtalVoltage").value),
    reboot: false
  };
  const error = validateLoraPayload(payload);
  if (error) {
    appendLog(`LORA_CONFIG_REJECTED ${error}`, "in");
    return;
  }
  if (!(await showConfirm(
    "Apply LoRa STAR settings now? The CH STAR radio must use the same values or the link will stop passing data.",
    "warn",
    "Apply LoRa"
  ))) return;
  const ack = await applyAndAlert(`SET_LORA_CONFIG_JSON ${JSON.stringify(payload)}`, "SET_LORA_CONFIG", "Apply LoRa");
  if (ack?.status === "ok") {
    await sendCommand("GET_INFO");
    await sendCommand("GET_STATUS");
  }
}
