import fs from 'node:fs/promises';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const root = 'D:/Github/PertaminaGLD';
const path = `${root}/outputs/gld1-mcp-sweep-20261021/gld1_mcp_response.xlsx`;
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(path));
for (const sensor of ['MQ7', 'MQ6', 'MQ2']) {
  const check = await workbook.inspect({
    kind: 'table', range: `${sensor}!A1:H7`, include: 'values,formulas', tableMaxRows: 7, tableMaxCols: 8,
  });
  console.log(check.ndjson);
  const preview = await workbook.render({ sheetName: sensor, range: 'A1:T31', scale: 1.2, format: 'png' });
  await fs.writeFile(`${root}/outputs/gld1-mcp-sweep-20261021/preview-${sensor.toLowerCase()}-latest.png`, new Uint8Array(await preview.arrayBuffer()));
}
