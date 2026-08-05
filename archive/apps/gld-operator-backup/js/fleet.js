// Multi-slot Fleet panel: a lightweight per-slot registry (port/deviceId/
// mode/alarm) backs a real sidebar list, while the existing detail-view
// tabs always represent whichever slot is "active" - full rendering logic
// is untouched by adding more slots, keeping regression risk low.

import { elements, state, MAX_FLEET_SLOTS, ensureFleetSlot } from "./state.js";
import { setSetupOpen, showBanner } from "./ui.js";
import { parseJsonAfter, formatGas, resetDeviceSnapshot, sendCommand } from "./serial-protocol.js";
import { updateConnectionUi, bridgeFetch } from "./bridge-client.js";
import { drawChart } from "./chart.js";

function textValue(value, fallback = "Unknown") {
  if (value === "unknown") return fallback;
  return value == null || value === "" ? fallback : String(value);
}

export function syncDeviceSummary() {
  const deviceId = textValue(state.status?.deviceId || state.info?.deviceId);
  const mode = textValue(state.status?.mode || state.info?.mode || state.mode);
  const telemetry = state.status?.telemetry || {};
  const gas = textValue(telemetry.gasName || formatGas(telemetry.gasClass), "n/a");
  const confidence = Number.isFinite(telemetry.confidence) ? `${telemetry.confidence}%` : "-%";
  const port = state.mock ? "mock" : elements.portSelect.value || (state.connected ? "selected" : "No port selected");

  elements.topDeviceStatus.textContent = deviceId;
  elements.topModeStatus.textContent = mode;
  elements.topGasStatus.textContent = gas;
  elements.topConfidenceStatus.textContent = confidence;
  elements.sideDeviceSummary.textContent = deviceId;
  elements.sidePortSummary.textContent = port;

  const activeEntry = ensureFleetSlot(state.activeSlot);
  activeEntry.deviceId = deviceId === "Unknown" ? "" : deviceId;
  activeEntry.mode = mode === "Unknown" ? "unknown" : mode;
  activeEntry.gas = gas;
  activeEntry.alarm = state.alarmActive === true;
  activeEntry.connected = state.mock || state.connected;
  activeEntry.port = state.mock ? "mock" : (elements.portSelect.value || activeEntry.port);
  renderFleetPanel();
}

export function renderFleetPanel() {
  const slotCount = Object.keys(state.fleet).length;
  elements.fleetCountBadge.textContent = `${slotCount} / ${MAX_FLEET_SLOTS} slots`;
  const others = Object.values(state.fleet)
    .filter((entry) => entry.slot !== state.activeSlot)
    .sort((a, b) => a.slot - b.slot);
  elements.fleetExtra.innerHTML = "";
  for (const entry of others) {
    const card = document.createElement("div");
    card.className = `fleet-card${entry.alarm ? " alarm" : ""}`;
    const head = document.createElement("span");
    head.textContent = `Slot ${entry.slot}${entry.connected ? "" : " (idle)"}`;
    const device = document.createElement("strong");
    device.textContent = entry.deviceId || "Unknown";
    const detail = document.createElement("small");
    detail.textContent = `${entry.port || "no port"} - ${entry.mode} - ${entry.gas}${entry.alarm ? " - ALARM" : ""}`;
    const actions = document.createElement("div");
    actions.className = "fleet-card-actions";
    const activateBtn = document.createElement("button");
    activateBtn.type = "button";
    activateBtn.textContent = "Make Active";
    activateBtn.addEventListener("click", () => setActiveSlot(entry.slot));
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", () => removeFleetSlot(entry.slot));
    actions.append(activateBtn, removeBtn);
    card.append(head, device, detail, actions);
    elements.fleetExtra.append(card);
  }
  elements.addSlotBtn.disabled = slotCount >= MAX_FLEET_SLOTS;
}

export function addFleetSlot() {
  for (let slot = 1; slot <= MAX_FLEET_SLOTS; slot += 1) {
    if (!state.fleet[slot]) {
      ensureFleetSlot(slot);
      setActiveSlot(slot);
      setSetupOpen(true);
      showBanner(`Slot ${slot} added and made active. Open Port Setup to connect a GLD to it.`, "ok");
      return;
    }
  }
  showBanner(`Maximum of ${MAX_FLEET_SLOTS} GLD slots reached.`, "warn");
}

export async function removeFleetSlot(slot) {
  const entry = state.fleet[slot];
  if (!entry) return;
  if (entry.connected && state.bridgeAvailable) {
    try {
      await bridgeFetch("/api/serial/disconnect", { method: "POST", body: JSON.stringify({ slot }) });
    } catch {
      /* best-effort */
    }
  }
  delete state.fleet[slot];
  renderFleetPanel();
}

export async function setActiveSlot(slot) {
  if (slot === state.activeSlot) return;
  state.activeSlot = slot;
  elements.activeSlotLabel.textContent = String(slot);
  ensureFleetSlot(slot);
  resetDeviceSnapshot();
  state.history = [];
  drawChart();
  const entry = state.fleet[slot];
  updateConnectionUi(entry.connected ? "connected" : "bridge ready", "ok");
  elements.portLabel.textContent = entry.port || "browser selected";
  syncDeviceSummary();
  if (entry.connected && state.bridgeAvailable) {
    await sendCommand("GET_INFO");
    await sendCommand("GET_STATUS");
  }
}

export function updateFleetFromLine(slot, line) {
  if (slot === state.activeSlot) return;
  const entry = ensureFleetSlot(slot);
  try {
    const info = parseJsonAfter("GLD_INFO_JSON", line);
    if (info) {
      entry.deviceId = info.deviceId || entry.deviceId;
      entry.mode = info.mode || entry.mode;
    }
    const status = parseJsonAfter("GLD_STATUS_JSON", line);
    if (status) {
      entry.deviceId = status.deviceId || entry.deviceId;
      entry.mode = status.mode || entry.mode;
      const telemetry = status.telemetry || {};
      entry.gas = telemetry.gasName || formatGas(telemetry.gasClass);
      entry.alarm = Boolean(telemetry.alarm || status.alarm);
    }
  } catch {
    /* ignore malformed background-slot lines */
  }
  renderFleetPanel();
}
