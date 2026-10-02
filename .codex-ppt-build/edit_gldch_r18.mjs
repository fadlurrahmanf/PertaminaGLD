import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const workspaceDir = "D:/Github/PertaminaGLD";
const sourcePath = `${workspaceDir}/docs/wiring/GLDCH.pptx`;
const skillDir = "C:/Users/MSI/.codex/plugins/cache/openai-primary-runtime/presentations/26.909.12148/skills/presentations";
const buildDir = path.join(workspaceDir, ".codex-ppt-build");
const outputDir = path.join(workspaceDir, "output", "presentations");
const candidatePath = path.join(buildDir, "GLDCH-sensor-flow-r18-candidate.pptx");
const finalPath = path.join(outputDir, "GLDCH-sensor-flow-r18.pptx");
const navy = "#16324A", orange = "#B86518", teal = "#0F766E", muted = "#35526A";

const deck = await PresentationFile.importPptx(await FileBlob.load(sourcePath));
const sourceSlides = {
  v1: deck.slides.getItem(1), v2: deck.slides.getItem(4), v3: deck.slides.getItem(5), v4: deck.slides.getItem(6), v5: deck.slides.getItem(7),
  chV1: deck.slides.getItem(9), chV2: deck.slides.getItem(10), chV3: deck.slides.getItem(11),
};

function text(slide, value, position, style = {}) {
  const shape = slide.shapes.add({ geometry: "textbox", position, fill: "none", line: { fill: "none", width: 0 } });
  shape.text = value;
  shape.text.style = { typeface: "Aptos", fontSize: 15, color: muted, autoFit: "shrinkText", ...style };
}

function note(slide, position, limitation, improvement, compact = false) {
  const left = position.left;
  const gap = compact ? 19 : 26;
  const headingWidth = compact ? 92 : 110;
  const labelSize = compact ? 12 : 15;
  const bodySize = compact ? 12 : 15;
  text(slide, "Kekurangan", { left, top: position.top, width: headingWidth, height: gap }, { fontSize: labelSize, bold: true, color: orange });
  text(slide, limitation, { left: left + headingWidth + 8, top: position.top, width: position.width - headingWidth - 8, height: gap }, { fontSize: bodySize, color: muted });
  text(slide, "Perbaikan", { left, top: position.top + gap, width: headingWidth, height: gap }, { fontSize: labelSize, bold: true, color: teal });
  text(slide, improvement, { left: left + headingWidth + 8, top: position.top + gap, width: position.width - headingWidth - 8, height: gap }, { fontSize: bodySize, color: muted });
}

// Plain text sits in original white space only. No rectangle/card is added over a board image.
note(sourceSlides.v1, { left: 62, top: 592, width: 1120 },
  "sensor dan analog masih menyatu di motherboard; PCF8574 dan SHT40 belum tersedia.",
  "V2 memisahkan sensor module dan menambah PCF8574, SHT40, OPA320, serta kontrol daya.");
note(sourceSlides.v2, { left: 54, top: 618, width: 1120 },
  "V1 memakai INA333, OPA333, LM321, dan ULN2003 pada motherboard.",
  "V2 memakai OPA320 dan 8 sensor module eksternal; +5VA serta TPL5010 tetap tersedia.", true);
note(sourceSlides.v3, { left: 56, top: 585, width: 1120 },
  "source PCB belum menunjukkan penggantian IC atau acquisition baru dibanding V2.",
  "V3 mempertahankan OPA320, ADS1256, PCF8574, SHT40, TCA/MCP, +5VA, dan TPL5010.");
note(sourceSlides.v4, { left: 42, top: 450, width: 740 },
  "source PCB belum menunjukkan pembaruan acquisition dibanding V3.",
  "V4 mempertahankan sensor module eksternal, OPA320, ADS1256, PCF8574, SHT40, +5VA, dan TPL5010.");

// V5 fills its canvas with board images; a separate text-only slide keeps that evidence fully visible.
const v5Note = deck.slides.insert({ after: sourceSlides.v5, layout: "Blank" }).slide;
v5Note.shapes.add({ geometry: "rect", position: { left: 0, top: 0, width: 1280, height: 720 }, fill: "#FFFFFF", line: { fill: "none", width: 0 } });
text(v5Note, "V5", { left: 85, top: 80, width: 300, height: 55 }, { fontSize: 38, bold: true, color: navy });
text(v5Note, "Board adapter", { left: 88, top: 138, width: 400, height: 32 }, { fontSize: 19, color: muted });
text(v5Note, "Kekurangan", { left: 88, top: 260, width: 180, height: 30 }, { fontSize: 22, bold: true, color: orange });
text(v5Note, "Adapter tidak memuat ADS1256, TCA, PCF8574, SHT40, OPA, MCP4725, atau +5VA.", { left: 88, top: 300, width: 1060, height: 42 }, { fontSize: 21, color: muted });
text(v5Note, "Perbaikan", { left: 88, top: 410, width: 180, height: 30 }, { fontSize: 22, bold: true, color: teal });
text(v5Note, "V5 memusatkan interface E22, USB-UART, RS-485, dan OLED. TPS2116, TPS22964, TPS3839, TPS61175, serta TPL5010 tetap ada.", { left: 88, top: 450, width: 1080, height: 64 }, { fontSize: 21, color: muted });

note(sourceSlides.chV1, { left: 410, top: 125, width: 780 },
  "CH V1 tidak memiliki WDT; detail IC belum dapat dipastikan tanpa PCB JSON/BOM yang cocok.",
  "CH V2 menambahkan WDT dan tetap menerima atau meneruskan data radio dari GLD.");
note(sourceSlides.chV2, { left: 50, top: 623, width: 1160 },
  "CH V1 tidak memiliki WDT dan memakai papan memanjang dengan holder baterai.",
  "CH V2 memiliki WDT dan memakai PCB bundar/kompak; nomor IC memerlukan BOM yang sesuai.", true);
note(sourceSlides.chV3, { left: 420, top: 120, width: 770 },
  "pergantian IC dari CH V2 ke V3 belum dapat dibuktikan oleh source PCB/BOM.",
  "CH V3 tetap memiliki WDT dan kembali memakai papan memanjang dengan holder baterai.");

await fs.mkdir(outputDir, { recursive: true });
await (await PresentationFile.exportPptx(deck)).save(candidatePath);
const { finalizePresentation } = await import(pathToFileURL(path.join(skillDir, "container_tools", "artifact_tool_utils.mjs")).href);
const result = await finalizePresentation({
  workspaceDir, candidatePath, finalPath,
  pythonExecutable: "C:/Users/MSI/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe",
  integrityValidatorPath: path.join(skillDir, "container_tools", "inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(skillDir, "container_tools", "inspect_presentation_layout_geometry.py"),
  layoutArgs: ["--expected-slide-size-emu", "12192000,6858000", "--validate-bullet-geometry", "--validate-heading-fit"],
  explicitTotalSlideCount: 13,
  requiredNativeTableOwnerSlides: [],
  receiptPath: path.join(buildDir, "GLDCH-sensor-flow-r18.validation.json"),
  verifyArtifactToolImport: true,
});
console.log(JSON.stringify(result, null, 2));
