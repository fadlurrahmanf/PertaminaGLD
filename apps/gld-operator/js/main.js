// GLD Operator entry point: wires DOM events and boots the app. Imports
// pull in every feature module; several are stubs until their milestone
// lands (see each module's header comment), so this file needs no further
// edits as those modules are fleshed out.

import { $, elements, state, SERIAL_RESPONSE_TIMEOUT_MS, DATASET_RUNTIME_READY_TIMEOUT_MS, DATASET_WAITING_STUCK_MS, loadTimeoutOverrides, applyTimeoutOverrides } from "./state.js";
import { setBadge, showBanner, hideBanner, withBusy, switchTab, setSetupOpen, numberField, saveForm, loadForm, exportLog, stamp } from "./ui.js";
import {
  initBridge, startBridgeHealthPoll, refreshPorts, ensureManualPortOption,
  updateSelectedPortDetail, connectSerial, disconnectSerial
} from "./bridge-client.js";
import { requireUnlock } from "./security.js";
import {
  sendCommand, togglePolling, renderSensorCheck, toggleAlarmMute, updateAlarmState
} from "./serial-protocol.js";
import { drawChart, renderLegend, pruneHistory, exportCsv } from "./chart.js";
import { applyNullingConfig, updateNullingMeta, renderNullingChannels } from "./nulling.js";
import {
  renderDatasetSession, applyGldSettings, publishDatasetCommand, saveDatasetCsv,
  downloadDatasetCsv, openDatasetFolder, clearDatasetSession, useLocalhost,
  testMqttBroker, saveSessionLog, refreshDatasetWaitingState
} from "./dataset.js";
import { loadManifestFile, uploadFirmware, injectDeviceId, checkPortLock } from "./firmware.js";
import { syncDeviceSummary, renderFleetPanel, addFleetSlot } from "./fleet.js";
import { toggleMock } from "./mock.js";

function setupEvents() {
  elements.portSetupBtn.addEventListener("click", () => {
    setSetupOpen(true);
    if (state.bridgeAvailable) refreshPorts(true);
  });
  elements.closeSetupBtn.addEventListener("click", () => setSetupOpen(false));
  document.querySelectorAll("[data-close-setup]").forEach((node) => {
    node.addEventListener("click", () => setSetupOpen(false));
  });
  elements.connectBtn.addEventListener("click", () => withBusy(elements.connectBtn, "Connecting...", connectSerial));
  elements.disconnectBtn.addEventListener("click", () => state.mock ? toggleMock() : disconnectSerial());
  elements.alarmMuteBtn.addEventListener("click", toggleAlarmMute);
  elements.mockBtn.addEventListener("click", toggleMock);
  elements.refreshPortsBtn.addEventListener("click", () => refreshPorts());
  elements.useManualPortBtn.addEventListener("click", () => ensureManualPortOption(true));
  elements.manualPortInput.addEventListener("change", saveForm);
  elements.portSelect.addEventListener("change", updateSelectedPortDetail);
  elements.refreshLoopBtn.addEventListener("click", togglePolling);
  elements.rangeSelect.addEventListener("change", () => {
    pruneHistory();
    drawChart();
  });
  $("clearChartBtn").addEventListener("click", () => {
    state.history = [];
    drawChart();
  });
  $("exportCsvBtn").addEventListener("click", exportCsv);
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
  $("switchDatasetBtn").addEventListener("click", () => sendCommand("SET_MODE dataset"));
  $("startDatasetBtn").addEventListener("click", () => withBusy($("startDatasetBtn"), "Starting...", () => publishDatasetCommand("START_DATASET")));
  $("stopDatasetBtn").addEventListener("click", () => withBusy($("stopDatasetBtn"), "Stopping...", () => publishDatasetCommand("STOP_DATASET")));
  $("saveDatasetCsvBtn").addEventListener("click", () => withBusy($("saveDatasetCsvBtn"), "Saving...", saveDatasetCsv));
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
  $("loadManifestBtn").addEventListener("click", () => $("manifestFile").click());
  $("manifestFile").addEventListener("change", (event) => loadManifestFile(event.target.files[0]));
  $("uploadFirmwareBtn").addEventListener("click", () => withBusy($("uploadFirmwareBtn"), "Uploading...", uploadFirmware));
  $("injectIdBtn").addEventListener("click", () => withBusy($("injectIdBtn"), "Injecting...", injectDeviceId));
  $("checkPortLockBtn").addEventListener("click", () => withBusy(elements.checkPortLockBtn, "Checking...", checkPortLock));
  $("testMqttBtn").addEventListener("click", () => withBusy(elements.testMqttBtn, "Testing...", testMqttBroker));
  elements.globalBannerDismiss.addEventListener("click", hideBanner);
  $("applyTimeoutsBtn")?.addEventListener("click", () => {
    applyTimeoutOverrides(numberField("timeoutSerialResponseMs"), numberField("timeoutDatasetReadyMs"), numberField("timeoutDatasetStuckMs"));
    showBanner("Timeout settings applied.", "ok");
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
    button.addEventListener("click", () => switchTab(button.dataset.tab));
  });
  document.querySelectorAll("input").forEach((input) => {
    if (input.id !== "datasetNullingFirst") input.addEventListener("change", saveForm);
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setSetupOpen(false);
  });
  window.addEventListener("resize", drawChart);
}

async function bootstrap() {
  loadForm();
  loadTimeoutOverrides();
  if ($("timeoutSerialResponseMs")) {
    $("timeoutSerialResponseMs").value = SERIAL_RESPONSE_TIMEOUT_MS;
    $("timeoutDatasetReadyMs").value = DATASET_RUNTIME_READY_TIMEOUT_MS;
    $("timeoutDatasetStuckMs").value = DATASET_WAITING_STUCK_MS;
  }
  setupEvents();
  renderFleetPanel();
  renderLegend([]);
  renderDatasetSession();
  setInterval(refreshDatasetWaitingState, 1000);
  updateNullingMeta();
  renderNullingChannels();
  renderSensorCheck();
  drawChart();
  updateAlarmState(false);
  syncDeviceSummary();
  await initBridge();
  startBridgeHealthPoll();
  if (!window.isSecureContext) {
    console.info("WEB_SERIAL_NOTE Serve this page from http://127.0.0.1 or HTTPS for Web Serial.");
  }
  if (!state.bridgeAvailable && !("serial" in navigator)) {
    setBadge(elements.connectionBadge, "Web Serial unavailable", "warn");
  }
}

bootstrap();
