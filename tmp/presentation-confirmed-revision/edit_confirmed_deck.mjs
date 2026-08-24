import { FileBlob, PresentationFile } from "@oai/artifact-tool";
import fs from "node:fs/promises";
import path from "node:path";

const starterPptxPath = "D:/Github/PertaminaGLD/tmp/presentation-confirmed-revision/template-starter.pptx";
const finalPptxPath = "D:/Github/PertaminaGLD/output/presentation/Presentasi-Rapat-Cilacap-Terkonfirmasi-2026-08-19.pptx";
const previewDir = "D:/Github/PertaminaGLD/tmp/presentation-confirmed-revision/final-preview";
const layoutDir = "D:/Github/PertaminaGLD/tmp/presentation-confirmed-revision/final-layout";
const montagePath = "D:/Github/PertaminaGLD/tmp/presentation-confirmed-revision/final-montage.webp";

await fs.mkdir(path.dirname(finalPptxPath), { recursive: true });
await fs.mkdir(previewDir, { recursive: true });
await fs.mkdir(layoutDir, { recursive: true });

async function saveBlob(blob, outputPath) {
  if (blob && typeof blob.arrayBuffer === "function") {
    await fs.writeFile(outputPath, Buffer.from(await blob.arrayBuffer()));
    return;
  }
  if (blob instanceof Uint8Array || Buffer.isBuffer(blob)) {
    await fs.writeFile(outputPath, Buffer.from(blob));
    return;
  }
  throw new Error(`Expected a Blob or Uint8Array for ${outputPath}`);
}

const presentation = await PresentationFile.importPptx(await FileBlob.load(starterPptxPath));
const inventory = await presentation.inspect({
  kind: "slide,textbox,shape,image,table,chart,notes",
  maxChars: 250000,
});
const records = inventory.ndjson.split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));

function findRecord(slide, name, kinds = ["textbox", "shape"]) {
  const record = records.find((item) => item.slide === slide && item.name === name && kinds.includes(item.kind));
  if (!record) throw new Error(`Inherited element not found: slide ${slide}, ${name}`);
  return record;
}

function setText(slide, name, value) {
  const record = findRecord(slide, name);
  const target = presentation.resolve(record.id);
  target.text.set(value);
}

function setSlideTable(slide, values) {
  const record = records.find((item) => item.slide === slide && item.kind === "table");
  if (!record) throw new Error(`Inherited table not found on slide ${slide}`);
  const table = presentation.resolve(record.id);
  if (table.rowCount !== values.length || table.columnCount !== values[0].length) {
    throw new Error(`Table dimensions do not match on slide ${slide}`);
  }
  for (let row = 0; row < values.length; row += 1) {
    for (let column = 0; column < values[row].length; column += 1) {
      table.cells.set(row, column, values[row][column]);
    }
  }
}

function setNotes(slideNumber, lines) {
  const record = records.find((item) => item.slide === slideNumber && item.kind === "slide");
  if (!record) throw new Error(`Slide ${slideNumber} not found`);
  const slide = presentation.resolve(record.id);
  slide.speakerNotes.textFrame.setText(lines.join("\n"));
  slide.speakerNotes.setVisible(true);
}

function setFooter(slide, name) {
  setText(slide, name, "INTERNAL • 19 AGUSTUS 2026");
}

// Slide 1 — cover.
setText(1, "cover-kicker", "PERTAMINA • LGU | INTERNAL");
setText(1, "cover-title", "Ringkasan Meeting\ndan Rencana Implementasi");
setText(1, "cover-subtitle", "Keputusan terkonfirmasi, arsitektur, area SRU, kebutuhan site, dan rencana menuju target September 2027.");
setText(1, "cover-date", "19 AGUSTUS 2026");
setText(1, "cover-footer", "INTERNAL • TERKONFIRMASI");
setNotes(1, [
  "[Sources]",
  "- Konfirmasi pengguna, 19 Agustus 2026.",
  "- Rekaman dan catatan meeting.",
]);

