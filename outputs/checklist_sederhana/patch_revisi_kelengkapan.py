from pathlib import Path
p=Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/contoh-ok.mjs')
s=p.read_text(encoding='utf-8-sig')
s=s.replace("const {items,hardware}=Function(defs+'; return {items,hardware};')();", """const {items,hardware}=Function(defs+'; return {items,hardware};')();
for (const r of items) {
 if(r[1]==='ID sensor board') r[1]='ID node GLD';
 if(r[1]==='Kondisi konektor antar-board') r[1]='Kondisi konektor internal';
 if(r[1]==='Konektor sensor board: kondisi dan kontinuitas') r[1]='Konektor sensor: kondisi dan kontinuitas';
}
for (let i=hardware.length-1;i>=0;i--) if(['Sensor board','Pengikat kabel'].includes(hardware[i][1])) hardware.splice(i,1);
for (const r of hardware) {
 if(r[1]==='Dudukan antena') r[1]='Sambungan dudukan antena ke PCB / board';
 if(r[1]==='Kabel dan konektor antar-board') r[1]='Kabel dan konektor internal';
}
const hwExamples={
 'Casing / main body':'1','Tutup casing':'1','Baut tutup casing':'3','Seal tutup casing':'1',
 'Buzzer / unit alarm':'1','Kabel dan konektor buzzer':'Baik; kabel tidak putus',
 'Antena LoRa':'1; pastikan antena LoRa','Kabel dan konektor antena':'Kondisi baik',
 'Sambungan dudukan antena ke PCB / board':'Foto; sambungan tidak terputus',
 'Board GLD':'1','Baut board ke casing':'4; terpasang','Spacer board ke casing':'4; terpasang',
 'MQ-2':'1','MQ-3':'1','MQ-4':'1','MQ-5':'1','MQ-6':'1','MQ-7':'1','MQ-8':'1','MQ-135':'1','Socket sensor MQ':'1',
 'Kipas':'1','Spacer kipas':'4','Baut kipas':'4; terhubung ke spacer','Kabel dan konektor kipas':'Kondisi baik',
 'Kabel power keluar casing (panjang: m)':'5 meter','Gland kabel power':'Terpasang','Konektor / terminal power':'Tidak longgar',
 'Kabel dan konektor internal':'Kondisi baik','Kabel grounding casing ke board':'Tes buzzer: tersambung'
};""")
s=s.replace("if(q.includes('id sensor'))return 'mis. SB-001';", "if(q.includes('id node gld'))return 'GLD-0x1001';")
s=s.replace("isHardware?[j+1,x[1],'Jumlah sesuai; baik',null,null,null,null,null]", "isHardware?[j+1,x[1],hwExamples[x[1]] ?? 'Kondisi baik',null,null,null,null,null]")
s=s.replace('Checklist_Internal_3_GLD_Contoh_OK.xlsx','Checklist_Internal_3_GLD_Revisi_Kelengkapan.xlsx').replace('contoh-sebelum-hasil.png','revisi-kelengkapan.png')
Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/revisi-kelengkapan.mjs').write_text(s,encoding='utf-8')
