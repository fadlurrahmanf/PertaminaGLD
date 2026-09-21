import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const sessionDir = "D:/Github/PertaminaGLD/apps/mq8-test-console/output/sessions/20260805_005912";
const outputPath = path.join(sessionDir, "MQ8_REPORT_FIXED.xlsx");
const previewDir = "D:/Github/PertaminaGLD/apps/mq8-test-console/.report-work/previews";
const sensors = ["mq8_v", "mq135_v", "mq3_v", "mq5_v", "mq4_v", "mq7_v", "mq6_v", "mq2_v"];
const sensorLabels = ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"];
const NAVY = "#173D63", BLUE = "#2F75B5", TEAL = "#0F766E", ORANGE = "#F59E0B", RED = "#C00000", GREEN = "#2E7D32", PALE = "#EAF2F8", GRID = "#C9D6E2";

function csvLine(line) {
  const out = []; let cell = "", quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (ch === '"') { if (quoted && line[i + 1] === '"') { cell += '"'; i += 1; } else quoted = !quoted; }
    else if (ch === "," && !quoted) { out.push(cell); cell = ""; }
    else cell += ch;
  }
  out.push(cell); return out;
}
async function readPhase(file) {
  const lines = (await fs.readFile(file, "utf8")).trim().split(/\r?\n/);
  const headers = csvLine(lines.shift());
  const rows = lines.map(csvLine).map(values => Object.fromEntries(headers.map((h, i) => [h, values[i] ?? ""])));
  const valid = rows.filter(r => r.telemetry_valid === "1" && r.mq8_status === "0");
  if (!valid.length) throw new Error(`Tidak ada data valid: ${path.basename(file)}`);
  const start = Number(valid[0].elapsed_s), end = Number(valid.at(-1).elapsed_s);
  const tail = valid.filter(r => Number(r.elapsed_s) >= end - 300);
  const mean = Object.fromEntries(sensors.map(key => [key, tail.reduce((sum, r) => sum + Number(r[key]) * 1000, 0) / tail.length]));
  const bins = new Map();
  for (const row of valid) {
    const bin = Math.floor((Number(row.elapsed_s) - start) / 30);
    if (!bins.has(bin)) bins.set(bin, []); bins.get(bin).push(Number(row.mq8_v) * 1000);
  }
  const binned = [...bins].map(([bin, values]) => ({ minute: bin / 2, mean: values.reduce((a, b) => a + b, 0) / values.length, range: Math.max(...values) - Math.min(...values), samples: values.length }));
  const tailVals = tail.map(r => Number(r.mq8_v) * 1000);
  const tailMinutes = (Number(tail.at(-1).elapsed_s) - Number(tail[0].elapsed_s)) / 60;
  return {
    file: path.basename(file), phase: valid.at(-1).phase, role: valid.at(-1).role, duty: Number(valid.at(-1).duty_pct),
    samples: valid.length, duration: (end - start) / 60, startMv: Number(valid[0].mq8_v) * 1000, endMv: Number(valid.at(-1).mq8_v) * 1000,
    final5Mean: mean.mq8_v, tailRange: Math.max(...tailVals) - Math.min(...tailVals),
    tailTrend: tailMinutes > 0 ? (tailVals.at(-1) - tailVals[0]) / tailMinutes : 0, mean, binned,
  };
}
function col(index) { let value = ""; for (let n = index; n >= 0; n = Math.floor(n / 26) - 1) value = String.fromCharCode(65 + (n % 26)) + value; return value; }
function title(sheet, heading, note, lastCol) {
  sheet.getRange(`A1:${lastCol}1`).merge(); sheet.getRange("A1").values = [[heading]];
  sheet.getRange(`A2:${lastCol}2`).merge(); sheet.getRange("A2").values = [[note]];
  sheet.getRange(`A1:${lastCol}1`).format = { fill: NAVY, font: { bold: true, color: "#FFFFFF", size: 16 }, horizontalAlignment: "left", verticalAlignment: "center" };
  sheet.getRange(`A2:${lastCol}2`).format = { fill: "#D9EAF7", font: { italic: true, color: "#35546D", size: 10 }, wrapText: true, verticalAlignment: "center" };
  sheet.getRange("A1").format.rowHeight = 28; sheet.getRange("A2").format.rowHeight = 30; sheet.showGridLines = false;
}
function header(sheet, range) { sheet.getRange(range).format = { fill: NAVY, font: { bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true, borders: { preset: "all", style: "thin", color: GRID } }; }
function tableStyle(sheet, range) { sheet.getRange(range).format = { borders: { preset: "all", style: "thin", color: GRID }, verticalAlignment: "center" }; }
function setWidths(sheet, widths) { widths.forEach((width, index) => { sheet.getRange(`${col(index)}:${col(index)}`).format.columnWidth = width; }); }
function addLineChart(sheet, sourceRange, positionStart, positionEnd, chartTitle, yTitle, legend = true) {
  const chart = sheet.charts.add("line", sheet.getRange(sourceRange));
  chart.title = chartTitle; chart.hasLegend = legend; chart.legend.position = "bottom";
  chart.xAxis = { axisType: "textAxis", title: { text: "Waktu fase (menit)" }, textStyle: { fontSize: 9 } };
  chart.yAxis = { title: { text: yTitle }, numberFormatCode: "0.000", textStyle: { fontSize: 9 } };
  chart.setPosition(positionStart, positionEnd); return chart;
}
function statusText(pair) {
  const magnitude = Math.abs(pair.mq8Delta);
  if (magnitude <= 0.02) return "Sangat dekat dengan recovery 100%";
  if (magnitude <= 0.06) return "Dampak kecil vs recovery 100%";
  return "Dampak jelas vs recovery 100%";
}

const files = (await fs.readdir(sessionDir)).filter(name => /^MQ8_RECOVERY_20260805_005912_\d{2}_.*_\d+pct\.csv$/i.test(name)).sort();
const phases = [];
for (const file of files) phases.push(await readPhase(path.join(sessionDir, file)));
if (phases.length !== 34) throw new Error(`Fase ditemukan ${phases.length}; seharusnya 34.`);
const pairs = phases.flatMap((phase, index) => phase.role === "TEST" ? [{
  duty: phase.duty, test: phase, recovery: phases[index - 1], mq8Delta: phase.final5Mean - phases[index - 1].final5Mean,
  allDelta: Object.fromEntries(sensors.map(sensor => [sensor, phase.mean[sensor] - phases[index - 1].mean[sensor]])),
}] : []);

const workbook = Workbook.create();

// 1. Summary
{
  const sheet = workbook.worksheets.add("Ringkasan Report"); title(sheet, "MQ8 Report Fixed — Hot-state recovery duty sweep", "Sesi 20260805_005912 | 34 fase selesai | seluruh baris CSV valid saja | IO8 akhir HIGH 100%", "H");
  const summary = [
    ["Status sesi", "SELESAI"], ["Fase selesai", 34], ["Rentang duty uji", "15% sampai 95%"], ["Durasi target/fase", "10 menit"], ["Konfirmasi arah", "20 detik"], ["Telemetry loss akhir", 0], ["IO8 akhir", "HIGH 100% terkonfirmasi"],
  ];
  sheet.getRange("A4:B10").values = summary; header(sheet, "A4:B4"); sheet.getRange("A4:B4").values = [["Pemeriksaan", "Hasil"]]; tableStyle(sheet, "A4:B10");
  sheet.getRange("D4:H4").merge(); sheet.getRange("D4").values = [["Kesimpulan yang dapat dipakai"]]; header(sheet, "D4:H4");
  sheet.getRange("D5:H9").merge(); sheet.getRange("D5").values = [["Setiap duty test 15%–95% menghasilkan rata-rata MQ8 lima menit terakhir lebih negatif dibanding recovery 100% tepat sebelumnya. Dampak paling besar berada pada 15%–65% (sekitar -0,083 s.d. -0,125 mV). Pada 70%–95%, dampak menyusut; 95% hanya -0,011 mV dibanding recovery 100% sebelumnya. Jadi perubahan duty tetap terlihat, tetapi semakin kecil saat duty mendekati 100%."]]; sheet.getRange("D5:H9").format = { fill: PALE, wrapText: true, verticalAlignment: "top", borders: { preset: "all", style: "thin", color: GRID } };
  sheet.getRange("A13:C30").values = [["Duty", "Delta MQ8 vs recovery 100% (mV)", "Interpretasi"], ...pairs.map(pair => [pair.duty / 100, pair.mq8Delta, statusText(pair)])]; header(sheet, "A13:C13"); tableStyle(sheet, "A13:C30"); sheet.getRange("A14:A30").format.numberFormat = "0%"; sheet.getRange("B14:B30").format.numberFormat = "0.000";
  addLineChart(sheet, "A13:B30", "E12", "L30", "Dampak penurunan duty terhadap MQ8", "Delta vs recovery 100% (mV)", false);
  setWidths(sheet, [24, 22, 37, 18, 18, 18, 18, 18]); sheet.freezePanes.freezeRows(3);
}

// 2. Phase metrics
{
  const sheet = workbook.worksheets.add("Metrik per Fase"); title(sheet, "Metrik MQ8 per fase", "Rata-rata akhir memakai 5 menit terakhir setiap fase. Range dan tren tetap ditampilkan sebagai metrik pendukung, bukan definisi status stabil.", "M");
  const rows = [["Fase", "Peran", "Duty", "Durasi (min)", "Sampel valid", "Awal (mV)", "Akhir (mV)", "Rata-rata akhir 5m (mV)", "Δ fase (mV)", "Range akhir 5m (mV)", "Tren akhir (mV/min)", "Status", "CSV sumber"], ...phases.map(phase => [phase.phase, phase.role, phase.duty / 100, phase.duration, phase.samples, phase.startMv, phase.endMv, phase.final5Mean, phase.endMv - phase.startMv, phase.tailRange, phase.tailTrend, "Stabil", phase.file])];
  sheet.getRange(`A4:M${rows.length + 3}`).values = rows; header(sheet, "A4:M4"); tableStyle(sheet, `A4:M${rows.length + 3}`); sheet.getRange(`C5:C${rows.length + 3}`).format.numberFormat = "0%"; sheet.getRange(`D5:K${rows.length + 3}`).format.numberFormat = "0.000";
  addLineChart(sheet, `A4:H${rows.length + 3}`, "O4", "X21", "Rata-rata akhir 5 menit per fase", "MQ8 (mV)", false);
  setWidths(sheet, [29, 12, 10, 13, 14, 13, 13, 20, 13, 19, 18, 12, 58]); sheet.freezePanes.freezeRows(4);
}

// 3. All sensor paired impact
{
  const sheet = workbook.worksheets.add("Dampak Semua Sensor"); title(sheet, "Perubahan sensor lain saat duty MQ8 diturunkan", "Nilai = rata-rata 5 menit terakhir test dikurangi recovery 100% tepat sebelumnya. Ini menunjukkan keterkaitan waktu, bukan bukti sebab-akibat tanpa kontrol lingkungan tambahan.", "K");
  const rows = [["Duty", ...sensorLabels], ...pairs.map(pair => [pair.duty / 100, ...sensors.map(sensor => pair.allDelta[sensor])])];
  sheet.getRange(`A4:I${rows.length + 3}`).values = rows; header(sheet, "A4:I4"); tableStyle(sheet, `A4:I${rows.length + 3}`); sheet.getRange(`A5:A${rows.length + 3}`).format.numberFormat = "0%"; sheet.getRange(`B5:I${rows.length + 3}`).format.numberFormat = "0.000";
  addLineChart(sheet, `A4:I${rows.length + 3}`, "K4", "U22", "Delta akhir 5 menit: test vs recovery 100%", "Delta (mV)", true);
  sheet.getRange("A24:I27").values = [["Catatan interpretasi"], ["MQ8 dan MQ135 memperlihatkan kecenderungan negatif saat duty diturunkan. Sensor lain berubah tidak seragam; kondisi udara/lingkungan bisa ikut berkontribusi."], ["Gunakan sheet Chart tiap duty untuk memeriksa bentuk respons test dan recovery, bukan hanya rata-rata akhir."]]; sheet.getRange("A24:I24").merge(); header(sheet, "A24:I24"); sheet.getRange("A25:I26").merge(); sheet.getRange("A25").format = { wrapText: true, fill: PALE, borders: { preset: "all", style: "thin", color: GRID } };
  setWidths(sheet, [11, 13, 13, 13, 13, 13, 13, 13, 13, 3, 13]); sheet.freezePanes.freezeRows(4);
}

// 4. All phase charts are deliberately combined in one worksheet to avoid a long tab strip.
const baseline = phases[0];
{
  const sheet = workbook.worksheets.add("Chart 100 Baseline"); title(sheet, "MQ8 — Baseline 100%", "Rata-rata per bin 30 detik. Baseline awal sebelum duty pertama diturunkan.", "H");
  const rows = [["Menit", "MQ8 rata-rata (mV)", "Rentang bin (mV)", "Sampel/bin"], ...baseline.binned.map(bin => [bin.minute, bin.mean, bin.range, bin.samples])];
  sheet.getRange(`A4:D${rows.length + 3}`).values = rows; header(sheet, "A4:D4"); tableStyle(sheet, `A4:D${rows.length + 3}`); sheet.getRange(`A5:C${rows.length + 3}`).format.numberFormat = "0.000";
  addLineChart(sheet, `A4:B${rows.length + 3}`, "F4", "N22", "MQ8 rata-rata per 30 detik — baseline 100%", "MQ8 (mV)", false); setWidths(sheet, [12, 24, 21, 14, 3, 13]); sheet.freezePanes.freezeRows(4);
}
for (const pair of pairs) {
  const recoveryLabel = pair.recovery.role === "BASELINE" ? "Baseline 100% sebelum Test 15%" : `Recovery 100% setelah Test ${pair.recovery.duty}% (sebelum Test ${pair.duty}%)`;
  const sheet = workbook.worksheets.add(`Chart ${pair.duty}pct`); title(sheet, `MQ8 — Test ${pair.duty}% vs 100% sebelum test`, `Pembanding: ${recoveryLabel}. Delta rata-rata akhir 5 menit: ${pair.mq8Delta.toFixed(3)} mV. ${statusText(pair)}.`, "H");
  const count = Math.max(pair.test.binned.length, pair.recovery.binned.length);
  const rows = [["Menit", `Test ${pair.duty}% (mV)`, `${recoveryLabel} (mV)`, `Range test ${pair.duty}% (mV)`, "Range 100% (mV)"]];
  for (let index = 0; index < count; index += 1) rows.push([index / 2, pair.test.binned[index]?.mean ?? null, pair.recovery.binned[index]?.mean ?? null, pair.test.binned[index]?.range ?? null, pair.recovery.binned[index]?.range ?? null]);
  sheet.getRange(`A4:E${rows.length + 3}`).values = rows; header(sheet, "A4:E4"); tableStyle(sheet, `A4:E${rows.length + 3}`); sheet.getRange(`A5:E${rows.length + 3}`).format.numberFormat = "0.000";
  addLineChart(sheet, `A4:C${rows.length + 3}`, "G4", "O22", `MQ8: ${pair.duty}% vs 100% sebelum Test ${pair.duty}%`, "MQ8 (mV)", true);
  sheet.getRange("G24:O24").merge(); sheet.getRange("G24").values = [[`Rata-rata akhir 5 menit: test ${pair.test.final5Mean.toFixed(3)} mV | recovery ${pair.recovery.final5Mean.toFixed(3)} mV | delta ${pair.mq8Delta.toFixed(3)} mV`]]; sheet.getRange("G24:O24").format = { fill: PALE, font: { bold: true, color: NAVY }, horizontalAlignment: "center", borders: { preset: "all", style: "thin", color: GRID } };
  setWidths(sheet, [12, 22, 24, 22, 24, 3, 14]); sheet.freezePanes.freezeRows(4);
}
{
  const sheet = workbook.worksheets.add("Chart Gabungan"); title(sheet, "MQ8 — Chart Gabungan semua duty", "Baseline 100% dan setiap pasangan Test/100% sebelum test. Satu chart per baris agar tidak perlu scroll horizontal; tabel sumber berada di bawah seluruh chart untuk audit.", "K");
  const chartData = [{ title: "Baseline 100%", subtitle: "Baseline sebelum Test 15%", headers: ["Menit", "Baseline 100% (mV)", "Rentang baseline (mV)", "Sampel/bin"], rows: baseline.binned.map(bin => [bin.minute, bin.mean, bin.range, bin.samples]), seriesEnd: "B" }];
  for (const pair of pairs) {
    const recoveryLabel = pair.recovery.role === "BASELINE" ? "Baseline 100% sebelum Test 15%" : `Recovery 100% setelah Test ${pair.recovery.duty}% (sebelum Test ${pair.duty}%)`;
    const count = Math.max(pair.test.binned.length, pair.recovery.binned.length), rows = [];
    for (let index = 0; index < count; index += 1) rows.push([index / 2, pair.test.binned[index]?.mean ?? null, pair.recovery.binned[index]?.mean ?? null, pair.test.binned[index]?.range ?? null, pair.recovery.binned[index]?.range ?? null]);
    chartData.push({ title: `Test ${pair.duty}% vs 100% sebelum test`, subtitle: `${recoveryLabel} | Delta akhir 5m ${pair.mq8Delta.toFixed(3)} mV`, headers: ["Menit", `Test ${pair.duty}% (mV)`, `${recoveryLabel} (mV)`, `Range test ${pair.duty}% (mV)`, "Range 100% (mV)"], rows, seriesEnd: "C" });
  }
  let dataRow = 172;
  chartData.forEach((item, index) => {
    const chartRow = 4 + index * 19, chartStart = `A${chartRow}`, chartEnd = `K${chartRow + 17}`, lastColumn = col(item.headers.length - 1);
    sheet.getRange(`A${dataRow}:${lastColumn}${dataRow + item.rows.length}`).values = [item.headers, ...item.rows]; header(sheet, `A${dataRow}:${lastColumn}${dataRow}`); tableStyle(sheet, `A${dataRow}:${lastColumn}${dataRow + item.rows.length}`); sheet.getRange(`A${dataRow + 1}:${lastColumn}${dataRow + item.rows.length}`).format.numberFormat = "0.000";
    addLineChart(sheet, `A${dataRow}:${item.seriesEnd}${dataRow + item.rows.length}`, chartStart, chartEnd, item.title, "MQ8 (mV)", item.seriesEnd === "C");
    dataRow += item.rows.length + 4;
  });
  setWidths(sheet, [12, 24, 43, 22, 22, 3, 13, 13, 13, 13, 13]); sheet.freezePanes.freezeRows(3);
}

const workbookCheck = await workbook.inspect({ kind: "workbook,sheet", maxChars: 3000 });
console.log(workbookCheck.ndjson);
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "formula error scan" });
console.log(errors.ndjson);
await fs.mkdir(previewDir, { recursive: true });
for (const sheet of workbook.worksheets.items) {
  const preview = await workbook.render({ sheetName: sheet.name, autoCrop: "all", scale: 0.7, format: "png" });
  await fs.writeFile(path.join(previewDir, `${sheet.name.replace(/[^a-z0-9]+/gi, "_")}.png`), new Uint8Array(await preview.arrayBuffer()));
}
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(`OUTPUT=${outputPath}`);