// Slide 2 — outline.
setText(2, "section-2", "OUTLINE");
setText(2, "title-2", "Outline pembahasan");
setText(2, "outline-intro", "Lima bagian merangkum keputusan, rancangan, kebutuhan implementasi, dan tindak lanjut.");
setFooter(2, "footer-left-2");
setSlideTable(2, [
  ["01", "Hasil meeting dan agenda kunjungan"],
  ["02", "Arsitektur sistem dan ruang lingkup Cilacap"],
  ["03", "GLD, CH, serta bahan pembicaraan Gateway, jaringan, dan server"],
  ["04", "Lokasi SRU, mounting, dan kebutuhan site"],
  ["05", "Roadmap, pembagian tanggung jawab, dan tindak lanjut"],
]);
setNotes(2, [
  "[Sources]",
  "- Konfirmasi pengguna, 19 Agustus 2026.",
  "- Sintesis pembahasan program Kilang Cilacap.",
]);

// Slide 3 — meeting outcome.
setText(3, "section-3", "HASIL MEETING");
setText(3, "title-3", "Arah rapat: target kerja dan agenda kunjungan");
setText(3, "meeting-intro", "Catatan meeting dan konfirmasi lanjutan menetapkan empat arah utama:");
setText(3, "meeting-metric-1", "SEP 2027");
setText(3, "meeting-metric-1-label", "Target fase awal untuk Kilang Cilacap.");
setText(3, "meeting-metric-2", "AKHIR SEP 2026");
setText(3, "meeting-metric-2-label", "Paket support, kabel, material, dan drawing disiapkan.");
setText(3, "meeting-correction-title", "“3 minggu” mengacu pada kunjungan");
setText(3, "meeting-correction-body", "Per 10 Agustus 2026, kalimat “3 minggu lagi” berarti rencana kunjungan sekitar akhir Agustus 2026.");
setText(3, "meeting-contract", "Ruang lingkup Cilacap: 3 unit GLD; jumlah CH menyesuaikan kebutuhan cakupan area SRU.");
setText(3, "meeting-image-caption", "Catatan meeting sebagai referensi pembahasan.");
setFooter(3, "footer-left-3");
setNotes(3, [
  "[Sources]",
  "- Konfirmasi pengguna, 19 Agustus 2026.",
  "- Rekaman dan catatan meeting.",
  "- Acuan tanggal: 10 Agustus 2026; frasa tiga minggu merujuk pada rencana kunjungan.",
]);

// Slide 4 — architecture.
setText(4, "section-4", "ARSITEKTUR SISTEM");
setText(4, "title-4", "\u00A0Alur sistem GLD–CH–Gateway–Server");
setText(4, "architecture-sub", "Tiga GLD menjadi titik awal di Cilacap; jumlah CH menyesuaikan cakupan area SRU.");
setText(4, "node-gld-title", "GLD");
setText(4, "node-gld-body", "Sensing • inferensi\nSTAR uplink");
setText(4, "node-ch-title", "CH");
setText(4, "node-ch-body", "STAR receiver\nMESH relay");
setText(4, "node-gw-title", "GATEWAY");
setText(4, "node-gw-body", "Bridge radio–jaringan\nAgenda bersama IT");
setText(4, "node-server-title", "SERVER");
setText(4, "node-server-body", "Broker • dashboard\nAgenda bersama IT");
setText(4, "link-star", "STAR 920 MHz");
setText(4, "link-mesh", "MESH 921 MHz");
setText(4, "link-mqtt", "JARINGAN DATA");
setText(4, "architecture-note-title", "Ruang lingkup pembahasan");
setText(4, "architecture-note-body", "Alur GLD dan CH menjadi baseline sistem. Konfigurasi Gateway, jaringan, keamanan, dan server dibahas bersama tim IT sebelum ditetapkan.");
setFooter(4, "footer-left-4");
setNotes(4, [
  "[Sources]",
  "- Konfirmasi pengguna, 19 Agustus 2026.",
  "- Audit rangkaian, desain PCB, dan firmware.",
]);

// Slide 5 — confirmed status table.
setText(5, "section-5", "STATUS SISTEM");
setText(5, "title-5", "Status keputusan terkonfirmasi");
setText(5, "readiness-sub", "Baseline berikut memisahkan keputusan program dari agenda tindak lanjut implementasi.");
setFooter(5, "footer-left-5");
setSlideTable(5, [
  ["Area", "Keputusan saat ini", "Tindak lanjut"],
  ["GLD", "3 unit; catu 24 VDC/2 A", "Validasi rangkaian input dan FAT"],
  ["CH", "1 baterai 4000 mAh; 2 panel × 6 W", "Jumlah mengikuti cakupan SRU"],
  ["Gateway", "Menjadi agenda pembicaraan", "Bahas penempatan dan koneksi bersama IT"],
  ["Server", "Menjadi agenda pembicaraan", "Bahas layanan, keamanan, dan operasi"],
  ["Site", "Lokasi dialihkan dari LPG ke SRU", "Ukur mounting ... cm dan siapkan instalasi"],
]);
setNotes(5, [
  "[Sources]",
  "- Konfirmasi pengguna, 19 Agustus 2026.",
  "- Rekaman dan catatan meeting.",
]);

