const devices = {
  gld: { label: "GLD", name: "Gas Leak Detector", glyph: "G" },
  ch: { label: "CH", name: "Cluster Head", glyph: "C" },
  gw: { label: "Gateway", name: "Network Gateway", glyph: "W" }
};

let token = "";
let active = "gld";
let overview = {};
let lastTestReport = null;
const testReportsByDevice = {};
let initialFirmwareRequired = false;
let settingsOpened = false;
let reviewStep = 0;
let uploadEvents = null;
let uploadBusy = false;
let uploadProgress = 0;
let uploadLines = [];
let uploadEventsReady = false;
let uploadFlashDone = false;
let uploadReadbackVerified = false;
let uploadSuccessShown = false;
let testDeviceRunning = false;
const simulationMode = new URLSearchParams(location.search).get("simulate");
const $ = (id) => document.getElementById(id);
const notice = $("notice");

function prepareThreeStepWorkflow() {
  $("operatorSteps").innerHTML = `
    <li><button class="step-button" data-step="1" type="button" aria-label="Kembali ke tahap Hubungkan">1</button><div><b>Hubungkan</b><small>Port COM</small></div></li>
    <li><button class="step-button" data-step="2" type="button" aria-label="Kembali ke tahap Test Device">2</button><div><b>Test Device</b><small>Kesiapan</small></div></li>
    <li><button class="step-button" data-step="3" type="button" aria-label="Kembali ke tahap Konfigurasi">3</button><div><b>Konfigurasi</b><small>Parameter</small></div></li>`;
  $("nextAction").textContent = "Hubungkan perangkat untuk memulai.";
  document.querySelector(".connect-card .card-kicker").textContent = "TAHAP 1 DARI 3 / HUBUNGKAN";
  document.querySelector("#testDeviceCard .card-kicker").textContent = "TAHAP 2 DARI 3 / TEST DEVICE";
  $("continueBtn").innerHTML = "Lanjutkan ke Konfigurasi <span>&rarr;</span>";
  document.querySelector("#settingsCard .card-kicker").textContent = "TAHAP 3 DARI 3 / KONFIGURASI";
  document.querySelector("#firmwareStage .card-kicker").textContent = "KONFIGURASI SELESAI";
  $("testDeviceCard").insertAdjacentHTML("beforeend", '<button id="testUploadFirmwareBtn" class="test-upload-option secondary" type="button">Upload firmware</button>');
  const actions = document.querySelector("#firmwareStage .firmware-actions");
  actions.insertAdjacentHTML("beforeend", '<button id="restartWorkflowBtn" class="secondary" type="button">Kembali ke awal</button>');
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("button:not(:disabled)");
  if (!button) return;
  button.classList.remove("click-feedback");
  void button.offsetWidth;
  button.classList.add("click-feedback");
});

async function api(path, body) {
  const response = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json", "X-Operator-Hub-Token": token } : {},
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store"
  });
  const data = await response.json();
  if (!response.ok) throw Error(data.error || "Permintaan gagal");
  return data;
}

function show(message, kind = "") {
  notice.textContent = message;
  notice.className = `notice ${kind}`;
}

function setUploadBusy(busy) {
  uploadBusy = busy;
  if (!busy) {
    render();
    return;
  }
  ["initialFirmwareBtn", "testUploadFirmwareBtn", "connectBtn", "disconnectBtn"].forEach((id) => { $(id).disabled = true; });
  document.querySelectorAll("#deviceTabs button").forEach((button) => { button.disabled = true; });
}

function renderUploadProgress({ percent = uploadProgress, stage, line, error = false } = {}) {
  uploadProgress = Math.max(uploadProgress, Math.min(100, Math.round(percent)));
  if (line) {
    uploadLines.push(line);
    uploadLines = uploadLines.slice(-8);
  }
  $("uploadProgress").hidden = false;
  $("uploadProgress").classList.toggle("error", error);
  $("uploadProgressPercent").textContent = `${uploadProgress}%`;
  $("uploadProgressStage").textContent = stage || "Mengunggah firmware...";
  $("uploadProgressBar").style.width = `${uploadProgress}%`;
  $("uploadProgressLog").textContent = uploadLines.join("\n") || "Menunggu log upload...";
  $("uploadProgressLog").scrollTop = $("uploadProgressLog").scrollHeight;
}

