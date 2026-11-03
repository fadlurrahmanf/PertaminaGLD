from pathlib import Path
p=Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/ch-kondisi.mjs');s=p.read_text(encoding='utf-8-sig')
s=s.replace("{A:8,B:35,C:23,D:27,E:10,F:30,G:15,H:20}","{A:7,B:38,C:30,D:32,E:11,F:32,G:16,H:22}")
s=s.replace("s.freezePanes.freezeRows(4);", "s.getRange(`D1:D${row}`).format.horizontalAlignment='center';s.getRange(`A1:H${row}`).format.verticalAlignment='center';s.freezePanes.freezeRows(4);")
s=s.replace('Checklist_Hardware_CH_Kondisi_Butuh.xlsx','Checklist_Hardware_CH_Kolom_Rapi.xlsx').replace('${name}-kondisi-preview.png','${name}-kolom-preview.png')
Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/ch-kolom.mjs').write_text(s,encoding='utf-8')
