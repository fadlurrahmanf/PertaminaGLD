import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const sourcePath = "D:/Github/PertaminaGLD/docs/wiring/GLDCH.pptx";
const workspaceDir = "D:/Github/PertaminaGLD";
const skillDir = "C:/Users/MSI/.codex/plugins/cache/openai-primary-runtime/presentations/26.909.12148/skills/presentations";
const buildDir = path.join(workspaceDir, ".codex-ppt-build");
const outputDir = path.join(workspaceDir, "output", "presentations");
const candidatePath = path.join(buildDir, "GLDCH-sensor-flow-r16-candidate.pptx");
const finalPath = path.join(outputDir, "GLDCH-sensor-flow-r16.pptx");

const navy = "#16324A", blue = "#2E75B6", teal = "#0F766E", orange = "#B86518", pale = "#F5F9FC", line = "#B7C8D8";
const deck = await PresentationFile.importPptx(await FileBlob.load(sourcePath));
const sourceSlides = {
  v1: deck.slides.getItem(1), sensorImage: deck.slides.getItem(3), v2: deck.slides.getItem(4), v3: deck.slides.getItem(5),
  v4: deck.slides.getItem(6), v5: deck.slides.getItem(7), chV1: deck.slides.getItem(9), chV2: deck.slides.getItem(10), chV3: deck.slides.getItem(11),
};
deck.resolve("sh/kzmdova1").text.replace("V4", "V4 / ATEX");

function blankAfter(after) {
  const slide = deck.slides.insert({ after, layout: "Blank" }).slide;
  slide.shapes.add({ geometry: "rect", position: { left: 0, top: 0, width: 1280, height: 720 }, fill: "#FFFFFF", line: { fill: "none", width: 0 } });
  return slide;
}
function text(slide, value, position, style = {}) {
  const shape = slide.shapes.add({ geometry: "textbox", position, fill: "none", line: { fill: "none", width: 0 } });
  shape.text = value;
  shape.text.style = { typeface: "Aptos", fontSize: 16, color: navy, autoFit: "shrinkText", ...style };
  return shape;
}
function title(slide, value, sub = "") {
  text(slide, value, { left: 70, top: 34, width: 1140, height: 45 }, { fontSize: 30, bold: true });
  if (sub) text(slide, sub, { left: 70, top: 79, width: 1140, height: 28 }, { fontSize: 14, color: "#52708A" });
}
function card(slide, position, heading, body, accent = teal) {
  slide.shapes.add({ geometry: "roundRect", position, fill: pale, line: { fill: line, width: 1 } });
  slide.shapes.add({ geometry: "rect", position: { left: position.left, top: position.top, width: 7, height: position.height }, fill: accent, line: { fill: accent, width: 0 } });
  text(slide, heading, { left: position.left + 18, top: position.top + 13, width: position.width - 32, height: 28 }, { fontSize: 18, bold: true });
  text(slide, body, { left: position.left + 18, top: position.top + 47, width: position.width - 32, height: position.height - 58 }, { fontSize: 14, color: "#35526A" });
}
function arrow(slide, left, top, width, label, color = blue) {
  const a = slide.shapes.add({ geometry: "rightArrow", position: { left, top, width, height: 34 }, fill: color, line: { fill: color, width: 0 } });
  a.text = label; a.text.style = { typeface: "Aptos", fontSize: 12, bold: true, color: "#FFFFFF", autoFit: "shrinkText" };
}
function addNote(slide, position, value) {
  slide.shapes.add({ geometry: "roundRect", position, fill: "#F7FAFC", line: { fill: line, width: 1 } });
  text(slide, value, { left: position.left + 14, top: position.top + 8, width: position.width - 28, height: position.height - 16 }, { fontSize: 14, color: navy });
}
function styleTable(table, rows, cols, bodySize = 13) {
  table.styleOptions = { headerRow: true, bandedRows: true, firstColumn: true };
  table.borders.assign({ style: "solid", fill: line, width: 1 });
  for (let c = 0; c < cols; c += 1) { table.getCell(0, c).fill = navy; table.getCell(0, c).text.style = { typeface: "Aptos", fontSize: 14, bold: true, color: "#FFFFFF" }; }
  for (let r = 1; r < rows; r += 1) for (let c = 0; c < cols; c += 1) table.getCell(r, c).text.style = { typeface: "Aptos", fontSize: bodySize, color: navy };
}