function completeUploadProgress() {
  if (uploadSuccessShown) return;
  uploadSuccessShown = true;
  renderUploadProgress({ percent: 100, stage: "Firmware, reboot, dan read-back identitas terverifikasi.", line: "VERIFIED read-back selesai" });
  window.setTimeout(() => {
    $("uploadProgress").hidden = true;
    const toast = $("uploadSuccessToast");
    toast.hidden = false;
    toast.classList.remove("show");
    void toast.offsetWidth;
    toast.classList.add("show");
    window.setTimeout(() => {
      toast.classList.remove("show");
      toast.hidden = true;
    }, 2700);
  }, 450);
}

function markReadbackVerified() {
  uploadReadbackVerified = true;
  if (uploadFlashDone || !uploadEventsReady) return completeUploadProgress();
  renderUploadProgress({ percent: 99, stage: "Read-back identitas selesai. Menunggu konfirmasi flash...", line: "READBACK verified; waiting for UPLOAD_DONE" });
}

async function openUploadEvents(device) {
  if (!token || !window.EventSource) return;
  const source = new EventSource(`/api/simple/upload-events?device=${encodeURIComponent(device)}&token=${encodeURIComponent(token)}`);
  uploadEvents = source;
  const handle = (type, event) => {
    const payload = JSON.parse(event.data || "{}");
    if (type === "upload_start") {
      return renderUploadProgress({ percent: 1, stage: "Menyiapkan firmware utama...", line: `UPLOAD_START ${payload.cmd || "flash"}` });
    }
    if (type === "upload_done") {
      uploadFlashDone = true;
      if (uploadReadbackVerified) return completeUploadProgress();
      return renderUploadProgress({ percent: 99, stage: "Flash selesai. Menunggu reboot dan read-back...", line: `UPLOAD_DONE code=${payload.code ?? 0}` });
    }
    if (type === "upload_error") return renderUploadProgress({ stage: "Upload gagal.", line: `UPLOAD_ERROR ${payload.message || "unknown error"}`, error: true });
    if (type === "upload_progress") {
      return renderUploadProgress({
        percent: Math.min(99, Number(payload.packagePercent ?? payload.filePercent)),
        stage: "Memprogram package firmware ke board...",
      });
    }
    const line = String(payload.line || "");
    renderUploadProgress({ percent: uploadProgress, stage: "Memprogram firmware utama ke board...", line });
  };
  ["upload_start", "upload_progress", "upload_done", "upload_error", "upload_line"].forEach((type) => source.addEventListener(type, (event) => handle(type, event)));
  await new Promise((resolve) => {
    const ready = () => { uploadEventsReady = true; resolve(); };
    source.addEventListener("open", ready, { once: true });
    source.addEventListener("error", ready, { once: true });
    window.setTimeout(ready, 900);
  });
}

function closeUploadEvents() {
  uploadEvents?.close();
  uploadEvents = null;
}

async function runFirmwareUpload(payload) {
  uploadProgress = 0;
  uploadLines = ["Menyiapkan upload dan menghubungkan log flash..."];
  uploadEventsReady = false;
  uploadFlashDone = false;
  uploadReadbackVerified = false;
  uploadSuccessShown = false;
  $("uploadProgress").classList.remove("error");
  $("uploadSuccessToast").hidden = true;
  renderUploadProgress({ percent: 1, stage: "Menyiapkan upload..." });
  setUploadBusy(true);
  await openUploadEvents(payload.device);
  try {
    const result = await api("/api/simple/firmware/upload", payload);
    markReadbackVerified();
    return result;
  } catch (error) {
    renderUploadProgress({ stage: `Upload gagal: ${error.message}`, line: `ERROR ${error.message}`, error: true });
    throw error;
  } finally {
    window.setTimeout(closeUploadEvents, 400);
    setUploadBusy(false);
  }
}

