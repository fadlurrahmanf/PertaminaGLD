import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const OUT = "D:/Github/PertaminaGLD/output/presentation/PertaminaGLD-Pertanyaan-Integrasi.pptx";
const PREVIEW = "D:/Github/PertaminaGLD/tmp/presentations/pertamina-integration/rendered";
const W = 1280, H = 720;
const C = { ink: "#111111", muted: "#5F6670", panel: "#EDEDED", rule: "#B8BCC4", blue: "#3D8DFF", pale: "#D0EDFA", white: "#FFFFFF", amber: "#F4B740", green: "#2FA36B", red: "#D65252" };

const deck = Presentation.create({ slideSize: { width: W, height: H } });

function box(slide, x, y, w, h, fill=C.panel, line=C.rule, radius=false, name="box") {
  return slide.shapes.add({ geometry: radius ? "roundRect" : "rect", name, position:{left:x,top:y,width:w,height:h}, fill, line:{style:"solid",fill:line,width:1} });
}
function tx(slide, text, x, y, w, h, size=24, opts={}) {
  const s=slide.shapes.add({ geometry:"textbox", name:opts.name||"text", position:{left:x,top:y,width:w,height:h}, fill:"none", line:{style:"solid",fill:"none",width:0} });
  s.text=text;
  s.text.style={ fontSize:size, typeface:"Arial", color:opts.color||C.ink, bold:!!opts.bold, alignment:opts.align||"left", verticalAlignment:opts.valign||"top", autoFit:opts.autoFit||"shrinkText" };
  return s;
}
function line(slide, x, y, w, h=0, color=C.ink, width=2, name="line") {
  return slide.shapes.add({geometry:"straightConnector1",name,position:{left:x,top:y,width:w,height:h},fill:"none",line:{style:"solid",fill:color,width}});
}
function arrow(slide,x,y,w,h,color=C.blue,name="arrow") { return slide.shapes.add({geometry:"rightArrow",name,position:{left:x,top:y,width:w,height:h},fill:color,line:{style:"solid",fill:color,width:0}}); }
function leftArrow(slide,x,y,w,h,color=C.muted,name="left-arrow") { return slide.shapes.add({geometry:"leftArrow",name,position:{left:x,top:y,width:w,height:h},fill:color,line:{style:"solid",fill:color,width:0}}); }
function title(slide, text, no) {
  tx(slide,text,42,34,1140,72,39,{bold:true,name:"slide-title"});
  tx(slide,String(no).padStart(2,"0"),1184,660,54,24,13,{align:"right",color:C.muted,name:"page"});
}
function bulletList(slide, items, x, y, w, lineH=47, size=21, accent=C.blue) {
  items.forEach((it,i)=>{ box(slide,x,y+i*lineH+9,9,9,accent,accent,false,`bullet-${i}`); tx(slide,it,x+25,y+i*lineH,w-25,lineH-3,size,{name:`bullet-text-${i}`}); });
}
function note(slide, sources) { slide.speakerNotes.textFrame.setText(`[Sources]\n${sources.join("\n")}`); }

// 1 - restrained Codex Grid cover silhouette.
{
  const s=deck.slides.add(); s.background.fill=C.white;
  tx(s,"PERTAMINA × LGU",42,42,500,40,25,{bold:true,color:C.muted,name:"eyebrow"});
  tx(s,"Kesiapan Integrasi\nGLD · CH · Gateway · Server",42,175,1030,245,65,{bold:true,name:"cover-title"});
  tx(s,"Daftar pertanyaan dan keputusan sebelum pemasangan awal",42,505,800,55,28,{color:C.muted,name:"cover-subtitle"});
  box(s,1010,505,180,7,C.blue,C.blue,false,"accent-rule");
  tx(s,"13 Agustus 2026",42,600,400,35,18,{color:C.muted});
  note(s,["Catatan rapat yang diberikan pengguna, 13 Agustus 2026.","Repository PertaminaGLD: dokumen desain dan source firmware (audit read-only)."]);
}

