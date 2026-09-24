import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "D:/Github/PertaminaGLD/outputs/utility-survey-20260924";
const outputPath = `${outputDir}/Daftar_Kebutuhan_Utilitas_SRU_Revisi.xlsx`;
const wb = Workbook.create();
const ws = wb.worksheets.add("Daftar Kebutuhan");
const guide = wb.worksheets.add("Petunjuk");
const font = "Arial";

const items = [
  ["1.1","Server","Infrastruktur","Server fisik atau VM","Host aplikasi operasional","","unit","Belum dipetakan","IT","Belum disurvei",""],
  ["1.2","Server","Utilitas listrik","Listrik AC 220 V","Sumber, kapasitas, dan panel asal","","titik","Belum dipetakan","Listrik","Belum disurvei",""],
  ["1.3","Server","Utilitas listrik","UPS","Kapasitas dan durasi backup yang diperlukan","","unit","Belum dipetakan","IT/Listrik","Belum disurvei",""],
  ["1.4","Server","Infrastruktur","Rack atau ruang server","Lokasi, pendinginan, akses fisik","","lokasi","Belum dipetakan","IT","Belum disurvei",""],
  ["1.5","Server","Jaringan","Switch LAN dan port jaringan","Port tersedia dan jalur patch cord","","port","Belum dipetakan","IT","Belum disurvei",""],
  ["1.6","Server","Jaringan","IP statis / VLAN / subnet","Alokasi IP, gateway, DNS, dan VLAN","","paket","Belum dipetakan","IT","Belum disurvei",""],
  ["1.7","Server","Jaringan","Internet","Kebutuhan akses internet yang disetujui","","layanan","Belum dipetakan","IT","Belum disurvei",""],
  ["1.8","Server","Keamanan jaringan","Firewall rule","Akses GW ke broker/server dan port yang diizinkan","","rule","Belum dipetakan","IT","Belum disurvei",""],
  ["1.9","Server","Aplikasi","MQTT Broker","Hostname/IP, port, akun, dan kebijakan akses","","layanan","Belum dipetakan","IT","Belum disurvei",""],
  ["1.10","Server","Aplikasi","Node-RED","Host, akses administrasi, dan strategi deployment","","layanan","Belum dipetakan","IT","Belum disurvei",""],
  ["1.11","Server","Aplikasi","Database MySQL","Host, storage, akun aplikasi, backup","","layanan","Belum dipetakan","IT","Belum disurvei",""],
  ["1.12","Server","Aplikasi","Storage data dan log","Kapasitas dan retensi CSV/log","","GB","Belum dipetakan","IT","Belum disurvei",""],
  ["1.13","Server","Operasional","Backup dan uji restore","Jadwal, media backup, PIC, bukti uji restore","","prosedur","Belum dipetakan","IT","Belum disurvei",""],
  ["1.14","Server","Jaringan","NTP / sinkronisasi waktu","Server waktu yang diizinkan dan jalur akses","","layanan","Belum dipetakan","IT","Belum disurvei",""],
  ["1.15","Server","Keamanan","Akun admin dan operator","Role, otorisasi, dan mekanisme pengelolaan akun","","paket","Belum dipetakan","IT/Operasi","Belum disurvei",""],
  ["1.16","Server","Keamanan","Sertifikat TLS","CA, masa berlaku, dan PIC pengelola sertifikat","","sertifikat","Belum dipetakan","IT","Belum disurvei",""],
  ["2.1","Gateway","Utilitas listrik","Sumber listrik Gateway","Titik sumber, tegangan, dan kapasitas","","titik","Belum dipetakan","Listrik","Belum disurvei",""],
  ["2.2","Gateway","Utilitas listrik","Power supply / adaptor","Sesuai spesifikasi unit Gateway","","unit","Belum dipetakan","Listrik","Belum disurvei",""],
  ["2.3","Gateway","Utilitas listrik","UPS kecil","Ditentukan dari kebutuhan kontinuitas layanan","","unit","Belum dipetakan","Listrik/Operasi","Belum disurvei",""],
  ["2.4","Gateway","Jaringan","Ethernet atau Wi-Fi perusahaan","Media koneksi yang tersedia di titik GW","","titik","Belum dipetakan","IT","Belum disurvei",""],
  ["2.5","Gateway","Jaringan","IP, gateway, DNS, VLAN","Data provisioning jaringan Gateway","","paket","Belum dipetakan","IT","Belum disurvei",""],
  ["2.6","Gateway","Jaringan","Akses ke MQTT Broker dan Server","Hostname/IP, port, firewall, TLS bila digunakan","","rule","Belum dipetakan","IT","Belum disurvei",""],
  ["2.7","Gateway","Radio","Antena LoRa eksternal","Jenis, gain, konektor, dan posisi pemasangan","","unit","Belum dipetakan","Instrument","Belum disurvei",""],
  ["2.8","Gateway","Radio","Kabel coax dan konektor RF","Panjang jalur, tipe kabel, konektor, proteksi","","set","Belum dipetakan","Instrument","Belum disurvei",""],
  ["2.9","Gateway","Mekanik","Pole/bracket antena","Tinggi, orientasi, serta kekuatan mounting","","set","Belum dipetakan","Sipil/Instrument","Belum disurvei",""],
  ["2.10","Gateway","Mekanik","Enclosure atau panel Gateway","Indoor/outdoor, IP rating sesuai area, akses servis","","unit","Belum dipetakan","Instrument","Belum disurvei",""],
  ["2.11","Gateway","Proteksi","Grounding","Titik grounding dan kontinuitas grounding","","titik","Belum dipetakan","Listrik","Belum disurvei",""],
  ["2.12","Gateway","Proteksi","Surge / proteksi petir","Proteksi suplai dan antena sesuai desain lokasi","","set","Belum dipetakan","Listrik/Instrument","Belum disurvei",""],
  ["2.13","Gateway","Operasional","Akses commissioning dan maintenance","Akses fisik, izin, dan PIC area","","lokasi","Belum dipetakan","Operasi","Belum disurvei",""],
  ["2.14","Gateway","Radio","Survei lokasi antena","Tinggi, halangan, kualitas link, dan foto titik","","kegiatan","Belum dipetakan","Instrument","Belum disurvei",""],
  ["3.1","Cluster Head","Utilitas listrik","Sumber listrik CH","Titik sumber, tegangan, dan kapasitas","","titik","Belum dipetakan","Listrik","Belum disurvei",""],
  ["3.2","Cluster Head","Utilitas listrik","Power supply CH","Sesuai spesifikasi unit Cluster Head","","unit","Belum dipetakan","Listrik","Belum disurvei",""],
  ["3.3","Cluster Head","Utilitas listrik","Backup power / UPS","Ditentukan oleh kebutuhan kontinuitas layanan","","unit","Belum dipetakan","Listrik/Operasi","Belum disurvei",""],
  ["3.4","Cluster Head","Mekanik","Enclosure/panel CH","Indoor/outdoor, akses servis, dan perlindungan lingkungan","","unit","Belum dipetakan","Instrument","Belum disurvei",""],
  ["3.5","Cluster Head","Radio","Antena LoRa sisi GLD","Jenis, gain, konektor, orientasi, dan tinggi","","unit","Belum dipetakan","Instrument","Belum disurvei",""],
  ["3.6","Cluster Head","Radio","Antena LoRa sisi Gateway","Jenis, gain, konektor, orientasi, dan tinggi","","unit","Belum dipetakan","Instrument","Belum disurvei",""],
  ["3.7","Cluster Head","Radio","Kabel coax dan konektor RF","Panjang, tipe kabel, konektor, dan proteksi","","set","Belum dipetakan","Instrument","Belum disurvei",""],
  ["3.8","Cluster Head","Mekanik","Pole/bracket antena","Tinggi dan kekuatan mounting","","set","Belum dipetakan","Sipil/Instrument","Belum disurvei",""],
  ["3.9","Cluster Head","Proteksi","Grounding","Titik grounding dan kontinuitas grounding","","titik","Belum dipetakan","Listrik","Belum disurvei",""],
  ["3.10","Cluster Head","Proteksi","Surge / proteksi petir","Proteksi suplai dan antena sesuai desain lokasi","","set","Belum dipetakan","Listrik/Instrument","Belum disurvei",""],
  ["3.11","Cluster Head","Operasional","Akses commissioning","Akses serial/USB, izin kerja, dan PIC area","","lokasi","Belum dipetakan","Operasi","Belum disurvei",""],
  ["3.12","Cluster Head","Dokumentasi","Label node ID","ID CH, lokasi, dan label perangkat","","label","Belum dipetakan","Instrument","Belum disurvei",""],
  ["3.13","Cluster Head","Radio","Uji RSSI/SNR ke GW dan GLD","Hasil ukur per link serta indikasi blank spot","","kegiatan","Belum dipetakan","Instrument","Belum disurvei",""],
  ["4.1","GLD","Utilitas listrik","Sumber listrik GLD","Catu daya 24 V DC, 1 A per GLD","","titik","Belum dipetakan","Listrik","Belum disurvei",""],
  ["4.2","GLD","Instalasi listrik","Kabel daya, terminal, gland, conduit","Panjang/jalur kabel, tipe gland, proteksi mekanik","","set","Belum dipetakan","Listrik/Instrument","Belum disurvei",""],
  ["4.3","GLD","Mekanik","Enclosure/panel GLD","Kondisi area, akses servis, dan perlindungan lingkungan","","unit","Belum dipetakan","Instrument","Belum disurvei",""],
  ["4.4","GLD","Proteksi","Grounding unit","Titik grounding dan kontinuitas grounding","","titik","Belum dipetakan","Listrik","Belum disurvei",""],
  ["4.5","GLD","Mekanik","Mounting/bracket","Posisi unit, tinggi pemasangan, dan akses maintenance","","set","Belum dipetakan","Instrument","Belum disurvei",""],
  ["4.6","GLD","Radio","Antena LoRa","Tipe internal/eksternal, jalur kabel, dan orientasi bila eksternal","","unit","Belum dipetakan","Instrument","Belum disurvei",""],
  ["4.7","GLD","Proses","Posisi sensor terhadap sumber kebocoran","Tag equipment, jenis gas, dan titik potensi kebocoran","","titik","Belum dipetakan","Operasi/Instrument","Belum disurvei",""],
  ["4.8","GLD","Proses","Arah angin/ventilasi","Arah aliran udara dan potensi akumulasi gas","","titik","Belum dipetakan","Operasi/HSE","Belum disurvei",""],
  ["4.9","GLD","Operasional","Akses inspeksi dan maintenance","Ruang kerja, izin akses, dan PIC area","","lokasi","Belum dipetakan","Operasi","Belum disurvei",""],
  ["4.10","GLD","Operasional","Proses warm-up/zeroing/nulling/kalibrasi","Metode, jadwal, alat uji, dan PIC","","prosedur","Belum dipetakan","Instrument","Belum disurvei",""],
  ["4.11","GLD","Dokumentasi","Tag equipment dan node ID","ID GLD, lokasi, serta label perangkat","","label","Belum dipetakan","Instrument","Belum disurvei",""],
  ["4.12","GLD","Radio","Uji kualitas link GLD ke CH","RSSI/SNR, jarak, penghalang, dan hasil uji","","kegiatan","Belum dipetakan","Instrument","Belum disurvei",""],
  ["4.13","GLD","Keselamatan","Indikator/alarm lokal","Kebutuhan lampu/buzzer/interlock dan PIC keputusan","","set","Belum dipetakan","Operasi/HSE","Belum disurvei",""],
  ["4.14","GLD","Dokumentasi","Logbook pemeriksaan","Format catatan inspeksi, hasil uji, dan tindak lanjut","","prosedur","Belum dipetakan","Operasi/Instrument","Belum disurvei",""],
  ["5.1","Lintas sistem","Dokumentasi","Denah area dan layout titik","Denah terkini dan titik Server/GW/CH/GLD","","dokumen","Belum dipetakan","Operasi","Belum disurvei",""],
  ["5.2","Lintas sistem","Koordinasi","Daftar PIC","PIC IT, listrik, instrument, operasi, dan HSE","","daftar","Belum dipetakan","PM/Operasi","Belum disurvei",""],
  ["5.3","Lintas sistem","Dokumentasi","Foto tiap titik","Foto sumber listrik, jaringan, antena, dan lokasi unit","","set","Belum dipetakan","Surveyor","Belum disurvei",""],
  ["5.4","Lintas sistem","Keselamatan","Izin kerja dan klasifikasi area","Izin akses, klasifikasi area, dan persyaratan HSE","","dokumen","Belum dipetakan","HSE/Operasi","Belum disurvei",""],
  ["5.5","Lintas sistem","Material","Daftar material cadangan","Antena, kabel RF, konektor, power supply, dan unit spare","","set","Belum dipetakan","Instrument","Belum disurvei",""],
];