function requestConfirmation({ title, message, actionLabel = "Lanjutkan", phrase = "" }) {
  const dialog = $("confirmDialog");
  const phraseWrap = $("confirmPhraseWrap");
  const phraseInput = $("confirmPhraseInput");
  const error = $("confirmDialogError");
  $("confirmDialogTitle").textContent = title;
  $("confirmDialogMessage").textContent = message;
  $("confirmDialogAccept").textContent = actionLabel;
  $("confirmPhraseExpected").textContent = phrase;
  phraseWrap.hidden = !phrase;
  phraseInput.value = "";
  error.hidden = true;
  return new Promise((resolve) => {
    let settled = false;
    const finish = (approved) => {
      if (settled) return;
      settled = true;
      dialog.close();
      resolve(approved);
    };
    $("confirmDialogCancel").onclick = () => finish(false);
    $("confirmDialogAccept").onclick = () => {
      if (phrase && phraseInput.value.trim() !== phrase) {
        error.textContent = `Ketik ${phrase} dengan tepat untuk melanjutkan.`;
        error.hidden = false;
        phraseInput.focus();
        return;
      }
      finish(true);
    };
    dialog.oncancel = (event) => {
      event.preventDefault();
      finish(false);
    };
    dialog.showModal();
    if (phrase) phraseInput.focus();
  });
}

function requestFirmwareUploadOptions({ device, port, initialFirmware = false }) {
  const spec = devices[device];
  const dialog = document.createElement("dialog");
  const modelPicker = device === "gld" ? `
    <label>PAKET FIRMWARE GLD
      <select id="firmwareUploadModel"><option value="model_1">Model 1 - Board 1</option><option value="model_2">Model 2 - Board 2</option><option value="model_3">Model 3 - Board 2 v2</option><option value="gld_v2">GLD2 - Board GLD V2</option><option disabled>Model 4 - artefak belum tersedia</option></select>
      <small>Pilih package sesuai board yang akan di-flash.</small>
    </label>` : "";
  dialog.className = "firmware-upload-dialog";
  dialog.innerHTML = `<form method="dialog">
    <p class="card-kicker">UPLOAD FIRMWARE</p>
    <h2>Upload Firmware ${spec.label}</h2>
    <p id="firmwareUploadPackageLabel" class="firmware-upload-package">Package: ${spec.label} / ${device === "gld" ? "Model 1" : "default"}</p>
    <label>FIRMWARE ENVIRONMENT<select id="firmwareUploadEnvironment"><option>${spec.label}</option></select></label>
    ${modelPicker}
    <label>TARGET COM<select id="firmwareUploadPort"><option>${port}</option></select></label>
    <label class="firmware-reset"><input type="checkbox" id="firmwareUploadReset"${initialFirmware ? " checked disabled" : ""}> Reset NVS?</label>
    <p class="firmware-upload-help">${initialFirmware ? "Firmware awal selalu mereset NVS. Identitas default akan dibaca ulang setelah board reboot." : "Unchecked: retain all NVS parameters. Checked: erase NVS, then boot with all defaults embedded in this firmware."}</p>
    <p id="firmwareUploadError" class="confirm-dialog-error" hidden></p>
    <div class="confirm-dialog-actions"><button id="firmwareUploadCancel" class="secondary" value="cancel">Batal</button><button id="firmwareUploadAccept" class="primary" value="default">Upload</button></div>
  </form>`;
  document.body.append(dialog);
  return new Promise((resolve) => {
    const reset = dialog.querySelector("#firmwareUploadReset");
    const model = dialog.querySelector("#firmwareUploadModel");
    const packageLabel = dialog.querySelector("#firmwareUploadPackageLabel");
    const error = dialog.querySelector("#firmwareUploadError");
    const finish = (result) => { dialog.close(); dialog.remove(); resolve(result); };
    dialog.querySelector("#firmwareUploadCancel").onclick = () => finish(null);
    model?.addEventListener("change", () => {
      const labels = { model_1: "Model 1", model_2: "Model 2", model_3: "Model 3", gld_v2: "GLD2 - Board GLD V2" };
      packageLabel.textContent = `Package: ${spec.label} / ${labels[model.value] || "Model 1"}`;
    });
    dialog.querySelector("#firmwareUploadAccept").onclick = (event) => {
      event.preventDefault();
      const resetNvs = initialFirmware || reset.checked;
      finish({ model: model?.value || "model_1", resetNvs, resetNvsConfirmation: resetNvs ? "RESET NVS" : "" });
    };
    dialog.oncancel = (event) => { event.preventDefault(); finish(null); };
    dialog.showModal();
  });
}

