from pathlib import Path
p=Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/three-gld.mjs')
s=p.read_text(encoding='utf-8-sig')
s=s.replace("add('Firmware',", "add('Fan','Fan menyala dan berputar normal');\nadd('Firmware',")
s=s.replace("const wb=Workbook.create();", """const hardware = [
 ['Casing','Main body'],['Casing','Tutup'],['Casing','Baut tutup'],['Casing','Seal tutup'],['Casing','Sambungan grounding casing'],
 ['Board','Board GLD'],['Board','Sensor board'],['Board','Baut board ke casing'],['Board','Spacer board ke casing'],
 ...['MQ-2','MQ-3','MQ-4','MQ-5','MQ-6','MQ-7','MQ-8','MQ-135'].map(x=>['Sensor',x+' dan socket']),
 ['Fan','Fan'],['Fan','Baut fan'],['Fan','Spacer fan ke casing'],['Fan','Kabel dan konektor fan'],
 ['Alarm','Unit alarm'],['Alarm','Dudukan / pengikat alarm'],['Alarm','Kabel dan konektor alarm'],
 ['LoRa','Antena LoRa'],['LoRa','Dudukan antena'],['LoRa','Kabel dan konektor antena'],
 ['Daya','Gland'],['Daya','Kabel ke junction box (catat panjang m)'],['Daya','Terminal / konektor daya'],
 ['Internal','Kabel antar-board'],['Internal','Konektor antar-board'],['Internal','Pengikat kabel']
];
const wb=Workbook.create();""")
s=s.replace("const r=i+4;sum.getRange", """const hstart=end+5, hend=hstart+hardware.length-1;
 s.getRange(`A${end+3}:G${end+3}`).merge();s.getRange(`A${end+3}`).values=[['KELENGKAPAN HARDWARE']];s.getRange(`A${end+3}:G${end+3}`).format.fill='#DCE9F0';s.getRange(`A${end+3}:G${end+3}`).format.font.bold=true;
 s.getRange(`A${end+4}:G${end+4}`).values=[['Kelompok','Item','Butuh','Terpasang','Kondisi / catatan','Status','Verifikator']];s.getRange(`A${end+4}:G${end+4}`).format.fill='#244761';s.getRange(`A${end+4}:G${end+4}`).format.font.color='#FFFFFF';s.getRange(`A${end+4}:G${end+4}`).format.font.bold=true;
 s.getRange(`A${hstart}:G${hend}`).values=hardware.map(([g,label])=>[g,label,null,null,null,null,null]);s.getRange(`A${hstart}:G${hend}`).format.rowHeight=27;s.getRange(`C${hstart}:G${hend}`).format.fill='#FFF4D6';s.getRange(`B${hstart}:B${hend}`).format.wrapText=true;
 s.getRange(`F${hstart}:F${hend}`).dataValidation={rule:{type:'list',values:['OK','Belum OK','Belum dicek','N.A.']}};
 s.getRange(`A${end+3}:G${hend}`).format.font.name='Arial';s.getRange(`A${end+3}:G${hend}`).format.font.size=10;s.getRange('F:F').format.columnWidth=16;s.getRange('G:G').format.columnWidth=22;
 const hr=i+15;sum.getRange(`A${hr}`).values=[[name]];sum.getRange(`B${hr}:F${hr}`).formulas=[[
  `=COUNTIF('${name}'!F${hstart}:F${hend},"OK")`, `=COUNTIF('${name}'!F${hstart}:F${hend},"Belum OK")`, `=COUNTBLANK('${name}'!F${hstart}:F${hend})+COUNTIF('${name}'!F${hstart}:F${hend},"Belum dicek")`, `=COUNTIF('${name}'!F${hstart}:F${hend},"N.A.")`,
  `=COUNTIF('${name}'!F${hstart}:F${hend},"OK")+COUNTIF('${name}'!F${hstart}:F${hend},"N.A.")-COUNTIFS('${name}'!F${hstart}:F${hend},"OK",'${name}'!C${hstart}:C${hend},"<>",'${name}'!D${hstart}:D${hend},"<>",'${name}'!E${hstart}:E${hend},"<>",'${name}'!G${hstart}:G${hend},"<>")-COUNTIFS('${name}'!F${hstart}:F${hend},"N.A.",'${name}'!E${hstart}:E${hend},"<>",'${name}'!G${hstart}:G${hend},"<>")`]];
 const r=i+4;sum.getRange""")
s=s.replace("sum.getRange('A10:G10').merge();", """sum.getRange('A13:G13').merge();sum.getRange('A13').values=[['KELENGKAPAN HARDWARE']];sum.getRange('A13:G13').format.fill='#DCE9F0';sum.getRange('A13:G13').format.font.bold=true;
 sum.getRange('A15:F15').values=[['Unit','OK','Belum OK','Belum dicek / kosong','N.A.','Data belum lengkap']];sum.getRange('A15:F15').format.fill='#244761';sum.getRange('A15:F15').format.font.color='#FFFFFF';sum.getRange('A15:F15').format.font.bold=true;
 sum.getRange('A20:G20').merge();sum.getRange('A20').values=[['Hardware OK perlu jumlah butuh, terpasang, kondisi dan verifikator. N.A. perlu alasan dan verifikator.']];
 sum.getRange('A21:G21').merge();sum.getRange('A21').values=[['Cocokkan jumlah dengan BOM atau unit fisik; status OK tetap ditetapkan oleh verifikator.']];
 sum.getRange('A10:G10').merge();""")
s=s.replace('Checklist_Internal_3_GLD.xlsx','Checklist_Internal_3_GLD_Hardware.xlsx')
s=s.replace("['Ringkasan','A1:G11'],['GLD 1','A1:E20']", "['Ringkasan','A1:G21'],['GLD 1',`A${end+3}:G${end+15}`]")
s=s.replace('`${root}/${name}-revisi-preview.png`','`${root}/${name}-hardware-preview.png`')
Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/hardware.mjs').write_text(s,encoding='utf-8')