// Slide 6 — GLD power.
setText(6, "section-6", "DAYA GLD");
setText(6, "title-6", "Catu daya GLD ditetapkan 24 VDC/2 A");
setText(6, "power-rating", "24 VDC / 2 A");
setText(6, "power-rating-label", "Spesifikasi suplai GLD\nyang dikonfirmasi");
setText(6, "power-consumption", "3 UNIT GLD");
setText(6, "power-consumption-label", "Ruang lingkup pemasangan di Kilang Cilacap");
setText(6, "power-blocker-title", "VALIDASI: proteksi 16 V pada jalur 24 V");
setText(6, "power-blocker-body", "Komponen input bertanda 16 V harus disesuaikan atau divalidasi untuk jalur 24 V sebelum perakitan lapangan.");
setText(6, "power-assumption-title", "Fokus verifikasi daya");
setText(6, "power-assumptions", "• Cold-start dan inrush\n• Voltage drop kabel\n• Seluruh beban aktif\n• Temperatur enclosure");
setText(6, "power-1a-title", "Kriteria penerimaan");
setText(6, "power-1a", "Catu 24 VDC/2 A stabil pada start, operasi kontinu, transmisi radio, alarm, dan beban tambahan dalam skenario FAT.");
setFooter(6, "footer-left-6");
setNotes(6, [
  "[Sources]",
  "- Konfirmasi pengguna, 19 Agustus 2026: catu GLD 24 VDC/2 A dan ruang lingkup 3 unit.",
  "- Audit rangkaian dan desain PCB: komponen proteksi bertanda 16 V berada pada jalur input 24 V.",
]);

// Slide 7 — FAT.
setText(7, "section-7", "FAT GLD");
setText(7, "title-7", "FAT memverifikasi kinerja catu GLD 24 VDC/2 A");
setText(7, "fat-1-title", "1. IDENTIFIKASI");
setText(7, "fat-1-body", "• MPN dan lot delapan sensor MQ\n• Resistansi heater saat dingin\n• Fan, alarm, dan beban tambahan\n• Panjang serta ukuran kabel");
setText(7, "fat-2-title", "2. PENGUKURAN");
setText(7, "fat-2-body", "• Cold-start setelah OFF ≥30 menit\n• Profil arus hingga 120 menit\n• Log input 24 V dan rail internal\n• Capture peak dengan instrumen memadai");
setText(7, "fat-3-title", "3. STRESS & ACCEPT");
setText(7, "fat-3-body", "• Seluruh heater + radio + RS485 + LED\n• Alarm/fan terpisah dan bersamaan\n• Kabel terpanjang + enclosure tertutup\n• Tanpa current-limit atau reset");
setText(7, "fat-label-1", "INPUT TERVERIFIKASI");
setText(7, "fat-label-2", "WAVEFORM & THERMAL");
setText(7, "fat-label-3", "24 VDC/2 A TERVERIFIKASI");
setFooter(7, "footer-left-7");
setNotes(7, [
  "[Sources]",
  "- Konfirmasi pengguna, 19 Agustus 2026.",
  "- Audit rangkaian, desain PCB, dan rencana FAT internal.",
]);

// Slide 8 — CH.
setText(8, "section-8", "ENERGI CH");
setText(8, "title-8", "CH memakai 1 baterai 4000 mAh dan 2 panel 6 W");
setText(8, "ch-image-caption", "Konsep enclosure CH; ukuran mounting sementara ditulis ... cm.");
setText(8, "ch-source-title", "Konfigurasi yang ditetapkan");
setText(8, "ch-source-body", "• 1 baterai LiitoKala 4000 mAh\n• 2 panel surya, masing-masing 6 W\n• Radio STAR 920 MHz dan MESH 921 MHz\n• Charger dan jalur daya single-cell");
setText(8, "ch-gap-title", "Implementasi di area SRU");
setText(8, "ch-gap-body", "• Jumlah CH menyesuaikan cakupan\n• Penempatan mengikuti hasil survei\n• Rute antena disesuaikan dengan titik\n• Dimensi mounting: ... cm");
setText(8, "ch-note-title", "Verifikasi energi");
setText(8, "ch-note-body", "Pengisian, autonomy, temperatur, dan pola komunikasi diuji sebagai bagian dari verifikasi CH sebelum pemasangan.");
setFooter(8, "footer-left-8");
setNotes(8, [
  "[Sources]",
  "- Konfirmasi pengguna, 19 Agustus 2026: 1 baterai LiitoKala 4000 mAh dan 2 panel 6 W per CH.",
  "- Audit rangkaian, desain PCB, dan firmware CH.",
]);

