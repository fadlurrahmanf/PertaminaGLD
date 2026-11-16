// CH (ClusterHead) Operator entry point: wires the DOM to the bridge and the
// serial protocol, then bootstraps. Serial-only over USB — no MQTT, no WiFi.

import { $, elements, state, validateChAddress, validateGatewayAddress, normalizeHexId, DEFAULT_CH_ID } from "./ch-state.js";
import { initTheme, toggleTheme } from "./theme.js";
import {
  appendLog, showBanner, hideBanner, switchTab, setDrawer, rerenderLog,
  unlockExpert, lockExpert, applyExpertLockUi, isExpertLocked
} from "./ch-ui.js";
import {
  initBridge, startBridgeHealthPoll, refreshPorts, connectSerial, disconnectSerial,
  ensureManualPortOption, updateConnectionUi, bridgeFetch
} from "./ch-bridge.js";
import {
  handleLine, sendCommand, sendCommandAndWaitAck, togglePolling, tickAges,
  renderOverview, renderNodes, renderParents, renderPullRequest, resetParentDiscovery
} from "./ch-protocol.js";

// ---- Command builders (CH Settings drawer) ---------------------------------

async function applyAndAlert(cmd, ackName, label) {
  if (!state.connected) return showBanner("Connect to the CH first.", "error");
  try {
    const ack = await sendCommandAndWaitAck(cmd, ackName);
    if (ack.status && String(ack.status).toLowerCase() !== "ok") {
      showBanner(`${label} rejected: ${ack.message || ack.status}`, "error");
    } else {
      showBanner(`${label} applied.`, "ok");
    }
  } catch (error) {
    // The CH firmware may not have the command parser yet; the command was
    // still sent, we just never saw a structured ack.
    showBanner(`${label}: sent, no ack (${error.message}). If the CH firmware lacks the serial parser this is expected.`, "warn");
  }
}

function applyChId() {
  const check = validateChAddress(elements.setChId.value);
  if (!check.ok) return showBanner(`CH ID ${check.message}.`, "error");
  applyAndAlert(`SET_CH_ADDRESS_JSON {"chId":"${check.id}","reboot":true}`, "SET_CH_ADDRESS_JSON", "CH ID");
}

function applyRootGw() {
  const check = validateGatewayAddress(elements.setRootGw.value);
  if (!check.ok) return showBanner(`Gateway ID ${check.message}.`, "error");
  applyAndAlert(`SET_ROOT_GATEWAY_JSON {"gatewayId":"${check.id}","reboot":true}`, "SET_ROOT_GATEWAY_JSON", "Root gateway");
}

function loraPayload(prefix) {
  const n = (id) => Number(elements[`${prefix}${id}`].value);
  return {
    freqMHz: n("Freq"), bwKHz: n("Bw"), sf: n("Sf"), cr: n("Cr"),
    syncWord: n("Sync"), txPowerDbm: n("Tx"), reboot: true
  };
}

function applyStarLora() {
  const p = loraPayload("star");
  if (!(p.freqMHz >= 920 && p.freqMHz <= 923)) return showBanner("STAR freq must be 920–923 MHz.", "error");
  applyAndAlert(`SET_STAR_LORA_JSON ${JSON.stringify(p)}`, "SET_STAR_LORA_JSON", "STAR LoRa");
}

function applyMeshLora() {
  const p = loraPayload("mesh");
  if (!(p.freqMHz >= 920 && p.freqMHz <= 923)) return showBanner("MESH freq must be 920–923 MHz.", "error");
  applyAndAlert(`SET_MESH_LORA_JSON ${JSON.stringify(p)}`, "SET_MESH_LORA_JSON", "MESH LoRa");
}

// ---- Log actions -----------------------------------------------------------

