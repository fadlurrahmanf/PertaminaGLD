import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const reportDir = "D:/Github/PertaminaGLD/apps/operator-hub/output/mq8-duty-cycle/heater/raw/Report";
const warmupPath = "D:/Github/PertaminaGLD/outputs/019fa1f7-6af7-7eb2-95d8-a5e9dc365fa2/30Juli2026/AllSensorWarmup.csv";
const outputDir = new URL(".", import.meta.url).pathname.replace(/^\//, "");
const outputPath = `${outputDir}/MQ8_REPORT_FIXED_rebuild.xlsx`;
const colors = { navy: "#17365D", blue: "#1F4E78", paleBlue: "#D9EAF7", paleYellow: "#FFF2CC", paleRed: "#FCE4D6", grid: "#D9E1F2", white: "#FFFFFF" };

function mean(values) { return values.reduce((sum, value) => sum + value, 0) / values.length; }
function slope(points) {
  const xMean = mean(points.map((p) => p.t)); const yMean = mean(points.map((p) => p.v));
  const den = points.reduce((sum, p) => sum + (p.t - xMean) ** 2, 0);
  return den ? points.reduce((sum, p) => sum + (p.t - xMean) * (p.v - yMean), 0) / den : 0;
}
function formatDuty(duty) { return `${duty.toFixed(duty % 1 ? 1 : 0)}%`; }
async function loadSession(file) {
  const text = await fs.readFile(path.join(reportDir, file), "utf8");
  const lines = text.trim().split(/\r?\n/);
  const rows = [];
  if (lines[0].startsWith("timestamp_local")) {
    const pattern = /^"[^"]*","([^"]+)","([^"]+)","([^"]+)","([^"]+)","([^"]+)","([^"]+)"/;
    for (const line of lines.slice(1)) {
      const match = line.match(pattern);
      if (!match) continue;
      rows.push({ t: Number(match[1]), session: match[2], on: Number(match[3]), off: Number(match[4]), duty: Number(match[5]), v: Number(match[6]) * 1000 });
    }
  } else {
    const headers = lines[0].split(",");
    const mq8Index = headers.indexOf("MQ8");
    const firstTime = new Date(lines[1].split(",")[0]).getTime();
    for (const line of lines.slice(1)) {
      const cols = line.split(",");
      const t = (new Date(cols[0]).getTime() - firstTime) / 1000;
      rows.push({ t, session: "ON1000OFF0_2", on: 1000, off: 0, duty: 100, v: Number(cols[mq8Index]) * 1000 });
    }
  }
  const valid = rows.filter((r) => Number.isFinite(r.t) && Number.isFinite(r.v));
  const duration = valid.at(-1).t;
  const first = valid.filter((r) => r.t <= Math.min(300, duration));
  const last = valid.filter((r) => r.t >= Math.max(0, duration - 300));
  const min = Math.min(...valid.map((r) => r.v)); const max = Math.max(...valid.map((r) => r.v));
  const bins = [];
  for (let start = 0; start <= duration; start += 30) {
    const group = valid.filter((r) => r.t >= start && r.t < start + 30);
    if (group.length) bins.push({ minute: start / 60, mean: mean(group.map((r) => r.v)), range: Math.max(...group.map((r) => r.v)) - Math.min(...group.map((r) => r.v)), count: group.length });
  }
  const lastSlope = slope(last);
  const last10Bins = bins.filter((b) => b.minute >= Math.max(0, duration / 60 - 5));
  const tailRange = Math.max(...last10Bins.map((b) => b.mean)) - Math.min(...last10Bins.map((b) => b.mean));
  const windows = [];
  for (let index = 0; index + 10 <= bins.length; index++) {
    const windowBins = bins.slice(index, index + 10);
    const windowSlope = slope(windowBins.map((bin) => ({ t: bin.minute, v: bin.mean })));
    const windowRange = Math.max(...windowBins.map((bin) => bin.mean)) - Math.min(...windowBins.map((bin) => bin.mean));
    windows.push({ start: windowBins[0].minute, end: windowBins.at(-1).minute + 0.5, slope: windowSlope, range: windowRange, score: windowRange + (5 * Math.abs(windowSlope)) });
  }
  return { file, rows: valid, session: valid[0].session, on: valid[0].on, off: valid[0].off, duty: valid[0].duty, duration, firstMean: mean(first.map((r) => r.v)), lastMean: mean(last.map((r) => r.v)), min, max, p2p: max - min, slope: lastSlope * 60, tailRange, bins, windows };
}

