// Gateway Operator entry point. Setup is intentionally staged:
// serial COM -> Gateway Wi-Fi save/test -> Gateway and monitor MQTT.

import { $, elements, state, normalizeHexId, DEFAULT_GATEWAY_ID } from "./gw-state.js";
import { initTheme, toggleTheme } from "./theme.js";
import {
  appendLog, showBanner, hideBanner, switchTab, setDrawer, rerenderLog,
  unlockExpert, lockExpert, applyExpertLockUi, isExpertLocked
} from "./gw-ui.js";
import {
  initBridge, startBridgeHealthPoll, refreshPorts, connectSerial, disconnectSerial,
  ensureManualPortOption, bridgeFetch, connectMqtt, disconnectMqtt, testMqtt,
  publishPull, publishNode, useLocalPc, applyWifiConfig, testGatewayWifi,
  applyMqttConfig, requestMeshLoraConfig, applyMeshLoraConfig, updateSetupFlowUi,
  requestGatewayAddress, applyGatewayAddress, reconnectSerialAfterGatewayReboot
} from "./gw-bridge.js";
import { validateMeshLoraConfig } from "./gw-lora-config.mjs";
import { validateGatewayId } from "./gw-gateway-id.mjs";
import {
  renderOverview, renderUplinks, clearUplinks, renderTopology, clearTopology,
  renderCommandLog, clearCommandLog, tickStatusAge
} from "./gw-protocol.js";

// ---- Broker Setup drawer ---------------------------------------------------

function mqttConfigFromForm() {
  return {
    host: elements.mqttHost.value.trim(),
    port: Number(elements.mqttPort.value) || 1884,
    username: elements.mqttUsername.value,
    password: elements.mqttPassword.value,
    topicRoot: elements.mqttTopicRoot.value.trim() || "gld/gateway"
  };
}

async function handleMqttConnect() {
  if (!state.wifiVerified) return showBanner("Verify Gateway Wi-Fi before connecting MQTT.", "error");
  const config = mqttConfigFromForm();
  if (!config.host) return showBanner("Broker host is required.", "error");
  await connectMqtt(config);
}

async function handleMqttDisconnect() {
  await disconnectMqtt();
}

async function handleMqttTest() {
  if (!state.wifiVerified) return showBanner("Verify Gateway Wi-Fi before testing MQTT.", "error");
  const config = mqttConfigFromForm();
  if (!config.host) return showBanner("Broker host is required.", "error");
  elements.mqttSetupDetail.textContent = "Testing…";
  try {
    const result = await testMqtt(config);
    elements.mqttSetupDetail.textContent = result.ok
      ? `Reachable (${result.latencyMs} ms).`
      : `Not reachable: ${result.message}`;
  } catch (error) {
    elements.mqttSetupDetail.textContent = `Test failed: ${error.message}`;
  }
}

async function useCurrentPcWifi() {
  if (!state.bridgeAvailable) {
    showBanner("Local bridge is not running. Start run-gw-operator.bat.", "error");
    return;
  }
  elements.gwUseThisWifiBtn.disabled = true;
  elements.gwApplyWifiStatus.textContent = "Reading the active Windows Wi-Fi profile…";
  try {
    const info = await bridgeFetch("/api/wifi/current");
    elements.gwWifiSsid.value = info.ssid || "";
    if (info.passwordAvailable) elements.gwWifiPassword.value = info.password || "";
    state.wifiVerified = false;
    state.wifiIp = "";
    elements.gwApplyWifiStatus.textContent = info.passwordAvailable
      ? `Filled from this PC's active Wi-Fi profile: ${info.ssid}.`
      : `SSID ${info.ssid} filled; enter its password manually.`;
    updateSetupFlowUi();
  } catch (error) {
    elements.gwApplyWifiStatus.textContent = `Wi-Fi autofill failed: ${error.message}`;
  } finally {
    elements.gwUseThisWifiBtn.disabled = !state.serialConnected;
  }
}

