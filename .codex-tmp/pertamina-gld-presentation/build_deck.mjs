import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
const pptxgen = require("pptxgenjs");
const repo = "D:\\ITB\\BAHAN TA\\SMART FARMING\\BAHAN DOKTOR\\PROYEK GAS LEAK\\PertaminaGLD_Github";
const out = path.join(repo, "Pertamina_GLD_Detailed_Presentation.pptx");
const pptx = new pptxgen();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "OpenAI Codex";
pptx.company = "Pertamina GLD Project";
pptx.subject = "Detailed technical presentation: design, operation, specification, and comparison results";
pptx.title = "Pertamina Gas Leak Detection - Presentasi Teknis Detail";
pptx.lang = "id-ID";
pptx.theme = {
  headFontFace: "Arial",
  bodyFontFace: "Arial",
  lang: "id-ID"
};
pptx.defineLayout({ name: "CUSTOM_WIDE", width: 13.333, height: 7.5 });
pptx.layout = "CUSTOM_WIDE";

const C = {
  ink: "111827",
  muted: "4B5563",
  light: "F3F4F6",
  line: "CBD5E1",
  accent: "2563EB",
  accent2: "0EA5E9",
  good: "16A34A",
  warn: "F59E0B",
  red: "DC2626",
  white: "FFFFFF",
  black: "000000"
};

const W = 13.333;
const H = 7.5;
const M = 0.55;
const titleY = 0.42;
const bodyTop = 1.18;

const src = {
  readme: "README.md",
  gld: "docs/design/gld/final_design.md",
  ch: "docs/design/ch/final_design.md",
  gw: "docs/design/gw/final_design.md",
  server: "docs/design/server/final_design.md",
  protocol: "Pertamina_GLD_Protocol_Reference.md",
  payload: "docs/design/gld-ch/payload-contract.draft.md",
  progress: "docs/progress.md",
  activity: "ActivityAI/codexactivity.md",
  fieldLog: "server/nodered/field-test-logs/field-test-20260729.csv",
  tpl: "docs/firmware/gld-tpl5010-powercycle-test-com3-report.md",
  mapping: "docs/firmware/gld-ads-mcp-channel-mapping-report.md",
  audit: "audit-report/00-summary.md",
  nodered: "server/nodered/README.md"
};

function addBg(slide) {
  slide.background = { color: C.white };
  slide.addShape(pptx.ShapeType.rect, {
    x: 0, y: 0, w: W, h: H,
    fill: { color: C.white },
    line: { color: C.white, transparency: 100 }
  });
}

function footer(slide, n) {
  slide.addShape(pptx.ShapeType.line, {
    x: M, y: 7.07, w: W - 2 * M, h: 0,
    line: { color: "E5E7EB", width: 0.8 }
  });
  slide.addText("Pertamina GLD - technical presentation", {
    x: M, y: 7.16, w: 4.8, h: 0.16, fontSize: 7.5, color: "6B7280", margin: 0
  });
  slide.addText(String(n).padStart(2, "0"), {
    x: W - M - 0.45, y: 7.16, w: 0.45, h: 0.16, fontSize: 7.5, color: "6B7280", align: "right", margin: 0
  });
}

function title(slide, text, sub) {
  slide.addText(text, {
    x: M, y: titleY, w: 10.95, h: 0.82,
    fontFace: "Arial", fontSize: 24, bold: true, color: C.ink,
    margin: 0, breakLine: false, fit: "shrink"
  });
  if (sub) {
    slide.addText(sub, {
      x: M, y: 1.12, w: 9.8, h: 0.24,
      fontSize: 11.5, color: C.muted, margin: 0, fit: "shrink"
    });
  }
}

function note(slide, sources) {
  slide.addNotes(`[Sources]\n${sources.map(s => `- ${s}`).join("\n")}`);
}

function bullet(slide, items, x, y, w, h, opts = {}) {
  const runs = [];
  for (const item of items) {
    runs.push({ text: item, options: { bullet: { indent: 14 }, hanging: 4, breakLine: true } });
  }
  slide.addText(runs, {
    x, y, w, h,
    fontSize: opts.fontSize ?? 12.5,
    color: opts.color ?? C.ink,
    breakLine: false,
    margin: opts.margin ?? 0.06,
    fit: "shrink",
    valign: "mid"
  });
}

function label(slide, text, x, y, w, h, fill = C.light, color = C.ink, size = 12) {
  slide.addShape(pptx.ShapeType.rect, {
    x, y, w, h,
    fill: { color: fill },
    line: { color: fill },
  });
  slide.addText(text, {
    x: x + 0.09, y: y + 0.08, w: w - 0.18, h: h - 0.12,
    fontSize: size, bold: true, color, margin: 0.02, fit: "shrink",
    valign: "mid"
  });
}

function smallText(slide, text, x, y, w, h, size = 10.5, color = C.muted) {
  slide.addText(text, { x, y, w, h, fontSize: size, color, margin: 0.02, fit: "shrink", valign: "mid" });
}

