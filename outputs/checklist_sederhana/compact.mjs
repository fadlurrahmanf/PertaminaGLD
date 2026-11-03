import fs from 'node:fs/promises';
import {Workbook, SpreadsheetFile} from '@oai/artifact-tool';
const root='D:/Github/PertaminaGLD/outputs/checklist_sederhana';
const data=JSON.parse(await fs.readFile(root+'/data.json','utf8')); const all=Object.values(data).flat();
const groups={
'GL Detector':{'L-01':'Unit, nomor seri dan fungsi GLD','L-02':'Gland M20 × 1,5 untuk kabel 2C 16 AWG','L-03':'Antena, ID node dan frekuensi LoRa','L-13':'Prosedur terminasi, polaritas dan tegangan','L-21':'Ukur polaritas dan tegangan; nyalakan GLD','R-01':'Stanchion 2 inci tegak dan kokoh','R-02':'Pasang GLD dan cek tinggi sensor','R-03':'Pasang dan grounding junction box SS316','R-04':'PSU 220 VAC / 24 VDC, ≥ 1 A per GLD','R-05':'Sumber 220 VAC, MCB dan L/N/PE','R-06':'Pasang kabel daya 2C 16 AWG','R-07':'Masukkan dan kencangkan kabel pada gland'},
'Cluster Head':{'L-04':'Unit CH dan konfigurasi star / mesh','L-05':'Solar cell, bracket dan klem CH','L-19':'Pembagian tiang, bracket dan klem CH','R-08':'Pasang CH dan panel; cek line of sight','R-09':'Pasang dan cor tiang 2 inci Sch40, 4 m'},
'Gateway':{'L-06':'Unit Gateway, frekuensi dan penerimaan CH','L-07':'Adaptor Gateway 5 VDC','R-10':'Pasang dudukan; cek jangkauan antena'},
'Router dan LAN':{'L-08':'Router 2,4 GHz, SSID dan WPA2','L-09':'Adaptor router','L-10':'Serahkan skema jaringan dan spesifikasi Cat6','R-16':'Pasang dan beri label Cat6 (≤ 90 m)'},
'UPS':{'R-11':'Kapasitas dan waktu cadangan UPS','R-12':'Outlet UPS untuk Gateway, router dan server'},
'Server':{'L-11':'Siapkan broker, backend dan dashboard','L-22':'Pasang dan jalankan aplikasi di server','R-13':'Sediakan PC server','R-14':'Siapkan ruang dan akses tim LGU','R-15':'Port intranet, persetujuan IT dan akses dashboard'},
'Uji Sistem':{'L-14':'Uji LoRa GLD–CH; ukur PDR dan RSSI','L-15':'Uji LoRa CH–Gateway, mesh dan failover','L-16':'Uji WiFi Gateway–router','L-17':'Uji data dan alarm di laboratorium','L-23':'Commissioning: link, alarm dan waktu respons','R-18':'Saksikan commissioning dan uji alarm'},
'Persiapan dan Serah Terima':{'L-12':'Serahkan dokumen pembagian tugas dan instalasi','L-18':'Periksa kesiapan LGU dan ITB','L-20':'Supervisi pemasangan dan foto tiap titik','L-24':'Siapkan foto, nomor seri dan hasil uji','R-17':'Izin masuk, izin kerja, TRA/JSA dan klasifikasi area','R-19':'Tandatangani berita acara instalasi dan commissioning'}
};
const wb=Workbook.create(); let seen=[];
for(const [name,items] of Object.entries(groups)){
 const s=wb.worksheets.add(name);s.showGridLines=false;s.getRange('A1:E1').merge();s.getRange('A1').values=[[name.toUpperCase()]];s.getRange('A2:E2').merge();s.getRange('A2').values=[['Status mengikuti file asal per 28 Oktober 2026. Detail dan bukti: lihat file asal.']];
 let row=4;
 for(const party of ['LGU','RU IV']){
  const entries=Object.entries(items).filter(([id])=>id.startsWith(party==='LGU'?'L-':'R-'));if(!entries.length)continue;
  s.getRange(`A${row}:E${row}`).merge();s.getRange(`A${row}`).values=[[party]];s.getRange(`A${row}:E${row}`).format.fill='#DCE9F0';s.getRange(`A${row}:E${row}`).format.font.bold=true;row++;
  s.getRange(`A${row}:E${row}`).values=[['No','Yang dicek','Status','PIC','Catatan']];s.getRange(`A${row}:E${row}`).format.fill='#244761';s.getRange(`A${row}:E${row}`).format.font.color='#FFFFFF';s.getRange(`A${row}:E${row}`).format.font.bold=true;row++;
  const start=row;const out=entries.map(([id,label])=>{const r=all.find(x=>x[0]===id);if(!r)throw Error(id);seen.push(id);return [id,label,r[6],r[7],r[10]]});s.getRange(`A${row}:E${row+out.length-1}`).values=out;row+=out.length;
  s.getRange(`A${start}:E${row-1}`).format.wrapText=true;s.getRange(`A${start}:E${row-1}`).format.rowHeight=40;s.getRange(`C${start}:C${row-1}`).dataValidation={rule:{type:'list',values:['Belum','Proses','Menunggu','Selesai','N.A.']}};row+=2;
 }
 s.getRange(`A1:E${row}`).format.font.name='Arial';s.getRange(`A1:E${row}`).format.font.size=11;s.getRange('A1').format.font.size=14;s.getRange('A1').format.font.bold=true;
 for(const [c,w] of Object.entries({A:10,B:58,C:14,D:14,E:47}))s.getRange(`${c}:${c}`).format.columnWidth=w;
}
if(seen.length!==43||new Set(seen).size!==43)throw Error('Missing or duplicate items');wb.recalculate();
for(const n of ['GL Detector','Cluster Head']){const p=await wb.render({sheetName:n,range:'A1:E15',scale:1,format:'png'});await fs.writeFile(`${root}/${n}-simple.png`,new Uint8Array(await p.arrayBuffer()));}
const f=await SpreadsheetFile.exportXlsx(wb);await f.save(root+'/Checklist_Per_Komponen_Ringkas.xlsx');console.log('43 items in 8 separate component sheets');
