from pathlib import Path
p=Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/ch-inventaris.mjs')
s=p.read_text(encoding='utf-8-sig')
s=s.replace("const wb=Workbook.create();", """const smallGroups={...groups,'Catu daya':['Kabel power panel ke CH','Konektor paralel panel','Konektor / terminal power','Gland kabel','Baterai'], 'Solar cell dan pemasangan':['Panel solar cell','Dudukan panel solar cell','Kabel dan konektor panel','Klem CH dan baut pemasangan']};
const qty={'Casing / badan':3,'Board CH':3,'Antena LoRa':3,'Baterai':3,'Panel solar cell':6,'Dudukan panel solar cell':6,'Kabel power panel ke CH':3,'Konektor paralel panel':3};
const hints={'Casing / badan':'1 per CH','Board CH':'1 per CH','Antena LoRa':'1 per CH','Baterai':'1 per CH','Panel solar cell':'2 per CH','Dudukan panel solar cell':'1 per panel','Kabel power panel ke CH':'1 per CH','Konektor paralel panel':'1 per CH'};
const wb=Workbook.create();""")
s=s.replace("[['ID CH']]", "[[name==='CH Kecil'?'ID CH (3 unit)':'ID CH']]")
s=s.replace("[['Daftar awal: cocokkan item dan jumlah dengan unit / BOM. N.A. beri alasan.']]", "[[name==='CH Kecil'?'Kebutuhan total untuk 3 CH kecil. Kolom Ada diisi setelah pemeriksaan.':'Daftar awal: cocokkan item dan jumlah dengan unit / BOM. N.A. beri alasan.']]")
s=s.replace("Object.entries(groups)", "Object.entries(name==='CH Kecil'?smallGroups:groups)")
s=s.replace("group==='Dokumentasi'?'Referensi tersedia':'Jumlah sesuai; baik',null,null,null,null,null", "name==='CH Kecil'&&hints[v]?hints[v]:(group==='Dokumentasi'?'Referensi tersedia':'Jumlah sesuai; baik'),name==='CH Kecil'?(qty[v]??null):null,null,null,null,null")
s=s.replace('Checklist_Hardware_CH_Kecil_Besar.xlsx','Checklist_Hardware_CH_Kebutuhan_3_Unit.xlsx').replace('${name}-preview.png','${name}-3-unit-preview.png')
Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/ch-tiga.mjs').write_text(s,encoding='utf-8')
