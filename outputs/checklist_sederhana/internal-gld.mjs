import fs from 'node:fs/promises';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const root='D:/Github/PertaminaGLD/outputs/checklist_sederhana';
const groups={
'1. Board dan elektronik':['Versi / nama motherboard','Motherboard terpasang dan kondisi baik','Versi / nama sensor board','Sensor board terpasang dan kondisi baik','Konektor antar-board terpasang kuat','IC dan rangkaian pendukung lengkap / baik'],
'2. Sensor MQ':['MQ-2 terpasang, kondisi dan pembacaan','MQ-3 terpasang, kondisi dan pembacaan','MQ-4 terpasang, kondisi dan pembacaan','MQ-5 terpasang, kondisi dan pembacaan','MQ-6 terpasang, kondisi dan pembacaan','MQ-7 terpasang, kondisi dan pembacaan','MQ-8 terpasang, kondisi dan pembacaan','MQ-135 terpasang, kondisi dan pembacaan','Hasil uji sensor sesuai kriteria'],
'3. Catu daya':['Polaritas input benar','GLD menyala dengan 24 VDC','Tegangan internal sesuai','Unit berjalan normal selama pengujian'],
'4. LoRa dan antena':['Modul LoRa terpasang dan terdeteksi','Antena tersedia dan terpasang','Kabel / konektor antena kuat','GLD berhasil mengirim data','Data diterima CH'],
'5. Alarm':['Unit alarm tersedia dan terpasang','Kabel / konektor alarm terpasang','Alarm menyala saat diuji','Alarm mati kembali saat diuji'],
'6. Casing dan konektor':['Casing dan tutup lengkap','Baut dan seal tutup lengkap','Konektor internal terpasang kuat','Gland dan jalur masuk kabel lengkap','Sambungan menuju junction box siap'],
'7. Firmware dan konfigurasi':['Versi firmware','Model AI terpasang','Hasil boot / pesan error','Status IC / perangkat saat boot','ID GLD','Frekuensi dan konfigurasi LoRa','Konfigurasi sesuai CH tujuan']};
const wb=Workbook.create();const s=wb.worksheets.add('Internal GLD');s.showGridLines=false;
s.getRange('A1:E1').merge();s.getRange('A1').values=[['CHECKLIST INTERNAL GLD']];
s.getRange('A2').values=[['No. seri']];s.getRange('C2').values=[['Tanggal']];
s.getRange('A3:E3').merge();s.getRange('A3').values=[['Catat hasil atau nilai pengukuran. Gunakan N.A. jika tidak berlaku; jelaskan di kolom hasil.']];
s.getRange('A4:E4').merge();s.getRange('A4').values=[['Cocokkan versi board, daftar sensor, dan kriteria uji dengan unit yang diperiksa.']];
let row=6;for(const [name,items] of Object.entries(groups)){
 s.getRange(`A${row}:E${row}`).merge();s.getRange(`A${row}`).values=[[name.toUpperCase()]];s.getRange(`A${row}:E${row}`).format.fill='#DCE9F0';s.getRange(`A${row}:E${row}`).format.font.bold=true;s.getRange(`A${row}:E${row}`).format.rowHeight=24;row++;
 s.getRange(`A${row}:E${row}`).values=[['No','Yang dicek','Hasil / nilai','Status','Verifikator']];s.getRange(`A${row}:E${row}`).format.fill='#244761';s.getRange(`A${row}:E${row}`).format.font.color='#FFFFFF';s.getRange(`A${row}:E${row}`).format.font.bold=true;row++;
 const start=row;let n=1;const out=items.map(x=>[n++,x,null,null,null]);s.getRange(`A${row}:E${row+out.length-1}`).values=out;row+=out.length;s.getRange(`A${start}:E${row-1}`).format.rowHeight=26;s.getRange(`C${start}:E${row-1}`).format.fill='#FFF4D6';s.getRange(`D${start}:D${row-1}`).dataValidation={rule:{type:'list',values:['OK','Belum OK','Belum dicek','N.A.']}};row+=2;
}
s.getRange(`A1:E${row}`).format.font.name='Arial';s.getRange(`A1:E${row}`).format.font.size=11;s.getRange('A1').format.font.bold=true;s.getRange('A1').format.font.size=14;
for(const [c,w] of Object.entries({A:8,B:54,C:38,D:17,E:22}))s.getRange(`${c}:${c}`).format.columnWidth=w;
s.getRange('B2').format.fill='#FFF4D6';s.getRange('D2:E2').format.fill='#FFF4D6';s.freezePanes.freezeRows(4);wb.recalculate();
const p=await wb.render({sheetName:'Internal GLD',range:'A1:E19',scale:1,format:'png'});await fs.writeFile(root+'/internal-gld-preview.png',new Uint8Array(await p.arrayBuffer()));
const f=await SpreadsheetFile.exportXlsx(wb);await f.save(root+'/Checklist_Internal_GLD.xlsx');console.log('7 sections, 40 checks');
