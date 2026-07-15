# GLD Operator Design — "Manifold" Rebuild

Last updated: 2026-07-15 (full ground-up UI rebuild, revision 2 — see §0)

## 0. Why a second full rebuild

The 2026-07-14 rebuild (amber/near-black instrument-panel theme, horizontal
tab rail) was replaced once already on 2026-07-15 with a light "Clinical Lab"
theme, collapsible left sidebar, and per-tab settings drawers. The operator
using this app daily found that second look generic and asked for a full,
different visual identity — not another incremental reskin. This document is
the spec for that third visual system, codenamed **Manifold** (grounded in
the actual subject: a Pertamina gas-pipeline instrument cluster), built with
a genuinely different layout shape (no left sidebar at all — see §4) so it
reads as a distinct app, not a recolor of the previous one.

**Hard constraint carried over from both prior revisions:** every feature
that already works against the unchanged `bridge.py` REST/SSE contract must
keep working. Only the browser-side markup, CSS, and DOM-facing wiring
change. See §8 for the full preserved-feature checklist and §9 for what is
genuinely new in this revision.

## 1. Ringkasan

GLD Operator adalah aplikasi operator PC untuk mengoperasikan satu GLD aktif
(dari fleet hingga 8 slot) melalui serial COM dan MQTT dataset. Stack tetap
ringan dan tanpa build step:

- `index.html` — struktur UI, dirombak total di revisi ini.
- `style.css` (entry) + `css/*.css` — design system baru "Manifold", dirombak
  total (lihat §5).
- `js/*.js` — modul ES native. Modul logika bisnis (`dataset.js`,
  `nulling.js`, `firmware.js`, `fleet.js`, `security.js`, `chart.js`,
  `bridge-client.js`, `serial-protocol.js`, `mock.js`) **tidak ditulis ulang**
  — hanya markup/ID yang mereka rujuk yang direstrukturisasi seperlunya.
  `ui.js`, `main.js`, `theme.js` disesuaikan untuk IA baru (lihat §7).
- `bridge.py` — **tidak disentuh sama sekali** di revisi ini. Kontrak
  REST/SSE persis sama dengan yang didokumentasikan di §11-§12 (dipertahankan
  dari revisi sebelumnya, backend tidak berubah).

Target tetap operator bench Windows yang memakai GLD di COM port lokal.

## 2. Tujuan revisi ini

- Identitas visual yang benar-benar baru dan bisa dibedakan sekilas dari dua
  revisi sebelumnya — bukan variasi warna dari layout yang sama.
- Struktur navigasi baru: **tanpa sidebar kiri permanen**. Kontrol yang tidak
  perlu selalu terlihat (Fleet, Commands, Device Mode) dipindah ke satu
  **Ops Panel** yang slide-over dari kanan, dibuka lewat satu tombol di
  topbar. Ini pola show/hide yang sama semangatnya dengan permintaan
  sebelumnya, tapi bentuknya dibalik (kanan, bukan kolom kiri permanen) agar
  workspace dapat lebar penuh secara default.
- Navigasi tab utama jadi segmented pill horizontal langsung di bawah
  instrument strip, dengan urutan tetap: **Running, Dataset, Nulling, Log,
  Expert** (Firmware Upload tetap di dalam Expert, sesuai revisi sebelumnya).
- Settings per-tab (Running/Dataset/Nulling) tetap ada sebagai drawer kanan
  (pola yang sudah terbukti berguna dari revisi sebelumnya), tapi memakai
  mekanisme drawer yang **sama persis** dengan Ops Panel dan Port Setup — satu
  komponen drawer dipakai ulang di lima tempat, bukan lima pola berbeda.
  Ini juga jadi elemen tanda tangan visual: setiap panel sekunder di app selalu
  muncul dari kanan dengan header yang sama.
- Dark/Light theme toggle dipertahankan (lihat §5.4), localStorage persist
  seperti sebelumnya.
