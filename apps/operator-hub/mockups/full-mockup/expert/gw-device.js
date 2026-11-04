/*
  Simulated Gateway firmware + local MQTT bridge for the Gateway Operator
  mockup. Serial replies use the firmware formats (GW_CMD_ACK, GW_MESH_LORA_JSON,
  GW_GATEWAY_ADDRESS_JSON); MQTT traffic is synthesised as the bridge's
  mqtt_status / mqtt_message / mqtt_publish events. Representative values only.
*/
(() => {
  "use strict";
  const DEFAULTS = () => ({
    gatewayId: 0x0001, firmwareVersion: "0.8.18", protocolVersion: "0.2.0",
    wifi: { ssid: "PGL-BENCH", configured: true },
    mqtt: { host: "192.168.1.10", port: 1884, topicRoot: "gld/gateway", authConfigured: true },
    meshLora: { freqMHz: 922.0, bwKHz: 125, sf: 9, cr: 5, syncWord: 0x34, txPowerDbm: 17 }
  });
  const dev = { cfg: DEFAULTS(), bootAt: Date.now(), wifiUp: true, mqttUp: true, timer: null, bridgeMqtt: false, published: 0, seq: 10 };
  const hex = (n) => `0x${Number(n).toString(16).toUpperCase().padStart(4, "0")}`;
  const ack = (cmd, fields = {}) => `GW_CMD_ACK cmd=${cmd} ${Object.entries({ status: "ok", ...fields }).map(([k, v]) => `${k}=${String(v).replace(/\s+/g, "_")}`).join(" ")}`;
  const ip = () => (dev.wifiUp ? "192.168.1.57" : "none");

  function statusJson() {
    const c = dev.cfg;
    return {
      gatewayId: hex(c.gatewayId), state: dev.wifiUp && dev.mqttUp ? "ONLINE" : dev.wifiUp ? "WIFI_ONLY" : "OFFLINE",
      firmwareVersion: c.firmwareVersion, protocolVersion: c.protocolVersion, uptimeMs: Date.now() - dev.bootAt,
      ip: dev.wifiUp ? ip() : "", wifi: dev.wifiUp, mqtt: dev.mqttUp, meshReady: true,
      mqttQueueDepth: 0, mqttQueueCapacity: 32, mqttQueueDropped: 0, mqttQueuePublished: dev.published,
      wifiSsid: c.wifi.ssid, wifiRssi: -58, wifiChannel: 6, wifiMac: "34:85:18:A1:B2:C3",
      mqttHost: c.mqtt.host, mqttPort: c.mqtt.port, mqttState: dev.mqttUp ? 0 : -2, mqttAuthConfigured: c.mqtt.authConfigured,
      mqttSubscriptionsReady: dev.mqttUp, topicRoot: c.mqtt.topicRoot,
      meshFreqMhz: c.meshLora.freqMHz, meshBandwidthKhz: c.meshLora.bwKHz, meshSpreadingFactor: c.meshLora.sf,
      meshCodingRate: c.meshLora.cr, meshSyncWord: c.meshLora.syncWord, meshTxPowerDbm: c.meshLora.txPowerDbm, meshPreamble: 12
    };
  }

  function uplink(ctx, extra = {}) {
    dev.seq = (dev.seq + 1) % 256;
    dev.published += 1;
    const json = {
      msgType: 0x31, typeFlags: 0x31, srcId: "0x0066", dstId: hex(dev.cfg.gatewayId), seq: dev.seq, payloadLen: 68,
      rssi: -70 - Math.round(Math.random() * 10), snr: Number((5 + Math.random() * 4).toFixed(1)), parseStatus: "ok",
      records: [{ nodeId: "0x1A2B", seq: dev.seq, flags: "0x00", payloadLen: 29 }], ...extra
    };
    ctx.emit("mqtt_message", { kind: "uplink", topic: `${dev.cfg.mqtt.topicRoot}/${hex(dev.cfg.gatewayId)}/uplink`, json, payload: JSON.stringify(json) });
  }

  function topology(ctx) {
    ctx.emit("mqtt_message", {
      kind: "topology", topic: `${dev.cfg.mqtt.topicRoot}/${hex(dev.cfg.gatewayId)}/topology`,
      json: { chId: "0x0066", parentId: "0x0065", batteryMv: 3920, rssi: -74, snr: 7.5, reportType: "HELLO", routeFlags: 15 }
    });
    ctx.emit("mqtt_message", {
      kind: "topology", topic: `${dev.cfg.mqtt.topicRoot}/${hex(dev.cfg.gatewayId)}/topology`,
      json: { chId: "0x0065", parentId: "0x0064", batteryMv: 4010, rssi: -69, snr: 8.25, reportType: "HELLO", routeFlags: 15 }
    });
  }

  function startMqttFeed(ctx) {
    clearInterval(dev.timer);
    let tick = 0;
    const publishStatus = () => ctx.emit("mqtt_message", { kind: "status", topic: `${dev.cfg.mqtt.topicRoot}/${hex(dev.cfg.gatewayId)}/status`, json: statusJson() });
    publishStatus();
    topology(ctx);
    dev.timer = setInterval(() => {
      if (!dev.bridgeMqtt) return;
      tick += 1;
      if (tick % 2 === 0) uplink(ctx);
      if (tick % 3 === 0) publishStatus();
      if (tick % 6 === 0) topology(ctx);
    }, 3500);
  }

  async function boot(ctx, reason) {
    dev.bootAt = Date.now();
    await ctx.lines([
      "ESP-ROM:esp32s3-20210327", `GW boot reason=${reason}`,
      `GW_FIRMWARE version=${dev.cfg.firmwareVersion} protocol=${dev.cfg.protocolVersion}`,
      `GW_ID gatewayId=${hex(dev.cfg.gatewayId)}`, "GW_MESH_BEGIN_STATE=0",
      dev.cfg.wifi.configured ? `GW_WIFI_CONNECTED ssid=${dev.cfg.wifi.ssid} ip=${ip()} rssi=-58` : "GW_WIFI_NOT_CONFIGURED",
      dev.mqttUp ? `GW_MQTT_CONNECTED host=${dev.cfg.mqtt.host}:${dev.cfg.mqtt.port}` : "GW_MQTT_DISCONNECTED"
    ], 70);
  }

  function parseArgs(line) {
    const index = line.indexOf("{");
    if (index < 0) return {};
    try { return JSON.parse(line.slice(index)); } catch { return null; }
  }

  async function onCommand(line, ctx) {
    const name = line.split(/\s+/)[0].toUpperCase();
    const args = parseArgs(line);
    if (args === null) return ctx.line(ack(name.replace(/_JSON$/, ""), { status: "error", message: "invalid_json" }));
    switch (name) {
      case "GET_GATEWAY_ADDRESS": return ctx.line(`GW_GATEWAY_ADDRESS_JSON ${JSON.stringify({ gatewayId: hex(dev.cfg.gatewayId) })}`);
      case "GET_MESH_LORA": return ctx.line(`GW_MESH_LORA_JSON ${JSON.stringify(dev.cfg.meshLora)}`);
      case "GET_STATUS": return ctx.line(`GW_STATUS_JSON ${JSON.stringify(statusJson())}`);
      case "SET_WIFI_CONFIG_JSON":
        if (!String(args.ssid || "").trim()) return ctx.line(ack("SET_WIFI_CONFIG", { status: "error", message: "ssid_required" }));
        dev.cfg.wifi = { ssid: String(args.ssid), configured: true };
        dev.wifiUp = false;
        ctx.line(ack("SET_WIFI_CONFIG", { message: "saved" }));
        await ctx.sleep(900);
        dev.wifiUp = true;
        return ctx.line(`GW_WIFI_CONNECTED ssid=${dev.cfg.wifi.ssid} ip=${ip()} rssi=-58`);
      case "TEST_WIFI":
        await ctx.sleep(600);
        return ctx.line(ack("TEST_WIFI", { connected: dev.wifiUp ? 1 : 0, ip: ip(), ssid: dev.cfg.wifi.ssid, rssi: -58 }));
      case "SET_MQTT_CONFIG_JSON":
        if (!String(args.host || "").trim()) return ctx.line(ack("SET_MQTT_CONFIG", { status: "error", message: "host_required" }));
        dev.cfg.mqtt = { ...dev.cfg.mqtt, host: String(args.host), port: Number(args.port) || 1884, topicRoot: args.topicRoot || dev.cfg.mqtt.topicRoot, authConfigured: Boolean(args.username) };
        ctx.line(ack("SET_MQTT_CONFIG", { message: "saved" }));
        await ctx.sleep(700);
        dev.mqttUp = true;
        return ctx.line(`GW_MQTT_CONNECTED host=${dev.cfg.mqtt.host}:${dev.cfg.mqtt.port}`);
      case "SET_MESH_LORA_JSON": {
        const freq = Number(args.freqMHz);
        if (!(freq >= 920 && freq <= 923)) return ctx.line(ack(name, { status: "error", message: "freq_out_of_range" }));
        const { reboot, ...radio } = args;
        dev.cfg.meshLora = { ...dev.cfg.meshLora, ...radio };
        ctx.line(ack(name, { message: "saved", reboot: reboot ? 1 : 0 }));
        if (reboot) { await ctx.sleep(500); await boot(ctx, "radio-config"); }
        return ctx.line(`GW_MESH_LORA_JSON ${JSON.stringify(dev.cfg.meshLora)}`);
      }
      case "SET_GATEWAY_ADDRESS_JSON": {
        const value = parseInt(String(args.gatewayId || "").replace(/^0x/i, ""), 16);
        if (!(value >= 1 && value <= 0xf)) return ctx.line(ack(name, { status: "error", message: "gatewayId_out_of_range" }));
        const changed = value !== dev.cfg.gatewayId;
        dev.cfg.gatewayId = value;
        ctx.line(ack(name, { message: "saved", gatewayId: hex(value), reboot: changed ? 1 : 0 }));
        if (changed) { await ctx.sleep(300); await boot(ctx, "identity-change"); }
        return undefined;
      }
      case "RESTART":
        ctx.line(ack(name, { message: "restarting", reboot: 1 }));
        await ctx.sleep(500);
        return boot(ctx, "software-restart");
      default:
        return ctx.line(ack(name, { status: "error", message: "unknown_command" }));
    }
  }

  const mqttTopics = () => [`${dev.cfg.mqtt.topicRoot}/+/status`, `${dev.cfg.mqtt.topicRoot}/+/uplink`, `${dev.cfg.mqtt.topicRoot}/+/topology`];
  window.__expertDevice = {
    appId: "gw-operator",
    ports: [["COM3", "USB-SERIAL CH340 (COM3)", "wch.cn"], ["COM1", "Communications Port (COM1)", "(Standard port types)"]],
    packages: { gw: { firmwareVersion: "0.8.18" } },
    rejectPort: (port) => (port === "COM1" ? `${port} is a system port; no Gateway responded` : ""),
    health: () => ({ mqtt: { connected: dev.bridgeMqtt, host: dev.cfg.mqtt.host, port: dev.cfg.mqtt.port, topicRoot: dev.cfg.mqtt.topicRoot } }),
    async onConnect(ctx) { await boot(ctx, "usb-serial-open"); },
    onCommand,
    onFlashed({ resetNvs, version }) {
      if (resetNvs) { dev.cfg = DEFAULTS(); dev.cfg.wifi = { ssid: "", configured: false }; dev.wifiUp = false; dev.mqttUp = false; }
      dev.cfg.firmwareVersion = version;
    },
    routes: {
      "GET /api/wifi/current": () => ({ ssid: "PGL-BENCH", passwordAvailable: true, password: "mockup-wifi-pass" }),
      "GET /api/local-broker": () => ({ host: "192.168.1.10", port: 1884, username: "pgl-hub", password: "mockup-broker-pass", topicRoot: "gld/gateway" }),
      "POST /api/mqtt/test": async (body) => {
        await new Promise((r) => setTimeout(r, 400));
        return body.host ? { ok: true, latencyMs: 14, host: body.host, port: body.port } : { ok: false, message: "host is required" };
      },
      "POST /api/mqtt/connect": async (body) => {
        if (!body.host) throw Object.assign(new Error("host is required"), { status: 400 });
        const ctx = window.__expertDevice.ctx;
        dev.bridgeMqtt = true;
        if (body.topicRoot) dev.cfg.mqtt.topicRoot = body.topicRoot;
        setTimeout(() => {
          ctx.emit("mqtt_status", { connected: true, host: body.host, port: body.port, topicRoot: dev.cfg.mqtt.topicRoot, topics: mqttTopics() });
          startMqttFeed(ctx);
        }, 400);
        return { ok: true, connecting: true };
      },
      "POST /api/mqtt/disconnect": () => {
        dev.bridgeMqtt = false;
        clearInterval(dev.timer);
        window.__expertDevice.ctx.emit("mqtt_status", { connected: false, topics: [] });
        return { ok: true };
      },
      "POST /api/mqtt/publish/pull": (body) => publish("pull", body),
      "POST /api/mqtt/publish/node": (body) => publish("node", body)
    }
  };

  function publish(kind, body) {
    const ctx = window.__expertDevice.ctx;
    if (!dev.bridgeMqtt) throw Object.assign(new Error("MQTT is not connected"), { status: 409 });
    const topic = `${dev.cfg.mqtt.topicRoot}/${hex(dev.cfg.gatewayId)}/cmd/${kind}`;
    const payload = JSON.stringify(body);
    ctx.emit("mqtt_publish", { topic, payload });
    // The simulated mesh answers a pull with a cluster data response shortly after.
    setTimeout(() => uplink(ctx, kind === "pull" ? { requestId: body.requestId, srcId: body.cluster || "0x0066" } : { msgType: 0x21, typeFlags: 0x21 }), 1200);
    return { ok: true, topic, payload };
  }
})();
