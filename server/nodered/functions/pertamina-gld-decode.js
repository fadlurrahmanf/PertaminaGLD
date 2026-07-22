const GAS_CLASS = {
    0: "clearGas",
    1: "LPG",
    2: "methane",
    3: "propane",
    4: "butane",
    5: "reserve",
    6: "anomaly"
};

const MSG_SENSOR_DATA = 0x10;
const MSG_SERVER_PULL_REQUEST = 0x30;
const MSG_CLUSTER_DATA_RESPONSE = 0x31;
const MSG_CH_HELLO = 0x33;
const MSG_MESH_CONTROL_MIN = 0x30;
const MSG_MESH_CONTROL_MAX = 0x3F;
const MSG_TYPE_MASK = 0x3F;
const FLAG_ALARM_ACK = 0x40;
const FLAG_GLD_EXT_POWER = 0x80;
const NC_FLAG_ALARM = 0x01;
const NC_FLAG_EXT_POWER = 0x10;
const GLD_ENCRYPTED_LEN = 29;
const GLD_RECORD_LEN = 34;
const DEFAULT_GATEWAY_ID = 0x006F;
const REPLAY_WINDOW_BITS = 32;
const REPLAY_STATE_TTL_MS = 24 * 60 * 60 * 1000;
const REPLAY_STATE_MAX_DEVICES = 2048;

function fail(reason, detail) {
    return {
        req: msg.req,
        res: msg.res,
        payload: {
            ok: false,
            kind: "pertamina-gld-error",
            reason,
            detail,
            sourceTopic: msg.topic,
            receivedAt: new Date().toISOString()
        },
        topic: "gld/gateway/error"
    };
}

function cleanHex(input) {
    return String(input || "").replace(/^0x/i, "").replace(/[^0-9a-fA-F]/g, "");
}

function hexToBuffer(input) {
    const hex = cleanHex(input);
    if (hex.length === 0 || hex.length % 2 !== 0) {
        throw new Error("invalid hex length");
    }
    return Buffer.from(hex, "hex");
}

function be16(buf, offset) {
    return (buf[offset] << 8) | buf[offset + 1];
}

function crc16CcittFalse(buf) {
    let crc = 0xFFFF;
    for (const byte of buf) {
        crc ^= byte << 8;
        for (let i = 0; i < 8; i++) {
            crc = (crc & 0x8000) ? ((crc << 1) ^ 0x1021) : (crc << 1);
            crc &= 0xFFFF;
        }
    }
    return crc;
}

function getAesKey(keyId) {
    const envKeyId = Number(env.get("GLD_KEY_ID") || "1");
    if (keyId !== envKeyId) {
        throw new Error(`unknown keyId ${keyId}, expected ${envKeyId}`);
    }

    const configuredKey = env.get("GLD_AES128_KEY_HEX");
    if (!configuredKey) {
        throw new Error("GLD_AES128_KEY_HEX is required; production decoder must not fall back to the self-test key");
    }
    const keyHex = cleanHex(configuredKey).toUpperCase();
    if (keyHex.length !== 32) {
        throw new Error("GLD_AES128_KEY_HEX must be 32 hex characters");
    }
    return {
        key: Buffer.from(keyHex, "hex"),
        source: "env"
    };
}

function getGatewayId() {
    const raw = String(env.get("PGL_GATEWAY_ID") || env.get("GATEWAY_ID") || "0x006F").trim();
    const value = raw.toLowerCase().startsWith("0x") ? parseInt(raw, 16) : Number(raw);
    return Number.isFinite(value) ? value : DEFAULT_GATEWAY_ID;
}

function idHex(value) {
    const n = Number(value) & 0xFFFF;
    return `0x${n.toString(16).toUpperCase().padStart(4, "0")}`;
}

function parseIdValue(value, fallback = 0) {
    if (value === undefined || value === null || value === "") {
        return fallback;
    }
    if (typeof value === "string") {
        const trimmed = value.trim();
        const parsed = trimmed.toLowerCase().startsWith("0x") ? parseInt(trimmed, 16) : Number(trimmed);
        return Number.isFinite(parsed) ? parsed : fallback;
    }
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
}

function envNumber(name, fallback) {
    const value = Number(env.get(name));
    return Number.isFinite(value) && value >= 0 ? value : fallback;
}

const TOPOLOGY_PARENT_TTL_MS = envNumber("PGL_TOPOLOGY_PARENT_TTL_MS", 900000);
const TOPOLOGY_DISCOVERY_TTL_MS = envNumber("PGL_TOPOLOGY_DISCOVERY_TTL_MS", 420000);
const TOPOLOGY_GATEWAY_LINK_TTL_MS = envNumber("PGL_TOPOLOGY_GATEWAY_LINK_TTL_MS", 420000);

