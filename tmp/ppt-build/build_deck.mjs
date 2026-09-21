import fs from "node:fs/promises";
import path from "node:path";
import {
  Presentation,
  PresentationFile,
  layers,
  shape,
  text,
} from "@oai/artifact-tool";

const TMP_DIR = String.raw`D:\Github\PertaminaGLD\tmp\ppt-build`;
const FINAL_PPTX = String.raw`D:\Github\PertaminaGLD\output\presentation\Presentasi-Rapat-Cilacap-2026-08-18.pptx`;

const IMG_GLD = String.raw`C:\Users\MSI\Downloads\cilacap\GLD.png`;
const IMG_CH = String.raw`C:\Users\MSI\Downloads\cilacap\CH&GW.png`;
const IMG_MAP = String.raw`C:\Users\MSI\Downloads\cilacap\WhatsApp Image 2026-08-18 at 16.01.54.jpeg`;
const IMG_TARGET = String.raw`C:\Users\MSI\Downloads\cilacap\WhatsApp Image 2026-08-18 at 16.01.55 (1).jpeg`;

const W = 1280;
const H = 720;
const C = {
  canvas: "#FFFFFF",
  ink: "#111827",
  muted: "#667085",
  panel: "#EDEDED",
  panelSoft: "#F7F7F7",
  rule: "#B8BCC4",
  blue: "#3D8DFF",
  blueSoft: "#EAF5FB",
  bluePale: "#D0EDFA",
  green: "#3B7D4E",
  greenSoft: "#E8F3E8",
  amber: "#A86500",
  amberSoft: "#FFF2CC",
  red: "#C01818",
  redSoft: "#FBE7E5",
  white: "#FFFFFF",
};

const FONT = "Arial";

function px(value) {
  return `${value}px`;
}

function t(name, value, left, top, width, height, options = {}) {
  return text([value], {
    name,
    position: { left, top },
    width,
    height,
    style: {
      fontSize: px(options.fontSize ?? 22),
      typeface: FONT,
      color: options.color ?? C.ink,
      bold: options.bold ?? false,
      alignment: options.alignment ?? "left",
      verticalAlignment: options.verticalAlignment ?? "top",
      autoFit: options.autoFit ?? "shrinkText",
      wrap: options.wrap ?? "square",
      insets: options.insets ?? { top: 0, right: 0, bottom: 0, left: 0 },
    },
  });
}

function rect(name, left, top, width, height, fill = C.panelSoft, lineFill = "none", lineWidth = 0) {
  return shape({
    name,
    geometry: "rect",
    fill,
    line: { style: "solid", fill: lineFill, width: lineWidth },
    position: { left, top },
    width,
    height,
  });
}

function line(name, left, top, width, color = C.rule, weight = 1) {
  return shape({
    name,
    geometry: "line",
    fill: "none",
    line: { style: "solid", fill: color, width: weight },
    position: { left, top },
    width,
    height: 1,
  });
}

function arrow(name, left, top, width, height, fill = C.blue) {
  return shape({
    name,
    geometry: "rightArrow",
    fill,
    line: { style: "solid", fill, width: 0 },
    position: { left, top },
    width,
    height,
  });
}

function base(slide, title, number, section = "READINESS & ACTION PLAN") {
  slide.background.fill = C.canvas;
  return [
    t(`section-${number}`, section, 52, 30, 480, 18, { fontSize: 14, bold: true, color: C.muted }),
    t(`title-${number}`, title, 52, 58, 1176, 60, { fontSize: 48, bold: false, autoFit: "shrinkText" }),
    line(`footer-rule-${number}`, 52, 668, 1176, C.rule, 1),
    t(`footer-left-${number}`, "INTERNAL • 18 AGUSTUS 2026", 52, 680, 360, 20, { fontSize: 14, color: C.muted }),
    t(`footer-number-${number}`, String(number).padStart(2, "0"), 1178, 680, 50, 20, { fontSize: 14, color: C.muted, alignment: "right" }),
  ];
}

function compose(slide, name, elements) {
  slide.compose(
    layers({ name, width: "fill", height: "fill" }, elements),
    { frame: { left: 0, top: 0, width: W, height: H }, baseUnit: 1 },
  );
}

function sources(slide, sourceLines) {
  const notes = ["[Sources]", ...sourceLines.map((item) => `- ${item}`)].join("\n");
  slide.speakerNotes.textFrame.setText(notes);
  slide.speakerNotes.setVisible(true);
}

async function addImage(slide, imagePath, alt, position, fit = "cover", crop = undefined) {
  const bytes = await fs.readFile(imagePath);
  const ext = path.extname(imagePath).toLowerCase();
  const contentType = ext === ".png" ? "image/png" : "image/jpeg";
  slide.images.add({
    blob: bytes,
    contentType,
    alt,
    fit,
    position,
    ...(crop ? { crop } : {}),
    geometry: "rect",
  });
}

function styleTable(table, rows, columns, options = {}) {
  table.styleOptions = { headerRow: options.headerRow ?? true, bandedRows: false };
  table.borders.assign({ style: "solid", fill: C.rule, width: 1 });
  const all = table.cells.block({ row: 0, column: 0, rowCount: rows, columnCount: columns });
  all.assign({
    textStyle: { fontSize: options.fontSize ?? 19, color: C.ink, typeface: FONT },
    margins: { top: 8, right: 10, bottom: 8, left: 10 },
    anchor: "middle",
  });
  if (options.headerRow ?? true) {
    const header = table.cells.block({ row: 0, column: 0, rowCount: 1, columnCount: columns });
    header.assign({ fill: C.panel, textStyle: { fontSize: options.headerFontSize ?? 18, bold: true, color: C.ink, typeface: FONT } });
  }
}

