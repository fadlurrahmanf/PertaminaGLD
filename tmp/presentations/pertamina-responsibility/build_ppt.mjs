import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const OUT="D:/Github/PertaminaGLD/output/presentation/PertaminaGLD-Pembagian-Tugas-LGU-Pertamina.pptx";
const RENDER="D:/Github/PertaminaGLD/tmp/presentations/pertamina-responsibility/rendered";
const W=1280,H=720;
const C={ink:"#111827",muted:"#5F6670",blue:"#246BFD",green:"#268A5E",pale:"#DDEEFF",panel:"#F1F3F5",rule:"#C4C9D0",amber:"#FFF4D7",white:"#FFFFFF"};
const deck=Presentation.create({slideSize:{width:W,height:H}});

function box(s,x,y,w,h,fill=C.panel,line=C.rule,name="box"){
  return s.shapes.add({geometry:"rect",name,position:{left:x,top:y,width:w,height:h},fill,line:{style:"solid",fill:line,width:1}});
}
function tx(s,text,x,y,w,h,size=20,o={}){
  const sh=s.shapes.add({geometry:"textbox",name:o.name||"text",position:{left:x,top:y,width:w,height:h},fill:"none",line:{style:"solid",fill:"none",width:0}});
  sh.text=text; sh.text.style={fontSize:size,typeface:"Arial",color:o.color||C.ink,bold:!!o.bold,alignment:o.align||"left",verticalAlignment:o.valign||"top",autoFit:o.autoFit||"shrinkText"}; return sh;
}
function title(s,text,no){tx(s,text,42,32,1160,70,39,{bold:true,name:"slide-title"});tx(s,String(no).padStart(2,"0"),1185,665,50,22,13,{align:"right",color:C.muted,name:"page"});}
function bullets(s,items,x,y,w,lineH=62,size=20,color=C.blue){items.forEach((v,i)=>{box(s,x,y+i*lineH+8,9,9,color,color,`bullet-${i}`);tx(s,v,x+25,y+i*lineH,w-25,lineH-3,size,{name:`bullet-text-${i}`});});}
function notes(s,arr){s.speakerNotes.textFrame.setText(`[Sources]\n${arr.join("\n")}`);}
function twoCol(s,leftTitle,leftItems,rightTitle,rightItems,y=145,h=430,lineH=76,bodySize=19){box(s,42,y,560,h,C.panel,C.rule,"left-panel");box(s,630,y,608,h,C.pale,C.rule,"right-panel");tx(s,leftTitle,64,y+24,510,38,24,{bold:true,color:C.blue});tx(s,rightTitle,652,y+24,558,60,24,{bold:true,color:C.blue});bullets(s,leftItems,64,y+88,510,lineH,bodySize,C.blue);bullets(s,rightItems,652,y+88,545,lineH,bodySize,C.green);}

// 1 Cover
{
 const s=deck.slides.add();s.background.fill=C.white;
 tx(s,"PERTAMINA × LGU",42,42,420,36,24,{bold:true,color:C.muted});
 tx(s,"Kebutuhan Lapangan dan\nPembagian Tugas Integrasi",42,165,1040,175,59,{bold:true});
 tx(s,"GLD · CH · Gateway · Server",42,380,800,52,30,{bold:true,color:C.blue});
 tx(s,"Dokumen koordinasi sebelum pemasangan lapangan",42,492,700,45,24,{color:C.muted});
 box(s,990,492,200,8,C.blue,C.blue,"accent");tx(s,"13 Agustus 2026",42,610,300,30,17,{color:C.muted});
 notes(s,["Poin revisi pengguna, 13 Agustus 2026.","PDF sumber: output/pdf/PertaminaGLD-Pembagian-Tugas-LGU-Pertamina.pdf"]);
}

