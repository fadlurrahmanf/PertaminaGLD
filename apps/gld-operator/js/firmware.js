// Firmware tab: manifest load/validate, PlatformIO upload with COM-lock
// preflight, and device ID injection.

import { $, elements, state } from "./state.js";
import { appendLog, getField, switchTab, showBanner, showConfirm } from "./ui.js";
import { bridgeFetch, refreshPorts, updateSelectedPortDetail, connectSerial, disconnectSerial } from "./bridge-client.js";
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
  if (!isGldId(targetDeviceId)) return "target GLD ID must be in 1001-FEFF";
  if (manifest.schemaVersion !== 2 || manifest.packageType !== "pertamina-gld-prebuilt-firmware") return "firmware package must use the trusted schema-v2 format";
  const manifestEnv = manifest.environment;
  if (manifestEnv !== env) return `manifest environment ${manifestEnv} does not match selected env ${env}`;
  const packageDeviceId = String(manifest.deviceId || "").toUpperCase();
  if (packageDeviceId !== "ANY" && packageDeviceId !== targetDeviceId) {
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
    encoded[item.path] = typeof file === "string" ? file : arrayBufferToBase64(await file.arrayBuffer());
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

function setUploadDialog(open) {
  const dialog = $("firmwareUploadDialog");
  dialog?.classList.toggle("open", open);
  dialog?.setAttribute("aria-hidden", String(!open));
}

function setUploadDialogStatus(message, state = "") {
  const status = $("firmwareUploadStatus");
  if (!status) return;
  status.textContent = message;
  status.dataset.state = state;
  status.setAttribute("aria-busy", String(state === "loading"));
}

export async function uploadFirmware() {
  switchTab("expert");
  if (state.bridgeAvailable) await refreshPorts(true);
  const portSelect = $("firmwareUploadPort");
  const selectedPort = elements.portSelect.value;
  portSelect.replaceChildren(...Array.from(elements.portSelect.options).map((option) => new Option(option.text, option.value, false, option.value === selectedPort)));
  await loadBuiltinPackage($("firmwareUploadEnv").value);
  const ready = Boolean(state.manifest && /^COM\d+$/i.test(portSelect.value));
  $("firmwareUploadConfirmBtn").disabled = !ready;
  setUploadDialogStatus(ready ? "Ready to upload." : "Choose a valid package and COM port first.");
  setUploadDialog(true);
}

async function loadBuiltinPackage(environment) {
  try {
    const result = await bridgeFetch(`/api/firmware/package?env=${encodeURIComponent(environment)}`);
    state.manifest = result.manifest;
    state.manifestPackageFiles = new Map(Object.entries(result.packageFiles || {}));
    $("firmwareUploadPackage").textContent = `Package: ${state.manifest.environment} v${state.manifest.firmwareVersion}`;
  } catch (error) {
    state.manifest = null;
    state.manifestPackageFiles = new Map();
    $("firmwareUploadPackage").textContent = `Package belum tersedia: ${error.message}`;
  }
}

async function performFirmwareUpload() {
  if (!(await requireUnlock())) return;
  if (!state.bridgeAvailable) {
    appendLog("UPLOAD_SKIPPED local bridge is required for firmware upload", "in");
    showBanner("Firmware upload requires the local bridge to be running.", "warn");
    return;
  }
  const port = $("firmwareUploadPort").value;
  const env = state.manifest?.environment || "gld";
  const targetDeviceId = getField("targetDeviceId").toUpperCase();
  if (!/^COM\d+$/i.test(port)) {
    appendLog("UPLOAD_SKIPPED select a COM port first", "in");
    return;
  }
  const manifestWarning = validateManifestForUpload(state.manifest, env, targetDeviceId);
  if (manifestWarning) {
    appendLog(`UPLOAD_SKIPPED ${manifestWarning}`, "in");
    switchTab("expert");
    return;
  }
  elements.portSelect.value = port;
  updateSelectedPortDetail();
  $("firmwareUploadConfirmBtn").disabled = true;
  $("firmwareUploadCancelBtn").disabled = true;
  $("firmwareResetNvs").disabled = true;
  setUploadDialogStatus(`Disconnecting serial, then uploading to ${port}…`, "loading");
  try {
    await disconnectSerial();
    const packageFiles = await readPackageFiles(state.manifest);
    const result = await bridgeFetch("/api/firmware/upload", {
      method: "POST",
      body: JSON.stringify({ env, port, targetDeviceId, resetNvs: $("firmwareResetNvs").checked, manifest: state.manifest, packageFiles, slot: state.activeSlot })
    });
    setUploadDialogStatus(result.nvsReset
      ? `NVS direset. Connecting to ${port} dengan default firmware…`
      : `Upload berhasil. Parameter NVS dipertahankan. Connecting to ${port}…`, "success");
    await connectSerial();
    setUploadDialogStatus(state.connected
      ? `Upload berhasil. Connected to ${port}.`
      : `Upload berhasil, tetapi reconnect ke ${port} gagal. Periksa Port Setup.`, state.connected ? "success" : "warn");
    if (state.connected) setUploadDialog(false);
  } catch (error) {
    appendLog(`UPLOAD_ERROR ${error.message}`, "in");
    showBanner(`Firmware upload failed: ${error.message}`, "error");
    setUploadDialogStatus(`Upload gagal: ${error.message}`, "error");
  } finally {
    $("firmwareUploadCancelBtn").disabled = false;
    $("firmwareResetNvs").disabled = false;
    $("firmwareUploadCancelBtn").textContent = "Close";
  }
}

export function initFirmwareUploadDialog() {
  $("firmwareUploadCancelBtn")?.addEventListener("click", () => setUploadDialog(false));
  document.querySelectorAll("[data-upload-dialog-close]").forEach((node) => node.addEventListener("click", () => setUploadDialog(false)));
  $("firmwareUploadConfirmBtn")?.addEventListener("click", performFirmwareUpload);
  $("firmwareUploadEnv")?.addEventListener("change", async (event) => {
    await loadBuiltinPackage(event.target.value);
    $("firmwareUploadConfirmBtn").disabled = !state.manifest || !/^COM\d+$/i.test($("firmwareUploadPort").value);
  });
}

export async function injectDeviceId() {
  if (!(await requireUnlock())) return;
  const deviceId = getField("targetDeviceId").toUpperCase();
  if (!isGldId(deviceId)) {
    appendLog("ID_REJECTED target GLD ID must be in 1001-FEFF", "in");
    return;
  }
  if (!(await showConfirm(`Inject GLD ID ${deviceId} and reboot?`, "warn", "Inject GLD ID"))) return;
  await applyAndAlert(`SET_DEVICE_ID_JSON ${JSON.stringify({ deviceId, reboot: true })}`, "SET_DEVICE_ID", "Inject GLD ID");
}

function isGldId(value) {
  return /^[0-9A-F]{4}$/.test(value) && Number.parseInt(value, 16) >= 0x1001 && Number.parseInt(value, 16) <= 0xFEFF;
}

export function validateChAddress(chId, targetDeviceId) {
  if (!/^[0-9A-F]{4}$/.test(chId) || Number.parseInt(chId, 16) < 0x0010 || Number.parseInt(chId, 16) > 0x0FFF) return "CH address must be in 0010-0FFF";
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
