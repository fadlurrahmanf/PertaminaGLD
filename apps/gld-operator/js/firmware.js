// Firmware tab: manifest load/validate, PlatformIO upload with COM-lock
// preflight, and device ID injection.

import { $, elements, state } from "./state.js";
import { appendLog, getField, switchTab, showBanner } from "./ui.js";
import { bridgeFetch } from "./bridge-client.js";
import { sendCommand } from "./serial-protocol.js";
import { requireUnlock } from "./security.js";

export async function loadManifestFile(file) {
  if (!file) return;
  const text = await file.text();
  try {
    const manifest = JSON.parse(text);
    state.manifest = manifest;
    $("packageDeviceId").value = manifest.deviceId || "";
    if (manifest.env || manifest.environment) $("firmwareEnv").value = manifest.env || manifest.environment;
    $("manifestPreview").textContent = JSON.stringify(manifest, null, 2);
  } catch (error) {
    state.manifest = null;
    $("manifestPreview").textContent = `Invalid manifest: ${error.message}`;
  }
}

function validateManifestForUpload(manifest, env, targetDeviceId) {
  if (!manifest) return "";
  const manifestEnv = manifest.env || manifest.environment;
  if (manifestEnv && manifestEnv !== env) return `manifest env ${manifestEnv} does not match selected env ${env}`;
  const packageDeviceId = String(manifest.deviceId || "").toUpperCase();
  if (packageDeviceId && packageDeviceId !== "F000" && packageDeviceId !== targetDeviceId) {
    return `manifest deviceId ${packageDeviceId} does not match target ID ${targetDeviceId}`;
  }
  const chip = manifest.chipFamily || manifest.chip;
  if (chip && !/esp32s3/i.test(String(chip))) return `manifest chip ${chip} is not ESP32-S3`;
  return "";
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
    switchTab("firmware");
    return;
  }
  const lock = await checkPortLock();
  if (lock && !lock.free) {
    const proceed = window.confirm(
      `${port} looks busy (${lock.message}). Upload will disconnect this app's serial session and retry once, `
      + "but if PlatformIO still reports the chip not responding, close other serial monitors and replug the GLD USB. Continue anyway?"
    );
    if (!proceed) return;
  }
  if (!window.confirm(`Upload PlatformIO env ${env} to ${port}?`)) return;
  try {
    await bridgeFetch("/api/firmware/upload", {
      method: "POST",
      body: JSON.stringify({ env, port, targetDeviceId, manifest: state.manifest, slot: state.activeSlot })
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
  if (!window.confirm(`Inject GLD ID ${deviceId} and reboot?`)) return;
  await sendCommand(`SET_DEVICE_ID_JSON ${JSON.stringify({ deviceId, reboot: true })}`);
}
