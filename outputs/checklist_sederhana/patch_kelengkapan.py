from pathlib import Path
p=Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/hardware.mjs')
s=p.read_text(encoding='utf-8-sig')
a=s.index('const hardware = ['); b=s.index('\nconst wb=Workbook.create();',a)
s=s[:a]+'''const hardware = [
 ['Casing','Casing / main body'],['Casing','Tutup casing'],['Casing','Baut tutup casing'],['Casing','Seal tutup casing'],
 ['Alarm','Buzzer / unit alarm'],['Alarm','Kabel dan konektor buzzer'],
 ['LoRa','Antena LoRa'],['LoRa','Kabel dan konektor antena'],['LoRa','Dudukan antena'],
 ['Board','Board GLD'],['Board','Sensor board'],['Board','Baut board ke casing'],['Board','Spacer board ke casing'],
 ...['MQ-2','MQ-3','MQ-4','MQ-5','MQ-6','MQ-7','MQ-8','MQ-135'].map(x=>['Sensor MQ',x]),
 ['Sensor MQ','Socket sensor MQ'],['Kipas','Kipas'],['Kipas','Spacer kipas'],['Kipas','Baut kipas'],['Kipas','Kabel dan konektor kipas'],
 ['Power','Kabel power keluar casing (panjang: m)'],['Power','Gland kabel power'],['Power','Konektor / terminal power'],
 ['Internal','Kabel dan konektor antar-board'],['Internal','Kabel grounding casing ke board'],['Internal','Pengikat kabel']
];''' + s[b:]
s=s.replace('Checklist_Internal_3_GLD_Hardware.xlsx','Checklist_Internal_3_GLD_Kelengkapan.xlsx')
s=s.replace('hardware-preview.png','kelengkapan-preview.png')
Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/kelengkapan.mjs').write_text(s,encoding='utf-8')
