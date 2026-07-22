// GLD Operator entry point: wires DOM events and boots the app. Imports
// pull in every feature module; several are stubs until their milestone
// lands (see each module's header comment), so this file needs no further
// edits as those modules are fleshed out.

import { $, elements, state, SERIAL_RESPONSE_TIMEOUT_MS, DATASET_RUNTIME_READY_TIMEOUT_MS, DATASET_WAITING_STUCK_MS, loadTimeoutOverrides, applyTimeoutOverrides } from "./state.js";
import { setBadge, showBanner, hideBanner, withBusy, switchTab, setPanelOpen, numberField, saveForm, loadForm, exportLog, stamp, showAlert, showConfirm, initAppModal, appendLog, loadUiSession, togglePauseLog, applyLogPauseVisibility } from "./ui.js";
import { initTheme, toggleTheme } from "./theme.js";
import {
  initBridge, startBridgeHealthPoll, refreshPorts, ensureManualPortOption,
  updateSelectedPortDetail, connectSerial, disconnectSerial
} from "./bridge-client.js";
import { requireUnlock } from "./security.js";
import {
  sendCommand, applyAndAlert, togglePolling, stopPolling, renderSensorCheck, toggleAlarmMute, updateAlarmState
} from "./serial-protocol.js";
import { drawChart, renderLegend, pruneHistory, exportCsv } from "./chart.js";
import { applyNullingConfig, updateNullingMeta, renderNullingChannels } from "./nulling.js";
import {
  renderDatasetSession, applyGldSettings, publishDatasetCommand, confirmDatasetConfig,
  downloadDatasetCsv, openDatasetFolder, clearDatasetSession, useLocalhost,
  testMqttBroker, saveSessionLog, refreshDatasetWaitingState,
  beginDatasetSwitch, markDatasetWizardStarted, initDatasetWizard
} from "./dataset.js";
import { loadManifestFile, uploadFirmware, initFirmwareUploadDialog, injectDeviceId, injectChAddress, applyLoraConfig, checkPortLock } from "./firmware.js";
import { syncDeviceSummary, renderFleetPanel, addFleetSlot } from "./fleet.js";
import { toggleMock } from "./mock.js";
import { initQcTab, switchQcTab, switchQcGroup, restoreQcLatch } from "./qc.js";

