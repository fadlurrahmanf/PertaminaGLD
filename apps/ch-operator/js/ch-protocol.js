// CH serial protocol: parse every line the ClusterHead emits and drive the
// UI from it. Two sources feed the same view:
//   1. The CH_* log stream the firmware already prints today (CH_CACHE_ENTRY,
//      CH_PARENT_CANDIDATE, CH_HELLO_TX, CH_STATE, CH_IDS, boot header ...).
//   2. Structured CH_*_JSON replies (CH_INFO_JSON / CH_STATUS_JSON /
//      CH_NODES_JSON / CH_PARENTS_JSON / CH_CMD_ACK_JSON) that arrive once the
//      CH firmware gains its serial command parser.
// The app is useful over the raw log stream alone, and gets richer when the
// JSON surface is present.

import { elements, state, DEFAULT_POLL_INTERVAL_MS, SERIAL_RESPONSE_TIMEOUT_MS, NODE_STALE_AFTER_MS, BATT_HISTORY_MAX } from "./ch-state.js";
import { appendLog, setBadge } from "./ch-ui.js";
import { writeSerialLine } from "./ch-bridge.js";

// ---- Parsing helpers -------------------------------------------------------

function parseKv(rest) {
  const out = {};
  for (const token of rest.trim().split(/\s+/)) {
    const eq = token.indexOf("=");
    if (eq > 0) out[token.slice(0, eq)] = token.slice(eq + 1);
  }
  return out;
}

function hex4(value) {
  if (value == null) return "";
  let s = String(value).trim();
  if (s.toLowerCase().startsWith("0x")) s = s.slice(2);
  if (/^[0-9a-fA-F]+$/.test(s)) return s.toUpperCase().padStart(4, "0");
  return s.toUpperCase();
}

