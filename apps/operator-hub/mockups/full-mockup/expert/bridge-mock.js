/*
  Generic local-bridge simulation for the Expert Console mockups (GLD, CH and
  Gateway Operator). It replaces fetch() for /api/* and EventSource before the
  unchanged operator app loads. A device emulator registered earlier as
  window.__expertDevice answers serial commands with the firmware's own line
  formats, so the real app parses and renders them exactly as on hardware.
  Nothing here opens a COM port, reaches the network or flashes firmware.
*/
(() => {
  "use strict";
  const device = window.__expertDevice || {};
  const TOKEN = "mockup-bridge-token";
  const slot = { connected: false, port: null };
  const sources = new Set();
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function emit(type, payload) {
    sources.forEach((source) => source._dispatch(type, payload));
  }
  const ctx = {
    emit, sleep, slot,
    line(text) { if (slot.connected) emit("serial_line", { slot: 1, line: text }); },
    async lines(list, gap = 70) {
      for (const text of list) { ctx.line(text); await sleep(gap); }
    },
    setConnected(connected, port = slot.port) {
      slot.connected = connected;
      slot.port = port;
      emit("serial_status", { slot: 1, connected, port });
    }
  };
  device.ctx = ctx;

  class MockEventSource {
    constructor(url) {
      this.url = String(url);
      this.readyState = 0;
      this.listeners = {};
      this.onopen = null;
      this.onerror = null;
      this.onmessage = null;
      sources.add(this);
      setTimeout(() => { this.readyState = 1; this._dispatch("open", null); }, 60);
    }
    addEventListener(type, handler, options) { (this.listeners[type] ||= []).push({ handler, once: Boolean(options?.once) }); }
    removeEventListener(type, handler) { this.listeners[type] = (this.listeners[type] || []).filter((x) => x.handler !== handler); }
    _dispatch(type, payload) {
      if (this.readyState === 2) return;
      const event = { type, data: payload == null ? "" : JSON.stringify(payload), lastEventId: "" };
      const property = this[`on${type}`];
      if (typeof property === "function") property.call(this, event);
      (this.listeners[type] || []).slice().forEach((item) => {
        if (item.once) this.removeEventListener(type, item.handler);
        item.handler.call(this, event);
      });
    }
    close() { this.readyState = 2; sources.delete(this); }
  }

  const PORTS = device.ports || [["COM3", "USB-SERIAL CH340 (COM3)", "wch.cn"]];
  // Real manifests are embedded at build time (metadata only, no binaries).
  const manifests = window.__mockManifests || {};
  const packages = { ...(device.packages || {}) };
  Object.entries(manifests).forEach(([env, manifest]) => { packages[env] = { firmwareVersion: manifest.firmwareVersion }; });

  async function upload(body) {
    const port = String(body.port || "").toUpperCase();
    if (!/^COM\d+$/.test(port)) throw Object.assign(new Error("valid COM port required"), { status: 400 });
    const env = body.env || Object.keys(packages)[0];
    const pack = packages[env];
    if (!pack) throw Object.assign(new Error(`package ${env} not available`), { status: 400 });
    if (slot.connected) ctx.setConnected(false);
    emit("upload_start", { cmd: `esptool --port ${port} write_flash (${env})` });
    const steps = ["esptool.py v4.7.0", `Serial port ${port}`, "Connecting....", "Chip is ESP32-S3 (QFN56) (revision v0.2)",
      "Uploading stub...", "Changing baud rate to 921600", "Configuring flash size..."];
    if (body.resetNvs) steps.push("Erasing NVS partition 0x9000 (0x5000 bytes)...");
    for (const text of steps) { emit("upload_line", { line: text }); await sleep(160); }
    for (let percent = 4; percent <= 100; percent += 8) {
      emit("upload_progress", { filePercent: percent, packagePercent: percent });
      emit("upload_line", { line: `Writing at 0x${(0x10000 + percent * 0x3a00).toString(16).padStart(8, "0")}... (${percent} %)` });
      await sleep(110);
    }
    emit("upload_line", { line: "Hash of data verified." });
    emit("upload_line", { line: "Hard resetting via RTS pin..." });
    emit("upload_done", { code: 0 });
    device.onFlashed?.({ env, resetNvs: Boolean(body.resetNvs), targetDeviceId: body.targetDeviceId, version: pack.firmwareVersion });
    await sleep(500);
    return { ok: true, env, port, firmwareVersion: pack.firmwareVersion, nvsReset: Boolean(body.resetNvs), verified: true };
  }

  const routes = {
    "GET /api/health": () => ({
      ok: true, version: "mockup", appId: device.appId, csrfToken: TOKEN,
      features: { serial: true, mqtt: true, upload: true, ...(device.features || {}) },
      slots: { 1: { connected: slot.connected, port: slot.port } }, errors: {},
      mqttBroker: { host: "127.0.0.1", port: 1884 }, ...(device.health?.() || {})
    }),
    "GET /api/ports": () => ({ ports: PORTS.map(([path, description, manufacturer]) => ({ path, description, manufacturer: manufacturer || "" })) }),
    "GET /api/serial/status": () => ({ connected: slot.connected, port: slot.port, slot: 1 }),
    "GET /api/serial/recent": () => ({ sequence: 0, lines: [] }),
    "GET /api/serial/port-status": (_body, query) => ({ port: query.get("port"), free: !(slot.connected && slot.port === query.get("port")), message: slot.connected && slot.port === query.get("port") ? "open in this console (mockup)" : "not opened by another program (mockup)" }),
    "POST /api/serial/connect": async (body) => {
      const port = String(body.port || "").toUpperCase();
      if (!/^COM\d+$/.test(port)) throw Object.assign(new Error("valid COM port required"), { status: 400 });
      if (device.rejectPort?.(port)) throw Object.assign(new Error(device.rejectPort(port)), { status: 409 });
      await sleep(250);
      ctx.setConnected(true, port);
      setTimeout(() => device.onConnect?.(ctx), 150);
      return { ok: true, connected: true, port, slot: 1, baud: body.baud || 115200 };
    },
    "POST /api/serial/disconnect": async () => {
      const port = slot.port;
      if (slot.connected) ctx.setConnected(false, port);
      device.onDisconnect?.(ctx);
      return { ok: true, connected: false, port };
    },
    "POST /api/serial/write": async (body) => {
      if (!slot.connected) throw Object.assign(new Error("serial port is not connected"), { status: 409 });
      const line = String(body.line || "").trim();
      emit("serial_tx", { slot: 1, line });
      setTimeout(() => device.onCommand?.(line, ctx), 80);
      return { ok: true, written: line.length + 1 };
    },
    "GET /api/firmware/package": (_body, query) => {
      const env = query.get("env");
      const pack = packages[env];
      if (!pack) throw Object.assign(new Error(`package ${env} not found`), { status: 404 });
      const manifest = manifests[env] || {
        schemaVersion: 2, packageType: "pertamina-gld-prebuilt-firmware", deviceId: "ANY", environment: env,
        firmwareVersion: pack.firmwareVersion, protocolVersion: "0.2.0", chip: "esp32s3",
        flashFiles: [{ path: "firmware.bin", offset: "0x00010000", size: 0, sha256: "" }]
      };
      // Binaries are not embedded in the mockup; the simulated flash never reads them.
      const packageFiles = Object.fromEntries((manifest.flashFiles || []).map((item) => [item.path, "TU9DS1VQ"]));
      return { manifest, packageFiles };
    },
    "POST /api/firmware/upload": upload,
    "POST /api/session/log": () => ({ ok: true, path: "(mockup) log tidak disimpan ke disk" }),
    ...(device.routes || {})
  };

  const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
  const realFetch = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    const raw = typeof input === "string" ? input : input?.url;
    const url = new URL(String(raw), "http://127.0.0.1/");
    if (!url.pathname.startsWith("/api/")) return realFetch(input, init);
    const method = String(init.method || "GET").toUpperCase();
    const route = routes[`${method} ${url.pathname}`];
    let body = {};
    try { body = init.body ? JSON.parse(init.body) : {}; } catch { body = {}; }
    if (!route) {
      console.info(`[mockup] ${method} ${url.pathname} tidak disimulasikan; respons generik.`);
      return method === "GET" ? json({ error: `mockup: ${url.pathname} tidak tersedia di mockup` }, 404) : json({ ok: true, mockup: true });
    }
    try {
      return json(await route(body, url.searchParams));
    } catch (error) {
      return json({ error: error.message }, error.status || 500);
    }
  };
  window.EventSource = MockEventSource;
})();