function setupEvents() {
  elements.portSetupBtn.addEventListener("click", () => {
    setPanelOpen(elements.setupPanel, true);
    if (state.bridgeAvailable) refreshPorts(true);
  });
  $("firmwareUploadBtn")?.addEventListener("click", async () => {
    if (!state.bridgeAvailable) await initBridge();
    await uploadFirmware();
  });
  document.querySelectorAll("[data-close-dialog]").forEach((node) => {
    node.addEventListener("click", () => setPanelOpen($(node.dataset.closeDialog), false));
  });
  $("opsPanelBtn")?.addEventListener("click", () => setPanelOpen($("opsPanel"), true));
  $("restartGldBtn")?.addEventListener("click", async () => {
    const confirmed = await showConfirm(
      "Restart GLD sekarang? Board akan reboot, koneksi serial terputus sesaat, dan mode kembali ke default setelah boot.",
      "warn",
      "Restart GLD"
    );
    if (!confirmed) return;
    const button = $("restartGldBtn");
    await withBusy(button, "Restarting...", () => applyAndAlert("RESTART", "RESTART", "Restart GLD"));
  });
  $("runningSettingsBtn")?.addEventListener("click", () => setPanelOpen($("runningSettingsPanel"), true));
  $("datasetSettingsBtn")?.addEventListener("click", () => setPanelOpen($("datasetSettingsPanel"), true));
  $("nullingSettingsBtn")?.addEventListener("click", () => setPanelOpen($("nullingSettingsPanel"), true));
  $("themeToggleBtn")?.addEventListener("click", toggleTheme);
  elements.connectBtn.addEventListener("click", () => withBusy(elements.connectBtn, "Connecting...", connectSerial));
  elements.disconnectBtn.addEventListener("click", () => state.mock ? toggleMock() : disconnectSerial());
  elements.refreshPortsBtn.addEventListener("click", () => refreshPorts());
  elements.useManualPortBtn.addEventListener("click", () => ensureManualPortOption(true));
  elements.manualPortInput.addEventListener("change", saveForm);
  elements.portSelect.addEventListener("change", updateSelectedPortDetail);
  document.querySelectorAll(".poll-btn").forEach((button) => button.addEventListener("click", togglePolling));
  elements.rangeSelect.addEventListener("change", () => {
    pruneHistory();
    drawChart();
  });
  $("datasetRangeSelect")?.addEventListener("change", () => {
    pruneHistory();
    drawChart();
  });
  $("clearChartBtn").addEventListener("click", () => {
    state.history = [];
    drawChart();
  });
  $("datasetClearChartBtn")?.addEventListener("click", () => {
    state.history = [];
    drawChart();
  });
  $("exportCsvBtn").addEventListener("click", exportCsv);
  $("datasetExportCsvBtn")?.addEventListener("click", exportCsv);
  ["chartYAxisFixed", "chartYAxisMin", "chartYAxisMax"].forEach((id) => {
    $(id)?.addEventListener("change", drawChart);
  });
  $("downloadLogBtn").addEventListener("click", exportLog);
  $("clearLogBtn").addEventListener("click", () => {
    state.logs = [];
    elements.serialLog.textContent = "";
  });
  $("clearNullingBtn").addEventListener("click", () => {
    state.nullingLogs = [];
    elements.nullingLog.textContent = "";
    elements.nullingSummary.textContent = "No nulling activity.";
    updateNullingMeta();
    renderNullingChannels();
  });
  $("refreshSensorCheckBtn").addEventListener("click", () => sendCommand("GET_STATUS"));
  $("clearSensorCheckBtn").addEventListener("click", () => {
    state.status = null;
    state.bootDiagnostics = { reportSeen: false, bootRows: {}, probes: {}, lastLine: "" };
    renderSensorCheck();
  });
  $("applyConfigBtn").addEventListener("click", () => withBusy($("applyConfigBtn"), "Applying...", applyGldSettings));
  $("applyNullingConfigBtn").addEventListener("click", applyNullingConfig);
  $("refreshNullingConfigBtn").addEventListener("click", () => sendCommand("GET_STATUS"));
  $("switchDatasetBtn").addEventListener("click", () => withBusy($("switchDatasetBtn"), "Switching...", beginDatasetSwitch));
  $("startDatasetBtn").addEventListener("click", () => {
    markDatasetWizardStarted();
    if (!state.polling) togglePolling();
    withBusy($("startDatasetBtn"), "Starting...", () => publishDatasetCommand("START_DATASET"));
  });
  $("stopDatasetBtn").addEventListener("click", () => withBusy($("stopDatasetBtn"), "Stopping...", () => publishDatasetCommand("STOP_DATASET")));
  $("confirmDatasetConfigBtn").addEventListener("click", () => withBusy($("confirmDatasetConfigBtn"), "Confirming...", confirmDatasetConfig));
  $("downloadDatasetCsvBtn").addEventListener("click", downloadDatasetCsv);
  $("openDatasetFolderBtn").addEventListener("click", () => withBusy($("openDatasetFolderBtn"), "Opening...", openDatasetFolder));
  $("clearDatasetSessionBtn").addEventListener("click", clearDatasetSession);
  $("useThisPcBtn").addEventListener("click", () => withBusy($("useThisPcBtn"), "Reading PC info...", useLocalhost));
  $("unlockExpertBtn").addEventListener("click", () => requireUnlock());
  $("sendRawBtn").addEventListener("click", () => {
    const command = $("rawCommand").value.trim();
    if (command) sendCommand(command);
  });
  $("rawCommand").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !$("sendRawBtn").disabled) $("sendRawBtn").click();
  });
  initFirmwareUploadDialog();
  $("injectIdBtn")?.addEventListener("click", () => withBusy($("injectIdBtn"), "Injecting...", injectDeviceId));
  $("injectChBtn")?.addEventListener("click", () => withBusy($("injectChBtn"), "Applying...", injectChAddress));
  $("applyLoraConfigBtn")?.addEventListener("click", () => withBusy($("applyLoraConfigBtn"), "Applying...", applyLoraConfig));
  $("checkPortLockBtn")?.addEventListener("click", () => withBusy(elements.checkPortLockBtn, "Checking...", checkPortLock));
  $("testMqttBtn")?.addEventListener("click", () => withBusy(elements.testMqttBtn, "Testing...", testMqttBroker));
  elements.globalBannerDismiss.addEventListener("click", hideBanner);
  $("applyTimeoutsBtn")?.addEventListener("click", () => {
    applyTimeoutOverrides(numberField("timeoutSerialResponseMs"), numberField("timeoutDatasetReadyMs"), numberField("timeoutDatasetStuckMs"));
    showBanner("Timeout settings applied.", "ok");
    showAlert("Timeout settings applied.", "ok", "Timeout Settings");
  });
  elements.addSlotBtn.addEventListener("click", addFleetSlot);
  elements.runNullingNowBtn.addEventListener("click", () => {
    switchTab("nulling");
    sendCommand("SET_MODE nulling");
  });
  $("saveSessionLogBtn")?.addEventListener("click", () => saveSessionLog(state.dataset.sessionId || stamp(), "serial"));

  document.querySelectorAll("[data-command]").forEach((button) => {
    button.addEventListener("click", () => sendCommand(button.dataset.command));
  });
  document.querySelectorAll("[data-mode]").forEach((button) => {
    button.addEventListener("click", () => sendCommand(`SET_MODE ${button.dataset.mode}`));
  });
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      switchTab(button.dataset.tab);
      if (button.dataset.tab === "qc") sendCommand("GET_QC_STATUS");
    });
  });
  document.querySelectorAll("input").forEach((input) => {
    if (input.id !== "datasetNullingFirst") input.addEventListener("change", saveForm);
  });
  window.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    document.querySelectorAll(".drawer.open").forEach((panel) => setPanelOpen(panel, false));
    document.querySelectorAll(".modal.open").forEach((panel) => {
      if (panel.id === "appModal") return;
      setPanelOpen(panel, false);
    });
  });
  window.addEventListener("resize", drawChart);
}

