import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const outputDir = new URL(".", import.meta.url).pathname.replace(/^\//, "");
const inputPath = `${outputDir}/MQ8_REPORT_FIXED.xlsx`;
const outputPath = `${outputDir}/MQ8_REPORT_FIXED_analysis_temp.xlsx`;
const warmupPath = "D:/Github/PertaminaGLD/outputs/019fa1f7-6af7-7eb2-95d8-a5e9dc365fa2/30Juli2026/AllSensorWarmup.csv";
const colors = { navy: "#17365D", blue: "#1F4E78", paleBlue: "#D9EAF7", paleYellow: "#FFF2CC", paleRed: "#FCE4D6", paleGreen: "#D9EAD3", grid: "#D9E1F2", white: "#FFFFFF" };

function mean(values) { return values.reduce((total, value) => total + value, 0) / values.length; }
function slope(points) {
  const xm = mean(points.map((point) => point.t)); const ym = mean(points.map((point) => point.v));
  const denominator = points.reduce((total, point) => total + (point.t - xm) ** 2, 0);
  return denominator ? points.reduce((total, point) => total + (point.t - xm) * (point.v - ym), 0) / denominator : 0;
}
function title(sheet, range, text, subtitle) {
  sheet.getRange(range).merge(); sheet.getRange(range.split(":")[0]).values = [[text]];
  sheet.getRange(range).format = { fill: colors.navy, font: { bold: true, color: colors.white, size: 16 }, verticalAlignment: "center" };
  const start = range.split(":")[0]; const endColumn = range.split(":")[1].replace(/[0-9]/g, ""); const row = Number(start.match(/\d+/)[0]) + 1; const column = start.replace(/[0-9]/g, "");
  sheet.getRange(`${column}${row}:${endColumn}${row}`).merge(); sheet.getRange(`${column}${row}`).values = [[subtitle]];
  sheet.getRange(`${column}${row}:${endColumn}${row}`).format = { fill: colors.paleBlue, font: { italic: true, color: "#404040" }, wrapText: true };
}
function header(sheet, range) { sheet.getRange(range).format = { fill: colors.blue, font: { bold: true, color: colors.white }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true, borders: { preset: "all", style: "thin", color: "#9EADBE" } }; }
function body(sheet, range) { sheet.getRange(range).format = { verticalAlignment: "center", wrapText: true, borders: { preset: "inside", style: "thin", color: colors.grid } }; }
function widths(sheet, items) { for (const [column, width] of items) sheet.getRange(`${column}:${column}`).format.columnWidth = width; }

const lines = (await fs.readFile(warmupPath, "utf8")).trim().split(/\r?\n/);
const headers = lines[0].split(","); const sensors = headers.slice(7);
const firstTimestamp = new Date(lines[1].split(",")[0]).getTime();
const rows = lines.slice(1).map((line) => {
  const values = line.split(",");
  return { t: (new Date(values[0]).getTime() - firstTimestamp) / 60000, values: sensors.map((_, index) => Number(values[index + 7])) };
}).filter((row) => Number.isFinite(row.t) && row.values.every(Number.isFinite));
const duration = rows.at(-1).t;
const bins = [];
for (let minute = 0; minute <= duration; minute += 0.5) {
  const group = rows.filter((row) => row.t >= minute && row.t < minute + 0.5);
  if (group.length) bins.push({ minute, values: sensors.map((_, index) => mean(group.map((row) => row.values[index]))) });
}
const sensorResults = sensors.map((sensor, index) => {
  const tail = bins.filter((bin) => bin.minute >= Math.max(0, duration - 5));
  const tailValues = tail.map((bin) => bin.values[index]);
  const tailSlope = slope(tail.map((bin) => ({ t: bin.minute, v: bin.values[index] })));
  const tailRange = Math.max(...tailValues) - Math.min(...tailValues);
  const stableWindows = [];
  for (let start = 0; start + 10 <= bins.length; start++) {
    const window = bins.slice(start, start + 10);
    const windowSlope = slope(window.map((bin) => ({ t: bin.minute, v: bin.values[index] })));
    const windowValues = window.map((bin) => bin.values[index]);
    const windowRange = Math.max(...windowValues) - Math.min(...windowValues);
    if (Math.abs(windowSlope) <= 0.001 && windowRange <= 0.010) stableWindows.push({ minute: window[0].minute, slope: windowSlope, range: windowRange });
  }
  const firstStable = stableWindows[0];
  const status = firstStable ? "STABIL SEMENTARA" : "MASIH BERGERAK";
  return { sensor, tailMean: mean(tailValues), tailSlope, tailRange, firstStable, status };
});

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const analysis = workbook.worksheets.add("Analisis Warmup");
analysis.showGridLines = false;
title(analysis, "A1:H1", "Analisis Warm-up Semua Sensor", "Sumber: AllSensorWarmup.csv, durasi 17.96 menit, status telemetry tercatat CO2. Analisis ini mendukung pembacaan warm-up, bukan pengganti acuan duty-cycle 100%.");
analysis.getRange("A4:H5").merge(); analysis.getRange("A4").values = [["Aturan pembacaan sementara: sensor dinilai ‘stabil sementara’ bila dalam satu jendela 5 menit nilai rata-rata per 30 detik memiliki perubahan kurang dari ±0,001 V/menit dan rentang tidak lebih dari 0,010 V. Aturan ini adalah kriteria laporan untuk membantu membaca grafik, bukan spesifikasi resmi sensor MQ."]];
analysis.getRange("A4:H5").format = { fill: colors.paleYellow, wrapText: true, verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: "#C9B458" } };
analysis.getRange("A7:G7").values = [["Sensor", "Status akhir rekaman", "Mulai stabil sementara", "Rata-rata 5 menit akhir (V)", "Slope akhir (V/menit)", "Rentang akhir (V)", "Arti sederhana"]]; header(analysis, "A7:G7");
analysis.getRange(`A8:G${7 + sensorResults.length}`).values = sensorResults.map((result) => [
  result.sensor,
  result.status,
  result.firstStable ? result.firstStable.minute : null,
  result.tailMean,
  result.tailSlope,
  result.tailRange,
  result.firstStable ? "Di bagian akhir, perubahan sudah kecil." : "Masih berubah; belum memenuhi aturan stabil sementara."
]);
body(analysis, `A8:G${7 + sensorResults.length}`);
analysis.getRange(`C8:C${7 + sensorResults.length}`).format.numberFormat = "0.0 \"menit\"";
analysis.getRange(`D8:F${7 + sensorResults.length}`).format.numberFormat = "0.000000";
analysis.getRange(`B8:B${7 + sensorResults.length}`).conditionalFormats.add("containsText", { text: "STABIL", format: { fill: colors.paleGreen, font: { bold: true, color: "#006100" } } });
analysis.getRange(`B8:B${7 + sensorResults.length}`).conditionalFormats.add("containsText", { text: "MASIH", format: { fill: colors.paleRed, font: { bold: true, color: "#9C0006" } } });
analysis.getRange("A19:H21").merge(); analysis.getRange("A19").values = [["Kesimpulan pemakaian: file ini memperlihatkan fase perubahan besar pada menit-menit awal lalu banyak kanal memasuki perubahan kecil. Namun rekaman hanya sampai sekitar 18 menit dan kondisi telemetry bertanda CO2; karena itu hasil ini mendukung aturan warm-up konservatif, tetapi tidak membuktikan bahwa semua sensor sudah siap untuk interpretasi gas pada kondisi apa pun."]];
analysis.getRange("A19:H21").format = { fill: colors.paleBlue, wrapText: true, verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: "#9EADBE" } };
analysis.freezePanes.freezeRows(7); widths(analysis, [["A", 13], ["B", 22], ["C", 22], ["D", 23], ["E", 22], ["F", 18], ["G", 48], ["H", 3]]);

const summary = workbook.worksheets.getItem("Ringkasan Report");
summary.getRange("A21:D23").merge(); summary.getRange("A21").values = [["Tambahan warm-up semua sensor: rekaman 17,96 menit menunjukkan banyak kanal sudah memasuki perubahan kecil pada bagian akhir. Karena data ini bertanda CO2 dan berhenti pada menit ke-18, ia dipakai sebagai dukungan warm-up saja—bukan pengganti acuan kestabilan duty-cycle 100%. Lihat sheet ‘Analisis Warmup’. "]];
summary.getRange("A21:D23").format = { fill: colors.paleBlue, wrapText: true, verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: "#9EADBE" } };

const preview = await workbook.render({ sheetName: "Analisis Warmup", autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/MQ8_REPORT_FIXED_warmup_analysis_preview.png`, new Uint8Array(await preview.arrayBuffer()));
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "formula errors" });
await fs.writeFile(`${outputDir}/MQ8_REPORT_FIXED_analysis_errors.txt`, errors.ndjson ?? String(errors));
const output = await SpreadsheetFile.exportXlsx(workbook); await output.save(outputPath);
console.log(JSON.stringify(sensorResults));
