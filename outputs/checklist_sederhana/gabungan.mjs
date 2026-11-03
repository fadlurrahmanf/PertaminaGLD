import fs from 'node:fs/promises';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const root='D:/Github/PertaminaGLD/outputs/checklist_sederhana';
const source=await fs.readFile(root+'/verifikasi.mjs','utf8');
const defs=source.slice(source.indexOf('const items='),source.indexOf('\nconst wb=Workbook.create()'));
const {items,hardware}=Function(defs+'; return {items,hardware};')();
for (const r of items) {
 if(r[1]==='ID sensor board') r[1]='ID node GLD';
 if(r[1]==='Kondisi konektor antar-board') r[1]='Kondisi konektor internal';
 if(r[1]==='Konektor sensor board: kondisi dan kontinuitas') r[1]='Konektor sensor: kondisi dan kontinuitas';
}
for (let i=hardware.length-1;i>=0;i--) if(['Sensor board','Pengikat kabel','Baut tutup casing','Spacer kipas'].includes(hardware[i][1])) hardware.splice(i,1);
for (const r of hardware) {
 if(r[1]==='Dudukan antena') r[1]='Sambungan dudukan antena ke PCB / board';
 if(r[1]==='Kabel dan konektor antar-board') r[1]='Kabel dan konektor internal';
}
const hwExamples={
 'Casing / main body':'1','Tutup casing':'1','Baut tutup casing':'3','Seal tutup casing':'1',
 'Buzzer / unit alarm':'1','Kabel dan konektor buzzer':'Baik; kabel tidak putus',
 'Antena LoRa':'1; pastikan antena LoRa','Kabel dan konektor antena':'Kondisi baik',
 'Sambungan dudukan antena ke PCB / board':'Foto; sambungan tidak terputus',
 'Board GLD':'1','Baut board ke casing':'4; terpasang','Spacer board ke casing':'4; terpasang',
 'MQ-2':'1','MQ-3':'1','MQ-4':'1','MQ-5':'1','MQ-6':'1','MQ-7':'1','MQ-8':'1','MQ-135':'1','Socket sensor MQ':'1',
 'Kipas':'1','Spacer kipas':'4','Baut kipas':'4; terhubung ke spacer','Kabel dan konektor kipas':'Kondisi baik',
 'Kabel power keluar casing (panjang: m)':'5 meter','Gland kabel power':'Terpasang','Konektor / terminal power':'Tidak longgar',
 'Kabel dan konektor internal':'Kondisi baik','Kabel grounding casing ke board':'Tes buzzer: tersambung'
};
const wb=Workbook.create();const summary=wb.worksheets.add('Ringkasan');summary.showGridLines=false;
summary.getRange('A1:G1').merge();summary.getRange('A1').values=[['RINGKASAN PEMERIKSAAN 3 GLD']];summary.getRange('A2:G2').merge();summary.getRange('A2').values=[['Isi hasil, status dan verifikator pada sheet tiap GLD. N.A. perlu alasan.']];
function head(range,labels){const r=summary.getRange(range);r.values=[labels];r.format.fill='#244761';r.format.font.color='#FFFFFF';r.format.font.bold=true;}
head('A4:G4',['Unit','ID GLD','OK','Belum OK','Belum dicek','N.A.','Data kurang']);head('A13:F13',['Unit','OK','Belum OK','Belum dicek','N.A.','Data kurang']);
summary.getRange('A11:G11').merge();summary.getRange('A11').values=[['KELENGKAPAN HARDWARE']];summary.getRange('A11:G11').format.fill='#DCE9F0';summary.getRange('A11:G11').format.font.bold=true;
summary.getRange('A9:G9').merge();summary.getRange('A9').values=[['Data kurang: item OK / N.A. belum memiliki hasil atau alasan dan verifikator.']];summary.getRange('A18:G18').merge();summary.getRange('A18').values=[['Hardware OK perlu jumlah butuh, terpasang, kondisi dan verifikator. N.A. perlu alasan dan verifikator.']];
function uniqueGroups(rows){return [...new Set(rows.map(x=>x[0]))]}
let trialRow, hardwareTrialRow;
for(let i=1;i<=3;i++){
 const name=`GLD ${i}`;const s=wb.worksheets.add(name);s.showGridLines=false;
 s.getRange('A1:G1').merge();s.getRange('A1').values=[[`CHECKLIST INTERNAL ${name}`]];s.getRange('A2').values=[['ID GLD']];s.getRange('C2').values=[['Tanggal']];s.getRange('B2').format.fill='#FFF4D6';s.getRange('D2').format.fill='#FFF4D6';
 s.getRange('A3:G3').merge();s.getRange('A3').values=[['Catat hasil dan verifikator. N.A.: tulis alasan. Uji kontinuitas saat daya dilepas.']];s.getRange('A4:G4').merge();s.getRange('A4').values=[['Contoh OK hanya ilustrasi; kriteria dan nilai sesuai prosedur yang disepakati.']];
 let row=6;const first=row+2;
 function table(label,records,isHardware){
  const lastcol=isHardware?'H':'F';s.getRange(`A${row}:${lastcol}${row}`).merge();s.getRange(`A${row}`).values=[[label.toUpperCase()]];s.getRange(`A${row}:${lastcol}${row}`).format.fill='#DCE9F0';s.getRange(`A${row}:${lastcol}${row}`).format.font.bold=true;row++;
  const h=s.getRange(`A${row}:${lastcol}${row}`);h.values=[isHardware?['No','Item','Contoh OK','Butuh','Terpasang','Kondisi / catatan','Status','Verifikator']:['No','Yang dicek','Contoh OK','Hasil / nilai','Status','Verifikator']];h.format.fill='#244761';h.format.font.color='#FFFFFF';h.format.font.bold=true;row++;
  const from=row;function example(label){const q=label.toLowerCase();if(q.includes('nulling (v)'))return 'mis. 0,05 V';if(q.includes('tegangan')&&q.includes('input'))return 'mis. 24 VDC';if(q.includes('tegangan'))return 'mis. 3,30 V';if(q.includes('arus / daya'))return 'mis. 0,25 A / 6 W';if(q.includes('lama uji'))return '2 jam; tidak restart';if(q.includes('panjang'))return 'mis. 5 m';if(q.includes('foto'))return 'foto_GLD1.jpg';if(q.includes('form')||q.includes('dokumen'))return 'Form GLD-01';if(q.includes('firmware'))return 'mis. v1.2.3';if(q.includes('konfigurasi lora'))return 'mis. 921 MHz; SF7';if(q.includes('tujuan'))return 'mis. CH-01';if(q.includes('id node gld'))return 'GLD-0x1001';if(q.includes('inferensi'))return 'Berjalan; hasil normal';if(q.includes('responsif'))return 'Nilai berubah saat diuji';if(q.includes('terbaca'))return 'Terbaca';if(q.includes('boot'))return 'Boot normal';if(q.includes('kontinuitas'))return 'Terhubung; buzzer';return 'Baik / berfungsi';}
  const vals=records.map((x,j)=>isHardware?[j+1,x[1],hwExamples[x[1]] ?? 'Kondisi baik',null,null,null,null,null]:[j+1,x[1],example(x[1]),null,null,null]);const to=row+vals.length-1;s.getRange(`A${from}:${lastcol}${to}`).values=vals;s.getRange(`A${from}:${lastcol}${to}`).format.rowHeight=30;s.getRange(`B${from}:C${to}`).format.wrapText=true;s.getRange(`C${from}:C${to}`).format.fill='#E9F2E7';s.getRange(`D${from}:${lastcol}${to}`).format.fill='#FFF4D6';
  const col=isHardware?'G':'E';s.getRange(`${col}${from}:${col}${to}`).dataValidation={rule:{type:'list',values:['OK','Belum OK','Belum dicek','N.A.']}};row=to+3;return {from,to};
 }
 let franges=[];for(const group of uniqueGroups(items))franges.push(table(group,items.filter(x=>x[0]===group),false));const fend=franges.at(-1).to;
 s.getRange(`A${row}:G${row}`).merge();s.getRange(`A${row}`).values=[['KELENGKAPAN HARDWARE']];s.getRange(`A${row}:G${row}`).format.font.bold=true;row+=2;
 let hranges=[];for(const group of uniqueGroups(hardware))hranges.push(table('Hardware - '+group,hardware.filter(x=>x[0]===group),true));const hs=hranges[0].from,he=hranges.at(-1).to;
 if(i===1){trialRow=franges[0].from;hardwareTrialRow=hs;}
 s.getRange(`A1:H${row}`).format.font.name='Arial';s.getRange(`A1:H${row}`).format.font.size=10;s.getRange('A1').format.font.bold=true;s.getRange('A1').format.font.size=14;for(const [c,w] of Object.entries({A:8,B:48,C:29,D:22,E:16,F:23,G:16,H:22}))s.getRange(`${c}:${c}`).format.columnWidth=w;s.freezePanes.freezeRows(4);
 const d=`'${name}'!E${first}:E${fend}`,c=`'${name}'!D${first}:D${fend}`,e=`'${name}'!F${first}:F${fend}`;
 const f=`'${name}'!G${hs}:G${he}`,hc=`'${name}'!D${hs}:D${he}`,hd=`'${name}'!E${hs}:E${he}`,hcond=`'${name}'!F${hs}:F${he}`,hv=`'${name}'!H${hs}:H${he}`;
 const count=(range,v)=>`COUNTIF(${range},"${v}")`,missing=(range,n)=>`${n}-${count(range,'OK')}-${count(range,'Belum OK')}-${count(range,'N.A.')}`;
 let r=i+4;summary.getRange(`A${r}`).values=[[name]];summary.getRange(`B${r}`).formulas=[[`=IF('${name}'!B2="","",'${name}'!B2)`]];
 summary.getRange(`C${r}:G${r}`).formulas=[[`=${count(d,'OK')}`,`=${count(d,'Belum OK')}`,`=${missing(d,items.length)}`,`=${count(d,'N.A.')}`,`=${count(d,'OK')}+${count(d,'N.A.')}-COUNTIFS(${d},"OK",${c},"<>",${e},"<>")-COUNTIFS(${d},"N.A.",${c},"<>",${e},"<>")`]];
 r=i+13;summary.getRange(`A${r}`).values=[[name]];summary.getRange(`B${r}:F${r}`).formulas=[[`=${count(f,'OK')}`,`=${count(f,'Belum OK')}`,`=${missing(f,hardware.length)}`,`=${count(f,'N.A.')}`,`=${count(f,'OK')}+${count(f,'N.A.')}-COUNTIFS(${f},"OK",${hc},"<>",${hd},"<>",${hcond},"<>",${hv},"<>")-COUNTIFS(${f},"N.A.",${hcond},"<>",${hv},"<>")`]];
}
summary.getRange('A1:G18').format.font.name='Arial';summary.getRange('A1:G18').format.font.size=10;summary.getRange('A1').format.font.size=14;summary.getRange('A1').format.font.bold=true;for(const [c,w] of Object.entries({A:13,B:22,C:12,D:15,E:20,F:15,G:24}))summary.getRange(`${c}:${c}`).format.columnWidth=w;
const groups={'Casing':['Casing / badan','Tutup casing','Seal dan pengunci tutup'], 'Board CH':['Board CH','Baut board','Spacer board','Konektor pada board'], 'Antena dan kabel':['Antena LoRa','Dudukan antena','Kabel dan konektor antena'], 'Catu daya':['Kabel power','Konektor / terminal power','Gland kabel','Baterai, jika digunakan'], 'Solar cell dan pemasangan':['Panel solar cell','Kabel dan konektor panel','Bracket panel','Klem CH dan baut pemasangan'], 'Dokumentasi':['Foto perangkat dan komponen','ID / nomor seri perangkat','Referensi BOM / form verifikasi']};
const smallGroups={...groups,'Board CH':['Board CH','Konektor pada board'],'Catu daya':['Kabel power panel ke CH','Konektor ke charger','Baterai'], 'Solar cell dan pemasangan':['Panel solar cell','Dudukan panel solar cell','Konektor paralel panel','Klem CH dan baut pemasangan'],'Dokumentasi':['Foto perangkat dan komponen','ID CH yang sudah OK']};
const qty={'Konektor ke charger':1,'Klem CH dan baut pemasangan':3,'Tutup casing':3,'Seal dan pengunci tutup':3,'Dudukan antena':6,'Casing / badan':3,'Board CH':3,'Antena LoRa':3,'Baterai':3,'Panel solar cell':6,'Dudukan panel solar cell':6,'Kabel power panel ke CH':3,'Konektor paralel panel':3};
const hints={'Konektor ke charger':'Kondisi baik; tidak longgar','Klem CH dan baut pemasangan':'1 set per CH','ID CH yang sudah OK':'Catat ID CH yang OK','Tutup casing':'1 per CH','Seal dan pengunci tutup':'1 per CH','Konektor pada board':'Kondisi baik','Dudukan antena':'2 per CH; tidak longgar','Kabel dan konektor antena':'Konektor antena baik','Casing / badan':'1 per CH','Board CH':'1 per CH','Antena LoRa':'1 per CH','Baterai':'1 per CH','Panel solar cell':'2 per CH','Dudukan panel solar cell':'1 per panel','Kabel power panel ke CH':'1 per CH','Konektor paralel panel':'1 per CH; 2 panel paralel'};
const largeExamples={'Casing / badan':'Casing utuh','Tutup casing':'Tutup lengkap dan baik','Seal dan pengunci tutup':'Seal baik; tutup terkunci','Board CH':'Board tersedia; fisik baik','Baut board':'Terpasang dan kencang','Spacer board':'Terpasang dan baik','Konektor pada board':'Konektor tidak rusak / longgar','Antena LoRa':'Antena LoRa tersedia; baik','Dudukan antena':'Terpasang; tidak longgar','Kabel dan konektor antena':'Kabel baik; konektor tidak longgar','Kabel power':'Kabel ada dan tidak rusak','Konektor / terminal power':'Konektor baik; tidak longgar','Gland kabel':'Terpasang dan baik','Baterai, jika digunakan':'Tersedia; kondisi fisik baik','Panel solar cell':'Panel tersedia; kondisi baik','Kabel dan konektor panel':'Kabel dan konektor baik','Bracket panel':'Tersedia; kondisi baik','Klem CH dan baut pemasangan':'Lengkap; kondisi baik','Foto perangkat dan komponen':'Foto perangkat tersedia','ID / nomor seri perangkat':'ID tercatat, mis. CH-01','Referensi BOM / form verifikasi':'Nomor form tercatat'};
const kebutuhanKondisi={
'Casing / badan':'Utuh; tidak retak','Tutup casing':'Utuh; dapat ditutup','Seal dan pengunci tutup':'Seal utuh; terkunci rapat','Board CH':'Tersedia; fisik baik','Baut board':'Lengkap; terpasang kencang','Spacer board':'Lengkap; terpasang','Konektor pada board':'Baik; tidak longgar',
'Antena LoRa':'Antena LoRa utuh','Dudukan antena':'Baik; tidak longgar','Kabel dan konektor antena':'Kabel utuh; konektor kuat',
'Kabel power':'Kabel utuh; tidak putus','Kabel power panel ke CH':'Kabel utuh; tidak putus','Konektor ke charger':'Baik; tidak longgar','Konektor / terminal power':'Baik; tidak longgar','Gland kabel':'Terpasang; rapat','Baterai, jika digunakan':'Kondisi fisik baik','Baterai':'Kondisi fisik baik',
'Panel solar cell':'Panel utuh; tidak retak','Dudukan panel solar cell':'Terpasang; kokoh','Konektor paralel panel':'Sesuai; kondisi baik','Kabel dan konektor panel':'Kabel utuh; konektor baik','Bracket panel':'Lengkap; kokoh','Klem CH dan baut pemasangan':'Lengkap; terpasang kuat',
'Foto perangkat dan komponen':'Foto jelas; tersedia','ID / nomor seri perangkat':'ID tercatat','ID CH yang sudah OK':'ID CH yang OK tercatat','Referensi BOM / form verifikasi':'Referensi tersedia'
};
const largeGroups={
'Casing':['Casing / badan','Tutup casing','Seal dan pengunci tutup'],
'Board CH':['Board CH','Konektor pada board'],
'Antena dan port':['Antena besar','Antena kecil','Port baterai','Port panel surya','Dudukan antena','Kabel dan konektor antena'],
'Baterai dan power':['Baterai dan konektor','Kabel power panel ke CH besar','Sealant kabel'],
'Panel surya':['Panel solar cell','Dudukan panel solar cell','Konektor paralel panel'],
'Mounting CH':['Dudukan U-bolt 4 inci','Mur dan baut U-bolt'],
'Dokumentasi':['Foto perangkat dan komponen','ID / nomor seri perangkat','Referensi BOM / form verifikasi'],
'Tiang - RU IV':['Tiang diameter 8 cm']
};
const largeReq={'Casing / badan':2,'Tutup casing':'Sesuai 2 casing','Seal dan pengunci tutup':'Utuh; tutup rapat','Board CH':3,'Antena besar':2,'Antena kecil':2,'Port baterai':2,'Port panel surya':2,'Dudukan antena':'Kuat; tidak lepas','Kabel dan konektor antena':'Kabel utuh; konektor kuat','Baterai dan konektor':2,'Kabel power panel ke CH besar':'Jumlah konfirmasi','Sealant kabel':2,'Panel solar cell':2,'Dudukan panel solar cell':2,'Konektor paralel panel':2,'Dudukan U-bolt 4 inci':2,'Mur dan baut U-bolt':4,'Tiang diameter 8 cm':'Diameter 8 cm'};
const largeHint={'Antena besar':'Pastikan antena LoRa','Antena kecil':'Pastikan antena LoRa','Baterai dan konektor':'2 set; baterai 4,2 V','Kabel power panel ke CH besar':'Kondisi baik; tidak putus','Sealant kabel':'2 untuk 2 CH','Panel solar cell':'2 panel total','Dudukan panel solar cell':'1 per panel','Konektor paralel panel':'2 untuk 2 CH','Dudukan U-bolt 4 inci':'2 buah; ukuran 4 inci','Mur dan baut U-bolt':'4 buah','Tiang diameter 8 cm':'Oleh RU IV'};