async function handleApplyWifiConfig() {
  const config = {
    ssid: elements.gwWifiSsid.value.trim(),
    password: elements.gwWifiPassword.value,
    reboot: true
  };
  if (!config.ssid) {
    elements.gwApplyWifiStatus.textContent = "Wi-Fi SSID is required.";
    return;
  }
  elements.gwApplyWifiBtn.disabled = true;
  elements.gwApplyWifiStatus.textContent = "Sending to Gateway…";
  try {
    const ack = await applyWifiConfig(config);
    if (ack.status === "ok") {
      state.wifiVerified = false;
      state.wifiIp = "";
      elements.gwApplyWifiStatus.textContent = "Saved. Gateway is rebooting; reconnect COM if needed, then test Wi-Fi.";
      updateSetupFlowUi();
    } else {
      elements.gwApplyWifiStatus.textContent = `Rejected by device: ${ack.message || ack.status}`;
    }
  } catch (error) {
    elements.gwApplyWifiStatus.textContent = `Failed: ${error.message}`;
  } finally {
    elements.gwApplyWifiBtn.disabled = !state.serialConnected;
  }
}

async function handleTestGatewayWifi() {
  elements.gwTestWifiBtn.disabled = true;
  elements.gwApplyWifiStatus.textContent = "Testing Wi-Fi on the Gateway…";
  try {
    const ack = await testGatewayWifi();
    state.wifiVerified = ack.status === "ok" && ack.connected === "1";
    state.wifiIp = state.wifiVerified && ack.ip !== "none" ? ack.ip : "";
    elements.gwApplyWifiStatus.textContent = state.wifiVerified
      ? `Wi-Fi connected. Gateway IP: ${state.wifiIp || "available"}.`
      : "Wi-Fi is not connected on the Gateway. MQTT remains locked.";
  } catch (error) {
    state.wifiVerified = false;
    state.wifiIp = "";
    elements.gwApplyWifiStatus.textContent = `Wi-Fi test failed: ${error.message}`;
  } finally {
    elements.gwTestWifiBtn.disabled = !state.serialConnected;
    updateSetupFlowUi();
  }
}

async function handleApplyMqttConfig() {
  const config = {
    host: elements.mqttHost.value.trim(),
    port: Number(elements.mqttPort.value) || 1884,
    username: elements.mqttUsername.value,
    password: elements.mqttPassword.value
  };
  if (!config.host) {
    elements.gwApplyMqttStatus.textContent = "MQTT host is required.";
    return;
  }
  elements.gwApplyMqttBtn.disabled = true;
  elements.gwApplyMqttStatus.textContent = "Saving MQTT settings to the Gateway…";
  try {
    const ack = await applyMqttConfig(config);
    if (ack.status !== "ok") throw new Error(ack.message || ack.status);
    elements.gwApplyMqttStatus.textContent = "Saved. Gateway is connecting to MQTT.";
  } catch (error) {
    elements.gwApplyMqttStatus.textContent = `MQTT configuration failed: ${error.message}`;
  } finally {
    elements.gwApplyMqttBtn.disabled = !state.wifiVerified;
  }
}

function populateMeshLoraForm(config) {
  if (!config) return;
  elements.meshSetFreq.value = config.freqMHz ?? "";
  elements.meshSetBw.value = String(config.bwKHz ?? 125);
  elements.meshSetSf.value = config.sf ?? "";
  elements.meshSetCr.value = config.cr ?? "";
  elements.meshSetSync.value = config.syncWord ?? "";
  elements.meshSetTx.value = config.txPowerDbm ?? "";
  state.meshLoraDirty = false;
  elements.meshApplyStatus.textContent = "Current MESH LoRa settings loaded from Gateway.";
}

function populateGatewayIdentity(config) {
  const gatewayId = validateGatewayId(config?.gatewayId ?? state.gatewayId);
  state.gatewayId = gatewayId;
  elements.gatewayCurrentId.textContent = `0x${gatewayId}`;
  elements.gatewayIdInput.value = gatewayId;
  elements.gatewayIdStatus.textContent = "Current Gateway ID loaded from device NVS/runtime.";
}