function downloadLog() {
  const text = state.logs.join("\n");
  const blob = new Blob([text], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `ch-serial-${new Date().toISOString().replace(/[:.]/g, "-")}.log`;
  a.click();
  URL.revokeObjectURL(a.href);
}

async function saveLogToDisk() {
  try {
    const result = await bridgeFetch("/api/session/log", {
      method: "POST",
      body: JSON.stringify({ text: state.logs.join("\n"), filename: `ch-serial-${Date.now()}.log` })
    });
    showBanner(`Saved log to ${result.path}`, "ok");
  } catch (error) {
    showBanner(`Save failed: ${error.message}`, "error");
  }
}

function toggleLogPause() {
  state.logPaused = !state.logPaused;
  elements.pauseLogBtn.textContent = state.logPaused ? `Resume (${state.logPausedCount})` : "Pause";
  if (!state.logPaused) {
    state.logPausedCount = 0;
    rerenderLog();
  }
}

function clearLog() {
  state.logs = [];
  state.logPausedCount = 0;
  elements.serialLog.textContent = "";
}

// ---- Firmware upload -------------------------------------------------------

function readFileBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const bytes = new Uint8Array(reader.result);
      let binary = "";
      for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
      resolve(btoa(binary));
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(file);
  });
}

let manualUploadPackage = null;
let packageRequest = 0;

function pickFirmwareFolder() {
  const input = document.createElement("input");
  input.type = "file";
  input.webkitdirectory = true;
  input.onchange = async () => {
    try {
      const files = Array.from(input.files || []);
      const manifestFile = files.find((f) => f.name === "manifest.json" && (f.webkitRelativePath.split("/").length <= 2));
      if (!manifestFile) throw new Error("manifest.json not found at the package root");
      const manifest = JSON.parse(await manifestFile.text());
      state.manifest = manifest;
      state.manifestFiles = new Map();
      for (const item of manifest.flashFiles || []) {
        const bin = files.find((f) => f.name === item.path);
        if (!bin) throw new Error(`binary ${item.path} missing from folder`);
        state.manifestFiles.set(item.path, await readFileBase64(bin));
      }
      manualUploadPackage = {manifest, packageFiles: Object.fromEntries(state.manifestFiles)};
      elements.fwTargetId.value = manifest.deviceId === "ANY" ? DEFAULT_CH_ID : (manifest.deviceId || DEFAULT_CH_ID);
      elements.fwStatus.textContent = `Loaded ${manifest.environment} v${manifest.firmwareVersion} (${manifest.flashFiles.length} files, chip ${manifest.chip}).`;
      applyExpertLockUi();
    } catch (error) {
      state.manifest = null;
      manualUploadPackage = null;
      elements.fwStatus.textContent = `Package error: ${error.message}`;
      applyExpertLockUi();
    }
  };
  input.click();
}

function setFirmwareUploadDialog(open) {
  const dialog = $("firmwareUploadDialog");
  dialog?.classList.toggle("open", open);
  dialog?.setAttribute("aria-hidden", String(!open));
}

function setFirmwareUploadStatus(message, state = "") {
  const status = $("firmwareUploadStatus");
  const resolvedState = state || (message.startsWith("Disconnecting") ? "loading" : message.startsWith("Upload berhasil") ? "success" : message.startsWith("Upload gagal") ? "error" : "");
  status.textContent = message;
  status.dataset.state = resolvedState;
  status.setAttribute("aria-busy", String(resolvedState === "loading"));
}

async function loadFirmwareUploadProfile() {
  const request = ++packageRequest;
  const profile = $("firmwareUploadEnv").value;
  state.manifest = null;
  state.manifestFiles = new Map();
  $("firmwareUploadConfirmBtn").disabled = true;
  $("firmwareUploadPackage").textContent = "Memuat paket...";
  try {
    const candidate = profile === "ch_small" || profile === "ch_large";
    const builtin = profile === "custom" ? manualUploadPackage : profile
      ? await bridgeFetch(`/api/firmware/package?env=${encodeURIComponent(profile)}${candidate ? "&package=current-source-20261116" : ""}`)
      : null;
    if (request !== packageRequest) return;
    if (!builtin || !builtin.manifest || (profile !== "custom" && builtin.manifest.environment !== profile)) {
      throw new Error("Pilih paket CH yang tersedia dan sesuai board");
    }
    state.manifest = builtin.manifest;
    state.manifestFiles = new Map(Object.entries(builtin.packageFiles || {}));
    $("firmwareUploadPackage").textContent = `Package: ${state.manifest.environment} v${state.manifest.firmwareVersion} - ${state.manifest.boardProfile} - ${state.manifest.createdAtUtc || "tanggal tidak tersedia"}`;
    const ready = /^COM\d+$/i.test($("firmwareUploadPort").value);
    $("firmwareUploadConfirmBtn").disabled = !ready;
    setFirmwareUploadStatus(ready ? "Ready to upload." : "Choose a valid COM port first.");
  } catch (error) {
    if (request !== packageRequest) return;
    $("firmwareUploadPackage").textContent = "Paket tidak tersedia.";
    setFirmwareUploadStatus(`Paket gagal dimuat: ${error.message}`);
  }
}

