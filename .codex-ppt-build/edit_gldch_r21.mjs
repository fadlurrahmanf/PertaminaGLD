import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const workspaceDir = "D:/Github/PertaminaGLD";
const sourcePath = `${workspaceDir}/docs/wiring/Presentations/GLDCH.pptx`;
const skillDir = "C:/Users/MSI/.codex/plugins/cache/openai-primary-runtime/presentations/26.909.12148/skills/presentations";
const buildDir = path.join(workspaceDir, ".codex-ppt-build");
const outputDir = path.join(workspaceDir, "output", "presentations");
const candidatePath = path.join(buildDir, "GLDCH-sensor-flow-r23-candidate.pptx");
const finalPath = path.join(outputDir, "GLDCH-sensor-flow-r23.pptx");

const navy = "#16324A";
const orange = "#B86518";
const teal = "#0F766E";
const muted = "#35526A";
const paleLine = "#B7C8D8";

const deck = await PresentationFile.importPptx(await FileBlob.load(sourcePath));

function resolve(id) {
  return deck.resolve(id);
}

function hideText(id) {
  resolve(id).text = "";
}

function move(id, left, top, width, height) {
  resolve(id).position = { left, top, width, height };
}

function addText(slide, value, position, style = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    position,
    fill: "none",
    line: { fill: "none", width: 0 },
  });
  shape.text = value;
  shape.text.style = {
    typeface: "Aptos",
    fontSize: 18,
    color: muted,
    autoFit: "shrinkText",
    ...style,
  };
  return shape;
}

function addNarrative(slide, title, lead, paragraphs, { bodyTop = 178, bodyHeight = 470, titleLeft = 700 } = {}) {
  addText(slide, title, { left: titleLeft, top: 52, width: 1220 - titleLeft, height: 46 }, { fontSize: 31, bold: true, color: navy });
  slide.shapes.add({
    geometry: "rect",
    position: { left: 700, top: 116, width: 500, height: 2 },
    fill: paleLine,
    line: { fill: paleLine, width: 0 },
  });
  addText(slide, lead, { left: 700, top: 138, width: 500, height: 30 }, { fontSize: 18, bold: true, color: orange });
  addText(
    slide,
    paragraphs.join("\n\n"),
    { left: 700, top: bodyTop, width: 500, height: bodyHeight },
    { fontSize: 17, color: muted },
  );
}

// GLD V1: retain both board views, reduce them into the left evidence area.
const v1 = deck.slides.getItem(1);
move("im/nix0be18", 22, 116, 320, 285.7);
move("im/jy5w3a14", 354, 116, 310.5, 285.7);
hideText("sh/r65knqtk");
addNarrative(v1, "GLD V1", "Baseline motherboard", [
  "ESP32, ADS1256, TCA9548, dan MCP4725 berada pada motherboard.",
  "Jalur analog memakai INA333, OPA333, dan LM321. Sensor serta bridge MQ masih berada pada board utama.",
  "TPL5010 mengatur wake-up/deep-sleep dan kontrol catu 5V/3.3V board, sementara baterai dipertahankan.",
  "ULN2003 mengendalikan buzzer, alarm 5V, dan DC fan.",
]);

// SensorBoardMQ: give the separate module its own short, source-backed explanation.
const mq = deck.slides.getItem(3);
move("im/z6lc7q1o", 28, 122, 305, 290);
move("im/fed47q18", 352, 122, 286, 290);
hideText("sh/3ihk3et8");
addNarrative(mq, "SensorBoardMQ", "Bagian dari perubahan V2", [
  "INA333, MCP4725, dan rangkaian bridge sensor MQ dipisahkan dari motherboard.",
  "TPS22919 pada module mengendalikan ON/OFF daya sensor MQ.",
  "Module terhubung ke motherboard melalui socket.",
], { bodyTop: 205, bodyHeight: 280 });

// GLD V2.
const v2 = deck.slides.getItem(4);
move("im/h8juxg7q", 22, 116, 320, 259);
move("im/apobah8v", 358, 116, 278, 263);
hideText("sh/l4bupwny");
addNarrative(v2, "GLD V2", "Perubahan dari V1", [
  "LM321 diganti OPA320 pada jalur analog. PCF8574 dan SHT40 juga ditambahkan.",
  "INA333, MCP4725, dan bridge MQ pindah ke SensorBoardMQ yang memakai TPS22919 untuk ON/OFF daya sensor.",
  "DC fan tidak ada. Pin Alarm menyediakan tegangan 24V.",
  "Pemilih 24V/Battery/5V terhubung langsung tanpa jumper. Pada revisi awal V2, +5VA belum tersambung.",
]);

// GLD V3.
const v3 = deck.slides.getItem(5);
move("im/mxg36h47", 22, 116, 320, 279);
move("im/lwn2dc3m", 358, 116, 295, 279);
hideText("sh/ml07i9sv");
addNarrative(v3, "GLD V3", "Perubahan dari V2", [
  "Socket DC_FAN 5V sudah tersedia kembali.",
  "+5VA sudah tersambung dan diperbaiki.",
  "Konfigurasi sensor module, OPA320, ADS1256, TCA9548, PCF8574, dan SHT40 tetap dipertahankan.",
], { bodyTop: 205, bodyHeight: 300, titleLeft: 770 });

