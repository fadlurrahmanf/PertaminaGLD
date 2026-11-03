import fs from 'node:fs/promises';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const root='D:/Github/PertaminaGLD/outputs/checklist_sederhana';
const source=await fs.readFile(root+'/verifikasi.mjs','utf8');
const defs=source.slice(source.indexOf('const items='),source.indexOf('\nconst wb=Workbook.create()'));
const {items,hardware}=Function(defs+'; return {items,hardware};')();
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
 s.getRange('A3:G3').merge();s.getRange('A3').values=[['Catat hasil dan verifikator. N.A.: tulis alasan. Uji kontinuitas saat daya dilepas.']];s.getRange('A4:G4').merge();s.getRange('A4').values=[['Titik ukur, durasi dan kriteria uji mengikuti prosedur yang disepakati.']]; s.getRange('I4:M4').merge();s.getRange('I4').values=[['CONTOH SAJA — bukan hasil atau kriteria lulus.']];s.getRange('I4').format.font.italic=true;
 let row=6;const first=row+2;
 function table(label,records,isHardware){
  const lastcol=isHardware?'G':'E';s.getRange(`A${row}:${lastcol}${row}`).merge();s.getRange(`A${row}`).values=[[label.toUpperCase()]];s.getRange(`A${row}:${lastcol}${row}`).format.fill='#DCE9F0';s.getRange(`A${row}:${lastcol}${row}`).format.font.bold=true;row++;
  const h=s.getRange(`A${row}:${lastcol}${row}`);h.values=[isHardware?['No','Item','Butuh','Terpasang','Kondisi / catatan','Status','Verifikator']:['No','Yang dicek','Hasil / nilai','Status','Verifikator']];h.format.fill='#244761';h.format.font.color='#FFFFFF';h.format.font.bold=true;row++;
  const from=row;let vals=records.map((x,j)=>isHardware?[j+1,x[1],null,null,null,null,null]:[j+1,x[1],null,null,null]);const to=row+vals.length-1;s.getRange(`A${from}:${lastcol}${to}`).values=vals;s.getRange(`A${from}:${lastcol}${to}`).format.rowHeight=26;s.getRange(`B${from}:B${to}`).format.wrapText=true;s.getRange(`C${from}:${lastcol}${to}`).format.fill='#FFF4D6';
  const col=isHardware?'F':'D';s.getRange(`${col}${from}:${col}${to}`).dataValidation={rule:{type:'list',values:['OK','Belum OK','Belum dicek','N.A.']}};
  const ec=isHardware?'M':'K';s.getRange(`I${from-1}:${ec}${from-1}`).values=[isHardware?['Contoh butuh','Contoh terpasang','Contoh kondisi','Contoh status','Contoh verifikator']:['Contoh hasil','Contoh status','Contoh verifikator']];s.getRange(`I${from-1}:${ec}${from-1}`).format.fill='#D9E8D7';s.getRange(`I${from-1}:${ec}${from-1}`).format.font.bold=true;
  function example(label){const q=label.toLowerCase(); if(q.includes('nulling (v)'))return '0,05 V'; if(q.includes('tegangan')&&q.includes('input'))return '24 VDC';if(q.includes('tegangan'))return '3,30 V';if(q.includes('arus / daya'))return '0,25 A / 6 W';if(q.includes('lama uji'))return '2 jam; tidak restart';if(q.includes('panjang'))return '5 m';if(q.includes('foto'))return 'foto_GLD1.jpg';if(q.includes('form')||q.includes('dokumen'))return 'Form GLD-01';if(q.includes('firmware'))return 'v1.2.3';if(q.includes('frekuensi')||q.includes('konfigurasi lora'))return '921 MHz; SF7';if(q.includes('tujuan'))return 'CH-01';if(q.includes('id sensor'))return 'SB-001';if(q.includes('inferensi'))return 'Berjalan; hasil normal';if(q.includes('responsif'))return 'Nilai berubah saat diuji';if(q.includes('terbaca'))return 'Terbaca';if(q.includes('boot'))return 'Boot normal';if(q.includes('kontinuitas'))return 'Terhubung; buzzer';return 'Baik / berfungsi';}
  const examples=records.map(x=>isHardware?[1,1,'Baik','OK','Nama pemeriksa']:[example(x[1]),'OK','Nama pemeriksa']);s.getRange(`I${from}:${ec}${to}`).values=examples;s.getRange(`I${from}:${ec}${to}`).format.font.color='#526253';
  row=to+3;return {from,to};
 }
 let franges=[];for(const group of uniqueGroups(items))franges.push(table(group,items.filter(x=>x[0]===group),false));const fend=franges.at(-1).to;
 s.getRange(`A${row}:G${row}`).merge();s.getRange(`A${row}`).values=[['KELENGKAPAN HARDWARE']];s.getRange(`A${row}:G${row}`).format.font.bold=true;row+=2;
 let hranges=[];for(const group of uniqueGroups(hardware))hranges.push(table('Hardware - '+group,hardware.filter(x=>x[0]===group),true));const hs=hranges[0].from,he=hranges.at(-1).to;
 if(i===1){trialRow=franges[0].from;hardwareTrialRow=hs;}
 s.getRange(`A1:M${row}`).format.font.name='Arial';s.getRange(`A1:M${row}`).format.font.size=10;s.getRange('A1').format.font.bold=true;s.getRange('A1').format.font.size=14;for(const [c,w] of Object.entries({A:9,B:50,C:34,D:15,E:22,F:16,G:22,H:5,I:22,J:19,K:21,L:18,M:22}))s.getRange(`${c}:${c}`).format.columnWidth=w;s.freezePanes.freezeRows(4);
 const d=`'${name}'!D${first}:D${fend}`,c=`'${name}'!C${first}:C${fend}`,e=`'${name}'!E${first}:E${fend}`;
 const f=`'${name}'!F${hs}:F${he}`,hc=`'${name}'!C${hs}:C${he}`,hd=`'${name}'!D${hs}:D${he}`,hcond=`'${name}'!E${hs}:E${he}`,hv=`'${name}'!G${hs}:G${he}`;
 const count=(range,v)=>`COUNTIF(${range},"${v}")`,missing=(range,n)=>`${n}-${count(range,'OK')}-${count(range,'Belum OK')}-${count(range,'N.A.')}`;
 let r=i+4;summary.getRange(`A${r}`).values=[[name]];summary.getRange(`B${r}`).formulas=[[`=IF('${name}'!B2="","",'${name}'!B2)`]];
 summary.getRange(`C${r}:G${r}`).formulas=[[`=${count(d,'OK')}`,`=${count(d,'Belum OK')}`,`=${missing(d,items.length)}`,`=${count(d,'N.A.')}`,`=${count(d,'OK')}+${count(d,'N.A.')}-COUNTIFS(${d},"OK",${c},"<>",${e},"<>")-COUNTIFS(${d},"N.A.",${c},"<>",${e},"<>")`]];
 r=i+13;summary.getRange(`A${r}`).values=[[name]];summary.getRange(`B${r}:F${r}`).formulas=[[`=${count(f,'OK')}`,`=${count(f,'Belum OK')}`,`=${missing(f,hardware.length)}`,`=${count(f,'N.A.')}`,`=${count(f,'OK')}+${count(f,'N.A.')}-COUNTIFS(${f},"OK",${hc},"<>",${hd},"<>",${hcond},"<>",${hv},"<>")-COUNTIFS(${f},"N.A.",${hcond},"<>",${hv},"<>")`]];
}
summary.getRange('A1:G18').format.font.name='Arial';summary.getRange('A1:G18').format.font.size=10;summary.getRange('A1').format.font.size=14;summary.getRange('A1').format.font.bold=true;for(const [c,w] of Object.entries({A:13,B:22,C:12,D:15,E:20,F:15,G:24}))summary.getRange(`${c}:${c}`).format.columnWidth=w;
const trial=wb.worksheets.getItem('GLD 1');trial.getRange(`D${trialRow}`).values=[['OK']];trial.getRange(`F${hardwareTrialRow}`).values=[['OK']];wb.recalculate();console.log('missing fields',summary.getRange('G5').values,summary.getRange('F14').values);trial.getRange(`C${trialRow}`).values=[['test']];trial.getRange(`E${trialRow}`).values=[['test']];trial.getRange(`C${hardwareTrialRow}:G${hardwareTrialRow}`).values=[[1,1,'baik','OK','test']];wb.recalculate();console.log('completed fields',summary.getRange('G5').values,summary.getRange('F14').values);trial.getRange(`C${trialRow}:E${trialRow}`).clear({applyTo:'contents'});trial.getRange(`C${hardwareTrialRow}:G${hardwareTrialRow}`).clear({applyTo:'contents'});wb.recalculate();
console.log((await wb.inspect({kind:'table',range:'Ringkasan!A4:G7',include:'values',tableMaxRows:4,tableMaxCols:7})).ndjson);
for(const [name,range] of [['Ringkasan','A1:G18'],['GLD 1','A1:M25']]){const p=await wb.render({sheetName:name,range,scale:1,format:'png'});await fs.writeFile(`${root}/${name}-contoh-pengisian.png`,new Uint8Array(await p.arrayBuffer()));}
const f=await SpreadsheetFile.exportXlsx(wb);await f.save(root+'/Checklist_Internal_3_GLD_Contoh.xlsx');