async function loadAllSensorWarmup() {
  const lines = (await fs.readFile(warmupPath, "utf8")).trim().split(/\r?\n/);
  const headers = lines[0].split(",");
  const sensors = headers.slice(7);
  const firstTimestamp = new Date(lines[1].split(",")[0]).getTime();
  const rows = lines.slice(1).map((line) => {
    const columns = line.split(",");
    return { timeIso: columns[0], elapsedMin: (new Date(columns[0]).getTime() - firstTimestamp) / 60000, values: sensors.map((_, index) => Number(columns[index + 7])) };
  }).filter((row) => Number.isFinite(row.elapsedMin) && row.values.every(Number.isFinite));
  const duration = rows.at(-1).elapsedMin;
  const bins = [];
  for (let start = 0; start <= duration; start += 0.5) {
    const group = rows.filter((row) => row.elapsedMin >= start && row.elapsedMin < start + 0.5);
    if (group.length) bins.push([start, ...sensors.map((_, sensorIndex) => mean(group.map((row) => row.values[sensorIndex])))]);
  }
  const first = rows.filter((row) => row.elapsedMin <= Math.min(5, duration));
  const last = rows.filter((row) => row.elapsedMin >= Math.max(0, duration - 5));
  const summary = sensors.map((sensor, sensorIndex) => [sensor, mean(first.map((row) => row.values[sensorIndex])), mean(last.map((row) => row.values[sensorIndex]))]);
  return { sensors, rows, duration, bins, summary };
}

const files = (await fs.readdir(reportDir)).filter((name) => name.toLowerCase().endsWith(".csv")).sort();
const sessions = await Promise.all(files.map(loadSession));
const referenceSession = sessions.find((session) => session.file.startsWith("13_ON1000_OFF0_HEATING"));
const referenceWindow = referenceSession.windows.reduce((best, candidate) => candidate.score < best.score ? candidate : best);
const stabilityResults = sessions.map((session) => {
  const best = session.windows.reduce((bestWindow, candidate) => candidate.score < bestWindow.score ? candidate : bestWindow);
  const firstEquivalent = session.file === referenceSession.file ? referenceWindow : session.windows.find((candidate) => candidate.score <= referenceWindow.score);
  return { session, best, firstEquivalent, reachesReference: Boolean(firstEquivalent) };
});
const warmup = await loadAllSensorWarmup();
const workbook = Workbook.create();
const summary = workbook.worksheets.add("Ringkasan Report");
const table = workbook.worksheets.add("Metrik per File");
const binsSheet = workbook.worksheets.add("Bin 30 Detik");
const stabilitySheet = workbook.worksheets.add("Stabilitas vs 100pct");
const warmupSheet = workbook.worksheets.add("Warmup Semua Sensor");
const warmupRawSheet = workbook.worksheets.add("Warmup Raw");
for (const sheet of [summary, table, binsSheet, stabilitySheet, warmupSheet, warmupRawSheet]) sheet.showGridLines = false;