function box(slide, x, y, w, h, heading, body, opts = {}) {
  slide.addShape(pptx.ShapeType.rect, {
    x, y, w, h,
    fill: { color: opts.fill ?? C.light },
    line: { color: opts.line ?? "E5E7EB", width: 1 }
  });
  slide.addText(heading, {
    x: x + 0.16, y: y + 0.14, w: w - 0.32, h: 0.28,
    fontSize: opts.headingSize ?? 13, bold: true, color: opts.headingColor ?? C.ink,
    margin: 0, fit: "shrink"
  });
  slide.addText(body, {
    x: x + 0.16, y: y + 0.52, w: w - 0.32, h: h - 0.64,
    fontSize: opts.bodySize ?? 10.7, color: opts.bodyColor ?? C.muted,
    margin: 0, fit: "shrink", valign: "top"
  });
}

function arrow(slide, x1, y1, x2, y2, color = C.accent) {
  slide.addShape(pptx.ShapeType.line, {
    x: x1, y: y1, w: x2 - x1, h: y2 - y1,
    line: { color, width: 1.5, beginArrowType: "none", endArrowType: "triangle" }
  });
}

function table(slide, values, x, y, w, h, widths, fontSize = 8.8) {
  slide.addTable(values, {
    x, y, w, h,
    colW: widths,
    border: { type: "solid", color: "D1D5DB", pt: 0.6 },
    fontSize
  });
  // Header overlay keeps header readable across PowerPoint versions.
  slide.addShape(pptx.ShapeType.rect, {
    x, y, w, h: Math.min(0.34, h / values.length),
    fill: { color: C.ink },
    line: { color: C.ink }
  });
  const rowH = Math.min(0.34, h / values.length);
  let cx = x;
  for (let i = 0; i < values[0].length; i++) {
    slide.addText(String(values[0][i]), {
      x: cx + 0.04, y: y + 0.07, w: widths[i] - 0.08, h: rowH - 0.08,
      fontSize: fontSize, color: C.white, bold: true, margin: 0, fit: "shrink"
    });
    cx += widths[i];
  }
}

function addSectionMarker(slide, text) {
  slide.addText(text.toUpperCase(), { x: M, y: 0.22, w: 2.8, h: 0.22, fontSize: 8.5, bold: true, color: C.accent, margin: 0 });
}

let n = 1;
const maxSlides = Number(process.env.MAX_SLIDES || "0");
function addSlide(kind, builder, sources) {
  if (maxSlides && n > maxSlides) {
    n++;
    return null;
  }
  const slide = pptx.addSlide();
  addBg(slide);
  builder(slide);
  footer(slide, n++);
  if (sources) note(slide, sources);
  return slide;
}

addSlide("cover", (s) => {
  s.addText("Pertamina Gas Leak Detection", {
    x: M, y: 1.15, w: 8.5, h: 0.75,
    fontSize: 40, bold: true, color: C.ink, margin: 0, fit: "shrink"
  });
  s.addText("Desain sistem, cara kerja, spesifikasi, dan hasil perbandingan", {
    x: M, y: 2.05, w: 7.7, h: 0.42, fontSize: 17, color: C.muted, margin: 0, fit: "shrink"
  });
  s.addText("Ringkasan teknis berbasis dokumen desain, protokol, firmware, Node-RED, dan log uji lapangan repo.", {
    x: M, y: 5.92, w: 7.4, h: 0.58, fontSize: 12, color: C.muted, margin: 0, fit: "shrink"
  });
  s.addShape(pptx.ShapeType.line, { x: M, y: 5.63, w: 7.8, h: 0, line: { color: C.accent, width: 2.2 } });
  box(s, 9.1, 1.25, 3.35, 1.05, "Output utama", "Sistem GLD siap dijelaskan sebagai rantai sensor - edge inference - LoRa STAR/MESH - MQTT/Node-RED.");
  box(s, 9.1, 2.65, 3.35, 1.05, "Bukti kunci", "Normal pull, alarm push, dataset capture, TPL5010 sleep-wake, dan field-test logging sudah terdokumentasi.");
  box(s, 9.1, 4.05, 3.35, 1.05, "Batas klaim", "Akurasi model final tidak diklaim; repo menandai model replacement sebagai pekerjaan lanjutan.");
}, [src.readme, src.progress, src.audit]);

