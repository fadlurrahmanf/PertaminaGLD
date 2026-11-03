from pathlib import Path
p=Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/ch-butuh.mjs');s=p.read_text(encoding='utf-8-sig')
s=s.replace("const wb=Workbook.create();", """const kebutuhanKondisi={
'Casing / badan':'Utuh; tidak retak','Tutup casing':'Utuh; dapat ditutup','Seal dan pengunci tutup':'Seal utuh; terkunci rapat','Board CH':'Tersedia; fisik baik','Baut board':'Lengkap; terpasang kencang','Spacer board':'Lengkap; terpasang','Konektor pada board':'Baik; tidak longgar',
'Antena LoRa':'Antena LoRa utuh','Dudukan antena':'Baik; tidak longgar','Kabel dan konektor antena':'Kabel utuh; konektor kuat',
'Kabel power':'Kabel utuh; tidak putus','Kabel power panel ke CH':'Kabel utuh; tidak putus','Konektor ke charger':'Baik; tidak longgar','Konektor / terminal power':'Baik; tidak longgar','Gland kabel':'Terpasang; rapat','Baterai, jika digunakan':'Kondisi fisik baik','Baterai':'Kondisi fisik baik',
'Panel solar cell':'Panel utuh; tidak retak','Dudukan panel solar cell':'Terpasang; kokoh','Konektor paralel panel':'Sesuai; kondisi baik','Kabel dan konektor panel':'Kabel utuh; konektor baik','Bracket panel':'Lengkap; kokoh','Klem CH dan baut pemasangan':'Lengkap; terpasang kuat',
'Foto perangkat dan komponen':'Foto jelas; tersedia','ID / nomor seri perangkat':'ID tercatat','ID CH yang sudah OK':'ID CH yang OK tercatat','Referensi BOM / form verifikasi':'Referensi tersedia'
};
const wb=Workbook.create();""")
s=s.replace("(qty[v]??'Cek')", "(qty[v]??kebutuhanKondisi[v]??'Konfirmasi sesuai unit')")
s=s.replace("?'1 per CH':'Cek')", "?'1 per CH':(kebutuhanKondisi[v]??'Konfirmasi sesuai unit'))")
s=s.replace('Cek = jumlah belum ditentukan; isi setelah konfirmasi unit atau BOM.','Butuh berisi jumlah atau kondisi yang harus dipenuhi; jumlah lain konfirmasi ke BOM.')
s=s.replace("format.rowHeight=28", "format.rowHeight=34")
s=s.replace("s.getRange(`B${from}:C${end}`).format.wrapText=true", "s.getRange(`B${from}:D${end}`).format.wrapText=true")
s=s.replace("{A:8,B:35,C:23,D:10,E:10,F:30,G:15,H:20}","{A:8,B:35,C:23,D:27,E:10,F:30,G:15,H:20}")
s=s.replace('Checklist_Hardware_CH_Butuh_Lengkap.xlsx','Checklist_Hardware_CH_Kondisi_Butuh.xlsx').replace('${name}-butuh-preview.png','${name}-kondisi-preview.png')
Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/ch-kondisi.mjs').write_text(s,encoding='utf-8')