// Slide 9 — Gateway and network discussion agenda.
setText(9, "section-9", "GATEWAY & JARINGAN");
setText(9, "title-9", "Bahan pembicaraan Gateway dan jaringan IT");
setText(9, "gw-intro", "Gateway, jaringan, dan server belum dibahas atau disepakati; bagian ini menjadi agenda pembicaraan awal dengan tim IT.");
setText(9, "gw-physical-title", "Penempatan & perangkat");
setText(9, "gw-physical-body", "• Lokasi Gateway\n• Pilihan koneksi site\n• Posisi dan rute antena\n• Catu daya serta grounding\n• Dukungan operasional");
setText(9, "gw-ticket-title", "Data untuk dibahas dengan IT");
setText(9, "gw-ticket-body", "1  MAC Wi-Fi unit\n2  Alamat broker/server\n3  Port komunikasi\n4  SSID, VLAN, DHCP, DNS, NTP\n5  Keamanan dan penanggung jawab");
setText(9, "gw-footnote", "Output pembicaraan: lokasi, metode koneksi, parameter jaringan, penanggung jawab, dan kriteria penerimaan.");
setFooter(9, "footer-left-9");
setNotes(9, [
  "[Sources]",
  "- Konfirmasi pengguna, 19 Agustus 2026: topik Gateway, jaringan, dan server belum dibahas atau disepakati.",
  "- Agenda teknis disusun dari arsitektur sistem dan kebutuhan onboarding IT.",
]);

// Slide 10 — security discussion agenda.
setText(10, "section-10", "KEAMANAN JARINGAN");
setText(10, "title-10", "\u00A0Agenda keamanan jaringan");
setText(10, "tls-intro", "Opsi berikut disiapkan untuk menentukan arah keamanan komunikasi bersama tim IT.");
setText(10, "tls-current-label", "KEPUTUSAN ARSITEKTUR");
setText(10, "tls-current-title", "Proteksi komunikasi");
setText(10, "tls-current-body", "• Protokol dan penggunaan TLS\n• Identitas setiap perangkat\n• Autentikasi dan autorisasi\n• Pengelolaan kredensial");
setText(10, "tls-required-label", "BUKTI PENERIMAAN");
setText(10, "tls-required-title", "Uji dan pencatatan");
setText(10, "tls-required-body", "• Topic ACL dan broker log\n• CONNACK serta pub/sub\n• Reconnect dan restart\n• Siklus hidup sertifikat");
setText(10, "tls-note-text", "Poin keputusan bersama IT: protokol, identitas, akses, logging, kredensial, dan pengujian penerimaan.");
setFooter(10, "footer-left-10");
setNotes(10, [
  "[Sources]",
  "- Konfirmasi pengguna, 19 Agustus 2026: keamanan jaringan menjadi bahan pembicaraan bersama tim IT.",
  "- Audit firmware dan arsitektur sistem sebagai dasar agenda teknis.",
]);

// Slide 11 — server discussion agenda.
setText(11, "section-11", "SERVER & DASHBOARD");
setText(11, "title-11", "Bahan pembicaraan server dan dashboard");
setText(11, "server-intro", "Pembahasan awal perlu menetapkan layanan, platform, keamanan, operasi, dan kriteria penerimaan.");
setText(11, "server-source-title", "KEBUTUHAN LAYANAN");
setText(11, "server-source-big", "Data & dashboard");
setText(11, "server-source-body", "• Broker komunikasi\n• Pengolahan data\n• Dashboard pengguna\n• Dataset dan log");
setText(11, "server-pilot-title", "PLATFORM & HOSTING");
setText(11, "server-pilot-big", "Keputusan bersama IT");
setText(11, "server-pilot-body", "Lokasi hosting, kapasitas, sistem operasi, runtime, akses pengguna, dan integrasi jaringan.");
setText(11, "server-prod-title", "OPERASI & KEAMANAN");
setText(11, "server-prod-big", "Runbook layanan");
setText(11, "server-prod-body", "• TLS dan ACL\n• Backup dan restore\n• Monitoring serta retention\n• HTTPS/RBAC dan owner operasi");
setText(11, "server-two-gaps", "Output pembicaraan: arsitektur, kapasitas, keamanan, operasi, owner, dan acceptance test yang disepakati.");
setFooter(11, "footer-left-11");
setNotes(11, [
  "[Sources]",
  "- Konfirmasi pengguna, 19 Agustus 2026: server dan dashboard menjadi bahan pembicaraan, bukan keputusan final.",
  "- Agenda teknis disusun dari kebutuhan sistem end-to-end.",
]);