function renderActivity(items = []) {
  $("activity").innerHTML = items.length
    ? items.map((item) => `<li><b>${item.time} / ${(devices[item.device] || {}).label || item.device}</b>${item.action}<br>${item.detail}</li>`).join("")
    : "<li><b>Belum ada aktivitas</b>Semua tindakan perangkat akan tercatat di sini.</li>";
}

function renderLastResult(items = []) {
  const latest = items.find((item) => item.device === active);
  $("lastResult").textContent = latest
    ? `${latest.action}: ${latest.detail}`
    : "Belum ada tindakan pada perangkat ini.";
}

function renderTestReport(report) {
  const details = $("testDeviceDetails");
  const list = $("testDeviceList");
  const summary = $("testDeviceSummary");
  const score = $("testScore");
  const testCard = $("testDeviceCard");
  if (!report) {
    details.hidden = true;
    list.replaceChildren();
    summary.textContent = "Hubungkan perangkat dahulu";
    summary.className = "";
    score.hidden = true;
    testCard.classList.remove("passed", "failed");
    return;
  }
  const suffix = report.failed ? ` / error ${report.failed}` : report.unknown ? ` / ${report.unknown} menunggu` : "";
  summary.textContent = `${report.passed}/${report.total} OK${suffix}`;
  summary.className = report.failed ? "fail" : report.unknown ? "" : "ok";
  score.hidden = false;
  score.textContent = `${report.passed}/${report.total}`;
  testCard.classList.toggle("passed", report.failed === 0 && report.unknown === 0);
  testCard.classList.toggle("failed", report.failed > 0);
  details.hidden = false;
  list.replaceChildren(...(report.checks || []).map((item) => {
    const line = document.createElement("li");
    line.className = item.ok === false ? "fail" : "";
    line.textContent = `${item.label}: ${item.ok === true ? "OK" : item.ok === false ? "Error" : "Menunggu"} - ${item.detail}`;
    return line;
  }));
}

function isReady(value) {
  return value === true || value === 1;
}

function valueInfo(info) {
  if (!info) return [];
  if (active === "gld") return [
    ["Device ID", info.deviceId], ["Target CH", info.targetChId], ["Firmware", info.firmwareVersion],
    ["STAR", info.starLora?.freqMHz ? `${info.starLora.freqMHz} MHz` : "-"],
    ["Radio", isReady(info.radioReady) ? "Ready" : info.radioReady === false || info.radioReady === 0 ? "Tidak siap" : "Menunggu"]
  ];
  if (active === "ch") return [
    ["CH ID", info.chId], ["Root Gateway", info.rootGatewayId], ["Firmware", info.firmwareVersion],
    ["STAR", info.starLora?.freqMHz ? `${info.starLora.freqMHz} MHz` : "-"],
    ["Radio STAR", isReady(info.radio?.starReady) ? "Ready" : "Tidak siap"], ["Mesh", "Fixed by design"]
  ];
  return [
    ["Gateway ID", info.gatewayId], ["Firmware", info.firmwareVersion],
    ["Radio Mesh", isReady(info.meshReady) ? "Ready" : "Tidak siap"],
    ["Wi-Fi", isReady(info.wifi) ? "Connected" : "Belum tersambung"],
    ["MQTT", isReady(info.mqtt) ? "Connected" : "Belum tersambung"]
  ];
}

