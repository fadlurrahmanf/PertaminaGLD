import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = new URL(".", import.meta.url).pathname.replace(/^\//, "");
const outputPath = `${outputDir}/MQ8_DUTY_ANALYSIS.xlsx`;

const colors = {
  navy: "#17365D",
  blue: "#1F4E78",
  teal: "#0F766E",
  paleBlue: "#D9EAF7",
  paleGreen: "#D9EAD3",
  paleYellow: "#FFF2CC",
  paleRed: "#FCE4D6",
  gray: "#F3F6F8",
  grid: "#D9E1F2",
  white: "#FFFFFF",
};

function title(sheet, range, text, subtitle) {
  sheet.getRange(range).merge();
  sheet.getRange(range.split(":")[0]).values = [[text]];
  sheet.getRange(range).format = {
    fill: colors.navy,
    font: { bold: true, color: colors.white, size: 16 },
    horizontalAlignment: "left",
    verticalAlignment: "center",
  };
  const first = range.split(":")[0].replace(/[0-9]/g, "");
  const row = Number(range.match(/\d+/)[0]) + 1;
  sheet.getRange(`${first}${row}:${range.split(":")[1].replace(/[0-9]/g, "")}${row}`).merge();
  sheet.getRange(`${first}${row}`).values = [[subtitle]];
  sheet.getRange(`${first}${row}:${range.split(":")[1].replace(/[0-9]/g, "")}${row}`).format = {
    fill: colors.paleBlue,
    font: { italic: true, color: "#404040", size: 10 },
    wrapText: true,
    verticalAlignment: "center",
  };
}

function header(sheet, range) {
  sheet.getRange(range).format = {
    fill: colors.blue,
    font: { bold: true, color: colors.white },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: "#9EADBE" },
  };
}

function body(sheet, range) {
  sheet.getRange(range).format = {
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "inside", style: "thin", color: colors.grid },
  };
}

function note(sheet, range, text, fill = colors.paleYellow) {
  sheet.getRange(range).merge();
  sheet.getRange(range.split(":")[0]).values = [[text]];
  sheet.getRange(range).format = {
    fill,
    font: { color: "#404040", italic: true },
    wrapText: true,
    verticalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: "#C9B458" },
  };
}

function setWidths(sheet, entries) {
  for (const [col, width] of entries) sheet.getRange(`${col}:${col}`).format.columnWidth = width;
}

const controlled = [
  ["OFF", "0,1000", 0, 15, -1.132, -1.147, 0.368, -0.004, "Tidak ada respons", "Baseline dingin; pembanding."],
  ["12.5%", "125,875", 12.5, 40, -1.133, -1.163, 0.475, -0.004, "Tidak ada respons", "Setara baseline dingin dalam rentang noise."],
  ["25%", "250,750", 25, 40, -1.144, -1.128, 0.426, 0.004, "Tidak ada respons", "Setara baseline dingin dalam rentang noise."],
  ["37.5%", "375,625", 37.5, 40, 108.671, 126.391, 130.025, -0.278, "Respons kuat", "Band lokal sekitar 124–126 mV; perlu pengulangan dingin."],
  ["50%", "500,500", 50, 40, 233.049, 234.007, 289.816, -0.017, "Respons kuat", "Band lokal sekitar 225–234 mV; ada drift ringan setelah 30 menit."],
  ["100% / 40 min", "1000,0", 100, 40, 226.216, 6.399, 434.082, -0.523, "Belum plateau", "Terus turun hingga akhir rekaman; bukan plateau stabil."],
  ["100% / 60 min", "1000,0", 100, 60, 38.446, 20.762, 79.513, 0.381, "Tidak repeatable", "Turun lalu naik kembali; perilaku tidak konsisten dengan run 40 min."],
];

const cooldown = [
  ["12.5%", -1.1444, -1.1511, -0.0067, 0.4008, "Kembali ke baseline dingin"],
  ["25%", -1.1086, -1.1030, 0.0056, 0.2916, "Kembali ke baseline dingin"],
  ["37.5%", -1.0982, -1.0969, 0.0013, 0.3219, "Kembali ke baseline dingin"],
  ["50%", -1.1091, -1.1277, -0.0187, 0.4133, "Kembali ke baseline dingin"],
  ["100%", -1.1119, -1.0952, 0.0166, 0.4444, "Kembali ke baseline dingin"],
];

const trend = [
  [0, 46.77, 171.54, 324.88, 44.385],
  [5, 124.60, 231.96, 95.30, 16.562],
  [10, 123.92, 225.41, 46.65, 6.105],
  [15, 123.14, 225.43, 26.04, 4.053],
  [20, 123.46, 226.09, 19.55, 2.975],
  [25, 124.47, 226.25, 13.18, 11.674],
  [30, 125.78, 228.76, 9.85, 11.563],
  [35, 126.42, 233.78, 7.02, 14.529],
  [40, null, null, null, 13.708],
  [45, null, null, null, 14.458],
  [50, null, null, null, 16.947],
  [55, null, null, null, 20.070],
];

