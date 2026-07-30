import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const outputDir = new URL(".", import.meta.url).pathname.replace(/^\//, "");
const inputPath = `${outputDir}/MQ8_REPORT_FIXED_rebuild.xlsx`;
const outputPath = `${outputDir}/MQ8_REPORT_FIXED_warmup_temp.xlsx`;
const warmupPath = "D:/Github/PertaminaGLD/outputs/019fa1f7-6af7-7eb2-95d8-a5e9dc365fa2/30Juli2026/AllSensorWarmup.csv";
const colors = { navy: "#17365D", blue: "#1F4E78", paleBlue: "#D9EAF7", paleYellow: "#FFF2CC", grid: "#D9E1F2", white: "#FFFFFF" };

function mean(values) { return values.reduce((total, value) => total + value, 0) / values.length; }
function title(sheet, range, text, subtitle) {
  sheet.getRange(range).merge(); sheet.getRange(range.split(":")[0]).values = [[text]];
  sheet.getRange(range).format = { fill: colors.navy, font: { bold: true, color: colors.white, size: 16 }, verticalAlignment: "center" };
  const start = range.split(":")[0]; const endColumn = range.split(":")[1].replace(/[0-9]/g, ""); const row = Number(start.match(/\d+/)[0]) + 1; const column = start.replace(/[0-9]/g, "");
  sheet.getRange(`${column}${row}:${endColumn}${row}`).merge(); sheet.getRange(`${column}${row}`).values = [[subtitle]];
  sheet.getRange(`${column}${row}:${endColumn}${row}`).format = { fill: colors.paleBlue, font: { italic: true, color: "#404040" }, wrapText: true };
}
function header(sheet, range) { sheet.getRange(range).format = { fill: colors.blue, font: { bold: true, color: colors.white }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true, borders: { preset: "all", style: "thin", color: "#9EADBE" } }; }
function body(sheet, range) { sheet.getRange(range).format = { verticalAlignment: "center", wrapText: true, borders: { preset: "inside", style: "thin", color: colors.grid } }; }
function widths(sheet, values) { for (const [column, width] of values) sheet.getRange(`${column}:${column}`).format.columnWidth = width; }

const lines = (await fs.readFile(warmupPath, "utf8")).trim().split(/\r?\n/);
const headers = lines[0].split(",");
const sensors = headers.slice(7);
const firstTimestamp = new Date(lines[1].split(",")[0]).getTime();
const rows = lines.slice(1).map((line) => {
  const values = line.split(",");
  return { timeIso: values[0], elapsedMin: (new Date(values[0]).getTime() - firstTimestamp) / 60000, values: sensors.map((_, index) => Number(values[index + 7])) };
}).filter((row) => Number.isFinite(row.elapsedMin) && row.values.every(Number.isFinite));
const duration = rows.at(-1).elapsedMin;
const bins = [];
for (let minute = 0; minute <= duration; minute += 0.5) {
  const group = rows.filter((row) => row.elapsedMin >= minute && row.elapsedMin < minute + 0.5);
  if (group.length) bins.push([minute, ...sensors.map((_, index) => mean(group.map((row) => row.values[index])))]);
}
const first5 = rows.filter((row) => row.elapsedMin <= Math.min(5, duration));
const last5 = rows.filter((row) => row.elapsedMin >= Math.max(0, duration - 5));
const sensorSummary = sensors.map((sensor, index) => [sensor, mean(first5.map((row) => row.values[index])), mean(last5.map((row) => row.values[index])), null]);

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
for (const name of ["Warmup Semua Sensor", "Warmup Raw"]) {
  const existing = workbook.worksheets.getItemOrNullObject(name);
  if (!existing.isNullObject) workbook.worksheets.delete(name);
}
const sheet = workbook.worksheets.add("Warmup Semua Sensor");
const raw = workbook.worksheets.add("Warmup Raw");
sheet.showGridLines = false; raw.showGridLines = false;

title(sheet, "A1:K1", "Warm-up Semua Sensor", "Sumber: AllSensorWarmup.csv. Data diringkas menjadi rata-rata per 30 detik agar perubahan saat pemanasan mudah dilihat.");
sheet.getRange("A4:C4").values = [["Durasi rekaman (menit)", "Jumlah sampel", "Sumber"]]; header(sheet, "A4:C4");
sheet.getRange("A5:C5").values = [[duration, rows.length, "30Juli2026/AllSensorWarmup.csv"]]; body(sheet, "A5:C5"); sheet.getRange("A5").format.numberFormat = "0.000";
sheet.getRange("A8:D8").values = [["Sensor", "Rata-rata 5 menit awal (V)", "Rata-rata 5 menit akhir (V)", "Perubahan (V)"]]; header(sheet, "A8:D8");
sheet.getRange(`A9:D${8 + sensorSummary.length}`).values = sensorSummary;
for (let row = 9; row < 9 + sensorSummary.length; row++) sheet.getRange(`D${row}`).formulas = [[`=C${row}-B${row}`]];
body(sheet, `A9:D${8 + sensorSummary.length}`); sheet.getRange(`B9:D${8 + sensorSummary.length}`).format.numberFormat = "0.000000";
const tableStart = 20; const endColumn = String.fromCharCode(65 + sensors.length);
sheet.getRange(`A${tableStart}:${endColumn}${tableStart}`).values = [["Menit", ...sensors.map((sensor) => `${sensor} (V)`)]]; header(sheet, `A${tableStart}:${endColumn}${tableStart}`);
sheet.getRange(`A${tableStart + 1}:${endColumn}${tableStart + bins.length}`).values = bins; body(sheet, `A${tableStart + 1}:${endColumn}${tableStart + bins.length}`); sheet.getRange(`A${tableStart + 1}:I${tableStart + bins.length}`).format.numberFormat = "0.000000";
const chart = sheet.charts.add("line", sheet.getRange(`A${tableStart}:${endColumn}${tableStart + bins.length}`));
chart.title = "Warm-up semua sensor — rata-rata per 30 detik"; chart.hasLegend = true; chart.xAxis = { axisType: "textAxis" }; chart.yAxis = { numberFormatCode: "0.000" }; chart.setPosition("K4", "T24");
sheet.getRange("A17:H18").merge(); sheet.getRange("A17").values = [["Catatan warna chart: tiap warna mewakili sensor yang berbeda (MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, dan MQ2). Ini hanya perbandingan nilai tegangan saat warm-up; bukan klasifikasi gas atau alarm."]];
sheet.getRange("A17:H18").format = { fill: colors.paleYellow, wrapText: true, verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: "#C9B458" } };
sheet.freezePanes.freezeRows(tableStart); widths(sheet, [["A", 18], ["B", 23], ["C", 23], ["D", 18], ["E", 14], ["F", 14], ["G", 14], ["H", 14], ["I", 14], ["J", 3], ["K", 14]]);

