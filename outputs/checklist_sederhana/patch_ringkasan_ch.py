from pathlib import Path
p=Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/gabungan.mjs');s=p.read_text(encoding='utf-8-sig')
insert='''
summary.getRange('A20:G20').merge();summary.getRange('A20').values=[['RINGKASAN CH']];summary.getRange('A20:G20').format.fill='#DCE9F0';summary.getRange('A20:G20').format.font.bold=true;
summary.getRange('A22:G22').values=[['Jenis','ID CH','OK','Belum OK','Belum dicek','N.A.','Data kurang']];summary.getRange('A22:G22').format.fill='#244761';summary.getRange('A22:G22').format.font.color='#FFFFFF';summary.getRange('A22:G22').format.font.bold=true;
for(const [name,r,gs] of [['CH Kecil',23,smallGroups],['CH Besar',24,largeGroups]]){
 const n=Object.values(gs).reduce((a,x)=>a+x.length,0);const last=wb.worksheets.getItem(name).getUsedRange().address;const range=`'${name}'!G6:G200`,condition=`'${name}'!F6:F200`,verifier=`'${name}'!H6:H200`;
 summary.getRange(`A${r}`).values=[[name]];summary.getRange(`B${r}`).formulas=[[`=IF('${name}'!B2="","",'${name}'!B2)`]];
 summary.getRange(`C${r}:G${r}`).formulas=[[
 `=COUNTIF(${range},"OK")`, `=COUNTIF(${range},"Belum OK")`, `=${n}-COUNTIF(${range},"OK")-COUNTIF(${range},"Belum OK")-COUNTIF(${range},"N.A.")`, `=COUNTIF(${range},"N.A.")`,
 `=COUNTIF(${range},"OK")+COUNTIF(${range},"N.A.")-COUNTIFS(${range},"OK",${condition},"<>",${verifier},"<>")-COUNTIFS(${range},"N.A.",${condition},"<>",${verifier},"<>")`]];
}
summary.getRange('A26:G26').merge();summary.getRange('A26').values=[['Data kurang: item OK / N.A. belum memiliki kondisi atau alasan dan nama verifikator.']];
summary.getRange('A20:G26').format.font.name='Arial';summary.getRange('A20:G26').format.font.size=10;
const chtrial=wb.worksheets.getItem('CH Kecil');chtrial.getRange('G8').values=[['OK']];wb.recalculate();console.log('CH trial incomplete',summary.getRange('C23:G23').values);chtrial.getRange('F8').values=[['Baik']];chtrial.getRange('H8').values=[['Tester']];wb.recalculate();console.log('CH trial complete',summary.getRange('C23:G23').values);chtrial.getRange('F8:H8').clear({applyTo:'contents'});
'''
s=s.replace("const trial=wb.worksheets.getItem('GLD 1');",insert+"\nconst trial=wb.worksheets.getItem('GLD 1');")
s=s.replace("['Ringkasan','A1:G18']","['Ringkasan','A1:G26']")
s=s.replace('Checklist_GLD_dan_CH.xlsx','Checklist_GLD_dan_CH_Ringkasan.xlsx').replace('gabungan-preview.png','ringkasan-ch-preview.png')
Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/gabungan-ringkasan.mjs').write_text(s,encoding='utf-8')