- **Poll interval GLD tidak lagi dipatok ke 1 detik** (lihat §9.1) — operator
  bisa mengatur intervalnya, default mengikuti kecepatan akuisisi asli GLD.

## 3. Non-goals

Tidak berubah dari revisi sebelumnya:

- Bukan aplikasi Electron/desktop bundling besar, tanpa build step (native
  ES modules, `<script type="module">`).
- Bukan database server, bukan MQTT broker produksi.
- Bukan compiler firmware custom.
- Fleet tetap "1 active slot dengan detail penuh + ringkasan slot lain",
  bukan N dashboard paralel (lihat riwayat keputusan di git history /
  `apps/gld-operator-backup/design.md` §26 untuk rasionalnya, masih berlaku).

## 4. Layout shape — kenapa tanpa sidebar kiri

Dua revisi sebelumnya sama-sama memakai kolom kiri permanen (baik berisi tab
rail vertikal maupun panel Fleet/Commands/Mode). Supaya revisi ini terasa
benar-benar berbeda, bentuk dasarnya dibalik:

```text
┌───────────────────────────────────────────────────────────┐
│ Instrument strip: brand · live gauges · alarm · Ops Panel  │  <- always visible, thin
├───────────────────────────────────────────────────────────┤
│      [ Running ] [ Dataset ] [ Nulling ] [ Log ] [ Expert ] │  <- segmented pill nav, centered
├───────────────────────────────────────────────────────────┤
│                                                             │
│                     workspace (full width)                 │
│                                                             │
└───────────────────────────────────────────────────────────┘
```

Klik "Ops Panel" (topbar) atau gear icon per-tab membuka drawer kanan yang
sama:

```text
┌───────────────────────────────────────────┬───────────────┐
│                                           │  DRAWER        │
│              workspace (dimmed)          │  header        │
│                                           │  content       │
│                                           │  ...           │
└───────────────────────────────────────────┴───────────────┘
```

Workspace tidak pernah kehilangan lebar secara permanen (drawer mengambang di
atas, bukan mendorong grid seperti kolom sidebar sebelumnya) — ini juga
menyederhanakan CSS dibanding revisi sebelumnya yang punya
`grid-template-columns` yang berubah-ubah.

## 5. Design system "Manifold"

### 5.1 Palet

Berangkat dari subjek aslinya: instrumen bench untuk mendeteksi kebocoran gas
di lingkungan Pertamina (oil & gas), bukan dashboard generik.

| Token | Dark | Light | Peran |
|---|---|---|---|
| `--ink` | `#0b1418` | `#f5f3ee` | Page canvas (near-black pipeline coating / warm site-paper, bukan putih klinis) |
| `--surface` | `#121e24` | `#ffffff` | Module/card |
| `--surface-2` | `#16262d` | `#eee9df` | Raised/nested surface |
| `--accent` | `#ff7a1f` | `#e0630f` | Primary accent — safety-marking amber-orange, dipakai untuk active state & primary action |
| `--accent-2` | `#2bb3b6` | `#177a7c` | Secondary accent — pipe-marking teal, dipakai untuk info/focus/secondary highlight |
| `--alarm` | `#ff4d3d` | `#d5271a` | **Hanya** untuk alarm gas aktif, tidak pernah dekoratif |
| `--ok` | `#3ecf8e` | `#1f8f5c` | Status sukses/pass |
| `--text` | `#eef2f0` | `#16211f` | Teks utama |
| `--text-muted` | `#8fa39d` | `#5c6b66` | Teks sekunder |