function versionTable(slide, position, values, bodySize = 11) {
  slide.shapes.add({ geometry: "rect", position: { left: position.left, top: position.top, width: position.width, height: position.height }, fill: "#FFFFFF", line: { fill: "none", width: 0 } });
  const table = slide.tables.add({ rows: values.length, columns: values[0].length, ...position, values });
  styleTable(table, values.length, values[0].length, bodySize);
  return table;
}

versionTable(sourceSlides.v1, { left: 35, top: 410, width: 1210, height: 175, columnWidths: [170, 1040] }, [
  ["Aspek", "V1 — baseline"],
  ["Letak sensor", "8 footprint/sirkuit sensor menyatu pada motherboard (gambar PCB); MCP4725 terdapat di source V1."],
  ["Analog / driver", "INA333 + OPA333 + LM321 + ULN2003."],
  ["PCF / SHT40", "PCF8574 dan SHT40 tidak ditemukan pada motherboard V1."],
  ["Power / proteksi", "TPS2116, TPS22964, TPS3839, dan TPS61175 tidak ditemukan pada motherboard V1."],
  ["+5VA", "Tersedia pada source V1 untuk blok analog."],
  ["WDT", "TPL5010 ada pada motherboard V1."],
], 10);
versionTable(sourceSlides.v2, { left: 35, top: 420, width: 1210, height: 180, columnWidths: [155, 340, 700] }, [
  ["Aspek", "V1", "V2 / GLD2"],
  ["Letak sensor", "Menyatu pada motherboard", "Terpisah sebagai sensor module eksternal melalui H2/H1/H3–H8."],
  ["Analog / driver", "INA333 + OPA333 + LM321 + ULN2003", "OPA320; blok analog/driver lama tidak ada; ADS1256 tetap membaca AIN0–AIN7."],
  ["PCF / SHT40", "Keduanya tidak ada", "PCF8574 P0–P7 → EN0–EN7; SHT40 pada root I2C 0x44."],
  ["Power / proteksi", "TPS2116/TPS22964/TPS3839/TPS61175 tidak ada", "Ditambah TPS2116 power mux, TPS22964 load switch, TPS3839 supervisor, TPS61175 boost."],
  ["+5VA / nulling", "+5VA ada; MCP di board", "+5VA tetap ada; MCP4725 berada per module dan dipilih via TCA 0x71."],
  ["WDT", "TPL5010 ada", "TPL5010 tetap ada."],
], 10);
versionTable(sourceSlides.v3, { left: 35, top: 420, width: 1210, height: 165, columnWidths: [155, 340, 700] }, [
  ["Aspek", "V2 / GLD2", "V3"],
  ["Letak sensor", "Module eksternal via H2/H1/H3–H8", "Tetap module eksternal."],
  ["Analog / OPA", "OPA320 + ADS1256", "Tetap OPA320 + ADS1256."],
  ["PCF / SHT40", "PCF8574 + SHT40", "Tetap PCF8574 + SHT40."],
  ["Power / proteksi", "TPS2116 + TPS22964 + TPS3839 + TPS61175", "Tetap sama."],
  ["+5VA / I2C", "+5VA, TCA9548A, MCP per module", "Blok acquisition utama sama pada source; tidak ada IC baru yang ditemukan."],
  ["WDT", "TPL5010 ada", "TPL5010 tetap ada."],
], 10);
versionTable(sourceSlides.v4, { left: 25, top: 315, width: 855, height: 300, columnWidths: [145, 250, 445] }, [
  ["Aspek", "V3", "V4 / ATEX"],
  ["Letak sensor", "Module eksternal", "Tetap module eksternal."],
  ["Analog / OPA", "OPA320 + ADS1256", "Tetap OPA320 + ADS1256."],
  ["PCF / SHT40", "PCF8574 + SHT40", "Tetap PCF8574 + SHT40."],
  ["Power / proteksi", "TPS2116 + TPS22964 + TPS3839 + TPS61175", "Tetap sama."],
  ["+5VA / nulling", "+5VA; TCA/MCP per module", "Tetap basis acquisition yang sama."],
  ["WDT", "TPL5010 ada", "TPL5010 tetap ada."],
  ["Perubahan terverifikasi", "—", "Profile firmware menambah jalur kontrol fan GPIO7; bukan bukti sertifikasi ATEX."],
], 10);
versionTable(sourceSlides.v5, { left: 805, top: 185, width: 455, height: 430, columnWidths: [150, 290] }, [
  ["Aspek", "V5 adapter vs V4"],
  ["Sensor / +5VA", "Tidak ada slot/modul sensor atau +5VA pada PCB adapter."],
  ["Analog / OPA", "INA333, OPA333, LM321, OPA320, ADS1256, dan MCP4725 tidak ada."],
  ["PCF / SHT40", "PCF8574, TCA9548A, dan SHT40 tidak ada."],
  ["Power / proteksi", "TPS2116, TPS22964, TPS3839, dan TPS61175 tetap ada pada adapter."],
  ["WDT", "TPL5010 tetap ada pada adapter."],
  ["Arti sistem", "Bukan bukti sensor dihapus; V5 adalah board interface (E22, USB-UART, RS-485, OLED)."],
], 10);

