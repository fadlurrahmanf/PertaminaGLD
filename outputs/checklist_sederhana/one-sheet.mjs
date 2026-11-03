import fs from 'node:fs/promises';
import {Workbook, SpreadsheetFile} from '@oai/artifact-tool';
const root='D:/Github/PertaminaGLD/outputs/checklist_sederhana';
const source=await fs.readFile(root+'/compact.mjs','utf8');
const definition=source.slice(source.indexOf('const groups='),source.indexOf('\nconst wb=')).replace('const groups=','return ');
const groups=Function(definition)();
const data=JSON.parse(await fs.readFile(root+'/data.json','utf8'));const all=Object.values(data).flat();
const wb=Workbook.create();const s=wb.worksheets.add('Checklist');s.showGridLines=false;
s.getRange('A1:D1').merge();s.getRange('A1').values=[['CHECKLIST INSTALASI RU IV']];
s.getRange('A2:D2').merge();s.getRange('A2').values=[['Status mengikuti file asal per 28 Oktober 2026. Detail dan bukti tersedia pada file asal.']];
let row=4, seen=[];
for(const [name,items] of Object.entries(groups)){
 s.getRange(`A${row}:D${row}`).merge();s.getRange(`A${row}`).values=[[name.toUpperCase()]];s.getRange(`A${row}:D${row}`).format.fill='#DCE9F0';s.getRange(`A${row}:D${row}`).format.font.bold=true;s.getRange(`A${row}:D${row}`).format.rowHeight=24;row++;
 s.getRange(`A${row}:D${row}`).values=[['No','Yang dicek','Pihak','Status']];s.getRange(`A${row}:D${row}`).format.fill='#244761';s.getRange(`A${row}:D${row}`).format.font.color='#FFFFFF';s.getRange(`A${row}:D${row}`).format.font.bold=true;s.getRange(`A${row}:D${row}`).format.rowHeight=22;row++;
 const start=row;const out=Object.entries(items).map(([id,label])=>{const r=all.find(x=>x[0]===id);if(!r)throw Error(id);seen.push(id);return [id,label,id.startsWith('L-')?'LGU':'RU IV',r[6]]});
 s.getRange(`A${row}:D${row+out.length-1}`).values=out;row+=out.length;s.getRange(`A${start}:D${row-1}`).format.rowHeight=24;s.getRange(`B${start}:B${row-1}`).format.wrapText=true;
 s.getRange(`D${start}:D${row-1}`).dataValidation={rule:{type:'list',values:['Belum','Proses','Menunggu','Selesai','N.A.']}};row+=2;
}
if(seen.length!==43||new Set(seen).size!==43)throw Error('Item mismatch');
s.getRange(`A1:D${row}`).format.font.name='Arial';s.getRange(`A1:D${row}`).format.font.size=11;s.getRange('A1').format.font.bold=true;s.getRange('A1').format.font.size=14;
for(const [c,w] of Object.entries({A:10,B:65,C:12,D:16}))s.getRange(`${c}:${c}`).format.columnWidth=w;
wb.recalculate();const p=await wb.render({sheetName:'Checklist',range:'A1:D20',scale:1,format:'png'});await fs.writeFile(root+'/satu-sheet.png',new Uint8Array(await p.arrayBuffer()));
const f=await SpreadsheetFile.exportXlsx(wb);await f.save(root+'/Checklist_Satu_Sheet_Per_Komponen.xlsx');console.log('43 distinct items; 8 separate tables; 1 sheet');
