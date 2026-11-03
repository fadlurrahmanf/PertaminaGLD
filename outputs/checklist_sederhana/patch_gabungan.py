from pathlib import Path
root=Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana')
gld=(root/'revisi-spacer.mjs').read_text(encoding='utf-8-sig')
ch=(root/'ch-panel-confirm.mjs').read_text(encoding='utf-8-sig')
defs=ch[ch.index('const groups='):ch.index('const wb=Workbook.create();')]
loop=ch[ch.index("for(const name of ['CH Kecil','CH Besar']){"):ch.index('\nwb.recalculate();')]
gld=gld.replace("const trial=wb.worksheets.getItem('GLD 1');", defs+'\n'+loop+"\nconst trial=wb.worksheets.getItem('GLD 1');")
gld=gld.replace('Checklist_Internal_3_GLD_Revisi_Spacer.xlsx','Checklist_GLD_dan_CH.xlsx').replace('revisi-spacer.png','gabungan-preview.png')
(root/'gabungan.mjs').write_text(gld,encoding='utf-8')