versionTable(sourceSlides.chV1, { left: 390, top: 130, width: 835, height: 330, columnWidths: [190, 630] }, [
  ["Aspek", "CH V1 — baseline visual"],
  ["Bentuk / daya", "PCB memanjang dengan holder baterai; dua konektor SMA terlihat pada gambar."],
  ["Hubungan GLD", "Menerima data GLD lewat radio; bukan board ADC atau sensor module."],
  ["Radio / interface", "Dua konektor SMA terlihat, tetapi nomor radio dan detail interface tidak dapat dipastikan tanpa PCB JSON/BOM yang cocok."],
  ["WDT", "Tidak ada WDT pada CH V1."],
  ["IC / fungsi", "Tidak ada source PCB/BOM yang dipetakan eksplisit ke CH V1."],
], 11);
versionTable(sourceSlides.chV2, { left: 45, top: 395, width: 1190, height: 220, columnWidths: [175, 360, 640] }, [
  ["Aspek", "CH V1", "CH V2"],
  ["Bentuk", "Papan memanjang + holder baterai", "PCB bundar/kompak pada gambar."],
  ["Hubungan GLD", "Terima/relay data radio dari GLD", "Peran tetap setelah GLD/E22; bukan jalur analog sensor."],
  ["WDT", "Tidak ada", "Ada WDT; nomor part belum dipetakan ke BOM source yang cocok."],
  ["IC / interface", "Tidak ada BOM source cocok", "Tidak boleh mengklaim perubahan IC hanya dari gambar 3D."],
  ["Bukti yang diperlukan", "—", "PCB JSON atau BOM yang menyebut CH V2 secara eksplisit."],
], 11);
versionTable(sourceSlides.chV3, { left: 400, top: 105, width: 825, height: 365, columnWidths: [190, 270, 350] }, [
  ["Aspek", "CH V2", "CH V3"],
  ["Bentuk", "PCB bundar/kompak", "Kembali ke papan memanjang dengan holder baterai pada gambar."],
  ["Hubungan GLD", "Terima/relay data LoRa", "Tetap bukan ADC atau pengendali sensor module."],
  ["WDT", "Ada WDT", "Ada WDT."],
  ["IC / interface", "Tidak ada BOM source cocok", "Tidak ada BOM source cocok; perubahan IC belum dapat diverifikasi."],
  ["Bukti yang diperlukan", "—", "PCB JSON/BOM CH V3 untuk menetapkan perubahan teknis secara pasti."],
], 11);

