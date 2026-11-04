/*
  Simulated Cluster Head firmware for the CH Operator mockup. Answers the
  serial commands the CH Operator sends with the firmware's line formats
  (CH_INFO_JSON, CH_STATUS_JSON, CH_CMD_ACK_JSON, CH_* log lines). Values are
  representative bench values, not live data.
*/
(() => {
  "use strict";
  const hex = (n) => `0x${n.toString(16).toUpperCase().padStart(4, "0")}`;
  const DEFAULTS = () => ({
    chId: "0066", rootGatewayId: "0001", firmwareVersion: "0.8.18", protocolVersion: "0.2.0", caps: "15",
    starLora: { freqMHz: 921.4, bwKHz: 125, sf: 9, cr: 5, syncWord: 0x12, txPowerDbm: 14 },
    meshLora: { freqMHz: 922.0, bwKHz: 125, sf: 9, cr: 5, syncWord: 0x34, txPowerDbm: 17 },
    helloProfile: { intervalMs: 15000, jitterMs: 2000, healthTimeoutMs: 45000 }
  });
  const dev = {
    cfg: DEFAULTS(), bootAt: Date.now(), state: "JOINED", parentId: "0065", backupParentId: "0064",
    batteryMv: 3920, seq: 40, timer: null, debug: false,
    nodes: [{ nodeId: "1A2B", seq: 40, alarm: false, extPower: true, unsent: 0, ageMs: 1200 },
      { nodeId: "1A2C", seq: 17, alarm: false, extPower: false, unsent: 1, ageMs: 8400 }]
  };
  // Parent candidates heard over MESH (CH2 = 0x0065, CH1 = 0x0064).
  const CANDIDATES = {
    "0065": { parent: "0x0064", depth: 1, rssi: -74, snr: 7.5, battMv: 4010, caps: 15 },
    "0064": { parent: "0x0001", depth: 0, rssi: -88, snr: 2.25, battMv: 3980, caps: 15 }
  };
  const candidateLine = (id) => {
    const c = CANDIDATES[id];
    return `CH_PARENT_CANDIDATE id=${hex(parseInt(id, 16))} parent=${c.parent} depth=${c.depth} rssi=${c.rssi} snr=${c.snr} battMv=${c.battMv} caps=${c.caps}`;
  };
  const uptime = () => Math.floor((Date.now() - dev.bootAt) / 1000);
  const json = (prefix, obj) => `${prefix} ${JSON.stringify(obj)}`;
  const ack = (cmd, status = "ok", message = "applied", extra = {}) => json("CH_CMD_ACK_JSON", { cmd, status, message, ...extra });
  const statusJson = () => json("CH_STATUS_JSON", {
    state: dev.state, batteryMv: dev.batteryMv, uptimeSec: uptime(), parentId: hex(parseInt(dev.parentId, 16)),
    parentRssi: CANDIDATES[dev.parentId].rssi, parentSnr: CANDIDATES[dev.parentId].snr, meshDepth: CANDIDATES[dev.parentId].depth + 1, nodeCount: dev.nodes.length
  });
  const infoJson = () => json("CH_INFO_JSON", {
    chId: hex(parseInt(dev.cfg.chId, 16)), rootGatewayId: hex(parseInt(dev.cfg.rootGatewayId, 16)),
    firmwareVersion: dev.cfg.firmwareVersion, protocolVersion: dev.cfg.protocolVersion, caps: dev.cfg.caps,
    starLora: dev.cfg.starLora, meshLora: dev.cfg.meshLora, helloProfile: dev.cfg.helloProfile
  });
  const parentsJson = () => json("CH_PARENTS_JSON", {
    active: hex(parseInt(dev.parentId, 16)),
    candidates: Object.keys(CANDIDATES).map((id) => ({ id: hex(parseInt(id, 16)), ...CANDIDATES[id] }))
  });

  async function boot(ctx, reason = "power-on") {
    dev.bootAt = Date.now();
    dev.state = "JOINING";
    await ctx.lines([
      "ESP-ROM:esp32s3-20210327", `CH boot reason=${reason}`,
      `Firmware version: ${dev.cfg.firmwareVersion}`, `Protocol version: ${dev.cfg.protocolVersion}`,
      `CH_IDS ch=${hex(parseInt(dev.cfg.chId, 16))} rootGateway=${hex(parseInt(dev.cfg.rootGatewayId, 16))}`,
      "CH_STAR_BEGIN_STATE=0", "CH_MESH_BEGIN_STATE=0", "CH_RUNTIME_READY star=1 mesh=1",
      `CH_ACK_PROFILE helloIntervalMs=${dev.cfg.helloProfile.intervalMs} helloJitterMs=${dev.cfg.helloProfile.jitterMs} healthTimeoutMs=${dev.cfg.helloProfile.healthTimeoutMs}`,
      `CH_BATT_MV=${dev.batteryMv} stableCount=16 threshold=3150`,
      "CH_STATE state=JOINING reason=boot", "CH_CONFIG_REQUEST_TX"
    ], 60);
    await ctx.sleep(700);
    await ctx.lines([
      candidateLine("0065"), candidateLine("0064"),
      `CH_PARENT_SELECT parent=${hex(parseInt(dev.parentId, 16))} backup=${hex(parseInt(dev.backupParentId, 16))} reason=best-rssi`,
      "CH_STATE state=JOINED reason=config-ack"
    ], 120);
    dev.state = "JOINED";
  }

  async function hello(ctx) {
    dev.batteryMv = 3900 + Math.round(Math.random() * 40);
    await ctx.lines([
      `CH_HELLO_TX parentId=${hex(parseInt(dev.parentId, 16))} battMv=${dev.batteryMv} uptimeSec=${uptime()} depth=${CANDIDATES[dev.parentId].depth + 1} caps=${dev.cfg.caps} ackWait=1`,
      "CH_HELLO_ACK_RECV"
    ], 350);
  }

  async function starRx(ctx) {
    const node = dev.nodes[0];
    node.seq = (node.seq + 1) % 256;
    await ctx.lines([
      `CH_STAR_RX node=0x${node.nodeId} rssi=${-60 - Math.round(Math.random() * 12)} snr=${(6 + Math.random() * 4).toFixed(1)} len=34`,
      `CH_CACHE_ENTRY node=0x${node.nodeId} seq=${node.seq} flags=0x00 alarm=0 extPwr=1 unsent=1 ageMs=0`,
      `CH_CACHE_SUMMARY used=${dev.nodes.length} capacity=32 unsent=1`
    ], 60);
  }

  function startRuntime(ctx) {
    clearInterval(dev.timer);
    let tick = 0;
    dev.timer = setInterval(() => {
      if (!ctx.slot.connected) return;
      tick += 1;
      if (tick % 3 === 0) starRx(ctx);
      if (tick % 5 === 0) hello(ctx);
      if (tick % 7 === 0) ctx.line(`CH_BATT_MV=${dev.batteryMv} stableCount=16 threshold=3150`);
    }, 2000);
  }

  function hexId(value) {
    const text = String(value ?? "").trim().toUpperCase().replace(/^0X/, "");
    return /^[0-9A-F]{1,4}$/.test(text) ? text.padStart(4, "0") : null;
  }
  function parseArgs(line) {
    const index = line.indexOf("{");
    if (index < 0) return {};
    try { return JSON.parse(line.slice(index)); } catch { return null; }
  }

  async function onCommand(line, ctx) {
    const [cmd] = line.split(/\s+/);
    const name = cmd.toUpperCase();
    const args = parseArgs(line);
    if (args === null) return ctx.line(ack(name, "error", "invalid JSON"));
    switch (name) {
      case "APP_PING": return ctx.line(ack("APP_PING", "ok", "pong", { app: "ch", uptimeSec: uptime() }));
      case "GET_INFO": return ctx.line(infoJson());
      case "GET_STATUS": return ctx.line(statusJson());
      case "GET_NODES": return ctx.line(json("CH_NODES_JSON", { nodes: dev.nodes.map((n) => ({ ...n, nodeId: `0x${n.nodeId}` })) }));
      case "GET_PARENTS": return ctx.line(parentsJson());
      case "SEND_HELLO": await hello(ctx); return ctx.line(ack("SEND_HELLO"));
      case "DEBUG_ON": case "DEBUG_OFF": dev.debug = name === "DEBUG_ON"; return ctx.line(ack(name, "ok", dev.debug ? "debug on" : "debug off"));
      case "CLEAR_PARENT_NVS":
        ctx.line(ack(name, "ok", "parent NVS cleared"));
        ctx.line("CH_STATE state=JOINING reason=parent-nvs-cleared");
        dev.state = "JOINING";
        await ctx.sleep(1500);
        ctx.line(`CH_PARENT_SELECT parent=${hex(parseInt(dev.parentId, 16))} backup=${hex(parseInt(dev.backupParentId, 16))} reason=rediscovery`);
        dev.state = "JOINED";
        return ctx.line("CH_STATE state=JOINED reason=config-ack");
      case "FORCE_FAILOVER":
        ctx.line(ack(name, "ok", "failover requested"));
        ctx.line("CH_STATE state=PARENT_FAILOVER reason=operator");
        dev.state = "PARENT_FAILOVER";
        [dev.parentId, dev.backupParentId] = [dev.backupParentId, dev.parentId];
        await ctx.sleep(1200);
        ctx.line(`CH_PARENT_SELECT parent=${hex(parseInt(dev.parentId, 16))} backup=${hex(parseInt(dev.backupParentId, 16))} reason=failover`);
        dev.state = "JOINED";
        ctx.line("CH_STATE state=JOINED reason=failover-complete");
        return ctx.line(statusJson());
      case "RESTART":
        ctx.line(ack(name, "ok", "restarting", { rebootExpected: true }));
        await ctx.sleep(600);
        return boot(ctx, "software-restart");
      case "SET_CH_ADDRESS_JSON": {
        const id = hexId(args.chId);
        if (!id || parseInt(id, 16) < 0x10 || parseInt(id, 16) > 0xfff) return ctx.line(ack(name, "error", "chId must be 0x0010-0x0FFF"));
        dev.cfg.chId = id;
        ctx.line(ack(name, "ok", `chId saved ${hex(parseInt(id, 16))}`, { rebootExpected: Boolean(args.reboot) }));
        if (args.reboot) { await ctx.sleep(500); await boot(ctx, "config-change"); ctx.line(infoJson()); }
        return undefined;
      }
      case "SET_ROOT_GATEWAY_JSON": {
        const id = hexId(args.gatewayId);
        if (!id || parseInt(id, 16) < 1 || parseInt(id, 16) > 0xf) return ctx.line(ack(name, "error", "gatewayId must be 0x0001-0x000F"));
        dev.cfg.rootGatewayId = id;
        ctx.line(ack(name, "ok", `rootGateway saved ${hex(parseInt(id, 16))}`, { rebootExpected: Boolean(args.reboot) }));
        if (args.reboot) { await ctx.sleep(500); await boot(ctx, "config-change"); }
        return ctx.line(infoJson());
      }
      case "SET_STAR_LORA_JSON": case "SET_MESH_LORA_JSON": {
        const freq = Number(args.freqMHz);
        if (!(freq >= 920 && freq <= 923)) return ctx.line(ack(name, "error", "freqMHz must be 920-923"));
        const key = name === "SET_STAR_LORA_JSON" ? "starLora" : "meshLora";
        dev.cfg[key] = { ...dev.cfg[key], ...args };
        delete dev.cfg[key].reboot;
        ctx.line(ack(name, "ok", `${key} saved`, { rebootExpected: Boolean(args.reboot) }));
        if (args.reboot) { await ctx.sleep(500); await boot(ctx, "radio-config"); }
        return ctx.line(infoJson());
      }
      default:
        return ctx.line(ack(name, "error", "unknown command"));
    }
  }

  window.__expertDevice = {
    appId: "ch-operator",
    ports: [["COM39", "USB-SERIAL CH340 (COM39)", "wch.cn"], ["COM38", "USB-SERIAL CH340 (COM38)", "wch.cn"], ["COM5", "USB-SERIAL CH340 (COM5)", "wch.cn"], ["COM1", "Communications Port (COM1)", "(Standard port types)"]],
    packages: { ch: { firmwareVersion: "0.8.18" }, chFieldtest: { firmwareVersion: "0.8.14" } },
    rejectPort: (port) => (port === "COM1" ? `${port} is a system port; no CH responded` : ""),
    async onConnect(ctx) {
      await boot(ctx, "usb-serial-open");
      startRuntime(ctx);
    },
    onDisconnect() { clearInterval(dev.timer); },
    onCommand,
    onFlashed({ env, resetNvs, targetDeviceId, version }) {
      if (resetNvs) dev.cfg = DEFAULTS();
      dev.cfg.firmwareVersion = version;
      const id = hexId(targetDeviceId);
      if (id) dev.cfg.chId = id;
      dev.flashedEnv = env;
    }
  };
})();