function num(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function parseJsonAfter(prefix, line) {
  const idx = line.indexOf("{");
  if (idx < 0) return null;
  try {
    return JSON.parse(line.slice(idx));
  } catch {
    return null;
  }
}

// ---- Line dispatch ---------------------------------------------------------

export function handleLine(line) {
  if (line == null || line === "") return;
  appendLog(line, "in");

  if (line.startsWith("CH_INFO_JSON")) return applyInfoJson(parseJsonAfter("CH_INFO_JSON", line));
  if (line.startsWith("CH_STATUS_JSON")) return applyStatusJson(parseJsonAfter("CH_STATUS_JSON", line));
  if (line.startsWith("CH_NODES_JSON")) return applyNodesJson(parseJsonAfter("CH_NODES_JSON", line));
  if (line.startsWith("CH_PARENTS_JSON")) return applyParentsJson(parseJsonAfter("CH_PARENTS_JSON", line));
  if (line.startsWith("CH_CMD_ACK_JSON")) return applyCmdAck(parseJsonAfter("CH_CMD_ACK_JSON", line));

  // Raw CH_* log lines (present in the firmware today).
  // CH_STAR_RX carries the RSSI/SNR of whichever GLD frame the CH just
  // received, but the firmware's NodeCache never stores link quality per
  // node - the very next CH_CACHE_ENTRY line with ageMs=0 is that same
  // frame's node (STAR RX is processed one packet at a time, synchronously),
  // so we stash the reading here and attach it there.
  if (line.startsWith("CH_STAR_RX")) return applyStarRx(parseKv(line.slice("CH_STAR_RX".length)));
  if (line.startsWith("CH_CACHE_ENTRY")) return applyCacheEntry(parseKv(line.slice("CH_CACHE_ENTRY".length)));
  if (line.startsWith("CH_CACHE_SUMMARY")) return applyCacheSummary(parseKv(line.slice("CH_CACHE_SUMMARY".length)));
  if (line.startsWith("CH_CACHE_EXPIRED")) return applyCacheExpired(parseKv(line.slice("CH_CACHE_EXPIRED".length)));
  if (line.startsWith("CH_STATE")) return applyState(parseKv(line.slice("CH_STATE".length)));
  if (line.startsWith("CH_IDS")) return applyIds(parseKv(line.slice("CH_IDS".length)));
  if (line.startsWith("CH_HELLO_TX")) return applyHelloTx(parseKv(line.slice("CH_HELLO_TX".length)));
  if (line.startsWith("CH_HELLO_ACK_RECV")) return applyHelloAckRecv();
  if (line.startsWith("CH_HELLO_ACK_REPROBE")) return applyHelloAckReprobe(parseKv(line.slice("CH_HELLO_ACK_REPROBE".length)));
  if (line.startsWith("CH_CONFIG_REQUEST_TX")) return applyConfigRequestTx();
  if (line.startsWith("CH_ACK_PROFILE")) return applyAckProfile(parseKv(line.slice("CH_ACK_PROFILE".length)));
  if (line.startsWith("CH_PARENT_SELECT")) return applyParentSelect(parseKv(line.slice("CH_PARENT_SELECT".length)));
  if (line.startsWith("CH_PARENT_CANDIDATE") && !line.startsWith("CH_PARENT_CANDIDATE_REJECT")) {
    return applyParentCandidate(parseKv(line.slice("CH_PARENT_CANDIDATE".length)));
  }
  if (line.startsWith("CH_BATT_MV=")) return applyBattMv(line);
  if (line.startsWith("CH_ALARM_ACK_RECV")) return applyAlarmAck(parseKv(line.slice("CH_ALARM_ACK_RECV".length)));
  // Radio begin() outcome, printed once per boot per radio: 0 = RADIOLIB_ERR_NONE,
  // -2 = RADIOLIB_ERR_CHIP_NOT_FOUND (SPI didn't see the SX1262). The *_BEGIN_STATE
  // line is the final result after any TCXO->XTAL fallback, so it supersedes the
  // earlier *_BEGIN_TCXO16_STATE probe line.
  if (line.startsWith("CH_STAR_BEGIN_STATE=")) return applyRadioBegin("star", line);
  if (line.startsWith("CH_MESH_BEGIN_STATE=")) return applyRadioBegin("mesh", line);
  if (line.startsWith("CH_RUNTIME_READY")) return applyRuntimeReady(parseKv(line.slice("CH_RUNTIME_READY".length)));
  // MSG_SERVER_PULL_REQUEST handling: the Gateway (or an upstream CH relaying
  // one downstream) asked this CH for its cluster data. This CH only ever
  // reacts to a pull request over MESH - the serial console has no command
  // that originates one, since that is the Gateway's role, not an operator's.
  // CH_MESH_PARSE fires for every decoded MESH frame; only a pull-request
  // frame (msgType 0x30) starts the "processing" phase tracked below - it
  // marks the request as seen, then CH_PULL_RELAY (this CH is a mid-hop, not
  // the target) or CH_PULL_PROCESS (this CH serves it) resolves it moments
  // later once the firmware finishes building/queuing the reply.
  if (line.startsWith("CH_MESH_PARSE")) return applyMeshParse(parseKv(line.slice("CH_MESH_PARSE".length)));
  if (line.startsWith("CH_PULL_RELAY")) return applyPullRelay();
  if (line.startsWith("CH_PULL_PROCESS")) return applyPullProcess(parseKv(line.slice("CH_PULL_PROCESS".length)));
  if (line.startsWith("Firmware version:")) { state.info.firmwareVersion = line.split(":")[1]?.trim() || ""; return renderOverview(); }
  if (line.startsWith("Protocol version:")) { state.info.protocolVersion = line.split(":")[1]?.trim() || ""; return renderOverview(); }
}

// ---- Raw log line handlers -------------------------------------------------

// CH_CONFIG_REQUEST_TX is only sent (repeatedly, every CFG_REQUEST_INTERVAL_MS)
// while JOINING or PARENT_FAILOVER - see firmware/config/ChConfig.h. Fixed
// compile-time constant, not reported over serial, so it's mirrored here.
const CFG_REQUEST_INTERVAL_MS = 5000;

// helloIntervalMs() mirror from ChStarMeshRuntimeMain.cpp: a deterministic
// per-CH jitter added to the base interval, so the app's countdown can match
// the firmware's actual schedule instead of just the un-jittered base value.
function helloIntervalMsCalc() {
  const base = state.hello.intervalMs;
  const jitterMax = state.hello.jitterMs;
  if (!base) return null;
  if (!jitterMax) return base;
  const chIdNum = parseInt(state.info.chId, 16);
  if (!Number.isFinite(chIdNum)) return base;
  return base + ((chIdNum * 997) % jitterMax);
}

function applyState(kv) {
  if (kv.state) state.status.state = kv.state;
  if (kv.reason) state.status.stateReason = kv.reason;
  state.configSearch.active = kv.state === "JOINING" || kv.state === "PARENT_FAILOVER";
  renderOverview();
}

function applyIds(kv) {
  if (kv.ch) state.info.chId = hex4(kv.ch);
  if (kv.rootGateway) state.info.rootGatewayId = hex4(kv.rootGateway);
  renderOverview();
}

function applyAckProfile(kv) {
  if (kv.helloIntervalMs != null) state.hello.intervalMs = num(kv.helloIntervalMs);
  if (kv.helloJitterMs != null) state.hello.jitterMs = num(kv.helloJitterMs);
  renderOverview();
}

function applyHelloTx(kv) {
  if (kv.parentId) state.status.parentId = hex4(kv.parentId);
  if (kv.battMv != null) pushBattery(num(kv.battMv));
  if (kv.uptimeSec != null) state.status.uptimeSec = num(kv.uptimeSec);
  if (kv.depth != null) state.status.meshDepth = num(kv.depth);
  if (kv.caps) state.info.caps = kv.caps;
  state.hello.lastTxAt = Date.now();
  const interval = helloIntervalMsCalc();
  if (interval != null) state.hello.nextDueAt = state.hello.lastTxAt + interval;
  renderOverview();
}

function applyHelloAckRecv() {
  state.hello.failureCount = 0;
  renderOverview();
}

function applyHelloAckReprobe(kv) {
  state.hello.failureCount = num(kv.failure) ?? state.hello.failureCount;
  state.hello.threshold = num(kv.threshold) ?? state.hello.threshold;
  const dueInMs = num(kv.dueInMs);
  if (dueInMs != null) state.hello.nextDueAt = Date.now() + dueInMs;
  renderOverview();
}

function applyConfigRequestTx() {
  state.configSearch.active = true;
  state.configSearch.lastTxAt = Date.now();
  state.configSearch.nextDueAt = state.configSearch.lastTxAt + CFG_REQUEST_INTERVAL_MS;
  renderOverview();
}

function applyParentSelect(kv) {
  if (kv.parent) state.status.parentId = hex4(kv.parent);
  if (kv.parentRssi != null) state.status.parentRssi = num(kv.parentRssi);
  if (kv.parentSnr != null) state.status.parentSnr = num(kv.parentSnr);
  if (kv.parentDepth != null) state.status.meshDepth = num(kv.parentDepth);
  if (kv.parent && hex4(kv.parent) !== "0000") state.hello.failureCount = 0;
  markActiveParent();
  renderOverview();
}

function applyParentCandidate(kv) {
  const id = hex4(kv.id);
  if (!id) return;
  state.parents.set(id, {
    id,
    parent: hex4(kv.parent),
    depth: num(kv.depth),
    rssi: num(kv.rssi),
    snr: num(kv.snr),
    battMv: num(kv.battMv),
    caps: kv.caps || "",
    seenAt: Date.now()
  });
  markActiveParent();
  renderParents();
}

function applyBattMv(line) {
  // Line form: "CH_BATT_MV=1234 stableCount=.. threshold=.."
  const first = line.split(/\s+/)[0]; // CH_BATT_MV=1234
  const mv = num(first.split("=")[1]);
  if (mv != null) pushBattery(mv);
  renderOverview();
}

function applyAlarmAck(kv) {
  const id = hex4(kv.nodeId);
  const node = state.nodes.get(id);
  if (node) { node.alarm = true; renderNodes(); }
}

function applyRadioBegin(radio, line) {
  const code = num(line.split("=")[1]);
  state.status[`${radio}Begin`] = { code, ok: code === 0 };
  renderOverview();
}

function applyRuntimeReady(kv) {
  if (kv.star != null) state.status.starReady = kv.star === "1";
  if (kv.mesh != null) state.status.meshReady = kv.mesh === "1";
  renderOverview();
}

const MSG_SERVER_PULL_REQUEST = 0x30;
// A pull-request frame is logged by CH_MESH_PARSE before the firmware checks
// whether it's actually addressed to this CH - a mismatch prints
// CH_MESH_IGNORE dst=... reason=not-local instead of ever reaching
// CH_PULL_RELAY/CH_PULL_PROCESS. Without this timeout the Overview/Mesh
// cards would show "Processing..." forever for a request meant for a
// different CH on the same channel.
const PULL_PROCESSING_TIMEOUT_MS = 5000;

function applyMeshParse(kv) {
  const typeFlags = Number(kv.typeFlags);
  if (!Number.isFinite(typeFlags) || (typeFlags & 0x3F) !== MSG_SERVER_PULL_REQUEST) return;
  if (state.lastPull?.processingTimer) clearTimeout(state.lastPull.processingTimer);
  const pull = {
    phase: "processing",
    relayedOnly: false,
    requestId: null, status: null, dataStatus: null, records: null,
    responseSize: null, onwardQueued: null,
    requestedAt: Date.now(), respondedAt: null,
    processingTimer: null
  };
  pull.processingTimer = setTimeout(() => {
    if (state.lastPull === pull && pull.phase === "processing") {
      pull.phase = "done";
      pull.status = "NotForThisCh";
      pull.respondedAt = Date.now();
      renderPullRequest();
      renderOverview();
    }
  }, PULL_PROCESSING_TIMEOUT_MS);
  state.lastPull = pull;
  renderPullRequest();
  renderOverview();
}

function applyPullRelay() {
  if (!state.lastPull) state.lastPull = { requestedAt: Date.now() };
  if (state.lastPull.processingTimer) clearTimeout(state.lastPull.processingTimer);
  state.lastPull.phase = "done";
  state.lastPull.relayedOnly = true;
  state.lastPull.respondedAt = Date.now();
  renderPullRequest();
  renderOverview();
}

function applyPullProcess(kv) {
  if (!state.lastPull) state.lastPull = { requestedAt: Date.now() };
  if (state.lastPull.processingTimer) clearTimeout(state.lastPull.processingTimer);
  state.lastPull.phase = "done";
  state.lastPull.relayedOnly = false;
  state.lastPull.requestId = kv.requestId;
  state.lastPull.status = kv.status;
  state.lastPull.dataStatus = kv.dataStatus;
  state.lastPull.records = num(kv.records);
  state.lastPull.responseSize = num(kv.responseSize);
  state.lastPull.onwardQueued = kv.onwardQueued === "1";
  state.lastPull.respondedAt = Date.now();
  renderPullRequest();
  renderOverview();
}

function applyCacheSummary(kv) {
  state.status.nodeUsed = num(kv.used);
  state.status.nodeUnsent = (num(kv.unsentNormal) || 0) + (num(kv.unsentAlarm) || 0);
  renderOverview();
}

function applyStarRx(kv) {
  const rssi = num(kv.rssi);
  const snr = num(kv.snr);
  // Single-use: only the next ageMs=0 CH_CACHE_ENTRY may consume this.
  state.pendingStarSample = { rssi, snr };
}

function applyCacheEntry(kv) {
  const id = hex4(kv.node);
  if (!id) return;
  const ageMs = num(kv.ageMs) || 0;
  const existing = state.nodes.get(id);
  const entry = {
    nodeId: id,
    seq: num(kv.seq),
    alarm: kv.alarm === "1",
    extPower: kv.extPwr === "1",
    unsent: num(kv.unsent),
    flags: kv.flags || "",
    seenAt: Date.now() - ageMs,
    // Not stored by the firmware's NodeCache - app-side only, display
    // purposes: carry the last known reading forward until a fresher one
    // arrives, since a node the CH already knows about but hasn't just
    // retransmitted has no new sample to attach.
    rssi: existing?.rssi ?? null,
    snr: existing?.snr ?? null
  };
  if (ageMs === 0 && state.pendingStarSample) {
    entry.rssi = state.pendingStarSample.rssi;
    entry.snr = state.pendingStarSample.snr;
    state.pendingStarSample = null;
  }
  state.nodes.set(id, entry);
  renderNodes();
  renderOverview();
}

function applyCacheExpired(kv) {
  const id = hex4(kv.node);
  if (id && state.nodes.delete(id)) { renderNodes(); renderOverview(); }
}

// ---- JSON reply handlers (available once CH parser lands) -------------------

function applyInfoJson(json) {
  if (!json) return;
  if (json.chId) state.info.chId = hex4(json.chId);
  if (json.rootGatewayId) state.info.rootGatewayId = hex4(json.rootGatewayId);
  if (json.firmwareVersion) state.info.firmwareVersion = json.firmwareVersion;
  if (json.protocolVersion) state.info.protocolVersion = json.protocolVersion;
  if (json.caps != null) state.info.caps = String(json.caps);
  state.info.starLora = json.starLora || state.info.starLora;
  state.info.meshLora = json.meshLora || state.info.meshLora;
  renderOverview();
}

function applyStatusJson(json) {
  if (!json) return;
  const s = state.status;
  if (json.state) s.state = json.state;
  if (json.batteryMv != null) pushBattery(num(json.batteryMv));
  if (json.uptimeSec != null) s.uptimeSec = num(json.uptimeSec);
  if (json.parentId) s.parentId = hex4(json.parentId);
  if (json.parentRssi != null) s.parentRssi = num(json.parentRssi);
  if (json.parentSnr != null) s.parentSnr = num(json.parentSnr);
  if (json.meshDepth != null) s.meshDepth = num(json.meshDepth);
  if (json.nodeCount != null) s.nodeUsed = num(json.nodeCount);
  renderOverview();
}

function applyNodesJson(json) {
  if (!json || !Array.isArray(json.nodes)) return;
  state.nodes.clear();
  for (const n of json.nodes) {
    const id = hex4(n.nodeId);
    if (!id) continue;
    state.nodes.set(id, {
      nodeId: id,
      seq: num(n.seq),
      alarm: Boolean(n.alarm),
      extPower: Boolean(n.extPower),
      unsent: num(n.unsent),
      seenAt: Date.now() - (num(n.ageMs) || 0)
    });
  }
  renderNodes();
  renderOverview();
}

function applyParentsJson(json) {
  if (!json || !Array.isArray(json.candidates)) return;
  state.parents.clear();
  for (const c of json.candidates) {
    const id = hex4(c.id);
    if (!id) continue;
    state.parents.set(id, {
      id, parent: hex4(c.parent), depth: num(c.depth), rssi: num(c.rssi),
      snr: num(c.snr), battMv: num(c.battMv), caps: String(c.caps ?? ""), seenAt: Date.now()
    });
  }
  if (json.active) state.status.parentId = hex4(json.active);
  markActiveParent();
  renderParents();
}

function applyCmdAck(json) {
  if (!json) return;
  const pending = state.pendingAck;
  if (pending && (!pending.cmd || String(json.cmd).toUpperCase() === pending.cmd)) {
    clearTimeout(pending.timer);
    state.pendingAck = null;
    pending.resolve(json);
  }
}

// ---- Derived state ---------------------------------------------------------

function markActiveParent() {
  const active = state.status.parentId;
  for (const p of state.parents.values()) p.active = active && p.id === active;
}

function pushBattery(mv) {
  if (mv == null) return;
  state.status.batteryMv = mv;
  state.battHistory.push({ mv, t: Date.now() });
  if (state.battHistory.length > BATT_HISTORY_MAX) state.battHistory.shift();
}

// ---- Rendering -------------------------------------------------------------

function fmtAge(ms) {
  if (ms == null) return "—";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s ago`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m ago`;
}

function fmtUptime(sec) {
  if (sec == null) return "—";
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (d) return `${d}d ${h}h ${m}m`;
  if (h) return `${h}h ${m}m`;
  return `${m}m ${sec % 60}s`;
}

export function renderOverview() {
  const { info, status } = state;
  const set = (id, v) => { if (elements[id]) elements[id].textContent = v ?? "—"; };
  set("ovState", status.state || "—");
  set("ovStateReason", status.stateReason || "waiting");
  set("ovBatt", status.batteryMv != null ? status.batteryMv : "—");
  set("ovUptime", fmtUptime(status.uptimeSec));
  set("ovNodeCount", state.nodes.size || status.nodeUsed || 0);
  set("ovNodeUnsent", `${status.nodeUnsent || 0} unsent`);
  set("ovChId", info.chId ? `0x${info.chId}` : "—");
  set("ovRootGw", info.rootGatewayId ? `0x${info.rootGatewayId}` : "—");
  set("ovFirmware", info.firmwareVersion || "—");
  set("ovProtocol", info.protocolVersion || "—");
  set("ovCaps", info.caps || "—");
  set("ovParent", status.parentId ? `0x${status.parentId}` : "—");
  set("ovParentRssi", status.parentRssi != null ? `${status.parentRssi} dBm` : "—");
  set("ovParentSnr", status.parentSnr != null ? `${status.parentSnr} dB` : "—");
  set("ovDepth", status.meshDepth != null ? status.meshDepth : "—");

  setBadge(elements.chIdBadge, info.chId ? `0x${info.chId}` : "—");
  setBadge(elements.stateBadge, status.state || "—");
  setBadge(elements.parentBadge, status.parentId ? `0x${status.parentId}` : "—");
  const mv = status.batteryMv;
  setBadge(elements.battBadge, mv != null ? `${mv} mV` : "—", mv != null && mv < 3150 ? "warn" : "");
  renderRadioCard("star", info.starLora, status.starBegin, status.starReady);
  renderRadioCard("mesh", info.meshLora, status.meshBegin, status.meshReady);
  renderOverviewPull();
  renderHelloConfigTimers();
  drawBattChart();
}

function fmtCountdown(dueAt) {
  if (dueAt == null) return null;
  const remaining = dueAt - Date.now();
  if (remaining <= 0) return "due now";
  const s = Math.ceil(remaining / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

function renderHelloConfigTimers() {
  const set = (id, v) => { if (elements[id]) elements[id].textContent = v ?? "—"; };
  const hello = state.hello;
  set("ovHelloCountdown", hello.lastTxAt == null ? "no hello seen yet" : (fmtCountdown(hello.nextDueAt) ?? "—"));
  set("ovHelloFailures", hello.threshold != null ? `${hello.failureCount} / ${hello.threshold}` : `${hello.failureCount}`);

  const cfg = state.configSearch;
  if (!cfg.active) {
    set("ovConfigCountdown", state.status.state === "JOINED" ? "not searching (CH is JOINED)" : "not searching");
  } else {
    set("ovConfigCountdown", cfg.lastTxAt == null ? "starting…" : (fmtCountdown(cfg.nextDueAt) ?? "—"));
  }
}

// RadioLib error code -> label. Only codes this firmware is known to hit are
// named; anything else still shows the raw numeric code instead of a guess.
function radioLibCodeLabel(code) {
  if (code === 0) return "NONE";
  if (code === -2) return "CHIP_NOT_FOUND";
  return String(code);
}

function renderRadioCard(radio, lora, begin, ready) {
  const set = (id, v) => { if (elements[id]) elements[id].textContent = v ?? "—"; };
  const statusEl = elements[`${radio}BeginStatus`];
  if (statusEl) {
    if (begin == null) {
      statusEl.textContent = "no data yet";
    } else if (begin.ok) {
      statusEl.innerHTML = `<span class="pill fresh">OK</span>${ready === false ? " (not ready)" : ""}`;
    } else {
      statusEl.innerHTML = `<span class="pill on">FAILED</span> code=${begin.code} (${radioLibCodeLabel(begin.code)})`;
    }
  }
  if (lora) {
    set(`${radio}FreqValue`, `${lora.freqMHz} MHz`);
    set(`${radio}BwSfCr`, `${lora.bwKHz} kHz / SF${lora.sf} / CR 4/${lora.cr}`);
    set(`${radio}SyncValue`, lora.syncWord != null ? `0x${Number(lora.syncWord).toString(16)}` : "—");
  } else {
    set(`${radio}FreqValue`, "—");
    set(`${radio}BwSfCr`, "—");
    set(`${radio}SyncValue`, "—");
  }
}

export function renderNodes() {
  const body = elements.nodesBody;
  if (!body) return;
  const rows = Array.from(state.nodes.values()).sort((a, b) => a.nodeId.localeCompare(b.nodeId));
  if (!rows.length) {
    body.innerHTML = `<tr><td class="empty" colspan="8">No GLD nodes seen yet. Connect to the CH and wait for STAR uplinks (or run GET_NODES).</td></tr>`;
    return;
  }
  const now = Date.now();
  body.innerHTML = rows.map((n) => {
    const age = now - n.seenAt;
    const stale = age > NODE_STALE_AFTER_MS;
    const rowClass = n.alarm ? "alarm" : (stale ? "stale" : "");
    const power = n.extPower
      ? `<span class="pill ext">Ext</span>`
      : `<span class="pill battery">Battery</span>`;
    const alarm = n.alarm
      ? `<span class="dot dot-alarm" title="ALARM"></span>`
      : `<span class="dot dot-ok" title="No alarm"></span>`;
    const unsent = (n.unsent ?? 0) > 0 ? `<span class="pill unsend">UNSEND</span>` : "—";
    const fresh = stale ? `<span class="pill stale">stale</span>` : `<span class="pill fresh">fresh</span>`;
    return `<tr class="${rowClass}">
      <td>0x${n.nodeId}</td>
      <td>${alarm}</td>
      <td>${power}</td>
      <td>${unsent}</td>
      <td>${n.rssi != null ? `${n.rssi} dBm` : "—"}</td>
      <td>${n.snr != null ? `${n.snr} dB` : "—"}</td>
      <td>${fmtAge(age)}</td>
      <td>${fresh}</td>
    </tr>`;
  }).join("");
}

export function renderParents() {
  const body = elements.parentsBody;
  if (!body) return;
  const rows = Array.from(state.parents.values()).sort((a, b) => (b.rssi ?? -999) - (a.rssi ?? -999));
  if (!rows.length) {
    body.innerHTML = `<tr><td class="empty" colspan="8">No parent candidates heard yet.</td></tr>`;
    return;
  }
  body.innerHTML = rows.map((p) => `<tr>
    <td>0x${p.id}</td>
    <td>${p.parent ? `0x${p.parent}` : "—"}</td>
    <td>${p.depth ?? "—"}</td>
    <td>${p.rssi != null ? p.rssi : "—"}</td>
    <td>${p.snr != null ? p.snr : "—"}</td>
    <td>${p.battMv != null && p.battMv !== 65535 ? p.battMv : "—"}</td>
    <td>${p.caps || "—"}</td>
    <td>${p.active ? `<span class="pill on">active</span>` : ""}</td>
  </tr>`).join("");
}

const PULL_STATUS_LABELS = { NotForThisCh: "not addressed to this CH (ignored)" };

// Shared "how much GLD data did this CH actually send" summary, used by both
// the Mesh/Parent detail card and the Overview summary card.
function describePullData(pull) {
  if (!pull) return "No pull request seen yet";
  if (pull.phase === "processing") return "Processing...";
  if (pull.status === "NotForThisCh") return "Not addressed to this CH - no response sent";
  if (pull.relayedOnly) return "Relayed to another CH - this CH did not send its own GLD data";
  if (pull.dataStatus === "DataOk") {
    const n = pull.records ?? 0;
    return `${n} GLD record${n === 1 ? "" : "s"} sent (${pull.responseSize ?? "—"} bytes)`;
  }
  if (pull.dataStatus === "DataEmpty") return "No GLD data available - sent empty response";
  if (pull.dataStatus) return `Not sent (${pull.dataStatus})`;
  return "—";
}

export function renderPullRequest() {
  const set = (id, v) => { if (elements[id]) elements[id].textContent = v ?? "—"; };
  const pull = state.lastPull;
  if (!pull) {
    set("pullSeenAt", "no request seen yet");
    set("pullRequestId", "—"); set("pullStatus", "—"); set("pullDataStatus", "—");
    set("pullRecords", "—"); set("pullOnwardQueued", "—");
    return;
  }
  set("pullSeenAt", fmtAge(Date.now() - pull.requestedAt));
  if (pull.phase === "processing") {
    set("pullRequestId", "—");
    set("pullStatus", "Processing...");
    set("pullDataStatus", "—");
    set("pullRecords", "—");
    set("pullOnwardQueued", "—");
    return;
  }
  set("pullRequestId", pull.relayedOnly || pull.status === "NotForThisCh" ? "—" : (pull.requestId ?? "—"));
  set("pullStatus", pull.relayedOnly ? "Relayed (not served locally)" : (PULL_STATUS_LABELS[pull.status] || pull.status || "—"));
  set("pullDataStatus", pull.relayedOnly || pull.status === "NotForThisCh" ? "—" : (pull.dataStatus || "—"));
  set("pullRecords", describePullData(pull));
  set("pullOnwardQueued", pull.status === "NotForThisCh" ? "—" : (pull.relayedOnly ? "yes (relayed downstream)" : (pull.onwardQueued ? "yes" : "no")));
}

function setStep(id, stepState) {
  const el = elements[id];
  if (!el) return;
  el.classList.remove("pending", "active", "done", "skipped");
  el.classList.add(stepState);
}

// Drives the 3-step tracker: 1) request received (CH_MESH_PARSE saw a pull
// request), 2) processing (firmware building/relaying the reply),
// 3) response delivered - either sent to the parent, relayed downstream to
// another CH, or skipped if the request turned out not to be for this CH.
function renderOverviewPull() {
  const set = (id, v) => { if (elements[id]) elements[id].textContent = v ?? "—"; };
  const pull = state.lastPull;
  set("ovPullRequested", pull ? fmtAge(Date.now() - pull.requestedAt) : "never");
  set("ovPullData", describePullData(pull));
  set("pullStep3Label", "Response sent");

  if (!pull) {
    setStep("pullStep1", "pending");
    setStep("pullStep2", "pending");
    setStep("pullStep3", "pending");
    return;
  }
  if (pull.phase === "processing") {
    setStep("pullStep1", "done");
    setStep("pullStep2", "active");
    setStep("pullStep3", "pending");
    return;
  }
  setStep("pullStep1", "done");
  if (pull.status === "NotForThisCh") {
    setStep("pullStep2", "skipped");
    setStep("pullStep3", "skipped");
    set("pullStep3Label", "Not for this CH");
    return;
  }
  setStep("pullStep2", "done");
  setStep("pullStep3", "done");
  set("pullStep3Label", pull.relayedOnly ? "Relayed downstream" : "Response sent");
}

function drawBattChart() {
  const canvas = elements.battChart;
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width = canvas.clientWidth || 600;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  const data = state.battHistory;
  if (data.length < 2) return;
  const vals = data.map((d) => d.mv);
  const min = Math.min(...vals, 3000);
  const max = Math.max(...vals, 4200);
  const range = max - min || 1;
  const accent = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#e0630f";
  ctx.strokeStyle = accent;
  ctx.lineWidth = 2;
  ctx.beginPath();
  data.forEach((d, i) => {
    const x = (i / (data.length - 1)) * (w - 8) + 4;
    const y = h - 6 - ((d.mv - min) / range) * (h - 12);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
}

// Re-render node ages and the hello/config countdowns on a ticker, so they
// count down live instead of only updating when a new log line arrives.
export function tickAges() {
  if (state.nodes.size) renderNodes();
  renderHelloConfigTimers();
}

// ---- Command sending -------------------------------------------------------

export async function sendCommand(cmd) {
  const line = String(cmd || "").trim();
  if (!line) return;
  if (!state.connected) {
    appendLog(`CMD_SKIPPED not connected: ${line}`, "err");
    return;
  }
  try {
    await writeSerialLine(line);
  } catch (error) {
    appendLog(`CMD_ERROR ${error.message}`, "err");
  }
}

// Send a command and resolve when its CH_CMD_ACK_JSON arrives (or time out).
export function sendCommandAndWaitAck(cmd, ackCmd) {
  return new Promise(async (resolve, reject) => {
    if (state.pendingAck) {
      clearTimeout(state.pendingAck.timer);
      state.pendingAck.reject(new Error("superseded by a newer command"));
    }
    const timer = setTimeout(() => {
      if (state.pendingAck && state.pendingAck.resolve === resolve) state.pendingAck = null;
      reject(new Error(`timed out waiting for ack to ${ackCmd || cmd}`));
    }, SERIAL_RESPONSE_TIMEOUT_MS);
    state.pendingAck = { cmd: String(ackCmd || cmd.split(/\s+/)[0]).toUpperCase(), resolve, reject, timer };
    await sendCommand(cmd);
  });
}

export function resetDeviceSnapshot() {
  state.info = { chId: "", rootGatewayId: "", firmwareVersion: "", protocolVersion: "", caps: "" };
  state.status = { state: "", stateReason: "", batteryMv: null, uptimeSec: null, parentId: "", parentRssi: null, parentSnr: null, meshDepth: null };
  state.nodes.clear();
  state.parents.clear();
  state.battHistory = [];
  state.pendingStarSample = null;
  state.hello = { lastTxAt: null, nextDueAt: null, intervalMs: null, jitterMs: null, failureCount: 0, threshold: null };
  state.configSearch = { lastTxAt: null, nextDueAt: null, active: false };
  if (state.lastPull?.processingTimer) clearTimeout(state.lastPull.processingTimer);
  state.lastPull = null;
  renderOverview();
  renderNodes();
  renderParents();
  renderPullRequest();
}

// ---- Polling ---------------------------------------------------------------

export function togglePolling() {
  if (state.polling) stopPolling();
  else startPolling();
}

export function startPolling() {
  if (!state.connected) return;
  stopPolling();
  state.polling = true;
  elements.pollToggleBtn.textContent = "Stop polling";
  state.pollTimer = setInterval(() => {
    sendCommand("GET_STATUS");
    sendCommand("GET_NODES");
  }, DEFAULT_POLL_INTERVAL_MS);
}

export function stopPolling() {
  state.polling = false;
  clearInterval(state.pollTimer);
  state.pollTimer = null;
  if (elements.pollToggleBtn) elements.pollToggleBtn.textContent = "Start polling";
}
