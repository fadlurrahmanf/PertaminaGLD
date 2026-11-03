from pathlib import Path
p=Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/kelengkapan.mjs')
s=p.read_text(encoding='utf-8-sig')
s=s.replace("add('Fan','Fan menyala dan berputar normal');", """add('Fan','Fan menyala dan berputar normal');
add('Kebutuhan power','Kebutuhan tegangan input (VDC)','Kebutuhan arus / daya (A / W)','Arus / daya terukur (A / W; kondisi uji)');
add('Mode inferensi','Mode inferensi berjalan','Hasil inferensi / masalah');
add('Mode nulling','Mode nulling berjalan','Nulling selesai; catat hasil dan masalah');
add('Dokumen verifikasi','Form verifikasi node GLD','Foto komponen dan board','Foto sensor dan socket','Foto casing, fan dan sambungan','Dokumen kebutuhan power','Hasil uji inferensi dan nulling');""")
s=s.replace("'Hasil inferensi dan masalah',",'')
s=s.replace('Checklist_Internal_3_GLD_Kelengkapan.xlsx','Checklist_Internal_3_GLD_Verifikasi.xlsx')
s=s.replace('kelengkapan-preview.png','verifikasi-preview.png')
Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/verifikasi.mjs').write_text(s,encoding='utf-8')
