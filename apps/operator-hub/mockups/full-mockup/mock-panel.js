/*
  Reviewer panel for the Operator Hub mockup. Lives outside the production UI.
  It boots the wrapped hub.js, switches scenarios IN PLACE (reset mock, restore
  the pristine Hub DOM, boot again — no reload/navigation, so it also works in
  sandboxed previews), intercepts links that would leave the Hub (Expert
  Console, GLD Operator hotspot), and can auto-play a preset to reach a stage.
*/
(() => {
  "use strict";
  const mock = window.__operatorHubMock;
  if (!mock) return;
  const { DEFAULTS } = mock;
  const $ = (id) => document.getElementById(id);
  let builtIn = null;
  try { builtIn = new URLSearchParams(location.search).get("simulate"); } catch { builtIn = null; }

  const OPTIONS = {
    gld: [["normal", "Normal — firmware ada, test lulus"], ["fresh", "Board baru — tanpa firmware"], ["fail", "Test gagal — MCP4725/DAC/Sensor"], ["pending", "Test belum lengkap — Sensor menunggu"], ["alarm-locked", "Kontrak alarm tidak lengkap"]],
    ch: [["normal", "Normal — firmware ada, test lulus"], ["fresh", "Board baru — tanpa firmware"], ["fail", "Test gagal — Radio Mesh"]],
    gw: [["normal", "Normal — Wi-Fi & MQTT tersambung"], ["fresh", "Board baru — tanpa firmware"], ["fail", "Test gagal — MQTT belum tersambung"]],
    gwfw: [["non_tls", "Firmware MQTT non-TLS"], ["tls", "Firmware MQTT over TLS (TLS-capable)"], ["legacy", "Firmware lama — transport tidak dilaporkan"]],
    drive: [["steady_24v", "Steady 24 V (perangkat eksternal 1 s ON/OFF)"], ["gpio41_high", "GLD1 GPIO41 active-high"], ["gpio41_pullup", "GLD1 GPIO41 active-low + ULN2003 pull-up"]],
    inference: [["0", "Tidak aktif"], ["1", "AKTIF"]],
    upload: [["success", "Sukses + read-back terverifikasi"], ["error", "Gagal di tengah flash"]],
    speed: [["normal", "Realistis"], ["fast", "Cepat (×4)"]]
  };
  const LABELS = {
    gld: "Kondisi GLD", ch: "Kondisi Cluster Head", gw: "Kondisi Gateway", gwfw: "Firmware Gateway",
    drive: "Output alarm fisik GLD", inference: "Alarm inferensi GLD", upload: "Hasil upload firmware", speed: "Kecepatan simulasi"
  };
  const PRESETS = [
    ["Mulai dari awal", "Semua perangkat normal, tahap Hubungkan.", {}],
    ["GLD → Konfigurasi", "GLD otomatis terhubung, lulus test, buka tahap 3.", { preset: "gld-config" }],
    ["GLD test gagal", "Boot Report 3/6 dengan error MCP4725/DAC/Sensor.", { gld: "fail", preset: "gld-test" }],
    ["GLD board baru", "COM terhubung tanpa firmware → Upload Firmware Awal.", { gld: "fresh", preset: "gld-connect" }],
    ["GLD alarm MANUAL", "GLD1 pull-up; uji mode MANUAL dan Test Alarm ON/OFF.", { drive: "gpio41_pullup", preset: "gld-config" }],
    ["CH → Konfigurasi", "CH lulus test; ID, STAR, Root Gateway.", { preset: "ch-config" }],
    ["CH board baru", "CH tanpa firmware; pilih Rectangle/Circle.", { ch: "fresh", preset: "ch-connect" }],
    ["Gateway TLS", "Gateway firmware TLS; isi Root CA + NTP.", { gwfw: "tls", preset: "gw-config" }],
    ["Gateway MQTT gagal", "Test Gateway gagal karena MQTT belum tersambung.", { gw: "fail", preset: "gw-test" }],
    ["Upload gagal", "GLD terhubung; upload firmware berhenti dengan error.", { upload: "error", preset: "gld-test" }]
  ];

  function hashFor(values) {
    const merged = { ...DEFAULTS, ...values };
    const params = new URLSearchParams();
    Object.entries(merged).forEach(([key, value]) => { if (value !== DEFAULTS[key]) params.set(key, value); });
    return params.toString();
  }
  // Pristine copies of every Hub region hub.js mutates, captured before first boot.
  const REGIONS = ["header.topbar", "main.shell", "#confirmDialog", "#uploadSuccessToast"];
  const snapshots = REGIONS.map((selector) => document.querySelector(selector)?.outerHTML || "");
  function restoreHubDom() {
    document.querySelectorAll(".firmware-upload-dialog").forEach((dialog) => { try { dialog.close(); } catch { /* not open */ } dialog.remove(); });
    REGIONS.forEach((selector, index) => {
      const current = document.querySelector(selector);
      const template = document.createElement("template");
      template.innerHTML = snapshots[index];
      if (current && template.content.firstElementChild) current.replaceWith(template.content.firstElementChild);
    });
  }

  let run = 0;
  function boot(values, simulate = null) {
    run += 1;
    builtIn = simulate;
    window.__mockSimulate = simulate;
    mock.configure(values);
    try { history.replaceState(null, "", `#${hashFor(values)}`); } catch { /* sandboxed preview: URL is fixed */ }
    if (run > 1) restoreHubDom();
    renderChrome();
    window.scrollTo(0, 0);
    window.__bootHub();
    if (mock.cfg.preset && !simulate) autoplay(mock.cfg.preset, run);
  }
  const go = (values) => { setPanel(false); boot(values); };

  // ------------------------------------------------------------- drawer DOM
  const panel = document.createElement("aside");
  panel.id = "mockPanel";
  panel.className = "mock-panel";
  panel.setAttribute("aria-label", "Panel peninjau mockup");
  panel.hidden = true;
  const panelHtml = () => `
    <div class="mock-panel-head">
      <div><p class="card-kicker">MOCKUP / PANEL PENINJAU</p><h2>Skenario simulasi</h2></div>
      <button id="mockPanelClose" class="mock-icon" type="button" aria-label="Tutup panel">&times;</button>
    </div>
    <p class="mock-note">Semua respons berasal dari simulasi di browser. Tidak ada port COM, firmware, NVS, MQTT, data, atau perangkat nyata yang disentuh.</p>
    <section><h3>Lompat cepat</h3><div class="mock-presets">${PRESETS.map(([title, detail], i) => `<button type="button" data-preset="${i}"><b>${title}</b><small>${detail}</small></button>`).join("")}</div></section>
    <section><h3>Kondisi kustom</h3><div id="mockForm" class="mock-form">${Object.keys(OPTIONS).map((key) => `<label>${LABELS[key]}<select name="${key}">${OPTIONS[key].map(([value, label]) => `<option value="${value}"${mock.cfg[key] === value ? " selected" : ""}>${label}</option>`).join("")}</select></label>`).join("")}
      <div class="mock-form-actions"><button type="button" id="mockReset" class="secondary">Reset</button><button type="button" id="mockApply" class="primary">Terapkan skenario</button></div></div></section>
    <section><h3>Simulasi bawaan hub.js</h3><p class="mock-note">Mode <code>?simulate=</code> yang sudah ada di aplikasi produksi (tanpa backend).</p><div class="mock-links">
      <button type="button" data-simulate="ch-com6">CH pada COM6</button><button type="button" data-simulate="ch-com6-new">CH COM6 board baru</button>${builtIn ? '<button type="button" data-simulate="">Kembali ke mockup penuh</button>' : ""}</div></section>
    <details class="mock-coverage"><summary>Cakupan alur yang direpresentasikan</summary><ul>
      <li>Pilih perangkat GLD / CH / Gateway, daftar COM per perangkat, Connect / Disconnect</li>
      <li>Connect → identitas terbaca → Test Device otomatis (Boot Report GLD 6 cek, CH 4 cek, Gateway 4 cek)</li>
      <li>Board tanpa firmware → kartu Upload Firmware Awal (NVS selalu di-reset)</li>
      <li>Dialog Upload Firmware: paket GLD, bentuk board CH/GW, transport MQTT GW, Reset NVS, peringatan downgrade GLD1 v0.8.38, larangan Hotspot + Reset</li>
      <li>Progres flash + log esptool, read-back, toast Upload Success, upload gagal, verifikasi hotspot tertunda</li>
      <li>Stepper 3 tahap dengan navigasi kembali; Lanjutkan ke Konfigurasi; Kembali ke awal</li>
      <li>Konfigurasi: Device ID, STAR frequency, Target CH (GLD), Root Gateway (CH), Wi-Fi &amp; MQTT non-TLS/TLS (Gateway) dengan validasi rentang</li>
      <li>Alarm fisik GLD: AUTO/MANUAL (konfirmasi ketik MANUAL), Test Alarm ON/OFF, 3 varian output, kontrak terkunci</li>
      <li>Restart perangkat (konfirmasi), aktivitas terbaru, ringkasan perangkat, Expert Console (dicegat)</li>
    </ul></details>`;
  const launcher = document.createElement("button");
  launcher.type = "button";
  launcher.className = "mock-launcher";
  launcher.innerHTML = "<span>MOCKUP</span> Panel peninjau";
  const banner = document.createElement("div");
  banner.className = "mock-banner";
  banner.setAttribute("role", "note");

  function describe() {
    if (builtIn) return `Simulasi bawaan: ${builtIn}`;
    const cfg = mock.cfg;
    const changed = Object.keys(OPTIONS).filter((key) => cfg[key] !== DEFAULTS[key]);
    return changed.length ? changed.map((key) => `${LABELS[key]}: ${OPTIONS[key].find(([v]) => v === cfg[key])?.[1] || cfg[key]}`).join(" · ") : "Skenario: semua normal";
  }

  // --------------------------------------------------------- expert modal
  const modal = document.createElement("dialog");
  modal.className = "confirm-dialog mock-dialog";
  modal.innerHTML = `<div class="confirm-dialog-card"><p class="card-kicker">MOCKUP / NAVIGASI KELUAR</p><h2 id="mockDialogTitle"></h2><p id="mockDialogBody"></p><p class="mock-dialog-url"><code id="mockDialogUrl"></code></p><div class="confirm-dialog-actions"><button type="button" class="primary" id="mockDialogOk">Mengerti</button></div></div>`;

  function openExternal(title, body, url) {
    $("mockDialogTitle").textContent = title;
    $("mockDialogBody").textContent = body;
    $("mockDialogUrl").textContent = url;
    modal.showModal();
  }

  window.addEventListener("click", (event) => {
    if (event.target.closest("#expertBtn")) {
      event.preventDefault();
      event.stopPropagation();
      const device = document.querySelector("#deviceTabs .device-tab.active")?.dataset.device || "gld";
      const port = device === "gld" ? 5174 : device === "ch" ? 5273 : 5373;
      const name = { gld: "GLD Operator", ch: "CH Operator", gw: "Gateway Operator" }[device];
      openExternal(`Expert Console — ${name}`, `Di aplikasi nyata tombol ini membuka konsol ${name} (bridge terpisah, mode lanjutan: serial log, perintah mentah, Mesh). Konsol tersebut di luar cakupan mockup Simple Hub ini.`, `http://127.0.0.1:${port}/`);
      return;
    }
    const link = event.target.closest("#notice a");
    if (link) {
      event.preventDefault();
      event.stopPropagation();
      openExternal("Verifikasi hotspot di GLD Operator", "Di aplikasi nyata, laptop disambungkan ke Wi-Fi GLD-DATASET-…, lalu GLD Operator > Dataset Wireless > Connect GLD memverifikasi firmware hotspot.", link.href);
    }
  }, true);

  // --------------------------------------------------------------- presets
  let autoplayRun = 0;
  const waitFor = async (check, timeout = 20000) => {
    const end = Date.now() + timeout;
    const mine = autoplayRun;
    while (Date.now() < end) {
      if (mine !== run) return false; // scenario switched meanwhile
      if (check()) return true;
      await new Promise((resolve) => setTimeout(resolve, 120));
    }
    return false;
  };
  const visible = (el) => Boolean(el && !el.hidden && el.offsetParent !== null);

  async function autoplay(preset, token) {
    autoplayRun = token;
    const [device, stage] = preset.split("-");
    if (!["gld", "ch", "gw"].includes(device)) return;
    if (!(await waitFor(() => $("runtimeText")?.textContent === "Runtime siap"))) return;
    if (!(await waitFor(() => document.querySelector(`#deviceTabs [data-device="${device}"]`)))) return;
    document.querySelector(`#deviceTabs [data-device="${device}"]`).click();
    await waitFor(() => [...$("portSelect").options].some((o) => o.value && o.value !== "COM1") && $("connectionTitle").textContent.includes(
      { gld: "Gas Leak Detector", ch: "Cluster Head", gw: "Network Gateway" }[device]));
    if (token !== run) return;
    const select = $("portSelect");
    select.value = [...select.options].find((o) => o.value && o.value !== "COM1").value;
    $("connectBtn").click();
    if (stage !== "config") return;
    if (await waitFor(() => visible($("continueBtn")), 30000)) $("continueBtn").click();
  }

  // ------------------------------------------------------------------ wire
  function setPanel(open) {
    panel.hidden = !open;
    launcher.setAttribute("aria-expanded", String(open));
  }
  function renderChrome() {
    banner.innerHTML = `<b>MOCKUP</b><span>Representasi Operator Hub — simulasi browser, tidak terhubung ke perangkat.</span><span class="mock-banner-scenario">${describe()}</span>`;
    panel.innerHTML = panelHtml();
    $("mockPanelClose").onclick = () => setPanel(false);
    panel.querySelectorAll("[data-preset]").forEach((button) => {
      button.onclick = () => go(PRESETS[Number(button.dataset.preset)][2]);
    });
    panel.querySelectorAll("[data-simulate]").forEach((button) => {
      button.onclick = () => { setPanel(false); boot({ ...mock.cfg, preset: "" }, button.dataset.simulate || null); };
    });
    // Plain buttons, not a <form>: sandboxed previews block form submission.
    $("mockApply").onclick = () => go(Object.fromEntries([...panel.querySelectorAll("#mockForm select")].map((select) => [select.name, select.value])));
    $("mockReset").onclick = () => go({});
  }

  document.body.prepend(banner);
  document.body.append(launcher, panel, modal);
  launcher.onclick = () => setPanel(panel.hidden);
  $("mockDialogOk").onclick = () => modal.close();
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !panel.hidden) setPanel(false); });
  boot({ ...mock.cfg }, builtIn);
})();
