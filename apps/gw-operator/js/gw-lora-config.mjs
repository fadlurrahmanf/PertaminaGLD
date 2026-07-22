export const MESH_BANDWIDTHS_KHZ = [7.8, 10.4, 15.6, 20.8, 31.25, 41.7, 62.5, 125, 250, 500];

function finiteNumber(value, label) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new Error(`${label} must be a number.`);
  return parsed;
}

function integerInRange(value, label, min, max) {
  const parsed = finiteNumber(value, label);
  if (!Number.isInteger(parsed) || parsed < min || parsed > max) {
    throw new Error(`${label} must be an integer from ${min} to ${max}.`);
  }
  return parsed;
}

export function validateMeshLoraConfig(raw) {
  const freqMHz = finiteNumber(raw.freqMHz, "Frequency");
  if (freqMHz < 900 || freqMHz > 930) throw new Error("Frequency must be 900–930 MHz.");

  const bwKHz = finiteNumber(raw.bwKHz, "Bandwidth");
  if (!MESH_BANDWIDTHS_KHZ.includes(bwKHz)) {
    throw new Error(`Bandwidth must be one of: ${MESH_BANDWIDTHS_KHZ.join(", ")} kHz.`);
  }

  return {
    freqMHz,
    bwKHz,
    sf: integerInRange(raw.sf, "SF", 5, 12),
    cr: integerInRange(raw.cr, "CR", 5, 8),
    syncWord: integerInRange(raw.syncWord, "Sync word", 0, 255),
    txPowerDbm: integerInRange(raw.txPowerDbm, "TX power", -9, 22),
    reboot: true
  };
}