addSlide("takeaway", (s) => {
  addSectionMarker(s, "Executive view");
  title(s, "Sistem sudah membentuk rantai deteksi end-to-end", "Dari sensor gas di node ujung sampai dashboard server lokal.");
  box(s, 0.75, 1.65, 3.7, 1.4, "1. Edge detection", "GLD membaca 8 sensor MQ melalui ADS1256, melakukan moving average dan inferensi ML lokal, lalu membentuk payload 4 byte yang terenkripsi.", { fill: "F8FAFC" });
  box(s, 4.85, 1.65, 3.7, 1.4, "2. Resilient radio path", "CH memisahkan STAR untuk GLD dan MESH untuk CH/Gateway, menyimpan NodeCache, serta meneruskan alarm prioritas tanpa menunggu pull.", { fill: "F8FAFC" });
  box(s, 8.95, 1.65, 3.7, 1.4, "3. Server observability", "Gateway mengubah frame MESH menjadi MQTT; Node-RED melakukan decrypt, dedup, alarm routing, topology UI, dan field-test logs.", { fill: "F8FAFC" });
  label(s, "Kesimpulan teknis", 0.75, 4.25, 2.15, 0.45, C.ink, C.white, 12);
  smallText(s, "Rantai normal dan alarm telah terbukti pada bench dan field-test, sementara klaim performa klasifikasi gas masih menunggu model trained final dan dataset validasi lapangan.", 3.08, 4.14, 8.95, 0.78, 16, C.ink);
}, [src.gld, src.ch, src.gw, src.server, src.progress, src.activity]);

addSlide("agenda", (s) => {
  addSectionMarker(s, "Agenda");
  title(s, "Alur pembahasan mengikuti rantai sistem", "Setiap bagian menjawab apa yang dibangun, bagaimana bekerja, dan bukti hasilnya.");
  const rows = [
    ["01", "Desain sistem", "Topologi GLD, CH, Gateway, server"],
    ["02", "Cara kerja", "Jalur normal pull, alarm push, downlink, dataset/nulling"],
    ["03", "Spesifikasi", "Hardware, radio, payload, power, kapasitas cache"],
    ["04", "Hasil uji", "Bench, field-test logs, power-cycle, mapping sensor"],
    ["05", "Perbandingan", "Mode normal vs alarm, bench vs field, sebelum vs sesudah hardening"],
    ["06", "Implikasi", "Keterbatasan dan rekomendasi pengembangan"]
  ];
  table(s, rows, 0.9, 1.65, 11.5, 4.15, [0.72, 2.55, 8.23], 11);
}, [src.readme, src.protocol, src.progress]);

addSlide("architecture", (s) => {
  addSectionMarker(s, "Desain sistem");
  title(s, "Arsitektur dibagi menjadi empat peran yang jelas", "GLD menangkap data, CH mengelola cluster, Gateway menjembatani MESH-MQTT, Server memproses data.");
  const y = 2.1;
  box(s, 0.65, y, 2.45, 1.3, "GLD node", "8 MQ sensors\nADS1256 24-bit\nML inference\nAES-GCM uplink", { fill: "EFF6FF", headingColor: C.accent });
  box(s, 3.75, y, 2.45, 1.3, "Cluster Head", "STAR receiver\nNodeCache 32\nAlarm queue\nMESH parent", { fill: "F8FAFC" });
  box(s, 6.85, y, 2.45, 1.3, "Gateway", "MESH root\nWiFi/LAN\nMQTT bridge\nTopology publish", { fill: "F8FAFC" });
  box(s, 9.95, y, 2.45, 1.3, "Server", "Node-RED\nAES decrypt\nDedup/replay guard\nDashboard/logging", { fill: "F8FAFC" });
  arrow(s, 3.1, y + 0.65, 3.74, y + 0.65);
  arrow(s, 6.2, y + 0.65, 6.84, y + 0.65);
  arrow(s, 9.3, y + 0.65, 9.94, y + 0.65);
  smallText(s, "LoRa STAR 920 MHz SF7", 2.65, y + 0.16, 1.1, 0.22, 8.8);
  smallText(s, "LoRa MESH 921 MHz SF9", 5.66, y + 0.16, 1.2, 0.22, 8.8);
  smallText(s, "MQTT :1884", 8.97, y + 0.16, 0.8, 0.22, 8.8);
  label(s, "Design principle", 0.75, 4.85, 1.75, 0.36, C.ink, C.white, 10.5);
  bullet(s, [
    "Gas inference tetap di edge sehingga jaringan hanya membawa hasil ringkas.",
    "CH tidak perlu decrypt payload; ia menjaga cache dan prioritas alarm sebagai opaque record.",
    "Server menjadi tempat decrypt, dedup, topology state, command, dan logging."
  ], 2.75, 4.62, 9.6, 1.05, { fontSize: 13 });
}, [src.gld, src.ch, src.gw, src.server, src.payload]);