async function writeBlob(filePath, blob) {
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

async function main() {
  await fs.mkdir(TMP_DIR, { recursive: true });
  await fs.mkdir(path.dirname(FINAL_PPTX), { recursive: true });

  const deck = Presentation.create({ slideSize: { width: W, height: H } });

  // 01 — cover-image-field composition
  {
    const slide = deck.slides.add();
    slide.background.fill = C.canvas;
    compose(slide, "cover-image-field", [
      t("cover-kicker", "PERTAMINA • LGU | INTERNAL", 52, 42, 480, 22, { fontSize: 15, bold: true, color: C.muted }),
      t("cover-title", "Kesiapan Sistem\ndan Rencana Tindak Lanjut", 52, 150, 565, 190, { fontSize: 70, bold: false, autoFit: "shrinkText" }),
      t("cover-subtitle", "Ringkasan keputusan meeting, readiness teknis, safety hold, kebutuhan site, dan rencana menuju target September 2027.", 52, 390, 535, 110, { fontSize: 25, color: C.muted }),
      rect("cover-accent", 52, 548, 360, 8, C.blue),
      t("cover-date", "18 AGUSTUS 2026", 52, 578, 300, 26, { fontSize: 17, bold: true, color: C.ink }),
      rect("cover-image-backing", 658, 42, 570, 588, C.blueSoft, C.rule, 1),
      line("cover-footer-rule", 52, 668, 1176, C.rule, 1),
      t("cover-footer", "INTERNAL • EVIDENCE-BOUNDED", 52, 680, 360, 20, { fontSize: 14, color: C.muted }),
    ]);
    await addImage(slide, IMG_GLD, "Konsep perangkat GLD yang disediakan pengguna", { left: 658, top: 42, width: 570, height: 588 }, "cover", { left: 0.02, top: 0, right: 0.02, bottom: 0 });
    sources(slide, [
      "Laporan internal terverifikasi, 18 Agustus 2026.",
      "Foto konsep perangkat yang disediakan pengguna; bukan bukti sertifikasi atau produk final.",
    ]);
  }

  // 02 — agenda/table-evidence composition
  {
    const slide = deck.slides.add();
    compose(slide, "agenda-table-evidence", [
      ...base(slide, "Outline pembahasan", 2, "OUTLINE"),
      t("outline-intro", "Lima bagian berikut membentuk alur keputusan—bukan inventaris teknis.", 52, 132, 950, 32, { fontSize: 22, color: C.muted }),
    ]);
    const values = [
      ["01", "Keputusan meeting dan koreksi jadwal"],
      ["02", "Arsitektur sistem dan status readiness"],
      ["03", "GLD, CH, Gateway, jaringan, dan server"],
      ["04", "Hazardous-area, mounting, dan kebutuhan site"],
      ["05", "Roadmap, ownership, dan keputusan yang diminta"],
    ];
    const table = slide.tables.add({ rows: 5, columns: 2, left: 52, top: 196, width: 1176, height: 405, columnWidths: [110, 1066], values });
    styleTable(table, 5, 2, { headerRow: false, fontSize: 24 });
    table.cells.block({ row: 0, column: 0, rowCount: 5, columnCount: 1 }).assign({ fill: C.blueSoft, textStyle: { fontSize: 24, bold: true, color: C.blue, typeface: FONT } });
    sources(slide, ["Sintesis laporan internal dan agenda keputusan rapat."]);
  }

  // 03 — meeting evidence with image split
  {
    const slide = deck.slides.add();
    compose(slide, "meeting-evidence-split", [
      ...base(slide, "Arah rapat jelas; tanggal sertifikat belum", 3, "MEETING OUTCOME"),
      t("meeting-intro", "Rekaman dan catatan lapangan mendukung empat arah utama:", 52, 132, 560, 32, { fontSize: 22, color: C.muted }),
      t("meeting-metric-1", "SEP 2027", 52, 190, 245, 55, { fontSize: 43, bold: true, color: C.blue }),
      t("meeting-metric-1-label", "Target fase awal terpasang/diterima—definisi milestone perlu dikonfirmasi.", 52, 250, 245, 92, { fontSize: 20 }),
      t("meeting-metric-2", "AKHIR SEP 2026", 330, 190, 280, 55, { fontSize: 34, bold: true, color: C.blue }),
      t("meeting-metric-2-label", "Support, tiang, kabel, material/BOM, drawing, dan kebutuhan IT harus masuk.", 330, 250, 280, 92, { fontSize: 20 }),
      rect("meeting-correction", 52, 382, 558, 146, C.redSoft, "none", 0),
      t("meeting-correction-title", "“3 minggu” bukan tanggal sertifikat", 76, 406, 510, 34, { fontSize: 27, bold: true, color: C.red }),
      t("meeting-correction-body", "Tanggal rilis disebut belum diketahui. Angka tersebut lebih konsisten dengan perjalanan/pengajuan ke manufaktur.", 76, 454, 510, 58, { fontSize: 20 }),
      t("meeting-contract", "Lead time kontrak disebut sekitar 3–4 bulan; scope pendukung harus dibekukan lebih awal.", 52, 558, 558, 52, { fontSize: 20, color: C.ink }),
      rect("meeting-image-backing", 658, 132, 570, 478, C.panelSoft, C.rule, 1),
      t("meeting-image-caption", "Catatan kontemporer—belum merupakan minutes yang disahkan.", 658, 620, 570, 28, { fontSize: 16, color: C.muted, alignment: "center" }),
    ]);
    await addImage(slide, IMG_TARGET, "Catatan meeting dengan target September 2027 dan kebutuhan akhir September 2026", { left: 658, top: 132, width: 570, height: 478 }, "cover", { left: 0.04, top: 0.02, right: 0.02, bottom: 0.04 });
    sources(slide, [
      "Rekaman meeting 14 Agustus 2026, transkripsi offline dan cross-check.",
      "Catatan lapangan yang disediakan pengguna; belum ditandatangani sebagai minutes resmi.",
    ]);
  }

  // 04 — simple native-shape system flow
  {
    const slide = deck.slides.add();
    const elements = [
      ...base(slide, "Alur sistem jelas; bukti lapangan belum", 4, "END-TO-END SYSTEM"),
      t("architecture-sub", "Source saat ini mendukung alur data dan command; RF, broker, deployment, serta site network masih memerlukan bukti live.", 52, 130, 1176, 52, { fontSize: 22, color: C.muted }),
      // Arrows are deliberately placed before nodes so they remain behind them.
      arrow("arrow-gld-ch", 278, 292, 92, 34, C.blue),
      arrow("arrow-ch-gw", 574, 292, 92, 34, C.blue),
      arrow("arrow-gw-server", 870, 292, 92, 34, C.blue),
      rect("node-gld", 70, 230, 208, 160, C.blueSoft, C.blue, 2),
      rect("node-ch", 366, 230, 208, 160, C.panelSoft, C.rule, 1),
      rect("node-gw", 662, 230, 208, 160, C.panelSoft, C.rule, 1),
      rect("node-server", 958, 230, 252, 160, C.panelSoft, C.rule, 1),
      t("node-gld-title", "GLD", 94, 260, 160, 42, { fontSize: 34, bold: true, alignment: "center" }),
      t("node-gld-body", "Sensing • inferensi\nSTAR uplink", 94, 312, 160, 58, { fontSize: 20, color: C.muted, alignment: "center" }),
      t("node-ch-title", "CH", 390, 260, 160, 42, { fontSize: 34, bold: true, alignment: "center" }),
      t("node-ch-body", "STAR receiver\nMESH relay", 390, 312, 160, 58, { fontSize: 20, color: C.muted, alignment: "center" }),
      t("node-gw-title", "GATEWAY", 686, 260, 160, 42, { fontSize: 28, bold: true, alignment: "center" }),
      t("node-gw-body", "MESH root\nMQTT bridge", 686, 312, 160, 58, { fontSize: 20, color: C.muted, alignment: "center" }),
      t("node-server-title", "SERVER", 982, 260, 204, 42, { fontSize: 28, bold: true, alignment: "center" }),
      t("node-server-body", "Broker • Node-RED\nDashboard • dataset", 982, 312, 204, 58, { fontSize: 20, color: C.muted, alignment: "center" }),
      t("link-star", "STAR 920 MHz", 270, 342, 110, 24, { fontSize: 15, color: C.muted, alignment: "center" }),
      t("link-mesh", "MESH 921 MHz", 566, 342, 110, 24, { fontSize: 15, color: C.muted, alignment: "center" }),
      t("link-mqtt", "Wi-Fi / MQTT", 862, 342, 110, 24, { fontSize: 15, color: C.muted, alignment: "center" }),
      rect("architecture-note", 70, 454, 1140, 118, C.blueSoft, "none", 0),
      t("architecture-note-title", "Interpretasi yang aman", 94, 480, 260, 32, { fontSize: 26, bold: true, color: C.blue }),
      t("architecture-note-body", "Diagram ini menjelaskan boundary dan ownership aliran. Ia bukan bukti range RF, konektivitas broker, TLS, deployment revision, atau keberhasilan lapangan.", 365, 474, 815, 62, { fontSize: 21 }),
    ];
    compose(slide, "system-flow", elements);
    sources(slide, [
      "Audit source terkini untuk GLD, CH, Gateway, dan flow server.",
      "Konfigurasi/source diperlakukan sebagai bukti statis, bukan bukti RF atau deployment live.",
    ]);
  }

  // 05 — readiness table
  {
    const slide = deck.slides.add();
    compose(slide, "readiness-table", [
      ...base(slide, "Source tersedia; bukti live masih terbatas", 5, "READINESS"),
      t("readiness-sub", "Status dibedakan agar rapat tidak mengubah source evidence menjadi klaim lapangan.", 52, 132, 1176, 36, { fontSize: 22, color: C.muted }),
    ]);
    const values = [
      ["Area", "Terbukti dari desain/source", "Masih harus dibuktikan"],
      ["GLD", "Power tree, 8 socket MQ, firmware/radio path", "MPN sensor, cold-start, thermal, F1 24 V, sensing accuracy"],
      ["CH", "Dual radio, charger/power path, cadence source", "Cell/panel, autonomy, enclosure, RF site test"],
      ["Gateway", "Wi-Fi STA, radio–MQTT bridge, queue/status", "Unit MAC, onboarding IT, TLS, antenna/PSU field"],
      ["Server", "Node-RED/dataset components dan generator", "Flow sync, production package, backup/restore, live revision"],
      ["Site / Ex", "Arah meeting dan daftar hold point", "Area classification, certificate, permit, installation acceptance"],
    ];
    const table = slide.tables.add({ rows: 6, columns: 3, left: 52, top: 196, width: 1176, height: 410, columnWidths: [170, 470, 536], values });
    styleTable(table, 6, 3, { fontSize: 18, headerFontSize: 18 });
    table.cells.block({ row: 1, column: 0, rowCount: 5, columnCount: 1 }).assign({ fill: C.blueSoft, textStyle: { fontSize: 19, bold: true, color: C.ink, typeface: FONT } });
    table.cells.block({ row: 1, column: 2, rowCount: 5, columnCount: 1 }).assign({ fill: "#FFF9E8", textStyle: { fontSize: 18, color: C.ink, typeface: FONT } });
    sources(slide, ["Laporan internal: status GLD, CH, Gateway, server, mounting, serta hazardous-area."]);
  }

  // 06 — GLD power
  {
    const slide = deck.slides.add();
    compose(slide, "gld-power-metrics", [
      ...base(slide, "GLD memakai 24 VDC/2 A secara provisional", 6, "GLD POWER"),
      rect("power-left", 52, 150, 420, 420, C.blueSoft, "none", 0),
      t("power-rating", "24 VDC / 2 A", 82, 194, 360, 74, { fontSize: 50, bold: true, color: C.blue, alignment: "center" }),
      t("power-rating-label", "Kapasitas nameplate PSU lapangan\n—bukan arus kontinu GLD", 82, 282, 360, 68, { fontSize: 23, alignment: "center" }),
      line("power-mid-rule", 102, 372, 320, C.rule, 1),
      t("power-consumption", "≈ 0,4–0,8 A", 82, 396, 360, 54, { fontSize: 38, bold: true, color: C.ink, alignment: "center" }),
      t("power-consumption-label", "Envelope worst-design setelah margin; final harus diukur.", 102, 464, 320, 58, { fontSize: 20, color: C.muted, alignment: "center" }),
      rect("power-blocker", 512, 150, 716, 150, C.redSoft, "none", 0),
      t("power-blocker-title", "BLOCKER: proteksi 16 V berada pada jalur 24 V", 540, 178, 660, 38, { fontSize: 29, bold: true, color: C.red }),
      t("power-blocker-body", "Komponen input bertanda 16 V harus diganti atau divalidasi dengan part berating 24 V beserta transient lapangan sebelum field acceptance.", 540, 228, 660, 54, { fontSize: 20 }),
      t("power-assumption-title", "Mengapa 2 A tetap rasional", 512, 338, 340, 34, { fontSize: 28, bold: true }),
      t("power-assumptions", "• Cold heater / inrush\n• Ambient dan thermal derating\n• Cable dan connector drop\n• Fan/alarm belum terukur", 536, 388, 330, 150, { fontSize: 22 }),
      t("power-1a-title", "Kapan 1 A boleh dipilih", 894, 338, 310, 34, { fontSize: 28, bold: true }),
      t("power-1a", "Setelah FAT membuktikan peak/steady, cable-drop, beban tambahan, dan closed-enclosure thermal tetap lulus dengan ≥20% headroom.", 894, 388, 310, 150, { fontSize: 22 }),
    ]);
    sources(slide, [
      "Audit schematic/PCB dan perhitungan power GLD.",
      "Littelfuse miniSMD resettable PTC datasheet: https://m.littelfuse.com/~/media/electronics/datasheets/resettable_ptcs/littelfuse_ptc_minismdc_datasheet.pdf.pdf",
      "Nilai heater memakai envelope datasheet kandidat karena manufacturer/MPN aktual belum terbukti.",
    ]);
  }

  // 07 — FAT timeline
  {
    const slide = deck.slides.add();
    compose(slide, "fat-three-card-timeline", [
      ...base(slide, "FAT menentukan kebutuhan daya final GLD", 7, "GLD FAT"),
      line("fat-track", 86, 580, 1100, C.ink, 1),
      shape({ name: "fat-dot-1", geometry: "ellipse", fill: C.ink, position: { left: 86, top: 574 }, width: 12, height: 12 }),
      shape({ name: "fat-dot-2", geometry: "ellipse", fill: C.ink, position: { left: 458, top: 574 }, width: 12, height: 12 }),
      shape({ name: "fat-dot-3", geometry: "ellipse", fill: C.ink, position: { left: 830, top: 574 }, width: 12, height: 12 }),
      rect("fat-card-1", 86, 154, 330, 360, C.panelSoft, "none", 0),
      rect("fat-card-2", 458, 154, 330, 360, C.panelSoft, "none", 0),
      rect("fat-card-3", 830, 154, 356, 360, C.panelSoft, "none", 0),
      t("fat-1-title", "1. IDENTIFIKASI", 116, 186, 270, 30, { fontSize: 24, bold: true, color: C.blue }),
      t("fat-1-body", "• Manufacturer / MPN / lot delapan MQ\n• Resistance heater saat dingin\n• Fan/alarm dan power source aktual\n• Cable length dan gauge desain", 116, 242, 270, 210, { fontSize: 21 }),
      t("fat-2-title", "2. PENGUKURAN", 488, 186, 270, 30, { fontSize: 24, bold: true, color: C.blue }),
      t("fat-2-body", "• ≥20 cold-start setelah OFF ≥30 menit\n• Profil arus sampai 120 menit\n• Log input 24 V, rail 5 V/3,3 V, heater\n• Capture peak dengan instrument memadai", 488, 242, 270, 220, { fontSize: 21 }),
      t("fat-3-title", "3. STRESS & ACCEPT", 860, 186, 296, 30, { fontSize: 24, bold: true, color: C.blue }),
      t("fat-3-body", "• All-heater + LoRa + RS485 + LED\n• Alarm/fan terpisah dan bersamaan\n• Kabel terpanjang + closed enclosure\n• Tanpa current-limit/reset; steady ≤80% rating", 860, 242, 296, 220, { fontSize: 21 }),
      t("fat-label-1", "INPUT TERVERIFIKASI", 86, 610, 300, 24, { fontSize: 17, bold: true }),
      t("fat-label-2", "WAVEFORM & THERMAL", 458, 610, 300, 24, { fontSize: 17, bold: true }),
      t("fat-label-3", "KEPUTUSAN 1 A / 2 A", 830, 610, 356, 24, { fontSize: 17, bold: true }),
    ]);
    sources(slide, ["Matriks FAT power dan acceptance evidence pada laporan internal."]);
  }

  // 08 — CH image split
  {
    const slide = deck.slides.add();
    compose(slide, "ch-image-split", [
      ...base(slide, "CH: radio siap di source; energi belum final", 8, "CH READINESS"),
      rect("ch-image-backing", 52, 150, 430, 470, C.blueSoft, C.rule, 1),
      t("ch-image-caption", "Konsep enclosure—bukan bukti IP/IK/Ex atau dimensi final.", 52, 628, 430, 26, { fontSize: 15, color: C.muted, alignment: "center" }),
      t("ch-source-title", "Yang sudah terdefinisi", 530, 154, 310, 34, { fontSize: 28, bold: true }),
      t("ch-source-body", "• Dua radio: STAR 920 MHz dan MESH 921 MHz\n• Charger/power path single-cell\n• Watchdog dan cadence firmware\n• Default Hello production 300 s", 530, 208, 320, 176, { fontSize: 22 }),
      t("ch-gap-title", "Yang belum boleh dibekukan", 880, 154, 320, 34, { fontSize: 28, bold: true, color: C.amber }),
      t("ch-gap-body", "• Cell/pack dan panel aktual\n• Autonomy, recharge, night/bad-weather budget\n• Thermal, corrosion, enclosure qualification\n• Dua feedthrough/antenna route dan RF site proof", 880, 208, 320, 190, { fontSize: 22 }),
      rect("ch-note", 530, 438, 670, 142, C.amberSoft, "none", 0),
      t("ch-note-title", "Catatan daya", 558, 464, 180, 32, { fontSize: 26, bold: true, color: C.amber }),
      t("ch-note-body", "Charger bukan MPPT. Interval 30 s + jitter adalah profil uji sementara, bukan kemampuan autonomy production.", 748, 460, 420, 66, { fontSize: 21 }),
    ]);
    await addImage(slide, IMG_CH, "Konsep enclosure CH atau Gateway yang disediakan pengguna", { left: 52, top: 150, width: 430, height: 470 }, "contain");
    sources(slide, [
      "Audit schematic/PCB dan current source CH.",
      "TI BQ25185 datasheet: https://www.ti.com/lit/ds/symlink/bq25185.pdf",
      "Foto konsep yang disediakan pengguna; tidak membuktikan material, ingress, corrosion, atau certification.",
    ]);
  }

  // 09 — Gateway onboarding
  {
    const slide = deck.slides.add();
    compose(slide, "gateway-two-column", [
      ...base(slide, "Onboarding IT butuh data unit aktual", 9, "GATEWAY & INTRANET"),
      t("gw-intro", "Gateway memulai koneksi outbound. Tidak harus satu SSID/subnet dengan server selama routed reachability disetujui.", 52, 130, 1176, 54, { fontSize: 22, color: C.muted }),
      rect("gw-physical", 52, 216, 540, 350, C.panelSoft, "none", 0),
      t("gw-physical-title", "Penempatan & perangkat", 82, 250, 480, 34, { fontSize: 29, bold: true }),
      t("gw-physical-body", "• Indoor / safe area yang tertulis\n• Antena menuju rooftop\n• PSU 5 V industrial dan grounding TBD\n• Current source: Wi-Fi STA\n• Ethernet dan WPA-Enterprise belum terbukti", 82, 312, 480, 200, { fontSize: 23 }),
      rect("gw-ticket", 636, 216, 592, 350, C.blueSoft, "none", 0),
      t("gw-ticket-title", "Data wajib pada tiket IT", 666, 250, 532, 34, { fontSize: 29, bold: true, color: C.blue }),
      t("gw-ticket-body", "1  Wi-Fi STA MAC unit aktual\n2  Broker/server FQDN atau IP\n3  Destination TCP port final\n4  SSID, VLAN, DHCP/NAC, DNS, NTP\n5  TLS/identity/topic ACL dan owner", 666, 310, 532, 218, { fontSize: 23 }),
      t("gw-footnote", "Port 1884 dan placeholder host saat ini adalah bench/configuration evidence—bukan nilai production yang disetujui IT.", 52, 594, 1176, 48, { fontSize: 19, color: C.muted }),
    ]);
    sources(slide, [
      "Audit current source Gateway dan catatan kebutuhan IT.",
      "NIST SP 800-82 Rev. 3 OT Security: https://csrc.nist.gov/pubs/sp/800/82/r3/final",
    ]);
  }

  // 10 — security gap comparison
  {
    const slide = deck.slides.add();
    compose(slide, "security-gap-comparison", [
      ...base(slide, "TLS end-to-end belum siap", 10, "NETWORK SECURITY"),
      t("tls-intro", "Current source dan policy generator belum konsisten untuk broker non-loopback.", 52, 132, 1176, 36, { fontSize: 22, color: C.muted }),
      rect("tls-current", 52, 206, 520, 300, C.redSoft, "none", 0),
      t("tls-current-label", "CURRENT SOURCE", 82, 236, 460, 28, { fontSize: 20, bold: true, color: C.red }),
      t("tls-current-title", "MQTT plaintext", 82, 282, 460, 50, { fontSize: 38, bold: true }),
      t("tls-current-body", "• WiFiClient tanpa TLS\n• Queue RAM 8 × 1024 B, volatile\n• Bench endpoint/port belum production\n• TCP reachability belum membuktikan MQTT", 82, 352, 460, 128, { fontSize: 22 }),
      arrow("tls-arrow", 590, 324, 100, 46, C.blue),
      rect("tls-required", 708, 206, 520, 300, C.greenSoft, "none", 0),
      t("tls-required-label", "PRODUCTION DIRECTION", 738, 236, 460, 28, { fontSize: 20, bold: true, color: C.green }),
      t("tls-required-title", "TLS + identity + ACL", 738, 282, 460, 50, { fontSize: 38, bold: true }),
      t("tls-required-body", "• Trust/certificate lifecycle\n• Per-device identity dan topic ACL\n• Broker logs / CONNACK success\n• Negative, reconnect, restart, dan expiry tests", 738, 352, 460, 128, { fontSize: 22 }),
      rect("tls-note", 52, 548, 1176, 76, C.blueSoft, "none", 0),
      t("tls-note-text", "MAC allowlist membantu asset control, tetapi tidak menggantikan authentication dan authorization.", 82, 570, 1116, 34, { fontSize: 23, bold: true, alignment: "center" }),
    ]);
    sources(slide, [
      "Audit current source Gateway dan generator server.",
      "OASIS MQTT Version 5.0: https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html",
      "NIST SP 800-82 Rev. 3 OT Security: https://csrc.nist.gov/pubs/sp/800/82/r3/final",
    ]);
  }

  // 11 — server three-column
  {
    const slide = deck.slides.add();
    compose(slide, "server-three-column", [
      ...base(slide, "Server pilot menunggu penutupan dua gap", 11, "SERVER & DASHBOARD"),
      t("server-intro", "Baseline sizing bersifat proposal pilot; production platform dan acceptance tetap milik Pertamina IT.", 52, 130, 1176, 48, { fontSize: 22, color: C.muted }),
      rect("server-source", 52, 208, 350, 348, C.panelSoft, "none", 0),
      rect("server-pilot", 465, 208, 350, 348, C.blueSoft, "none", 0),
      rect("server-prod", 878, 208, 350, 348, C.panelSoft, "none", 0),
      t("server-source-title", "SOURCE SAAT INI", 82, 240, 290, 28, { fontSize: 20, bold: true, color: C.muted }),
      t("server-source-big", "Flow drift", 82, 286, 290, 42, { fontSize: 34, bold: true, color: C.red }),
      t("server-source-body", "• Snapshot utama tertinggal\n• Status Gateway belum masuk snapshot\n• Dataset flow konsisten\n• Live deployment tidak diaudit", 82, 350, 290, 150, { fontSize: 21 }),
      t("server-pilot-title", "BASELINE PILOT", 495, 240, 290, 28, { fontSize: 20, bold: true, color: C.blue }),
      t("server-pilot-big", "4 vCPU • 8 GB\n100 GB SSD", 495, 286, 290, 78, { fontSize: 32, bold: true }),
      t("server-pilot-body", "OS LTS/server yang disetujui IT; service auto-start, health check, backup, monitoring.", 495, 392, 290, 104, { fontSize: 21 }),
      t("server-prod-title", "PRODUCTION CLOSURE", 908, 240, 290, 28, { fontSize: 20, bold: true, color: C.muted }),
      t("server-prod-big", "Package & runbook", 908, 286, 290, 42, { fontSize: 32, bold: true }),
      t("server-prod-body", "• Version/checksum manifest\n• Broker/TLS/ACL config\n• HTTPS/RBAC dan retention\n• Restore, RPO/RTO, patching, rollback", 908, 350, 290, 150, { fontSize: 21 }),
      t("server-two-gaps", "Dua gap awal: sinkronkan flow snapshot dan sepakati arah TLS sebelum packaging/deployment.", 52, 590, 1176, 44, { fontSize: 22, bold: true, alignment: "center" }),
    ]);
    sources(slide, ["Audit read-only Node-RED, dataset flow, generator, dan snapshot server."]);
  }

  // 12 — hazardous-area hold
  {
    const slide = deck.slides.add();
    compose(slide, "hazardous-hold", [
      ...base(slide, "Trial classified-area tetap ditahan", 12, "HAZARDOUS AREA"),
      rect("safety-banner", 52, 142, 1176, 104, C.redSoft, "none", 0),
      t("safety-banner-label", "SAFETY HOLD", 82, 170, 220, 34, { fontSize: 30, bold: true, color: C.red }),
      t("safety-banner-text", "Belum ada bukti certificate/marking untuk complete assembly GLD maupun CH.", 302, 170, 896, 40, { fontSize: 27, bold: true }),
      t("safety-rule-title", "Keputusan yang berlaku", 52, 292, 360, 34, { fontSize: 28, bold: true }),
      t("safety-rules", "• Tidak ada trial dekat/bawah tangki LPG\n• SRU/Sampit tetap kandidat—bukan otomatis safe area\n• Metal enclosure, IP/IK, atau partisi biasa bukan Ex certificate\n• Klaim jadwal sertifikat harus disertai application/test schedule", 76, 344, 560, 196, { fontSize: 22 }),
      t("safety-gates-title", "Empat gate sebelum classified installation", 688, 292, 500, 34, { fontSize: 28, bold: true }),
      t("safety-gates", "1  Area classification per titik\n2  Accepted complete-assembly certification scope\n3  Approved installation design + permit/JSA\n4  Competent initial inspection + HSE/site sign-off", 712, 344, 476, 196, { fontSize: 22 }),
      rect("safety-bottom", 52, 574, 1176, 64, C.amberSoft, "none", 0),
      t("safety-bottom-text", "Sebelum gate ditutup, trial hanya pada lokasi non-hazardous yang ditetapkan Pertamina secara tertulis.", 76, 594, 1128, 28, { fontSize: 22, bold: true, alignment: "center" }),
    ]);
    sources(slide, [
      "Rekaman meeting dan laporan internal: penolakan trial dekat tangki LPG sebelum acceptance.",
      "ATEX Directive 2014/34/EU: https://eur-lex.europa.eu/eli/dir/2014/34",
      "IECEx Certified Equipment Scheme: https://www.iecex.com/certified-equipment-scheme/overview/",
      "IEC 60079-10-1: https://webstore.iec.ch/en/publication/63327",
      "IEC 60079-14: https://webstore.iec.ch/en/publication/66049",
    ]);
  }

  // 13 — mounting/site image split
  {
    const slide = deck.slides.add();
    compose(slide, "mounting-site-split", [
      ...base(slide, "Mounting final menunggu survey", 13, "SITE INTERFACE"),
      t("mounting-intro", "Angka meeting adalah proposal awal; drawing fabrikasi harus mengikuti data site dan approval struktur.", 52, 130, 540, 56, { fontSize: 22, color: C.muted }),
      t("mounting-survey-title", "Output survey yang wajib", 52, 218, 500, 34, { fontSize: 29, bold: true }),
      t("mounting-survey-body", "• Pole/handrail OD, material, thickness, existing load\n• Wind/seismic/vibration/corrosion dan anchor policy\n• Power source, cable route, gland, allowable drop\n• Antenna height/LOS/coax/lightning/grounding\n• Access, maintenance envelope, work-at-height", 76, 274, 500, 222, { fontSize: 22 }),
      rect("mounting-proposal", 52, 524, 540, 102, C.amberSoft, "none", 0),
      t("mounting-proposal-text", "±1,5 m extension dan ±2–2,5 m pole adalah proposal meeting—bukan dimensi final.", 76, 548, 492, 54, { fontSize: 21, bold: true, color: C.amber, alignment: "center" }),
      rect("mounting-image-backing", 636, 146, 592, 444, C.panelSoft, C.rule, 1),
      t("mounting-caption", "Referensi survey historis—bukan layout aktif atau approved plot plan.", 636, 604, 592, 28, { fontSize: 16, color: C.muted, alignment: "center" }),
    ]);
    await addImage(slide, IMG_MAP, "Referensi survey historis dan catatan penempatan sistem", { left: 636, top: 146, width: 592, height: 444 }, "cover", { left: 0.01, top: 0.02, right: 0.01, bottom: 0.02 });
    sources(slide, [
      "Catatan meeting dan referensi survey historis yang disediakan pengguna.",
      "Laporan internal: mounting, antenna, cable, grounding, dan site-interface requirements.",
    ]);
  }

  // 14 — roadmap three-card timeline
  {
    const slide = deck.slides.add();
    compose(slide, "roadmap-three-card", [
      ...base(slide, "Target 2027 dimulai dari support pack 2026", 14, "ROADMAP"),
      line("roadmap-track", 72, 582, 1135, C.ink, 1),
      shape({ name: "roadmap-dot-1", geometry: "ellipse", fill: C.ink, position: { left: 72, top: 576 }, width: 12, height: 12 }),
      shape({ name: "roadmap-dot-2", geometry: "ellipse", fill: C.ink, position: { left: 452, top: 576 }, width: 12, height: 12 }),
      shape({ name: "roadmap-dot-3", geometry: "ellipse", fill: C.ink, position: { left: 832, top: 576 }, width: 12, height: 12 }),
      rect("roadmap-card-1", 72, 154, 336, 360, C.panelSoft, "none", 0),
      rect("roadmap-card-2", 452, 154, 336, 360, C.blueSoft, "none", 0),
      rect("roadmap-card-3", 832, 154, 376, 360, C.panelSoft, "none", 0),
      t("roadmap-1-title", "AGUSTUS 2026", 102, 186, 276, 30, { fontSize: 24, bold: true, color: C.blue }),
      t("roadmap-1-body", "• Enam keputusan internal\n• RFI terkonsolidasi\n• Datasheet + measurement plan\n• Pre-survey pack dan permit request", 102, 246, 276, 194, { fontSize: 22 }),
      t("roadmap-2-title", "SEPTEMBER 2026", 482, 186, 276, 30, { fontSize: 24, bold: true, color: C.blue }),
      t("roadmap-2-body", "• Survey dimensi/HSE/RF/jaringan\n• Freeze phase-1 interface\n• Support, cable, pole, drawing/BOM\n• Submit sebelum akhir bulan", 482, 246, 276, 194, { fontSize: 22 }),
      t("roadmap-3-title", "OKT 2026 → SEP 2027", 862, 186, 316, 30, { fontSize: 24, bold: true, color: C.blue }),
      t("roadmap-3-body", "• Design closure + FAT\n• Certification workstream\n• Contract, installation, IT onboarding\n• SAT, soak, training, handover\n• Field acceptance target", 862, 246, 316, 224, { fontSize: 22 }),
      t("roadmap-label-1", "DECISION PACK", 72, 612, 300, 22, { fontSize: 17, bold: true }),
      t("roadmap-label-2", "SUPPORT PACKAGE", 452, 612, 300, 22, { fontSize: 17, bold: true }),
      t("roadmap-label-3", "READY → ACCEPTED", 832, 612, 376, 22, { fontSize: 17, bold: true }),
    ]);
    sources(slide, ["Rekaman meeting, catatan target, dan rencana kerja berbasis tanggal pada laporan internal."]);
  }

  // 15 — ownership three-column
  {
    const slide = deck.slides.add();
    compose(slide, "ownership-three-column", [
      ...base(slide, "Ownership ditetapkan per organisasi", 15, "RESPONSIBILITY SPLIT"),
      t("ownership-intro", "Nama individual dan signatory harus disahkan; tidak disimpulkan dari audio tanpa diarization.", 52, 130, 1176, 42, { fontSize: 22, color: C.muted }),
      rect("owner-lgu", 52, 204, 350, 374, C.blueSoft, "none", 0),
      rect("owner-pertamina", 465, 204, 350, 374, C.panelSoft, "none", 0),
      rect("owner-vendor", 878, 204, 350, 374, C.panelSoft, "none", 0),
      t("owner-lgu-title", "LGU", 82, 236, 290, 42, { fontSize: 34, bold: true, color: C.blue }),
      t("owner-lgu-body", "R / A untuk:\n• Device datasheet dan BOM\n• GLD power/FAT dan CH energy\n• Gateway config/test support\n• Server package dan runbook\n• Controlled design dossier", 82, 302, 290, 224, { fontSize: 21 }),
      t("owner-pertamina-title", "PERTAMINA", 495, 236, 290, 42, { fontSize: 34, bold: true }),
      t("owner-pertamina-body", "A / C untuk:\n• Area classification dan HSE basis\n• Site power, cable, structure\n• Permit, contractor, installation\n• IT platform, VLAN/firewall/policy\n• Acceptance dan sign-off", 495, 302, 290, 224, { fontSize: 21 }),
      t("owner-vendor-title", "VENDOR / ExCB", 908, 236, 290, 42, { fontSize: 30, bold: true }),
      t("owner-vendor-body", "R / C untuk:\n• Exact part dan certificate data\n• Assessment/test schedule\n• Certificate scope dan conditions\n• Battery/solar/enclosure evidence\n• Inspection support", 908, 302, 290, 224, { fontSize: 21 }),
      t("ownership-key", "R = Responsible • A = Accountable • C = Consulted", 52, 606, 1176, 28, { fontSize: 18, bold: true, color: C.muted, alignment: "center" }),
    ]);
    sources(slide, ["RACI organisasi pada laporan internal; owner personal belum disahkan."]);
  }

  // 16 — close with explicit decisions
  {
    const slide = deck.slides.add();
    compose(slide, "closing-decisions", [
      ...base(slide, "Enam keputusan untuk mulai bergerak", 16, "DECISION REQUEST"),
      t("decision-intro", "Setiap keputusan harus menghasilkan owner, due date, dan evidence gate.", 52, 132, 1176, 36, { fontSize: 22, color: C.muted }),
      t("decision-1-num", "01", 52, 202, 70, 42, { fontSize: 28, bold: true, color: C.blue }),
      t("decision-1", "Setujui 24 VDC/2 A provisional dan closure proteksi input GLD.", 130, 202, 470, 48, { fontSize: 22, bold: true }),
      t("decision-2-num", "02", 52, 294, 70, 42, { fontSize: 28, bold: true, color: C.blue }),
      t("decision-2", "Pertahankan safety hold; trial hanya pada titik tertulis non-hazardous.", 130, 294, 470, 54, { fontSize: 22, bold: true }),
      t("decision-3-num", "03", 52, 394, 70, 42, { fontSize: 28, bold: true, color: C.blue }),
      t("decision-3", "Pilih arah TLS end-to-end atau exception terisolasi yang formal.", 130, 394, 470, 54, { fontSize: 22, bold: true }),
      t("decision-4-num", "04", 662, 202, 70, 42, { fontSize: 28, bold: true, color: C.blue }),
      t("decision-4", "Approve baseline server pilot dan owner platform/operations.", 740, 202, 470, 48, { fontSize: 22, bold: true }),
      t("decision-5-num", "05", 662, 294, 70, 42, { fontSize: 28, bold: true, color: C.blue }),
      t("decision-5", "Konfirmasi isi support pack akhir September dan agenda next survey.", 740, 294, 470, 54, { fontSize: 22, bold: true }),
      t("decision-6-num", "06", 662, 394, 70, 42, { fontSize: 28, bold: true, color: C.blue }),
      t("decision-6", "Tetapkan accountable owner dan signatory untuk setiap workstream.", 740, 394, 470, 54, { fontSize: 22, bold: true }),
      rect("decision-output", 52, 520, 1176, 116, C.blueSoft, "none", 0),
      t("decision-output-title", "OUTPUT RAPAT", 82, 548, 220, 28, { fontSize: 22, bold: true, color: C.blue }),
      t("decision-output-body", "Decision log • owner organisasi • due date • acceptance authority • bukti penutupan", 302, 544, 896, 40, { fontSize: 26, bold: true, alignment: "center" }),
      t("decision-output-note", "Dengan enam keputusan ini, tim dapat bergerak tanpa mengubah asumsi menjadi klaim readiness.", 302, 590, 896, 28, { fontSize: 19, color: C.muted, alignment: "center" }),
    ]);
    sources(slide, ["Sintesis keputusan, RFI, roadmap, dan acceptance gates pada laporan internal."]);
  }

  const renderDir = path.join(TMP_DIR, "artifact-render");
  await fs.mkdir(renderDir, { recursive: true });
  for (const [index, slide] of deck.slides.items.entries()) {
    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    const png = await deck.export({ slide, format: "png", scale: 1 });
    await writeBlob(path.join(renderDir, `${stem}.png`), png);
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(path.join(renderDir, `${stem}.layout.json`), await layout.text(), "utf8");
  }
  const montage = await deck.export({ format: "webp", montage: true, scale: 1 });
  await writeBlob(path.join(renderDir, "deck-montage.webp"), montage);

  const inspection = await deck.inspect({ kind: "slide,textbox,shape,image,table,notes", maxChars: 100000 });
  await fs.writeFile(path.join(TMP_DIR, "deck-inspect.ndjson"), inspection.ndjson, "utf8");

  const pptx = await PresentationFile.exportPptx(deck);
  await pptx.save(FINAL_PPTX);

  console.log(JSON.stringify({ output: FINAL_PPTX, slides: deck.slides.items.length, renderDir }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