Hazard red tetap eksklusif untuk alarm (konvensi yang sudah divalidasi dua
revisi sebelumnya — operator harus tetap bisa mengandalkan "merah = alarm
saja").

### 5.2 Tipografi

- **Eyebrow/label** (uppercase, huruf kecil, tracking lebar): `Bahnschrift`
  (bawaan Windows 10/11, target OS resmi app ini) — dipakai HANYA untuk label
  mikro (eyebrow di atas judul, badge, header modul), bukan untuk judul besar
  seperti revisi pertama. Ini membalik peran font tersebut supaya tidak
  terasa seperti reskin dari revisi pertama.
- **Body/heading**: `Segoe UI` / `system-ui` — netral, dipakai untuk judul
  tab, isi form, teks umum.
- **Data/mono**: `Cascadia Mono` / `Consolas` / `ui-monospace` — tabular
  figures untuk semua angka telemetry, DAC code, log, tabel dataset. Pilihan
  ini tidak berubah dari revisi-revisi sebelumnya karena memang pilihan yang
  benar untuk data GLD di Windows (bukan sekadar dipertahankan karena malas
  ganti).

### 5.3 Layout primitives

- `--radius: 10px` — sudut lembut tapi bukan pil di mana-mana (beda dari
  radius 8px "clinical" dan radius 3px "instrument panel" sebelumnya).
- Drawer kanan: satu komponen (`.drawer` + `.drawer-backdrop`) dipakai untuk
  Ops Panel, Port Setup, dan tiga settings panel (Running/Dataset/Nulling).
- Instrument strip: flex row, tinggi tetap ~56px, selalu `position: sticky`.
- Segmented nav: pill container dengan indicator aktif (background
  `--accent`, teks kontras), bukan garis bawah seperti tab rail sebelumnya.

### 5.4 Tema gelap/terang

Dipertahankan dari revisi sebelumnya: token di atas didefinisikan di
`:root` (default terang) dan di-override di `[data-theme="dark"]` serta
`@media (prefers-color-scheme: dark)`. Toggle di topbar, persist ke
`localStorage.gldOperatorWeb.theme` (kunci sama, tidak reset preferensi
operator yang sudah ada).

### 5.5 Signature element

Setiap header modul punya garis tipis 2px di bawah judul yang terisi warna
`--accent` sesaat (~600ms, dihormati `prefers-reduced-motion`) setiap kali
modul itu menerima data baru dari GLD — "denyut" hidup yang menunjukkan
data benar-benar mengalir, bukan hiasan statis. Elemen ini kecil dan tidak
mengganggu keterbacaan, sesuai catatan lama "tidak rumit, mudah dipahami".

## 6. Informasi arsitektur (IA)

### 6.1 Instrument strip (selalu terlihat)

- Brand (Pertamina GLD — Operator Console).
- Live gauges ringkas: Port, Device ID, Mode, Gas, Confidence.
- Alarm badge (tetap paling mencolok, memakai `--alarm` eksklusif).
- Tombol: **Ops Panel** (buka drawer Fleet/Commands/Device Mode), **Port
  Setup**, **Mute Alarm**, **Mock GLD**, **Theme toggle**.

### 6.2 Segmented nav (5 tab, urutan tetap)

1. Running
2. Dataset
3. Nulling
4. Log
5. Expert (berisi Expert Terminal, Timeout Settings, dan Firmware Upload)

### 6.3 Ops Panel (drawer kanan, dari topbar)

Berisi persis konten yang sebelumnya ada di kolom sidebar kiri:

- Fleet (active slot card, daftar slot lain, + Add Slot).
- Commands (Ping, Info, Status, Poll — lihat §9.1 untuk field baru).
- Device Mode (switch SET_MODE running/dataset/nulling langsung ke GLD).

### 6.4 Per-tab settings drawer (gear icon)

Sama seperti revisi sebelumnya, dipertahankan karena terbukti berguna:

- **Running settings**: MQ Sensor Check (boot report + channel presence),
  Device Identity (Target GLD ID + Inject ID), CH Address (Target CH Address
  + Apply CH Address). Sama seperti revisi sebelumnya §7 lama.
- **Dataset settings**: Capture Parameters + WiFi/MQTT + Apply GLD Settings.
- **Nulling settings**: Nulling Thresholds.

Body tab tetap berisi monitor/hasil saja (progress, tabel, channel grid, raw
log) — parameter murni ada di drawer, konsisten dengan keputusan revisi
sebelumnya.

## 7. Pemetaan file (apa yang ditulis ulang vs dipertahankan)

| File | Status |
|---|---|
| `index.html` | Ditulis ulang total (markup baru, ID dipertahankan — lihat §7.1) |
| `css/tokens.css` | Ditulis ulang total (§5.1) |
| `css/base.css` | Ditulis ulang total (radius, tipografi dasar) |
| `css/layout.css` | Ditulis ulang total (instrument strip, segmented nav, drawer, tanpa grid sidebar) |
| `css/components.css` | Ditulis ulang total (gauge, tag, tabel, dll mengikuti token baru) |
| `css/nulling.css` | Disesuaikan ke token baru, sweep-meter tetap (elemen tanda tangan Nulling dari revisi pertama yang terbukti bagus, dipertahankan) |
| `js/state.js` | Tambah beberapa `elements` baru untuk id markup baru, logic tidak berubah |
| `js/ui.js` | Tambah/rename helper drawer generik, `switchTab` tidak berubah |
| `js/main.js` | Wiring event disesuaikan ke markup baru + logic poll interval baru (§9.1) |
| `js/theme.js` | Tidak berubah |
| `js/serial-protocol.js` | Hanya `togglePolling` yang berubah (§9.1), sisanya tidak berubah |
| `js/dataset.js`, `nulling.js`, `firmware.js`, `fleet.js`, `security.js`, `chart.js`, `bridge-client.js`, `mock.js` | **Tidak berubah** — semua rujuk elemen lewat ID yang sama |
| `bridge.py`, `local_mqtt_broker.py`, `requirements.txt`, `run-gld-operator.bat` | **Tidak disentuh** |

### 7.1 ID kontrak yang harus tetap ada di markup baru

Semua ID di bawah ini dipakai langsung oleh `js/*.js` lewat `document.getElementById`
dan **tidak boleh berubah nama**, hanya posisi/pembungkusnya di markup yang
berubah:

```text
connectionBadge, bridgeBadge, portLabel, topDeviceStatus, topModeStatus,
topGasStatus, topConfidenceStatus, alarmBadge, portSetupBtn, alarmMuteBtn,
mockBtn, closeSetupBtn, setupPanel, portSelect, manualPortInput,
useManualPortBtn, portDetail, refreshPortsBtn, connectBtn, disconnectBtn,
refreshLoopBtn, rangeSelect, sensorChart, legend, serialLog, deviceId,
firmwareValue, modeValue, powerMode, gasValue, confidenceValue, loraValue,
batteryValue, externalPower, batteryValueMirror, adsHealth, mcpHealth,
dacHealth, mlHealth, clearChartBtn, exportCsvBtn, datasetStateValue,
datasetPhaseValue, datasetProgressValue, datasetElapsedValue,
datasetRowsValue, datasetLastSampleValue, datasetOutputName,
datasetOutputPath, datasetProgressBar, datasetLastEvent, datasetHint,
datasetNullingFirst, datasetRowsBody, runNullingNowBtn, switchDatasetBtn,
startDatasetBtn, stopDatasetBtn, saveDatasetCsvBtn, downloadDatasetCsvBtn,
openDatasetFolderBtn, clearDatasetSessionBtn, datasetLabel, targetSamples,
sampleIntervalMs, maxDurationMs, fanOnMs, postFanSettleMs, useThisPcBtn,
testMqttBtn, mqttTestStatus, wifiSsid, wifiPassword, mqttHost, mqttPort,
mqttUser, mqttPass, topicRoot, applyConfigBtn, nullingLog, nullingSummary,
nullingMeta, nullingChannels, clearNullingBtn, nullingThresholdV,
nullingMinFinalV, applyNullingConfigBtn, refreshNullingConfigBtn,
downloadLogBtn, saveSessionLogBtn, clearLogBtn, unlockExpertBtn, rawCommand,
sendRawBtn, timeoutSerialResponseMs, timeoutDatasetReadyMs,
timeoutDatasetStuckMs, applyTimeoutsBtn, loadManifestBtn, checkPortLockBtn,
uploadFirmwareBtn, injectIdBtn, injectChBtn, firmwareLockStatus,
firmwarePortStatus, firmwareEnv, targetDeviceId, packageDeviceId,
manifestFile, targetChAddress, currentChAddress, chAddressStatus,
manifestPreview, refreshSensorCheckBtn, clearSensorCheckBtn,
sensorCheckSummary, sensorCheckMeta, bootReportSummary, bootReportGrid,
sensorCheckChannels, fleetCountBadge, fleetExtra, addSlotBtn,
activeSlotLabel, sideDeviceSummary, sidePortSummary, globalBanner,
globalBannerText, globalBannerDismiss, protocolLabel,
[data-command], [data-mode], [data-close-setup]
```

Tambahan baru untuk revisi ini (lihat §9): `pollIntervalMs` (input),
`opsPanelBtn`, `opsPanel`, `runningSettingsBtn`/`runningSettingsPanel`,
`datasetSettingsBtn`/`datasetSettingsPanel`,
`nullingSettingsBtn`/`nullingSettingsPanel`, `themeToggleBtn`,
`[data-close-dialog]` (generalisasi dari `data-close-setup`, dipertahankan
dari revisi sebelumnya).

## 8. Fitur yang harus tetap bekerja (checklist verifikasi)

Semua ini sudah bekerja di revisi sebelumnya dan **wajib** tetap bekerja
setelah rebuild — dipakai sebagai checklist §14 acceptance:

- Bridge health poll + reconnect-after-downtime (`bridgeBadge`).
- Scan/manual COM port, Connect/Disconnect serial, handshake
  APP_PING/GET_INFO/GET_STATUS.
- Mock GLD (toggle, tanpa hardware).
- Running: 4 gauge card, chart telemetry + range + clear + export CSV, Power
  & Boot Health disclosure.
- Sensor Check (kini di drawer Running settings): refresh status, run boot
  check, boot IC report grid, MQ channel grid.
- Dataset: switch mode, start/stop, WiFi/MQTT config + Use this PC + Test
  Broker + Apply GLD Settings (drawer), session monitor (status/progress/
  rows/output), Run Nulling Now action saat `reject_no_profile`, save/
  download CSV, open folder, clear session.
- Nulling: switch mode, 8 channel card + sweep meter + stage detail, raw
  log, thresholds (drawer), apply/refresh.
- Log: serial log, download, save to disk, clear.
- Expert: PIN unlock (local SHA-256), raw command terminal, timeout
  settings, firmware manifest load + validate, upload dengan COM-lock
  preflight, device ID inject dan CH address apply (kini di drawer Running
  settings, tapi tetap gated oleh unlock yang sama).
- Fleet: 1-8 slot, add/switch/remove, alarm surfacing lintas slot.
- Alarm: badge + mute lokal + audio beep, tidak mengganggu GLD-side state.
- Theme toggle + sidebar-equivalent (Ops Panel) show/hide, keduanya persist.

## 9. Apa yang benar-benar baru di revisi ini

### 9.1 Poll interval bisa diatur, tidak dipatok 1 detik

Sebelumnya `togglePolling()` di `js/serial-protocol.js` selalu memakai
`setInterval(() => sendCommand("GET_STATUS"), 1000)` — angka 1000 ms hardcode
dan tidak berhubungan dengan kecepatan akuisisi GLD yang sebenarnya.

Firmware (`firmware/config/GldConfig.h`) memindai sensor setiap
`GLD_SCAN_INTERVAL_MS = 500` ms — itu batas bawah yang masuk akal, karena di
bawah itu sweep ADS 8-sensor (~330 ms) bisa overlap dengan siklus berikutnya.

Perubahan:

- Field baru `pollIntervalMs` (input number, min 200, step 100,
  default **500** — mengikuti `GLD_SCAN_INTERVAL_MS`) ditambahkan ke Ops
  Panel, dekat tombol Poll.
- `togglePolling()` membaca nilai ini saat start polling, bukan angka
  hardcode. Tersimpan ke `localStorage` lewat mekanisme `saveForm()` yang
  sudah ada (field ditambahkan ke `FORM_STORAGE_IDS`).
- Label tombol Poll menampilkan interval aktif, contoh "Poll 500ms" bukan
  "Poll 1s" statis, supaya operator selalu tahu rate yang sedang berjalan
  tanpa buka drawer.
- Tidak ada perubahan di firmware atau bridge — ini murni interval polling
  `GET_STATUS` dari app ke GLD lewat serial, tetap dibatasi wajar (default
  500 ms) supaya tidak membanjiri serial link.

### 9.2 Ops Panel menggantikan kolom sidebar kiri

Lihat §4 dan §6.3. Secara fungsional identik dengan kolom Fleet/Commands/
Device Mode sebelumnya, hanya berubah bentuk jadi drawer kanan yang konsisten
dengan drawer settings lainnya.

### 9.3 Drawer generik dipakai di 5 tempat

`data-close-dialog="<panelId>"` (sudah ada sejak revisi sebelumnya untuk 3
settings panel) sekarang juga dipakai oleh Port Setup dan Ops Panel, jadi ada
satu mekanisme buka/tutup drawer untuk semuanya, bukan campuran
`data-close-setup` khusus Port Setup + `data-close-dialog` untuk yang lain.

## 10. Verifikasi

Sama seperti dua revisi sebelumnya, wajib diverifikasi langsung ke bridge
nyata (COM10/COM9, bukan hanya Mock GLD) sebelum dianggap selesai:

- `node --check` semua file `js/*.js` yang diubah.
- Klik-tes semua 5 tab, semua drawer (Ops Panel, 3 settings, Port Setup),
  toggle tema, toggle Ops Panel, tanpa error console.
- Poll dengan interval custom (misalnya 250 ms) benar-benar mengubah rate
  `GET_STATUS` yang terkirim (lihat serial log / network di bridge).
- `python firmware/tests/run_tests.py` tidak perlu dijalankan ulang karena
  firmware tidak disentuh di revisi ini.

## 11. Backend contract (tidak berubah — ringkasan)

Detail lengkap REST/SSE/protokol serial ada di riwayat git dan di
`apps/gld-operator-backup/design.md` §5, §8-§17 (revisi sebelum rebuild ini,
isinya masih akurat karena `bridge.py` tidak berubah). Ringkasan yang relevan
untuk frontend:

- Base URL bridge: `http://127.0.0.1:5173/`.
- Endpoint: `/api/health`, `/api/ports`, `/api/network`,
  `/api/dataset/output-dir`, `/api/events` (SSE), `/api/serial/connect`,
  `/api/serial/disconnect`, `/api/serial/write`, `/api/serial/port-status`,
  `/api/mqtt/dataset`, `/api/mqtt/dataset-monitor/stop`, `/api/mqtt/test`,
  `/api/dataset/save`, `/api/dataset/open-folder`, `/api/firmware/upload`,
  `/api/session/log` — semua menerima `slot` opsional (default 1).
- Serial command yang dikirim app tidak berubah: `APP_PING`, `GET_INFO`,
  `GET_STATUS`, `SET_MODE ...`, `SET_APP_CONFIG_JSON`,
  `SET_DEVICE_ID_JSON`, `SET_CH_ADDRESS_JSON`, `RUN_BOOT_CHECK`.

## 12. Keamanan

Tidak berubah dari revisi sebelumnya (§18 di dokumen lama): PIN lock lokal
untuk Expert Terminal dan Firmware Upload/Inject ID/Apply CH Address, bridge
CORS permisif untuk localhost bench saja, kredensial WiFi/MQTT tidak
dipersist di localStorage.

## 12A. Perbaikan pasca-rebuild (2026-07-15, sore)

- `refreshLoopBtn` ("Poll") dipindah dari Ops Panel ke toolbar Sensor
  Telemetry di tab Running, supaya operator tidak perlu buka Ops Panel untuk
  mulai merekam telemetry ke grafik. `pollIntervalMs` dipindah ke drawer
  Running Settings, dekat kontrol GLD ID/CH Address lainnya.
- Running Settings drawer diurutkan ulang: form (Poll Interval, Device
  Identity, CH Address) di atas, MQ Sensor Check/Boot IC Report/MQ Channels
  (read-only) di bawah.
- Battery display bug: `power.batteryMv` firmware bisa berisi sentinel
  `65535` (uint16 "tidak terbaca") saat GLD berjalan di power eksternal
  24V/5V tanpa baterai, tapi itu tetap angka finite secara JS sehingga lolos
  cek lama. Diperbaiki dengan memeriksa flag `power.batteryValid` dari
  firmware (`firmware/gld/src/GldUnifiedMain.cpp` `emitStatusJson`) - Battery
  sekarang tampil "-" saat tidak valid, bukan "65535 mV".

## 12B. Dataset chart + 6-step capture wizard (2026-07-15, malam)

- `js/chart.js` refactored: `drawOneChart()` is now generic (any canvas +
  range select + legend + optional vertical markers), and `drawChart()` (the
  single exported entry point every other module already calls) draws both
  the Running chart and a new Dataset tab chart from the same
  `state.history` feed, so no other call site needed to change.
- Dataset tab chart has its own range/poll/clear/export controls
  (`datasetRangeSelect`, `.poll-btn` shared with Running, `datasetClearChartBtn`,
  `datasetExportCsvBtn`) and overlays dashed START (green) / STOP (red)
  vertical markers at `state.dataset.startedAt`/`endedAt`.
- New 6-step capture wizard (`#datasetWizard`, rendered by
  `renderDatasetWizard()` in `js/dataset.js`): Switch Mode -> Confirm Config
  -> Start -> Capturing -> Stop -> Save. Each step is gray (pending), amber
  (active), or green (done). It observes the existing workflow rather than
  gating it - an operator who starts a capture without using the wizard's
  intended order still gets a sensible in-order picture
  (`fastForwardWizardTo`) instead of a stuck indicator.
- `beginDatasetSwitch()` (wired to "Switch to Dataset") sends `SET_MODE
  dataset`, polls for confirmation, then opens the app's centered popup
  (§12) showing the current capture parameters for the operator to verify
  before continuing - this is a new mandatory checkpoint that did not exist
  before.

## 13. Riwayat revisi

- 2026-07-14: Rebuild pertama dari `app.js` monolitik ke modul `js/*.js` +
  tema instrument-panel amber/near-black + tab rail horizontal.
- 2026-07-15 (pagi): Rebuild kedua — tema "Clinical Lab Light" + dark/light
  toggle + sidebar kiri collapsible + drawer settings per-tab + firmware
  digabung ke Expert.
- 2026-07-15 (revisi ini): Rebuild ketiga "Manifold" — identitas visual baru,
  layout tanpa sidebar kiri (Ops Panel drawer kanan), poll interval
  configurable. Alasan: operator menganggap revisi kedua masih terasa
  generik/serupa dan minta identitas visual yang benar-benar baru.

## 14. Acceptance definition

Revisi ini dianggap selesai ketika:

- Semua item checklist §8 terverifikasi bekerja terhadap bridge nyata.
- Tidak ada error console di 5 tab + semua drawer.
- Poll interval bisa diubah dan benar-benar mengubah rate `GET_STATUS`.
- Visual berbeda jelas dari dua revisi sebelumnya (palet, tipografi, dan
  bentuk layout, bukan cuma warna).
- `apps/gld-operator-backup/` tetap ada dan tidak disentuh, sebagai jalur
  rollback.