function title(sheet, range, text, subtitle) {
  sheet.getRange(range).merge(); sheet.getRange(range.split(":")[0]).values = [[text]];
  sheet.getRange(range).format = { fill: colors.navy, font: { bold: true, color: colors.white, size: 16 }, verticalAlignment: "center" };
  const start = range.split(":")[0]; const endCol = range.split(":")[1].replace(/[0-9]/g, ""); const row = Number(start.match(/\d+/)[0]) + 1; const col = start.replace(/[0-9]/g, "");
  sheet.getRange(`${col}${row}:${endCol}${row}`).merge(); sheet.getRange(`${col}${row}`).values = [[subtitle]];
  sheet.getRange(`${col}${row}:${endCol}${row}`).format = { fill: colors.paleBlue, font: { italic: true, color: "#404040" }, wrapText: true };
}
function header(sheet, range) { sheet.getRange(range).format = { fill: colors.blue, font: { bold: true, color: colors.white }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true, borders: { preset: "all", style: "thin", color: "#9EADBE" } }; }
function body(sheet, range) { sheet.getRange(range).format = { verticalAlignment: "center", wrapText: true, borders: { preset: "inside", style: "thin", color: colors.grid } }; }
function widths(sheet, items) { for (const [column, width] of items) sheet.getRange(`${column}:${column}`).format.columnWidth = width; }

title(summary, "A1:H1", "Ringkasan Report — Apakah Sensor Sudah Stabil?", "Jawaban singkat dari pengujian duty cycle. Acuan stabilitas diambil dari bagian paling stabil pada run 100% selama 40 menit.");
summary.getRange("A4:H5").merge(); summary.getRange("A4").values = [["Cara baca: ‘stabil’ berarti grafik MQ8 sudah cukup datar selama lima menit. Ini tidak berarti nilai tegangannya harus sama dengan 100%; yang dibandingkan adalah kestabilan grafiknya."]];
summary.getRange("A4:H5").format = { fill: colors.paleYellow, wrapText: true, verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: "#C9B458" } };
summary.getRange("A7:D7").values = [["Duty cycle", "Grafik sudah stabil?", "Mulai stabil", "Arti sederhana"]]; header(summary, "A7:D7");
summary.getRange(`A8:D${7 + stabilityResults.length}`).values = stabilityResults.map((result) => {
  const isReference = result.session.file === referenceSession.file;
  const stable = isReference ? "YA — ACUAN" : result.reachesReference ? "YA" : "BELUM";
  const start = isReference ? referenceWindow.start : result.reachesReference ? result.firstEquivalent.start : null;
  const meaning = isReference ? "Ini menjadi pembanding kestabilan." : result.reachesReference ? (result.session.duty <= 25 ? "Grafik datar pada level rendah." : "Grafik sudah datar seperti acuan stabilitas.") : "Grafik masih berubah; waktu uji belum cukup.";
  return [result.session.duty / 100, stable, start, meaning];
});
body(summary, `A8:D${7 + stabilityResults.length}`); summary.getRange(`A8:A${7 + stabilityResults.length}`).format.numberFormat = "0.0%"; summary.getRange(`C8:C${7 + stabilityResults.length}`).format.numberFormat = "0.0 \"menit\"";
summary.getRange(`B8:B${7 + stabilityResults.length}`).conditionalFormats.add("containsText", { text: "YA", format: { fill: "#C6E0B4", font: { bold: true, color: "#006100" } } });
summary.getRange(`B8:B${7 + stabilityResults.length}`).conditionalFormats.add("containsText", { text: "BELUM", format: { fill: "#F4CCCC", font: { bold: true, color: "#9C0006" } } });
summary.getRange("A17:H19").merge(); summary.getRange("A17").values = [["Kesimpulan praktis: 12,5%, 25%, 37,5%, dan 50% memiliki periode grafik datar menurut acuan ini. Run 100% tambahan berdurasi 13,2 menit belum stabil. Detail cara hitung, angka teknis, dan interval acuan tersedia di sheet ‘Stabilitas vs 100pct’. "]];
summary.getRange("A17:H19").format = { fill: colors.paleBlue, wrapText: true, verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: "#9EADBE" } };
summary.freezePanes.freezeRows(2); widths(summary, [["A", 16], ["B", 22], ["C", 17], ["D", 54], ["E", 3], ["F", 3], ["G", 3], ["H", 3]]);