// 2
{
  const s=deck.slides.add(); title(s,"Tujuan rapat: menetapkan prasyarat sebelum tanggal pemasangan",2);
  tx(s,"Tanggal pemasangan awal baru dapat dijanjikan setelah empat kelompok keputusan ditutup bersama.",42,120,1100,60,25,{color:C.muted});
  const labels=["Fisik siap","Jaringan siap","Server siap","SAT disepakati"];
  const desc=["Power, mounting, antena, akses","IP, firewall, broker, security","VM/OS, database, hak admin","Uji normal, alarm, command, recovery"];
  labels.forEach((v,i)=>{const x=42+i*300; box(s,x,235,260,235,i===3?C.pale:C.panel,C.rule,false,`gate-${i}`); tx(s,`0${i+1}`,x+18,252,70,55,31,{bold:true,color:C.blue}); tx(s,v,x+18,325,224,48,25,{bold:true}); tx(s,desc[i],x+18,390,224,92,20,{color:C.muted});});
  tx(s,"Output yang diminta dari Pertamina: PIC, keputusan teknis, bukti kesiapan, dan target tanggal per item.",42,570,1130,50,24,{bold:true});
  note(s,["Catatan rapat pengguna.","docs/design/gw-server/final_design.md","docs/design/gld-ch/payload-contract.draft.md"]);
}

// 3 - arrows first, nodes second.
{
  const s=deck.slides.add(); title(s,"Arsitektur end-to-end: data naik, kontrol kembali melalui jalur yang sama",3);
  arrow(s,272,290,63,35,C.blue,"data-arrow-1"); arrow(s,565,290,45,35,C.blue,"data-arrow-2"); arrow(s,840,290,45,35,C.blue,"data-arrow-3");
  leftArrow(s,272,390,63,35,C.muted,"control-arrow-1"); leftArrow(s,565,390,45,35,C.muted,"control-arrow-2"); leftArrow(s,840,390,45,35,C.muted,"control-arrow-3");
  const nodes=[{x:42,t:"GLD",d:"Sensor gas\n24 VDC"},{x:335,t:"CH",d:"STAR receiver\nCache + MESH"},{x:610,t:"GATEWAY",d:"LoRa MESH\nWi-Fi + MQTT"},{x:885,t:"SERVER",d:"Broker · Node-RED\nDB · Dashboard"}];
  nodes.forEach((n,i)=>{box(s,n.x,220,230,230,i===3?C.pale:C.panel,C.rule,false,`node-${i}`); tx(s,n.t,n.x+18,248,194,44,27,{bold:true}); tx(s,n.d,n.x+18,322,194,75,21,{color:C.muted});});
  tx(s,"DATA / ALARM →",42,155,300,32,18,{bold:true,color:C.blue}); tx(s,"← COMMAND / ACK",42,493,300,32,18,{bold:true,color:C.muted});
  box(s,42,555,1138,65,C.white,C.rule,false,"normal-alarm-note"); tx(s,"Normal: disimpan di cache CH lalu diambil (pull)  ·  Alarm: dikirim segera (push) dan di-ACK berjenjang",60,573,1100,32,21,{bold:true});
  note(s,["docs/design/gld/final_design.md:594-595","docs/design/gld-ch/payload-contract.draft.md:177-202","docs/design/gw-server/final_design.md:38-47"]);
}

// 4
{
  const s=deck.slides.add(); title(s,"Empat layer memisahkan kebutuhan lapangan, jaringan, proses data, dan pengguna",4);
  const rows=[
    ["04  APPLICATION","Dashboard web · alarm · histori · user/role · audit · laporan",C.pale],
    ["03  DATA PROCESSING","MQTT broker · validasi · decrypt · dedup · database · integrasi alarm",C.panel],
    ["02  NETWORKING","LoRa STAR/MESH · Wi-Fi · IP/DNS/NTP · firewall · MQTT · TLS/ACL",C.pale],
    ["01  PHYSICAL","GLD · CH · GW · server/VM · power · mounting · antenna · cable · protection",C.panel]
  ];
  rows.forEach((r,i)=>{const y=155+i*115; box(s,42,y,1138,88,r[2],C.rule,false,`layer-${i}`); tx(s,r[0],62,y+20,285,42,24,{bold:true,color:i===0?C.blue:C.ink}); tx(s,r[1],360,y+20,790,48,22,{color:C.muted});});
  tx(s,"Security dan operasional berlaku lintas layer—bukan hanya urusan Wi-Fi.",42,635,1138,35,20,{bold:true});
  note(s,["Pemetaan integrasi berdasarkan catatan rapat dan source PertaminaGLD.","docs/design/gw-server/final_design.md:58-104","docs/design/ch/final_design.md:174-194"]);
}