function setStepState(identified) {
  const testPassed = lastTestReport && lastTestReport.failed === 0 && lastTestReport.unknown === 0;
  const steps = [...$("operatorSteps").children];
  steps.forEach((step) => step.classList.remove("done", "active"));
  if (!identified) {
    steps[0]?.classList.add("active");
  } else if (!testPassed) {
    steps[0]?.classList.add("done");
    steps[1]?.classList.add("active");
  } else if (!settingsOpened) {
    steps[0]?.classList.add("done");
    steps[1]?.classList.add("done");
    steps[2]?.classList.add("active");
  } else {
    steps[0]?.classList.add("done");
    steps[1]?.classList.add("done");
    steps[2]?.classList.add("active");
  }
  steps.forEach((step) => {
    const button = step.querySelector(".step-button");
    if (!button) return;
    const available = step.classList.contains("done") || step.classList.contains("active");
    button.disabled = !available;
    button.setAttribute("aria-current", step.classList.contains("active") ? "step" : "false");
  });
  $("settingsCard").classList.toggle("locked", !testPassed);
  $("firmwareStage").classList.toggle("locked", !testPassed);
  document.querySelector("#settingsCard .guard-badge").hidden = Boolean(testPassed);
  const reviewingEarlierStep = reviewStep > 0 && reviewStep <= 2;
  $("futureStages").hidden = !testPassed || !settingsOpened || reviewingEarlierStep;
  $("secondaryDetails").hidden = !testPassed || !settingsOpened || reviewingEarlierStep;
  const workspace = document.querySelector(".workspace");
  const simpleView = !identified || reviewStep === 1 ? "connect"
    : !testPassed || reviewStep === 2 ? "test" : "settings";
  workspace.dataset.simpleView = simpleView;
  $("devicePanel").dataset.simpleView = simpleView;
  workspace.classList.toggle("single-task", !testPassed);
  workspace.classList.toggle("review-connect", Boolean(identified && reviewStep === 1));
  workspace.classList.toggle("settings-stage", Boolean(testPassed && settingsOpened && !reviewingEarlierStep));
  $("continueBtn").hidden = !testPassed || settingsOpened;
  $("testDeviceCopy").textContent = testPassed
    ? settingsOpened ? "Test Device sudah lulus. Parameter perangkat dapat ditinjau atau diubah di tahap berikutnya." : "Perangkat lulus pemeriksaan. Tekan Lanjutkan untuk membuka tahap pengaturan."
    : "Hubungkan perangkat lalu jalankan pemeriksaan tanpa mengubah konfigurasi.";
  const next = !identified ? "Pilih COM lalu hubungkan perangkat; nama COM selalu mengikuti komputer saat ini."
    : !testPassed ? "Perangkat teridentifikasi. Lanjutkan dengan Test Device."
      : settingsOpened ? "Parameter siap ditinjau. Perangkat siap digunakan." : "Test Device lulus. Lanjutkan ke Pengaturan bila parameter perlu diubah.";
  $("nextAction").textContent = next;
  return Boolean(testPassed);
}

