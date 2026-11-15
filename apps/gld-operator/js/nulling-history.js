// Local observations only: the GLD retains the latest saved profile, not its history.
const PREFIX = "gld.nulling.profileHistory.v1.";
const memory = new Map();
const volatileKeys = new Set();
const keyFor = id => PREFIX + encodeURIComponent(String(id || "").trim().toUpperCase());
export function validNullingProfile(profile) {
  return profile?.valid === true && Number.isInteger(Number(profile.profileId)) && Number(profile.profileId) > 0 &&
    Array.isArray(profile.dacCode) && profile.dacCode.length === 8 &&
    profile.dacCode.every(v => v !== null && v !== "" && Number.isInteger(Number(v)) && Number(v) >= 0 && Number(v) <= 4095) &&
    Array.isArray(profile.channelOk) && profile.channelOk.length === 8 && profile.channelOk.every(v => v === true);
}
function read(id) {
  const key = keyFor(id);
  if (volatileKeys.has(key)) return memory.get(key) || [];
  try { const value = JSON.parse(localStorage.getItem(key) || "null"); if (Array.isArray(value)) { memory.set(key, value); return value; } } catch {}
  return memory.get(key) || [];
}
export function getNullingHistory(id) { return id ? read(id).filter(x => validNullingProfile(x)) : []; }
export function rememberNullingProfile(id, profile) {
  if (!id || !validNullingProfile(profile)) return { saved: false, history: getNullingHistory(id) };
  const history = getNullingHistory(id).slice();
  const code = profile.dacCode.map(Number), profileId = Number(profile.profileId);
  const last = history.at(-1);
  if (last && last.profileId === profileId && last.dacCode.every((v, i) => v === code[i])) return { saved: true, history };
  // A reset, reused ID, or conflicting read starts a separate sequence; never
  // claim a delta between unrelated profiles or overwrite an observation.
  const epoch = last ? (profileId <= last.profileId ? (last.epoch || 0) + 1 : (last.epoch || 0)) : 0;
  history.push({ valid: true, profileId, dacCode: code, channelOk: Array(8).fill(true), epoch, observedAt: new Date().toISOString() });
  const bounded = history.slice(-200); const key = keyFor(id); memory.set(key, bounded);
  try { localStorage.setItem(key, JSON.stringify(bounded)); volatileKeys.delete(key); return { saved: true, history: bounded }; }
  catch { volatileKeys.add(key); return { saved: false, history: bounded }; }
}
export function channelHistory(id, channel) {
  const items = getNullingHistory(id);
  return items.map((p, index) => {
    const before = items[index - 1];
    const delta = before && before.epoch === p.epoch && before.profileId + 1 === p.profileId
      ? p.dacCode[channel] - before.dacCode[channel] : null;
    return { profileId: p.profileId, value: p.dacCode[channel], delta, epoch: p.epoch };
  });
}
export function formatMcpDelta(delta) {
  if (delta === null || delta === undefined || !Number.isFinite(delta)) return "pembanding tidak tersedia";
  return delta > 0 ? `naik +${delta}` : delta < 0 ? `turun ${delta}` : "tetap 0";
}
export function summarizeProfiles(previous, current, names) {
  const comparable = previous && previous.epoch === current.epoch && previous.profileId + 1 === current.profileId;
  let up = 0, down = 0, same = 0;
  const lines = current.dacCode.map((value, i) => {
    const delta = comparable ? value - previous.dacCode[i] : null;
    if (delta > 0) up++; else if (delta < 0) down++; else if (delta === 0) same++;
    return `CH${i + 1} ${names[i] || ""}: ${value} (${formatMcpDelta(delta)})`;
  });
  let advice = "Simpan riwayat ini untuk membandingkan nulling berikutnya.";
  if (comparable) {
    const deltas = current.dacCode.map((value, i) => value - previous.dacCode[i]);
    const largest = Math.max(...deltas.map(Math.abs));
    const channels = deltas.flatMap((value, i) => Math.abs(value) === largest && largest > 0 ? [`CH${i + 1} ${names[i] || ""}`] : []);
    advice = largest ? `Perubahan terbesar: ${channels.join(", ")} (${largest} kode). Periksa jika tidak sesuai kondisi kalibrasi.` : "Semua nilai MCP sama dengan profil sebelumnya.";
  }
  return [`Profil #${current.profileId} tersimpan untuk 8 channel.`, comparable ? `Dibandingkan profil #${previous.profileId}: ${up} naik, ${down} turun, ${same} tetap.` : "Profil sebelumnya belum tersedia di aplikasi ini.", ...lines, advice, "Perubahan MCP adalah perbandingan kode DAC; bukan diagnosis kondisi sensor."].join("\n");
}
