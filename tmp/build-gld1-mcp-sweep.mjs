import fs from 'node:fs/promises';
import sharp from 'sharp';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const root = 'D:/Github/PertaminaGLD';
const templatePath = `${root}/outputs/gld1-mcp-sweep-20261020/gld1_mcp_response.xlsx`;
const outputDir = `${root}/outputs/gld1-mcp-sweep-20261021`;
const outputPath = `${outputDir}/gld1_mcp_response.xlsx`;
const points = JSON.parse(await fs.readFile(`${outputDir}/nulling-measured-points.json`, 'utf8'));
const sensorOrder = ['MQ8', 'MQ135', 'MQ3', 'MQ5', 'MQ4', 'MQ7', 'MQ6', 'MQ2'];
const profileId = 5;
const phaseLabel = { Baseline: 'A-Baseline', Exponential: 'B-Exponential', Binary: 'C-Binary', Confirm: 'D-Confirm' };
let workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(templatePath));

for (const sensor of sensorOrder) {
  const sourceRows = points.filter((item) => item.sensor === sensor).sort((a, b) => a.sequence - b.sequence);
  const baseline = sourceRows[0]?.baselineV ?? null;
  const target = sourceRows[0]?.targetV ?? null;
  const selected = sourceRows.find((item) => item.selected) ?? null;
  const firstCrossing = sourceRows.find((item) => item.crossing) ?? null;
  const sheet = workbook.worksheets.getItem(sensor);
  const lastDataRow = 7 + sourceRows.length;

  // Preserve the user-maintained stage labels and their filter/sort workflow.
  sheet.getRange('A3:B3').values = [['Kanal', sourceRows[0]?.channel ?? 'Tidak ada']];
  sheet.getRange('D3:E3').values = [['Crossing pertama DAC', firstCrossing?.dacCode ?? 'Tidak ada']];
  sheet.getRange('A4:B4').values = [['Baseline rata-rata (V)', baseline ?? 'Tidak ada']];
  sheet.getRange('D4:E4').values = [['Tegangan crossing (V)', firstCrossing?.voltageV ?? 'Tidak ada']];
  sheet.getRange('A6:B6').values = [['MCP dipilih', selected?.dacCode ?? 'Tidak ada']];
  sheet.getRange('D6:E6').values = [['Status kandidat', selected ? `Profil ${profileId}: terpilih dari confirm` : 'Tidak ada kandidat valid']];
  sheet.getRange('A6').format.font = { name: 'Aptos', size: 10, bold: true, color: '#152B36' };
  sheet.getRange('D6').format.font = { name: 'Aptos', size: 10, bold: true, color: '#152B36' };
  sheet.getRange('B6').format = { fill: '#FEF3C7', font: { name: 'Aptos', size: 10, bold: true, color: '#92400E' } };
  sheet.getRange('A:A').format.columnWidth = 16;
  sheet.getRange('A5:B5').values = [['Target Y / threshold (V)', target ?? 'Tidak ada']];
  sheet.getRange('G3:H3').values = [['Selisih ke target Y (V)', selected ? selected.voltageV - target : 'Tidak ada']];
  sheet.getRange('G3').format.font = { name: 'Aptos', size: 10, bold: true, color: '#152B36' };
  if (selected) {
    sheet.getRange('H3').format = { fill: '#FEF3C7', font: { name: 'Aptos', size: 10, bold: true, color: '#92400E' }, numberFormat: '0.000000000' };
  }

  const tableRows = sourceRows.map((item) => [
    item.sequence, phaseLabel[item.phase], item.dacCode, item.voltageV, item.targetV,
    item.voltageV - baseline, item.voltageV - item.targetV, item.samples,
    item.valid ? 'Ya' : 'Tidak', item.crossing ? 'Ya' : null,
  ]);
  sheet.getRange('A8:J200').clear({ applyTo: 'contents' });
  sheet.getRange(`A8:J${lastDataRow}`).values = tableRows;
  for (let row = 8; row <= lastDataRow; row += 1) {
    sheet.getRange(`A${row}:J${row}`).format = {
      fill: row % 2 === 0 ? '#D7F0FA' : '#F7FCFE',
      font: { name: 'Aptos', size: 10, color: '#152B36' },
    };
  }
  if (selected) {
    const rowNumber = sourceRows.findIndex((item) => item.selected) + 8;
    sheet.getRange(`A${rowNumber}:J${rowNumber}`).format = {
      fill: '#FEF3C7',
      font: { name: 'Aptos', size: 10, bold: true, color: '#78350F' },
    };
  }

  const chartRows = [...sourceRows].sort((a, b) => (a.dacCode - b.dacCode) || (a.sequence - b.sequence));
  const helperRows = chartRows.map((item) => [item.dacCode, item.voltageV, target, null]);
  const helperFirstRow = 8;
  const helperLastRow = helperFirstRow + helperRows.length - 1;
  sheet.getRange('X7:AA7').values = [['Kode MCP', 'Tegangan terukur (V)', 'Y = Threshold (V)', 'X MCP terpilih']];
  sheet.getRange(`X${helperFirstRow}:AA${helperLastRow}`).values = helperRows;
  sheet.getRange(`Y${helperFirstRow}:AA${helperLastRow}`).format.numberFormat = '0.000000000';

  // Rebuild only this workbook's generated drawing.  A line-chart series cannot
  // hold two values at one category, so it renders the selected-MCP indicator
  // diagonally.  Rasterize the native chart and overlay one exact vertical line.
  sheet.charts.deleteAll();
  sheet.shapes.deleteAll();
  for (const image of [...sheet.images.items]) {
    image.delete();
  }
  const chart = sheet.charts.add('line', sheet.getRange(`X7:Z${helperLastRow}`));
  chart.title = selected ? `${sensor}: respons MCP dan Y = threshold (X = ${selected.dacCode})` : `${sensor}: respons MCP dan Y = threshold`;
  chart.titleTextStyle.typeface = 'Aptos';
  chart.titleTextStyle.fontSize = 12;
  chart.legend = { position: 'top', textStyle: { typeface: 'Aptos', fontSize: 9 } };
  chart.xAxis = { axisType: 'textAxis', title: { text: 'Kode MCP' }, textStyle: { typeface: 'Aptos', fontSize: 9 } };
  chart.yAxis = { title: { text: 'Tegangan (V)' }, numberFormatCode: '0.000', numberFormatSourceLinked: false, textStyle: { typeface: 'Aptos', fontSize: 9 } };
  chart.series.items[0].line = { fill: '#0F766E', style: 'solid', width: 2 };
  chart.applySeriesStyle(0, { marker: { symbol: 'circle', size: 4, fill: '#0F766E' } });
  chart.series.items[1].line = { fill: '#DC2626', style: 'dashed', width: 2 };
  chart.setPosition('L8', 'T31');

}

