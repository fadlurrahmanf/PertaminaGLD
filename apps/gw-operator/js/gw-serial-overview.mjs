// Only use fields actually reported by the Gateway; an absent value is unknown.
export function mergeSerialOverview(previous, line) {
  const statusPrefix = "GW_STATUS_JSON ";
  const meshPrefix = "GW_MESH_LORA_JSON ";
  let payload;
  try {
    if (line.startsWith(statusPrefix)) {
      payload = JSON.parse(line.slice(statusPrefix.length));
      if (!payload || typeof payload !== "object" || !payload.gatewayId) return null;
      const oldId = String(previous?.gatewayId || "").replace(/^0x/i, "").toUpperCase();
      const newId = String(payload.gatewayId).replace(/^0x/i, "").toUpperCase();
      const same = oldId && oldId === newId;
      const keep = same || (!oldId && previous?._source === "serial");
      return { ...(keep ? previous : {}), ...payload, state: "serial connected", _source: "serial" };
    }
    if (line.startsWith(meshPrefix)) {
      payload = JSON.parse(line.slice(meshPrefix.length));
      if (!payload || typeof payload !== "object") return null;
      return { ...(previous || { state: "serial connected", _source: "serial" }),
        meshFreqMhz: payload.freqMHz, meshBandwidthKhz: payload.bwKHz,
        meshSpreadingFactor: payload.sf, meshCodingRate: payload.cr,
        meshSyncWord: payload.syncWord, meshTxPowerDbm: payload.txPowerDbm };
    }
  } catch { return null; }
  return null;
}
