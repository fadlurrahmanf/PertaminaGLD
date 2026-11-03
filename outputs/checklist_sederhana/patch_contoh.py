from pathlib import Path
p=Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/tabel-terpisah.mjs')
s=p.read_text(encoding='utf-8-sig')
s=s.replace("s.getRange('A4:G4').merge();s.getRange('A4').values=[['Titik ukur, durasi dan kriteria uji mengikuti prosedur yang disepakati.']];", "s.getRange('A4:G4').merge();s.getRange('A4').values=[['Titik ukur, durasi dan kriteria uji mengikuti prosedur yang disepakati.']]; s.getRange('I4:M4').merge();s.getRange('I4').values=[['CONTOH SAJA — bukan hasil atau kriteria lulus.']];s.getRange('I4').format.font.italic=true;")
old="const col=isHardware?'F':'D';s.getRange(`${col}${from}:${col}${to}`).dataValidation={rule:{type:'list',values:['OK','Belum OK','Belum dicek','N.A.']}};row=to+3;return {from,to};"
new='''const col=isHardware?'F':'D';s.getRange(`${col}${from}:${col}${to}`).dataValidation={rule:{type:'list',values:['OK','Belum OK','Belum dicek','N.A.']}};
  const ec=isHardware?'M':'K';s.getRange(`I${from-1}:${ec}${from-1}`).values=[isHardware?['Contoh butuh','Contoh terpasang','Contoh kondisi','Contoh status','Contoh verifikator']:['Contoh hasil','Contoh status','Contoh verifikator']];s.getRange(`I${from-1}:${ec}${from-1}`).format.fill='#D9E8D7';s.getRange(`I${from-1}:${ec}${from-1}`).format.font.bold=true;
  function example(label){const q=label.toLowerCase(); if(q.includes('nulling (v)'))return '0,05 V'; if(q.includes('tegangan')&&q.includes('input'))return '24 VDC';if(q.includes('tegangan'))return '3,30 V';if(q.includes('arus / daya'))return '0,25 A / 6 W';if(q.includes('lama uji'))return '2 jam; tidak restart';if(q.includes('panjang'))return '5 m';if(q.includes('foto'))return 'foto_GLD1.jpg';if(q.includes('form')||q.includes('dokumen'))return 'Form GLD-01';if(q.includes('firmware'))return 'v1.2.3';if(q.includes('frekuensi')||q.includes('konfigurasi lora'))return '921 MHz; SF7';if(q.includes('tujuan'))return 'CH-01';if(q.includes('id sensor'))return 'SB-001';if(q.includes('inferensi'))return 'Berjalan; hasil normal';if(q.includes('responsif'))return 'Nilai berubah saat diuji';if(q.includes('terbaca'))return 'Terbaca';if(q.includes('boot'))return 'Boot normal';if(q.includes('kontinuitas'))return 'Terhubung; buzzer';return 'Baik / berfungsi';}
  const examples=records.map(x=>isHardware?[1,1,'Baik','OK','Nama pemeriksa']:[example(x[1]),'OK','Nama pemeriksa']);s.getRange(`I${from}:${ec}${to}`).values=examples;s.getRange(`I${from}:${ec}${to}`).format.font.color='#526253';
  row=to+3;return {from,to};'''
assert old in s
s=s.replace(old,new)
s=s.replace("s.getRange(`A1:G${row}`).format.font.name='Arial';s.getRange(`A1:G${row}`).format.font.size=10;", "s.getRange(`A1:M${row}`).format.font.name='Arial';s.getRange(`A1:M${row}`).format.font.size=10;")
s=s.replace("{A:9,B:50,C:34,D:15,E:22,F:16,G:22}","{A:9,B:50,C:34,D:15,E:22,F:16,G:22,H:5,I:22,J:19,K:21,L:18,M:22}")
s=s.replace("['GLD 1','A1:G25']", "['GLD 1','A1:M25']")
s=s.replace('tabel-terpisah.png','contoh-pengisian.png').replace('Checklist_Internal_3_GLD_Tabel_Terpisah.xlsx','Checklist_Internal_3_GLD_Contoh.xlsx')
Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/contoh.mjs').write_text(s,encoding='utf-8')
