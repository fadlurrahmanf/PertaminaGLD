// Readable GET_STATUS feedback for the Expert tab.  This is deliberately a
// view of the device snapshot, not a second readiness policy: firmware stays
// authoritative for every TX/inference gate.

import { $, state } from "./state.js";
import { modelBindingState } from "./model-binding.js";

function knownBoolean(value) {
  return value === true || value === false ? value : null;
}

function boolFrom(...values) {
  for (const value of values) {
    const parsed = knownBoolean(value);
    if (parsed !== null) return parsed;
  }
  return null;
}

function statusText(value) {
  return value === true ? "SIAP" : value === false ? "BELUM SIAP" : "BELUM TERSEDIA";
}

function firstProblem(checks) {
  return checks.find((check) => check.value === false);
}

function nextAction(key) {
  const actions = {
    sensors: "Periksa sensor/ADS lalu tunggu satu scan dengan semua channel valid.",
    primed: "Tunggu sensor selesai priming/stabil sebelum mengirim ke CH.",
    ml: "Model ML belum siap; periksa hasil boot dan profil model.",
    nulling: "Profil nulling belum diterapkan; selesaikan nulling yang valid.",
    binding: "Binding model dan profil nulling aktif belum cocok; lakukan bind ulang dari Running Settings.",
    dac: "Verifikasi DAC belum siap; periksa hasil nulling/DAC pada status GLD.",
    engine: "Inference belum menghasilkan hasil valid; lihat baris GLD_SENSOR_SCAN dan ML di log Expert."
  };
  return actions[key] || "Kirim GET_STATUS lagi setelah GLD menyelesaikan inisialisasi.";
}

function asRows(status) {
  const boot = status?.bootHealth || {};
  const model = status?.model || {};
  // GLD1 >= this diagnostic revision publishes the exact latest scan state in
  // model.readiness. Keep the older top-level aliases below it for boards
  // that have not yet been updated.
  const readiness = model.readiness || {};
  const binding = modelBindingState(status);
  const telemetry = status?.telemetry || {};
  const sensorStatuses = Array.isArray(telemetry.sensorStatus) ? telemetry.sensorStatus : null;
  const allSensorStatusOk = sensorStatuses && sensorStatuses.length >= 8
    ? sensorStatuses.slice(0, 8).every((entry) => Number(entry) === 0)
    : null;

  return [
    { key: "sensors", label: "Sensor / ADS valid", value: boolFrom(readiness.allSensorsValid, model.allSensorsValid, model.sensorsValid, telemetry.allSensorsValid, allSensorStatusOk) },
    { key: "primed", label: "Sensor sudah stabil", value: boolFrom(readiness.sensorsPrimed, model.sensorsPrimed, model.primed, telemetry.primed) },
    { key: "ml", label: "Model ML siap", value: boolFrom(readiness.mlReady, model.mlReady, boot.mlReady) },
    { key: "nulling", label: "Profil nulling diterapkan", value: boolFrom(readiness.nullingProfileApplied, model.nullingProfileApplied, boot.nullingProfileApplied) },
    {
      key: "binding",
      label: binding.value === true ? "Binding model / profil cocok" : `Binding · ${binding.label}`,
      value: binding.value,
      detail: binding.text
    },
    { key: "dac", label: "Verifikasi DAC siap", value: boolFrom(readiness.dacVerificationReady, model.dacVerificationReady, boot.dacVerificationReady, boot.dacReady) },
    { key: "engine", label: "Hasil inference valid", value: boolFrom(readiness.inferenceValid, model.inferenceEngineOk, model.inferenceValid, telemetry.inferenceValid) }
  ];
}

export function resetExpertStatus() {
  const summary = $("expertStatusSummary");
  const rows = $("expertStatusRows");
  const hint = $("expertStatusHint");
  if (!summary || !rows || !hint) return;
  summary.textContent = "Menunggu GET_STATUS dari GLD.";
  summary.className = "expert-status-summary is-unknown";
  rows.replaceChildren();
  hint.textContent = "Ketik GET_STATUS lalu Send untuk membaca kondisi inference yang aktif di GLD.";
}

export function renderExpertStatus(status = state.status) {
  const summary = $("expertStatusSummary");
  const rowsElement = $("expertStatusRows");
  const hint = $("expertStatusHint");
  if (!summary || !rowsElement || !hint) return;
  if (!status || typeof status !== "object") {
    resetExpertStatus();
    return;
  }

  const boardProfile = String(status.boardProfile || state.info?.boardProfile || "");
  const isKnownOtherGld = /GLD2|GLD3/i.test(boardProfile) || status.sensorPower?.available === true;
  if (isKnownOtherGld) {
    summary.textContent = "KHUSUS GLD1";
    summary.className = "expert-status-summary is-unknown";
    rowsElement.replaceChildren();
    hint.textContent = "Panel diagnosis inference ini hanya memakai kontrak GET_STATUS GLD1; GLD2/GLD3 tidak diubah.";
    return;
  }

  const rows = asRows(status);
  const hasDeviceFields = rows.some((row) => row.value !== null);
  if (!hasDeviceFields) {
    summary.textContent = "STATUS BELUM LENGKAP";
    summary.className = "expert-status-summary is-unknown";
    rowsElement.replaceChildren();
    hint.textContent = "Firmware ini belum mengirim detail readiness inference. Perbarui paket GLD1 lalu kirim GET_STATUS kembali.";
    return;
  }

  const problem = firstProblem(rows);
  const unknown = rows.some((row) => row.value === null);
  summary.textContent = problem ? "INFERENCE BELUM SIAP" : unknown ? "INFERENCE MENUNGGU DATA" : "INFERENCE SIAP";
  summary.className = `expert-status-summary ${problem ? "is-blocked" : unknown ? "is-unknown" : "is-ready"}`;
  rowsElement.replaceChildren(...rows.map((row) => {
    const item = document.createElement("div");
    if (row.detail) item.title = row.detail;
    item.className = `expert-status-row ${row.value === true ? "is-ready" : row.value === false ? "is-blocked" : "is-unknown"}`;
    const label = document.createElement("span");
    label.textContent = row.label;
    const value = document.createElement("strong");
    value.textContent = statusText(row.value);
    item.append(label, value);
    return item;
  }));
  const blocker = typeof status?.model?.readiness?.blocker === "string" ? status.model.readiness.blocker : "";
  hint.textContent = problem ? `${problem.detail || nextAction(problem.key)}${blocker && blocker !== "none" ? ` Kode GLD: ${blocker}.` : ""}`
    : unknown ? "Sebagian detail belum dikirim firmware; GET_STATUS berikutnya akan memperbarui panel ini."
      : "Semua gate inference yang dilaporkan GLD siap. TX normal masih dapat gagal jika radio/SX1262 tidak siap.";
}
