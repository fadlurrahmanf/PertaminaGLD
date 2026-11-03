import fs from 'node:fs/promises';
import {Workbook, SpreadsheetFile} from '@oai/artifact-tool';
const root='D:/Github/PertaminaGLD/outputs/checklist_sederhana';
const source=await fs.readFile(root+'/compact.mjs','utf8');
const definition=source.slice(source.indexOf('const groups='),source.indexOf('\nconst wb=')).replace('const groups=','return ');
const groups=Function(definition)();
const data=JSON.parse(await fs.readFile(root+'/data.json','utf8')); const all=Object.values(data).flat();
const wb=Workbook.create();const s=wb.worksheets.add('Checklist');s.showGridLines=false;
s.getRange('A1:J1').merge();s.getRange('A1').values=[['CHECKLIST KESIAPAN INSTALASI RU IV']];
s.getRange('A2:J2').merge();s.getRange('A2').values=[['Status lama per 28 Oktober 2026; verifikasi ulang sebelum dinyatakan selesai. Detail dan BOM: file sumber.']];
s.getRange('A3:J3').merge();s.getRange('A3').values=[['Proses: sedang dikerjakan atau belum memenuhi seluruh syarat. Selesai: syarat terpenuhi, diverifikasi dan ada bukti.']];
s.getRange('A4:J4').merge();s.getRange('A4').values=[['Jumlah diisi untuk barang; cadangan di luar jumlah butuh. Bukti: nomor form, foto, atau dokumen. Kosong = belum diisi.']];
let row=6,seen=[];
function table(name,rows){
 s.getRange(`A${row}:J${row}`).merge();s.getRange(`A${row}`).values=[[name.toUpperCase()]];s.getRange(`A${row}:J${row}`).format.fill='#DCE9F0';s.getRange(`A${row}:J${row}`).format.font.bold=true;s.getRange(`A${row}:J${row}`).format.rowHeight=24;row++;
 s.getRange(`A${row}:J${row}`).values=[['No','Yang dicek / syarat selesai','Butuh','Ada','Cadangan','Pihak','Verifikator','Status','Target','Bukti / form']];s.getRange(`A${row}:J${row}`).format.fill='#244761';s.getRange(`A${row}:J${row}`).format.font.color='#FFFFFF';s.getRange(`A${row}:J${row}`).format.font.bold=true;s.getRange(`A${row}:J${row}`).format.rowHeight=25;row++;
 const start=row;s.getRange(`A${row}:J${row+rows.length-1}`).values=rows;row+=rows.length;
 s.getRange(`A${start}:J${row-1}`).format.rowHeight=30;s.getRange(`A${start}:J${row-1}`).format.wrapText=true;s.getRange(`C${start}:E${row-1}`).format.fill='#FFF4D6';s.getRange(`G${start}:G${row-1}`).format.fill='#FFF4D6';s.getRange(`I${start}:J${row-1}`).format.fill='#FFF4D6';
 s.getRange(`H${start}:H${row-1}`).dataValidation={rule:{type:'list',values:['Belum','Proses','Menunggu','Selesai','N.A.']}};row+=2;
}
for(const [name,items] of Object.entries(groups)){
 const rows=Object.entries(items).map(([id,label])=>{const r=all.find(x=>x[0]===id);if(!r)throw Error(id);seen.push(id);return [id,label,null,null,null,id.startsWith('L-')?'LGU':'RU IV',null,r[6],null,r[9]?'Lihat file asal':null]});
 if(name==='GL Detector') rows.push(['T-01','Dudukan kipas tersedia',null,null,null,null,null,'Belum',null,null]);
 table(name,rows);
}
table('Peralatan dan material instalasi',[
 ['T-02','Kabel instalasi tersedia',null,null,null,null,null,'Belum',null,null],
 ['T-03','Terminal tersedia',null,null,null,null,null,'Belum',null,null],
 ['T-04','Alat pemasangan diperiksa bersama tim',null,null,null,null,null,'Belum',null,null],
 ['T-05','Material kecil lain diperiksa bersama tim',null,null,null,null,null,'Belum',null,null]
]);
table('Simulasi dan administrasi',[
 ['T-06','Simulasi pemasangan awal hingga akhir',null,null,null,null,null,'Belum',null,null],
 ['T-07','Kekurangan hasil simulasi ditindaklanjuti',null,null,null,null,null,'Belum',null,null],
 ['T-08','Form pemeriksaan dan BOM disiapkan',null,null,null,null,null,'Belum',null,null],
 ['T-09','Progres dibagikan dan dipantau bersama',null,null,null,null,null,'Belum',null,null]
]);
if(seen.length!==43||new Set(seen).size!==43)throw Error('Source item mismatch');
s.getRange(`A1:J${row}`).format.font.name='Arial';s.getRange(`A1:J${row}`).format.font.size=10;s.getRange('A1').format.font.bold=true;s.getRange('A1').format.font.size=14;
for(const [c,w] of Object.entries({A:9,B:48,C:9,D:9,E:10,F:11,G:18,H:13,I:14,J:22}))s.getRange(`${c}:${c}`).format.columnWidth=w;
s.freezePanes.freezeRows(4);wb.recalculate();
const p=await wb.render({sheetName:'Checklist',range:'A1:J16',scale:1,format:'png'});await fs.writeFile(root+'/notulensi-preview.png',new Uint8Array(await p.arrayBuffer()));
const f=await SpreadsheetFile.exportXlsx(wb);await f.save(root+'/Checklist_Instalasi_Revisi_Notulensi.xlsx');console.log('43 source items plus 9 follow-up items; one sheet, separate tables.');
