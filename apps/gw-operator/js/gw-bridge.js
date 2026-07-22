// Local bridge networking for the Gateway operator: fetch wrapper, health
// poll + reconnect, SSE wiring, MQTT connect/publish, and COM port
// scan/connect for the boot-log tail and staged Wi-Fi/MQTT provisioning.
// Talks to bridge.py on 127.0.0.1:5373.

import { elements, state } from "./gw-state.js";
import { setupAccess } from "./gw-setup-flow.mjs";
import { setBadge, appendLog, showBanner, switchTab } from "./gw-ui.js";
import { handleStatus, handleUplink, handleTopologyEvent, logCommand } from "./gw-protocol.js";

const BRIDGE_PORT = "5373";
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
      ...(bridgeToken ? { "X-GW-Bridge-Token": bridgeToken } : {}),
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
    const activeSlot = health.slots?.[String(state.activeSlot)];
    state.serialConnected = Boolean(activeSlot?.connected);
    setBadge(elements.bridgeBadge, "ok", "ok");
    startBridgeEvents();
    await refreshPorts(true);
    if (activeSlot?.port) elements.portSelect.value = activeSlot.port;
    updateSerialUi();
    if (state.serialConnected) {
      setTimeout(() => requestMeshLoraConfig().catch(() => {}), 300);
    }
    if (health.mqtt?.connected) {
      state.mqttConnected = true;
      state.mqttConfig = { ...state.mqttConfig, ...health.mqtt };
      updateMqttUi();
    }
    if (!health.features?.serial) {
      appendLog(`SERIAL_UNAVAILABLE ${health.errors?.serial || "pyserial not installed"}`, "err");
    }
    if (!health.features?.mqtt) {
      showBanner(`MQTT unavailable: ${health.errors?.mqtt || "paho-mqtt not installed"}`, "error", 0);
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

function updateMqttUi() {
  setBadge(elements.mqttBadge, state.mqttConnected ? "connected" : "disconnected", state.mqttConnected ? "ok" : "");
  setBadge(elements.connectionBadge, state.mqttConnected ? "live" : "idle", state.mqttConnected ? "ok" : "");
  if (elements.mqttConnectBtn) elements.mqttConnectBtn.disabled = state.mqttConnected || !state.wifiVerified;
  if (elements.mqttDisconnectBtn) elements.mqttDisconnectBtn.disabled = !state.mqttConnected;
}

export function updateSetupFlowUi() {
  const { wifiUnlocked, mqttUnlocked, mqttPanelEnabled } = setupAccess(state);
  if (elements.wifiSetupStep) {
    elements.wifiSetupStep.disabled = !wifiUnlocked;
    elements.wifiSetupStep.setAttribute("aria-disabled", String(!wifiUnlocked));
  }
  if (elements.mqttSetupStep) {
    elements.mqttSetupStep.disabled = !mqttPanelEnabled;
    elements.mqttSetupStep.setAttribute("aria-disabled", String(!mqttPanelEnabled));
  }
  if (elements.meshLoraSetupStep) {
    elements.meshLoraSetupStep.disabled = !wifiUnlocked;
    elements.meshLoraSetupStep.setAttribute("aria-disabled", String(!wifiUnlocked));
  }
  if (elements.meshApplyStatus && !wifiUnlocked) {
    elements.meshApplyStatus.textContent = "Locked until COM is connected.";
  }
  if (elements.mqttLockNote) {
    elements.mqttLockNote.textContent = mqttUnlocked
      ? `Wi-Fi verified on Gateway (${state.wifiIp || "IP available"}). MQTT setup is unlocked.`
      : "Locked until the Gateway Wi-Fi test passes.";
  }
  if (!wifiUnlocked && elements.gwApplyWifiStatus) {
    elements.gwApplyWifiStatus.textContent = "Locked until COM is connected.";
  }
  updateMqttUi();
}

function startBridgeEvents() {
  if (state.eventSource) state.eventSource.close();
  const source = new EventSource(bridgeUrl(`/api/events?token=${encodeURIComponent(bridgeToken)}`));
  source.onerror = () => {
    if (!state.bridgeAvailable) return;
    setBadge(elements.connectionBadge, "event lost", "warn");
  };
  source.addEventListener("mqtt_status", (event) => {
    const payload = JSON.parse(event.data);
    state.mqttConnected = Boolean(payload.connected);
    if (payload.topicRoot) state.mqttConfig.topicRoot = payload.topicRoot;
    updateMqttUi();
    if (elements.mqttSetupDetail) {
      elements.mqttSetupDetail.textContent = state.mqttConnected
        ? `Subscribed: ${(payload.topics || []).join(", ")}`
        : "Not connected.";
    }
  });
  source.addEventListener("mqtt_message", (event) => {
    const payload = JSON.parse(event.data);
    if (payload.kind === "status") {
      handleStatus(payload.json);
      if (state.serialConnected && payload.json?.wifi) {
        state.wifiVerified = true;
        state.wifiIp = payload.json.ip || "";
        if (elements.gwApplyWifiStatus) {
          elements.gwApplyWifiStatus.textContent = `Wi-Fi connected. Gateway IP: ${state.wifiIp || "available"}.`;
        }
        updateSetupFlowUi();
      }
    }
    else if (payload.kind === "uplink") handleUplink(payload.json, payload.payload);
    else if (payload.kind === "topology") handleTopologyEvent(payload.json);
  });
  source.addEventListener("mqtt_publish", (event) => {
    const payload = JSON.parse(event.data);
    appendLog(`MQTT_PUBLISH ${payload.topic} ${payload.payload}`, "tx");
  });
  source.addEventListener("serial_line", (event) => {
    const payload = JSON.parse(event.data);
    if ((payload.slot || 1) !== state.activeSlot) return;
    appendLog(payload.line, "in");
    window.dispatchEvent(new CustomEvent("gw-serial-line", { detail: payload.line }));
    const meshPrefix = "GW_MESH_LORA_JSON ";
    if (payload.line.startsWith(meshPrefix)) {
      try {
        const config = JSON.parse(payload.line.slice(meshPrefix.length));
        window.dispatchEvent(new CustomEvent("gw-mesh-lora-config", { detail: config }));
      } catch {
        appendLog("GW_MESH_LORA_JSON_PARSE_ERROR", "err");
      }
    }
  });
  source.addEventListener("serial_status", (event) => {
    const payload = JSON.parse(event.data);
    if ((payload.slot || 1) !== state.activeSlot) return;
    state.serialConnected = Boolean(payload.connected);
    if (!state.serialConnected) {
      state.wifiVerified = false;
      state.wifiIp = "";
    }
    updateSerialUi();
  });
  source.addEventListener("serial_error", (event) => {
    const payload = JSON.parse(event.data);
    if ((payload.slot || 1) !== state.activeSlot) return;
    state.serialConnected = false;
    state.wifiVerified = false;
    state.wifiIp = "";
    appendLog(`SERIAL_ERROR ${payload.message}`, "err");
    updateSerialUi();
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

function updateSerialUi() {
  if (elements.connectSerialBtn) elements.connectSerialBtn.disabled = state.serialConnected;
  if (elements.disconnectSerialBtn) elements.disconnectSerialBtn.disabled = !state.serialConnected;
  const port = elements.portSelect.value;
  updateSelectedPortDetail();
  updateSetupFlowUi();
  void port;
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
    const preferred = ports.find((p) => p.path === previousPort) || ports[0];
    elements.portSelect.value = preferred.path;
    updateSelectedPortDetail();
  } catch (error) {
    appendLog(`PORT_SCAN_ERROR ${error.message}`, "err");
  } finally {
    btn.textContent = oldText;
    btn.disabled = false;
  }
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
  }
  return manual;
}

export async function connectSerial() {
  if (!state.bridgeAvailable) {
    showBanner("Local bridge is not running. Start run-gw-operator.bat.", "error");
    return;
  }
  const port = elements.portSelect.value;
  if (!port) {
    appendLog("CONNECT_SKIPPED select a COM port first", "err");
    return;
  }
  try {
    await bridgeFetch("/api/serial/connect", {
      method: "POST",
      body: JSON.stringify({ port, baud: 115200, slot: state.activeSlot })
    });
    state.serialConnected = true;
    updateSerialUi();
    await requestMeshLoraConfig().catch((error) => appendLog(`GET_MESH_LORA_ERROR ${error.message}`, "err"));
  } catch (error) {
    appendLog(`CONNECT_ERROR ${error.message}`, "err");
  }
}

export async function disconnectSerial() {
  if (!state.bridgeAvailable) return;
  await bridgeFetch("/api/serial/disconnect", {
    method: "POST",
    body: JSON.stringify({ slot: state.activeSlot })
  }).catch((error) => appendLog(`DISCONNECT_ERROR ${error.message}`, "err"));
  state.serialConnected = false;
  updateSerialUi();
}

// ---- MQTT --------------------------------------------------------------

export async function connectMqtt(config) {
  if (!state.bridgeAvailable) {
    showBanner("Local bridge is not running. Start run-gw-operator.bat.", "error");
    return;
  }
  try {
    await bridgeFetch("/api/mqtt/connect", { method: "POST", body: JSON.stringify(config) });
    state.mqttConfig = { ...state.mqttConfig, ...config };
    showBanner(`Connecting to ${config.host}:${config.port}…`, "ok");
  } catch (error) {
    showBanner(`MQTT connect failed: ${error.message}`, "error");
  }
}

export async function disconnectMqtt() {
  try {
    await bridgeFetch("/api/mqtt/disconnect", { method: "POST", body: JSON.stringify({}) });
  } catch (error) {
    showBanner(`MQTT disconnect failed: ${error.message}`, "error");
  }
  state.mqttConnected = false;
  updateMqttUi();
}

export async function testMqtt(config) {
  return bridgeFetch("/api/mqtt/test", { method: "POST", body: JSON.stringify(config) });
}

// Gateway has no serial command console in the UI - this is the one command
// it understands (SET_WIFI_CONFIG_JSON, mirrors GLD's SET_APP_CONFIG_JSON).
// Waits for the device's GW_CMD_ACK line over the existing serial_line SSE
// stream rather than polling, since the ack can arrive well before the HTTP
// POST that queued the write even resolves.
function waitForAck(ackCmd, timeoutMs = 8000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      window.removeEventListener("gw-serial-line", onLine);
      reject(new Error("timeout waiting for device response"));
    }, timeoutMs);

    function onLine(event) {
      const text = event.detail;
      const prefix = `GW_CMD_ACK cmd=${ackCmd} `;
      if (!text.startsWith(prefix)) return;
      const fields = {};
      for (const part of text.slice(prefix.length).split(" ")) {
        const idx = part.indexOf("=");
        if (idx > 0) fields[part.slice(0, idx)] = part.slice(idx + 1);
      }
      clearTimeout(timer);
      window.removeEventListener("gw-serial-line", onLine);
      resolve(fields);
    }
    window.addEventListener("gw-serial-line", onLine);
  });
}

