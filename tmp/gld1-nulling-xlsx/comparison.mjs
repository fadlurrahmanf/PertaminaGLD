import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "D:/Github/PertaminaGLD";
const out = `${root}/outputs/gld1-nulling-eksperimen-20261019`;
const data = JSON.parse(await fs.readFile(`${root}/tmp/gld1-nulling-comparison-20261019.json`, "utf8"));
const wb = Workbook.create();
const summary = wb.worksheets.add("Perbandingan");
const stages = wb.worksheets.add("Tahapan");
const raw = wb.worksheets.add("Observasi");
for (const sheet of [summary, stages, raw]) sheet.showGridLines = false;
function head(range) { range.format = { fill: "#17324A", font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" }, verticalAlignment: "center" }; }
function title(sheet, text) { sheet.getRange("A2").values = [[text]]; sheet.getRange("A2").format.font = { name: "Arial", size: 14, bold: true, color: "#17324A" }; }

title(summary, "Perbandingan nulling GLD1 Model 1 di COM7");
summary.getRange("A4:F4").values = [["Durasi service", "Sebelum (detik)", "Eksperimen (detik)", "Hemat (detik)", "Hemat (%)", "Hasil firmware"]];
head(summary.getRange("A4:F4"));
summary.getRange("A5:F5").values = [["8 kanal", data.baseline.serviceSeconds, data.experiment.serviceSeconds, null, null, "8/8 OK; profil 3"]];
summary.getRange("D5:E5").formulas = [["=B5-C5", "=(B5-C5)/B5"]];
summary.getRange("B5:D5").setNumberFormat("0.000");
summary.getRange("E5").setNumberFormat("0.0%");
summary.getRange("F5").format.horizontalAlignment = "center";
summary.getRange("A7").values = [["Satu run per firmware; PASS 8/8 bukan bukti akurasi. Pembanding independen dan uji berulang belum tersedia."]];
summary.getRange("A8").values = [["Durasi adalah waktu penerimaan log pada PC; eksperimen memakai polling sekitar 0,25 detik."]];
summary.getRange("A9").values = [["Sumber: rekaman serial GLD1 sebelum dan sesudah firmware eksperimen, 19 Oktober 2026."]];
summary.getRange("A11:I11").values = [["Sensor", "Sebelum (s)", "Eksperimen (s)", "Hemat (s)", "DAC lama", "DAC baru", "Akhir lama (V)", "Akhir baru (V)", "Hasil baru"]];
head(summary.getRange("A11:I11"));
const compareRows = Array.from({length: 8}, (_, i) => {
  const a = data.baseline.channels[String(i)], b = data.experiment.channels[String(i)];
  return [a?.sensor ?? b?.sensor ?? "", a?.seconds ?? null, b?.seconds ?? null, null,
    a?.dac ?? null, b?.dac ?? null, a?.after ?? null, b?.after ?? null, b?.result ?? "BELUM"];
});
summary.getRange("A12:I19").values = compareRows;
summary.getRange("D12:D19").formulas = compareRows.map((_,i) => [`=B${i+12}-C${i+12}`]);
summary.getRange("B12:D19").setNumberFormat("0.000");
summary.getRange("G12:H19").setNumberFormat("0.000000000");
summary.getRange("A21").values = [["DAC dan tegangan dapat berubah karena kondisi sensor/waktu; perbedaan tidak menentukan akurasi."]];
summary.getRange("A22").values = [["Stable=0: toleransi stabilitas observasi tidak terpenuhi; bukan otomatis gagal atau bukti kalibrasi benar."]];
summary.getRange("A:A").format.columnWidth = 18;
summary.getRange("B:E").format.columnWidth = 20;
summary.getRange("F:F").format.columnWidth = 22;
summary.getRange("G:H").format.columnWidth = 23;
summary.getRange("I:I").format.columnWidth = 17;
summary.getRange("I12:I19").format.horizontalAlignment = "center";

title(stages, "Waktu observasi per tahap");
stages.getRange("A4").values = [["Jumlah observeMs berasal dari perangkat dan tidak termasuk semua overhead; bukan durasi wall-clock tahap."]];
stages.getRange("A6:G6").values = [["Firmware", "CH", "Sensor", "Tahap", "Observasi", "Observe (detik)", "Stable=1"]];
head(stages.getRange("A6:G6"));
const phaseRows = [["Sebelum", data.baseline], ["Eksperimen", data.experiment]].flatMap(([name, run]) =>
  run.stages.map(s => [name, s.ch, s.sensor, s.stage, s.count, s.observeMs/1000, s.stable]));
stages.getRangeByIndexes(6, 0, phaseRows.length, 7).values = phaseRows;
stages.getRange("F:F").setNumberFormat("0.000");
stages.getRange("A:G").format.columnWidth = 20;
stages.getRangeByIndexes(6, 1, phaseRows.length, 1).format.horizontalAlignment = "center";
stages.freezePanes.freezeRows(6);

title(raw, "Observasi DAC tiap langkah");
raw.getRange("A4").values = [["Timestamp kosong berarti log historis tidak memiliki waktu per baris. Waktu lainnya adalah penerimaan PC."]];
raw.getRange("A6:J6").values = [["Firmware", "Urutan", "CH", "Sensor", "Tahap", "DAC", "Stable", "Spread (V)", "Observe (ms)", "Waktu PC WIB"]];
head(raw.getRange("A6:J6"));
const wibSerial = stamp => stamp ? Date.parse(`${stamp.slice(0, 23)}Z`) / 86400000 + 25569 : null;
const rawRows = [["Sebelum", data.baseline], ["Eksperimen", data.experiment]].flatMap(([name, run]) =>
  run.observations.map(o => [name, o.sequence, o.ch, o.sensor, o.stage, o.code, o.stable, o.spreadV, o.observeMs, wibSerial(o.stamp)]));
raw.getRangeByIndexes(6, 0, rawRows.length, 10).values = rawRows;
raw.getRange("H:H").setNumberFormat("0.000000000");
raw.getRange("A:I").format.columnWidth = 17;
raw.getRange("J:J").format.columnWidth = 33;
raw.getRangeByIndexes(6, 9, rawRows.length, 1).setNumberFormat("yyyy-mm-dd hh:mm:ss.000");
raw.getRangeByIndexes(6, 2, rawRows.length, 1).format.horizontalAlignment = "center";
raw.freezePanes.freezeRows(6);

wb.recalculate();
console.log((await wb.inspect({kind:"table", range:"Perbandingan!A4:I19", include:"values,formulas", tableMaxRows:20, tableMaxCols:9})).ndjson);
const firstExperimentRow = 7 + data.baseline.observations.length;
console.log((await wb.inspect({kind:"table", range:`Observasi!A${firstExperimentRow}:J${firstExperimentRow+2}`, include:"values", tableMaxRows:3, tableMaxCols:10})).ndjson);
console.log((await wb.inspect({kind:"match", searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options:{useRegex:true,maxResults:50}})).ndjson);
await fs.mkdir(out, {recursive:true});
for (const [name, range, image] of [["Perbandingan","A1:I22","perbandingan"],["Tahapan","A1:G18","tahapan"],["Observasi","A1:J18","observasi"]]) {
  const blob = await wb.render({sheetName:name, range, scale:1, format:"png"});
  await fs.writeFile(`${root}/tmp/gld1-nulling-xlsx/${image}-eksperimen.png`, new Uint8Array(await blob.arrayBuffer()));
}
const experimentPreview = await wb.render({sheetName:"Observasi", range:`A${firstExperimentRow}:J${firstExperimentRow+7}`, scale:1, format:"png"});
await fs.writeFile(`${root}/tmp/gld1-nulling-xlsx/observasi-eksperimen-live.png`, new Uint8Array(await experimentPreview.arrayBuffer()));
const file = await SpreadsheetFile.exportXlsx(wb);
await file.save(`${out}/Perbandingan_Nulling_GLD1.xlsx`);
console.log(`EXPORTED=${out}/Perbandingan_Nulling_GLD1.xlsx`);
