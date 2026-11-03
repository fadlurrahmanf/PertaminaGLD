// Shared display policy only. Firmware remains authoritative for NVS binding
// and inference; missing legacy metadata never becomes a green status.
export function modelBindingState(status) {
  const model = status?.model || {};
  const readiness = model.readiness || {};
  const bound = model.boundNullingProfileId;
  const active = model.activeNullingProfileId;
  const validId = (id) => Number.isInteger(id) && Number.isFinite(id) && id > 0;
  const flag = (key) => [readiness[key], model[key]];
  const falseFlag = (key) => flag(key).includes(false);
  const trueFlag = (key) => flag(key).includes(true);
  const result = (value, reason, label, text) => ({ value, reason, label, text });

  if (falseFlag("productionApproved")) {
    return result(false, "model_not_approved", "model belum disetujui",
      "Model belum disetujui untuk produksi. Bind ulang tidak dapat mengaktifkan inferensi; gunakan paket model yang sudah disetujui.");
  }
  if (falseFlag("bindingValid")) {
    return result(false, "binding_invalid", "binding belum valid",
      "Binding model belum valid. Gunakan profil nulling lengkap yang tersimpan, lalu bind model melalui Running Settings.");
  }
  if (falseFlag("bindingModelMatches")) {
    return result(false, "model_mismatch", "model tidak cocok",
      "Binding tersimpan tidak cocok dengan model yang terpasang. Bind model ke profil nulling aktif setelah profil dinyatakan valid.");
  }
  if (validId(bound) && validId(active) && bound !== active) {
    return result(false, "profile_id_mismatch", `profil #${bound} ≠ #${active}`,
      `Binding menunjuk profil nulling #${bound}, sedangkan profil aktif #${active}. Bind ulang ke profil aktif; inferensi tetap diblokir.`);
  }
  if (falseFlag("profileReady") || status?.bootHealth?.modelProfileReady === false) {
    return result(false, "profile_not_ready", "profil belum siap",
      "Firmware melaporkan profil model/nulling belum siap. Periksa profil nulling dan readiness GLD sebelum melakukan bind ulang.");
  }
  if (!validId(bound) || !validId(active)) {
    return result(null, "profile_id_unknown", "ID profil belum valid",
      "ID profil nulling bound/aktif belum tersedia atau tidak valid. Kirim GET_STATUS; binding belum dapat dinyatakan cocok.");
  }
  if (!trueFlag("bindingValid") || !trueFlag("bindingModelMatches") || !trueFlag("productionApproved")) {
    return result(null, "binding_unknown", "data belum lengkap",
      "Persetujuan model atau detail binding belum lengkap. Kirim GET_STATUS; firmware tetap menentukan apakah bind dan inferensi diizinkan.");
  }
  return result(true, "matched", "cocok",
    `Model terikat ke profil nulling #${bound}; profil aktif #${active} cocok.`);
}
