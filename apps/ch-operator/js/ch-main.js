// CH (ClusterHead) Operator entry point: wires the DOM to the bridge and the
// serial protocol, then bootstraps. Serial-only over USB — no MQTT, no WiFi.

import { elements, state, validateChAddress, normalizeHexId } from "./ch-state.js";
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
  renderOverview, renderNodes, renderParents, renderPullRequest
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
  const id = normalizeHexId(elements.setRootGw.value);
  if (!/^[0-9A-F]{4}$/.test(id)) return showBanner("Gateway ID must be 4 hex digits.", "error");
  applyAndAlert(`SET_ROOT_GATEWAY_JSON {"gatewayId":"${id}","reboot":true}`, "SET_ROOT_GATEWAY_JSON", "Root gateway");
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
  if (!(p.freqMHz >= 900 && p.freqMHz <= 930)) return showBanner("STAR freq must be 900–930 MHz.", "error");
  applyAndAlert(`SET_STAR_LORA_JSON ${JSON.stringify(p)}`, "SET_STAR_LORA_JSON", "STAR LoRa");
}

function applyMeshLora() {
  const p = loraPayload("mesh");
  if (!(p.freqMHz >= 900 && p.freqMHz <= 930)) return showBanner("MESH freq must be 900–930 MHz.", "error");
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
      elements.fwTargetId.value = manifest.deviceId || "";
      elements.fwStatus.textContent = `Loaded ${manifest.environment} v${manifest.firmwareVersion} (${manifest.flashFiles.length} files, chip ${manifest.chip}).`;
      applyExpertLockUi();
    } catch (error) {
      state.manifest = null;
      elements.fwStatus.textContent = `Package error: ${error.message}`;
      applyExpertLockUi();
    }
  };
  input.click();
}

async function uploadFirmware() {
  if (!state.manifest) return showBanner("Load a firmware package folder first.", "error");
  const targetId = normalizeHexId(elements.fwTargetId.value);
  const port = elements.portSelect.value;
  if (!/^COM\d+$/i.test(port)) return showBanner("Select a COM port in Port Setup first.", "error");
  try {
    const result = await bridgeFetch("/api/firmware/upload", {
      method: "POST",
      body: JSON.stringify({
        env: state.manifest.environment || "ch",
        port,
        targetDeviceId: targetId,
        slot: state.activeSlot,
        manifest: state.manifest,
        packageFiles: Object.fromEntries(state.manifestFiles)
      })
    });
    showBanner(`Flashing v${result.firmwareVersion} to ${port}…`, "ok");
  } catch (error) {
    showBanner(`Upload failed: ${error.message}`, "error");
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
    if (confirm("Clear the stored parent from NVS and force re-discovery?")) sendCommand("CLEAR_PARENT_NVS");
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
  elements.fwUploadBtn.addEventListener("click", uploadFirmware);

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
