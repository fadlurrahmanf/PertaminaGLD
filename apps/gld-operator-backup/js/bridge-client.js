// Local bridge networking: fetch wrapper, health poll + reconnect, SSE
// wiring, and COM port scan/select. This is the only module that talks to
// bridge.py's REST/SSE surface directly.

import { elements, state, decoder } from "./state.js";
import { setBadge, setText, appendLog, showBanner, switchTab, setSetupOpen, wait } from "./ui.js";
import { syncDeviceSummary, renderFleetPanel, updateFleetFromLine } from "./fleet.js";
import { handleLine, clearSerialResponseWatch, sendCommand, resetDeviceSnapshot, stopPolling } from "./serial-protocol.js";
import { setDatasetState, handleDatasetMqttEvent, renderDatasetSession } from "./dataset.js";

const DEFAULT_BRIDGE_ORIGIN = "http://127.0.0.1:5173";

export function bridgeUrl(path) {
  const onBridgeOrigin = location.protocol.startsWith("http")
    && location.hostname === "127.0.0.1"
    && location.port === "5173";
  return onBridgeOrigin ? path : `${DEFAULT_BRIDGE_ORIGIN}${path}`;
}

export async function bridgeFetch(path, options = {}) {
  const response = await fetch(bridgeUrl(path), {
    ...options,
    headers: {
      "Content-Type": "application/json",
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
    const wasAvailable = state.bridgeAvailable;
    state.bridgeAvailable = Boolean(health.ok);
    state.bridgeFeatures = health.features || {};
    setBadge(elements.connectionBadge, "bridge ready", "ok");
    setBadge(elements.bridgeBadge, "bridge: ok", "ok");
    setText("protocolLabel", "bridge");
    elements.protocolLabel.title = `bridge ${health.version}`;
    startBridgeEvents();
    await refreshPorts(true);
    await initDatasetOutputDir();
    if (!state.bridgeFeatures.mqtt) {
      appendLog(`MQTT bridge unavailable: ${health.errors?.mqtt || "paho-mqtt not installed"}`, "in");
    }
    if (state.bridgeFeatures.mqttBroker) {
      appendLog(`MQTT_BROKER_READY ${health.mqttBroker?.host || "0.0.0.0"}:${health.mqttBroker?.port || 1884}`, "in");
    } else if (health.errors?.mqttBroker) {
      appendLog(`MQTT broker unavailable: ${health.errors.mqttBroker}`, "in");
    }
    if (!wasAvailable && state.bridgeReconnecting) {
      state.bridgeReconnecting = false;
      showBanner("Bridge reconnected.", "ok");
    }
  } catch {
    state.bridgeAvailable = false;
    setBadge(elements.bridgeBadge, "bridge: unreachable", "warn");
    if (!("serial" in navigator)) {
      setBadge(elements.connectionBadge, "Web Serial unavailable", "warn");
    }
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
        setBadge(elements.bridgeBadge, "bridge: reconnecting...", "warn");
        showBanner("Lost contact with the local bridge. Retrying...", "warn");
      } else {
        setBadge(elements.bridgeBadge, "bridge: unreachable", "warn");
      }
    }
  }, 5000);
}

async function initDatasetOutputDir() {
  try {
    const result = await bridgeFetch("/api/dataset/output-dir");
    if (result.path && state.dataset.outputPath === "Waiting for session") {
      state.dataset.outputPath = result.path;
      renderDatasetSession();
    }
  } catch (error) {
    appendLog(`DATASET_OUTPUT_DIR_ERROR ${error.message}`, "in");
  }
}