// 2 GLD
{
 const s=deck.slides.add();title(s,"GLD: suplai 24 VDC kontinu harus diverifikasi di lokasi",2);
 tx(s,"Kebutuhan LGU",42,128,420,35,24,{bold:true,color:C.blue});
 bullets(s,["Suplai 24 VDC dengan kapasitas minimal 2 A yang tersedia secara kontinu.","Pemasangan direncanakan dekat sensor existing agar memanfaatkan sumber daya tersedia.","Battery GLD belum siap untuk operasi kontinu; optimasi power management masih dikembangkan."],42,180,548,98,20,C.blue);
 box(s,630,130,550,325,C.pale,C.rule,"pertamina-power");tx(s,"Konfirmasi Pertamina",654,154,500,35,24,{bold:true,color:C.green});
 bullets(s,["Pastikan kapasitas sisa sumber existing cukup untuk sensor existing dan GLD.","Berikan titik terminal, polaritas, proteksi, grounding, konektor dan standar kabel.","Lakukan verifikasi tegangan/arus dan setujui titik pengambilan daya."],654,210,500,77,20,C.green);
 box(s,42,510,1138,92,C.amber,C.rule,"boundary");tx(s,"Batas penerapan",62,528,260,32,22,{bold:true,color:C.blue});tx(s,"Tahap lapangan saat ini menggunakan 24 VDC. Opsi baterai tidak diposisikan sebagai sumber kontinu sampai optimasi selesai dan hasil pengembangan divalidasi.",300,524,850,50,20,{bold:true});
 notes(s,["Poin revisi pengguna - sisi GLD.","Static repo evidence does not prove 2 A site capacity or field readiness."]);
}

// 3 CH
{
 const s=deck.slides.add();title(s,"CH: desain LGU mengikuti struktur existing, instalasi fisik oleh Pertamina",3);
 tx(s,"Mounting CH dan panel surya disesuaikan dengan tiang atau handrail existing di area Pertamina.",42,112,1120,40,22,{color:C.muted});
 const rows=[
  ["01","Desain mounting","LGU membuat mounting berdasarkan foto, ukuran dan kondisi struktur existing."],
  ["02","Panel surya","LGU memilih panel tersertifikasi; Pertamina menentukan sertifikasi yang diterima."],
  ["03","Instalasi lapangan","Tim Pertamina melaksanakan instalasi dengan personel dan tools yang sesuai."],
  ["04","Mur, baut, kunci","Pertamina memberikan standar fastener dan ukuran kunci pas yang digunakan."],
  ["05","Batas pemasangan","Pertamina memberi batas tinggi antenna, area berbahaya dan jalur yang diizinkan."],
  ["06","Kabel panel–CH","Pertamina memberi jenis kabel, konektor, proteksi dan standar instalasi."],
  ["07","Ketentuan battery","Pertamina menetapkan jenis, enclosure, sertifikasi, inspeksi dan pembatasan lokasi."]
 ];
 rows.forEach((r,i)=>{const y=170+i*62;box(s,42,y,1138,58,i%2?C.panel:C.white,C.rule,`row-${i}`);box(s,42,y,65,58,C.pale,C.rule,`num-${i}`);tx(s,r[0],57,y+17,36,25,17,{bold:true});tx(s,r[1],128,y+15,250,28,18,{bold:true});tx(s,r[2],395,y+12,760,36,17);});
 notes(s,["Poin revisi pengguna - sisi CH."]);
}

// 4 GW
{
 const s=deck.slides.add();title(s,"Gateway: Pertamina perlu membuka jalur IP dan menjelaskan security jaringan",4);
 twoCol(s,"RENCANA LGU",[
  "Gateway menggunakan adaptor 5 VDC dan ditempatkan di dalam ruangan.",
  "Antenna ditempatkan di rooftop dengan kebutuhan jalur kabel dan proteksi.",
  "Konfigurasi Wi-Fi dasar saat ini memakai SSID dan password.",
  "Gateway terhubung ke broker MQTT melalui IP atau hostname server."
 ],"INFORMASI PERTAMINA",[
  "Prosedur registrasi MAC, SSID/security, DHCP/static IP, VLAN, DNS, NTP dan firewall.",
  "Alamat/port broker, credential, TLS/mTLS, certificate dan topic ACL.",
  "Titik daya indoor, akses rooftop, batas antenna, rute coax, grounding dan proteksi petir.",
  "Jalur IP/routing ke broker - tidak harus satu SSID atau subnet."
 ],135,360,62,18);
 const metrics=[{x:42,w:260,n:"< 1 KB",d:"Target data per pesan"},{x:322,w:300,n:"90 byte / 10 detik",d:"Estimasi periode tercepat"},{x:642,w:538,n:"Validasi MQTT",d:"Ukur paket aktual karena JSON, topic, TCP/IP dan security menambah overhead"}];
 metrics.forEach((m,i)=>{box(s,m.x,535,m.w,94,i===2?C.amber:(i===1?C.pale:C.panel),C.rule,`metric-${i}`);tx(s,m.n,m.x+18,550,m.w-36,34,i===1?25:29,{bold:true,color:i===2?C.blue:C.ink});tx(s,m.d,m.x+18,591,m.w-36,25,16,{color:C.muted});});
 notes(s,["Poin revisi pengguna - sisi Gateway.","firmware/gateway/src/GatewayMqttMeshMain.cpp","firmware/config/GwConfig.h"]);
}

