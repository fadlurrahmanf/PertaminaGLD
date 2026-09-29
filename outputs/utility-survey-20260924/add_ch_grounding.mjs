import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const outputDir = "D:/Github/PertaminaGLD/outputs/utility-survey-20260924";
const outputPath = `${outputDir}/Daftar_Kebutuhan_Utilitas_SRU_Revisi.xlsx`;
const input = await FileBlob.load(outputPath);
const wb = await SpreadsheetFile.importXlsx(input);
const ws = wb.worksheets.getItem("Daftar Kebutuhan");

// Move the manual GLD and lintas-sistem rows down one row without changing their style.
for (let row = 30; row >= 23; row -= 1) {
  ws.getRange(`A${row + 1}:G${row + 1}`).copyFrom(ws.getRange(`A${row}:G${row}`), "all");
}
ws.getRange("A23:G23").values = [[
  "3.4\u200B",
  "Cluster Head",
  "Proteksi",
  "Grounding / proteksi petir",
  "Titik grounding dan proteksi antena sesuai kondisi lokasi",
  "",
  "titik/set",
]];

// Add CH to the summary while retaining the user's manually edited layout.
ws.getRange("A4:B9").values = [
  ["Total item", 20],
  ["Server", 5],
  ["Gateway", 6],
  ["GLD", 4],
  ["CH", 1],
  ["Lintas sistem", 4],
];

wb.recalculate();
const check = await wb.inspect({ kind: "table", range: "Daftar Kebutuhan!A2:G31", include: "values,formulas", tableMaxRows: 31, tableMaxCols: 7 });
console.log(check.ndjson);
const errors = await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 50 }, summary: "final formula error scan" });
console.log(errors.ndjson);
const preview = await wb.render({ sheetName: "Daftar Kebutuhan", range: "A2:G31", scale: 1 });
await fs.writeFile(`${outputDir}/Daftar_Kebutuhan_Utilitas_SRU_Revisi_preview.png`, new Uint8Array(await preview.arrayBuffer()));
const xlsx = await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(outputPath);
console.log(`OUTPUT=${outputPath}`);