function render() {
  const state = overview.devices?.[active] || { device: active };
  const spec = devices[active];
  const identified = Boolean(state.connected && state.info);
  const needsInitialFirmware = Boolean(initialFirmwareRequired && state.connected && !state.info);
  const info = state.info;
  $("devicePanel").hidden = false;
  document.querySelector(".workspace").classList.toggle("connected", identified);
  document.querySelector(".workspace").classList.toggle("initial-firmware", needsInitialFirmware);
  $("deviceName").textContent = spec.name;
  $("connectionTitle").textContent = `Hubungkan ${spec.name}`;
  $("testDeviceName").textContent = spec.name;
  $("testDevicePort").textContent = identified
    ? `${state.port || "COM"} — ${spec.label} terdeteksi dan terhubung.`
    : "COM — perangkat belum terhubung";
  $("testConnectionIndicator").textContent = identified ? "● Terhubung" : "Offline";
  $("testConnectionIndicator").classList.toggle("online", identified);
  $("deviceGlyph").textContent = spec.glyph;
  $("connectionText").textContent = state.connected
    ? identified ? `${state.port || "COM"} tersambung dan teridentifikasi.` : `${state.port || "COM"} tersambung, menunggu identitas.`
    : "Belum tersambung. Pilih COM pada komputer ini untuk memulai.";
  $("connectionIndicator").textContent = identified ? "Online" : state.connected ? "Membaca identitas" : "Offline";
  $("connectionIndicator").classList.toggle("online", identified);
  $("connectBtn").disabled = Boolean(state.connected);
  $("disconnectBtn").disabled = !state.connected;
  $("statusList").innerHTML = valueInfo(info).map(([key, value]) => `<div><dt>${key}</dt><dd>${value ?? "-"}</dd></div>`).join("") || "<div><dt>Status</dt><dd>Menunggu perangkat</dd></div>";
  $("idInput").value = active === "gld" ? info?.deviceId || "" : active === "ch" ? info?.chId || "" : String(info?.gatewayId || "").replace(/^0x/i, "");
  $("freqInput").value = info?.starLora?.freqMHz ?? "";
  $("targetChInput").value = String(info?.targetChId || "").replace(/^0x/i, "");
  $("rootGatewayInput").value = active === "ch" ? String(info?.rootGatewayId || "").replace(/^0x/i, "") : "";
  $("starCard").hidden = active === "gw";
  $("saveFreqBtn").hidden = active === "gw";
  $("targetChCard").hidden = active !== "gld";
  $("saveTargetChBtn").hidden = active !== "gld";
  const isClusterHead = active === "ch";
  $("rootGatewayCard").hidden = !isClusterHead;
  $("saveRootGatewayBtn").hidden = !isClusterHead;
  $("gatewayNetworkCard").hidden = active !== "gw";
  $("testDeviceBtn").disabled = !identified || testDeviceRunning;
  $("testDeviceBtn").textContent = testDeviceRunning ? "Memeriksa…" : "Test Device";
  $("testDeviceCard").classList.toggle("testing", testDeviceRunning);
  $("testUploadFirmwareBtn").disabled = !identified;
  $("initialFirmwareCard").hidden = !needsInitialFirmware;
  $("initialFirmwarePort").textContent = `${state.port || "COM"} — ${spec.label}`;
  renderTestReport(lastTestReport);
  if (identified && !lastTestReport) {
    $("testDeviceSummary").textContent = "Siap diperiksa";
  }
  const pack = overview.packages?.[active];
  $("packageVersion").textContent = pack?.firmwareVersion
    ? `Firmware ${pack.firmwareVersion} / ${pack.environment} terdeteksi`
    : "Versi firmware tidak terbaca";
  const testPassed = setStepState(identified);
  $("readyDeviceCopy").textContent = testPassed
    ? "Test Device lulus. Perangkat siap digunakan."
    : "Selesaikan Test Device untuk memastikan perangkat siap digunakan.";
  renderActivity(overview.activity);
  renderLastResult(overview.activity);
}

async function loadPorts() {
  try {
    const data = await api(`/api/simple/ports?device=${active}`);
    const ports = Array.isArray(data.ports || data) ? data.ports || data : [];
    $("portSelect").innerHTML = '<option value="">Pilih COM port pada komputer ini</option>' + ports.map((port) => {
      const value = typeof port === "string" ? port : port.path || port.port;
      const detail = typeof port === "string" ? "" : port.description || "";
      return `<option value="${value}" title="${detail}">${value}${detail ? ` - ${detail}` : ""}</option>`;
    }).join("");
  } catch {
    $("portSelect").innerHTML = '<option value="">COM tidak tersedia</option>';
  }
}

async function refresh(query = false) {
  overview = await api("/api/simple/overview");
  render();
  if (query && overview.devices?.[active]?.connected) {
    overview.devices[active] = await api("/api/simple/refresh", { device: active });
    render();
  }
}

async function action(path, body, success) {
  try {
    show("Memproses - menunggu ACK dan read-back perangkat...");
    await api(path, body);
    show(success, "ok");
    await refresh(true);
  } catch (error) {
    show(error.message, "bad");
  }
}

function buildTabs() {
  const tabs = $("deviceTabs");
  tabs.innerHTML = Object.entries(devices).map(([id, device]) => `<button class="device-tab ${id === active ? "active" : ""}" data-device="${id}" type="button"><span class="glyph">${device.glyph}</span><span><strong>${device.label}</strong><small>${device.name}</small></span></button>`).join("");
  tabs.onclick = async (event) => {
    const selected = event.target.closest("[data-device]")?.dataset.device;
    if (!selected) return;
    active = selected;
    lastTestReport = testReportsByDevice[active] || null;
    initialFirmwareRequired = false;
    settingsOpened = false;
    reviewStep = 0;
    [...tabs.children].forEach((tab) => tab.classList.toggle("active", tab.dataset.device === active));
    await loadPorts();
    render();
  };
}