function ageMsOf(entry, nowMs = Date.now()) {
    const t = Date.parse(entry && entry.receivedAt);
    return Number.isFinite(t) ? Math.max(0, nowMs - t) : Number.POSITIVE_INFINITY;
}

function pruneTopology(topology, nowMs = Date.now()) {
    topology.parents = topology.parents || {};
    topology.discovery = topology.discovery || {};
    topology.gatewayLinks = topology.gatewayLinks || {};
    topology.hellos = topology.hellos || {};
    topology.routes = topology.routes || {};

    for (const [clusterIdHex, entry] of Object.entries(topology.parents)) {
        if (ageMsOf(entry, nowMs) > TOPOLOGY_PARENT_TTL_MS) {
            delete topology.parents[clusterIdHex];
            delete topology.routes[clusterIdHex];
        }
    }
    for (const [clusterIdHex, entry] of Object.entries(topology.hellos)) {
        if (ageMsOf(entry, nowMs) > TOPOLOGY_PARENT_TTL_MS) {
            delete topology.hellos[clusterIdHex];
        }
    }
    for (const [clusterIdHex, entry] of Object.entries(topology.discovery)) {
        if (ageMsOf(entry, nowMs) > TOPOLOGY_DISCOVERY_TTL_MS) {
            delete topology.discovery[clusterIdHex];
        }
    }
    for (const [clusterIdHex, entry] of Object.entries(topology.gatewayLinks)) {
        if (ageMsOf(entry, nowMs) > TOPOLOGY_GATEWAY_LINK_TTL_MS) {
            delete topology.gatewayLinks[clusterIdHex];
        }
    }
    for (const clusterIdHex of Object.keys(topology.routes)) {
        if (!topology.parents[clusterIdHex]) {
            delete topology.routes[clusterIdHex];
        }
    }
    return topology;
}

function getTopologyState() {
    return pruneTopology(flow.get("pglTopology") || {
        gatewayIdHex: idHex(getGatewayId()),
        parents: {},
        discovery: {},
        gatewayLinks: {},
        hellos: {},
        routes: {},
        updatedAt: null
    });
}

function buildRouteTo(clusterIdHex, topology) {
    const gatewayIdHex = topology.gatewayIdHex || idHex(getGatewayId());
    const route = [];
    const seen = {};
    let current = clusterIdHex;

    for (let guard = 0; guard < 16; guard++) {
        if (!current || current === gatewayIdHex || current === "0x0000" || seen[current]) {
            break;
        }
        seen[current] = true;
        const entry = topology.parents[current];
        if (!entry) {
            return [];
        }
        route.unshift(current);
        current = entry.parentIdHex;
    }
    return route;
}

function updateTopology(topologyEvent) {
    const topology = getTopologyState();
    topology.gatewayIdHex = idHex(topologyEvent.gatewayId || getGatewayId());
    topology.discovery = topology.discovery || {};
    topology.gatewayLinks = topology.gatewayLinks || {};
    topology.hellos = topology.hellos || {};
    delete topology.resetAt;
    topology.updatedAt = new Date().toISOString();
    topology.parents[topologyEvent.clusterIdHex] = topologyEvent;
    if (String(topologyEvent.report || "").toLowerCase() === "ch-hello") {
        topology.hellos[topologyEvent.clusterIdHex] = topologyEvent;
    }
    delete topology.discovery[topologyEvent.clusterIdHex];

    for (const clusterIdHex of Object.keys(topology.parents)) {
        topology.routes[clusterIdHex] = buildRouteTo(clusterIdHex, topology);
    }
    const route = topology.routes[topologyEvent.clusterIdHex] || [];
    flow.set("pglTopology", topology);
    return { topology, route };
}

