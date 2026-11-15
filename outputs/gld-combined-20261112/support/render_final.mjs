import fs from 'node:fs/promises';
import {SpreadsheetFile} from '@oai/artifact-tool';
const bytes=await fs.readFile('render_snapshot.bin');
console.log('Importing verified cached workbook for visual QA');
const wb=await SpreadsheetFile.importXlsx(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
console.log((await wb.inspect({kind:'sheet',include:'id,name',maxChars:1800})).ndjson);
for(const [name,range,out]of [
 ['Summary','A1:Q30','final_summary.png'],
 ['Summary','A34:Q216','final_combined.png'],
 ['Grafik Rekaman','A1:Q119','final_individual.png'],
 ['Raw Cuplikan','AO1:AV21','final_short_stats.png'],
]){
 console.log('Rendering',name,range);
 const img=await wb.render({sheetName:name,range,scale:1});
 await fs.writeFile(out,new Uint8Array(await img.arrayBuffer()));
 console.log('Saved',out);
}