const user100 = [
  [0, -1.014, 0.165], [0.5, 77.131, 101.370], [1, 81.927, 22.334], [1.5, 69.376, 10.604],
  [2, 58.911, 9.798], [2.5, 50.104, 9.207], [3, 42.282, 6.193], [3.5, 37.380, 5.769],
  [4, 31.087, 6.078], [4.5, 28.347, 5.270], [5, 25.574, 3.534], [5.5, 22.083, 4.692],
  [6, 20.242, 5.178], [6.5, 17.519, 6.370], [7, 16.958, 4.878], [7.5, 16.674, 7.186],
  [8, 15.308, 5.903], [8.5, 15.809, 5.027], [9, 13.721, 7.170], [9.5, 13.274, 6.206],
  [10, 11.547, 8.255], [10.5, 10.980, 6.914], [11, 10.828, 5.733], [11.5, 10.178, 5.961],
  [12, 11.532, 3.785], [12.5, 12.942, 5.378], [13, 11.591, 5.925],
];

const legacy = [
  ["12.5%", 5.57, -1.063, -1.053, 0.411],
  ["25%", 6.91, -1.012, -1.041, 0.372],
  ["37.5%", 5.03, -1.072, -1.071, 0.359],
  ["50%", 5.87, 96.280, 99.544, 117.820],
  ["62.5%", 5.51, 181.632, 194.510, 221.782],
];

const workbook = Workbook.create();
const summary = workbook.worksheets.add("Ringkasan");
const tests = workbook.worksheets.add("Uji Terkontrol");
const cooldownSheet = workbook.worksheets.add("Cooldown");
const trendSheet = workbook.worksheets.add("Trend 1 Menit");
const userSheet = workbook.worksheets.add("100pct Pengguna");
const legacySheet = workbook.worksheets.add("Referensi Lama");

for (const sheet of [summary, tests, cooldownSheet, trendSheet, userSheet, legacySheet]) sheet.showGridLines = false;

title(summary, "A1:J1", "Analisis MQ8 — Duty Cycle Heater (IO8)", "Sumber: CSV eksperimen terorganisasi hingga 30 Juli 2026. Nilai adalah tegangan MQ8; interpretasi tidak dipakai untuk inferensi gas/alarm.");
summary.getRange("A4:B4").values = [["Keputusan", "Hasil berbasis data"]];
summary.getRange("B4:F4").merge();
header(summary, "A4:F4");
summary.getRange("A5:B9").values = [
  ["Tujuan", "Menilai respons MQ8 terhadap duty cycle IO8 dan menentukan apakah ada plateau stabil."],
  ["Ambang respons", "Baseline dingin: rata-rata -1.1375 mV; batas mean + 3SD = -1.0483 mV."],
  ["12.5% & 25%", "Tidak berbeda bermakna dari baseline dingin dalam rekaman 40 menit."],
  ["37.5% & 50%", "Ada respons kuat dan band lokal, tetapi masing-masing hanya satu run terkendali; belum cukup untuk karakteristik final."],
  ["100%", "Dua run tidak repeatable dan belum membuktikan plateau permanen. Jangan tetapkan waktu siap dari 100% saja."],
];
summary.getRange("B5:F9").merge(true);
body(summary, "A5:F9");
note(summary, "A11:J12", "Rekomendasi operasional sementara: gunakan pemanasan kontinu dan aturan warm-up konservatif 15–20 menit sambil mengumpulkan pengulangan cold-start. Untuk data saat ini, jangan memakai duty cycle 12.5%/25% sebagai mode pembacaan karena responsnya tetap seperti sensor dingin.", colors.paleYellow);
summary.getRange("A14:F14").values = [["Run", "Duty", "Durasi (min)", "Δ 5 menit (mV)", "Status", "Kesimpulan singkat"]];
header(summary, "A14:F14");
summary.getRange("A15:F21").values = controlled.map((r) => [r[0], r[2] / 100, r[3], null, r[8], r[9]]);
summary.getRange("D15").formulas = [["='Uji Terkontrol'!G5"]];
summary.getRange("D15:D21").fillDown();
body(summary, "A15:F21");
summary.getRange("B15:B21").format.numberFormat = "0.0%";
summary.getRange("C15:D21").format.numberFormat = "0.000";
summary.getRange("D15:D21").conditionalFormats.add("colorScale", { colors: ["#F8696B", "#FFEB84", "#63BE7B"] });
summary.freezePanes.freezeRows(2);
setWidths(summary, [["A", 19], ["B", 17], ["C", 15], ["D", 16], ["E", 19], ["F", 42], ["G", 14], ["H", 14], ["I", 14], ["J", 14]]);