const removedItemIds = new Set([
  "1.5", "1.6", "1.8", "1.9", "1.10", "1.11", "1.12", "1.13", "1.14", "1.15",
  "2.6", "2.7", "2.8", "2.9", "2.10", "2.11", "2.12", "2.14",
  "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8", "3.9", "3.10", "3.11", "3.12", "3.13",
  "4.3", "4.5", "4.6", "4.7", "4.8", "4.10", "4.11", "4.12", "4.13", "4.14",
  "5.5",
]);
const activeItems = items.filter((row) => !removedItemIds.has(row[0]));

ws.showGridLines = false;
ws.tabColor = "#1F4E78";
ws.getRange("A2:K2").merge();
ws.getRange("A2").values = [["Daftar Kebutuhan Utilitas dan Survei SRU"]];
ws.getRange("A3:K3").merge();
ws.getRange("A3").values = [["Cakupan: Server, Gateway (GW), Cluster Head (CH), dan Gas Leak Detector (GLD)"]];
ws.getRange("A2:K2").format = { font: { name: font, size: 14, bold: true, color: "#1F2937" } };
ws.getRange("A3:K3").format = { font: { name: font, size: 10, italic: true, color: "#4B5563" } };
ws.getRange("A5:B5").values = [["Ringkasan", "Jumlah"]];
ws.getRange("A6:B10").values = [["Total item", null], ["Server", null], ["Gateway", null], ["GLD", null], ["Lintas sistem", null]];
ws.getRange("B6:B10").formulas = [["=COUNTA(A14:A200)"], ["=COUNTIF(B14:B200,\"Server\")"], ["=COUNTIF(B14:B200,\"Gateway\")"], ["=COUNTIF(B14:B200,\"GLD\")"], ["=COUNTIF(B14:B200,\"Lintas sistem\")"]];
ws.getRange("D5:K5").merge();
ws.getRange("D5").values = [["Isian berwarna kuning diperbarui dari hasil survei. Kolom jumlah, ketersediaan, PIC, status, dan catatan disiapkan untuk diisi tim."]];
ws.getRange("A5:B5").format = { fill: "#1F4E78", font: { name: font, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center" };
ws.getRange("A6:B10").format = { font: { name: font, size: 10 }, borders: { style: "continuous", color: "#D1D5DB" } };
ws.getRange("B6:B10").format = { font: { name: font, bold: true }, horizontalAlignment: "center" };
ws.getRange("D5:K5").format = { fill: "#FFF2CC", font: { name: font, size: 10, italic: true, color: "#5B4A00" }, wrapText: true, verticalAlignment: "center" };
ws.getRange("D5:K5").format.rowHeight = 32;

const headers = [["No.","Komponen","Kategori","Kebutuhan / Utilitas","Detail yang dipetakan saat survei","Jumlah","Satuan","Ketersediaan","PIC","Status Survei","Catatan lokasi / tindak lanjut"]];
// Keep hierarchical list numbers such as 1.10 and 3.10 exactly as written.
// A zero-width space keeps the identifier as text without affecting display.
const tableItems = activeItems.map((row) => [row[0] + "\u200B", ...row.slice(1)]);
ws.getRange(`A13:K${13 + activeItems.length}`).values = [...headers, ...tableItems];
ws.getRange("A13:K13").format = {
  fill: "#0F6B86",
  font: { name: font, size: 10, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
ws.getRange("A13:K13").format.rowHeight = 24;
for (let i = 0; i < activeItems.length; i += 1) {
  const row = 14 + i;
  const fill = i % 2 === 0 ? "#CFEAF6" : "#FFFFFF";
  ws.getRange(`A${row}:E${row}`).format.fill = fill;
  ws.getRange(`G${row}:G${row}`).format.fill = fill;
}
ws.getRange(`A14:K${13 + activeItems.length}`).format.font = { name: font, size: 10, color: "#1F2937" };
ws.getRange(`E14:K${13 + activeItems.length}`).format.wrapText = true;
ws.getRange(`F14:K${13 + activeItems.length}`).format.verticalAlignment = "center";
ws.getRange(`F14:F${13 + activeItems.length}`).format.fill = "#FFF2CC";
ws.getRange(`H14:K${13 + activeItems.length}`).format.fill = "#FFF2CC";
ws.getRange(`A14:K${13 + activeItems.length}`).format.rowHeight = 34;
ws.getRange("A:A").format.columnWidth = 8;
ws.getRange("B:B").format.columnWidth = 16;
ws.getRange("C:C").format.columnWidth = 18;
ws.getRange("D:D").format.columnWidth = 30;
ws.getRange("E:E").format.columnWidth = 42;
ws.getRange("F:F").format.columnWidth = 10;
ws.getRange("G:G").format.columnWidth = 12;
ws.getRange("H:H").format.columnWidth = 20;
ws.getRange("I:I").format.columnWidth = 20;
ws.getRange("J:J").format.columnWidth = 20;
ws.getRange("K:K").format.columnWidth = 34;
ws.freezePanes.freezeRows(13);
ws.freezePanes.freezeColumns(4);
ws.getRange("M2").values = [["Sumber / batasan"]];
ws.getRange("M3").values = [["Daftar rekomendasi untuk mapping survei. Konfirmasi final kebutuhan utilitas, klasifikasi area, dan persetujuan instalasi oleh SRU/IT/HSE."]];
ws.getRange("M4").values = [["Referensi teknis: docs/design/server/final_design.md; docs/design/ch-gw/final_design.md; firmware/versions/version.md."]];
ws.getRange("M2").format = { fill: "#D9EAF7", font: { name: font, bold: true } };
ws.getRange("M3:M4").format = { font: { name: font, size: 9, italic: true, color: "#4B5563" }, wrapText: true };
ws.getRange("M:M").format.columnWidth = 42;
ws.getRange("M3:M4").format.rowHeight = 42;

guide.showGridLines = false;
guide.tabColor = "#5B9BD5";
guide.getRange("A2:H2").merge();
guide.getRange("A2").values = [["Petunjuk Pengisian"]];
guide.getRange("A2").format = { font: { name: font, size: 14, bold: true, color: "#1F2937" } };
guide.getRange("A4:B9").values = [
  ["Kolom","Cara isi"],
  ["Jumlah","Isi kebutuhan aktual setelah survei. Kosongkan bila belum diketahui."],
  ["Ketersediaan","Isi manual, misalnya: Belum dipetakan, Tersedia, Tidak tersedia, Perlu pengadaan, atau Perlu konfirmasi."],
  ["PIC","Isi penanggung jawab yang menyetujui atau menindaklanjuti item."],
  ["Status Survei","Isi manual setelah titik diperiksa."],
  ["Catatan","Isi lokasi spesifik, nomor panel/switch, hasil ukur, hambatan, atau tindak lanjut."]
];
guide.getRange("A4:B4").format = {
  fill: "#0F6B86",
  font: { name: font, size: 10, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
guide.getRange("A4:B9").format.font = { name: font, size: 10 };
guide.getRange("B5:B9").format.wrapText = true;
guide.getRange("A:A").format.columnWidth = 22;
guide.getRange("B:B").format.columnWidth = 95;
guide.getRange("A5:B9").format.rowHeight = 32;
guide.getRange("A12:B14").values = [
  ["Catatan keselamatan",""],
  ["Klasifikasi area","Sebelum menetapkan enclosure, sumber daya, antena, atau metode instalasi di area berpotensi gas mudah terbakar, minta konfirmasi HSE/engineering mengenai klasifikasi area dan persyaratan yang berlaku."],
  ["Batasan","Workbook ini adalah daftar kebutuhan survei, bukan bukti kesesuaian sertifikasi atau bukti instalasi lapangan."]
];
guide.getRange("A12:B12").format = { fill: "#FCE4D6", font: { name: font, bold: true, color: "#9C0006" } };
guide.getRange("A13:B14").format = { font: { name: font, size: 10 }, wrapText: true, verticalAlignment: "top" };
guide.getRange("A13:B14").format.rowHeight = 48;

wb.recalculate();
const inspect = await wb.inspect({ kind: "table", range: `Daftar Kebutuhan!A2:K${13 + activeItems.length}`, include: "values,formulas", tableMaxRows: 70, tableMaxCols: 11 });
console.log(inspect.ndjson);
const errors = await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 50 }, summary: "final formula error scan" });
console.log(errors.ndjson);
const preview = await wb.render({ sheetName: "Daftar Kebutuhan", range: `A2:K${13 + activeItems.length}`, scale: 1 });
await fs.writeFile(`${outputDir}/Daftar_Kebutuhan_Utilitas_SRU_preview.png`, new Uint8Array(await preview.arrayBuffer()));
const xlsx = await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(outputPath);
console.log(`OUTPUT=${outputPath}`);
