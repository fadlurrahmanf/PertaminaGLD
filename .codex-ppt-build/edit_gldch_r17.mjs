import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const workspaceDir = "D:/Github/PertaminaGLD";
const sourcePath = `${workspaceDir}/docs/wiring/GLDCH.pptx`;
const skillDir = "C:/Users/MSI/.codex/plugins/cache/openai-primary-runtime/presentations/26.909.12148/skills/presentations";
const buildDir = path.join(workspaceDir, ".codex-ppt-build");
const outputDir = path.join(workspaceDir, "output", "presentations");
const candidatePath = path.join(buildDir, "GLDCH-sensor-flow-r17-candidate.pptx");
const finalPath = path.join(outputDir, "GLDCH-sensor-flow-r17.pptx");
const navy = "#16324A", pale = "#F7FAFC", line = "#B7C8D8", muted = "#35526A";

const deck = await PresentationFile.importPptx(await FileBlob.load(sourcePath));

function text(slide, value, position, style = {}) {
  const shape = slide.shapes.add({ geometry: "textbox", position, fill: "none", line: { fill: "none", width: 0 } });
  shape.text = value;
  shape.text.style = { typeface: "Aptos", fontSize: 15, color: muted, autoFit: "shrinkText", ...style };
  return shape;
}

function callout(slide, position, limitation, improvement) {
  slide.shapes.add({ geometry: "roundRect", position, fill: pale, line: { fill: line, width: 1 } });
  text(slide, "Kekurangan dan perbaikan", { left: position.left + 16, top: position.top + 10, width: position.width - 32, height: 22 }, { fontSize: 16, color: navy, bold: true });
  text(slide, `Kekurangan: ${limitation}\nPerbaikan: ${improvement}`, { left: position.left + 16, top: position.top + 38, width: position.width - 32, height: position.height - 48 }, { fontSize: 14, color: muted });
}

// GLD board visuals
callout(deck.slides.getItem(1), { left: 35, top: 440, width: 1210, height: 106 },
  "sensor masih menyatu di motherboard; PCF8574, SHT40, dan rangkaian proteksi tambahan belum ada.",
  "versi berikutnya memisahkan sensor module dan menambah kontrol daya, lingkungan, serta proteksi.");
callout(deck.slides.getItem(4), { left: 35, top: 438, width: 1210, height: 104 },
  "V1 memakai jalur analog/driver INA333, OPA333, LM321, dan ULN2003 pada motherboard.",
  "V2 memakai OPA320, 8 sensor module eksternal, PCF8574, SHT40, TCA/MCP, dan tetap menyediakan +5VA.");
callout(deck.slides.getItem(5), { left: 35, top: 440, width: 1210, height: 96 },
  "penggantian IC atau perubahan acquisition terhadap V2 belum ditemukan pada source PCB.",
  "V3 mempertahankan OPA320, ADS1256, PCF8574, SHT40, TCA/MCP, +5VA, dan TPL5010.");
callout(deck.slides.getItem(6), { left: 25, top: 500, width: 855, height: 106 },
  "source PCB belum menunjukkan pembaruan acquisition dibanding V3.",
  "V4 mempertahankan sensor module eksternal, OPA320, ADS1256, PCF8574, SHT40, +5VA, dan TPL5010.");
callout(deck.slides.getItem(7), { left: 805, top: 190, width: 455, height: 190 },
  "board adapter tidak memuat ADS1256, TCA, PCF8574, SHT40, OPA, MCP4725, atau +5VA.",
  "V5 memusatkan fungsi interface E22, USB-UART, RS-485, dan OLED; TPS2116, TPS22964, TPS3839, TPS61175, serta TPL5010 tetap ada.");

// CH board visuals
callout(deck.slides.getItem(9), { left: 390, top: 155, width: 835, height: 132 },
  "CH V1 belum memiliki WDT; perubahan IC belum dapat ditetapkan tanpa source PCB/BOM yang cocok.",
  "V2 menambahkan WDT dan tetap menerima atau meneruskan data radio dari GLD.");
callout(deck.slides.getItem(10), { left: 45, top: 420, width: 1190, height: 110 },
  "CH V1 tidak memiliki WDT dan menggunakan papan memanjang dengan holder baterai.",
  "CH V2 memiliki WDT serta memakai PCB bundar/kompak; detail nomor IC perlu BOM yang sesuai.");
callout(deck.slides.getItem(11), { left: 400, top: 125, width: 825, height: 130 },
  "detail penggantian IC dari CH V2 ke V3 belum dapat dibuktikan oleh source PCB/BOM.",
  "CH V3 tetap memiliki WDT dan kembali memakai papan memanjang dengan holder baterai.");

await fs.mkdir(outputDir, { recursive: true });
await (await PresentationFile.exportPptx(deck)).save(candidatePath);
const { finalizePresentation } = await import(pathToFileURL(path.join(skillDir, "container_tools", "artifact_tool_utils.mjs")).href);
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
  receiptPath: path.join(buildDir, "GLDCH-sensor-flow-r17.validation.json"),
  verifyArtifactToolImport: true,
});
console.log(JSON.stringify(result, null, 2));