title(table, "A1:N1", "Metrik MQ8 per File Report", "Semua nilai dalam mV. Awal/akhir memakai jendela hingga lima menit; delta dan slope merupakan formula/hasil yang dapat diaudit.");
table.getRange("A4:N4").values = [["File sumber", "Sesi", "ON (ms)", "OFF (ms)", "Duty", "Sampel", "Durasi (min)", "Awal 5m", "Akhir 5m", "Δ 5m", "Minimum", "Maksimum", "Slope akhir", "Rentang bin akhir"]]; header(table, "A4:N4");
table.getRange(`A5:N${4 + sessions.length}`).values = sessions.map((s) => [s.file, s.session, s.on, s.off, s.duty / 100, s.rows.length, s.duration / 60, s.firstMean, s.lastMean, null, s.min, s.max, s.slope, s.tailRange]);
for (let row = 5; row < 5 + sessions.length; row++) table.getRange(`J${row}`).formulas = [[`=I${row}-H${row}`]];
body(table, `A5:N${4 + sessions.length}`); table.getRange(`E5:E${4 + sessions.length}`).format.numberFormat = "0.0%"; table.getRange(`G5:N${4 + sessions.length}`).format.numberFormat = "0.000";
table.freezePanes.freezeRows(4); widths(table, [["A", 49], ["B", 31], ["C", 11], ["D", 11], ["E", 10], ["F", 11], ["G", 14], ["H", 13], ["I", 13], ["J", 13], ["K", 13], ["L", 13], ["M", 15], ["N", 17]]);

title(stabilitySheet, "A1:H1", "Apakah Duty Cycle Mencapai Stabilitas 100%?", "Acuan adalah jendela 5 menit paling stabil pada file 100% / 40 menit. Semua penilaian hanya memakai data dalam folder Report.");
stabilitySheet.getRange("A4:B8").values = [
  ["File acuan 100%", referenceSession.file],
  ["Jendela acuan", `${referenceWindow.start.toFixed(1)}–${referenceWindow.end.toFixed(1)} menit`],
  ["Rentang acuan", referenceWindow.range],
  ["Slope acuan", referenceWindow.slope],
  ["Skor stabilitas acuan", referenceWindow.score],
];
header(stabilitySheet, "A4:A8"); body(stabilitySheet, "B4:B8");
stabilitySheet.getRange("B6:B8").format.numberFormat = "0.000";
stabilitySheet.getRange("A10:H10").values = [["Duty", "File", "Jendela paling stabil", "Skor terbaik", "Setara acuan 100%?", "Mulai setara (menit)", "Status", "Makna"]];
header(stabilitySheet, "A10:H10");
stabilitySheet.getRange(`A11:H${10 + stabilityResults.length}`).values = stabilityResults.map((result) => {
  const isReference = result.session.file === referenceSession.file;
  return [
    result.session.duty / 100,
    result.session.file,
    `${result.best.start.toFixed(1)}–${result.best.end.toFixed(1)} menit`,
    result.best.score,
    isReference ? "ACUAN" : result.reachesReference ? "YA" : "TIDAK",
    isReference ? referenceWindow.start : result.reachesReference ? result.firstEquivalent.start : null,
    isReference ? "Acuan 100%" : result.reachesReference ? "Stabil setara" : "Belum stabil setara",
    isReference ? "Batas pembanding" : result.reachesReference ? "Pernah mencapai kestabilan minimal setara 100%." : "Tidak ada jendela 5 menit yang setara dengan acuan 100%."
  ];
});
body(stabilitySheet, `A11:H${10 + stabilityResults.length}`);
stabilitySheet.getRange(`A11:A${10 + stabilityResults.length}`).format.numberFormat = "0.0%";
stabilitySheet.getRange(`D11:D${10 + stabilityResults.length}`).format.numberFormat = "0.000";
stabilitySheet.getRange(`F11:F${10 + stabilityResults.length}`).format.numberFormat = "0.0";
stabilitySheet.getRange(`E11:E${10 + stabilityResults.length}`).conditionalFormats.add("containsText", { text: "YA", format: { fill: "#C6E0B4", font: { bold: true, color: "#006100" } } });
stabilitySheet.getRange(`E11:E${10 + stabilityResults.length}`).conditionalFormats.add("containsText", { text: "TIDAK", format: { fill: "#F4CCCC", font: { bold: true, color: "#9C0006" } } });
stabilitySheet.getRange("A20:H22").merge();
stabilitySheet.getRange("A20").values = [["Cara baca: skor stabilitas = rentang rata-rata 30-detik dalam jendela 5 menit + perkiraan perubahan karena slope selama 5 menit. Skor lebih kecil berarti lebih datar/stabil. Duty dinyatakan mencapai kestabilan bila ada jendela 5 menit dengan skor tidak lebih besar dari acuan 100%. Nilai tegangan absolut tidak harus sama dengan 100%; yang dibandingkan adalah kestabilannya."]];
stabilitySheet.getRange("A20:H22").format = { fill: colors.paleYellow, wrapText: true, verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: "#C9B458" } };
stabilitySheet.freezePanes.freezeRows(10); widths(stabilitySheet, [["A", 12], ["B", 49], ["C", 21], ["D", 14], ["E", 20], ["F", 20], ["G", 20], ["H", 48]]);