// 5
{
  const s=deck.slides.add(); title(s,"Pertanyaan Physical Layer: titik pemasangan harus jelas dan tersertifikasi",5);
  tx(s,"GLD",42,140,200,36,25,{bold:true,color:C.blue});
  bulletList(s,["Di mana titik 24 VDC per GLD, polaritas, grounding, MCB/fuse, konektor, dan hasil ukur?","Apakah kapasitas 2 A tersedia per titik dekat sensor existing?","Apakah area termasuk hazardous area; standar enclosure, gland, kabel, surge, dan sertifikasi apa?"],42,185,555,58,19);
  tx(s,"CH · PANEL SURYA · ANTENA",645,140,500,36,25,{bold:true,color:C.blue});
  bulletList(s,["Batas tinggi/posisi antenna, rute kabel, grounding dan lightning protection?","Standar kabel panel surya–CH, baterai yang diizinkan, orientasi panel, dan beban angin?","Ukuran mounting/lubang, baut/mur/bracket, tangga, kunci akses, serta PIC penyedia?"],645,185,545,58,19);
  box(s,42,584,1148,66,C.pale,C.rule,false,"physical-callout"); tx(s,"Catatan “power 24 V selesai” perlu ditutup dengan lokasi terminal dan bukti ukur saat serah terima.",60,602,1110,34,21,{bold:true});
  note(s,["Catatan rapat pengguna.","docs/design/gld/final_design.md:167-179 (mode power firmware; bukan bukti rating 2 A)."]);
}

// 6
{
  const s=deck.slides.add(); title(s,"Pertanyaan Networking Layer: definisikan jalur IP, broker, dan kontrol akses",6);
  tx(s,"“Satu jaringan” tidak harus satu SSID.",42,125,650,46,28,{bold:true,color:C.blue});
  tx(s,"Yang wajib: Gateway memperoleh IP dan dapat mencapai broker melalui routing/firewall yang disetujui.",42,175,745,60,22,{color:C.muted});
  bulletList(s,[
    "SSID/VLAN/subnet, DHCP reservation atau static IP, DNS, NTP, proxy/captive portal?",
    "Registrasi MAC: format, daftar device, PIC approval, dan SLA aktivasi?",
    "Wi-Fi PSK atau WPA2/3-Enterprise/802.1X? Jika enterprise: EAP, CA, identity, client certificate?",
    "Broker disediakan Pertamina atau LGU; FQDN/IP, port produksi, arah firewall, QoS dan topic ACL?",
    "Apakah TLS/mTLS wajib; siapa menerbitkan dan merotasi certificate/secret?"
  ],42,255,1140,58,21);
  box(s,835,122,345,72,C.panel,C.rule,false,"source-gap"); tx(s,"Source GW saat ini:\nWi-Fi station + plain MQTT",853,138,310,44,18,{bold:true});
  note(s,["firmware/gateway/src/GatewayMqttMeshMain.cpp:636-655, 788-828, 1589-1686","firmware/config/ServerConfig.h:36-64","firmware/config/GwConfig.h:97-103"]);
}