// chartToImage resolves charts only after a native XLSX round-trip.
const intermediatePath = `${outputDir}/.gld1_mcp_chart_intermediate.xlsx`;
const intermediateXlsx = await SpreadsheetFile.exportXlsx(workbook);
await intermediateXlsx.save(intermediatePath);
workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(intermediatePath));

for (const sensor of sensorOrder) {
  const sourceRows = points.filter((item) => item.sensor === sensor).sort((a, b) => a.sequence - b.sequence);
  const selected = sourceRows.find((item) => item.selected) ?? null;
  const chartRows = [...sourceRows].sort((a, b) => (a.dacCode - b.dacCode) || (a.sequence - b.sequence));
  const sheet = workbook.worksheets.getItem(sensor);
  const chart = sheet.charts.items[0];
  const chartImage = await workbook.chartToImage(sheet.index, chart.id);
  const overlay = selected ? (() => {
    const selectedIndex = chartRows.findIndex((item) => item.sequence === selected.sequence);
    // chartToImage emits a consistent 531 x 456 px chart; its plot area is
    // x=63..516 and y=62..411.  Category positions are evenly spaced.
    const x = Math.round(63 + ((selectedIndex / (chartRows.length - 1)) * (516 - 63)));
    return Buffer.from(`
      <svg xmlns="http://www.w3.org/2000/svg" width="${chartImage.widthPx}" height="${chartImage.heightPx}">
        <line x1="${x}" y1="62" x2="${x}" y2="411" stroke="#A855F7" stroke-width="2"/>
        <line x1="350" y1="42" x2="367" y2="42" stroke="#A855F7" stroke-width="2"/>
        <text x="372" y="45" font-family="Aptos, Arial, sans-serif" font-size="9" fill="#4C1D95">X = MCP terpilih</text>
      </svg>`);
  })() : null;
  const finalChartPng = await sharp(Buffer.from(chartImage.bytes))
    .composite(overlay ? [{ input: overlay, top: 0, left: 0 }] : [])
    .png()
    .toBuffer();
  sheet.charts.deleteAll();
  sheet.images.add({
    blob: new Uint8Array(finalChartPng),
    contentType: 'image/png',
    anchor: { from: { row: 7, col: 11 }, extent: { widthPx: chartImage.widthPx, heightPx: chartImage.heightPx } },
  });
}

workbook.recalculate();
const inspection = await workbook.inspect({
  kind: 'table', range: 'MQ8!A1:J18', include: 'values,formulas', tableMaxRows: 18, tableMaxCols: 10,
});
console.log(inspection.ndjson);
const errors = await workbook.inspect({
  kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',
  options: { useRegex: true, maxResults: 50 }, summary: 'formula error scan',
});
console.log(errors.ndjson);
const preview = await workbook.render({ sheetName: 'MQ8', range: 'A1:T30', scale: 1.5, format: 'png' });
await fs.writeFile(`${outputDir}/preview-mq8.png`, new Uint8Array(await preview.arrayBuffer()));
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
