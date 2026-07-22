// Local bridge networking for the CH operator: fetch wrapper, health poll +
// reconnect, SSE wiring, and COM port scan/connect. Serial-only — there is no
// MQTT or dataset surface. Talks to bridge.py on 127.0.0.1:5273.

import { elements, state } from "./ch-state.js";
import { setBadge, appendLog, showBanner, switchTab, setDrawer, wait } from "./ch-ui.js";
import { handleLine, sendCommand, resetDeviceSnapshot, stopPolling } from "./ch-protocol.js";

const BRIDGE_PORT = "5273";
const DEFAULT_BRIDGE_ORIGIN = `http://127.0.0.1:${BRIDGE_PORT}`;
let bridgeToken = "";

export function bridgeUrl(path) {
  const onBridgeOrigin = location.protocol.startsWith("http")
    && location.hostname === "127.0.0.1"
    && location.port === BRIDGE_PORT;
  return onBridgeOrigin ? path : `${DEFAULT_BRIDGE_ORIGIN}${path}`;
}

export async function bridgeFetch(path, options = {}) {
  const response = await fetch(bridgeUrl(path), {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(bridgeToken ? { "X-CH-Bridge-Token": bridgeToken } : {}),
      ...(options.headers || {})
    }
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `${response.status} ${response.statusText}`);
  return payload;
}

export async function initBridge() {
  try {
    const health = await bridgeFetch("/api/health");
    if (!health.csrfToken) throw new Error("bridge did not provide a request token");
    bridgeToken = health.csrfToken;
    const wasAvailable = state.bridgeAvailable;
    state.bridgeAvailable = Boolean(health.ok);
    state.bridgeFeatures = health.features || {};
    state.bridgeSlots = health.slots || {};
    setBadge(elements.bridgeBadge, "ok", "ok");
    startBridgeEvents();
    await refreshPorts(true);
    const activeSlot = state.bridgeSlots?.[String(state.activeSlot)];
    if (activeSlot?.connected) {
      state.connected = true;
      if (activeSlot.port) {
        elements.portSelect.value = activeSlot.port;
        updateSelectedPortDetail();
      }
      updateConnectionUi("connected", "ok");
    }
    if (!health.features?.serial) {
      appendLog(`SERIAL_UNAVAILABLE ${health.errors?.serial || "pyserial not installed"}`, "err");
    }
    if (!wasAvailable && state.bridgeReconnecting) {
      state.bridgeReconnecting = false;
      showBanner("Bridge reconnected.", "ok");
    }
  } catch {
    state.bridgeAvailable = false;
    setBadge(elements.bridgeBadge, "unreachable", "warn");
  }
}

export function startBridgeHealthPoll() {
  clearInterval(state.bridgeHealthTimer);
  state.bridgeHealthTimer = setInterval(async () => {
    try {
      const response = await fetch(bridgeUrl("/api/health"));
      if (!response.ok) throw new Error(`${response.status}`);
      if (!state.bridgeAvailable) {
        state.bridgeReconnecting = true;
        await initBridge();
      }
    } catch {
      if (state.bridgeAvailable) {
        state.bridgeAvailable = false;
        state.bridgeReconnecting = true;
        setBadge(elements.bridgeBadge, "reconnecting…", "warn");
        showBanner("Lost contact with the local bridge. Retrying…", "warn");
      } else {
        setBadge(elements.bridgeBadge, "unreachable", "warn");
      }
    }
  }, 5000);
}

function startBridgeEvents() {
  if (state.eventSource) state.eventSource.close();
  const source = new EventSource(bridgeUrl(`/api/events?token=${encodeURIComponent(bridgeToken)}`));
  source.onerror = () => {
    if (!state.bridgeAvailable) return;
    setBadge(elements.connectionBadge, "event lost", "warn");
  };
  source.addEventListener("serial_line", (event) => {
    const payload = JSON.parse(event.data);
    if ((payload.slot || 1) !== state.activeSlot) return;
    handleLine(payload.line);
  });
  source.addEventListener("serial_tx", (event) => {
    const payload = JSON.parse(event.data);
    if ((payload.slot || 1) !== state.activeSlot) return;
    appendLog(payload.line, "out");
  });
  source.addEventListener("serial_status", (event) => {
    const payload = JSON.parse(event.data);
    if ((payload.slot || 1) !== state.activeSlot) return;
    state.connected = Boolean(payload.connected);
    updateConnectionUi(payload.connected ? "connected" : "bridge ready", "ok");
    if (payload.port) setBadge(elements.portBadge, payload.port);
  });
  source.addEventListener("serial_error", (event) => {
    const payload = JSON.parse(event.data);
    if ((payload.slot || 1) !== state.activeSlot) return;
    state.connected = false;
    appendLog(`SERIAL_ERROR ${payload.message}`, "err");
    updateConnectionUi("serial error", "error");
  });
  source.addEventListener("upload_start", (event) => {
    appendLog(`UPLOAD_START ${JSON.parse(event.data).cmd}`, "in");
    switchTab("log");
  });
  source.addEventListener("upload_line", (event) => appendLog(JSON.parse(event.data).line, "in"));
  source.addEventListener("upload_done", (event) => appendLog(`UPLOAD_DONE code=${JSON.parse(event.data).code}`, "in"));
  source.addEventListener("upload_error", (event) => appendLog(`UPLOAD_ERROR ${JSON.parse(event.data).message}`, "err"));
  state.eventSource = source;
}