addSlide("gld-design", (s) => {
  addSectionMarker(s, "Desain GLD");
  title(s, "GLD menyatukan sensing, inference, crypto, dan power management", "Runtime aktif memakai mode persistent: inference, dataset, dan nulling.");
  box(s, 0.7, 1.5, 3.05, 1.2, "Sensing", "8 sensor MQ: MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2. ADS input 0..7 dan TCA/MCP mux 7,6,5,0,1,2,3,4.", { fill: "F8FAFC" });
  box(s, 4.0, 1.5, 2.75, 1.2, "Inference", "Scan tiap 1.000 ms, moving average 10 sampel, model class dipetakan ke clearGas/LPG/methane/propane/butane/anomaly.", { fill: "F8FAFC" });
  box(s, 7.0, 1.5, 2.55, 1.2, "Uplink", "Payload 4 byte dienkripsi AES-128-GCM menjadi 29 byte, dibungkus AppFrame 39 byte.", { fill: "F8FAFC" });
  box(s, 9.8, 1.5, 2.8, 1.2, "Power", "24 V, 5 V, atau battery. Battery session pulse DONE lalu CLR untuk mematikan main rail.", { fill: "F8FAFC" });
  const rows = [
    ["Mode", "Fungsi", "Koneksi"],
    ["inference", "ADS scan, ML, LoRa uplink, RX window", "WiFi off"],
    ["dataset", "Capture data via MQTT untuk training", "WiFi/MQTT on"],
    ["nulling", "Kalibrasi DAC baseline per sensor", "Offline"]
  ];
  table(s, rows, 0.78, 3.42, 5.95, 2.05, [1.25, 3.45, 1.25], 9.2);
  label(s, "Alarm rule", 7.15, 3.45, 1.45, 0.36, C.red, C.white, 10.5);
  smallText(s, "alarm = gasClass != clearGas && confidence >= 30", 8.78, 3.4, 3.65, 0.36, 12.5, C.ink);
  bullet(s, [
    "Normal monitoring mengirim frame setiap 10 detik.",
    "Alarm meminta compact ACK dan dapat diulang jika belum terkonfirmasi.",
    "Downlink SET_MODE diterima hanya setelah uplink membuka RX window."
  ], 7.18, 4.15, 5.1, 1.28, { fontSize: 12.1 });
}, [src.gld, src.payload, src.mapping]);

addSlide("ch-design", (s) => {
  addSectionMarker(s, "Desain CH");
  title(s, "CH adalah buffer, router, dan pengawal prioritas alarm", "Dual radio memisahkan trafik GLD lokal dan trafik MESH menuju parent/Gateway.");
  box(s, 0.8, 1.6, 2.65, 1.2, "Radio A - STAR", "Menerima GLD SENSOR_DATA pada 920 MHz SF7, mengirim compact alarm ACK dan downlink GLD.", { fill: "EFF6FF" });
  box(s, 3.8, 1.6, 2.65, 1.2, "Radio B - MESH", "Meneruskan alarm, CH_HELLO, pull response, dan relay frame pada 921 MHz SF9.", { fill: "F8FAFC" });
  box(s, 6.8, 1.6, 2.65, 1.2, "NodeCache", "32 slot, menyimpan seq, flags, lastSeen, dan encrypted payload terbaru dari GLD.", { fill: "F8FAFC" });
  box(s, 9.8, 1.6, 2.65, 1.2, "Routing state", "JOINING, JOINED, failover, parent dwell, anti-loop, dan route verify.", { fill: "F8FAFC" });
  const rows = [
    ["Kapasitas / ambang", "Nilai", "Implikasi"],
    ["NodeCache", "32 GLD", "satu snapshot terbaru per node"],
    ["Alarm queue", "8 item", "alarm diprioritaskan dari data normal"],
    ["Data stale", "5 menit", "tidak ikut pull response"],
    ["Entry expire", "1 jam", "slot cache dibersihkan"],
    ["Response MESH", "maks 2 GLD record", "34 byte per record, payload max 80 byte"]
  ];
  table(s, rows, 0.92, 3.45, 11.5, 2.05, [2.7, 1.45, 7.35], 8.9);
}, [src.ch, src.payload, src.protocol]);

addSlide("gw-server", (s) => {
  addSectionMarker(s, "Gateway dan server");
  title(s, "Gateway dan Node-RED mengubah radio mesh menjadi data operasional", "Gateway tetap sederhana; server memikul decode, dedup, command, UI, dan logging.");
  const rows = [
    ["Layer", "Input utama", "Output utama", "Tanggung jawab"],
    ["Gateway", "LoRa MESH RX", "MQTT uplink/status/topology", "Bridge WiFi/MQTT, compact ACK, CH_CONFIG response"],
    ["Node-RED", "MQTT uplink/topology/cmd", "decoded/alarm/topology/error", "AES-GCM decrypt, replay guard, topology state, command signing"],
    ["Dataset flow", "MQTT dataset data", "MySQL + CSV", "Capture training data dengan schema sensor_voltage/gain/feature_order"],
    ["Operator hub", "COM + HTTP local", "Provisioning/monitoring", "Flash firmware, configure NVS, observe topology"]
  ];
  table(s, rows, 0.75, 1.55, 11.95, 2.45, [1.35, 2.15, 2.55, 5.9], 8.4);
  label(s, "MQTT topics kunci", 0.85, 4.65, 2.05, 0.36, C.ink, C.white, 10.5);
  bullet(s, [
    "gld/gateway/uplink - JSON wrapper frame MESH dari Gateway.",
    "gld/server/decoded - data GLD non-alarm setelah decrypt.",
    "gld/server/alarm - alarm GLD yang lolos autentikasi.",
    "gld/gateway/cmd/pull dan cmd/node - jalur perintah dari server."
  ], 3.18, 4.38, 8.9, 1.18, { fontSize: 11.4 });
}, [src.gw, src.server, src.nodered]);