title(tests, "A1:K1", "Uji Duty Cycle Terkontrol", "Setiap run valid direkam setelah baseline dingin. Delta dihitung otomatis: rata-rata 5 menit akhir dikurangi rata-rata 5 menit awal.");
tests.getRange("A4:K4").values = [["Run", "Perintah UNO", "Duty", "Durasi (min)", "Awal 5m (mV)", "Akhir 5m (mV)", "Δ 5m (mV)", "P2P (mV)", "Slope akhir (mV/min)", "Status", "Interpretasi"]];
header(tests, "A4:K4");
tests.getRange("A5:K11").values = controlled.map((r) => [r[0], r[1], r[2] / 100, r[3], r[4], r[5], null, r[6], r[7], r[8], r[9]]);
tests.getRange("G5").formulas = [["=F5-E5"]];
tests.getRange("G5:G11").fillDown();
body(tests, "A5:K11");
tests.getRange("C5:C11").format.numberFormat = "0.0%";
tests.getRange("D5:I11").format.numberFormat = "0.000";
tests.getRange("G5:G11").conditionalFormats.add("colorScale", { colors: ["#F8696B", "#FFEB84", "#63BE7B"] });
tests.getRange("A14:K14").values = [["Sumber raw valid", "", "", "", "", "", "", "", "", "", ""]];
tests.getRange("A14:K14").merge();
tests.getRange("A14:K14").format = { fill: colors.paleBlue, font: { bold: true, color: colors.blue } };
tests.getRange("A15:A20").values = [
  ["heater/raw/02_ON125_OFF875_HEATING_20260729_170716.csv"],
  ["heater/raw/04_ON250_OFF750_HEATING_20260729_180309.csv"],
  ["heater/raw/08_ON375_OFF625_HEATING_RETRY_20260729_195308.csv"],
  ["heater/raw/10_ON500_OFF500_HEATING_20260729_204855.csv"],
  ["heater/raw/13_ON1000_OFF0_HEATING_20260729_220745.csv"],
  ["heater/raw/15_ON1000_OFF0_HEATING_60MIN_20260729_230351.csv"],
];
tests.getRange("A15:K20").merge(true);
body(tests, "A15:K20");
tests.freezePanes.freezeRows(4);
setWidths(tests, [["A", 18], ["B", 15], ["C", 11], ["D", 14], ["E", 15], ["F", 15], ["G", 14], ["H", 12], ["I", 18], ["J", 18], ["K", 45]]);

title(cooldownSheet, "A1:G1", "Validasi Cooldown", "Tujuan: memastikan pembacaan MQ8 kembali dekat ke baseline saat IO8 LOW. Semua file valid menunjukkan nilai dingin sekitar -1.1 mV.");
cooldownSheet.getRange("A4:G4").values = [["Duty sebelumnya", "Awal 5m (mV)", "Akhir 5m (mV)", "Δ 5m (mV)", "P2P (mV)", "Kesimpulan", "Status"]];
header(cooldownSheet, "A4:G4");
cooldownSheet.getRange("A5:G9").values = cooldown.map((r) => [r[0], r[1], r[2], r[3], r[4], r[5], "Valid"]);
body(cooldownSheet, "A5:G9");
cooldownSheet.getRange("B5:E9").format.numberFormat = "0.0000";
cooldownSheet.getRange("A12:G13").merge();
cooldownSheet.getRange("A12").values = [["Kesimpulan: cooldown rata-rata sama-sama kembali dekat baseline, sehingga perbedaan besar saat duty 37.5%/50% bukan sekadar offset yang menetap setelah pemanasan. Namun ini belum menggantikan kalibrasi sensor atau pengujian gas terkontrol."]];
cooldownSheet.getRange("A12:G13").format = { fill: colors.paleGreen, wrapText: true, verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: "#7F9F6E" } };
setWidths(cooldownSheet, [["A", 16], ["B", 17], ["C", 17], ["D", 15], ["E", 13], ["F", 32], ["G", 12]]);

