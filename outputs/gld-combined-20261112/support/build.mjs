import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';
const OUT='D:/Github/PertaminaGLD/outputs/gld-combined-20261112';
const SRC='D:/Github/PertaminaGLD/excel';
const LIMIT=Number(process.env.GLD_TEST_LIMIT||0);
const sensors=['MQ8','MQ135','MQ3','MQ5','MQ4','MQ7','MQ6','MQ2'];
const sc=['#2563EB','#D97706','#059669','#9333EA','#DC2626','#0891B2','#BE185D','#475569'];
const rc=['#2563EB','#D97706','#64748B','#059669','#9333EA'];
const defs=[
 ['dataset-gld.csv','Raw Awal','Awal',1,'Perubahan kecil selama rekaman.'],
 ['dataset-gld after nulling.csv','Raw After Nulling','After nulling',2,'Kenaikan multikanal; LPG muncul menjelang akhir.'],
 ['dataset-gld3.csv','Raw Cuplikan','Cuplikan',2,'Cuplikan 22,54 detik; bukan New 3. MA memakai jendela parsial.'],
 ['dataset-gld new 3.csv','Raw New 3','New 3',5,'MQ4, MQ7, MQ6 naik pada bagian akhir.'],
 ['dataset-gld Last.csv','Raw Last','Last',7,'Lima kanal naik di bagian akhir; seluruh prediksi Clear.'],
];
const col=n=>{let x='';for(;n;n=Math.floor((n-1)/26))x=String.fromCharCode(65+(n-1)%26)+x;return x;};
const log=(stage,more={})=>console.log(JSON.stringify({stage,...more,heapMB:Math.round(process.memoryUsage().heapUsed/1048576)}));
const parse=line=>line.split(/,(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)/).map(x=>x.replace(/^\"|\"$/g,'').replace(/\"\"/g,'\"'));
const data=[];
for(let k=0;k<defs.length;k++){
 const [file,sheetName,label,profile,note]=defs[k];const bytes=await fs.readFile(path.join(SRC,file));
 const lines=bytes.toString('utf8').replace(/^\uFEFF/,'').trimEnd().split(/\r?\n/);const headers=parse(lines.shift());
 let rows=lines.map((line,i)=>{const r=parse(line);if(r.length!==28)throw Error(`${file}: width ${i}`);return r.map((x,j)=>{if(j===1)return x;const n=Number(x);if(x===''||!Number.isFinite(n))throw Error(`${file}: number ${i},${j}`);return n;});});if(LIMIT)rows=rows.slice(0,LIMIT);
 const n=rows.length,t0=rows[0][0],end=rows.at(-1)[0],elapsed=rows.map(r=>(r[0]-t0)/60000);
 for(let i=1;i<n;i++)if(rows[i][0]<=rows[i-1][0])throw Error('Time not strictly increasing');
 const raw=sensors.map((_,j)=>rows.map(r=>r[j+2]));
 const maFor=minutes=>{let left=0;const sum=Array(8).fill(0),out=sensors.map(()=>[]),count=[];for(let i=0;i<n;i++){for(let j=0;j<8;j++)sum[j]+=rows[i][j+2];while(rows[left][0]<=rows[i][0]-minutes*60000){for(let j=0;j<8;j++)sum[j]-=rows[left][j+2];left++;}for(let j=0;j<8;j++)out[j].push(sum[j]/(i-left+1));count.push(i-left+1);}return {out,count};};
 data.push({file,sheetName,label,profile,note,headers,rows,n,t0,end,elapsed,raw,ma:maFor(1),ma5:maFor(5),hash:crypto.createHash('sha256').update(bytes).digest('hex'),color:rc[k]});
}
const wb=Workbook.create(),summary=wb.worksheets.add('Summary'),individual=wb.worksheets.add('Grafik Rekaman');
for(const d of data)d.sheet=wb.worksheets.add(d.sheetName);
const manifest=[];
const band=(sh,r)=>{sh.getRange(r).format={fill:'#243B53',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},rowHeight:32,wrapText:true,verticalAlignment:'center',horizontalAlignment:'center'};};
const title=(sh,cell,text)=>{sh.getRange(cell).values=[[text]];sh.getRange(cell).format.font={name:'Arial',size:15,bold:true,color:'#172554'};};
for(const [sh,height]of [[summary,220],[individual,122]]){sh.showGridLines=false;sh.getRange(`A1:Q${height}`).format={font:{name:'Arial',size:10,color:'#243B53'},columnWidth:12,rowHeight:21};}
summary.tabColor='#243B53';individual.tabColor='#55718B';summary.getRange('A1:A220').format.columnWidth=22;
title(summary,'A2','GLD1004 — gabungan rekaman sensor');
summary.getRange('A3').values=[['Lima rekaman dari folder excel. Data asli dan seluruh sampel grafik dipertahankan.']];
summary.getRange('A5').values=[['Jendela MA (menit)']];summary.getRange('C5').values=[[1]];
summary.getRange('C5').format={fill:'#FEF3C7',font:{name:'Arial',size:11,bold:true,color:'#92400E'},numberFormat:'0.00'};
summary.getRange('D5').formulas=[['=IF(AND(ISNUMBER(C5),C5>0),"Ubah sel kuning untuk menghitung ulang seluruh MA.","Masukkan angka menit lebih besar dari 0.")']];
summary.getRange('A6').values=[['MA: rata-rata sampel pada (t − jendela, t]. Awal rekaman memakai sampel tersedia; jeda tidak diinterpolasi.']];
summary.getRange('A8:I8').values=[['Rekaman','Sampel','Durasi (menit)','Profil nulling','Clear','LPG','LPG pertama (menit)','Jeda maks. (detik)','Sheet data']];band(summary,'A8:I8');
summary.getRange('A9:I13').format.rowHeight=30;
for(let k=0;k<data.length;k++){const d=data[k],r=9+k,q=`'${d.sheetName}'`;summary.getRange(`A${r}:I${r}`).values=[[d.label,null,null,d.profile,null,null,null,null,d.sheetName]];summary.getRange(`B${r}:C${r}`).formulas=[[`=${q}!AP5`, `=${q}!AS5`]];summary.getRange(`E${r}:H${r}`).formulas=[[`=${q}!AP6`,`=${q}!AS6`,`=${q}!AP7`,`=${q}!AS7`]];summary.getRange(`J${r}`).values=[[d.note]];}
summary.getRange('B9:B13').setNumberFormat('#,##0');summary.getRange('C9:C13').setNumberFormat('0.00');summary.getRange('E9:F13').setNumberFormat('#,##0');summary.getRange('G9:H13').setNumberFormat('0.00');
summary.getRange('I1:I220').format.columnWidth=22;
for(let k=0;k<data.length;k++){summary.getRange(`J${9+k}`).clear({applyTo:'contents'});summary.getRange(`K${9+k}`).values=[[data[k].note]];}
summary.getRange('A15').values=[['Grafik gabungan menyelaraskan menit 0 setiap rekaman; rekaman tidak disambung menjadi satu eksperimen.']];
summary.getRange('A16').values=[['Profil nulling berbeda. Clear/LPG adalah prediksi model; label clear_air bukan pengukuran gas independen.']];
summary.getRange('A17').values=[['Grafik per file berada di Grafik Rekaman. Lima sheet Raw memuat data CSV pada kolom A–AB tanpa perubahan.']];
summary.getRange('A18').values=[['Kolom AD–AM: waktu relatif, indeks awal jendela, dan MA. Grafik dalam volt (V); tabel perubahan dalam mV.']];
title(summary,'A20','Perubahan rata-rata awal–akhir (mV)');summary.getRange('A21:F21').values=[['Sensor',...data.map(d=>d.label)]];band(summary,'A21:F21');
for(let j=0;j<8;j++){summary.getRange(`A${22+j}`).values=[[sensors[j]]];summary.getRange(`B${22+j}:F${22+j}`).formulas=[data.map(d=>d.elapsed.at(-1)>=20?`='${d.sheetName}'!AR${11+j}`:'="n.a."')];}
summary.getRange('B22:F29').setNumberFormat('0.00;[Red]-0.00;0.00');
summary.getRange('H21').values=[['Metode perubahan']];summary.getRange('H22').values=[['Rata-rata 10 menit terakhir dikurangi 10 menit pertama.']];summary.getRange('H23').values=[['Durasi berbeda; angka ini bukan perbandingan laju drift.']];summary.getRange('H24').values=[['Cuplikan <20 menit tidak dinilai dengan metrik ini.']];
title(summary,'A32','Perbandingan seluruh rekaman per sensor');
title(individual,'A2','Grafik setiap rekaman');individual.getRange('A3').values=[['Kiri: seluruh sampel mentah. Kanan: moving average mengikuti Summary!C5. Satuan tegangan V.']];
const styleChart=(chart,t,a,b,colors)=>{chart.title=t;chart.setPosition(a,b);chart.titleTextStyle.fontSize=14;chart.titleTextStyle.typeface='Arial';chart.legend={position:'top',textStyle:{typeface:'Arial',fontSize:11}};chart.xAxis={numberFormatCode:'0.0',numberFormatSourceLinked:false,textStyle:{typeface:'Arial',fontSize:10}};chart.yAxis={numberFormatCode:'0.000',numberFormatSourceLinked:false,textStyle:{typeface:'Arial',fontSize:10}};chart.xAxis.title.text='Waktu sejak awal rekaman (menit)';chart.yAxis.title.text='Tegangan (V)';chart.series.items.forEach((se,j)=>{se.line={fill:colors[j],style:'solid',width:t.includes('Raw')?.7:1.5};});};
for(const [k,d]of data.entries()){
 const sh=d.sheet,last=d.n+1,q=`'${d.sheetName}'`;sh.showGridLines=false;
 sh.getRange(`A1:AM${last}`).format={font:{name:'Arial',size:10,color:'#243B53'},columnWidth:15,rowHeight:19};sh.getRange(`B1:B${last}`).format.columnWidth=49;
 sh.getRange('A1:AB1').values=[d.headers];band(sh,'A1:AB1');sh.getRange('A1:AM1').format.rowHeight=36;
 sh.getRange('AD1:AM1').values=[['Waktu relatif (menit)','Indeks awal MA',...sensors.map(s=>s+' MA (V)')]];band(sh,'AD1:AM1');
 log('write raw',{file:d.file,rows:d.n});
 for(let off=0;off<d.n;off+=2000){const block=d.rows.slice(off,off+2000);sh.getRangeByIndexes(1+off,0,block.length,28).values=block;}
 sh.getRange(`A2:A${last}`).setNumberFormat('0');sh.getRange(`C2:J${last}`).setNumberFormat('0.000000000');sh.getRange(`K2:K${last}`).setNumberFormat('0');sh.getRange(`L2:L${last}`).setNumberFormat('0.00000000');sh.getRange(`M2:AB${last}`).setNumberFormat('0');
 sh.getRange(`AD2:AD${last}`).formulas=d.rows.map((_,i)=>[`=(A${i+2}-$A$2)/60000`]);sh.getRange(`AD2:AD${last}`).setNumberFormat('0.00');
 log('write moving average',{file:d.file});
 for(let off=0;off<d.n;off+=2000){const len=Math.min(2000,d.n-off),fm=[];for(let i=0;i<len;i++){const row=off+i,r=2+row;fm.push(LIMIT?[`=IF(AND(ISNUMBER(Summary!$C$5),Summary!$C$5>0),IF(A${r}-Summary!$C$5*60000<$A$2,1,MATCH(A${r}-Summary!$C$5*60000,$A$2:$A$${last},1)+1),NA())`,...sensors.map((_,j)=>`=AVERAGE(INDEX($${col(j+3)}$2:$${col(j+3)}$${last},$AE${r}):${col(j+3)}${r})`)]:[row-d.ma.count[row]+2,...sensors.map((_,j)=>d.ma.out[j][row])]);}if(LIMIT)sh.getRangeByIndexes(1+off,30,len,9).formulas=fm;else sh.getRangeByIndexes(1+off,30,len,9).values=fm;}
 sh.getRange(`AE2:AE${last}`).setNumberFormat('0');sh.getRange(`AF2:AM${last}`).setNumberFormat('0.000000000');
 sh.getRange('AO1:AV20').format={font:{name:'Arial',size:10,color:'#243B53'},columnWidth:18,rowHeight:22};
 title(sh,'AO2','Ringkasan rekaman');sh.getRange('AO3').values=[['Sumber: '+d.file]];sh.getRange('AO4').values=[['Label: '+d.rows[0][1]]];
 sh.getRange('AO5:AT7').values=[['Sampel',null,null,'Menit',null,null],['Clear',null,null,'LPG',null,null],['LPG pertama (menit)',null,null,'Jeda maks. (detik)',null,null]];
 sh.getRange('AP5').formulas=[[`=COUNT(A2:A${last})`]];sh.getRange('AS5').formulas=[[`=(A${last}-A2)/60000`]];sh.getRange('AP6').formulas=[[`=COUNTIFS(K2:K${last},0)`]];sh.getRange('AS6').formulas=[[`=COUNTIFS(K2:K${last},1)`]];
 sh.getRange('AP7').formulas=[[`=IF(AS6=0,"n.a.",(INDEX(A2:A${last},MATCH(1,K2:K${last},0))-A2)/60000)`]];
 sh.getRange('AS7').values=[[Math.max(0,...d.rows.slice(1).map((r,i)=>(r[0]-d.rows[i][0])/1000))]];sh.getRange('AP7:AS7').setNumberFormat('0.00');sh.getRange('AS5').setNumberFormat('0.00');
 sh.getRange('AO8').values=[['Profil nulling: '+d.profile+'; GLD1004; model cnn-dualbranch-board-1-2class-v2.']];
 sh.getRange('AO10:AV10').values=[['Sensor','Awal 10m (mV)','Akhir 10m (mV)','Perubahan (mV)','Rata-rata (mV)','Minimum (mV)','Maksimum (mV)','MA akhir (V)']];band(sh,'AO10:AV10');
 for(let j=0;j<8;j++){const r=11+j,c=col(j+3),ma=col(j+32),range=`${c}2:${c}${last}`,time=`A2:A${last}`;sh.getRange(`AO${r}`).values=[[sensors[j]]];sh.getRange(`AP${r}:AV${r}`).formulas=[[`=AVERAGEIFS(${range},${time},"<"&($A$2+600000))*1000`,`=AVERAGEIFS(${range},${time},">="&($A$${last}-600000))*1000`,d.elapsed.at(-1)>=20?`=AQ${r}-AP${r}`:'="n.a."',`=AVERAGE(${range})*1000`,`=MIN(${range})*1000`,`=MAX(${range})*1000`,`=${ma}${last}`]];}
 sh.getRange('AP11:AU18').setNumberFormat('0.00');sh.getRange('AV11:AV18').setNumberFormat('0.000000');
 sh.getRange('AO20').values=[['SHA-256: '+d.hash]];sh.getRange('AO21').values=[[d.note]];sh.freezePanes.freezeRows(1);sh.freezePanes.freezeColumns(2);
 for(const mode of ['raw','ma']){const ma=mode==='ma',top=6+k*23;const chart=individual.charts.add('scatter',{series:sensors.map((sensor,j)=>({name:sensor,xValues:d.elapsed,values:ma?d.ma.out[j]:d.raw[j]}))});styleChart(chart,`${d.label} — ${ma?'Moving average':'Raw'} (V)`,`${ma?'J':'A'}${top}`,`${ma?'Q':'H'}${top+21}`,sc);manifest.push({sheet:'Grafik Rekaman',title:`${d.label} — ${ma?'Moving average':'Raw'} (V)`,series:sensors.map((sensor,j)=>({name:sensor,xFormula:`${q}!$AD$2:$AD$${last}`,yFormula:`${q}!$${col(ma?j+32:j+3)}$2:$${col(ma?j+32:j+3)}$${last}`,dataset:k,sensor:j,mode,color:sc[j]}))});}
 log('sheet ready',{file:d.file});
}
for(let j=0;j<8;j++)for(const mode of ['raw','ma']){const top=34+j*23,ma=mode==='ma';const chart=summary.charts.add('scatter',{series:data.map(d=>({name:d.label,xValues:d.elapsed,values:ma?d.ma.out[j]:d.raw[j],line:{fill:d.color,style:'solid',width:ma?1.5:.7}}))});styleChart(chart,`${sensors[j]} — ${ma?'Moving average':'Raw'} (V)`,`${ma?'J':'A'}${top}`,`${ma?'Q':'H'}${top+21}`,rc);manifest.push({sheet:'Summary',title:`${sensors[j]} — ${ma?'Moving average':'Raw'} (V)`,series:data.map((d,k)=>({name:d.label,xFormula:`'${d.sheetName}'!$AD$2:$AD$${d.n+1}`,yFormula:`'${d.sheetName}'!$${col(ma?j+32:j+3)}$2:$${col(ma?j+32:j+3)}$${d.n+1}`,dataset:k,sensor:j,mode,color:d.color}))});}
log('recalculate');wb.recalculate();
for(const d of data){const v=d.sheet.getRange(`AM${d.n+1}`).values[0][0],want=d.ma.out[7].at(-1);if(typeof v!=='number'||Math.abs(v-want)>1e-9)throw Error(`MA mismatch ${d.file} ${v} vs ${want}`);}log('1 minute checkpoints OK');
if(LIMIT){summary.getRange('C5').values=[[5]];wb.recalculate();for(const d of data){const v=d.sheet.getRange(`AM${d.n+1}`).values[0][0],want=d.ma5.out[7].at(-1);if(typeof v!=='number'||Math.abs(v-want)>1e-9)throw Error(`MA5 mismatch ${d.file} ${v} vs ${want}`);}log('5 minute recalculation OK');summary.getRange('C5').values=[[1]];wb.recalculate();}
console.log((await wb.inspect({kind:'table',range:'Summary!A8:I13',include:'values,formulas',tableMaxRows:6,tableMaxCols:9,maxChars:3000})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},summary:'formula errors',maxChars:2000})).ndjson);
await fs.writeFile(path.join(OUT,'support','chart-manifest.json'),JSON.stringify({datasets:data.map(({file,sheetName,label,profile,n,t0,end,hash,elapsed,raw,ma})=>({file,sheetName,label,profile,n,t0,end,hash,elapsed,raw,ma:ma.out})),charts:manifest}));
for(const [sh,ranges]of [[summary,['A1:Q30','A34:Q55']],[individual,['A6:Q27', 'A98:Q119']],...data.map(d=>[d.sheet,['A1:J7','AO1:AV21']])]){for(let i=0;i<ranges.length;i++){log('render',{sheet:sh.name,range:ranges[i]});const p=await wb.render({sheetName:sh.name,range:ranges[i],scale:1});await fs.writeFile(path.join(OUT,'support',`${sh.name.replaceAll(' ','_')}_${i}.png`),new Uint8Array(await p.arrayBuffer()));}}
log('export');const xlsx=await SpreadsheetFile.exportXlsx(wb);await xlsx.save(path.join(OUT,'GLD_Gabungan.xlsx'));
log('done',{charts:manifest.length,totalRows:data.reduce((n,d)=>n+d.n,0),testLimit:LIMIT});
