import fs from 'node:fs/promises';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const root='D:/Github/PertaminaGLD/outputs/checklist_sederhana';
const groups={'Casing':['Casing / badan','Tutup casing','Seal dan pengunci tutup'], 'Board CH':['Board CH','Baut board','Spacer board','Konektor pada board'], 'Antena dan kabel':['Antena LoRa','Dudukan antena','Kabel dan konektor antena'], 'Catu daya':['Kabel power','Konektor / terminal power','Gland kabel','Baterai, jika digunakan'], 'Solar cell dan pemasangan':['Panel solar cell','Kabel dan konektor panel','Bracket panel','Klem CH dan baut pemasangan'], 'Dokumentasi':['Foto perangkat dan komponen','ID / nomor seri perangkat','Referensi BOM / form verifikasi']};
const wb=Workbook.create();
for(const name of ['CH Kecil','CH Besar']){
 const s=wb.worksheets.add(name);s.showGridLines=false;s.getRange('A1:H1').merge();s.getRange('A1').values=[[`CHECKLIST HARDWARE ${name.toUpperCase()}`]];s.getRange('A2').values=[['ID CH']];s.getRange('C2').values=[['Tanggal']];s.getRange('B2').format.fill='#FFF4D6';s.getRange('D2').format.fill='#FFF4D6';
 s.getRange('A3:H3').merge();s.getRange('A3').values=[['Daftar awal: cocokkan item dan jumlah dengan unit / BOM. N.A. beri alasan.']];s.getRange('A4:H4').merge();s.getRange('A4').values=[['Contoh bersifat ilustrasi; catat kondisi dan referensi foto pada kolom hasil.']];let row=6;
 for(const [group,items] of Object.entries(groups)){
  s.getRange(`A${row}:H${row}`).merge();s.getRange(`A${row}`).values=[[group.toUpperCase()]];s.getRange(`A${row}:H${row}`).format.fill='#DCE9F0';s.getRange(`A${row}:H${row}`).format.font.bold=true;row++;
  s.getRange(`A${row}:H${row}`).values=[['No','Item','Contoh OK','Butuh','Ada','Kondisi / foto','Status','Verifikator']];s.getRange(`A${row}:H${row}`).format.fill='#244761';s.getRange(`A${row}:H${row}`).format.font.color='#FFFFFF';s.getRange(`A${row}:H${row}`).format.font.bold=true;row++;
  const from=row, vals=items.map((v,i)=>[i+1,v,group==='Dokumentasi'?'Referensi tersedia':'Jumlah sesuai; baik',null,null,null,null,null]);const end=row+vals.length-1;
  s.getRange(`A${from}:H${end}`).values=vals;s.getRange(`A${from}:H${end}`).format.rowHeight=28;s.getRange(`B${from}:C${end}`).format.wrapText=true;s.getRange(`C${from}:C${end}`).format.fill='#E9F2E7';s.getRange(`D${from}:H${end}`).format.fill='#FFF4D6';s.getRange(`G${from}:G${end}`).dataValidation={rule:{type:'list',values:['OK','Belum OK','Belum dicek','N.A.']}};row=end+3;
 }
 s.getRange(`A1:H${row}`).format.font.name='Arial';s.getRange(`A1:H${row}`).format.font.size=10;s.getRange('A1').format.font.size=14;s.getRange('A1').format.font.bold=true;
 for(const [c,w] of Object.entries({A:8,B:35,C:23,D:10,E:10,F:30,G:15,H:20}))s.getRange(`${c}:${c}`).format.columnWidth=w;s.freezePanes.freezeRows(4);
}
wb.recalculate();for(const name of ['CH Kecil','CH Besar']){const p=await wb.render({sheetName:name,range:'A1:H21',scale:1,format:'png'});await fs.writeFile(`${root}/${name}-preview.png`,new Uint8Array(await p.arrayBuffer()));}const f=await SpreadsheetFile.exportXlsx(wb);await f.save(root+'/Checklist_Hardware_CH_Kecil_Besar.xlsx');console.log('2 sheets, 6 grouped tables each');