function rememberDiscovery(topologyEvent) {
    const topology = getTopologyState();
    topology.gatewayIdHex = idHex(topologyEvent.gatewayId || getGatewayId());
    topology.discovery = topology.discovery || {};
    topology.gatewayLinks = topology.gatewayLinks || {};
    const hasFreshInstalledRoute = Boolean(topology.parents[topologyEvent.clusterIdHex]);
    if (hasFreshInstalledRoute) {
        delete topology.discovery[topologyEvent.clusterIdHex];
    } else {
        topology.discovery[topologyEvent.clusterIdHex] = topologyEvent;
    }
    if (topologyEvent.report === "ch-config-request" &&
        topologyEvent.parentIdHex === "0x0000" &&
        topologyEvent.rssi !== undefined) {
        topology.gatewayLinks[topologyEvent.clusterIdHex] = {
            clusterIdHex: topologyEvent.clusterIdHex,
            gatewayIdHex: topology.gatewayIdHex,
            rssi: topologyEvent.rssi,
            snr: topologyEvent.snr,
            receivedAt: topologyEvent.receivedAt,
            report: topologyEvent.report
        };
    }
    if (!hasFreshInstalledRoute) {
        topology.discoveryUpdatedAt = new Date().toISOString();
    }
    pruneTopology(topology);
    flow.set("pglTopology", topology);
    const route = topology.routes[topologyEvent.clusterIdHex] || [];
    return { topology, route };
}

function isInstalledTopologyReport(report) {
    const normalized = String(report || "").toLowerCase();
    return normalized === "ch-hello" ||
        normalized === "ch-topology" ||
        normalized === "installed" ||
        normalized === "stable-parent";
}

function decryptGldPayload(record) {
    if (record.payload.length !== GLD_ENCRYPTED_LEN) {
        return {
            decryptOk: false,
            skipped: true,
            skipReason: `payload length ${record.payload.length} is not encrypted phase-1 length ${GLD_ENCRYPTED_LEN}`
        };
    }

    const keyId = record.payload[0];
    const nonce = record.payload.subarray(1, 13);
    const ciphertext = record.payload.subarray(13, 17);
    const tag = record.payload.subarray(17, 29);
    const aad = Buffer.from([
        (record.nodeId >> 8) & 0xFF,
        record.nodeId & 0xFF,
        record.seq & 0xFF,
        record.flags & 0xFF,
        keyId & 0xFF
    ]);
    const { key, source } = getAesKey(keyId);

    let cryptoModule = global.get("crypto");
    if (!cryptoModule && typeof crypto !== "undefined") {
        cryptoModule = crypto;
    }
    if (!cryptoModule || typeof cryptoModule.createDecipheriv !== "function") {
        throw new Error("Node-RED crypto module is not available; set functionGlobalContext.crypto in settings.js");
    }

    const decipher = cryptoModule.createDecipheriv("aes-128-gcm", key, nonce, { authTagLength: 12 });
    decipher.setAAD(aad);
    decipher.setAuthTag(tag);
    const plaintext = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
    if (plaintext.length !== 4) {
        throw new Error(`plaintext length ${plaintext.length} invalid`);
    }

    const gasClass = plaintext[0];
    const confidence = plaintext[1];
    const batteryMv = be16(plaintext, 2);
    const gasName = GAS_CLASS[gasClass] || "invalid";
    const confidenceValid = confidence <= 100;
    const gasClassValid = gasClass <= 6;

    return {
        decryptOk: true,
        keyId,
        keySource: source,
        nonceHex: nonce.toString("hex").toUpperCase(),
        aadHex: aad.toString("hex").toUpperCase(),
        plaintextHex: plaintext.toString("hex").toUpperCase(),
        gasClass,
        gasName,
        confidence,
        confidenceValid,
        batteryMv,
        batteryValid: batteryMv !== 0xFFFF,
        gasClassValid
    };
}

function parseGldRecord(buf) {
    if (buf.length < 5) {
        throw new Error("GLDRecord too short");
    }
    const payloadLen = buf[4];
    if (buf.length !== 5 + payloadLen) {
        throw new Error(`GLDRecord length mismatch: buffer=${buf.length}, payloadLen=${payloadLen}`);
    }
    return {
        nodeId: be16(buf, 0),
        seq: buf[2],
        flags: buf[3],
        payloadLen,
        payload: buf.subarray(5),
        recordHex: buf.toString("hex").toUpperCase()
    };
}

function recordToEvent(record, outer, source) {
    const event = {
        ok: false,
        kind: "gld-event",
        source,
        receivedAt: new Date().toISOString(),
        sourceTopic: msg.topic,
        outer,
        nodeId: record.nodeId,
        nodeIdHex: `0x${record.nodeId.toString(16).toUpperCase().padStart(4, "0")}`,
        seq: record.seq,
        flags: record.flags,
        alarm: (record.flags & NC_FLAG_ALARM) !== 0,
        externalPower: (record.flags & NC_FLAG_EXT_POWER) !== 0,
        ingressClass: msg.topic === "gld/test/vector" ? "test" : (msg.req || msg.res ? "manual" : "production"),
        payloadLen: record.payloadLen,
        payloadHex: record.payload.toString("hex").toUpperCase(),
        dedupKey: `${outer && outer.srcIdHex ? outer.srcIdHex : "no-cluster"}:${record.nodeId}:${record.seq}:${(record.flags & NC_FLAG_ALARM) ? "alarm" : "normal"}`
    };

    try {
        Object.assign(event, decryptGldPayload(record));
        if (event.decryptOk === true && event.gasClassValid && event.confidenceValid) {
            event.ok = true;
        } else if (event.decryptOk === true) {
            event.decryptOk = false;
            event.decryptError = "decrypted payload failed semantic validation";
        }
    } catch (err) {
        event.decryptOk = false;
        event.decryptError = err.message;
    }

    return event;
}