title(trendSheet, "A1:F1", "Trend Rata-rata per Menit", "Ringkasan trend dari run valid. Dipakai untuk membaca bentuk respons, bukan sebagai model suhu/heater absolut.");
trendSheet.getRange("A4:E4").values = [["Menit", "37.5% (mV)", "50% (mV)", "100% / 40m (mV)", "100% / 60m (mV)"]];
header(trendSheet, "A4:E4");
trendSheet.getRange("A5:E16").values = trend;
body(trendSheet, "A5:E16");
trendSheet.getRange("A5:E16").format.numberFormat = "0.000";
const trendChart = trendSheet.charts.add("line", trendSheet.getRange("A4:E16"));
trendChart.title = "MQ8 per menit — respons run terkendali";
trendChart.hasLegend = true;
trendChart.xAxis = { axisType: "textAxis" };
trendChart.yAxis = { numberFormatCode: "0.0" };
trendChart.setPosition("G4", "N22");
note(trendSheet, "A19:F21", "Pembacaan chart: 37.5% dan 50% naik cepat lalu membentuk band lokal. Dua run 100% bergerak berbeda, sehingga belum ada dasar untuk menyebut 100% sebagai plateau repeatable.", colors.paleRed);
setWidths(trendSheet, [["A", 12], ["B", 18], ["C", 18], ["D", 20], ["E", 20], ["F", 4]]);

title(userSheet, "A1:G1", "Run 100% Tambahan — Data Pengguna", "Sumber: C:/Users/MSI/Downloads/ON1000OFF0_2.csv. Durasi 13.216 menit; fokus pada indikasi plateau, bukan pembandingan antar-run.");
userSheet.getRange("A4:D4").values = [["Menit", "Rata-rata bin 30s (mV)", "Rentang bin 30s (mV)", "Interpretasi"]];
header(userSheet, "A4:D4");
userSheet.getRange("A5:D31").values = user100.map((r) => [r[0], r[1], r[2], r[0] < 10 ? "Masih menurun" : "Mulai masuk band sempit; belum konfirmasi plateau"]);
body(userSheet, "A5:D31");
userSheet.getRange("A5:C31").format.numberFormat = "0.000";
const userChart = userSheet.charts.add("line", userSheet.getRange("A4:B31"));
userChart.title = "Run 100% tambahan — rerata bin 30 detik";
userChart.hasLegend = false;
userChart.xAxis = { axisType: "textAxis" };
userChart.yAxis = { numberFormatCode: "0.0" };
userChart.setPosition("F4", "M22");
note(userSheet, "A34:G36", "Kesimpulan run ini: respons mulai memasuki band yang lebih sempit sekitar menit ke-10, tetapi data berhenti pada 13.2 menit. Empat bin terakhir masih membentang 2.764 mV; plateau stabil belum dapat dikonfirmasi. Rekam hingga sedikitnya 17–20 menit bila mengulang run ini.", colors.paleYellow);
userSheet.freezePanes.freezeRows(4);
setWidths(userSheet, [["A", 12], ["B", 23], ["C", 23], ["D", 43], ["E", 4], ["F", 15], ["G", 15]]);

title(legacySheet, "A1:F1", "Referensi Lama dan Warm-up", "Data ini bersifat pendukung saja karena run lama tidak mengikuti cold-reset terkendali yang sama.");
legacySheet.getRange("A4:F4").values = [["Duty", "Durasi (min)", "Awal (mV)", "Akhir (mV)", "P2P (mV)", "Catatan"]];
header(legacySheet, "A4:F4");
legacySheet.getRange("A5:F9").values = legacy.map((r) => [...r, "Bukan cold-reset; jangan dipakai sebagai penetapan final."]);
body(legacySheet, "A5:F9");
legacySheet.getRange("B5:E9").format.numberFormat = "0.000";
legacySheet.getRange("A12:F12").merge();
legacySheet.getRange("A12").values = [["Referensi warm-up historis: WarmupBaru3 menunjukkan indikasi band lokal sekitar 12–15 menit (rekaman berhenti 17 menit); Warmup3 mencapai perilaku lebih tenang sekitar menit ke-21. Karena antar-run MQ tidak sepenuhnya repeatable, aturan operasional sementara 15–20 menit lebih aman daripada mengunci satu angka sempit."]];
legacySheet.getRange("A12:F12").format = { fill: colors.paleYellow, wrapText: true, verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: "#C9B458" } };
setWidths(legacySheet, [["A", 13], ["B", 15], ["C", 14], ["D", 14], ["E", 14], ["F", 46]]);

await fs.mkdir(outputDir, { recursive: true });
const preview = await workbook.render({ sheetName: "Ringkasan", autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/MQ8_DUTY_ANALYSIS_preview.png`, new Uint8Array(await preview.arrayBuffer()));
const trendPreview = await workbook.render({ sheetName: "Trend 1 Menit", autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/MQ8_DUTY_ANALYSIS_trend_preview.png`, new Uint8Array(await trendPreview.arrayBuffer()));
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);

const inspect = await workbook.inspect({ kind: "workbook,sheet,table,formula", maxChars: 3500, tableMaxRows: 8, tableMaxCols: 8 });
await fs.writeFile(`${outputDir}/MQ8_DUTY_ANALYSIS_inspect.txt`, inspect.ndjson ?? String(inspect));
console.log(outputPath);
