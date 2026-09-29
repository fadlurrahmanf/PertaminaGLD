import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const input = await FileBlob.load("D:/Github/PertaminaGLD/outputs/utility-survey-20260924/Daftar_Kebutuhan_Utilitas_SRU_Revisi.xlsx");
const wb = await SpreadsheetFile.importXlsx(input);
const result = await wb.inspect({ kind: "table", range: "Daftar Kebutuhan!A1:K35", include: "values,formulas", tableMaxRows: 35, tableMaxCols: 11 });
console.log(result.ndjson);
