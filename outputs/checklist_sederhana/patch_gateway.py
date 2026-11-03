from pathlib import Path
p=Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/gabungan-ringkasan.mjs');s=p.read_text(encoding='utf-8-sig')
insert='''
const gw=wb.worksheets.add('Gateway');gw.showGridLines=false;
gw.getRange('A1:H1').merge();gw.getRange('A1').values=[['CHECKLIST HARDWARE GATEWAY']];gw.getRange('A2').values=[['ID Gateway']];gw.getRange('C2').values=[['Tanggal']];gw.getRange('B2').format.fill='#FFF4D6';gw.getRange('D2').format.fill='#FFF4D6';
gw.getRange('A3:H3').merge();gw.getRange('A3').values=[['Daftar awal: cocokkan jumlah dan kelengkapan dengan unit / BOM. N.A. beri alasan.']];
const gwGroups={
 'LGU - Gateway':['Unit / board Gateway','Casing dan penutup','Konektor pada board'],
 'LGU - Antena':['Antena LoRa','Dudukan antena','Kabel dan konektor antena'],
 'LGU - Catu daya':['Adaptor 5 VDC','Kabel dan konektor adaptor'],
 'RU IV - Pemasangan':['Dudukan Gateway','Outlet dari UPS'],
 'Dokumentasi':['ID / nomor seri Gateway','Foto perangkat dan komponen','Referensi verifikasi']
};
const gwReq={'Unit / board Gateway':'Unit tersedia; fisik baik','Casing dan penutup':'Lengkap; dapat ditutup','Konektor pada board':'Baik; tidak longgar','Antena LoRa':'Antena LoRa tersedia; utuh','Dudukan antena':'Terpasang; kuat','Kabel dan konektor antena':'Kabel utuh; konektor kuat','Adaptor 5 VDC':'Adaptor 5 VDC tersedia','Kabel dan konektor adaptor':'Kabel utuh; konektor baik','Dudukan Gateway':'Dudukan tersedia; kokoh','Outlet dari UPS':'Outlet UPS tersedia','ID / nomor seri Gateway':'ID tercatat','Foto perangkat dan komponen':'Foto jelas; tersedia','Referensi verifikasi':'Referensi tersedia'};
let gr=5,gwCount=0;for(const [group,arr] of Object.entries(gwGroups)){
 gw.getRange(`A${gr}:H${gr}`).merge();gw.getRange(`A${gr}`).values=[[group.toUpperCase()]];gw.getRange(`A${gr}:H${gr}`).format.fill='#DCE9F0';gw.getRange(`A${gr}:H${gr}`).format.font.bold=true;gr++;
 gw.getRange(`A${gr}:H${gr}`).values=[['No','Item','Contoh OK','Butuh','Ada','Kondisi / foto','Status','Verifikator']];gw.getRange(`A${gr}:H${gr}`).format.fill='#244761';gw.getRange(`A${gr}:H${gr}`).format.font.color='#FFFFFF';gw.getRange(`A${gr}:H${gr}`).format.font.bold=true;gr++;
 const from=gr,to=gr+arr.length-1;gw.getRange(`A${from}:H${to}`).values=arr.map((x,i)=>[i+1,x,gwReq[x],gwReq[x],null,null,null,null]);gw.getRange(`A${from}:H${to}`).format.rowHeight=34;gw.getRange(`B${from}:D${to}`).format.wrapText=true;gw.getRange(`C${from}:C${to}`).format.fill='#E9F2E7';gw.getRange(`D${from}:H${to}`).format.fill='#FFF4D6';gw.getRange(`G${from}:G${to}`).dataValidation={rule:{type:'list',values:['OK','Belum OK','Belum dicek','N.A.']}};gwCount+=arr.length;gr=to+3;
}
gw.getRange(`A1:H${gr}`).format.font.name='Arial';gw.getRange(`A1:H${gr}`).format.font.size=10;gw.getRange('A1').format.font.size=14;gw.getRange('A1').format.font.bold=true;for(const [c,w] of Object.entries({A:8,B:35,C:27,D:30,E:11,F:30,G:16,H:22}))gw.getRange(`${c}:${c}`).format.columnWidth=w;gw.getRange(`D1:D${gr}`).format.horizontalAlignment='center';gw.freezePanes.freezeRows(3);
summary.getRange('A28:G28').merge();summary.getRange('A28').values=[['RINGKASAN GATEWAY']];summary.getRange('A28:G28').format.fill='#DCE9F0';summary.getRange('A28:G28').format.font.bold=true;
summary.getRange('A30:G30').values=[['Perangkat','ID Gateway','OK','Belum OK','Belum dicek','N.A.','Data kurang']];summary.getRange('A30:G30').format.fill='#244761';summary.getRange('A30:G30').format.font.color='#FFFFFF';summary.getRange('A30:G30').format.font.bold=true;summary.getRange('A31').values=[['Gateway']];summary.getRange('B31').formulas=[['=IF(Gateway!B2="","",Gateway!B2)']];
const sg=`Gateway!G5:G${gr}`,sc=`Gateway!F5:F${gr}`,sv=`Gateway!H5:H${gr}`;
summary.getRange('C31:G31').formulas=[[`=COUNTIF(${sg},"OK")`,`=COUNTIF(${sg},"Belum OK")`,`=${gwCount}-COUNTIF(${sg},"OK")-COUNTIF(${sg},"Belum OK")-COUNTIF(${sg},"N.A.")`,`=COUNTIF(${sg},"N.A.")`,`=COUNTIF(${sg},"OK")+COUNTIF(${sg},"N.A.")-COUNTIFS(${sg},"OK",${sc},"<>",${sv},"<>")-COUNTIFS(${sg},"N.A.",${sc},"<>",${sv},"<>")`]];
summary.getRange('A33:G33').merge();summary.getRange('A33').values=[['Data kurang: item OK / N.A. belum memiliki kondisi atau alasan dan nama verifikator.']];summary.getRange('A28:G33').format.font.name='Arial';summary.getRange('A28:G33').format.font.size=10;
gw.getRange('G7').values=[['OK']];wb.recalculate();console.log('Gateway incomplete',summary.getRange('C31:G31').values);gw.getRange('F7').values=[['Baik']];gw.getRange('H7').values=[['Tester']];wb.recalculate();console.log('Gateway complete',summary.getRange('C31:G31').values);gw.getRange('F7:H7').clear({applyTo:'contents'});
'''
s=s.replace("const chtrial=wb.worksheets.getItem('CH Kecil');",insert+"\nconst chtrial=wb.worksheets.getItem('CH Kecil');")
s=s.replace('RINGKASAN PEMERIKSAAN GLD DAN CH','RINGKASAN PEMERIKSAAN GLD, CH DAN GATEWAY')
s=s.replace("['Ringkasan','A1:G26'],['GLD 1','A1:G25']", "['Ringkasan','A1:G33'],['Gateway','A1:H21']")
s=s.replace('Checklist_GLD_dan_CH_Ringkasan.xlsx','Checklist_GLD_CH_Gateway.xlsx').replace('ringkasan-ch-preview.png','gateway-preview.png')
Path(r'D:/Github/PertaminaGLD/outputs/checklist_sederhana/gabungan-gateway.mjs').write_text(s,encoding='utf-8')