addSlide("workflow-normal", (s) => {
  addSectionMarker(s, "Cara kerja");
  title(s, "Jalur normal memakai pull agar data cache terkirim sesuai kebutuhan", "Data clear/normal tersimpan di CH sampai server meminta melalui hopList rute.");
  const y = 2.0;
  label(s, "1", 0.8, y, 0.45, 0.45, C.accent, C.white, 16);
  smallText(s, "GLD kirim SENSOR_DATA normal setiap 10 s", 1.35, y - 0.02, 2.0, 0.55, 11.5, C.ink);
  arrow(s, 3.35, y + 0.22, 4.05, y + 0.22);
  label(s, "2", 4.1, y, 0.45, 0.45, C.accent, C.white, 16);
  smallText(s, "CH update NodeCache dan tandai unsent", 4.68, y - 0.02, 2.0, 0.55, 11.5, C.ink);
  arrow(s, 6.72, y + 0.22, 7.42, y + 0.22);
  label(s, "3", 7.47, y, 0.45, 0.45, C.accent, C.white, 16);
  smallText(s, "Server publish cmd/pull dengan hopList", 8.05, y - 0.02, 2.0, 0.55, 11.5, C.ink);
  arrow(s, 10.08, y + 0.22, 10.78, y + 0.22);
  label(s, "4", 10.83, y, 0.45, 0.45, C.accent, C.white, 16);
  smallText(s, "CH balas CLUSTER_DATA_RESPONSE", 11.4, y - 0.02, 1.2, 0.55, 11.5, C.ink);
  const rows = [
    ["Bukti bench", "Nilai terverifikasi"],
    ["requestId", "1"],
    ["recordCount", "1"],
    ["nodeIdHex", "0xF001"],
    ["decryptOk", "true"],
    ["gasClass", "0 clearGas"],
    ["confidence", "100"]
  ];
  table(s, rows, 0.9, 3.45, 4.6, 2.35, [2.15, 2.45], 9.5);
  box(s, 6.1, 3.52, 5.9, 1.65, "Interpretasi", "Normal path efektif untuk polling berkala: server hanya menarik cache CH ketika route tersedia, sedangkan alarm tidak menunggu mekanisme ini.", { fill: "EFF6FF", bodySize: 13 });
}, [src.protocol, src.progress, src.payload]);

addSlide("workflow-alarm", (s) => {
  addSectionMarker(s, "Cara kerja");
  title(s, "Jalur alarm bersifat push dan prioritas", "Saat gasClass bukan clearGas dan confidence cukup, CH meneruskan alarm tanpa menunggu request server.");
  box(s, 0.8, 1.55, 2.7, 1.05, "GLD alarm", "typeFlags 0x50/0xD0, payload AES-GCM, compact ACK diperlukan.", { fill: "FEF2F2", headingColor: C.red });
  arrow(s, 3.55, 2.08, 4.25, 2.08, C.red);
  box(s, 4.3, 1.55, 2.7, 1.05, "CH alarm queue", "Update cache, ACK ke GLD, enqueue AlarmPush ke MESH.", { fill: "F8FAFC" });
  arrow(s, 7.05, 2.08, 7.75, 2.08, C.red);
  box(s, 7.8, 1.55, 2.7, 1.05, "Gateway", "Terima MESH alarm, publish MQTT, kirim compact ACK ke CH.", { fill: "F8FAFC" });
  arrow(s, 10.55, 2.08, 11.25, 2.08, C.red);
  box(s, 11.3, 1.55, 1.25, 1.05, "Server", "gld/server/alarm", { fill: "FEF2F2", bodySize: 10 });
  const rows = [
    ["Bukti alarm", "Nilai"],
    ["Topic", "gld/server/alarm"],
    ["outer.typeFlags", "208 / 0xD0"],
    ["gasClass", "1 LPG (bench)"],
    ["confidence", "30"],
    ["decryptOk", "true"]
  ];
  table(s, rows, 0.9, 3.35, 4.85, 2.1, [2.15, 2.7], 9.2);
  box(s, 6.45, 3.5, 5.65, 1.42, "Mengapa jalur ini berbeda", "Alarm adalah traffic darurat. Sistem menukar efisiensi polling dengan latensi lebih rendah: CH langsung push ke parent/Gateway, lalu server memproses alarm sebagai stream MQTT.", { fill: "FFF7ED", bodySize: 12.5 });
}, [src.gld, src.ch, src.gw, src.server, src.progress]);