export async function applyWifiConfig(config) {
  if (!state.bridgeAvailable) {
    throw new Error("Local bridge is not running. Start run-gw-operator.bat.");
  }
  if (!state.serialConnected) {
    throw new Error("Connect the Gateway's serial port first (Broker Setup → boot-log serial port).");
  }
  const line = `SET_WIFI_CONFIG_JSON ${JSON.stringify(config)}`;
  const ackPromise = waitForAck("SET_WIFI_CONFIG");
  await bridgeFetch("/api/serial/write", { method: "POST", body: JSON.stringify({ line, slot: state.activeSlot }) });
  return ackPromise;
}

export async function testGatewayWifi() {
  if (!state.serialConnected) {
    throw new Error("Connect the Gateway COM port first.");
  }
  const ackPromise = waitForAck("TEST_WIFI", 5000);
  await bridgeFetch("/api/serial/write", {
    method: "POST",
    body: JSON.stringify({ line: "TEST_WIFI", slot: state.activeSlot })
  });
  return ackPromise;
}

export async function applyMqttConfig(config) {
  if (!state.serialConnected) {
    throw new Error("Connect the Gateway COM port first.");
  }
  if (!state.wifiVerified) {
    throw new Error("Test the Gateway Wi-Fi successfully before configuring MQTT.");
  }
  const line = `SET_MQTT_CONFIG_JSON ${JSON.stringify(config)}`;
  const ackPromise = waitForAck("SET_MQTT_CONFIG");
  await bridgeFetch("/api/serial/write", {
    method: "POST",
    body: JSON.stringify({ line, slot: state.activeSlot })
  });
  return ackPromise;
}

