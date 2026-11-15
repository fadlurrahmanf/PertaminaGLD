import fs from 'node:fs/promises';
import {SpreadsheetFile} from '@oai/artifact-tool';
process.on('uncaughtException',e=>{console.error(String(e.message||e).slice(0,3000));process.exit(1);});
const b=await fs.readFile('layout_snapshot.bin');
const wb=await SpreadsheetFile.importXlsx(b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength));
for(const [s,r,p] of [['Summary','A1:Q30','final_layout_summary.png'],['Raw Last','A1:J7','final_layout_raw.png']]){
 const img=await wb.render({sheetName:s,range:r,scale:1});await fs.writeFile(p,new Uint8Array(await img.arrayBuffer()));console.log('Rendered',p);
}
