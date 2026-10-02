import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const workspaceDir = "D:/Github/PertaminaGLD";
const sourcePath = `${workspaceDir}/docs/wiring/GLDCH.pptx`;
const skillDir = "C:/Users/MSI/.codex/plugins/cache/openai-primary-runtime/presentations/26.909.12148/skills/presentations";
const buildDir = path.join(workspaceDir, ".codex-ppt-build");
const outputDir = path.join(workspaceDir, "output", "presentations");
const candidatePath = path.join(buildDir, "GLDCH-sensor-flow-r20-candidate.pptx");
const finalPath = path.join(outputDir, "GLDCH-sensor-flow-r20.pptx");
const navy = "#16324A", orange = "#B86518", teal = "#0F766E", muted = "#35526A", line = "#B7C8D8";

const deck = await PresentationFile.importPptx(await FileBlob.load(sourcePath));
const versions = [
  { after: deck.slides.getItem(1), title: "GLD V1", lead: "Kondisi awal", leadText: "Sensor, jalur analog, dan kontrol berada pada satu motherboard. PCF8574 dan SHT40 belum digunakan.", change: "Perubahan di V2", changeText: "V2 memisahkan sensor module, menggunakan OPA320, serta menambah PCF8574, SHT40, dan kontrol daya." },
  { after: deck.slides.getItem(4), title: "GLD V2", lead: "Perubahan dari V1", leadText: "V1 memakai INA333, OPA333, LM321, dan ULN2003 pada motherboard.", change: "Konfigurasi V2", changeText: "V2 memakai delapan sensor module eksternal. +5VA dan TPL5010 tetap tersedia." },
  { after: deck.slides.getItem(5), title: "GLD V3", lead: "Perubahan dari V2", leadText: "Source PCB tidak menunjukkan penggantian IC atau acquisition baru dibanding V2.", change: "Konfigurasi V3", changeText: "V3 mempertahankan OPA320, ADS1256, PCF8574, SHT40, TCA/MCP, +5VA, dan TPL5010." },
  { after: deck.slides.getItem(6), title: "GLD V4", lead: "Perubahan dari V3", leadText: "Source PCB tidak menunjukkan pembaruan acquisition dibanding V3.", change: "Konfigurasi V4", changeText: "V4 mempertahankan sensor module eksternal, OPA320, ADS1256, PCF8574, SHT40, +5VA, dan TPL5010." },
  { after: deck.slides.getItem(7), title: "GLD V5", lead: "Cakupan adapter", leadText: "Board adapter tidak memuat ADS1256, TCA, PCF8574, SHT40, OPA, MCP4725, atau +5VA.", change: "Fungsi adapter", changeText: "V5 memusatkan interface E22, USB-UART, RS-485, dan OLED. TPS2116, TPS22964, TPS3839, TPS61175, serta TPL5010 tetap ada." },
  { after: deck.slides.getItem(9), title: "CH V1", lead: "Kondisi awal", leadText: "CH V1 tidak memiliki WDT. Detail IC belum dapat dipastikan tanpa PCB JSON atau BOM yang cocok.", change: "Perubahan di V2", changeText: "CH V2 menambahkan WDT dan tetap menerima atau meneruskan data radio dari GLD." },
  { after: deck.slides.getItem(10), title: "CH V2", lead: "Perubahan dari V1", leadText: "CH V2 menggunakan PCB bundar/kompak dan menambahkan WDT.", change: "Batas bukti", changeText: "Nomor IC serta perubahan selain WDT memerlukan PCB JSON atau BOM yang sesuai." },
  { after: deck.slides.getItem(11), title: "CH V3", lead: "Perubahan dari V2", leadText: "Penggantian IC dari CH V2 ke V3 belum dapat dibuktikan oleh source PCB atau BOM.", change: "Konfigurasi V3", changeText: "CH V3 tetap memiliki WDT dan kembali memakai papan memanjang dengan holder baterai." },
];

function text(slide, value, position, style = {}) {
  const shape = slide.shapes.add({ geometry: "textbox", position, fill: "none", line: { fill: "none", width: 0 } });
  shape.text = value;
  shape.text.style = { typeface: "Aptos", fontSize: 20, color: muted, autoFit: "shrinkText", ...style };
}

function addExplanation(item) {
  const slide = deck.slides.insert({ after: item.after, layout: "Blank" }).slide;
  slide.shapes.add({ geometry: "rect", position: { left: 0, top: 0, width: 1280, height: 720 }, fill: "#FFFFFF", line: { fill: "none", width: 0 } });
  text(slide, item.title, { left: 90, top: 75, width: 400, height: 58 }, { fontSize: 38, bold: true, color: navy });
  slide.shapes.add({ geometry: "rect", position: { left: 90, top: 167, width: 1100, height: 2 }, fill: line, line: { fill: line, width: 0 } });
  text(slide, item.lead, { left: 92, top: 255, width: 300, height: 32 }, { fontSize: 22, bold: true, color: orange });
  text(slide, item.leadText, { left: 92, top: 300, width: 1050, height: 72 }, { fontSize: 23, color: muted });
  text(slide, item.change, { left: 92, top: 440, width: 300, height: 32 }, { fontSize: 22, bold: true, color: teal });
  text(slide, item.changeText, { left: 92, top: 485, width: 1050, height: 92 }, { fontSize: 23, color: muted });
}

for (const version of versions) addExplanation(version);

await fs.mkdir(outputDir, { recursive: true });
await (await PresentationFile.exportPptx(deck)).save(candidatePath);
const { finalizePresentation } = await import(pathToFileURL(path.join(skillDir, "container_tools", "artifact_tool_utils.mjs")).href);
const result = await finalizePresentation({
  workspaceDir, candidatePath, finalPath,
  pythonExecutable: "C:/Users/MSI/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe",
  integrityValidatorPath: path.join(skillDir, "container_tools", "inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(skillDir, "container_tools", "inspect_presentation_layout_geometry.py"),
  layoutArgs: ["--expected-slide-size-emu", "12192000,6858000", "--validate-bullet-geometry", "--validate-heading-fit"],
  explicitTotalSlideCount: 20,
  requiredNativeTableOwnerSlides: [],
  receiptPath: path.join(buildDir, "GLDCH-sensor-flow-r20.validation.json"),
  verifyArtifactToolImport: true,
});
console.log(JSON.stringify(result, null, 2));