addSlide("spec-radio-protocol", (s) => {
  addSectionMarker(s, "Spesifikasi");
  title(s, "Spesifikasi radio dan payload dibuat ringkas tetapi autentik", "Frame GLD aktif hanya membawa hasil klasifikasi dan baterai, bukan raw sensor penuh.");
  const radio = [
    ["Domain", "Freq", "BW", "SF", "CR", "Sync", "TX"],
    ["STAR GLD-CH", "920.0 MHz", "125 kHz", "7", "4/5", "0x12", "17 dBm"],
    ["MESH CH-GW", "921.0 MHz", "125 kHz", "9", "4/5", "0x34", "17 dBm"],
    ["Field-test MESH", "921.0 MHz", "125 kHz", "9", "4/5", "0x34", "hingga 22 dBm"]
  ];
  table(s, radio, 0.7, 1.45, 6.15, 1.5, [1.55, 1.1, 0.9, 0.55, 0.55, 0.75, 0.75], 8.5);
  const payload = [
    ["Item", "Ukuran", "Makna"],
    ["Plain payload", "4 byte", "gasClass, confidence, batteryMv"],
    ["AES-GCM payload", "29 byte", "keyId, nonce, ciphertext, tag"],
    ["AppFrame GLD", "39 byte", "8 byte header + 29 byte payload + CRC16"],
    ["GLDRecord", "34 byte", "nodeId, seq, flags, payloadLen, encrypted payload"],
    ["Cluster response", "maks 2 record", "6 + 2 x 34 = 74 byte dari 80 byte MESH"]
  ];
  table(s, payload, 7.1, 1.45, 5.55, 2.25, [1.55, 1.05, 2.95], 8.2);
  label(s, "Security boundary", 0.85, 4.35, 1.9, 0.36, C.ink, C.white, 10.5);
  bullet(s, [
    "GLD mengenkripsi data menggunakan AES-128-GCM dengan nonce 12 byte dan tag 12 byte.",
    "CH menyimpan payload terenkripsi sebagai opaque bytes; decrypt dilakukan di server.",
    "Downlink SET_MODE final memakai AES-CMAC 4 byte dan replay guard commandId."
  ], 3.05, 4.12, 8.9, 1.25, { fontSize: 12.4 });
}, [src.gld, src.ch, src.gw, src.payload, src.protocol]);

addSlide("spec-hardware", (s) => {
  addSectionMarker(s, "Spesifikasi");
  title(s, "Spesifikasi hardware difokuskan pada sensing, radio, dan daya", "Beberapa pin berbeda antara profil 4D ESP32-S3 dan WROOM bench.");
  const rows = [
    ["Komponen", "GLD", "CH", "Gateway"],
    ["MCU", "ESP32-S3 WROOM/4D", "ESP32-S3", "4D ESP32-S3"],
    ["Sensor", "8 MQ via ADS1256 + TCA/MCP", "Tidak baca sensor gas", "Tidak baca sensor gas"],
    ["Radio", "SX1262 STAR", "2x SX1262: STAR + MESH", "SX1262 MESH"],
    ["Power", "24 V / 5 V / battery + TPL5010", "battery ADC + WDT", "WiFi/LAN powered"],
    ["Storage", "NVS mode + nulling profile", "NVS CH ID + parent", "provisioned WiFi/MQTT"],
    ["Output lokal", "lamp/buzzer/LED opsional", "serial/topology logs", "status LED"]
  ];
  table(s, rows, 0.7, 1.45, 12.0, 2.75, [1.7, 3.55, 3.3, 3.45], 8.3);
  box(s, 0.82, 4.78, 3.6, 1.15, "Mapping sensor sudah direkonsiliasi", "ADS0..7 selaras dengan TCA/MCP 7,6,5,0,1,2,3,4; live sweep menunjukkan delta sekitar 469-484 mV.", { fill: "ECFDF5", headingColor: C.good, bodySize: 10.8 });
  box(s, 4.85, 4.78, 3.6, 1.15, "Battery wake terbukti fungsional", "TPL5010 + latch memberi rata-rata ON 60,22 s, OFF 100,71 s, periode wake-to-wake 160,95 s.", { fill: "EFF6FF", headingColor: C.accent, bodySize: 10.8 });
  box(s, 8.88, 4.78, 3.6, 1.15, "Produksi vs field-test dipisah", "README menegaskan env normal gld/ch/gw terpisah dari field-test dan power-cycle builds.", { fill: "F8FAFC", bodySize: 10.8 });
}, [src.gld, src.ch, src.gw, src.mapping, src.tpl, src.readme]);