for(const name of ['CH Kecil','CH Besar']){
 const s=wb.worksheets.add(name);s.showGridLines=false;s.getRange('A1:H1').merge();s.getRange('A1').values=[[`CHECKLIST HARDWARE ${name.toUpperCase()}`]];s.getRange('A2').values=[[name==='CH Kecil'?'ID CH (3 unit)':'ID CH']];s.getRange('C2').values=[['Tanggal']];s.getRange('B2').format.fill='#FFF4D6';s.getRange('D2').format.fill='#FFF4D6';
 s.getRange('A3:H3').merge();s.getRange('A3').values=[[name==='CH Kecil'?'Kebutuhan total untuk 3 CH kecil. Kolom Ada diisi setelah pemeriksaan.':'Daftar awal: cocokkan item dan jumlah dengan unit / BOM. N.A. beri alasan.']];s.getRange('A4:H4').merge();s.getRange('A4').values=[['Butuh berisi jumlah atau kondisi yang harus dipenuhi; jumlah lain konfirmasi ke BOM.']];let row=6;
 for(const [group,items] of Object.entries(name==='CH Kecil'?smallGroups:largeGroups)){
  s.getRange(`A${row}:H${row}`).merge();s.getRange(`A${row}`).values=[[(name==='CH Besar'&&group!=='Dokumentasi'&&group!=='Tiang - RU IV'?'LGU - ':'')+group.toUpperCase()]];s.getRange(`A${row}:H${row}`).format.fill='#DCE9F0';s.getRange(`A${row}:H${row}`).format.font.bold=true;row++;
  s.getRange(`A${row}:H${row}`).values=[['No','Item','Contoh OK','Butuh','Ada','Kondisi / foto','Status','Verifikator']];s.getRange(`A${row}:H${row}`).format.fill='#244761';s.getRange(`A${row}:H${row}`).format.font.color='#FFFFFF';s.getRange(`A${row}:H${row}`).format.font.bold=true;row++;
  const from=row, vals=items.map((v,i)=>[i+1,v,name==='CH Kecil'&&hints[v]?hints[v]:(name==='CH Besar'?(largeHint[v]??largeExamples[v]??'Kondisi baik'):(group==='Dokumentasi'?'Referensi tersedia':'Jumlah sesuai; baik')),name==='CH Kecil'?(qty[v]??kebutuhanKondisi[v]??'Konfirmasi sesuai unit'):(largeReq[v]??(['Foto perangkat dan komponen','ID / nomor seri perangkat','Referensi BOM / form verifikasi'].includes(v)?'1 per CH':(kebutuhanKondisi[v]??'Konfirmasi sesuai unit'))),null,null,null,null]);const end=row+vals.length-1;
  s.getRange(`A${from}:H${end}`).values=vals;s.getRange(`A${from}:H${end}`).format.rowHeight=34;s.getRange(`B${from}:D${end}`).format.wrapText=true;s.getRange(`C${from}:C${end}`).format.fill='#E9F2E7';s.getRange(`D${from}:H${end}`).format.fill='#FFF4D6';s.getRange(`G${from}:G${end}`).dataValidation={rule:{type:'list',values:['OK','Belum OK','Belum dicek','N.A.']}};row=end+3;
 }
 s.getRange(`A1:H${row}`).format.font.name='Arial';s.getRange(`A1:H${row}`).format.font.size=10;s.getRange('A1').format.font.size=14;s.getRange('A1').format.font.bold=true;
 for(const [c,w] of Object.entries({A:7,B:38,C:30,D:32,E:11,F:32,G:16,H:22}))s.getRange(`${c}:${c}`).format.columnWidth=w;s.getRange(`D1:D${row}`).format.horizontalAlignment='center';s.getRange(`A1:H${row}`).format.verticalAlignment='center';s.freezePanes.freezeRows(4);
}
const trial=wb.worksheets.getItem('GLD 1');trial.getRange(`E${trialRow}`).values=[['OK']];trial.getRange(`G${hardwareTrialRow}`).values=[['OK']];wb.recalculate();console.log('missing fields',summary.getRange('G5').values,summary.getRange('F14').values);trial.getRange(`D${trialRow}`).values=[['test']];trial.getRange(`F${trialRow}`).values=[['test']];trial.getRange(`D${hardwareTrialRow}:H${hardwareTrialRow}`).values=[[1,1,'baik','OK','test']];wb.recalculate();console.log('completed fields',summary.getRange('G5').values,summary.getRange('F14').values);trial.getRange(`D${trialRow}:F${trialRow}`).clear({applyTo:'contents'});trial.getRange(`D${hardwareTrialRow}:H${hardwareTrialRow}`).clear({applyTo:'contents'});wb.recalculate();
console.log((await wb.inspect({kind:'table',range:'Ringkasan!A4:G7',include:'values',tableMaxRows:4,tableMaxCols:7})).ndjson);
for(const [name,range] of [['Ringkasan','A1:G18'],['GLD 1','A1:H25']]){const p=await wb.render({sheetName:name,range,scale:1,format:'png'});await fs.writeFile(`${root}/${name}-gabungan-preview.png`,new Uint8Array(await p.arrayBuffer()));}
const f=await SpreadsheetFile.exportXlsx(wb);await f.save(root+'/Checklist_GLD_dan_CH.xlsx');