function replayPersistence() {
    const filePath = String(env.get("PGL_REPLAY_STATE_PATH") || "").trim();
    if (!filePath) return null;
    const fsModule = global.get("fs") || (typeof fs !== "undefined" ? fs : null);
    const pathModule = global.get("path") || (typeof path !== "undefined" ? path : null);
    if (!fsModule || !pathModule) {
        throw new Error("durable replay state requires fs and path modules");
    }
    return { filePath, fsModule, pathModule };
}

function loadReplayState() {
    const cached = flow.get("pglReplayState");
    if (cached && typeof cached === "object" && !Array.isArray(cached)) return cached;
    const persistence = replayPersistence();
    if (!persistence || !persistence.fsModule.existsSync(persistence.filePath)) return {};
    const parsed = JSON.parse(persistence.fsModule.readFileSync(persistence.filePath, "utf8"));
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("durable replay state is not a JSON object");
    }
    flow.set("pglReplayState", parsed);
    return parsed;
}

function saveReplayState(all) {
    const persistence = replayPersistence();
    if (persistence) {
        const dir = persistence.pathModule.dirname(persistence.filePath);
        persistence.fsModule.mkdirSync(dir, { recursive: true });
        const temporary = `${persistence.filePath}.${Date.now()}.${Math.random().toString(16).slice(2)}.tmp`;
        persistence.fsModule.writeFileSync(temporary, JSON.stringify(all), { encoding: "utf8", mode: 0o600 });
        persistence.fsModule.renameSync(temporary, persistence.filePath);
    }
    flow.set("pglReplayState", all);
}

function replayDecision(event) {
    const now = Date.now();
    const all = loadReplayState();
    for (const [key, value] of Object.entries(all)) {
        if (!value || now - Number(value.updatedAt || 0) > REPLAY_STATE_TTL_MS) {
            delete all[key];
        }
    }

    const key = `${event.ingressClass}:${event.nodeId}`;
    const seq = Number(event.seq) & 0xFF;
    const current = all[key];
    if (!current) {
        all[key] = { lastSeq: seq, bitmap: 1, updatedAt: now };
        const keys = Object.keys(all);
        if (keys.length > REPLAY_STATE_MAX_DEVICES) {
            keys.sort((a, b) => Number(all[a].updatedAt || 0) - Number(all[b].updatedAt || 0));
            for (let i = 0; i < keys.length - REPLAY_STATE_MAX_DEVICES; i++) delete all[keys[i]];
        }
        saveReplayState(all);
        return { accepted: true, reason: "first" };
    }

    const lastSeq = Number(current.lastSeq) & 0xFF;
    const forward = (seq - lastSeq + 256) & 0xFF;
    let bitmap = Number(current.bitmap) >>> 0;
    if (forward === 0) {
        return { accepted: false, reason: "duplicate-sequence" };
    }
    if (forward < 128) {
        bitmap = forward >= REPLAY_WINDOW_BITS ? 1 : (((bitmap << forward) | 1) >>> 0);
        all[key] = { lastSeq: seq, bitmap, updatedAt: now };
        saveReplayState(all);
        return { accepted: true, reason: forward < REPLAY_WINDOW_BITS ? "forward" : "forward-reset-window" };
    }

    const behind = 256 - forward;
    if (behind >= REPLAY_WINDOW_BITS) {
        return { accepted: false, reason: "stale-sequence" };
    }
    const mask = (1 << behind) >>> 0;
    if ((bitmap & mask) !== 0) {
        return { accepted: false, reason: "duplicate-out-of-order-sequence" };
    }
    current.bitmap = (bitmap | mask) >>> 0;
    current.updatedAt = now;
    all[key] = current;
    saveReplayState(all);
    return { accepted: true, reason: "out-of-order" };
}