// 5 Server
{
 const s=deck.slides.add();title(s,"Server: LGU menyediakan dashboard; Pertamina menetapkan lingkungan target",5);
 twoCol(s,"DISEDIAKAN LGU",[
  "Web dashboard, paket installer dan panduan konfigurasi.",
  "Kebutuhan minimum CPU/RAM/storage, OS/runtime dan database yang didukung.",
  "Dependency, port, service, schema database dan prosedur startup/backup.",
  "Dukungan instalasi, commissioning, dokumentasi dan training."
 ],"DIBUTUHKAN DARI PERTAMINA",[
  "Spesifikasi aktual server/VM: CPU, RAM, storage dan availability.",
  "OS/versi, akses admin, container policy, antivirus dan patching.",
  "Database, retention, backup/restore dan ownership DBA.",
  "IP/FQDN, broker MQTT, port/firewall, account, certificate dan PIC operasi."
 ],145,410);
 box(s,42,590,1138,62,C.pale,C.rule,"server-output");tx(s,"Output: server readiness sheet + jadwal instalasi + PIC + kriteria acceptance",62,606,1095,34,21,{bold:true});
 notes(s,["Poin revisi pengguna - sisi Server.","LGU requirements versus Pertamina actual environment must be reconciled before installation."]);
}

const responsibilities=[
 ["01 · Power GLD","Tetapkan kebutuhan 24 VDC minimal 2 A kontinu dan detail koneksi.","Sediakan titik daya dan buktikan kapasitas melalui pengukuran."],
 ["02 · Lokasi GLD","Usulkan lokasi dekat sensor existing dan metode pemasangan.","Berikan akses, izin, titik pemasangan dan aturan proteksi."],
 ["03 · Battery GLD","Lanjutkan optimasi power management; belum untuk kontinu.","Berikan ketentuan site untuk fase pengembangan berikutnya."],
 ["04 · Mounting CH","Desain dan fabrikasi mounting sesuai struktur existing.","Berikan foto, dimensi, batas beban dan persetujuan desain."],
 ["05 · Solar panel","Pilih panel tersertifikasi dan serahkan dokumen.","Tetapkan sertifikasi yang diterima dan setujui panel."],
 ["06 · Instalasi CH","Berikan drawing, wiring dan metode instalasi.","Laksanakan instalasi dengan personel, tools dan prosedur K3."],
 ["07 · Fastener","Sesuaikan mounting dengan standar mur/baut/kunci.","Berikan ukuran dan standar fastener yang digunakan."],
 ["08 · Batas CH","Sesuaikan antenna, enclosure dan kabel dengan aturan site.","Berikan batas tinggi, area bahaya, rute, grounding dan kabel."],
 ["09 · Battery CH","Serahkan spesifikasi, enclosure, proteksi dan SDS.","Jelaskan dan setujui ketentuan battery di area Pertamina."],
 ["10 · Gateway fisik","Sediakan GW, adaptor 5 V, antenna dan detail kabel.","Sediakan daya indoor, rooftop, rute coax dan proteksi petir."],
 ["11 · Registrasi jaringan","Berikan MAC/device list dan sesuaikan konfigurasi.","Berikan registrasi, SSID/security, IP, firewall dan broker."],
 ["12 · MQTT & payload","Berikan spec dan uji 90 byte/10 detik + capture.","Sediakan broker/ACL dan setujui limit payload/rate."],
 ["13 · Server/dashboard","Sediakan dashboard, installer, minimum spec dan training.","Sediakan host/OS/DB aktual, akses, network dan backup policy."],
 ["14 · Commissioning","Siapkan FAT/SAT, evidence, troubleshooting dan handover.","Jadwalkan SAT, hadirkan PIC, tutup temuan dan sign-off."]
];
function responsibilitySlide(part,no,data){
 const s=deck.slides.add();title(s,`Pembagian tugas LGU–Pertamina · ${part}`,no);
 tx(s,"Setiap baris perlu memiliki PIC, target tanggal, dan bukti penyelesaian.",42,104,1120,32,20,{color:C.muted});
 box(s,42,148,565,44,C.blue,C.blue,"head-lgu");box(s,607,148,573,44,C.green,C.green,"head-ptm");tx(s,"LGU",62,159,200,25,18,{bold:true,color:C.white});tx(s,"PERTAMINA",627,159,220,25,18,{bold:true,color:C.white});
 data.forEach((r,i)=>{const y=192+i*65;const fill=i%2?C.panel:C.white;box(s,42,y,565,65,fill,C.rule,`lgu-${i}`);box(s,607,y,573,65,fill,C.rule,`ptm-${i}`);tx(s,`${r[0]}\n${r[1]}`,62,y+8,525,50,16,{name:`lgu-text-${i}`});tx(s,`${r[0]}\n${r[2]}`,627,y+8,533,50,16,{name:`ptm-text-${i}`});});
 notes(s,["Pembagian tugas hasil konsolidasi poin pengguna."]);
}
responsibilitySlide("Bagian 1",6,responsibilities.slice(0,7));
responsibilitySlide("Bagian 2",7,responsibilities.slice(7));