// Restores the operator's last session (active tab, QC sub-tab/latch, and -
// if the local bridge is reachable - the previously connected COM port and
// polling state) instead of always starting from a blank Running tab. The
// GLD itself doesn't buffer historical telemetry/nulling logs for replay, so
// this puts the UI back where the operator left it and lets fresh data
// (GET_STATUS, GET_QC_STATUS) repopulate it, rather than reconstructing
// exactly what was on screen at the moment of refresh.
async function restoreSession(session) {
  if (session.qcActiveGroup) switchQcGroup(session.qcActiveGroup);
  if (session.qcActiveTab) switchQcTab(session.qcActiveTab);
  if (session.qcLatchOn) restoreQcLatch(true);

  const validTabIds = new Set(Array.from(document.querySelectorAll(".view")).map((view) => view.id));
  if (session.activeTab && validTabIds.has(session.activeTab)) switchTab(session.activeTab);

  if (!state.bridgeAvailable || !session.connected || !session.port) return;
  const hasPort = Array.from(elements.portSelect.options).some((option) => option.value === session.port);
  if (!hasPort) {
    appendLog(`AUTO_RECONNECT_SKIPPED port ${session.port} not found`, "in");
    return;
  }
  elements.portSelect.value = session.port;
  updateSelectedPortDetail();
  try {
    await connectSerial();
    if (session.polling) togglePolling();
    if (session.activeTab === "qc") sendCommand("GET_QC_STATUS");
  } catch (error) {
    appendLog(`AUTO_RECONNECT_ERROR ${error.message}`, "in");
  }
}

async function bootstrap() {
  const session = loadUiSession();
  loadForm();
  loadTimeoutOverrides();
  if ($("timeoutSerialResponseMs")) {
    $("timeoutSerialResponseMs").value = SERIAL_RESPONSE_TIMEOUT_MS;
    $("timeoutDatasetReadyMs").value = DATASET_RUNTIME_READY_TIMEOUT_MS;
    $("timeoutDatasetStuckMs").value = DATASET_WAITING_STUCK_MS;
  }
  initTheme();
  initAppModal();
  stopPolling();
  setupEvents();
  renderFleetPanel();
  renderLegend([]);
  initDatasetWizard();
  renderDatasetSession();
  setInterval(refreshDatasetWaitingState, 1000);
  updateNullingMeta();
  renderNullingChannels();
  initQcTab();
  renderSensorCheck();
  drawChart();
  updateAlarmState(false);
  syncDeviceSummary();
  await initBridge();
  startBridgeHealthPoll();
  await restoreSession(session);
  if (!window.isSecureContext) {
    console.info("WEB_SERIAL_NOTE Serve this page from http://127.0.0.1 or HTTPS for Web Serial.");
  }
  if (!state.bridgeAvailable && !("serial" in navigator)) {
    setBadge(elements.connectionBadge, "Web Serial unavailable", "warn");
  }
}

bootstrap();
