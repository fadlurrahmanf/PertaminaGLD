function cleanHex(input) {
  return String(input || "").replace(/^0x/i, "").replace(/[^0-9a-fA-F]/g, "");
}

function parseRequiredId(value, label) {
  if (value === undefined || value === null || value === "") {
    throw new Error(`${label} is required`);
  }
  const text = String(value).trim();
  if (!/^(?:0x)?[0-9a-fA-F]{1,4}$/.test(text)) {
    throw new Error(`${label} must be a 1..4 digit hexadecimal node ID`);
  }
  const parsed = parseInt(text.replace(/^0x/i, ""), 16);
  if (parsed <= 0 || parsed >= 0xFFFF) {
    throw new Error(`${label} must be between 0x0001 and 0xFFFE`);
  }
  return parsed;
}

function parseHopList(value) {
  if (value === undefined || value === null) return null;
  if (!Array.isArray(value) || value.length < 1 || value.length > 29) {
    throw new Error("hopList must be an array containing 1..29 node IDs");
  }
  const hops = value.map((hop, index) => parseRequiredId(hop, `hopList[${index}]`));
  if (new Set(hops).size !== hops.length) {
    throw new Error("hopList must not contain duplicate node IDs");
  }
  return hops;
}

function formatNodeId(value) {
  return `0x${value.toString(16).toUpperCase().padStart(4, "0")}`;
}

function u16be(value) {
  return Buffer.from([(value >> 8) & 0xFF, value & 0xFF]);
}

function xor16(a, b) {
  const out = Buffer.alloc(16);
  for (let i = 0; i < 16; i++) out[i] = a[i] ^ b[i];
  return out;
}

function leftShiftOne(block) {
  const out = Buffer.alloc(16);
  let carry = 0;
  for (let i = 15; i >= 0; i--) {
    const value = block[i];
    out[i] = ((value << 1) & 0xFF) | carry;
    carry = (value & 0x80) ? 1 : 0;
  }
  return out;
}

function aesBlock(cryptoModule, key, block) {
  const cipher = cryptoModule.createCipheriv("aes-128-ecb", key, null);
  cipher.setAutoPadding(false);
  return Buffer.concat([cipher.update(block), cipher.final()]);
}

function aesCmac(cryptoModule, key, message) {
  const zero = Buffer.alloc(16);
  const rb = 0x87;
  const l = aesBlock(cryptoModule, key, zero);
  const k1 = leftShiftOne(l);
  if (l[0] & 0x80) k1[15] ^= rb;
  const k2 = leftShiftOne(k1);
  if (k1[0] & 0x80) k2[15] ^= rb;

  const complete = message.length > 0 && message.length % 16 === 0;
  const blockCount = complete ? message.length / 16 : Math.floor(message.length / 16) + 1;
  let last = Buffer.alloc(16);
  const lastOffset = (blockCount - 1) * 16;
  if (complete) {
    last = xor16(message.subarray(lastOffset, lastOffset + 16), k1);
  } else {
    message.copy(last, 0, lastOffset);
    last[message.length - lastOffset] = 0x80;
    last = xor16(last, k2);
  }

  let x = Buffer.alloc(16);
  for (let i = 0; i < blockCount - 1; i++) {
    x = aesBlock(cryptoModule, key, xor16(x, message.subarray(i * 16, i * 16 + 16)));
  }
  return aesBlock(cryptoModule, key, xor16(x, last));
}

function reject(reason) {
  node.error(reason, msg);
  return null;
}

try {
  const p = msg.payload;
  if (!p || typeof p !== "object" || Array.isArray(p)) return reject("command payload must be a JSON object");
  const cryptoModule = global.get("crypto") || (typeof crypto !== "undefined" ? crypto : null);
  if (!cryptoModule || typeof cryptoModule.createCipheriv !== "function") {
    return reject("Node-RED crypto module is required for authenticated GLD node commands");
  }

  if (msg._pglTrustedLocal !== true) {
    const expected = String(env.get("PGL_COMMAND_AUTH_TOKEN") || "");
    const supplied = String(p.authorization || p.authToken || "").replace(/^Bearer\s+/i, "");
    if (expected.length < 32 || supplied.length !== expected.length) {
      return reject("command authorization failed");
    }
    const expectedBytes = Buffer.from(expected, "utf8");
    const suppliedBytes = Buffer.from(supplied, "utf8");
    if (!cryptoModule.timingSafeEqual(expectedBytes, suppliedBytes)) {
      return reject("command authorization failed");
    }
  }

  const keyHex = cleanHex(env.get("GLD_AES128_KEY_HEX"));
  if (keyHex.length !== 32) {
    return reject("GLD_AES128_KEY_HEX must be set to 32 hex chars before building GLD node commands");
  }

  const modeMap = { inference: 0, running: 0, dataset: 1, nulling: 2 };
  const modeText = String(p.mode ?? "").trim().toLowerCase();
  const mode = modeMap[modeText] !== undefined ? modeMap[modeText] : Number(p.mode);
  if (!Number.isInteger(mode) || mode < 0 || mode > 2) {
    return reject("mode must be inference/running, dataset, nulling, or 0..2");
  }

  const hopList = parseHopList(p.hopList ?? p.hops);
  let cluster;
  if (hopList) {
    cluster = hopList[hopList.length - 1];
    const explicitCluster = p.cluster ?? p.clusterId;
    if (explicitCluster !== undefined && explicitCluster !== null && explicitCluster !== "") {
      const requestedCluster = parseRequiredId(explicitCluster, "cluster");
      if (requestedCluster !== cluster) {
        throw new Error("cluster must match the final hopList node ID");
      }
    }
  } else {
    cluster = parseRequiredId(p.cluster ?? p.clusterId, "cluster");
  }
  const nodeId = parseRequiredId(p.node ?? p.nodeId, "node");
  const commandId = parseRequiredId(p.id ?? p.commandId, "command id");
  const ttl = p.ttl === undefined ? 600 : Number(p.ttl);
  if (!Number.isInteger(ttl) || ttl < 1 || ttl > 3600) return reject("ttl must be an integer from 1 to 3600 seconds");

  const appSeq = commandId & 0xFF;
  const command = Buffer.from([0x81, mode & 0xFF, (commandId >> 8) & 0xFF, commandId & 0xFF]);
  const macInput = Buffer.concat([u16be(cluster), u16be(nodeId), Buffer.from([appSeq]), command]);
  const tag = aesCmac(cryptoModule, Buffer.from(keyHex, "hex"), macInput).subarray(0, 4);

  msg.payload = {
    cluster: formatNodeId(cluster),
    node: formatNodeId(nodeId),
    id: commandId,
    ttl,
    mode,
    hex: Buffer.concat([command, tag]).toString("hex").toUpperCase(),
    commandAuth: "aes-cmac-32",
    commandPayload: "cmdType(0x81)+mode+commandId+cmacTag4"
  };
  if (hopList) msg.payload.hopList = hopList.map(formatNodeId);
  delete msg._pglTrustedLocal;
  return msg;
} catch (err) {
  return reject(err.message);
}
