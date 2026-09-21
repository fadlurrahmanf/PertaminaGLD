import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const presentation = await PresentationFile.importPptx(
  await FileBlob.load("D:/Github/PertaminaGLD/tmp/presentation-confirmed-revision/template-starter.pptx"),
);
const snapshot = await presentation.inspect({ kind: "textbox,table", search: "Kesiapan Sistem", maxChars: 4000 });
const record = snapshot.ndjson.split(/\r?\n/).filter(Boolean).map(JSON.parse).find((item) => item.kind === "textbox");
const target = presentation.resolve(record.id);
const tableSnapshot = await presentation.inspect({ kind: "table", search: "Keputusan meeting", maxChars: 4000 });
const tableRecord = tableSnapshot.ndjson.split(/\r?\n/).filter(Boolean).map(JSON.parse).find((item) => item.kind === "table");
const table = presentation.resolve(tableRecord.id);
process.stdout.write(JSON.stringify({
  record,
  targetKeys: Object.getOwnPropertyNames(target),
  targetProtoKeys: Object.getOwnPropertyNames(Object.getPrototypeOf(target)),
  textType: typeof target.text,
  textKeys: target.text && typeof target.text === "object" ? Object.getOwnPropertyNames(target.text) : [],
  textProtoKeys: target.text && typeof target.text === "object" ? Object.getOwnPropertyNames(Object.getPrototypeOf(target.text)) : [],
  tableKeys: Object.getOwnPropertyNames(table),
  tableProtoKeys: Object.getOwnPropertyNames(Object.getPrototypeOf(table)),
  cellsKeys: table.cells ? Object.getOwnPropertyNames(table.cells) : [],
  cellsProtoKeys: table.cells ? Object.getOwnPropertyNames(Object.getPrototypeOf(table.cells)) : [],
}, null, 2));