title(warmupSheet, "A1:K1", "Warm-up Semua Sensor", "Sumber: AllSensorWarmup.csv. Data diringkas menjadi rata-rata per 30 detik agar perubahan saat pemanasan mudah dilihat.");
warmupSheet.getRange("A4:C4").values = [["Durasi rekaman (menit)", "Jumlah sampel", "Sumber"]]; header(warmupSheet, "A4:C4");
warmupSheet.getRange("A5:C5").values = [[warmup.duration, warmup.rows.length, "30Juli2026/AllSensorWarmup.csv"]]; body(warmupSheet, "A5:C5"); warmupSheet.getRange("A5").format.numberFormat = "0.000";
warmupSheet.getRange("A8:D8").values = [["Sensor", "Rata-rata 5 menit awal (V)", "Rata-rata 5 menit akhir (V)", "Perubahan (V)"]]; header(warmupSheet, "A8:D8");
warmupSheet.getRange(`A9:D${8 + warmup.summary.length}`).values = warmup.summary.map((item) => [item[0], item[1], item[2], null]);
for (let row = 9; row < 9 + warmup.summary.length; row++) warmupSheet.getRange(`D${row}`).formulas = [[`=C${row}-B${row}`]];
body(warmupSheet, `A9:D${8 + warmup.summary.length}`); warmupSheet.getRange(`B9:D${8 + warmup.summary.length}`).format.numberFormat = "0.000000";
const warmupStartRow = 20;
warmupSheet.getRange(`A${warmupStartRow}:${String.fromCharCode(65 + warmup.sensors.length)}${warmupStartRow}`).values = [["Menit", ...warmup.sensors.map((sensor) => `${sensor} (V)`)]];
header(warmupSheet, `A${warmupStartRow}:${String.fromCharCode(65 + warmup.sensors.length)}${warmupStartRow}`);
warmupSheet.getRange(`A${warmupStartRow + 1}:${String.fromCharCode(65 + warmup.sensors.length)}${warmupStartRow + warmup.bins.length}`).values = warmup.bins;
body(warmupSheet, `A${warmupStartRow + 1}:${String.fromCharCode(65 + warmup.sensors.length)}${warmupStartRow + warmup.bins.length}`);
warmupSheet.getRange(`A${warmupStartRow + 1}:I${warmupStartRow + warmup.bins.length}`).format.numberFormat = "0.000000";
const warmupChart = warmupSheet.charts.add("line", warmupSheet.getRange(`A${warmupStartRow}:${String.fromCharCode(65 + warmup.sensors.length)}${warmupStartRow + warmup.bins.length}`));
warmupChart.title = "Warm-up semua sensor — rata-rata per 30 detik"; warmupChart.hasLegend = true; warmupChart.xAxis = { axisType: "textAxis" }; warmupChart.yAxis = { numberFormatCode: "0.000" }; warmupChart.setPosition("K4", "T24");
warmupSheet.getRange("A17:H18").merge(); warmupSheet.getRange("A17").values = [["Catatan warna chart: tiap warna mewakili sensor yang berbeda (MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, dan MQ2). Ini hanya perbandingan nilai tegangan saat warm-up; bukan klasifikasi gas atau alarm."]];
warmupSheet.getRange("A17:H18").format = { fill: colors.paleYellow, wrapText: true, verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: "#C9B458" } };
warmupSheet.freezePanes.freezeRows(warmupStartRow); widths(warmupSheet, [["A", 18], ["B", 23], ["C", 23], ["D", 18], ["E", 14], ["F", 14], ["G", 14], ["H", 14], ["I", 14], ["J", 3], ["K", 14]]);