// 8 Closing checklist
{
 const s=deck.slides.add();title(s,"Informasi minimum dari Pertamina sebelum pemasangan",8);
 bullets(s,[
  "Bukti kesiapan power GLD 24 VDC minimal 2 A: lokasi, polaritas, proteksi, grounding dan hasil ukur.",
  "Data mounting CH: foto, ukuran tiang/handrail, fastener, batas beban, area bahaya dan sertifikasi.",
  "Standar panel surya, kabel panel–CH, battery, enclosure, grounding dan proteksi petir.",
  "Lokasi Gateway indoor, adaptor 5 V, akses rooftop, batas antenna dan jalur coax.",
  "Registrasi jaringan: MAC, SSID/security, VLAN, IP, DNS, NTP, firewall, broker, ACL dan certificate.",
  "Spesifikasi server: VM/host, CPU/RAM/storage, OS, database, akses admin, backup dan PIC.",
  "Jadwal instalasi, daftar PIC, skenario SAT, kriteria lulus dan penandatangan acceptance."
 ],42,130,1138,62,19,C.green);
 box(s,42,578,1138,73,C.amber,C.rule,"tech-note");tx(s,"Catatan teknis",62,594,190,25,20,{bold:true,color:C.blue});tx(s,"“Satu jaringan” berarti tersedia IP routing ke broker. Nilai 90 byte adalah target data; paket MQTT aktual tetap harus diukur saat SAT.",250,590,900,38,19,{bold:true});
 notes(s,["Poin revisi pengguna dan konsolidasi readiness checklist."]);
}

await fs.mkdir(path.dirname(OUT),{recursive:true});await fs.mkdir(RENDER,{recursive:true});
for(const [i,s] of deck.slides.items.entries()){
 const stem=`slide-${String(i+1).padStart(2,"0")}`;const png=await deck.export({slide:s,format:"png",scale:1.5});await fs.writeFile(path.join(RENDER,`${stem}.png`),new Uint8Array(await png.arrayBuffer()));const layout=await s.export({format:"layout"});await fs.writeFile(path.join(RENDER,`${stem}.layout.json`),await layout.text());
}
const inspect=await deck.inspect({kind:"slide,textbox,shape,notes",maxChars:50000});await fs.writeFile(path.join(RENDER,"inspect.ndjson"),inspect.ndjson);
const pptx=await PresentationFile.exportPptx(deck);await pptx.save(OUT);
console.log(`WROTE ${OUT} slides=${deck.slides.items.length}`);
