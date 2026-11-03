from pathlib import Path
p=Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/ch-charger.mjs');s=p.read_text(encoding='utf-8-sig')
s=s.replace("name==='CH Kecil'?(qty[v]??null):(['Foto perangkat dan komponen','ID / nomor seri perangkat','Referensi BOM / form verifikasi'].includes(v)?'1 per CH':null)","name==='CH Kecil'?(qty[v]??'Cek'):(['Foto perangkat dan komponen','ID / nomor seri perangkat','Referensi BOM / form verifikasi'].includes(v)?'1 per CH':'Cek')")
s=s.replace('Contoh bersifat ilustrasi; catat kondisi dan referensi foto pada kolom hasil.','Cek = jumlah belum ditentukan; isi setelah konfirmasi unit atau BOM.')
s=s.replace('Checklist_Hardware_CH_Revisi_Charger.xlsx','Checklist_Hardware_CH_Butuh_Lengkap.xlsx').replace('${name}-charger-preview.png','${name}-butuh-preview.png')
Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/ch-butuh.mjs').write_text(s,encoding='utf-8')