function quarantineEvent(event, reason, topic) {
    return {
        req: msg.req,
        res: msg.res,
        topic,
        payload: {
            ok: false,
            kind: topic === "gld/server/replay" ? "gld-replay-rejected" : "gld-integrity-failure",
            reason,
            receivedAt: event.receivedAt,
            sourceTopic: event.sourceTopic,
            source: event.source,
            ingressClass: event.ingressClass,
            nodeId: event.nodeId,
            nodeIdHex: event.nodeIdHex,
            seq: event.seq,
            alarmClaimed: event.alarm,
            decryptError: event.decryptError,
            dedupKey: event.dedupKey
        }
    };
}

function routeRecords(records, outer, source) {
    const eventMsgs = [];
    const decodedMsgs = [];
    const quarantineMsgs = [];
    for (const record of records) {
        const event = recordToEvent(record, outer, source);
        if (event.decryptOk !== true || event.ok !== true) {
            quarantineMsgs.push(quarantineEvent(
                event,
                event.decryptError || event.skipReason || "record authentication failed",
                "gld/server/integrity"
            ));
            continue;
        }
        let replay;
        try {
            replay = replayDecision(event);
        } catch (err) {
            quarantineMsgs.push(quarantineEvent(event, `replay state unavailable: ${err.message}`, "gld/server/integrity"));
            continue;
        }
        if (!replay.accepted) {
            quarantineMsgs.push(quarantineEvent(event, replay.reason, "gld/server/replay"));
            continue;
        }
        event.replayStatus = replay.reason;
        const nonProduction = event.ingressClass !== "production";
        decodedMsgs.push({
            req: msg.req,
            res: msg.res,
            payload: event,
            topic: nonProduction ? "gld/server/test" : (event.alarm ? "gld/server/alarm" : "gld/server/decoded")
        });
        eventMsgs.push({
            req: msg.req,
            res: msg.res,
            payload: {
                ok: true,
                kind: "gld-event-envelope",
                outer,
                nodeId: event.nodeId,
                seq: event.seq,
                flags: event.flags,
                alarm: event.alarm,
                decryptOk: true,
                ingressClass: event.ingressClass
            },
            topic: nonProduction ? "gld/gateway/test-events" : "gld/gateway/events"
        });
    }
    return { eventMsgs, decodedMsgs, quarantineMsgs };
}