async function handleLoadGatewayIdentity() {
  elements.gatewayIdStatus.textContent = "Reading current Gateway ID from device…";
  try {
    populateGatewayIdentity(await requestGatewayAddress());
  } catch (error) {
    elements.gatewayIdStatus.textContent = `Read failed: ${error.message}`;
  }
}

async function handleApplyGatewayIdentity() {
  let requestedGatewayId;
  try {
    requestedGatewayId = validateGatewayId(elements.gatewayIdInput.value);
  } catch (error) {
    elements.gatewayIdStatus.textContent = error.message;
    return;
  }

  elements.gatewayIdApplyBtn.disabled = true;
  elements.gatewayIdLoadBtn.disabled = true;
  elements.gatewayIdStatus.textContent = `Saving Gateway ID 0x${requestedGatewayId}…`;
  try {
    const ack = await applyGatewayAddress(requestedGatewayId);
    if (String(ack.status).toLowerCase() !== "ok") {
      throw new Error(ack.message || ack.status || "device rejected Gateway ID");
    }
    if (ack.reboot !== "1") {
      state.gatewayId = requestedGatewayId;
      populateGatewayIdentity({ gatewayId: requestedGatewayId });
      elements.gatewayIdStatus.textContent = `Gateway ID remains 0x${requestedGatewayId}; reboot not required.`;
      return;
    }

    elements.gatewayIdStatus.textContent = `Saved as 0x${requestedGatewayId}. Gateway is rebooting; waiting for COM reconnect…`;
    const reconnect = await reconnectSerialAfterGatewayReboot();
    elements.gatewayIdStatus.textContent = `Reconnected to ${reconnect.port}; verifying Gateway ID…`;
    const readback = await requestGatewayAddress();
    const verifiedGatewayId = validateGatewayId(readback.gatewayId);
    if (verifiedGatewayId !== requestedGatewayId) {
      throw new Error(`readback mismatch: expected ${requestedGatewayId}, received ${verifiedGatewayId}`);
    }
    populateGatewayIdentity({ gatewayId: verifiedGatewayId });
    elements.gatewayIdStatus.textContent = `Gateway ID 0x${verifiedGatewayId} saved, rebooted, reconnected, and verified.`;
    showBanner(`Gateway identity is now 0x${verifiedGatewayId}.`, "ok");
  } catch (error) {
    elements.gatewayIdStatus.textContent = `Gateway ID update failed: ${error.message}`;
    showBanner(`Gateway ID update failed: ${error.message}`, "error");
  } finally {
    elements.gatewayIdLoadBtn.disabled = !state.serialConnected;
    elements.gatewayIdApplyBtn.disabled = !state.serialConnected;
  }
}

async function handleLoadMeshLora() {
  elements.meshApplyStatus.textContent = "Reading MESH LoRa settings from Gateway…";
  try {
    populateMeshLoraForm(await requestMeshLoraConfig());
  } catch (error) {
    elements.meshApplyStatus.textContent = `Read failed: ${error.message}`;
  }
}

async function handleApplyMeshLora() {
  let config;
  try {
    config = validateMeshLoraConfig({
      freqMHz: elements.meshSetFreq.value,
      bwKHz: elements.meshSetBw.value,
      sf: elements.meshSetSf.value,
      cr: elements.meshSetCr.value,
      syncWord: elements.meshSetSync.value,
      txPowerDbm: elements.meshSetTx.value
    });
  } catch (error) {
    return showBanner(error.message, "error");
  }

  elements.meshApplyBtn.disabled = true;
  elements.meshApplyStatus.textContent = "Saving and verifying MESH LoRa settings…";
  try {
    const ack = await applyMeshLoraConfig(config);
    if (String(ack.status).toLowerCase() !== "ok") {
      throw new Error(ack.message || ack.status || "device rejected the settings");
    }
    state.meshLoraDirty = false;
    elements.meshApplyStatus.textContent = "Saved and verified. Gateway is rebooting; MQTT will reconnect automatically.";
    showBanner("MESH LoRa settings saved. Gateway is rebooting.", "ok");
  } catch (error) {
    elements.meshApplyStatus.textContent = `Save failed: ${error.message}`;
    showBanner(`MESH LoRa save failed: ${error.message}`, "error");
  } finally {
    elements.meshApplyBtn.disabled = !state.serialConnected;
  }
}

