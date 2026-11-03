import fs from 'node:fs/promises';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const root='D:/Github/PertaminaGLD/outputs/checklist_sederhana';
const items=[];const add=(g, ...checks)=>checks.forEach(x=>items.push([g,x,null,null,null]));
add('Board','ID sensor board','Foto socket sensor','Sensor MQ terpasang kuat pada socket','Kondisi konektor antar-board','Kelengkapan komponen board GLD');
for(const n of ['MQ-2','MQ-3','MQ-4','MQ-5','MQ-6','MQ-7','MQ-8','MQ-135'])add('Sensor '+n,'Sensor terbaca','Nilai sensor responsif','Hasil nulling (V)');
add('Catu daya','Polaritas input benar','GLD menyala dengan 24 VDC','Tegangan suplai ESP (V)','Tegangan suplai komponen penting (V; sebutkan titik)','Lama uji ON dan kejadian mati / restart');
add('LoRa','LoRa begin berhasil','Antena LoRa terpasang','Sambungan antena ke board tidak longgar','Sambungan antena ke dudukan tidak longgar','Transmit GLD PASS; tidak terblokir','CH menerima data GLD');
add('Alarm','Alarm dan kabel terpasang','Konektor alarm ke board terpasang baik','Kontinuitas kabel alarm (buzzer)','Bunyi dan LED alarm berfungsi','Alarm dapat dikendalikan ON / OFF');
add('Casing','Main body dan tutup lengkap','Baut dan seal tiap sisi lengkap','Kondisi casing dan tutup tiap sisi');
add('Konektor dan kabel','Konektor daya ke board: kondisi dan kontinuitas','Konektor sensor board: kondisi dan kontinuitas','Konektor alarm: kondisi dan kontinuitas','Konektor antena di board: kondisi','Konektor antena di dudukan: kondisi','Gland: kelengkapan dan kekencangan','Jalur masuk kabel: kondisi','Kabel ke junction box tersedia; panjang (m)','Kontinuitas grounding casing ke ground board');
add('Firmware','Versi firmware yang di-upload','Hasil inferensi dan masalah','Hasil boot dan pesan error','Konfigurasi LoRa yang diterapkan','CH tujuan sudah diatur; catat ID CH');
const wb=Workbook.create();const sum=wb.worksheets.add('Ringkasan');sum.showGridLines=false;
sum.getRange('A1:G1').merge();sum.getRange('A1').values=[['RINGKASAN PEMERIKSAAN 3 GLD']];
sum.getRange('A2:G2').merge();sum.getRange('A2').values=[['Isi hasil, status, dan verifikator pada sheet tiap GLD. N.A. harus disertai alasan.']];
sum.getRange('A4:G4').values=[['Unit','ID GLD','OK','Belum OK','Belum dicek / kosong','N.A.','Butuh hasil / verifikator']];
sum.getRange('A4:G4').format.fill='#244761';sum.getRange('A4:G4').format.font.color='#FFFFFF';sum.getRange('A4:G4').format.font.bold=true;
const start=8,end=start+items.length-1;
for(let i=1;i<=3;i++){
 const name=`GLD ${i}`,s=wb.worksheets.add(name);s.showGridLines=false;s.getRange('A1:E1').merge();s.getRange('A1').values=[[`CHECKLIST INTERNAL ${name}`]];
 s.getRange('A2').values=[['ID GLD']];s.getRange('C2').values=[['Tanggal']];s.getRange('A3:E3').merge();s.getRange('A3').values=[['Catat hasil / nilai dan nama verifikator. N.A.: tulis alasan. Pengujian kontinuitas saat daya dilepas.']];
 s.getRange('A4:E4').merge();s.getRange('A4').values=[['Tegangan, durasi uji, kriteria respons sensor, dan titik ukur mengikuti prosedur yang disepakati.']];
 s.getRange('A7:E7').values=[['Kelompok','Yang dicek','Hasil / nilai','Status','Verifikator']];s.getRange('A7:E7').format.fill='#244761';s.getRange('A7:E7').format.font.color='#FFFFFF';s.getRange('A7:E7').format.font.bold=true;
 s.getRange(`A${start}:E${end}`).values=items;s.getRange(`A${start}:E${end}`).format.rowHeight=27;s.getRange(`B${start}:C${end}`).format.wrapText=true;s.getRange(`C${start}:E${end}`).format.fill='#FFF4D6';
 s.getRange(`D${start}:D${end}`).dataValidation={rule:{type:'list',values:['OK','Belum OK','Belum dicek','N.A.']}};
 s.getRange('B2').format.fill='#FFF4D6';s.getRange('D2').format.fill='#FFF4D6';
 s.getRange(`A1:E${end}`).format.font.name='Arial';s.getRange(`A1:E${end}`).format.font.size=10;s.getRange('A1').format.font.bold=true;s.getRange('A1').format.font.size=14;
 for(const [c,w] of Object.entries({A:18,B:52,C:35,D:15,E:21}))s.getRange(`${c}:${c}`).format.columnWidth=w;s.freezePanes.freezeRows(7);
 const r=i+4;sum.getRange(`A${r}`).values=[[name]];sum.getRange(`B${r}`).formulas=[[`=IF('${name}'!B2="","",'${name}'!B2)`]];
 sum.getRange(`C${r}:G${r}`).formulas=[[
 `=COUNTIF('${name}'!D${start}:D${end},"OK")`,
 `=COUNTIF('${name}'!D${start}:D${end},"Belum OK")`,
 `=COUNTBLANK('${name}'!D${start}:D${end})+COUNTIF('${name}'!D${start}:D${end},"Belum dicek")`,
 `=COUNTIF('${name}'!D${start}:D${end},"N.A.")`,
 `=COUNTIF('${name}'!D${start}:D${end},"OK")+COUNTIF('${name}'!D${start}:D${end},"N.A.")-COUNTIFS('${name}'!D${start}:D${end},"OK",'${name}'!C${start}:C${end},"<>",'${name}'!E${start}:E${end},"<>")-COUNTIFS('${name}'!D${start}:D${end},"N.A.",'${name}'!C${start}:C${end},"<>",'${name}'!E${start}:E${end},"<>")`
 ]];
}
sum.getRange('A10:G10').merge();sum.getRange('A10').values=[['Butuh hasil / verifikator: item OK atau N.A. yang belum memiliki hasil / alasan atau nama verifikator.']];
sum.getRange('A11:G11').merge();sum.getRange('A11').values=[['Kolom hasil digunakan untuk nilai, durasi, konfigurasi, referensi foto, atau alasan N.A.']];
sum.getRange('A1:G11').format.font.name='Arial';sum.getRange('A1:G11').format.font.size=10;sum.getRange('A1').format.font.size=14;sum.getRange('A1').format.font.bold=true;
for(const [c,w] of Object.entries({A:13,B:22,C:12,D:15,E:23,F:12,G:27}))sum.getRange(`${c}:${c}`).format.columnWidth=w;
const trial=wb.worksheets.getItem('GLD 1'); trial.getRange('D8').values=[['OK']]; wb.recalculate(); console.log('Trial missing fields:',sum.getRange('G5').values); trial.getRange('C8').values=[['tested']]; trial.getRange('E8').values=[['tester']]; wb.recalculate(); console.log('Trial complete:',sum.getRange('G5').values); trial.getRange('C8:E8').clear({applyTo:'contents'}); wb.recalculate();console.log('items per unit',items.length);console.log((await wb.inspect({kind:'table',range:'Ringkasan!A4:G7',include:'values,formulas',tableMaxRows:4,tableMaxCols:7})).ndjson);
for(const [name,range] of [['Ringkasan','A1:G11'],['GLD 1','A1:E20']]){const p=await wb.render({sheetName:name,range,scale:1,format:'png'});await fs.writeFile(`${root}/${name}-revisi-preview.png`,new Uint8Array(await p.arrayBuffer()));}
const f=await SpreadsheetFile.exportXlsx(wb);await f.save(root+'/Checklist_Internal_3_GLD.xlsx');


