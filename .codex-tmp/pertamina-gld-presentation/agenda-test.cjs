const PptxGenJS=require('pptxgenjs');
const pptx=new PptxGenJS(); pptx.defineLayout({ name:'CUSTOM_WIDE', width:13.333, height:7.5 }); pptx.layout='CUSTOM_WIDE'; let s=pptx.addSlide();
const rows = [
['01', 'Desain sistem', 'Topologi GLD, CH, Gateway, server'],
['02', 'Cara kerja', 'Jalur normal pull, alarm push, downlink, dataset/nulling'],
['03', 'Spesifikasi', 'Hardware, radio, payload, power, kapasitas cache'],
['04', 'Hasil uji', 'Bench, field-test logs, power-cycle, mapping sensor'],
['05', 'Perbandingan', 'Mode normal vs alarm, bench vs field, sebelum vs sesudah hardening'],
['06', 'Implikasi', 'Keterbatasan dan rekomendasi pengembangan']
];
s.addTable(rows, { x:0.9,y:1.65,w:11.5,h:4.15,colW:[0.72,2.55,8.23],margin:0.05,border:{type:'solid',color:'D1D5DB',pt:0.6},color:'111827',fontFace:'Arial',fontSize:11,valign:'mid',fit:'shrink',autoFit:false,fill:{color:'FFFFFF'}});
pptx.writeFile({fileName:'agenda-test.pptx'});
