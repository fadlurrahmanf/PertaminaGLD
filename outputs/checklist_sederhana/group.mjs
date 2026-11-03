import fs from 'node:fs/promises';
import {Workbook, SpreadsheetFile} from '@oai/artifact-tool';
const root='D:/Github/PertaminaGLD/outputs/checklist_sederhana';
const data=JSON.parse(await fs.readFile(root+'/data.json','utf8'));
const groups={
 'Checklist LGU':{'GL Detector':['L-01','L-02','L-03','L-13','L-21'],'Cluster Head dan solar cell':['L-04','L-05','L-19'],'Gateway':['L-06','L-07'],'Router WiFi dan jaringan':['L-08','L-09','L-10'],'Server dan aplikasi':['L-11','L-22'],'Uji komunikasi dan sistem':['L-14','L-15','L-16','L-17','L-23'],'Persiapan, supervisi dan serah terima':['L-12','L-18','L-20','L-24']},
 'Checklist RU IV Pertamina':{'GL Detector dan daya':['R-01','R-02','R-03','R-04','R-05','R-06','R-07'],'Cluster Head dan solar cell':['R-08','R-09'],'Gateway':['R-10'],'UPS dan outlet':['R-11','R-12'],'Server dan jaringan':['R-13','R-14','R-15','R-16'],'Izin, commissioning dan serah terima':['R-17','R-18','R-19']}
};
const wb=Workbook.create();
for (const [name,sections] of Object.entries(groups)) {
 const s=wb.worksheets.add(name); s.showGridLines=false;
 s.getRange('A1:H1').merge(); s.getRange('A1').values=[[name+' — Checklist Instalasi RU IV']];
 s.getRange('A2:H2').merge(); s.getRange('A2').values=[['Status dan bukti mengikuti file asal per 28 Oktober 2026. Perbarui sesuai hasil pemeriksaan.']];
 let row=4; const all=data[name]; const seen=[];
 for(const [label,ids] of Object.entries(sections)) {
  s.getRange(`A${row}:H${row}`).merge(); s.getRange(`A${row}`).values=[[label]]; s.getRange(`A${row}:H${row}`).format.fill='#DCE9F0'; s.getRange(`A${row}:H${row}`).format.font.bold=true; s.getRange(`A${row}:H${row}`).format.rowHeight=22; row++;
  s.getRange(`A${row}:H${row}`).values=[['No','Pemeriksaan (termasuk spesifikasi)','Terkait','Status','PIC','Tanggal cek','Bukti','Catatan']]; s.getRange(`A${row}:H${row}`).format.fill='#244761'; s.getRange(`A${row}:H${row}`).format.font.color='#FFFFFF'; s.getRange(`A${row}:H${row}`).format.font.bold=true; row++;
  const start=row; const out=ids.map(id=>{const r=all.find(x=>x[0]===id); if(!r) throw Error(id); seen.push(id); return [r[0],`${r[2]} — ${r[4]}\nSpesifikasi: ${r[3]}`,r[5],r[6],r[7],r[8],r[9],r[10]]});
  s.getRange(`A${row}:H${row+out.length-1}`).values=out; row+=out.length;
  s.getRange(`A${start}:H${row-1}`).format.wrapText=true; s.getRange(`A${start}:H${row-1}`).format.verticalAlignment='top'; s.getRange(`A${start}:H${row-1}`).format.rowHeight=65;
  s.getRange(`D${start}:D${row-1}`).dataValidation={rule:{type:'list',values:['Belum','Proses','Menunggu','Selesai','N.A.']}}; row++;
 }
 if(seen.length!==all.length || new Set(seen).size!==all.length) throw Error('Item mismatch '+name);
 s.getRange(`A1:H${row}`).format.font.name='Arial'; s.getRange(`A1:H${row}`).format.font.size=10; s.getRange('A1').format.font.size=14; s.getRange('A1').format.font.bold=true;
 for (const [col,width] of Object.entries({A:10,B:65,C:24,D:13,E:12,F:18,G:48,H:38})) s.getRange(`${col}:${col}`).format.columnWidth=width;
}
wb.recalculate();
for(const name of Object.keys(groups)){const p=await wb.render({sheetName:name,range:'A1:H15',scale:1,format:'png'});await fs.writeFile(`${root}/${name}-group.png`,new Uint8Array(await p.arrayBuffer()));}
const f=await SpreadsheetFile.exportXlsx(wb); await f.save(root+'/Checklist_Instalasi_Per_Device.xlsx');
console.log('Verified 24 LGU and 19 RU IV items, each once.');
