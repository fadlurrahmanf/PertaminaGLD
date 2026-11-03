from pathlib import Path
p=Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/ch-power.mjs')
s=p.read_text(encoding='utf-8-sig')
s=s.replace("'Catu daya':['Kabel power panel ke CH','Konektor / terminal power','Baterai']", "'Catu daya':['Kabel power panel ke CH','Konektor ke charger','Baterai']")
s=s.replace("'Konektor / terminal power':1", "'Konektor ke charger':1")
s=s.replace("'Konektor / terminal power':'Konektor power baik','Klem", "'Konektor ke charger':'Kondisi baik; tidak longgar','Klem")
s=s.replace("name==='CH Kecil'?(qty[v]??null):null", "name==='CH Kecil'?(qty[v]??null):(['Foto perangkat dan komponen','ID / nomor seri perangkat','Referensi BOM / form verifikasi'].includes(v)?'1 per CH':null)")
s=s.replace('Checklist_Hardware_CH_Revisi_Power.xlsx','Checklist_Hardware_CH_Revisi_Charger.xlsx').replace('${name}-power-preview.png','${name}-charger-preview.png')
Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/ch-charger.mjs').write_text(s,encoding='utf-8')