// 7
{
  const s=deck.slides.add(); title(s,"Pertanyaan Data Processing: Pertamina perlu menetapkan platform server dan kebijakan data",7);
  const left=["Server berupa VM atau bare-metal? Lokasi, availability, CPU/RAM/storage, UPS?","OS dan versi; hak admin; kebijakan Docker, Node.js/Node-RED, broker, antivirus, patching?","Database standar; retention, backup/restore, archive, kapasitas dan ownership DBA?"];
  const right=["NTP/timezone dan timestamp authoritative; toleransi duplikat, keterlambatan, restart?","Integrasi alarm ke SCADA/DCS/email/SMS/ticketing; severity, PIC, ACK dan SLA?","Monitoring broker/flow/database, log retention, RTO/RPO dan maintenance window?"];
  box(s,42,150,545,430,C.panel,C.rule,false,"server-column"); tx(s,"PLATFORM SERVER",62,172,500,38,24,{bold:true,color:C.blue}); bulletList(s,left,62,230,500,96,19);
  box(s,625,150,555,430,C.pale,C.rule,false,"data-column"); tx(s,"OPERASI DATA",645,172,510,38,24,{bold:true,color:C.blue}); bulletList(s,right,645,230,510,96,19);
  tx(s,"Repo membuktikan flow Node-RED/decode/decrypt/topology; bukan spesifikasi server produksi Pertamina.",42,615,1138,36,20,{bold:true});
  note(s,["server/nodered/flows/flows.json","docs/design/server/final_design.md:96-136","docs/design/gw-server/final_design.md:58-104"]);
}

// 8
{
  const s=deck.slides.add(); title(s,"Kapasitas payload harus disepakati per layer, bukan satu angka umum",8);
  const metrics=[{n:"39 B",t:"GLD LoRa AppFrame",d:"8 header + 29 encrypted + 2 CRC"},{n:"44 B",t:"Alarm single-record MESH",d:"34 record + 10 frame overhead"},{n:"Variabel",t:"MQTT JSON",d:"Frame hex + metadata + radio metrics"}];
  metrics.forEach((m,i)=>{const x=42+i*390; box(s,x,170,350,235,i===2?C.pale:C.panel,C.rule,false,`metric-${i}`); tx(s,m.n,x+22,195,306,70,40,{bold:true,color:C.blue}); tx(s,m.t,x+22,285,306,40,22,{bold:true}); tx(s,m.d,x+22,340,306,48,18,{color:C.muted});});
  bulletList(s,["Apakah target periode normal 10 detik berlaku per GLD? Berapa maksimum GLD/CH/GW dan burst alarm?","Minta batas broker: maximum payload, message rate, connection, QoS, retained dan LWT.","Ukur sampel MQTT aktual sebelum sizing; angka ±90 byte dari catatan rapat belum menjadi kontrak semua layer."],42,460,1138,55,20,C.amber);
  note(s,["docs/design/gld-ch/payload-contract.draft.md:20-44, 116-166, 192-242","firmware/gateway/src/GatewayMqttMeshMain.cpp:1281-1325","firmware/config/GwConfig.h:27-35 (status GW 10 detik; buffer bukan ukuran payload)."]);
}

// 9
{
  const s=deck.slides.add(); title(s,"Pertanyaan Application Layer: sepakati siapa memakai sistem dan apa yang dianggap berhasil",9);
  const groups=[
    ["AKSES","Viewer/operator/admin? SSO/LDAP/AD, MFA, session timeout, audit log?"],
    ["DASHBOARD","Topologi, health, histori/trend, filter site/device, alarm ACK, report/export?"],
    ["OPERASI","Concurrent users, browser/resolusi/bahasa, SLA, support dan maintenance window?"],
    ["ACCEPTANCE","Skenario UAT, data pembanding, kriteria lulus, PIC dan penandatangan sign-off?"]
  ];
  groups.forEach((g,i)=>{const x=i%2?645:42,y=i<2?155:390; box(s,x,y,545,185,i===3?C.pale:C.panel,C.rule,false,`app-${i}`); tx(s,g[0],x+20,y+20,500,35,22,{bold:true,color:C.blue}); tx(s,g[1],x+20,y+72,500,82,20,{color:C.muted});});
  note(s,["Catatan rapat pengguna.","docs/design/gw-server/final_design.md:186-195"]);
}