const moduleFlow = blankAfter(sourceSlides.sensorImage);
title(moduleFlow, "Sensor Module dalam Rantai GLD2", "Delapan modul adalah sumber data; motherboard menyalakan, memilih, men-null, lalu mengubah sinyal menjadi data digital.");
card(moduleFlow, { left: 70, top: 145, width: 230, height: 165 }, "1. Elemen MQ", "MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2. Heater dan elemen sensor berada pada modul.", orange);
arrow(moduleFlow, 315, 209, 90, "analog");
card(moduleFlow, { left: 420, top: 145, width: 240, height: 165 }, "2. Slot sensor", "+5V, GND, VMID, AIN, SDA/SCL cabang, dan EN tersedia pada header modul.");
arrow(moduleFlow, 675, 209, 90, "AIN0–7");
card(moduleFlow, { left: 780, top: 145, width: 430, height: 165 }, "3. Akuisisi GLD", "Filter analog → ADS1256. ESP32-S3 membaca delapan kanal dan membentuk data/telemetri.", blue);
card(moduleFlow, { left: 150, top: 390, width: 310, height: 170 }, "Daya per modul", "PCF8574 (0x20) mengeluarkan EN0–EN7. EN mengendalikan TPS22919; rail sensor dapat dipilih ON/OFF.", orange);
arrow(moduleFlow, 480, 455, 105, "pilih", teal);
card(moduleFlow, { left: 605, top: 390, width: 310, height: 170 }, "I2C per cabang", "TCA9548A (0x71) memilih SDA/SCL cabang. MCP4725 setiap cabang beralamat sama: 0x60.", teal);
arrow(moduleFlow, 935, 455, 105, "nulling", teal);
card(moduleFlow, { left: 1060, top: 390, width: 150, height: 170 }, "Offset", "MCP4725 memberi tegangan DAC saat prosedur nulling.", blue);
text(moduleFlow, "Bukti: source-GLD2.zip, BoardPinsGLD2.h, dan temuan live COM3 2026-08-19. Ini menjelaskan arsitektur GLD2; bukan klaim hasil gas/field test saat ini.", { left: 70, top: 635, width: 1140, height: 32 }, { fontSize: 12, color: "#52708A" });
moduleFlow.speakerNotes.textFrame.setText("Sources: docs/wiring/gld-project-ver2-2026-07-01/GLD2-nulling-live-findings-2026-08-19.md; firmware/gld/include/BoardPinsGLD2.h; output/diagrams/gld2/component-pins.csv.");

const mapping = blankAfter(sourceSlides.v2);
title(mapping, "Pemetaan 8 Sensor Module GLD2", "Pemetaan ini harus dipakai saat akses MCP4725/nulling karena urutan EN tidak sama dengan urutan sensor fisik.");
const mapValues = [["Header", "Sensor", "PCF / EN", "TCA", "ADS1256"], ["H2", "MQ8", "P0 / EN0", "7", "AIN0"], ["H1", "MQ135", "P6 / EN6", "6", "AIN1"], ["H3", "MQ3", "P7 / EN7", "5", "AIN2"], ["H4", "MQ5", "P3 / EN3", "4", "AIN3"], ["H5", "MQ4", "P4 / EN4", "3", "AIN4"], ["H6", "MQ7", "P5 / EN5", "2", "AIN5"], ["H7", "MQ6", "P2 / EN2", "1", "AIN6"], ["H8", "MQ2", "P1 / EN1", "0", "AIN7"]];
const mapTable = mapping.tables.add({ rows: mapValues.length, columns: 5, left: 160, top: 135, width: 960, height: 420, columnWidths: [140, 220, 220, 160, 220], values: mapValues });
styleTable(mapTable, mapValues.length, 5, 14);
addNote(mapping, { left: 100, top: 590, width: 1080, height: 70 }, "Urutan akses yang terbukti pada GLD2: matikan switch lain → aktifkan EN target → pilih TCA pasangannya → akses MCP 0x60. Root I2C: PCF8574 0x20, SHT40 0x44, TCA9548A 0x71.");
mapping.speakerNotes.textFrame.setText("Sources: docs/wiring/gld-project-ver2-2026-07-01/GLD2-nulling-live-findings-2026-08-19.md; docs/wiring/gld-project-ver2-2026-07-01/GLD2-functional-test-plan-draft.md; firmware/gld/include/BoardPinsGLD2.h.");