title(warmupRawSheet, "A1:K1", "Warm-up Semua Sensor — Data Raw", "Salinan nilai dari AllSensorWarmup.csv; kolom waktu relatif ditambahkan agar mudah dibaca di Excel.");
warmupRawSheet.getRange("A4:K4").values = [["timeIso", "Menit sejak awal", "MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2", "Sumber"]]; header(warmupRawSheet, "A4:K4");
warmupRawSheet.getRange(`A5:K${4 + warmup.rows.length}`).values = warmup.rows.map((row) => [row.timeIso, row.elapsedMin, ...row.values, "AllSensorWarmup.csv"]);
body(warmupRawSheet, `A5:K${4 + warmup.rows.length}`); warmupRawSheet.getRange(`B5:J${4 + warmup.rows.length}`).format.numberFormat = "0.000000";
warmupRawSheet.freezePanes.freezeRows(4); widths(warmupRawSheet, [["A", 29], ["B", 17], ["C", 14], ["D", 14], ["E", 14], ["F", 14], ["G", 14], ["H", 14], ["I", 14], ["J", 14], ["K", 25]]);

title(binsSheet, "A1:H1", "Bin MQ8 per 30 Detik — Report", "Data ringkas dihitung langsung dari setiap CSV di folder Report. Chart memakai nilai rata-rata setiap bin 30 detik.");
binsSheet.getRange("A4:E4").values = [["File", "Duty", "Menit", "Rata-rata MQ8 (mV)", "Rentang bin (mV)"]]; header(binsSheet, "A4:E4");
const binsRows = sessions.flatMap((s) => s.bins.map((b) => [s.file, s.duty / 100, b.minute, b.mean, b.range]));
binsSheet.getRange(`A5:E${4 + binsRows.length}`).values = binsRows; body(binsSheet, `A5:E${4 + binsRows.length}`); binsSheet.getRange(`B5:B${4 + binsRows.length}`).format.numberFormat = "0.0%"; binsSheet.getRange(`C5:E${4 + binsRows.length}`).format.numberFormat = "0.000";
const helpers = [["Menit", ...sessions.map((s) => `${formatDuty(s.duty)} ${s.file.includes("ON1000OFF0_2") ? "13m" : ""}`)]];
const maxBins = Math.max(...sessions.map((s) => s.bins.length));
for (let i = 0; i < maxBins; i++) helpers.push([i * 0.5, ...sessions.map((s) => s.bins[i]?.mean ?? null)]);
binsSheet.getRange(`G4:${String.fromCharCode(71 + sessions.length)}${4 + helpers.length}`).values = helpers;
const chart = binsSheet.charts.add("line", binsSheet.getRange(`G4:${String.fromCharCode(71 + sessions.length)}${4 + helpers.length}`));
chart.title = "MQ8 rata-rata per 30 detik — semua file Report"; chart.hasLegend = true; chart.xAxis = { axisType: "textAxis" }; chart.yAxis = { numberFormatCode: "0.0" }; chart.setPosition("G4", "P22");
binsSheet.freezePanes.freezeRows(4); widths(binsSheet, [["A", 49], ["B", 10], ["C", 11], ["D", 21], ["E", 18], ["F", 3], ["G", 12], ["H", 14]]);