// Slide 12 — location decision.
setText(12, "section-12", "LOKASI SRU");
setText(12, "title-12", "Lokasi pemasangan diarahkan ke area SRU");
setText(12, "safety-banner-label", "AREA SRU");
setText(12, "safety-banner-text", "Rencana awal pemasangan di area LPG telah dialihkan ke area SRU.");
setText(12, "safety-rule-title", "Ruang lingkup Cilacap");
setText(12, "safety-rules", "• Rencana awal: area LPG\n• Lokasi pemasangan: area SRU\n• Ruang lingkup: 3 unit GLD\n• Jumlah CH menyesuaikan cakupan");
setText(12, "safety-gates-title", "Koordinasi site & HSE");
setText(12, "safety-gates", "1  Penetapan titik pemasangan\n2  Klasifikasi area setiap titik\n3  Desain instalasi dan izin kerja\n4  Pemeriksaan serta persetujuan site");
setText(12, "safety-bottom-text", "Pemasangan mengikuti ketentuan site dan persyaratan HSE Pertamina.");
setFooter(12, "footer-left-12");
setNotes(12, [
  "[Sources]",
  "- Konfirmasi pengguna, 19 Agustus 2026: lokasi berubah dari area LPG ke area SRU.",
  "- Rekaman dan catatan meeting.",
]);

// Slide 13 — mounting.
setText(13, "section-13", "MOUNTING & SITE");
setText(13, "title-13", "Mounting untuk area SRU");
setText(13, "mounting-intro", "Dimensi sementara ditulis ... cm; drawing fabrikasi mengikuti pengukuran titik pemasangan.");
setText(13, "mounting-survey-title", "Data fabrikasi yang dicatat");
setText(13, "mounting-survey-body", "• OD, material, tebal, dan beban struktur\n• Angin, getaran, korosi, dan anchor\n• Sumber daya, rute kabel, gland, voltage drop\n• Tinggi antena, LOS, coax, grounding\n• Akses kerja dan ruang pemeliharaan");
setText(13, "mounting-proposal-text", "DIMENSI MOUNTING: ... cm");
setText(13, "mounting-caption", "Referensi survei untuk persiapan pemasangan di area SRU.");
setFooter(13, "footer-left-13");
setNotes(13, [
  "[Sources]",
  "- Konfirmasi pengguna, 19 Agustus 2026: dimensi sementara ditulis ... cm.",
  "- Rekaman dan catatan meeting serta referensi survei lapangan.",
]);

// Slide 14 — roadmap.
setText(14, "section-14", "ROADMAP");
setText(14, "title-14", "Roadmap menuju target September 2027");
setText(14, "roadmap-1-title", "AGUSTUS 2026");
setText(14, "roadmap-1-body", "• 10 Agustus: acuan “3 minggu lagi”\n• Rencana kunjungan sekitar akhir Agustus\n• Catu GLD ditetapkan 24 VDC/2 A\n• Konfigurasi energi CH ditetapkan");
setText(14, "roadmap-2-title", "SEPTEMBER 2026");
setText(14, "roadmap-2-body", "• Survei area SRU\n• Pengukuran mounting ... cm\n• Support, kabel, drawing, dan BOM\n• Bahan pembicaraan bersama IT");
setText(14, "roadmap-3-title", "OKT 2026 → SEP 2027");
setText(14, "roadmap-3-body", "• Penyelesaian desain dan FAT\n• Proses sertifikasi\n• Fabrikasi dan pemasangan\n• SAT, pelatihan, serah terima\n• Target penerimaan fase awal");
setText(14, "roadmap-label-1", "BASELINE & KUNJUNGAN");
setText(14, "roadmap-label-2", "SITE & SUPPORT PACK");
setText(14, "roadmap-label-3", "IMPLEMENTASI → TERIMA");
setFooter(14, "footer-left-14");
setNotes(14, [
  "[Sources]",
  "- Konfirmasi pengguna, 19 Agustus 2026.",
  "- Rekaman dan catatan meeting.",
]);