const gldComparison = blankAfter(sourceSlides.v5);
title(gldComparison, "Perbandingan GLD V1–V5: Posisi Sensor Module", "Versi visual dibandingkan dari artefak PCB yang tersedia. Detail mapping header yang lengkap hanya terverifikasi untuk GLD2.");
const gldValues = [["Versi", "Akuisisi / sensor", "Perubahan board", "Batas bukti"], ["V1", "ADS1256, TCA9548A, MCP4725; INA333 + OPA333 + LM321; +5VA; TPL5010", "Sensor menyatu pada motherboard", "Tidak ada mapping header lengkap yang dipasangkan ke slide V1"], ["V2 / GLD2", "8 slot eksternal: PCF8574/TPS22919, TCA, MCP4725, ADS1256; OPA320; SHT40; +5VA; TPL5010", "Pemetaan H2/H1/H3–H8 terverifikasi", "Bukti wiring dan hasil nulling 8/8 pada COM3 historis"], ["V3", "BOM sama dengan V2: OPA320, PCF8574, SHT40, ADS/TCA, +5VA, TPL5010", "Tidak ada penggantian IC yang ditemukan", "Tidak menyamakan layout fisik tanpa source per-version"], ["V4 / ATEX", "BOM sama dengan V3 termasuk OPA320, PCF8574, SHT40, +5VA, TPL5010", "Fan GPIO7 pada profile firmware", "Bukan bukti sertifikasi ATEX"], ["V5", "Adapter tanpa ADS/TCA/PCF/SHT40/OPA/+5VA; tetap TPL5010", "Adapter: E22/USB-UART/RS-485/OLED", "Tidak boleh disimpulkan bahwa sensor module hilang dari sistem lengkap"]];
const gldTable = gldComparison.tables.add({ rows: gldValues.length, columns: 4, left: 55, top: 120, width: 1170, height: 510, columnWidths: [140, 370, 320, 340], values: gldValues });
styleTable(gldTable, gldValues.length, 4, 13);
gldComparison.speakerNotes.textFrame.setText("Sources: docs/wiring/gld-project-ver2-2026-07-01/source-GLD_Project.zip; source-GLD2.zip; docs/wiring/Board_GLD3.zip; docs/wiring/GLD ATEX.zip; docs/wiring/GLD5.zip; firmware/gld/include/BoardPinsGLD2.h; firmware/gld/include/BoardPinsGLDATEX.h.");

const systemFlow = blankAfter(sourceSlides.chV3);
title(systemFlow, "Dari Sensor Module ke CH", "CH tidak membaca AIN/ADC sensor secara langsung; perannya adalah menerima dan meneruskan data GLD melalui radio E22.");
card(systemFlow, { left: 55, top: 160, width: 230, height: 180 }, "Sensor module ×8", "Elemen MQ menghasilkan sinyal analog. EN, I2C cabang, dan AIN kembali ke motherboard GLD.", orange);
arrow(systemFlow, 300, 232, 90, "AIN");
card(systemFlow, { left: 405, top: 160, width: 250, height: 180 }, "GLD acquisition", "PCF/TPS22919: daya; TCA/MCP: pilih & nulling; ADS1256: konversi analog ke data; ESP32-S3: proses.", teal);
arrow(systemFlow, 670, 232, 90, "LoRa");
card(systemFlow, { left: 775, top: 160, width: 210, height: 180 }, "E22 pada GLD", "Radio membawa telemetri/data yang sudah dibentuk oleh GLD; bukan sinyal sensor analog.", blue);
arrow(systemFlow, 1000, 232, 90, "LoRa");
card(systemFlow, { left: 1100, top: 160, width: 130, height: 180 }, "CH", "Dual E22: terima/relay data.", teal);
card(systemFlow, { left: 170, top: 445, width: 940, height: 125 }, "Bukti CH yang tersedia", "Source dualRadioCH_E220Ver4 membuktikan ESP32-S3, dua E22, BQ25185, TPS63020, TLV70233, TPL5010 dan CH340. Mapping radio/profile firmware ada, tetapi source tidak dipasangkan tegas ke gambar CH V1–V3 di deck.", blue);
text(systemFlow, "Batas klaim: alur hardware/board source; tidak menyatakan keberhasilan komunikasi RF, relay CH, gateway, atau server di lapangan.", { left: 100, top: 625, width: 1080, height: 28 }, { fontSize: 12, color: "#52708A" });
systemFlow.speakerNotes.textFrame.setText("Sources: docs/wiring/gld-project-ver2-2026-07-01/GLD2-nulling-live-findings-2026-08-19.md; docs/wiring/ch-dual-radio-e220-ver4-2026-07-21/README.md; docs/wiring/ch-dual-radio-e220-ver4-2026-07-21/1-PCB_PCB_dualRadioCH_E220Ver4.json.");