async function openFirmwareUploadDialog() {
  switchTab("expert");
  if (state.bridgeAvailable) await refreshPorts(true);
  elements.fwTargetId.value = DEFAULT_CH_ID;
  const dialogPort = $("firmwareUploadPort");
  const selectedPort = elements.portSelect.value;
  dialogPort.replaceChildren(...Array.from(elements.portSelect.options).map((option) => new Option(option.text, option.value, false, option.value === selectedPort)));
  $("firmwareUploadEnv").value = manualUploadPackage ? "custom" : "";
  await loadFirmwareUploadProfile();
  setFirmwareUploadDialog(true);
}

async function uploadFirmware() {
  if (!state.manifest) return;
  const manifest = state.manifest;
  const packageFiles = Object.fromEntries(state.manifestFiles);
  const targetId = normalizeHexId(elements.fwTargetId.value);
  const port = $("firmwareUploadPort").value;
  if (!/^COM\d+$/i.test(port)) return setFirmwareUploadStatus("Choose a valid COM port first.");
  const targetCheck = validateChAddress(targetId);
  if (!targetCheck.ok) return setFirmwareUploadStatus(`Target CH ID ${targetCheck.message}.`);
  elements.portSelect.value = port;
  $("firmwareUploadConfirmBtn").disabled = true;
  $("firmwareUploadCancelBtn").disabled = true;
  $("firmwareResetNvs").disabled = true;
  $("firmwareUploadEnv").disabled = true;
  $("firmwareUploadPort").disabled = true;
  appendLog(`UPLOAD_START requested port=${port} env=${manifest.environment}`, "in");
  switchTab("log");
  setFirmwareUploadStatus(`Disconnecting serial, then uploading to ${port}…`);
  $("firmwareUploadStatus").dataset.state = "loading";
  $("firmwareUploadStatus").setAttribute("aria-busy", "true");
  try {
    await disconnectSerial();
    const result = await bridgeFetch("/api/firmware/upload", {
      method: "POST",
      body: JSON.stringify({
        env: manifest.environment,
        port,
        targetDeviceId: targetId,
        resetNvs: $("firmwareResetNvs").checked,
        slot: state.activeSlot,
        manifest,
        packageFiles
      })
    });
    setFirmwareUploadStatus(result.nvsReset
      ? `NVS direset. Connecting to ${port} dengan default firmware…`
      : `Upload berhasil. Parameter NVS dipertahankan. Connecting to ${port}…`);
    await connectSerial();
    setFirmwareUploadStatus(state.connected
      ? `Upload berhasil. Connected to ${port}.`
      : `Upload berhasil, tetapi reconnect ke ${port} gagal. Periksa Port Setup.`);
    showBanner(`Firmware v${result.firmwareVersion} berhasil di-upload ke ${port}.`, "ok");
    if (state.connected) setFirmwareUploadDialog(false);
  } catch (error) {
    showBanner(`Upload failed: ${error.message}`, "error");
    setFirmwareUploadStatus(`Upload gagal: ${error.message}`);
  } finally {
    $("firmwareUploadCancelBtn").disabled = false;
    $("firmwareResetNvs").disabled = false;
    $("firmwareUploadEnv").disabled = false;
    $("firmwareUploadPort").disabled = false;
    $("firmwareUploadCancelBtn").textContent = "Close";
  }
}

// ---- Event wiring ----------------------------------------------------------

