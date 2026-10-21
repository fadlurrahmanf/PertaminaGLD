import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const base = "D:/Github/PertaminaGLD/tmp/gld1-nulling-xlsx";
const outDir = "D:/Github/PertaminaGLD/outputs/gld1-nulling-com7-20261019";
const outFile = `${outDir}/Laporan_Nulling_GLD1_COM7.xlsx`;
const data = JSON.parse(await fs.readFile(`${base}/analysis.json`, "utf8"));
// This path is the workbook first created by this task; reruns refine its layout.

const wb = Workbook.create();
const summary = wb.worksheets.add("Ringkasan");
const phases = wb.worksheets.add("Tahapan");
const steps = wb.worksheets.add("Per langkah");
const clock = (s) => { const [h,m,sec] = s.split(":").map(Number); return (h*3600+m*60+sec)/86400; };
const textTime = (s) => s ? clock(s.slice(11, 23)) : null;
const title = (sheet, label, last) => {
  sheet.showGridLines = false;
  sheet.getRange(`A1:${last}1`).format.font = { name: "Arial", size: 14, bold: true, color: "#17324A" };
  sheet.getRange("A1").values = [[label]];
};
const header = (range) => { range.format = { fill: "#17324A", font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" }, verticalAlignment: "center" }; };
const body = (sheet, range) => { sheet.getRange(range).format.font = { name: "Arial", size: 10, color: "#172D3B" }; };

title(summary, "Hasil nulling GLD1 Model 1 — COM7", "L");
summary.getRange("A3:F3").values = [["Tanggal", "19 Okt 2026", "Mulai service WIB", clock("14:52:36.526"), "Selesai WIB", clock("15:00:33.491")]];
summary.getRange("D3").setNumberFormat("hh:mm:ss.000");
summary.getRange("F3").setNumberFormat("hh:mm:ss.000");
summary.getRange("A4:F4").values = [["Durasi service (detik)", data.totalServiceSeconds, "Perintah sampai hasil (detik)", data.totalCommandSeconds, "Hasil", "8/8 OK"]];
summary.getRange("A5:F5").values = [["Profil aktif", 2, "Binding model", 1, "Inference", "BELUM SIAP"]];
summary.getRange("A6").values = [["Waktu kanal: selisih log diterima PC; interval polling sekitar 0,25 detik, ditambah latensi komunikasi."]];
summary.getRange("A7").values = [["Sumber: log serial GLD1 dan read-back Operator Hub, 19 Oktober 2026 (WIB)."]];
summary.getRange("A8:L8").values = [["CH", "Sensor", "Mulai WIB", "Selesai WIB", "Durasi (detik)", "Durasi (menit)", "DAC", "Hasil", "Baseline (V)", "Akhir (V)", "Delta (V)", "Ambang (V)"]];
header(summary.getRange("A8:L8"));
const sr = data.channels.map((x) => [x.ch,x.sensor,clock(x.start),clock(x.finish),null,null,x.dac,x.status,x.baselineV,x.afterV,x.deltaV,x.thresholdV]);
summary.getRange("A9:L16").values = sr;
summary.getRange("E9:F16").formulas = data.channels.map((_,i) => [`=(D${i+9}-C${i+9})*86400`, `=E${i+9}/60`]);
summary.getRange("C9:D16").setNumberFormat("hh:mm:ss.000");
summary.getRange("E9:E16").setNumberFormat("0.0");
summary.getRange("F9:F16").setNumberFormat("0.00");
summary.getRange("I9:L16").setNumberFormat("0.000000");
summary.getRange("A18").values = [["Keterangan: nilai observeMs pada tahap adalah waktu observasi ADC; bukan durasi wall-clock seluruh tahap."]];
summary.getRange("A19").values = [["Profil baru belum terikat ke model; inference tetap tertahan hingga binding disetujui operator."]];
body(summary, "A3:L19");
header(summary.getRange("A8:L8"));
summary.getRange("A:A").format.columnWidth = 24;
summary.getRange("B:B").format.columnWidth = 20;
summary.getRange("C:C").format.columnWidth = 26;
summary.getRange("D:D").format.columnWidth = 21;
summary.getRange("E:E").format.columnWidth = 22;
summary.getRange("F:F").format.columnWidth = 18;
summary.getRange("G:H").format.columnWidth = 13;
summary.getRange("I:L").format.columnWidth = 17;
summary.getRange("A8:L8").format.horizontalAlignment = "center";
summary.getRange("A9:B16").format.horizontalAlignment = "center";
summary.getRange("G9:H16").format.horizontalAlignment = "center";
summary.getRange("D3").format.horizontalAlignment = "center";
summary.getRange("F3").format.horizontalAlignment = "center";
summary.getRange("B3:B5").format.horizontalAlignment = "center";
summary.getRange("D4:D5").format.horizontalAlignment = "center";
summary.getRange("F4:F5").format.horizontalAlignment = "center";

title(phases, "Ringkasan observasi per tahap", "H");
phases.getRange("A3").values = [["Waktu total adalah jumlah observeMs dari GLD, bukan lama tahap wall-clock; DAC, jeda dan overhead lain tidak termasuk."]];
phases.getRange("A4").values = [["Stable=0 menandai observasi yang tidak memenuhi toleransi stabilitas; bukan otomatis berarti kanal gagal."]];
phases.getRange("A6:H6").values = [["CH", "Sensor", "Tahap", "Jumlah observasi", "Total observe (detik)", "Rata-rata (ms)", "Stable=1", "Rentang observe (ms)"]];
header(phases.getRange("A6:H6"));
const phaseRows = data.stages.map((x) => [x.ch,x.sensor,x.stage,x.count,x.observeMs/1000,null,x.stable,`${x.minMs}–${x.maxMs}`]);
phases.getRangeByIndexes(6,0,phaseRows.length,8).values = phaseRows;
phases.getRangeByIndexes(6,5,phaseRows.length,1).formulas = data.stages.map((_,i) => [`=E${i+7}*1000/D${i+7}`]);
phases.getRangeByIndexes(6,4,phaseRows.length,2).setNumberFormat("0.00");
body(phases, `A7:H${phaseRows.length+6}`);
phases.getRange("A:A").format.columnWidth = 8;
phases.getRange("B:C").format.columnWidth = 18;
phases.getRange("D:H").format.columnWidth = 23;
phases.getRange("A6:H6").format.horizontalAlignment = "center";
phases.getRangeByIndexes(6,0,phaseRows.length,2).format.horizontalAlignment = "center";
phases.getRangeByIndexes(6,6,phaseRows.length,2).format.horizontalAlignment = "center";
phases.freezePanes.freezeRows(6);

title(steps, "Observasi per langkah DAC", "I");
steps.getRange("A3").values = [["Waktu WIB hanya tersedia untuk log yang ditangkap langsung; data historis tidak memiliki timestamp per baris."]];
steps.getRange("A4:I4").values = [["Urutan log", "CH", "Sensor", "Tahap", "Kode DAC", "Stable", "Spread (V)", "Observe (ms)", "Waktu PC WIB"]];
header(steps.getRange("A4:I4"));
const rawRows = data.observations.map((x) => [x.sequence,x.ch,x.sensor,x.stage,x.code,x.stable,x.spreadV,x.observeMs,textTime(x.observedAt)]);
steps.getRangeByIndexes(4,0,rawRows.length,9).values = rawRows;
body(steps, `A5:I${rawRows.length+4}`);
steps.getRangeByIndexes(4,6,rawRows.length,1).setNumberFormat("0.000000000");
steps.getRangeByIndexes(4,8,rawRows.length,1).setNumberFormat("hh:mm:ss.000");
steps.getRange("A:B").format.columnWidth = 13;
steps.getRange("C:D").format.columnWidth = 18;
steps.getRange("E:F").format.columnWidth = 13;
steps.getRange("G:I").format.columnWidth = 20;
steps.getRange("A4:I4").format.horizontalAlignment = "center";
steps.getRangeByIndexes(4,1,rawRows.length,2).format.horizontalAlignment = "center";
steps.getRangeByIndexes(4,4,rawRows.length,2).format.horizontalAlignment = "center";
steps.freezePanes.freezeRows(4);

wb.recalculate();
console.log("SUMMARY", (await wb.inspect({kind:"table",range:"Ringkasan!A8:L16",include:"values,formulas",tableMaxRows:10,tableMaxCols:12})).ndjson);
console.log("ERRORS", (await wb.inspect({kind:"match",searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",options:{useRegex:true,maxResults:50},summary:"formula scan"})).ndjson);
for (const [sheetName, range, file] of [["Ringkasan","A1:L19","summary"],["Tahapan","A1:H18","phases"],["Per langkah","A1:I18","steps"]]) {
  const img = await wb.render({sheetName,range,scale:1,format:"png"});
  await fs.writeFile(`${base}/${file}.png`,new Uint8Array(await img.arrayBuffer()));
}
await fs.mkdir(outDir,{recursive:true});
const workbookFile = await SpreadsheetFile.exportXlsx(wb);
await workbookFile.save(outFile);
console.log(`EXPORTED=${outFile}`);