const chComparison = deck.slides.add({ width: 1280, height: 720 });
chComparison.shapes.add({ geometry: "rect", position: { left: 0, top: 0, width: 1280, height: 720 }, fill: "#FFFFFF", line: { fill: "none", width: 0 } });
title(chComparison, "Perbandingan CH V1–V3", "Peran CH terhadap sensor: menerima paket LoRa dari GLD; tidak berfungsi sebagai ADC/board sensor module.");
const chValues = [["Versi", "Bukti di deck/repo", "Hubungan ke sensor module", "Status teknis"], ["CH V1", "Gambar 3D tersedia; tidak ada PCB JSON/BOM yang cocok", "Menerima data GLD via radio (fungsi per-IC belum dapat dipetakan)", "Tidak ada WDT; perubahan IC lain belum terverifikasi"], ["CH V2", "Gambar 3D tersedia; tidak ada PCB JSON/BOM yang cocok", "Tetap berada setelah GLD/E22 dalam rantai data", "Ada WDT; IC lain belum terverifikasi"], ["CH V3", "Gambar 3D tersedia; tidak ada PCB JSON/BOM yang cocok", "Tetap bukan jalur analog atau pengendali sensor", "Ada WDT; IC lain belum terverifikasi"], ["Source CH E220 Ver4", "ESP32-S3, 2×E22, BQ25185, TPS63020, TLV70233, TPL5010, CH340", "Menerima/relay paket LoRa yang dikirim GLD", "TPL5010 referensi WDT source; bukan pemetaan pasti ke V1–V3"]];
const chTable = chComparison.tables.add({ rows: chValues.length, columns: 4, left: 55, top: 125, width: 1170, height: 480, columnWidths: [165, 390, 345, 270], values: chValues });
styleTable(chTable, chValues.length, 4, 13);
addNote(chComparison, { left: 90, top: 630, width: 1100, height: 46 }, "Agar perbandingan CH V1–V3 menjadi pasti, diperlukan source EasyEDA/PCB JSON atau BOM yang secara eksplisit menyebut masing-masing versi tersebut.");
chComparison.speakerNotes.textFrame.setText("Sources: docs/wiring/ch-dual-radio-e220-ver4-2026-07-21/README.md; docs/wiring/ch-dual-radio-e220-ver4-2026-07-21/1-PCB_PCB_dualRadioCH_E220Ver4.json; docs/wiring/Source_CH_Board_Kecil/Source_CH_Board_Kecil.zip.");

await fs.mkdir(outputDir, { recursive: true });
await (await PresentationFile.exportPptx(deck)).save(candidatePath);
const { finalizePresentation } = await import(pathToFileURL(path.join(skillDir, "container_tools", "artifact_tool_utils.mjs")).href);
const tableSlides = [2, 6, 7, 8, 9, 10, 11, 13, 14, 15, 17];
const result = await finalizePresentation({ workspaceDir, candidatePath, finalPath, pythonExecutable: "C:/Users/MSI/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe", integrityValidatorPath: path.join(skillDir, "container_tools", "inspect_presentation_package_integrity.py"), layoutValidatorPath: path.join(skillDir, "container_tools", "inspect_presentation_layout_geometry.py"), layoutArgs: ["--expected-slide-size-emu", "12192000,6858000", "--validate-bullet-geometry", "--validate-heading-fit", ...tableSlides.flatMap(number => ["--require-native-table-slide", String(number)])], explicitTotalSlideCount: 17, requiredNativeTableOwnerSlides: tableSlides, receiptPath: path.join(buildDir, "GLDCH-sensor-flow-r16.validation.json"), verifyArtifactToolImport: true });
console.log(JSON.stringify(result, null, 2));
