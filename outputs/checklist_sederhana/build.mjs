import fs from 'node:fs/promises';
import {Workbook, SpreadsheetFile} from '@oai/artifact-tool';
const data=JSON.parse(await fs.readFile('outputs/checklist_sederhana/data.json','utf8'));
const wb=Workbook.create();
for (const [name,rows] of Object.entries(data)) {
 const s=wb.worksheets.add(name); s.showGridLines=false;
 s.getRange('A1:H1').merge(); s.getRange('A1').values=[[name+' — Checklist Instalasi RU IV']];
 s.getRange('A2:H2').merge(); s.getRange('A2').values=[['Status dan bukti mengikuti file asal per 28 Oktober 2026. Isi PIC, tanggal, bukti, dan catatan sesuai hasil pemeriksaan.']];
 s.getRange('A4:H4').values=[['No','Pemeriksaan (termasuk spesifikasi)','Terkait','Status','PIC','Tanggal cek','Bukti','Catatan']];
 const out=rows.map(r=>[r[0],`${r[2]} — ${r[4]}\nSpesifikasi: ${r[3]}`,r[5],r[6],r[7],r[8],r[9],r[10]]);
 s.getRange(`A5:H${4+out.length}`).values=out;
 s.getRange(`A1:H${4+out.length}`).format.font.name='Arial'; s.getRange(`A1:H${4+out.length}`).format.font.size=10;
 s.getRange('A1:H1').format.font.bold=true; s.getRange('A1:H1').format.font.size=14;
 s.getRange('A4:H4').format.fill='#244761'; s.getRange('A4:H4').format.font.color='#FFFFFF'; s.getRange('A4:H4').format.font.bold=true;
 s.getRange(`A5:H${4+out.length}`).format.wrapText=true; s.getRange(`A5:H${4+out.length}`).format.verticalAlignment='top';
 for (const [col,width] of Object.entries({A:10,B:65,C:24,D:13,E:12,F:18,G:48,H:38})) s.getRange(`${col}:${col}`).format.columnWidth=width;
 s.getRange(`A5:H${4+out.length}`).format.rowHeight=65;
 s.getRange(`D5:D${4+out.length}`).dataValidation={rule:{type:'list',values:['Belum','Proses','Menunggu','Selesai','N.A.']}};
 s.freezePanes.freezeRows(4);
}
wb.recalculate();
for(const name of Object.keys(data)) { const im=await wb.render({sheetName:name,range:'A1:H9',scale:1,format:'png'}); await fs.writeFile(`outputs/checklist_sederhana/${name}.png`,new Uint8Array(await im.arrayBuffer())); }
const file=await SpreadsheetFile.exportXlsx(wb); await file.save('outputs/checklist_sederhana/Checklist_Instalasi_Sederhana.xlsx');
console.log((await wb.inspect({kind:'sheet',include:'id,name'})).ndjson);