function setupEvents() {
  elements.themeToggleBtn.addEventListener("click", toggleTheme);
  elements.bannerDismiss.addEventListener("click", hideBanner);

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  // Drawers
  elements.portSetupBtn.addEventListener("click", () => setDrawer("setup", true));
  $("firmwareUploadBtn")?.addEventListener("click", openFirmwareUploadDialog);
  $("firmwareUploadCancelBtn")?.addEventListener("click", () => setFirmwareUploadDialog(false));
  document.querySelectorAll("[data-upload-dialog-close]").forEach((node) => node.addEventListener("click", () => setFirmwareUploadDialog(false)));
  $("firmwareUploadConfirmBtn")?.addEventListener("click", uploadFirmware);
  $("firmwareUploadEnv")?.addEventListener("change", loadFirmwareUploadProfile);
  $("firmwareUploadPort")?.addEventListener("change", () => {
    $("firmwareUploadConfirmBtn").disabled = !(state.manifest && /^COM\d+$/i.test($("firmwareUploadPort").value));
  });
  elements.closeSetupBtn.addEventListener("click", () => setDrawer("setup", false));
  elements.setupBackdrop.addEventListener("click", () => setDrawer("setup", false));
  elements.settingsBtn.addEventListener("click", () => setDrawer("settings", true));
  elements.closeSettingsBtn.addEventListener("click", () => setDrawer("settings", false));
  elements.settingsBackdrop.addEventListener("click", () => setDrawer("settings", false));

  // Port setup
  elements.refreshPortsBtn.addEventListener("click", () => refreshPorts());
  elements.connectBtn.addEventListener("click", connectSerial);
  elements.disconnectBtn.addEventListener("click", disconnectSerial);
  elements.useManualPortBtn.addEventListener("click", () => ensureManualPortOption(true));

  // Overview
  elements.refreshOverviewBtn.addEventListener("click", () => {
    sendCommand("GET_INFO");
    sendCommand("GET_STATUS");
  });
  elements.pollToggleBtn.addEventListener("click", togglePolling);

  // Nodes
  elements.refreshNodesBtn.addEventListener("click", () => sendCommand("GET_NODES"));

  // Mesh / parent
  elements.sendHelloBtn.addEventListener("click", () => sendCommand("SEND_HELLO"));
  elements.clearParentBtn.addEventListener("click", () => {
    if (confirm("Clear the stored parent from NVS and force re-discovery?")) {
      sendCommand("CLEAR_PARENT_NVS");
      resetParentDiscovery();
    }
  });
  elements.forceFailoverBtn.addEventListener("click", () => sendCommand("FORCE_FAILOVER"));

  // Log
  elements.pauseLogBtn.addEventListener("click", toggleLogPause);
  elements.downloadLogBtn.addEventListener("click", downloadLog);
  elements.saveLogBtn.addEventListener("click", saveLogToDisk);
  elements.clearLogBtn.addEventListener("click", clearLog);

  // Expert
  elements.lockBtn.addEventListener("click", async () => {
    if (isExpertLocked()) { if (await unlockExpert()) applyExpertLockUi(); }
    else { lockExpert(); applyExpertLockUi(); }
    updateConnectionUi(state.connected ? "connected" : "bridge ready", state.connected ? "ok" : "");
  });
  elements.expertSendBtn.addEventListener("click", () => {
    const line = elements.expertInput.value.trim();
    if (line) { sendCommand(line); elements.expertInput.value = ""; }
  });
  elements.expertInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") elements.expertSendBtn.click();
  });
  document.querySelectorAll(".quickcmd").forEach((btn) => {
    btn.addEventListener("click", () => sendCommand(btn.dataset.cmd));
  });
  elements.fwPickBtn.addEventListener("click", pickFirmwareFolder);
  elements.fwUploadBtn.addEventListener("click", openFirmwareUploadDialog);

  // Settings
  elements.applyChIdBtn.addEventListener("click", applyChId);
  elements.applyRootGwBtn.addEventListener("click", applyRootGw);
  elements.applyStarLoraBtn.addEventListener("click", applyStarLora);
  elements.applyMeshLoraBtn.addEventListener("click", applyMeshLora);
  elements.settingsRestartBtn.addEventListener("click", () => {
    if (confirm("Restart the ClusterHead?")) sendCommand("RESTART");
  });
  elements.settingsDebugOnBtn.addEventListener("click", () => sendCommand("DEBUG_ON"));
  elements.settingsDebugOffBtn.addEventListener("click", () => sendCommand("DEBUG_OFF"));
}

async function bootstrap() {
  initTheme();
  setupEvents();
  applyExpertLockUi();
  renderOverview();
  renderNodes();
  renderParents();
  renderPullRequest();
  await initBridge();
  startBridgeHealthPoll();
  setInterval(tickAges, 1000);
  appendLog("CH Operator ready. Open Port Setup, pick the CH COM port (e.g. COM3), and Connect.", "in");
}

bootstrap();