function waitForMeshLoraConfig(timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      window.removeEventListener("gw-mesh-lora-config", onConfig);
      reject(new Error("timeout waiting for MESH LoRa readback"));
    }, timeoutMs);
    function onConfig(event) {
      clearTimeout(timer);
      window.removeEventListener("gw-mesh-lora-config", onConfig);
      resolve(event.detail);
    }
    window.addEventListener("gw-mesh-lora-config", onConfig);
  });
}

export async function requestMeshLoraConfig() {
  if (!state.serialConnected) throw new Error("Connect the Gateway COM port first.");
  const response = waitForMeshLoraConfig();
  await bridgeFetch("/api/serial/write", {
    method: "POST",
    body: JSON.stringify({ line: "GET_MESH_LORA", slot: state.activeSlot })
  });
  return response;
}

export async function applyMeshLoraConfig(config) {
  if (!state.serialConnected) throw new Error("Connect the Gateway COM port first.");
  const ackPromise = waitForAck("SET_MESH_LORA_JSON", 8000);
  await bridgeFetch("/api/serial/write", {
    method: "POST",
    body: JSON.stringify({ line: `SET_MESH_LORA_JSON ${JSON.stringify(config)}`, slot: state.activeSlot })
  });
  return ackPromise;
}

export async function useLocalPc() {
  if (!state.bridgeAvailable) {
    showBanner("Local bridge is not running. Start run-gw-operator.bat.", "error");
    return;
  }
  try {
    const info = await bridgeFetch("/api/local-broker");
    elements.mqttHost.value = info.host || "";
    elements.mqttPort.value = String(info.port || 1884);
    elements.mqttUsername.value = info.username || "";
    elements.mqttPassword.value = info.password || "";
    elements.mqttTopicRoot.value = info.topicRoot || "gld/gateway";
    appendLog(`USE_HUB_BROKER host=${info.host || ""} port=${info.port || ""} auth=${info.username ? 1 : 0}`, "in");
  } catch (error) {
    appendLog(`USE_HUB_BROKER_ERROR ${error.message}`, "in");
  }
}

export async function publishPull(payload) {
  const result = await bridgeFetch("/api/mqtt/publish/pull", { method: "POST", body: JSON.stringify(payload) });
  logCommand("pull", result.topic, result.payload);
  return result;
}

export async function publishNode(payload) {
  const result = await bridgeFetch("/api/mqtt/publish/node", { method: "POST", body: JSON.stringify(payload) });
  logCommand("node", result.topic, result.payload);
  return result;
}