title(raw, "A1:K1", "Warm-up Semua Sensor — Data Raw", "Salinan nilai dari AllSensorWarmup.csv; kolom waktu relatif ditambahkan agar mudah dibaca di Excel.");
raw.getRange("A4:K4").values = [["timeIso", "Menit sejak awal", "MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2", "Sumber"]]; header(raw, "A4:K4");
raw.getRange(`A5:K${4 + rows.length}`).values = rows.map((row) => [row.timeIso, row.elapsedMin, ...row.values, "AllSensorWarmup.csv"]); body(raw, `A5:K${4 + rows.length}`); raw.getRange(`B5:J${4 + rows.length}`).format.numberFormat = "0.000000";
raw.freezePanes.freezeRows(4); widths(raw, [["A", 29], ["B", 17], ["C", 14], ["D", 14], ["E", 14], ["F", 14], ["G", 14], ["H", 14], ["I", 14], ["J", 14], ["K", 25]]);

const preview = await workbook.render({ sheetName: "Warmup Semua Sensor", autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/MQ8_REPORT_FIXED_warmup_preview.png`, new Uint8Array(await preview.arrayBuffer()));
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "formula errors" });
await fs.writeFile(`${outputDir}/MQ8_REPORT_FIXED_warmup_errors.txt`, errors.ndjson ?? String(errors));
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