// Slide 15 — organizational ownership.
setText(15, "section-15", "TANGGUNG JAWAB");
setText(15, "title-15", "Tanggung jawab ditetapkan per organisasi");
setText(15, "ownership-intro", "Pembagian tanggung jawab menjadi dasar koordinasi dan action list implementasi.");
setText(15, "owner-lgu-title", "LGU");
setText(15, "owner-lgu-body", "R / A untuk:\n• GLD, CH, datasheet, dan BOM\n• Spesifikasi teknis dan desain support\n• FAT serta bukti teknis\n• Bahan pembicaraan Gateway/server\n• Dukungan SAT");
setText(15, "owner-pertamina-title", "PERTAMINA CILACAP");
setText(15, "owner-pertamina-body", "A / C untuk:\n• Titik pemasangan area SRU\n• Basis HSE, izin, dan utilitas\n• Kabel, struktur, dan kontraktor\n• Persetujuan instalasi\n• Penerimaan dan sign-off");
setText(15, "owner-vendor-title", "IT & VENDOR");
setText(15, "owner-vendor-body", "R / C untuk:\n• IT: jaringan, server, dan keamanan\n• IT: parameter serta acceptance\n• Vendor: dukungan kunjungan\n• Vendor: data sertifikasi\n• Dukungan pengujian/inspeksi");
setText(15, "ownership-key", "R = Responsible • A = Accountable • C = Consulted");
setFooter(15, "footer-left-15");
setNotes(15, [
  "[Sources]",
  "- Konfirmasi pengguna, 19 Agustus 2026: pembagian tanggung jawab organisasi tersedia.",
  "- Rekaman dan catatan meeting.",
]);

// Slide 16 — close.
setText(16, "section-16", "AKSI LANJUT");
setText(16, "title-16", "Baseline dan tindak lanjut");
setText(16, "decision-intro", "Fakta yang dikonfirmasi menjadi baseline; topik IT disiapkan sebagai agenda pembicaraan.");
setText(16, "decision-1", "Gunakan catu GLD 24 VDC/2 A.");
setText(16, "decision-2", "Siapkan 3 unit GLD untuk area SRU.");
setText(16, "decision-3", "Jumlah CH mengikuti cakupan; tiap CH memakai 1 baterai 4000 mAh dan 2 panel 6 W.");
setText(16, "decision-4", "Catat “3 minggu dari 10 Agustus” sebagai rencana kunjungan.");
setText(16, "decision-5", "Gunakan ... cm untuk dimensi mounting sementara.");
setText(16, "decision-6", "Siapkan pembicaraan Gateway, jaringan, keamanan, dan server bersama IT.");
setText(16, "decision-output-title", "OUTPUT");
setText(16, "decision-output-body", "Baseline teknis • agenda kunjungan • input survei SRU • bahan pembicaraan IT • tanggung jawab organisasi");
setText(16, "decision-output-note", "Tindak lanjut dicatat sebagai action list dengan owner organisasi, jadwal, dan bukti penyelesaian.");
setFooter(16, "footer-left-16");
setNotes(16, [
  "[Sources]",
  "- Konfirmasi pengguna, 19 Agustus 2026.",
  "- Rekaman dan catatan meeting.",
  "- Audit rangkaian, desain PCB, dan firmware.",
]);

for (let index = 0; index < presentation.slides.items.length; index += 1) {
  const slide = presentation.slides.items[index];
  const stem = `slide-${String(index + 1).padStart(2, "0")}`;
  const png = await presentation.export({ slide, format: "png", scale: 1 });
  await saveBlob(png, path.join(previewDir, `${stem}.png`));
  const layout = await presentation.export({ slide, format: "layout" });
  await saveBlob(layout, path.join(layoutDir, `${stem}.layout.json`));
}

const montage = await presentation.export({ format: "webp", montage: true, scale: 1 });
await saveBlob(montage, montagePath);

const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(finalPptxPath);

const finalInspect = await presentation.inspect({
  kind: "slide,textbox,shape,image,table,chart,notes",
  maxChars: 250000,
});
await fs.writeFile(
  "D:/Github/PertaminaGLD/tmp/presentation-confirmed-revision/final-inspect.ndjson",
  finalInspect.ndjson || "",
  "utf8",
);