addSlide("results-bench", (s) => {
  addSectionMarker(s, "Hasil uji");
  title(s, "Bench test membuktikan dua jalur komunikasi utama", "Normal path dan alarm path sama-sama mencapai Node-RED dengan decrypt valid.");
  box(s, 0.8, 1.62, 5.65, 1.1, "Normal pull path", "GLD -> CH cache -> Gateway -> Node-RED decoded.\nTerakhir: requestId=1, recordCount=1, decryptOk=true, clearGas confidence 100.", { fill: "ECFDF5", headingColor: C.good, bodySize: 12.2 });
  box(s, 6.9, 1.62, 5.65, 1.1, "Alarm push path", "GLD alarm -> CH alarmQueue -> Gateway -> Node-RED alarm.\nTerakhir: gld/server/alarm, decryptOk=true, LPG confidence 30.", { fill: "FEF2F2", headingColor: C.red, bodySize: 12.2 });
  const rows = [
    ["Aspek", "Normal pull", "Alarm push"],
    ["Trigger", "Server request", "GLD alarm flag"],
    ["CH behavior", "Pilih cache non-alarm oldest-first", "ACK GLD + enqueue alarm push"],
    ["Server topic", "gld/server/decoded", "gld/server/alarm"],
    ["Bukti terakhir", "recordCount=1, clearGas 100", "LPG 30, decryptOk=true"],
    ["Implikasi", "Cocok untuk monitoring periodik", "Cocok untuk kejadian darurat"]
  ];
  table(s, rows, 0.85, 3.25, 11.65, 2.25, [1.65, 4.65, 5.35], 8.6);
}, [src.progress, src.protocol, src.payload]);

addSlide("results-field", (s) => {
  addSectionMarker(s, "Hasil uji");
  title(s, "Field-test logger memberi bukti kuantitatif tanpa serial monitor", "Log 29 Juli 2026 merangkum topologi, pull, alarm, replay, dan kualitas link.");
  const metrics = [
    ["2.580", "baris log"],
    ["35", "pull request"],
    ["27", "alarm methane 0x1002"],
    ["10", "clearGas 0x1001"],
    ["-73,1 dBm", "RSSI rata-rata"],
    ["9,0 dB", "SNR rata-rata"]
  ];
  let x = 0.75, y = 1.55;
  for (let i = 0; i < metrics.length; i++) {
    const col = i % 3;
    const row = Math.floor(i / 3);
    box(s, x + col * 4.05, y + row * 1.28, 3.55, 0.92, metrics[i][0], metrics[i][1], {
      fill: i < 4 ? "F8FAFC" : "EFF6FF",
      headingSize: 22,
      headingColor: i === 2 ? C.red : C.accent,
      bodySize: 11
    });
  }
  const rows = [
    ["Response status", "Count", "Makna ringkas"],
    ["2, recordCount 0", "689", "Data belum tersedia / not available"],
    ["0, recordCount 1", "190", "Data OK berisi satu GLD record"],
    ["1, recordCount 0", "122", "Cache empty"]
  ];
  table(s, rows, 0.85, 4.35, 5.7, 1.5, [1.65, 0.85, 3.2], 8.5);
  box(s, 7.05, 4.4, 5.25, 1.22, "Catatan interpretasi", "RSSI/SNR rata-rata bagus untuk banyak event, tetapi ekstrem -127,5 dBm dan SNR -15,5 dB menunjukkan kondisi field masih memerlukan route selection, failover, dan logging pasif.", { fill: "FFF7ED", bodySize: 11.2 });
}, [src.activity, src.fieldLog]);

addSlide("comparison", (s) => {
  addSectionMarker(s, "Perbandingan");
  title(s, "Perbandingan: komunikasi matang, model final perlu validasi", "Yang sudah kuat adalah protokol dan jalur end-to-end; akurasi gas masih bergantung model replacement.");
  const rows = [
    ["Dimensi", "Sebelum/risiko", "Sesudah/bukti"],
    ["Normal data", "CH/Gateway harus selaras pull contract", "recordCount=1, decryptOk=true, clearGas 100"],
    ["Alarm data", "ACK/push sempat menjadi follow-up", "alarm methane 0x1002 dan LPG bench masuk server alarm"],
    ["Field observability", "Perlu serial monitor tiap board", "field-test CSV/JSONL pasif, 2.580 baris log"],
    ["Routing field", "Loop/weak link muncul pada jarak ekstrem", "GW retry, weak-link guard, CH field-test parent optimization"],
    ["Security", "Kunci kosong/test key tidak boleh jadi produksi", "flow wajib env key/token, replay state atomik"],
    ["ML inference", "Feature order pernah salah dan dataset repo kosong", "bug fixed; validasi model final tetap wajib"]
  ];
  table(s, rows, 0.65, 1.35, 12.05, 3.28, [1.45, 4.5, 6.1], 8.1);
  label(s, "Readiness call", 0.85, 5.2, 1.65, 0.36, C.ink, C.white, 10.5);
  smallText(s, "Sistem siap dipresentasikan sebagai platform deteksi dan komunikasi end-to-end. Untuk klaim deteksi gas produksi, gunakan dataset validasi real-hardware dan model trained final sebagai bukti tambahan.", 2.8, 5.0, 9.45, 0.75, 13.2, C.ink);
}, [src.progress, src.activity, src.audit, src.nodered]);