function invalidateWifiVerification() {
  if (!state.wifiVerified) return;
  state.wifiVerified = false;
  state.wifiIp = "";
  elements.gwApplyWifiStatus.textContent = "Wi-Fi credentials changed. Save and test again.";
  updateSetupFlowUi();
}

// ---- Commands tab: pull / node composers ------------------------------

function parseHopList(value) {
  return String(value || "")
    .split(/[\s,]+/)
    .map((v) => v.trim())
    .filter(Boolean)
    .map(normalizeHexId);
}

async function sendPull() {
  const hopList = parseHopList(elements.pullHopList.value);
  const cluster = normalizeHexId(elements.pullCluster.value);
  const requestId = Number(elements.pullRequestId.value) || undefined;
  if (!hopList.length && !cluster) return showBanner("Provide a hop list or a cluster ID.", "error");
  try {
    await publishPull({ gatewayId: `0x${state.gatewayId}`, hopList: hopList.length ? hopList : undefined, cluster: hopList.length ? undefined : cluster, requestId });
    showBanner("Pull request published.", "ok");
  } catch (error) {
    showBanner(`Pull publish failed: ${error.message}`, "error");
  }
}

async function sendNode() {
  const cluster = normalizeHexId(elements.nodeCluster.value);
  const node = normalizeHexId(elements.nodeId.value);
  const ttl = elements.nodeTtl.value ? Number(elements.nodeTtl.value) : undefined;
  const hex = elements.nodeHex.value.trim();
  const hopList = parseHopList(elements.nodeHopList.value);
  if (!cluster) return showBanner("Cluster ID is required.", "error");
  try {
    await publishNode({ gatewayId: `0x${state.gatewayId}`, cluster, node, id: node, ttl, hex, hopList: hopList.length ? hopList : undefined });
    showBanner("Node command published.", "ok");
  } catch (error) {
    showBanner(`Node publish failed: ${error.message}`, "error");
  }
}

// ---- Boot log actions -------------------------------------------------------