function parseAppFrame(buf) {
    if (buf.length < 10 || buf[0] !== 0xAA) {
        throw new Error("AppFrame magic/length invalid");
    }
    const payloadLen = buf[7];
    if (buf.length !== 10 + payloadLen) {
        throw new Error(`AppFrame length mismatch: buffer=${buf.length}, payloadLen=${payloadLen}`);
    }
    const expectedCrc = be16(buf, buf.length - 2);
    const actualCrc = crc16CcittFalse(buf.subarray(0, buf.length - 2));
    if (expectedCrc !== actualCrc) {
        throw new Error(`AppFrame CRC mismatch expected=0x${expectedCrc.toString(16)} actual=0x${actualCrc.toString(16)}`);
    }
    const typeFlags = buf[1];
    const msgType = typeFlags & MSG_TYPE_MASK;
    const outer = {
        typeFlags,
        msgType,
        alarmFlag: (typeFlags & FLAG_ALARM_ACK) !== 0,
        externalFlag: (typeFlags & FLAG_GLD_EXT_POWER) !== 0,
        srcId: be16(buf, 2),
        srcIdHex: `0x${be16(buf, 2).toString(16).toUpperCase().padStart(4, "0")}`,
        dstId: be16(buf, 4),
        dstIdHex: `0x${be16(buf, 4).toString(16).toUpperCase().padStart(4, "0")}`,
        seq: buf[6],
        payloadLen
    };
    const payload = buf.subarray(8, 8 + payloadLen);
    outer.payloadHex = payload.toString("hex").toUpperCase();
    const records = [];

    if (msgType === MSG_CLUSTER_DATA_RESPONSE) {
        if (payload.length < 6) {
            throw new Error("CLUSTER_DATA_RESPONSE payload too short");
        }
        outer.response = {
            requestId: be16(payload, 0),
            status: payload[2],
            chBatteryMv: be16(payload, 3),
            recordCount: payload[5]
        };
        let offset = 6;
        for (let i = 0; i < outer.response.recordCount; i++) {
            if (offset + 5 > payload.length) {
                throw new Error(`CLUSTER_DATA_RESPONSE record ${i} header truncated at offset ${offset}`);
            }
            const payloadLenAtRecord = payload[offset + 4];
            const len = 5 + payloadLenAtRecord;
            if (offset + len > payload.length) {
                throw new Error(`CLUSTER_DATA_RESPONSE record ${i} body truncated: need ${len} bytes at offset ${offset}, have ${payload.length - offset}`);
            }
            records.push(parseGldRecord(payload.subarray(offset, offset + len)));
            offset += len;
        }
    } else if (msgType === MSG_SERVER_PULL_REQUEST) {
        if (payload.length >= 2 && payload.length % 2 === 0) {
            const hopList = [];
            for (let offset = 2; offset < payload.length; offset += 2) {
                const hop = be16(payload, offset);
                hopList.push(`0x${hop.toString(16).toUpperCase().padStart(4, "0")}`);
            }
            outer.request = {
                requestId: be16(payload, 0),
                hopList
            };
        }
        return { outer, records, control: true, ignoredReason: "server-pull-request" };
    } else if (msgType === MSG_SENSOR_DATA) {
        records.push(parseGldRecord(payload));
    } else if (msgType === MSG_CH_HELLO) {
        if (payload.length < 8) {
            throw new Error("CH_HELLO payload too short");
        }
        outer.topology = {
            clusterId: be16(payload, 0),
            clusterIdHex: idHex(be16(payload, 0)),
            parentId: be16(payload, 2),
            parentIdHex: idHex(be16(payload, 2)),
            parentAltId: payload.length >= 11 ? be16(payload, 9) : 0,
            parentAltIdHex: payload.length >= 11 ? idHex(be16(payload, 9)) : "0x0000",
            batteryMv: be16(payload, 4),
            uptimeSec: be16(payload, 6),
            meshDepth: payload.length >= 9 ? payload[8] : null,
            viaHop: outer.srcId,
            viaHopHex: outer.srcIdHex,
            gatewayId: getGatewayId(),
            gatewayIdHex: idHex(getGatewayId()),
            rssi: msg.payload && typeof msg.payload === "object" ? msg.payload.rssi : undefined,
            snr: msg.payload && typeof msg.payload === "object" ? msg.payload.snr : undefined
        };
        return { outer, records, topology: true };
    } else if (msgType >= MSG_MESH_CONTROL_MIN && msgType <= MSG_MESH_CONTROL_MAX) {
        return { outer, records, control: true, ignoredReason: "mesh-control-frame" };
    } else {
        throw new Error(`unsupported AppFrame msgType 0x${msgType.toString(16)}`);
    }

    return { outer, records };
}

function normalizeInput(input) {
    if (Buffer.isBuffer(input)) {
        return { kind: "buffer", buffer: input };
    }
    if (Array.isArray(input)) {
        return { kind: "buffer", buffer: Buffer.from(input) };
    }
    if (typeof input === "string") {
        const trimmed = input.trim();
        try {
            return normalizeInput(JSON.parse(trimmed));
        } catch (_) {
            return { kind: "buffer", buffer: hexToBuffer(trimmed) };
        }
    }
    if (input && typeof input === "object") {
        if (input.gateway_id !== undefined && Array.isArray(input.events)) {
            return { kind: "gatewayStatus", status: input };
        }
        if (input.kind === "ch-topology" || input.kind === "gateway-topology" || input.topology) {
            return { kind: "topologyObject", topology: input.topology || input };
        }
        const hex = input.frameHex || input.appFrameHex || input.recordHex || input.payload_hex || input.payloadHex || input.hex;
        if (hex) {
            return {
                kind: input.frameHex || input.appFrameHex ? "appFrameHex" : "recordOrPayloadHex",
                buffer: hexToBuffer(hex),
                meta: input
            };
        }
    }
    throw new Error("unsupported input payload");
}