// 10
{
  const s=deck.slides.add(); title(s,"Pembagian tanggung jawab mencegah item kritis jatuh di antara dua tim",10);
  box(s,42,145,355,435,C.panel,C.rule,false,"lgu"); tx(s,"LGU",62,165,310,40,27,{bold:true,color:C.blue}); bulletList(s,["Perangkat, firmware, diagram dan daftar MAC/device ID","Drawing mounting dan kebutuhan power/network","Spec MQTT/payload dan installer dashboard","Commissioning script, dokumentasi dan training"],62,230,310,72,19);
  box(s,462,145,355,435,C.pale,C.rule,false,"pertamina"); tx(s,"PERTAMINA",482,165,310,40,27,{bold:true,color:C.blue}); bulletList(s,["Power/proteksi, izin, akses dan infrastruktur mounting","SSID/VLAN/IP/DNS/NTP/firewall/NAC","Server/VM/OS, broker/DB policy, account/certificate","Retention, integrasi alarm, SLA dan security approval"],482,230,310,72,19);
  box(s,882,145,298,435,C.white,C.rule,false,"shared"); tx(s,"BERSAMA",902,165,255,40,27,{bold:true,color:C.blue}); bulletList(s,["Site & radio survey","Cybersecurity review","FAT / SAT / UAT","Rollback, handover, sign-off"],902,230,245,72,19,C.green);
  note(s,["Rangkuman tanggung jawab dari catatan rapat dan audit integrasi PertaminaGLD."]);
}

// 11
{
  const s=deck.slides.add(); title(s,"Keputusan yang diminta: tutup readiness gate, lalu tetapkan tanggal pemasangan",11);
  const steps=[
    ["1","PHYSICAL","Titik power, mounting, antenna route, akses dan sertifikasi disetujui"],
    ["2","NETWORK","GW mendapat IP; broker reachable; MQTT CONNACK + ACL publish/subscribe terbukti"],
    ["3","SERVER","OS/spec/admin window; broker, Node-RED, database dan HTTPS siap"],
    ["4","SAT","Normal, alarm, topology, command, restart/reconnect, outage recovery dan dashboard lulus"]
  ];
  steps.forEach((v,i)=>{const y=145+i*105; box(s,42,y,75,75,i===3?C.blue:C.ink,i===3?C.blue:C.ink,false,`step-no-${i}`); tx(s,v[0],42,y+17,75,40,27,{bold:true,color:C.white,align:"center"}); tx(s,v[1],150,y+4,230,38,21,{bold:true,color:C.blue}); tx(s,v[2],390,y+4,790,58,20,{color:C.muted}); if(i<3) line(s,79,y+75,0,30,C.rule,2,`step-line-${i}`);});
  box(s,42,590,1138,63,C.pale,C.rule,false,"decision"); tx(s,"Mohon Pertamina menetapkan PIC dan target tanggal untuk setiap gate; jadwal pemasangan mengikuti gate terakhir yang selesai.",60,606,1100,35,21,{bold:true});
  note(s,["Catatan rapat pengguna.","Acceptance synthesis from source-backed integration audit."]);
}

await fs.mkdir(path.dirname(OUT),{recursive:true}); await fs.mkdir(PREVIEW,{recursive:true});
for (const [i,s] of deck.slides.items.entries()) {
  const blob=await deck.export({slide:s,format:"png",scale:1.5});
  await fs.writeFile(path.join(PREVIEW,`slide-${String(i+1).padStart(2,"0")}.png`),new Uint8Array(await blob.arrayBuffer()));
  const layout=await s.export({format:"layout"}); await fs.writeFile(path.join(PREVIEW,`slide-${String(i+1).padStart(2,"0")}.layout.json`),await layout.text());
}
const montage=await deck.export({format:"webp",montage:true,scale:1}); await fs.writeFile(path.join(PREVIEW,"montage.webp"),new Uint8Array(await montage.arrayBuffer()));
const pptx=await PresentationFile.exportPptx(deck); await pptx.save(OUT);
const inspect=await deck.inspect({kind:"slide,textbox,shape,notes",maxChars:50000}); await fs.writeFile(path.join(PREVIEW,"inspect.ndjson"),inspect.ndjson);
console.log(`WROTE ${OUT} slides=${deck.slides.items.length}`);
