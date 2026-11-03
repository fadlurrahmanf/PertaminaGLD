from pathlib import Path
p=Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/ch-besar.mjs');s=p.read_text(encoding='utf-8-sig')
a=s.index('const largeGroups=');b=s.index('\nconst wb=Workbook.create();',a)
s=s[:a]+'''const largeGroups={
'Casing':['Casing / badan','Tutup casing','Seal dan pengunci tutup'],
'Board CH':['Board CH','Konektor pada board'],
'Antena dan port':['Antena besar','Antena kecil','Port baterai','Port panel surya','Dudukan antena','Kabel dan konektor antena'],
'Baterai dan power':['Baterai dan konektor','Kabel power panel ke CH besar','Sealant kabel'],
'Panel surya':['Panel solar cell','Dudukan panel solar cell','Konektor paralel panel'],
'Mounting CH':['Dudukan U-bolt 4 inci','Mur dan baut U-bolt'],
'Dokumentasi':['Foto perangkat dan komponen','ID / nomor seri perangkat','Referensi BOM / form verifikasi'],
'Tiang - RU IV':['Tiang diameter 8 cm']
};
const largeReq={'Casing / badan':2,'Tutup casing':'Sesuai 2 casing','Seal dan pengunci tutup':'Utuh; tutup rapat','Board CH':3,'Antena besar':2,'Antena kecil':2,'Port baterai':2,'Port panel surya':2,'Dudukan antena':'Kuat; tidak lepas','Kabel dan konektor antena':'Kabel utuh; konektor kuat','Baterai dan konektor':2,'Kabel power panel ke CH besar':'Jumlah konfirmasi','Sealant kabel':2,'Panel solar cell':'Jumlah konfirmasi','Dudukan panel solar cell':'Jumlah sesuai panel','Konektor paralel panel':2,'Dudukan U-bolt 4 inci':2,'Mur dan baut U-bolt':4,'Tiang diameter 8 cm':'Diameter 8 cm'};
const largeHint={'Antena besar':'Pastikan antena LoRa','Antena kecil':'Pastikan antena LoRa','Baterai dan konektor':'2 set; baterai 4,2 V','Kabel power panel ke CH besar':'Kondisi baik; tidak putus','Sealant kabel':'2 untuk 2 CH','Panel solar cell':'2 panel per CH; cek total','Dudukan panel solar cell':'1 per panel','Konektor paralel panel':'2 untuk 2 CH','Dudukan U-bolt 4 inci':'2 buah; ukuran 4 inci','Mur dan baut U-bolt':'4 buah','Tiang diameter 8 cm':'Oleh RU IV'};''' + s[b:]
s=s.replace("s.getRange(`A${row}`).values=[[group.toUpperCase()]]", "s.getRange(`A${row}`).values=[[(name==='CH Besar'&&group!=='Dokumentasi'&&group!=='Tiang - RU IV'?'LGU - ':'')+group.toUpperCase()]]")
s=s.replace("(name==='CH Besar'?(largeExamples[v]??'Kondisi baik')", "(name==='CH Besar'?(largeHint[v]??largeExamples[v]??'Kondisi baik')")
s=s.replace('Checklist_Hardware_CH_Besar_Revisi.xlsx','Checklist_Hardware_CH_Pembagian_LGU_RU4.xlsx').replace('${name}-besar-revisi.png','${name}-lgu-ru4.png')
Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/ch-lgu-ru4.mjs').write_text(s,encoding='utf-8')