function startBridgeEvents() {
  if (state.eventSource) state.eventSource.close();
  const source = new EventSource(bridgeUrl("/api/events"));
  source.onerror = () => {
    if (!state.bridgeAvailable) return;
    setBadge(elements.connectionBadge, "bridge event lost", "warn");
  };
  source.addEventListener("serial_line", (event) => {
    const payload = JSON.parse(event.data);
    const slot = payload.slot || 1;
    if (slot !== state.activeSlot) {
      updateFleetFromLine(slot, payload.line);
      return;
    }
    if (state.mock) return;
    handleLine(payload.line);
  });
  source.addEventListener("serial_tx", (event) => {
    const payload = JSON.parse(event.data);
    if ((payload.slot || 1) !== state.activeSlot) return;
    appendLog(payload.line, "out");
  });
  source.addEventListener("serial_status", (event) => {
    const payload = JSON.parse(event.data);
    const slot = payload.slot || 1;
    updateFleetFromLine(slot, "");
    if (slot !== state.activeSlot) return;
    state.connected = Boolean(payload.connected);
    if (!payload.connected) clearSerialResponseWatch();
    updateConnectionUi(payload.connected ? "connected" : "bridge ready", "ok");
    if (payload.port) elements.portLabel.textContent = payload.port;
  });
  source.addEventListener("serial_error", (event) => {
    const payload = JSON.parse(event.data);
    if ((payload.slot || 1) !== state.activeSlot) return;
    clearSerialResponseWatch();
    state.connected = false;
    appendLog(`SERIAL_ERROR ${payload.message}`, "in");
    setBadge(elements.connectionBadge, "serial error", "error");
    updateConnectionUi("serial error", "error");
  });
  source.addEventListener("upload_start", (event) => {
    const payload = JSON.parse(event.data);
    appendLog(`UPLOAD_START ${payload.cmd}`, "in");
    switchTab("log");
  });
  source.addEventListener("upload_line", (event) => {
    const payload = JSON.parse(event.data);
    appendLog(payload.line, "in");
  });
  source.addEventListener("upload_done", (event) => {
    const payload = JSON.parse(event.data);
    appendLog(`UPLOAD_DONE code=${payload.code}`, "in");
  });
  source.addEventListener("upload_error", (event) => {
    const payload = JSON.parse(event.data);
    appendLog(`UPLOAD_ERROR ${payload.message}`, "in");
  });
  source.addEventListener("mqtt_publish", (event) => {
    const payload = JSON.parse(event.data);
    appendLog(`MQTT_PUBLISH ${payload.topic} ${payload.payload}`, "in");
  });
  source.addEventListener("dataset_monitor", (event) => {
    const payload = JSON.parse(event.data);
    if (payload.status === "started") {
      setDatasetState(state.dataset.state === "Idle" ? "Monitor Ready" : state.dataset.state, "MQTT dataset monitor started", `Dataset monitor ${payload.host}:${payload.port}`);
    } else if (payload.status === "subscribed") {
      setDatasetState(state.dataset.state, "Subscribed to dataset MQTT topics", `Subscribed ${payload.topics?.length || 0} dataset topics`);
    }
  });
  source.addEventListener("dataset_mqtt", (event) => {
    const payload = JSON.parse(event.data);
    appendLog(`DATASET_MQTT ${payload.topic} ${payload.payload}`, "in");
    handleDatasetMqttEvent(payload);
  });
  source.addEventListener("dataset_saved", (event) => {
    const payload = JSON.parse(event.data);
    state.dataset.outputName = payload.filename || state.dataset.outputName;
    state.dataset.outputPath = payload.path || state.dataset.outputPath;
    state.dataset.saved = true;
    renderDatasetSession();
  });
  state.eventSource = source;
}

export async function refreshPorts(bridgeAlreadyChecked = false) {
  const oldText = elements.refreshPortsBtn.textContent;
  elements.refreshPortsBtn.textContent = "Scanning";
  elements.refreshPortsBtn.disabled = true;
  if (!state.bridgeAvailable && !bridgeAlreadyChecked) {
    await initBridge();
  }
  if (!state.bridgeAvailable) {
    appendLog(`PORT_SCAN_SKIPPED bridge is not reachable at ${DEFAULT_BRIDGE_ORIGIN}`, "in");
    elements.refreshPortsBtn.textContent = oldText;
    elements.refreshPortsBtn.disabled = false;
    return;
  }
  try {
    const result = await bridgeFetch("/api/ports");
    elements.portSelect.innerHTML = "";
    const ports = result.ports || [];
    if (!ports.length) {
      elements.portSelect.append(new Option("No serial ports", ""));
      ensureManualPortOption(false);
      updateSelectedPortDetail();
      return;
    }
    for (const port of ports) {
      const option = new Option(port.path, port.path);
      option.dataset.description = port.description || "";
      option.dataset.manufacturer = port.manufacturer || "";
      elements.portSelect.append(option);
    }
    const manual = ensureManualPortOption(false);
    const preferred = ports.find((port) => port.path === "COM10")
      || (manual ? { path: manual } : null)
      || ports[0];
    elements.portSelect.value = preferred.path;
    elements.portLabel.textContent = preferred.path;
    updateSelectedPortDetail();
    const scanned = ports.map((port) => port.path).join(", ");
    appendLog(`PORT_SCAN_OK ${scanned}${manual && !ports.some((port) => port.path.toUpperCase() === manual) ? ` manual=${manual}` : ""}`, "in");
  } catch (error) {
    appendLog(`PORT_SCAN_ERROR ${error.message}`, "in");
  } finally {
    elements.refreshPortsBtn.textContent = oldText;
    elements.refreshPortsBtn.disabled = false;
  }
}

export function updateConnectionUi(text, kind) {
  setBadge(elements.connectionBadge, text, kind);
  elements.connectBtn.disabled = state.connected || state.mock;
  elements.disconnectBtn.disabled = !state.connected && !state.mock;
  if (state.mock) {
    elements.portLabel.textContent = "mock";
    elements.portDetail.textContent = "Mock GLD telemetry source.";
    elements.sidePortSummary.textContent = "mock";
  } else if (state.bridgeAvailable) {
    elements.portLabel.textContent = elements.portSelect.value || "bridge";
    updateSelectedPortDetail();
  } else {
    elements.portLabel.textContent = state.connected ? "selected" : "browser selected";
    elements.portDetail.textContent = state.connected ? "Browser-selected serial port." : "No serial port selected.";
    elements.sidePortSummary.textContent = state.connected ? "browser serial" : "No port selected";
  }
  syncDeviceSummary();
  renderFleetPanel();
}