function emitGatewayStatus(status) {
    const statusMsg = {
        req: msg.req,
        res: msg.res,
        payload: {
            ok: true,
            kind: "gateway-status",
            receivedAt: new Date().toISOString(),
            gatewayId: status.gateway_id,
            clusterCount: Array.isArray(status.clusters) ? status.clusters.length : 0,
            eventCount: Array.isArray(status.events) ? status.events.length : 0,
            clusters: status.clusters || []
        },
        topic: "gld/gateway/status"
    };

    const eventMsgs = [];
    const decodedMsgs = [];
    const quarantineMsgs = [];
    for (const e of status.events || []) {
        const base = {
            ok: true,
            kind: "gateway-event",
            receivedAt: new Date().toISOString(),
            gatewayId: status.gateway_id,
            clusterId: e.cluster_id,
            nodeId: e.node_id,
            seq: e.seq,
            flags: e.flags,
            alarm: !!e.alarm,
            payloadHex: e.payload_hex,
            legacy: true,
            raw: e
        };
        if (e.payload_hex) {
            try {
                const payload = hexToBuffer(e.payload_hex);
                let record;
                if (payload.length === GLD_RECORD_LEN) {
                    record = parseGldRecord(payload);
                } else if (payload.length === GLD_ENCRYPTED_LEN) {
                    record = {
                        nodeId: Number(e.node_id),
                        seq: Number(e.seq),
                        flags: Number(e.flags),
                        payloadLen: payload.length,
                        payload
                    };
                }
                if (record) {
                    const routed = routeRecords(
                        [record],
                        { srcId: e.cluster_id, srcIdHex: `0x${Number(e.cluster_id).toString(16).toUpperCase().padStart(4, "0")}` },
                        "gateway-status"
                    );
                    eventMsgs.push(...routed.eventMsgs);
                    decodedMsgs.push(...routed.decodedMsgs);
                    quarantineMsgs.push(...routed.quarantineMsgs);
                }
            } catch (err) {
                quarantineMsgs.push(fail("gateway event decode failed", { error: err.message, event: e }));
            }
        } else {
            base.unverified = true;
            base.alarmClaimed = base.alarm;
            delete base.alarm;
            eventMsgs.push({ req: msg.req, res: msg.res, payload: base, topic: "gld/gateway/unverified-events" });
        }
    }

    return [statusMsg, eventMsgs, decodedMsgs, quarantineMsgs];
}