async function testDevice() {
  if (testDeviceRunning) return;
  testDeviceRunning = true;
  try {
    reviewStep = 2;
    show("Memeriksa kesiapan perangkat — menunggu respons Boot Report…", "waiting");
    render();
    const result = await api("/api/simple/test-device", { device: active });
    lastTestReport = result.report;
    testReportsByDevice[active] = result.report;
    render();
    show(result.report.failed ? `Test Device selesai: ${result.report.passed}/${result.report.total} OK, error ${result.report.failed}.` : `Test Device selesai: ${result.report.passed}/${result.report.total} OK.`, result.report.failed ? "bad" : "ok");
    await refresh();
  } catch (error) {
    show(error.message, "bad");
  } finally {
    testDeviceRunning = false;
    render();
  }
}

function navigateToStep(stepNumber) {
  const step = $("operatorSteps").querySelector(`[data-step="${stepNumber}"]`)?.closest("li");
  if (!step || (!step.classList.contains("done") && !step.classList.contains("active"))) return;
  const testPassed = Boolean(lastTestReport && lastTestReport.failed === 0 && lastTestReport.unknown === 0);
  if (stepNumber === 1) {
    reviewStep = 1;
  } else if (stepNumber === 2) {
    reviewStep = 2;
  } else if (stepNumber === 3 && testPassed) {
    settingsOpened = true;
    reviewStep = 3;
  } else {
    return;
  }
  render();
  const target = stepNumber === 1 ? document.querySelector(".connect-card")
    : stepNumber === 2 ? $("testDeviceCard") : $("settingsCard");
  target?.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function connectDevice() {
  try {
    settingsOpened = false;
    reviewStep = 0;
    show("Menghubungkan dan membaca identitas perangkat...");
    const result = await api("/api/simple/connect", { device: active, port: $("portSelect").value });
    initialFirmwareRequired = Boolean(result.needsInitialFirmware || (result.connected && !result.info));
    await refresh();
    if (initialFirmwareRequired) {
      show(`${devices[active].label} terhubung, tetapi firmware tidak terdeteksi. Upload Firmware Awal diperlukan.`, "bad");
      return;
    }
    show(`${devices[active].label} tersambung. Menjalankan Test Device otomatis...`);
    await testDevice();
  } catch (error) {
    show(error.message, "bad");
  }
}

async function initialFirmwareUpload() {
  const port = overview.devices?.[active]?.port || $("portSelect").value;
  if (!port) return show("Pilih dan hubungkan COM board baru terlebih dahulu.", "bad");
  const options = await requestFirmwareUploadOptions({ device: active, port, initialFirmware: true });
  if (!options) return show("Upload firmware awal dibatalkan.");
  try {
    show("Mengunggah firmware awal; progres dan log flash ditampilkan di bawah.");
    await runFirmwareUpload({ device: active, port, initialFirmware: true, ...options });
    initialFirmwareRequired = false;
    await refresh(true);
    show("Firmware awal terverifikasi. Menjalankan Test Device...");
    await testDevice();
  } catch (error) {
    show(error.message, "bad");
  }
}

async function manualFirmwareUpload() {
  const port = overview.devices?.[active]?.port || $("portSelect").value;
  if (!port) return show("Hubungkan dan identifikasi perangkat terlebih dahulu.", "bad");
  const options = await requestFirmwareUploadOptions({ device: active, port });
  if (!options) return show("Upload firmware dibatalkan.");
  try {
    show("Mengunggah firmware; progres dan log flash ditampilkan di bawah.");
    await runFirmwareUpload({ device: active, port, ...options });
    await refresh(true);
    show("Firmware terverifikasi. Menjalankan Test Device ulang...");
    await testDevice();
  } catch (error) {
    show(error.message, "bad");
  }
}

async function init() {
  prepareThreeStepWorkflow();
  if (simulationMode === "ch-com6" || simulationMode === "ch-com6-new") {
    const unprogrammed = simulationMode === "ch-com6-new";
    active = "ch";
    initialFirmwareRequired = unprogrammed;
    overview = {
      devices: {
        gld: { device: "gld", connected: false },
        ch: { device: "ch", connected: unprogrammed, port: "COM6" },
        gw: { device: "gw", connected: false }
      },
      packages: { ch: { firmwareVersion: "preview", environment: "ch" } },
      activity: []
    };
    buildTabs();
    render();
    $("portSelect").innerHTML = '<option value="COM6" selected>COM6 - USB Serial CH340 (COM6)</option>';
    $("connectBtn").disabled = true;
    $("disconnectBtn").disabled = true;
    $("initialFirmwareBtn").onclick = initialFirmwareUpload;
    $("runtimeText").textContent = unprogrammed ? "Simulasi board baru" : "Simulasi CH / COM6";
    show(unprogrammed ? "Simulasi: CH pada COM6 terhubung, tetapi firmware belum terdeteksi. Tidak ada koneksi serial yang dibuka." : "Simulasi CH pada COM6 - tidak ada koneksi serial yang dibuka.", "ok");
    return;
  }
  const boot = await api("/api/simple/bootstrap");
  token = boot.apiToken;
  show("Menyudahi sesi serial sebelumnya...");
  await Promise.allSettled(Object.keys(devices).map((device) => api("/api/simple/disconnect", { device })));
  buildTabs();
  $("connectBtn").onclick = connectDevice;
  $("disconnectBtn").onclick = () => action("/api/simple/disconnect", { device: active }, "Koneksi perangkat ditutup.");
  $("restartBtn").onclick = async () => {
    const approved = await requestConfirmation({
      title: `Restart ${devices[active].label}?`,
      message: "Koneksi serial akan terputus sesaat saat board melakukan boot ulang.",
      actionLabel: "Restart board"
    });
    if (approved) await action("/api/simple/restart", { device: active }, "Perintah restart dikirim.");
  };
  $("initialFirmwareBtn").onclick = initialFirmwareUpload;
  $("testDeviceBtn").onclick = testDevice;
  $("testUploadFirmwareBtn").onclick = manualFirmwareUpload;
  $("continueBtn").onclick = () => {
    settingsOpened = true;
    reviewStep = 3;
    render();
    $("settingsCard").scrollIntoView({ behavior: "smooth", block: "start" });
  };
  $("restartWorkflowBtn").onclick = () => {
    settingsOpened = false;
    reviewStep = 1;
    render();
    document.querySelector(".connect-card")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  $("operatorSteps").onclick = (event) => {
    const stepNumber = Number(event.target.closest(".step-button")?.dataset.step);
    if (stepNumber) navigateToStep(stepNumber);
  };
  $("saveIdBtn").onclick = () => action("/api/simple/config/id", { device: active, value: $("idInput").value }, "ID tersimpan dan terverifikasi.");
  $("saveFreqBtn").onclick = () => action("/api/simple/config/star-frequency", { device: active, freqMHz: $("freqInput").value }, "STAR Frequency tersimpan dan terverifikasi.");
  $("saveTargetChBtn").onclick = () => action("/api/simple/config/target-ch", { device: "gld", value: $("targetChInput").value }, "Target CH tersimpan dan terverifikasi.");
  $("saveRootGatewayBtn").onclick = () => action("/api/simple/config/root-gateway", { device: "ch", value: $("rootGatewayInput").value }, "Root Gateway tersimpan dan terverifikasi.");
  $("saveWifiBtn").onclick = () => action("/api/simple/config/wifi", { device: "gw", ssid: $("wifiSsidInput").value, password: $("wifiPasswordInput").value }, "Wi-Fi tersimpan dan terverifikasi.");
  $("saveMqttBtn").onclick = () => action("/api/simple/config/mqtt", { device: "gw", host: $("mqttHostInput").value, port: $("mqttPortInput").value, username: $("mqttUsernameInput").value, password: $("mqttPasswordInput").value }, "MQTT tersimpan dan terverifikasi.");
  $("expertBtn").onclick = () => location.assign(`http://${location.hostname}:${active === "gld" ? 5174 : active === "ch" ? 5273 : 5373}/`);
  await refresh();
  await loadPorts();
  $("runtimeText").textContent = "Runtime siap";
  show("Sesi baru siap. Pilih COM pada komputer ini untuk memulai.");
}

init().catch((error) => show(error.message, "bad"));
