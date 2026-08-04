const devices = {
  gld: { label: "GLD", name: "Gas Leak Detector", glyph: "G" },
  ch: { label: "CH", name: "Cluster Head", glyph: "C" },
  gw: { label: "Gateway", name: "Network Gateway", glyph: "W" }
};

let token = "";
let active = "gld";
let overview = {};
let lastTestReport = null;
const $ = (id) => document.getElementById(id);
const notice = $("notice");

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
  steps[0]?.classList.add("done");
  if (!identified) {
    steps[1]?.classList.add("active");
  } else if (!testPassed) {
    steps[1]?.classList.add("done");
    steps[2]?.classList.add("active");
  } else {
    steps[1]?.classList.add("done");
    steps[2]?.classList.add("done");
    steps[3]?.classList.add("active");
  }
  $("settingsCard").classList.toggle("locked", !testPassed);
  $("firmwareStage").classList.toggle("locked", !testPassed);
  $("futureStages").hidden = !testPassed;
  $("secondaryDetails").hidden = !testPassed;
  document.querySelector(".workspace").classList.toggle("single-task", !testPassed);
  $("continueBtn").hidden = !testPassed;
  $("testDeviceCopy").textContent = testPassed
    ? "Perangkat lulus pemeriksaan. Anda dapat mengatur parameter atau lanjut menggunakan perangkat."
    : "Hubungkan perangkat lalu jalankan pemeriksaan tanpa mengubah konfigurasi.";
  const next = !identified ? "Pilih COM lalu hubungkan perangkat; nama COM selalu mengikuti komputer saat ini."
    : !testPassed ? "Perangkat teridentifikasi. Lanjutkan dengan Test Device."
      : "Perangkat siap. Atur parameter hanya bila diperlukan.";
  $("nextAction").textContent = next;
  return Boolean(testPassed);
}

function render() {
  const state = overview.devices?.[active] || { device: active };
  const spec = devices[active];
  const identified = Boolean(state.connected && state.info);
  const info = state.info;
  $("devicePanel").hidden = false;
  document.querySelector(".workspace").classList.toggle("connected", identified);
  $("deviceName").textContent = spec.name;
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
  $("rootGatewayInput").value = String(info?.rootGatewayId || "").replace(/^0x/i, "");
  $("starCard").hidden = active === "gw";
  $("saveFreqBtn").hidden = active === "gw";
  $("targetChCard").hidden = active !== "gld";
  $("saveTargetChBtn").hidden = active !== "gld";
  $("rootGatewayCard").hidden = active !== "ch";
  $("saveRootGatewayBtn").hidden = active !== "ch";
  $("gatewayNetworkCard").hidden = active !== "gw";
  $("testDeviceBtn").disabled = !identified;
  renderTestReport(lastTestReport);
  if (identified && !lastTestReport) {
    $("testDeviceSummary").textContent = "Siap diperiksa";
  }
  const pack = overview.packages?.[active];
  const uploadLabel = pack?.firmwareVersion ? `Upload ${spec.label} ${pack.firmwareVersion} ke ${state.port || "COM"}` : `Upload firmware ${spec.label}`;
  $("packageVersion").textContent = pack?.firmwareVersion ? `Latest / ${pack.firmwareVersion} / ${pack.environment}` : "Package terbaru tidak tersedia";
  $("uploadBtn").textContent = uploadLabel;
  const testPassed = setStepState(identified);
  $("uploadBtn").disabled = !testPassed;
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
    lastTestReport = null;
    [...tabs.children].forEach((tab) => tab.classList.toggle("active", tab.dataset.device === active));
    await loadPorts();
    render();
  };
}

async function upload() {
  const port = overview.devices?.[active]?.port || $("portSelect").value;
  const reset = $("resetNvs").checked;
  if (!port) return show("Hubungkan dan identifikasi perangkat terlebih dahulu.", "bad");
  if (!confirm(`Upload firmware ${devices[active].label} terbaru ke ${port}?${reset ? " NVS AKAN DIHAPUS." : " NVS tidak akan di-reset."}`)) return;
  let confirmation = "";
  if (reset) {
    confirmation = prompt("Ketik RESET NVS untuk melanjutkan.") || "";
    if (confirmation !== "RESET NVS") return show("Reset NVS dibatalkan.", "bad");
  }
  await action("/api/simple/firmware/upload", { device: active, port, resetNvs: reset, resetNvsConfirmation: confirmation }, reset ? "Upload selesai; NVS telah di-reset dan firmware terverifikasi." : "Upload selesai; NVS tetap tersimpan dan firmware terverifikasi.");
}

async function testDevice() {
  try {
    show("Menjalankan pemeriksaan kesiapan perangkat...");
    const result = await api("/api/simple/test-device", { device: active });
    lastTestReport = result.report;
    render();
    show(result.report.failed ? `Test Device selesai: ${result.report.passed}/${result.report.total} OK, error ${result.report.failed}.` : `Test Device selesai: ${result.report.passed}/${result.report.total} OK.`, result.report.failed ? "bad" : "ok");
    await refresh();
  } catch (error) {
    show(error.message, "bad");
  }
}

async function connectDevice() {
  try {
    show("Menghubungkan dan membaca identitas perangkat...");
    await api("/api/simple/connect", { device: active, port: $("portSelect").value });
    await refresh();
    show(`${devices[active].label} tersambung. Menjalankan Test Device otomatis...`);
    await testDevice();
  } catch (error) {
    show(error.message, "bad");
  }
}

async function init() {
  const boot = await api("/api/simple/bootstrap");
  token = boot.apiToken;
  show("Menyudahi sesi serial sebelumnya...");
  await Promise.allSettled(Object.keys(devices).map((device) => api("/api/simple/disconnect", { device })));
  buildTabs();
  $("connectBtn").onclick = connectDevice;
  $("disconnectBtn").onclick = () => action("/api/simple/disconnect", { device: active }, "Koneksi perangkat ditutup.");
  $("refreshBtn").onclick = () => refresh(true).catch((error) => show(error.message, "bad"));
  $("restartBtn").onclick = () => confirm(`Restart ${devices[active].label} sekarang?`) && action("/api/simple/restart", { device: active }, "Perintah restart dikirim.");
  $("uploadBtn").onclick = upload;
  $("testDeviceBtn").onclick = testDevice;
  $("continueBtn").onclick = () => {
    const card = $("settingsCard");
    card.open = true;
    card.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  $("settingsCard").addEventListener("toggle", (event) => {
    if ($("settingsCard").classList.contains("locked") && event.currentTarget.open) {
      event.currentTarget.open = false;
      show("Selesaikan Test Device sebelum membuka pengaturan.", "bad");
    }
  });
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