for (const session of sessions) {
  const chartName = `Chart ${formatDuty(session.duty).replace("%", "pct")} ${session.file.includes("ON1000OFF0_2") ? "13m" : "40m"}`;
  const runSheet = workbook.worksheets.add(chartName);
  runSheet.showGridLines = false;
  title(runSheet, "A1:J1", `MQ8 — ${session.file}`, "Rata-rata setiap 30 detik dihitung langsung dari file Report ini. Tabel juga memuat rentang setiap bin untuk melihat kestabilan lokal.");
  runSheet.getRange("A4:D4").values = [["Menit", "Rata-rata MQ8 (mV)", "Rentang bin (mV)", "Sampel/bin"]];
  header(runSheet, "A4:D4");
  runSheet.getRange(`A5:D${4 + session.bins.length}`).values = session.bins.map((bin) => [bin.minute, bin.mean, bin.range, bin.count]);
  body(runSheet, `A5:D${4 + session.bins.length}`);
  runSheet.getRange(`A5:C${4 + session.bins.length}`).format.numberFormat = "0.000";
  const runChart = runSheet.charts.add("line", { chartType: "line", title: `MQ8 rata-rata per 30 detik — ${formatDuty(session.duty)}`, hasLegend: false });
  const runSeries = runChart.series.add("MQ8 rata-rata");
  runSeries.categoryFormula = `'${chartName}'!$A$5:$A$${4 + session.bins.length}`;
  runSeries.formula = `'${chartName}'!$B$5:$B$${4 + session.bins.length}`;
  runChart.hasLegend = false;
  runChart.xAxis = { axisType: "textAxis" };
  runChart.yAxis = { numberFormatCode: "0.0" };
  runChart.setPosition("F4", "N22");
  const noteStart = 7 + session.bins.length;
  runSheet.getRange(`A${noteStart}:D${noteStart + 1}`).merge();
  runSheet.getRange(`A${noteStart}`).values = [[`Sumber: heater/raw/Report/${session.file}. Durasi ${(session.duration / 60).toFixed(3)} menit; duty ${formatDuty(session.duty)}; ON ${session.on} ms, OFF ${session.off} ms.`]];
  runSheet.getRange(`A${noteStart}:D${noteStart + 1}`).format = { fill: colors.paleBlue, wrapText: true, verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: "#9EADBE" } };
  runSheet.freezePanes.freezeRows(4);
  widths(runSheet, [["A", 12], ["B", 23], ["C", 20], ["D", 14], ["E", 3], ["F", 14], ["G", 14], ["H", 14], ["I", 14], ["J", 14]]);
}

await fs.mkdir(outputDir, { recursive: true });
const preview = await workbook.render({ sheetName: "Ringkasan Report", autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/MQ8_REPORT_ONLY_ANALYSIS_preview.png`, new Uint8Array(await preview.arrayBuffer()));
const chartPreview = await workbook.render({ sheetName: "Bin 30 Detik", autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/MQ8_REPORT_ONLY_ANALYSIS_chart_preview.png`, new Uint8Array(await chartPreview.arrayBuffer()));
const individualPreview = await workbook.render({ sheetName: "Chart 50pct 40m", autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/MQ8_REPORT_ONLY_ANALYSIS_individual_preview.png`, new Uint8Array(await individualPreview.arrayBuffer()));
const stabilityPreview = await workbook.render({ sheetName: "Stabilitas vs 100pct", autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/MQ8_REPORT_FIXED_stability_preview.png`, new Uint8Array(await stabilityPreview.arrayBuffer()));
const warmupPreview = await workbook.render({ sheetName: "Warmup Semua Sensor", autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/MQ8_REPORT_FIXED_warmup_preview.png`, new Uint8Array(await warmupPreview.arrayBuffer()));
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "formula errors" });
await fs.writeFile(`${outputDir}/MQ8_REPORT_ONLY_ANALYSIS_errors.txt`, errors.ndjson ?? String(errors));
const output = await SpreadsheetFile.exportXlsx(workbook); await output.save(outputPath);
console.log(outputPath);