addSlide("power-result", (s) => {
  addSectionMarker(s, "Hasil uji");
  title(s, "Power-cycle battery sudah lulus secara fungsional", "TPL5010, latch, DONE, dan CLR terbukti membentuk siklus wake-sleep berulang.");
  const values = [
    ["ON", 60.22, C.good],
    ["OFF", 100.71, "9CA3AF"]
  ];
  const total = 160.93;
  let bx = 1.0;
  for (const [name, val, color] of values) {
    const bw = 10.8 * val / total;
    s.addShape(pptx.ShapeType.rect, { x: bx, y: 2.05, w: bw, h: 0.72, fill: { color }, line: { color } });
    s.addText(`${name} ${val.toFixed(2).replace(".", ",")} s`, { x: bx + 0.08, y: 2.27, w: bw - 0.16, h: 0.22, fontSize: 10.2, bold: true, color: name === "ON" ? C.white : C.ink, margin: 0, fit: "shrink" });
    bx += bw;
  }
  const rows = [
    ["Metric", "Nilai"],
    ["Rata-rata ON", "60,22 detik"],
    ["Rata-rata OFF lengkap", "100,71 detik"],
    ["Wake-to-wake", "160,95 detik"],
    ["Status", "PASS fungsional"],
    ["Keterbatasan", "Belum oscilloscope/logic analyzer"]
  ];
  table(s, rows, 0.95, 3.52, 4.75, 2.05, [2.55, 2.2], 9.5);
  box(s, 6.35, 3.75, 5.6, 1.36, "Makna untuk desain lapangan", "Firmware dapat mematikan main rail setelah sesi battery dan board dapat wake kembali otomatis. Ini mengurangi kebutuhan always-on MCU, meski arus ON/OFF dan waveform mikrodetik masih perlu pengukuran instrumen.", { fill: "EFF6FF", bodySize: 12.1 });
}, [src.tpl, src.gld]);

addSlide("limitations", (s) => {
  addSectionMarker(s, "Implikasi");
  title(s, "Keterbatasan yang perlu dinyatakan secara jujur", "Deck ini memisahkan bukti sistem dari klaim performa klasifikasi gas.");
  box(s, 0.85, 1.55, 3.55, 1.25, "Model gas final", "Repo menandai model replacement sebagai next step. Audit juga mencatat dataset CSV in-repo tidak cukup untuk regression check akurasi.", { fill: "FEF2F2", headingColor: C.red });
  box(s, 4.85, 1.55, 3.55, 1.25, "Pengukuran power", "TPL5010 PASS secara fungsional, tetapi waveform DONE/CLR/WAKE belum diverifikasi dengan oscilloscope.", { fill: "FFF7ED", headingColor: C.warn });
  box(s, 8.85, 1.55, 3.55, 1.25, "Field link budget", "Log menunjukkan link ekstrem sangat lemah; deployment butuh penempatan CH/GW, failover, dan threshold yang divalidasi.", { fill: "FFF7ED", headingColor: C.warn });
  label(s, "Rekomendasi berikutnya", 0.95, 3.75, 2.3, 0.36, C.ink, C.white, 10.5);
  bullet(s, [
    "Ambil dataset gas real-hardware per kelas dengan protokol label yang konsisten.",
    "Replace model_data dan scaler_params dari training final, lalu uji confusion matrix di hardware.",
    "Lakukan field range test dengan logger aktif: topology, pull, alarm, RSSI/SNR, dan route transitions.",
    "Ukur konsumsi arus ON/OFF dan waveform TPL5010 menggunakan oscilloscope atau logic analyzer."
  ], 3.55, 3.48, 8.75, 1.55, { fontSize: 12.3 });
}, [src.audit, src.tpl, src.activity, src.progress]);

addSlide("close", (s) => {
  addSectionMarker(s, "Penutup");
  title(s, "Platform end-to-end sudah ada; bukti model final menyusul", "Bagian komunikasi, protokol, topology, alarm, dan power sudah punya bukti teknis yang dapat dipresentasikan.");
  box(s, 0.9, 1.65, 3.55, 1.45, "Yang sudah kuat", "Desain modular GLD-CH-GW-Server, protokol AppFrame/AES, normal pull, alarm push, topology UI, dan field-test logging.", { fill: "ECFDF5", headingColor: C.good });
  box(s, 4.9, 1.65, 3.55, 1.45, "Yang perlu dijaga", "Pemakaian build produksi vs field-test, credential MQTT/AES, dan dokumentasi route/link quality saat deployment.", { fill: "EFF6FF", headingColor: C.accent });
  box(s, 8.9, 1.65, 3.55, 1.45, "Yang belum boleh diklaim berlebih", "Akurasi klasifikasi gas produksi sebelum ada dataset validasi dan model trained final dari hardware target.", { fill: "FEF2F2", headingColor: C.red });
  s.addText("Deck ini dirancang untuk menjadi bahan presentasi teknis: bisa dipakai langsung, lalu diperbarui ketika data akurasi model final tersedia.", {
    x: 1.05, y: 4.72, w: 10.95, h: 0.72,
    fontSize: 18, bold: true, color: C.ink, align: "center", margin: 0, fit: "shrink"
  });
}, [src.readme, src.progress, src.audit, src.activity]);

await pptx.writeFile({ fileName: out });
console.log(out);