// GLD V4: the right-lower picture is the cover PCB with green terminals.
const v4 = deck.slides.getItem(6);
move("im/4ralkf6t", 20, 92, 315, 270);
move("im/rul4vapk", 340, 92, 282, 270);
move("im/6tc3mpoz", 20, 382, 310, 270);
move("im/wz6dk3it", 340, 382, 282, 265);
hideText("sh/kzmdova1");
addNarrative(v4, "GLD V4", "Perubahan dari V3", [
  "Ditambahkan lubang baut untuk pemasangan motherboard ke cover PCB.",
  "Cover PCB terpisah ditambahkan untuk men-terminalkan koneksi dan menutupi motherboard.",
  "Gambar kanan bawah menunjukkan Cover PCB dengan terminal berwarna hijau.",
], { bodyTop: 205, bodyHeight: 300 });

// GLD V5: adapter board at left, separated sensor functions at Sensor PCB.
const v5 = deck.slides.getItem(7);
move("im/yp8rix47", 16, 85, 212, 196);
move("im/jqhsb2ls", 236, 85, 216, 195);
move("im/krqtkn2x", 16, 294, 199, 187);
move("im/lszads3i", 224, 294, 209, 187);
move("im/alored4v", 452, 85, 198, 181);
move("im/bmxs7ilg", 452, 286, 196, 185);
move("sh/zipwbmdc", 10, 78, 450, 205);
move("sh/kfixwbe1", 10, 288, 430, 198);
move("sh/lgbepgvm", 446, 76, 210, 400);
hideText("sh/tkby9kzm");
addNarrative(v5, "GLD V5", "Perubahan dari V4", [
  "MotherBoardAdapter mempertahankan ESP32 dan TPL5010. Konektor 16-pin PHD2.0 membawa antarmuka menuju Sensor PCB.",
  "ADS1256, TCA9548, OPA320, PCF8574, SHT40, dan +5VA tidak lagi berada pada motherboard.",
  "Fungsi-fungsi tersebut dipisahkan ke Sensor PCB.",
], { bodyTop: 190, bodyHeight: 330, titleLeft: 770 });

// CH V1: retain original vertical views and use the existing empty area.
const ch1 = deck.slides.getItem(9);
hideText("sh/l036l83y");
addNarrative(ch1, "CH V1", "Baseline CH", [
  "Papan memanjang dengan holder baterai dan konektor antena SMA.",
  "TPL5010 sudah ada pada baseline source CH V1.",
  "Archive tidak membuktikan perubahan fungsi TPL5010 sebagai penambahan khusus versi berikutnya.",
], { bodyTop: 210, bodyHeight: 300 });

// CH V2.
const ch2 = deck.slides.getItem(10);
move("im/1k3i9gz2", 18, 102, 320, 310);
move("im/2lcz2l0n", 345, 102, 331, 310);
hideText("sh/98rytw72");
addNarrative(ch2, "CH V2", "Perubahan dari V1", [
  "PCB berbentuk lingkaran agar sesuai dengan casing aluminium.",
  "Socket antena diganti menjadi pin untuk sambungan ke connector antena fiberglass.",
  "TPL5010 tetap ada pada source V2, seperti baseline V1.",
], { bodyTop: 210, bodyHeight: 300 });

// CH V3.
const ch3 = deck.slides.getItem(11);
hideText("sh/dcbm583y");
addNarrative(ch3, "CH V3", "Bentuk modifikasi V1", [
  "Kembali memakai papan memanjang dengan holder baterai.",
  "TPL5010 tetap tercantum pada source V3.",
  "Karena TPL5010 juga ada pada baseline V1, source archive tidak mendukung klaim bahwa IC ini baru ditambahkan pada V3.",
], { bodyTop: 210, bodyHeight: 310 });

await fs.mkdir(outputDir, { recursive: true });
await (await PresentationFile.exportPptx(deck)).save(candidatePath);

const { finalizePresentation } = await import(pathToFileURL(
  path.join(skillDir, "container_tools", "artifact_tool_utils.mjs"),
).href);
const result = await finalizePresentation({
  workspaceDir,
  candidatePath,
  finalPath,
  pythonExecutable: "C:/Users/MSI/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe",
  integrityValidatorPath: path.join(skillDir, "container_tools", "inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(skillDir, "container_tools", "inspect_presentation_layout_geometry.py"),
  layoutArgs: ["--expected-slide-size-emu", "12192000,6858000", "--validate-bullet-geometry", "--validate-heading-fit"],
  explicitTotalSlideCount: 12,
  requiredNativeTableOwnerSlides: [],
  fontPolicy: { basis: "design", families: ["Aptos", "Aptos Display"] },
  receiptPath: path.join(buildDir, "GLDCH-sensor-flow-r23.validation.json"),
  verifyArtifactToolImport: true,
});
console.log(JSON.stringify(result, null, 2));