try {
    const input = normalizeInput(msg.payload);
    if (input.kind === "gatewayStatus") {
        return emitGatewayStatus(input.status);
    }
    if (input.kind === "topologyObject") {
        const t = input.topology || {};
        const clusterId = Number(t.clusterId || t.cluster_id || t.chId || t.ch_id || t.edgeFrom || t.edge_from);
        const parentId = Number(t.parentId || t.parent_id || t.edgeTo || t.edge_to || 0);
        const event = {
            ok: true,
            kind: "ch-topology",
            source: "gateway-topology-object",
            receivedAt: new Date().toISOString(),
            sourceTopic: msg.topic,
            report: t.reportType || t.report || t.kind,
            gatewayId: Number(t.gatewayId || t.gateway_id || getGatewayId()),
            gatewayIdHex: idHex(t.gatewayId || t.gateway_id || getGatewayId()),
            clusterId,
            clusterIdHex: idHex(clusterId),
            parentId,
            parentIdHex: idHex(parentId),
            parentAltId: parseIdValue(t.parentAltId || t.parentAltIdHex || t.parent_alt_id || t.altParentId || t.alt_parent_id || 0),
            parentAltIdHex: idHex(parseIdValue(t.parentAltId || t.parentAltIdHex || t.parent_alt_id || t.altParentId || t.alt_parent_id || 0)),
            parentIsRoot: parentId === Number(t.gatewayId || t.gateway_id || getGatewayId()),
            requesterId: t.requesterId !== undefined ? Number(t.requesterId) : undefined,
            requesterIdHex: t.requesterId !== undefined ? idHex(t.requesterId) : undefined,
            batteryMv: Number(t.batteryMv || t.battery_mv || 0xFFFF),
            uptimeSec: Number(t.uptimeSec || t.uptimeSec16 || t.uptime_sec || 0),
            meshDepth: t.meshDepth !== undefined ? Number(t.meshDepth) : (t.depth !== undefined ? Number(t.depth) : null),
            viaHop: Number(t.viaHop || t.via_hop || 0),
            viaHopHex: idHex(t.viaHop || t.via_hop || 0),
            rssi: t.rssi,
            snr: t.snr
        };
        if (event.report === "ch-config-request" && event.parentIdHex === "0x0000") {
            const topology = getTopologyState();
            const existingRoute = topology.routes && topology.routes[event.clusterIdHex];
            const route = Array.isArray(existingRoute) ? existingRoute : [];
            rememberDiscovery(event);
            event.hopList = route;
            event.nextHop = route.length > 0 ? route[0] : undefined;
            event.nextHopHex = event.nextHop;
            event.lastHop = route.length > 0 ? route[route.length - 1] : event.clusterIdHex;
            event.routeText = route.length > 0
                ? `${event.gatewayIdHex} -> ${route.join(" -> ")}`
                : `${event.gatewayIdHex} heard CH_CONFIG_REQUEST from ${event.clusterIdHex}; installed route pending`;
            event.requestPayload = route.length > 0 ? { requestId: 1, hopList: route } : undefined;
            event.routeStatus = route.length > 0 ? "CH_CONFIG request seen; retained fresh installed route" : "CH_CONFIG request seen; installed route pending";
            return [null, [{ req: msg.req, res: msg.res, payload: event, topic: "gld/server/topology" }], null, null];
        }

        if (!isInstalledTopologyReport(event.report)) {
            const { route } = rememberDiscovery(event);
            event.hopList = route;
            event.nextHop = route.length > 0 ? route[0] : undefined;
            event.nextHopHex = event.nextHop;
            event.lastHop = route.length > 0 ? route[route.length - 1] : event.clusterIdHex;
            event.routeText = route.length > 0
                ? `${event.gatewayIdHex} -> ${route.join(" -> ")}`
                : `${event.gatewayIdHex} heard ${event.report || "discovery"} from ${event.clusterIdHex}; installed route pending`;
            event.requestPayload = route.length > 0 ? { requestId: 1, hopList: route } : undefined;
            event.routeStatus = route.length > 0 ? "CH_CONFIG candidate seen; retained fresh installed route" : "CH_CONFIG candidate seen; installed route pending";
            event.discoveryOnly = true;
            return [null, [{ req: msg.req, res: msg.res, payload: event, topic: "gld/server/topology" }], null, null];
        }

        const { route } = updateTopology(event);
        event.hopList = route;
        event.nextHop = route.length > 0 ? route[0] : undefined;
        event.nextHopHex = event.nextHop;
        event.lastHop = route.length > 0 ? route[route.length - 1] : event.clusterIdHex;
        event.routeText = route.length > 0 ? `${event.gatewayIdHex} -> ${route.join(" -> ")}` : `${event.gatewayIdHex} -> ${event.clusterIdHex} (pending)`;
        event.requestPayload = route.length > 0 ? { requestId: 1, hopList: route } : undefined;
        event.routeStatus = route.length > 0 ? "CH route updated" : "CH route pending";
        return [null, [{ req: msg.req, res: msg.res, payload: event, topic: "gld/server/topology" }], null, null];
    }

    let parsed;
    if (input.buffer[0] === 0xAA) {
        parsed = parseAppFrame(input.buffer);
    } else if (input.buffer.length === GLD_RECORD_LEN) {
        parsed = { outer: { srcIdHex: "direct-record" }, records: [parseGldRecord(input.buffer)] };
    } else if (input.buffer.length === GLD_ENCRYPTED_LEN && input.meta) {
        parsed = {
            outer: { srcIdHex: "direct-payload" },
            records: [{
                nodeId: Number(input.meta.nodeId || input.meta.node_id),
                seq: Number(input.meta.seq),
                flags: Number(input.meta.flags || 0),
                payloadLen: input.buffer.length,
                payload: input.buffer
            }]
        };
    } else {
        throw new Error(`buffer length ${input.buffer.length} is not supported`);
    }

    if (parsed.control) {
        return [null, null, null, null];
    }

    if (parsed.topology && parsed.outer && parsed.outer.topology) {
        const event = Object.assign({
            ok: true,
            kind: "ch-topology",
            source: "app-frame",
            receivedAt: new Date().toISOString(),
            sourceTopic: msg.topic,
            report: "ch-hello",
            outer: parsed.outer
        }, parsed.outer.topology);
        const { route } = updateTopology(event);
        event.hopList = route;
        event.nextHop = route.length > 0 ? route[0] : undefined;
        event.nextHopHex = event.nextHop;
        event.lastHop = route.length > 0 ? route[route.length - 1] : event.clusterIdHex;
        event.routeText = route.length > 0 ? `${event.gatewayIdHex} -> ${route.join(" -> ")}` : `${event.gatewayIdHex} -> ${event.clusterIdHex} (pending)`;
        event.requestPayload = route.length > 0 ? { requestId: 1, hopList: route } : undefined;
        event.routeStatus = route.length > 0 ? "CH route updated" : "CH route pending";
        return [null, [{ req: msg.req, res: msg.res, payload: event, topic: "gld/server/topology" }], null, null];
    }

    if (parsed.outer && parsed.outer.msgType === MSG_CLUSTER_DATA_RESPONSE && parsed.outer.dstId !== getGatewayId()) {
        return [null, null, null, null];
    }

    const routed = routeRecords(parsed.records, parsed.outer, "contract");
    return [null, routed.eventMsgs, routed.decodedMsgs, routed.quarantineMsgs];
} catch (err) {
    return [null, null, null, fail("decode failed", err.message)];
}