export function updateSelectedPortDetail() {
  const option = elements.portSelect.selectedOptions[0];
  if (!option || !option.value) {
    elements.portDetail.textContent = state.bridgeAvailable ? "No serial port selected." : "Bridge not connected.";
    elements.portLabel.textContent = state.bridgeAvailable ? "bridge" : "browser selected";
    elements.sidePortSummary.textContent = "No port selected";
    return;
  }
  const parts = [option.value];
  if (option.dataset.manual === "true") parts.push("manual override");
  if (option.dataset.description) parts.push(option.dataset.description);
  if (option.dataset.manufacturer) parts.push(option.dataset.manufacturer);
  elements.portDetail.textContent = parts.join(" - ");
  elements.portLabel.textContent = option.value;
  elements.sidePortSummary.textContent = option.value;
}

function normalizePortName(value) {
  return String(value || "").trim().toUpperCase();
}

export async function connectSerial() {
  if (state.bridgeAvailable) {
    try {
      const connected = await connectBridgeSerialOnly({ resetSnapshot: true, openSetupOnMissingPort: true });
      if (!connected) return;
      await wait(180);
      await sendCommand("APP_PING");
      await wait(120);
      await sendCommand("GET_INFO");
      await wait(120);
      await sendCommand("GET_STATUS");
      setSetupOpen(false);
    } catch (error) {
      appendLog(`CONNECT_ERROR ${error.message}`, "in");
      setBadge(elements.connectionBadge, "error", "error");
    }
    return;
  }

  if (!("serial" in navigator)) {
    setBadge(elements.connectionBadge, "Web Serial unavailable", "error");
    appendLog("Browser does not expose Web Serial. Use Chrome or Edge over localhost/HTTPS.", "in");
    return;
  }
  try {
    const ports = await navigator.serial.getPorts();
    state.port = ports[0] || await navigator.serial.requestPort();
    await state.port.open({ baudRate: 115200, bufferSize: 4096 });
    state.writer = state.port.writable.getWriter();
    state.connected = true;
    updateConnectionUi("connected", "ok");
    readLoop();
    await sendCommand("APP_PING");
    await wait(120);
    await sendCommand("GET_INFO");
    await wait(120);
    await sendCommand("GET_STATUS");
    setSetupOpen(false);
  } catch (error) {
    setBadge(elements.connectionBadge, "error", "error");
    appendLog(`CONNECT_ERROR ${error.message}`, "in");
  }
}

export async function connectBridgeSerialOnly({ resetSnapshot = false, openSetupOnMissingPort = false } = {}) {
  const port = elements.portSelect.value;
  if (!port) {
    if (openSetupOnMissingPort) setSetupOpen(true);
    appendLog("CONNECT_SKIPPED select a COM port first", "in");
    return false;
  }
  if (resetSnapshot) {
    resetDeviceSnapshot();
  }
  await bridgeFetch("/api/serial/connect", {
    method: "POST",
    body: JSON.stringify({ port, baud: 115200, slot: state.activeSlot })
  });
  state.connected = true;
  updateConnectionUi("connected", "ok");
  return true;
}

async function readLoop() {
  try {
    state.reader = state.port.readable.getReader();
    while (state.connected) {
      const { value, done } = await state.reader.read();
      if (done) break;
      if (value) processChunk(decoder.decode(value, { stream: true }));
    }
  } catch (error) {
    if (state.connected) appendLog(`READ_ERROR ${error.message}`, "in");
  } finally {
    if (state.reader) {
      try { state.reader.releaseLock(); } catch {}
      state.reader = null;
    }
  }
}

function processChunk(text) {
  state.buffer += text;
  const parts = state.buffer.split(/\r?\n/);
  state.buffer = parts.pop() || "";
  parts.forEach(handleLine);
}

export async function disconnectSerial() {
  clearSerialResponseWatch();
  stopPolling();
  if (state.bridgeAvailable) {
    await bridgeFetch("/api/serial/disconnect", { method: "POST", body: JSON.stringify({ slot: state.activeSlot }) }).catch((error) => {
      appendLog(`DISCONNECT_ERROR ${error.message}`, "in");
    });
    state.connected = false;
    updateConnectionUi("bridge ready", "ok");
    return;
  }

  state.connected = false;
  try {
    if (state.reader) await state.reader.cancel();
  } catch {}
  try {
    if (state.writer) state.writer.releaseLock();
  } catch {}
  state.writer = null;
  try {
    if (state.port) await state.port.close();
  } catch {}
  state.port = null;
  updateConnectionUi("disconnected", "");
}

export function ensureManualPortOption(select = true) {
  const manual = normalizePortName(elements.manualPortInput.value);
  if (!/^COM\d+$/i.test(manual)) {
    appendLog(`MANUAL_PORT_REJECTED invalid COM port: ${elements.manualPortInput.value}`, "in");
    return "";
  }
  let option = Array.from(elements.portSelect.options).find((item) => item.value.toUpperCase() === manual);
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