export async function refreshPorts(bridgeAlreadyChecked = false) {
  const btn = elements.refreshPortsBtn;
  const previousPort = elements.portSelect.value;
  const oldText = btn.textContent;
  btn.textContent = "Scanning";
  btn.disabled = true;
  if (!state.bridgeAvailable && !bridgeAlreadyChecked) await initBridge();
  if (!state.bridgeAvailable) {
    appendLog(`PORT_SCAN_SKIPPED bridge not reachable at ${DEFAULT_BRIDGE_ORIGIN}`, "err");
    btn.textContent = oldText;
    btn.disabled = false;
    return;
  }
  try {
    const result = await bridgeFetch("/api/ports");
    elements.portSelect.innerHTML = "";
    const ports = result.ports || [];
    if (!ports.length) {
      elements.portSelect.append(new Option("No serial ports", ""));
      updateSelectedPortDetail();
      return;
    }
    for (const port of ports) {
      const option = new Option(port.path, port.path);
      option.dataset.description = port.description || "";
      option.dataset.manufacturer = port.manufacturer || "";
      elements.portSelect.append(option);
    }
    const activeSlotPort = state.bridgeSlots?.[String(state.activeSlot)]?.port;
    const preferred = ports.find((p) => p.path === activeSlotPort)
      || ports.find((p) => p.path === previousPort)
      || ports.find((p) => p.path === "COM3")
      || ports[0];
    elements.portSelect.value = preferred.path;
    updateSelectedPortDetail();
    appendLog(`PORT_SCAN_OK ${ports.map((p) => p.path).join(", ")}`, "in");
  } catch (error) {
    appendLog(`PORT_SCAN_ERROR ${error.message}`, "err");
  } finally {
    btn.textContent = oldText;
    btn.disabled = false;
  }
}

export function updateConnectionUi(text, kind) {
  setBadge(elements.connectionBadge, text, kind);
  elements.connectBtn.disabled = state.connected;
  elements.disconnectBtn.disabled = !state.connected;
  const port = elements.portSelect.value;
  setBadge(elements.portBadge, port || "—");
  updateSelectedPortDetail();
  document.querySelectorAll(".quickcmd").forEach((b) => (b.disabled = !state.connected || !state.expertUnlocked));
  if (elements.expertInput) elements.expertInput.disabled = !state.connected || !state.expertUnlocked;
  if (elements.expertSendBtn) elements.expertSendBtn.disabled = !state.connected || !state.expertUnlocked;
}

export function updateSelectedPortDetail() {
  const option = elements.portSelect.selectedOptions[0];
  if (!option || !option.value) {
    elements.portDetail.textContent = state.bridgeAvailable ? "No serial port selected." : "Bridge not connected.";
    return;
  }
  const parts = [option.value];
  if (option.dataset.manual === "true") parts.push("manual override");
  if (option.dataset.description) parts.push(option.dataset.description);
  if (option.dataset.manufacturer) parts.push(option.dataset.manufacturer);
  elements.portDetail.textContent = parts.join(" — ");
}

export function ensureManualPortOption(select = true) {
  const manual = String(elements.manualPortInput.value || "").trim().toUpperCase();
  if (!/^COM\d+$/i.test(manual)) {
    appendLog(`MANUAL_PORT_REJECTED invalid COM port: ${elements.manualPortInput.value}`, "err");
    return "";
  }
  let option = Array.from(elements.portSelect.options).find((o) => o.value.toUpperCase() === manual);
  if (!option) {
    option = new Option(`${manual} (manual)`, manual);
    option.dataset.manual = "true";
    elements.portSelect.append(option);
  }
  if (select) {
    elements.portSelect.value = manual;
    updateSelectedPortDetail();
    appendLog(`MANUAL_PORT_SELECTED ${manual}`, "in");
  }
  return manual;
}

export async function connectSerial() {
  if (!state.bridgeAvailable) {
    showBanner("Local bridge is not running. Start run-ch-operator.bat.", "error");
    return;
  }
  const port = elements.portSelect.value;
  if (!port) {
    setDrawer("setup", true);
    appendLog("CONNECT_SKIPPED select a COM port first", "err");
    return;
  }
  try {
    resetDeviceSnapshot();
    await bridgeFetch("/api/serial/connect", {
      method: "POST",
      body: JSON.stringify({ port, baud: 115200, slot: state.activeSlot })
    });
    state.connected = true;
    updateConnectionUi("connected", "ok");
    // Handshake: ask the CH to identify itself. These only get JSON replies
    // once the CH firmware has the serial command parser; before that the
    // Overview/Nodes still fill from the CH_* log stream.
    await wait(200);
    await sendCommand("APP_PING");
    await wait(120);
    await sendCommand("GET_INFO");
    await wait(120);
    await sendCommand("GET_STATUS");
    await wait(120);
    await sendCommand("GET_NODES");
    await wait(120);
    await sendCommand("GET_PARENTS");
    setDrawer("setup", false);
  } catch (error) {
    appendLog(`CONNECT_ERROR ${error.message}`, "err");
    setBadge(elements.connectionBadge, "error", "error");
  }
}

export async function disconnectSerial() {
  stopPolling();
  if (!state.bridgeAvailable) return;
  await bridgeFetch("/api/serial/disconnect", {
    method: "POST",
    body: JSON.stringify({ slot: state.activeSlot })
  }).catch((error) => appendLog(`DISCONNECT_ERROR ${error.message}`, "err"));
  state.connected = false;
  updateConnectionUi("bridge ready", "ok");
}

export async function writeSerialLine(line) {
  return bridgeFetch("/api/serial/write", {
    method: "POST",
    body: JSON.stringify({ line, slot: state.activeSlot })
  });
}
