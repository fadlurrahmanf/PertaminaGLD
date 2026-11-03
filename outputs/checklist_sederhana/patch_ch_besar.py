from pathlib import Path
p=Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/ch-kolom.mjs');s=p.read_text(encoding='utf-8-sig')
s=s.replace("const wb=Workbook.create();", """const largeGroups={...groups,'Board CH':['Board CH','Konektor pada board'],'Catu daya':['Kabel power','Konektor / terminal power','Baterai']};
const largeReq={'Casing / badan':1,'Tutup casing':'1; dapat ditutup','Seal dan pengunci tutup':'Seal utuh; tutup rapat','Board CH':3,'Antena LoRa':'Pastikan antena LoRa','Dudukan antena':'Kuat; tidak lepas','Baterai':'4,2 V','Panel solar cell':'Utuh; tidak rusak; ada tegangan'};
const wb=Workbook.create();""")
s=s.replace("Object.entries(name==='CH Kecil'?smallGroups:groups)","Object.entries(name==='CH Kecil'?smallGroups:largeGroups)")
s=s.replace("(['Foto perangkat dan komponen','ID / nomor seri perangkat','Referensi BOM / form verifikasi'].includes(v)?'1 per CH':(kebutuhanKondisi[v]??'Konfirmasi sesuai unit'))", "(largeReq[v]??(['Foto perangkat dan komponen','ID / nomor seri perangkat','Referensi BOM / form verifikasi'].includes(v)?'1 per CH':(kebutuhanKondisi[v]??'Konfirmasi sesuai unit')))")
s=s.replace('Checklist_Hardware_CH_Kolom_Rapi.xlsx','Checklist_Hardware_CH_Besar_Revisi.xlsx').replace('${name}-kolom-preview.png','${name}-besar-revisi.png')
Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/ch-besar.mjs').write_text(s,encoding='utf-8')
