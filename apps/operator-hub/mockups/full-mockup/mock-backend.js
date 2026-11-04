/*
  Operator Hub mockup backend — browser-only simulation.

  This script replaces window.fetch (for /api/simple/*) and window.EventSource
  BEFORE the unmodified production js/hub.js is executed, so every Simple Hub
  flow runs against an in-memory model instead of bridge.py. It never opens a
  serial port, never talks to the network, and never writes firmware, NVS,
  MQTT, or any project data. Response shapes and validation messages mirror
  apps/operator-hub/bridge.py so the UI behaves as it would in production.
*/
(() => {
  "use strict";

  // ---------------------------------------------------------------- scenario
  const DEFAULTS = {
    gld: "normal",       // normal | fresh | fail | pending | alarm-locked
    ch: "normal",        // normal | fresh | fail
    gw: "normal",        // normal | fresh | fail
    drive: "steady_24v", // steady_24v | gpio41_high | gpio41_pullup
    inference: "0",      // 1 = GLD inference alarm currently active
    gwfw: "non_tls",     // non_tls | tls | legacy
    upload: "success",   // success | error
    speed: "normal",     // normal | fast
    preset: ""           // optional auto-play, see mock-panel.js
  };
  const hashParams = new URLSearchParams(location.hash.slice(1));
  const cfg = Object.fromEntries(Object.entries(DEFAULTS).map(([key, value]) => [key, hashParams.get(key) ?? value]));
  const speed = cfg.speed === "fast" ? 0.25 : 1;
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms * speed));
  const clone = (value) => JSON.parse(JSON.stringify(value ?? null));
  const TOKEN = "mockup-token";

  // ----------------------------------------------------------- package catalog
  // Versions mirror firmware-packages/<env>/latest/manifest.json at build time.
  const GLD_MODELS = [
    ["gld", "GasleakDetector - GLD1 (GPIO41 Lamp & Buzzer)", "gld"],
    ["model_1", "Model 1 - Board 1", "gld_model_1"],
    ["model_2", "Model 2 - Board 2", "gld_model_2"],
    ["model_3", "Model 3 - Board 3", "gld_model_3"],
    ["model_1_dataset_wifi", "GLD1 Model 1 - Hotspot Dataset 500 ms (mode khusus)", "gld_model_1_dataset_wifi"],
    ["model_2_dataset_wifi", "GLD1 Model 2 - Hotspot Dataset 500 ms (mode khusus)", "gld_model_2_dataset_wifi"],
    ["model_3_dataset_wifi", "GLD1 Model 3 - Hotspot Dataset 500 ms (mode khusus)", "gld_model_3_dataset_wifi"],
    ["model_1_dataset_replay_wifi", "GLD1 Model 1 - Hotspot buffer 5 menit (tahap 2)", "gld_model_1_dataset_replay_wifi"],
    ["model_2_dataset_replay_wifi", "GLD1 Model 2 - Hotspot buffer 5 menit (tahap 2)", "gld_model_2_dataset_replay_wifi"],
    ["model_3_dataset_replay_wifi", "GLD1 Model 3 - Hotspot buffer 5 menit (tahap 2)", "gld_model_3_dataset_replay_wifi"],
    ["gld_v2", "GasleakDetector - Board V2", "gld_v2"],
    ["model_1_dataset_workflow_wifi", "GLD1 Model 1 - Hotspot Wizard Dataset", "gld_model_1_dataset_workflow_wifi"],
    ["model_2_dataset_workflow_wifi", "GLD1 Model 2 - Hotspot Wizard Dataset", "gld_model_2_dataset_workflow_wifi"],
    ["model_3_dataset_workflow_wifi", "GLD1 Model 3 - Hotspot Wizard Dataset", "gld_model_3_dataset_workflow_wifi"],
    ["gld_atex", "GasleakDetector - GLD ATEX (GPIO7 fan)", "gld_atex"]
  ].map(([value, label, environment]) => ({ value, label, environment }));
  const VERSIONS = {
    gld: "0.8.38", gld_model_1: "0.8.36", gld_model_2: "0.8.36", gld_model_3: "0.8.36",
    gld_model_1_dataset_wifi: "0.8.36", gld_model_2_dataset_wifi: "0.8.36", gld_model_3_dataset_wifi: "0.8.36",
    gld_model_1_dataset_replay_wifi: "0.8.36", gld_model_2_dataset_replay_wifi: "0.8.36", gld_model_3_dataset_replay_wifi: "0.8.36",
    gld_model_1_dataset_workflow_wifi: "0.8.36", gld_model_2_dataset_workflow_wifi: "0.8.36", gld_model_3_dataset_workflow_wifi: "0.8.36",
    gld_v2: "0.8.30", gld_atex: "0.8.30",
    ch_small: "0.8.0", ch_large: "0.8.0",
    gw_small: "0.2.0", gw_large: "0.2.0", gw_small_tls: "0.2.0", gw_large_tls: "0.2.0"
  };
  const HOTSPOT_ENVS = new Set(GLD_MODELS.map((m) => m.environment).filter((env) => /_dataset_(?:replay_|workflow_)?wifi$/.test(env)));
  const pkg = (environment) => ({
    environment, available: true, firmwareVersion: VERSIONS[environment], protocolVersion: "0.2.0",
    // GLD1 v0.8.38 (commit 69a493c) is the downgrade that requires Reset NVS.
    requiresNvsResetBeforeBoot: environment === "gld"
  });
  const BOARDS = [{ value: "small", label: "Rectangle (kecil)" }, { value: "large", label: "Circle (besar)" }];
  const TRANSPORTS = [{ value: "non_tls", label: "MQTT non-TLS" }, { value: "tls", label: "MQTT over TLS" }];
  const GW_ENVS = { small: { non_tls: "gw_small", tls: "gw_small_tls" }, large: { non_tls: "gw_large", tls: "gw_large_tls" } };
  const firmwarePackageOptions = {
    gld: {
      models: GLD_MODELS,
      environments: Object.fromEntries(GLD_MODELS.map((m) => [m.value, m.environment])),
      packages: Object.fromEntries(GLD_MODELS.map((m) => [m.environment, pkg(m.environment)]))
    },
    ch: { boards: BOARDS, environments: { small: "ch_small", large: "ch_large" }, packages: { ch_small: pkg("ch_small"), ch_large: pkg("ch_large") } },
    gw: {
      boards: BOARDS, transports: TRANSPORTS, environments: GW_ENVS,
      packages: Object.fromEntries(Object.values(GW_ENVS).flatMap((t) => Object.values(t)).map((env) => [env, pkg(env)]))
    }
  };

  // ------------------------------------------------------------ device model
  const PORTS = {
    gld: [["COM10", "USB-Enhanced-SERIAL CH343 (COM10)"], ["COM9", "Silicon Labs CP210x USB to UART Bridge (COM9)"], ["COM1", "Communications Port (COM1)"]],
    ch: [["COM39", "USB-SERIAL CH340 (COM39)"], ["COM38", "USB-SERIAL CH340 (COM38)"], ["COM5", "USB-SERIAL CH340 (COM5)"], ["COM1", "Communications Port (COM1)"]],
    gw: [["COM3", "USB-SERIAL CH340 (COM3)"], ["COM1", "Communications Port (COM1)"]]
  };

  function syncAlarm(alarm) {
    alarm.physicalCommanded = alarm.mode === "manual" ? alarm.manualCommanded : alarm.inferenceAlarm;
    if (alarm.outputDrive === "active_low_gpio41_uln2003_pullup") {
      alarm.gpio41CommandLevel = alarm.physicalCommanded ? "LOW" : "HIGH";
      alarm.j2LampExpectedLevel = alarm.physicalCommanded ? "HIGH" : "LOW";
    }
    return alarm;
  }

  function alarmContract() {
    if (cfg.gld === "alarm-locked") return { available: false };
    const alarm = {
      available: true, mode: "auto", modePersisted: false, sessionOnly: true, resetsToAutoOnBoot: true,
      manualCommanded: false, inferenceAlarm: cfg.inference === "1", physicalCommanded: false
    };
    if (cfg.drive === "gpio41_high") {
      Object.assign(alarm, { outputDrive: "active_high_gpio41_steady", externalDevicePattern: "steady_high_while_alarm", singleTrigger: true });
    } else if (cfg.drive === "gpio41_pullup") {
      Object.assign(alarm, { outputDrive: "active_low_gpio41_uln2003_pullup", externalDevicePattern: "steady_high_while_alarm", singleTrigger: true, requiresExternalPullup: true });
    } else {
      Object.assign(alarm, { outputDrive: "steady_24v", externalDevicePattern: "self_pulsed_1s_on_1s_off" });
    }
    return syncAlarm(alarm);
  }

  // `factory` = identity a freshly reset NVS reports; otherwise a configured bench unit.
  function makeInfo(device, { factory = false, version, transport } = {}) {
    if (device === "gld") {
      return {
        deviceId: factory ? "1001" : "1A2B", targetChId: factory ? "0064" : "0066",
        firmwareVersion: version || "0.8.36", starLora: { freqMHz: factory ? 920.0 : 921.4 },
        radioReady: true, alarmControl: alarmContract()
      };
    }
    if (device === "ch") {
      return {
        chId: factory ? "0064" : "0066", rootGatewayId: "0001", firmwareVersion: version || "0.8.0",
        starLora: { freqMHz: factory ? 920.0 : 921.4 },
        radio: { starReady: 1, meshReady: cfg.ch === "fail" ? 0 : 1 }
      };
    }
    const fw = transport || cfg.gwfw;
    const info = {
      gatewayId: "0x0001", firmwareVersion: version || "0.2.0", meshReady: 1,
      wifi: factory ? 0 : 1, mqtt: factory || cfg.gw === "fail" ? 0 : 1
    };
    if (fw === "tls") Object.assign(info, { mqttTransport: "tls", tlsCapable: true });
    if (fw === "non_tls") info.mqttTransport = "non_tls";
    return info;
  }

  const sim = Object.fromEntries(["gld", "ch", "gw"].map((device) => [device, {
    device, connected: false, port: null, hasFirmware: cfg[device] !== "fresh", info: null
  }]));
  const activity = [];

  function addActivity(device, action, detail) {
    const now = new Date();
    const time = [now.getHours(), now.getMinutes(), now.getSeconds()].map((n) => String(n).padStart(2, "0")).join(":");
    activity.unshift({ time, device, action, detail });
    activity.splice(12);
  }

  function publicState(device) {
    const s = sim[device];
    return clone({ device, connected: s.connected, port: s.connected ? s.port : null, info: s.connected ? s.info : null });
  }

  class ApiError extends Error {
    constructor(message, status = 400) { super(message); this.status = status; }
  }
  const bad = (message) => { throw new ApiError(message, 400); };
  const fail = (message) => { throw new ApiError(message, 500); };

  function deviceOf(body) {
    const device = String(body.device || "");
    if (!sim[device]) bad("device must be gld, ch, or gw");
    return device;
  }
  function identified(device, message = "connect and identify the device first") {
    const s = sim[device];
    if (!s.connected || !s.info) fail(message);
    return s;
  }

  // ------------------------------------------------------------ Boot reports
  function gldReport() {
    const c = (label, ok, detail) => ({ label, ok, detail });
    const failing = cfg.gld === "fail";
    const checks = [
      c("ADS1256", true, "ADS1256 siap"),
      failing ? c("MCP4725", false, "MCP4725 terdeteksi 6/8; periksa kanal TCA, alamat MCP, dan catu daya") : c("MCP4725", true, "MCP4725 terdeteksi pada semua 8 kanal"),
      failing ? c("DAC Control", false, "Uji tulis DAC lulus 6/8") : c("DAC Control", true, "Uji tulis DAC lulus pada semua kanal"),
      c("LoRa", true, "Radio LoRa siap"),
      c("ML Model", true, "Model ML siap"),
      failing ? c("Sensor Read", false, "Pembacaan sensor belum valid; selesaikan masalah ADS/MCP atau tunggu telemetri")
        : cfg.gld === "pending" ? c("Sensor Read", null, "Belum ada telemetri sensor setelah boot check")
          : c("Sensor Read", true, "Semua 8 pembacaan sensor valid")
    ];
    return summarize(checks);
  }
  function chReport(info) {
    const star = info.radio?.starReady === 1, mesh = info.radio?.meshReady === 1;
    return summarize([
      { label: "CH identity", ok: Boolean(info.chId), detail: info.chId || "CH ID tidak terbaca" },
      { label: "Root Gateway", ok: Boolean(info.rootGatewayId), detail: info.rootGatewayId || "Root Gateway ID tidak terbaca" },
      { label: "Radio STAR", ok: star, detail: star ? "STAR siap" : "Radio STAR tidak siap" },
      { label: "Radio Mesh", ok: mesh, detail: mesh ? "Mesh siap" : "Radio Mesh tidak siap" }
    ]);
  }
  function gwReport(info) {
    const yes = (v) => v === 1 || v === true;
    return summarize([
      { label: "Gateway identity", ok: Boolean(info.gatewayId), detail: info.gatewayId || "Gateway ID tidak terbaca" },
      { label: "Radio Mesh", ok: yes(info.meshReady), detail: yes(info.meshReady) ? "Mesh siap" : "Mesh tidak siap" },
      { label: "Wi-Fi", ok: yes(info.wifi), detail: yes(info.wifi) ? "Wi-Fi tersambung" : "Wi-Fi belum tersambung" },
      { label: "MQTT", ok: yes(info.mqtt), detail: yes(info.mqtt) ? "MQTT tersambung" : "MQTT belum tersambung" }
    ]);
  }
  function summarize(checks) {
    const passed = checks.filter((x) => x.ok === true).length;
    const failed = checks.filter((x) => x.ok === false).length;
    return { total: checks.length, passed, failed, unknown: checks.length - passed - failed, checks };
  }

  // -------------------------------------------------------- upload event bus
  const sources = new Set();
  function emit(device, type, payload) {
    sources.forEach((source) => { if (source.device === device) source.dispatch(type, payload); });
  }
  class MockEventSource {
    constructor(url) {
      this.url = url;
      this.device = new URL(url, location.href).searchParams.get("device");
      this.listeners = {};
      this.readyState = 0;
      sources.add(this);
      setTimeout(() => { this.readyState = 1; this.dispatch("open", null); }, 120);
    }
    addEventListener(type, handler, options) {
      (this.listeners[type] ||= []).push({ handler, once: Boolean(options?.once) });
    }
    removeEventListener(type, handler) {
      this.listeners[type] = (this.listeners[type] || []).filter((item) => item.handler !== handler);
    }
    dispatch(type, payload) {
      if (this.readyState === 2) return;
      const event = { type, data: payload == null ? "" : JSON.stringify(payload) };
      (this.listeners[type] || []).slice().forEach((item) => {
        if (item.once) this.removeEventListener(type, item.handler);
        item.handler(event);
      });
    }
    close() { this.readyState = 2; sources.delete(this); }
  }

  // ------------------------------------------------------------- endpoints
  const HEX4 = /^[0-9A-F]{4}$/;
  const inRange = (value, lo, hi) => parseInt(value, 16) >= parseInt(lo, 16) && parseInt(value, 16) <= parseInt(hi, 16);
  const normId = (value) => String(value || "").trim().toUpperCase().replace(/^0X/, "");

  const routes = {
    "GET /api/simple/bootstrap": () => ({ apiToken: TOKEN, activity }),
    "GET /api/simple/overview": async () => {
      await wait(180);
      return {
        devices: Object.fromEntries(Object.keys(sim).map((d) => [d, publicState(d)])),
        firmwarePackageOptions, activity: clone(activity),
        mesh: "Fixed by design; use Expert only to inspect."
      };
    },
    "GET /api/simple/ports": async (_body, query) => {
      const device = query.get("device");
      if (!PORTS[device]) bad("device must be gld, ch, or gw");
      await wait(150);
      return { ports: PORTS[device].map(([path, description]) => ({ path, description })) };
    },
    "POST /api/simple/connect": async (body) => {
      const device = deviceOf(body);
      const port = String(body.port || "").toUpperCase();
      if (!/^COM\d+$/.test(port)) bad("valid COM port required");
      if (port === "COM1") { await wait(900); fail(`${port} is a system port with no operator device; choose the USB serial port`); }
      const s = sim[device];
      await wait(1100);
      s.connected = true;
      s.port = port;
      s.info = s.hasFirmware ? (s.info || makeInfo(device)) : null;
      const state = publicState(device);
      state.needsInitialFirmware = Boolean(state.connected && !state.info);
      addActivity(device, "Connect", state.info ? `${port}; connected and identified` : `${port}; connected but firmware identity was not detected`);
      return state;
    },
    "POST /api/simple/disconnect": async (body) => {
      const device = deviceOf(body);
      const s = sim[device];
      const port = s.port;
      await wait(250);
      s.connected = false;
      addActivity(device, "Disconnect", `${port || "COM"}; serial disconnected`);
      return { connected: false, port };
    },
    "POST /api/simple/refresh": async (body) => { const device = deviceOf(body); await wait(400); return publicState(device); },
    "POST /api/simple/test-device": async (body) => {
      const device = deviceOf(body);
      const s = identified(device);
      await wait(device === "gld" ? 2600 : 1300);
      const report = device === "gld" ? gldReport() : device === "ch" ? chReport(s.info) : gwReport(s.info);
      const result = report.failed === 0 && report.unknown === 0 ? "all checks OK" : `${report.failed} error, ${report.unknown} pending`;
      addActivity(device, "Test Device", `${s.port}; ${report.passed}/${report.total} OK; ${result}`);
      return { report, status: clone(s.info) };
    },
    "POST /api/simple/restart": async (body) => {
      const device = deviceOf(body);
      const s = identified(device);
      await wait(1800);
      // Alarm MANUAL is session-only: every reboot returns to AUTO with test output OFF.
      if (device === "gld" && s.info.alarmControl?.available) {
        Object.assign(s.info.alarmControl, { mode: "auto", manualCommanded: false });
        syncAlarm(s.info.alarmControl);
      }
      addActivity(device, "Restart", `${s.port}; command sent`);
      return { ok: true };
    },
    "POST /api/simple/config/id": async (body) => {
      const device = deviceOf(body);
      const value = normId(body.value);
      if (!HEX4.test(value)) bad("ID must be 4 hexadecimal digits");
      if (device === "gld" && !inRange(value, "1001", "FEFF")) bad("GLD ID must be 1001-FEFF");
      if (device === "ch" && !inRange(value, "0010", "0FFF")) bad("CH ID must be 0010-0FFF");
      if (device === "gw" && !inRange(value, "0001", "000F")) bad("Gateway ID must be 0001-000F");
      const s = identified(device);
      await wait(1200);
      if (device === "gld") s.info.deviceId = value;
      else if (device === "ch") s.info.chId = value;
      else s.info.gatewayId = `0x${value}`;
      addActivity(device, "Set ID", `${s.port}; ${value} saved and read back`);
      return { ok: true, value };
    },
    "POST /api/simple/config/star-frequency": async (body) => {
      const device = deviceOf(body);
      if (device === "gw") bad("Gateway Mesh radio is fixed and cannot be edited here");
      const raw = String(body.freqMHz ?? "").trim();
      if (!raw) bad("frequency required");
      const frequency = Number(raw);
      if (!Number.isFinite(frequency)) bad("frequency required");
      if (frequency < 920 || frequency > 923) bad("STAR frequency must be 920.0-923.0 MHz");
      const s = identified(device);
      await wait(1400);
      s.info.starLora = { ...(s.info.starLora || {}), freqMHz: Math.round(frequency * 1000) / 1000 };
      addActivity(device, "Set STAR frequency", `${s.port}; ${frequency.toFixed(3)} MHz saved and read back`);
      return { ok: true };
    },
    "POST /api/simple/config/target-ch": async (body) => {
      if (body.device !== "gld") bad("Target CH is a GLD setting");
      const value = normId(body.value);
      if (!HEX4.test(value) || !inRange(value, "0010", "0FFF")) bad("Target CH ID must be 0010-0FFF");
      const s = identified("gld", "connect and identify the GLD first");
      await wait(2200); // firmware reboots after SET_CH_ADDRESS_JSON
      s.info.targetChId = value;
      addActivity("gld", "Set Target CH", `${s.port}; ${value} saved and read back`);
      return { ok: true };
    },
    "POST /api/simple/config/alarm-mode": async (body) => {
      if (body.device !== "gld") bad("Alarm mode is a GLD setting");
      if (!["auto", "manual"].includes(body.mode)) bad("alarm mode must be auto or manual");
      const s = identified("gld", "connect and identify the GLD first");
      if (!s.info.alarmControl?.available) fail("connected GLD did not report a complete alarm-control contract");
      await wait(1000);
      Object.assign(s.info.alarmControl, { mode: body.mode, manualCommanded: false });
      syncAlarm(s.info.alarmControl);
      addActivity("gld", "Set alarm mode", `${s.port}; ${body.mode.toUpperCase()} session-only; read back`);
      return { ok: true, readback: publicState("gld") };
    },
    "POST /api/simple/config/manual-alarm": async (body) => {
      if (body.device !== "gld") bad("Manual alarm output is a GLD setting");
      if (typeof body.enabled !== "boolean") bad("manual alarm enabled must be boolean");
      const s = identified("gld", "connect and identify the GLD first");
      if (s.info.alarmControl?.mode !== "manual") fail("select and verify session-only MANUAL mode before testing the alarm output");
      await wait(900);
      s.info.alarmControl.manualCommanded = body.enabled;
      syncAlarm(s.info.alarmControl);
      addActivity("gld", "Manual alarm output", `${s.port}; test output ${body.enabled ? "ON" : "OFF"}; read back`);
      return { ok: true, readback: publicState("gld") };
    },
    "POST /api/simple/config/root-gateway": async (body) => {
      if (body.device !== "ch") bad("Root Gateway is a CH setting");
      const value = normId(body.value);
      if (!HEX4.test(value) || !inRange(value, "0001", "000F")) bad("Root Gateway ID must be 0001-000F");
      const s = identified("ch", "connect and identify the CH first");
      await wait(1300);
      s.info.rootGatewayId = value;
      addActivity("ch", "Set Root Gateway", `${s.port}; ${value} saved and read back`);
      return { ok: true };
    },
    "POST /api/simple/config/wifi": async (body) => {
      if (body.device !== "gw") bad("Wi-Fi is a Gateway setting");
      const ssid = String(body.ssid || "").trim();
      const password = String(body.password || "");
      if (!ssid) bad("Wi-Fi SSID is required");
      if (password && (password.length < 8 || password.length > 63)) bad("Wi-Fi password must be 8-63 characters");
      const s = identified("gw", "connect and identify the Gateway first");
      await wait(2600); // save, restart, TEST_WIFI
      s.info.wifi = 1;
      addActivity("gw", "Set Wi-Fi", `${s.port}; saved, restarted, and Wi-Fi verified`);
      return { ok: true };
    },
    "POST /api/simple/config/mqtt": async (body) => {
      if (body.device !== "gw") bad("MQTT is a Gateway setting");
      const s = identified("gw", "connect and identify the Gateway first");
      if (s.info.wifi !== 1) fail("Wi-Fi must pass its test before MQTT can be configured");
      const actual = s.info.mqttTransport;
      const requested = body.mqttTransport || "non_tls";
      if (!["non_tls", "tls"].includes(requested)) bad("MQTT transport must be non_tls or tls");
      const host = String(body.host || "").trim();
      const port = Number(body.port);
      if (!host || !String(body.port || "").trim()) bad("MQTT host and port are required");
      if (!Number.isInteger(port) || port < 1 || port > 65535) bad("MQTT port must be 1-65535");
      if (requested === "tls") {
        if (actual !== "tls" || s.info.tlsCapable !== true) fail("connected Gateway does not explicitly identify as TLS-capable TLS firmware");
        const ca = String(body.tlsCaPem || "").trim();
        if (ca.length < 256 || ca.length > 3900) bad("Root CA PEM is required for TLS and must be 256 to 3900 bytes");
        if (/PRIVATE KEY/.test(ca)) bad("Root CA field must not contain a private key");
        const blocks = ca.match(/-----BEGIN CERTIFICATE-----/g) || [];
        if (blocks.length !== 1) bad(blocks.length ? "Root CA PEM must contain exactly one CERTIFICATE block" : "Root CA PEM must contain one CERTIFICATE block");
        const ntp = String(body.ntpHost || "").trim();
        if (!ntp || ntp.length > 64) bad("NTP host is required for TLS and must be at most 64 ASCII bytes");
        if (!/^[A-Za-z0-9.-]+$/.test(ntp)) bad("NTP host is not a valid hostname or IP address");
      } else if (actual === "tls") {
        fail("connected Gateway identifies as TLS firmware; select MQTT over TLS");
      }
      await wait(2600);
      s.info.mqtt = 1;
      addActivity("gw", "Set MQTT", `${s.port}; ${requested} saved and MQTT verified`);
      return { ok: true, mqttTransport: requested };
    },
    "POST /api/simple/firmware/upload": async (body) => uploadFirmware(body)
  };

  async function uploadFirmware(body) {
    const device = deviceOf(body);
    const port = String(body.port || "").toUpperCase();
    if (!/^COM\d+$/.test(port)) bad("valid COM port required");
    let environment;
    if (device === "gld") {
      environment = firmwarePackageOptions.gld.environments[body.model];
      if (!environment) bad("selected GLD model package is not available");
    } else {
      if (!["small", "large"].includes(body.boardFormFactor)) bad("board form factor must be small or large");
      if (device === "ch") environment = firmwarePackageOptions.ch.environments[body.boardFormFactor];
      else {
        if (!["non_tls", "tls"].includes(body.mqttTransport)) bad("MQTT transport must be non_tls or tls");
        environment = GW_ENVS[body.boardFormFactor][body.mqttTransport];
      }
    }
    const pack = pkg(environment);
    const resetNvs = body.resetNvs === true;
    const initial = body.initialFirmware === true;
    if (resetNvs && body.resetNvsConfirmation !== "RESET NVS") bad("Reset NVS requires the explicit confirmation RESET NVS");
    if (HOTSPOT_ENVS.has(environment) && (initial || resetNvs)) bad("Hotspot Dataset requires an existing valid nulling profile; upload without Reset NVS");
    if (pack.requiresNvsResetBeforeBoot && !resetNvs) bad("GLD1 v0.8.38 rollback wajib Reset NVS; konfigurasi, nulling dan binding model akan dihapus");
    const s = sim[device];
    if (!s.connected) fail("connect the device first");
    if (s.port !== port) fail("selected port must match the connected device");
    if (!initial && !s.info) fail("connect and identify the device first");

    const line = (text) => emit(device, "upload_line", { line: text });
    emit(device, "upload_start", { cmd: `esptool write_flash (${environment})` });
    await wait(300);
    for (const text of ["esptool.py v4.7.0", `Serial port ${port}`, "Connecting....", "Chip is ESP32-S3 (QFN56) (revision v0.2)",
      "Features: WiFi, BLE, Embedded PSRAM 8MB (AP_3v3)", "Uploading stub...", "Changing baud rate to 921600", "Configuring flash size..."]) {
      line(text);
      await wait(170);
    }
    if (resetNvs) { line("Erasing NVS partition 0x9000 (0x5000 bytes)..."); await wait(450); }
    for (let percent = 2; percent <= 96; percent += 3) {
      emit(device, "upload_progress", { packagePercent: percent });
      if (percent % 15 === 2) line(`Writing at 0x${(0x10000 + percent * 0x3a00).toString(16).padStart(8, "0")}... (${percent} %)`);
      if (cfg.upload === "error" && percent >= 44) {
        const message = "A fatal error occurred: Failed to write to target RAM (result was 01070000: Operation timed out)";
        emit(device, "upload_error", { message });
        addActivity(device, initial ? "Initial firmware upload" : "Firmware upload", `${port}; ${environment}; failed`);
        fail(`firmware upload failed: ${message}`);
      }
      await wait(85);
    }
    line("Wrote 1572864 bytes (812314 compressed) at 0x00010000 in 9.4 seconds");
    line("Hash of data verified.");
    line("Hard resetting via RTS pin...");
    emit(device, "upload_done", { code: 0 });
    const action = initial ? "Initial firmware upload" : "Firmware upload";
    if (HOTSPOT_ENVS.has(environment)) {
      // Dedicated hotspot images leave the serial console; verification happens over Wi-Fi.
      s.connected = false;
      s.hasFirmware = true;
      s.info = null;
      addActivity(device, action, `${port}; ${environment} ${pack.firmwareVersion}; flash completed, verification pending hotspot`);
      return {
        ok: true, selectedEnvironment: environment, firmwareVersion: pack.firmwareVersion,
        flashToolCompleted: true, deviceVerified: false, verificationPending: "hotspot",
        nextStep: "Pemrograman selesai. Sambungkan Wi-Fi laptop ke GLD-DATASET-1A2B, lalu buka GLD Operator > Dataset Wireless dan Connect GLD untuk verifikasi."
      };
    }
    await wait(1300); // reboot + identity read-back
    const transport = device === "gw" ? body.mqttTransport : undefined;
    if (resetNvs || initial || !s.info) {
      s.info = makeInfo(device, { factory: true, version: pack.firmwareVersion, transport });
    } else {
      s.info.firmwareVersion = pack.firmwareVersion;
      if (device === "gw") {
        if (transport === "tls") Object.assign(s.info, { mqttTransport: "tls", tlsCapable: true });
        else { s.info.mqttTransport = "non_tls"; delete s.info.tlsCapable; }
      }
      if (device === "gld" && s.info.alarmControl?.available) {
        Object.assign(s.info.alarmControl, { mode: "auto", manualCommanded: false });
        syncAlarm(s.info.alarmControl);
      }
    }
    s.hasFirmware = true;
    addActivity(device, action, `${port}; ${environment} ${pack.firmwareVersion}; flashed, rebooted, identity read back${resetNvs ? "; NVS reset" : ""}`);
    return { ok: true, selectedEnvironment: environment, firmwareVersion: pack.firmwareVersion, flashToolCompleted: true, deviceVerified: true, readback: publicState(device) };
  }

  // --------------------------------------------------------- fetch override
  const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
  const realFetch = window.fetch.bind(window);
  const state = { pending: 0 }; // in-flight simulated requests (used by automated checks)
  window.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === "string" ? input : input.url, location.href);
    if (!url.pathname.startsWith("/api/")) return realFetch(input, init);
    const method = (init.method || "GET").toUpperCase();
    const route = routes[`${method} ${url.pathname}`];
    if (!route) return json({ error: `mockup: ${method} ${url.pathname} is not simulated` }, 404);
    if (method === "POST" && init.headers?.["X-Operator-Hub-Token"] !== TOKEN) return json({ error: "invalid API token" }, 403);
    state.pending += 1;
    try {
      const body = init.body ? JSON.parse(init.body) : {};
      return json(await route(body, url.searchParams));
    } catch (error) {
      return json({ error: error.message }, error.status || 500);
    } finally {
      state.pending -= 1;
    }
  };
  window.EventSource = MockEventSource;
  window.__operatorHubMock = { cfg, DEFAULTS, sim, activity, state };
})();