function downloadLog() {
  const text = state.logs.join("\n");
  const blob = new Blob([text], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `gw-boot-${new Date().toISOString().replace(/[:.]/g, "-")}.log`;
  a.click();
  URL.revokeObjectURL(a.href);
}

async function saveLogToDisk() {
  try {
    const result = await bridgeFetch("/api/session/log", {
      method: "POST",
      body: JSON.stringify({ text: state.logs.join("\n"), filename: `gw-boot-${Date.now()}.log` })
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
  elements.bootLog.textContent = "";
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
      elements.fwTargetId.value = manifest.deviceId || DEFAULT_GATEWAY_ID;
      if (manifest.environment) elements.fwEnvSelect.value = manifest.environment;
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

async function openFirmwareUploadDialog() {
  switchTab("firmware");
  if (state.bridgeAvailable) await refreshPorts(true);
  try {
    const builtin = await bridgeFetch("/api/firmware/package?env=gw");
    state.manifest = builtin.manifest;
    state.manifestFiles = new Map(Object.entries(builtin.packageFiles || {}));
  } catch (error) {
    state.manifest = null;
    state.manifestFiles = new Map();
    showBanner(`Package Gateway belum tersedia: ${error.message}`, "error");
  }
  const dialogPort = $("firmwareUploadPort");
  const selectedPort = elements.portSelect.value;
  dialogPort.replaceChildren(...Array.from(elements.portSelect.options).map((option) => new Option(option.text, option.value, false, option.value === selectedPort)));
  $("firmwareUploadPackage").textContent = state.manifest
    ? `Package: ${state.manifest.environment || "unknown"} v${state.manifest.firmwareVersion || "unknown"}`
    : "Paket Gateway belum tersedia.";
  const ready = Boolean(state.manifest && /^COM\d+$/i.test(dialogPort.value));
  $("firmwareUploadConfirmBtn").disabled = !ready;
  setFirmwareUploadStatus(ready ? "Ready to upload." : "Choose a valid package and COM port first.");
  setFirmwareUploadDialog(true);
}

async function uploadFirmware() {
  if (!state.manifest) return;
  const targetId = normalizeHexId(elements.fwTargetId.value || DEFAULT_GATEWAY_ID);
  const port = $("firmwareUploadPort").value;
  if (!/^COM\d+$/i.test(port)) return setFirmwareUploadStatus("Choose a valid COM port first.");
  elements.portSelect.value = port;
  $("firmwareUploadConfirmBtn").disabled = true;
  $("firmwareUploadCancelBtn").disabled = true;
  $("firmwareResetNvs").disabled = true;
  appendLog(`UPLOAD_START requested port=${port} env=${elements.fwEnvSelect.value || state.manifest.environment || "gw"}`, "in");
  switchTab("log");
  setFirmwareUploadStatus(`Disconnecting serial, then uploading to ${port}…`);
  $("firmwareUploadStatus").dataset.state = "loading";
  $("firmwareUploadStatus").setAttribute("aria-busy", "true");
  try {
    await disconnectSerial();
    const result = await bridgeFetch("/api/firmware/upload", {
      method: "POST",
      body: JSON.stringify({
        env: elements.fwEnvSelect.value || state.manifest.environment || "gw",
        port,
        targetDeviceId: targetId,
        resetNvs: $("firmwareResetNvs").checked,
        slot: state.activeSlot,
        manifest: state.manifest,
        packageFiles: Object.fromEntries(state.manifestFiles)
      })
    });
    setFirmwareUploadStatus(result.nvsReset
      ? `NVS direset. Connecting to ${port} dengan default firmware…`
      : `Upload berhasil. Parameter NVS dipertahankan. Connecting to ${port}…`);
    await connectSerial();
    setFirmwareUploadStatus(state.serialConnected
      ? `Upload berhasil. Connected to ${port}.`
      : `Upload berhasil, tetapi reconnect ke ${port} gagal. Periksa Gateway Setup.`);
    showBanner(`Firmware v${result.firmwareVersion} berhasil di-upload ke ${port}.`, "ok");
    if (state.serialConnected) setFirmwareUploadDialog(false);
  } catch (error) {
    showBanner(`Upload failed: ${error.message}`, "error");
    setFirmwareUploadStatus(`Upload gagal: ${error.message}`);
  } finally {
    $("firmwareUploadCancelBtn").disabled = false;
    $("firmwareResetNvs").disabled = false;
    $("firmwareUploadCancelBtn").textContent = "Close";
  }
}

// ---- Event wiring ----------------------------------------------------------

function setupEvents() {
  elements.themeToggleBtn.addEventListener("click", toggleTheme);
  elements.bannerDismiss.addEventListener("click", hideBanner);
  $("firmwareUploadBtn")?.addEventListener("click", openFirmwareUploadDialog);
  $("firmwareUploadCancelBtn")?.addEventListener("click", () => setFirmwareUploadDialog(false));
  document.querySelectorAll("[data-upload-dialog-close]").forEach((node) => node.addEventListener("click", () => setFirmwareUploadDialog(false)));
  $("firmwareUploadConfirmBtn")?.addEventListener("click", uploadFirmware);

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  // Broker Setup drawer
  elements.brokerSetupBtn.addEventListener("click", () => setDrawer("setup", true));
  elements.closeSetupBtn.addEventListener("click", () => setDrawer("setup", false));
  elements.setupBackdrop.addEventListener("click", () => setDrawer("setup", false));
  elements.mqttConnectBtn.addEventListener("click", handleMqttConnect);
  elements.mqttDisconnectBtn.addEventListener("click", handleMqttDisconnect);
  elements.mqttTestBtn.addEventListener("click", handleMqttTest);
  elements.useThisPcBtn.addEventListener("click", useLocalPc);
  elements.gwUseThisWifiBtn.addEventListener("click", useCurrentPcWifi);
  elements.gwApplyWifiBtn.addEventListener("click", handleApplyWifiConfig);
  elements.gwTestWifiBtn.addEventListener("click", handleTestGatewayWifi);
  elements.gwApplyMqttBtn.addEventListener("click", handleApplyMqttConfig);
  elements.meshLoadBtn.addEventListener("click", handleLoadMeshLora);
  elements.meshApplyBtn.addEventListener("click", handleApplyMeshLora);
  elements.gatewayIdLoadBtn.addEventListener("click", handleLoadGatewayIdentity);
  elements.gatewayIdApplyBtn.addEventListener("click", handleApplyGatewayIdentity);
  window.addEventListener("gw-gateway-address", (event) => populateGatewayIdentity(event.detail));
  for (const input of [elements.meshSetFreq, elements.meshSetBw, elements.meshSetSf,
    elements.meshSetCr, elements.meshSetSync, elements.meshSetTx]) {
    input.addEventListener("input", () => { state.meshLoraDirty = true; });
  }
  window.addEventListener("gw-mesh-lora-config", (event) => {
    if (!state.meshLoraDirty) populateMeshLoraForm(event.detail);
  });
  elements.gwWifiSsid.addEventListener("input", invalidateWifiVerification);
  elements.gwWifiPassword.addEventListener("input", invalidateWifiVerification);
  elements.refreshPortsBtn.addEventListener("click", () => refreshPorts());
  elements.connectSerialBtn.addEventListener("click", connectSerial);
  elements.disconnectSerialBtn.addEventListener("click", disconnectSerial);
  elements.useManualPortBtn.addEventListener("click", () => ensureManualPortOption(true));

  // Overview
  elements.refreshOverviewBtn.addEventListener("click", renderOverview);

  // Uplinks
  elements.clearUplinksBtn.addEventListener("click", clearUplinks);

  // Topology
  elements.clearTopologyBtn.addEventListener("click", clearTopology);

  // Commands
  elements.sendPullBtn.addEventListener("click", sendPull);
  elements.sendNodeBtn.addEventListener("click", sendNode);
  elements.clearCommandLogBtn.addEventListener("click", clearCommandLog);

  // Boot log
  elements.pauseLogBtn.addEventListener("click", toggleLogPause);
  elements.downloadLogBtn.addEventListener("click", downloadLog);
  elements.saveLogBtn.addEventListener("click", saveLogToDisk);
  elements.clearLogBtn.addEventListener("click", clearLog);

  // Firmware
  elements.lockBtn.addEventListener("click", async () => {
    if (isExpertLocked()) { if (await unlockExpert()) applyExpertLockUi(); }
    else { lockExpert(); applyExpertLockUi(); }
  });
  elements.fwPickBtn.addEventListener("click", pickFirmwareFolder);
  elements.fwUploadBtn.addEventListener("click", openFirmwareUploadDialog);
}

async function bootstrap() {
  initTheme();
  setupEvents();
  applyExpertLockUi();
  renderOverview();
  renderUplinks();
  renderTopology();
  renderCommandLog();
  elements.fwTargetId.value = DEFAULT_GATEWAY_ID;
  elements.gatewayIdInput.value = DEFAULT_GATEWAY_ID;
  await initBridge();
  updateSetupFlowUi();
  startBridgeHealthPoll();
  setInterval(tickStatusAge, 1000);
  appendLog("Gateway Operator ready. Setup order: connect COM, verify Gateway identity, save and verify Wi-Fi, then configure MQTT.", "in");
}

bootstrap();
