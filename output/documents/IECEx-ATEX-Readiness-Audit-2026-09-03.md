# Audit Kesiapan IECEx/ATEX — GasleakDetector

Tanggal audit: 2026-09-03  
Sumber kebutuhan: `IECEx ATEX Certification Information Requirements_Edit` (bagian bahasa Inggris). Bagian Mandarin adalah terjemahan dan tidak dihitung dua kali.

## Batas bukti

Audit ini menilai **ketersediaan paket informasi**, bukan menyatakan produk tersertifikasi. Bukti source, skematik/PCB, datasheet, build, atau uji bench tidak menggantikan sertifikat IECEx/ATEX, laporan ExCB/laboratorium, maupun pembuktian produk lapangan. Status `Terbukti tersedia` hanya digunakan jika artefak yang diminta tersedia dan dapat ditelusuri; tidak satu pun baris dinyatakan demikian pada audit ini.

Untuk menjaga cakupan 26 butir dari dokumen sumber, tiga baris payung teknis dan satu baris payung sampel dipertahankan. Baris payung tidak menggantikan penutupan setiap sub-butirnya.

| No. | Poin yang dibahas & maksud | Status ketersediaan | Permasalahan/gap | Solusi yang diperlukan | Status penyelesaian | Bukti saat ini / bukti penutupan |
|---:|---|---|---|---|---|---|
| 1 | Form aplikasi ExCB — memulai pengajuan resmi. | Belum terbukti | Tidak ada template/form ExCB terisi. | Tentukan ExCB dan isi formulir aplikasi resminya. | Belum mulai | Belum ada bukti. |
| 2 | Legalitas badan usaha/manufaktur. | Belum terbukti | Tidak ada akta/izin usaha atau registrasi perusahaan. | Lampirkan dokumen legalitas yang masih berlaku. | Belum mulai | Belum ada bukti. |
| 3 | Struktur organisasi & kontak manufaktur. | Belum terbukti | Tidak ada struktur, peran mutu, atau PIC formal. | Buat bagan organisasi dan daftar kontak pengajuan. | Belum mulai | Belum ada bukti. |
| 4 | Alamat pabrik & fasilitas produksi — menunjukkan lokasi/sarana manufaktur. | Belum terbukti | Tidak ada profil pabrik/fasilitas. | Sediakan alamat, denah/profil fasilitas, dan ruang lingkup produksinya. | Belum mulai | Belum ada bukti. |
| 5 | ISO 9001, quality manual, dan prosedur untuk QAR/QAN (bila relevan). | Tidak berlaku—perlu konfirmasi | Jalur QAR/QAN dan relevansinya belum dikonfirmasi; tidak ada sertifikat ISO atau sistem mutu yang dapat diaudit. | Konfirmasi jalur QAR/QAN dengan ExCB; bila berlaku, kumpulkan sertifikat dan controlled quality manual/prosedur. | Menunggu konfirmasi | Belum ada bukti. |
| 6 | **Payung:** deskripsi produk teknis. | Sebagian tersedia | Ada deskripsi prototipe, tetapi belum menjadi technical file terkendali untuk ExCB. | Satukan sub-butir 7–10 dalam technical description ber-revisi dan terkontrol. | Berjalan | `output/pdf/Technical-Datasheet-GasleakDetector-EN.pdf` menyebut status *Engineering Prototype*; bukan bukti sertifikasi. |
| 7 | Nama produk, model, dan daftar spesifikasi. | Sebagian tersedia | Nama produk ada, tetapi model/varian dan daftar spesifikasi sertifikasi belum dibekukan. | Tetapkan model/varian yang diajukan dan controlled specification list. | Berjalan | Technical Datasheet EN rev. 4.0 mencantumkan `GasleakDetector`; baseline firmware dalamnya sudah historis. |
| 8 | Fungsi dan parameter listrik/mekanik lengkap. | Sebagian tersedia | Fungsi dan beberapa parameter ada; parameter mekanik serta rating yang dapat disertifikasi belum lengkap/terverifikasi. | Buat datasheet teknis terkendali dengan rating, toleransi, dan konfigurasi final. | Berjalan | Technical Datasheet EN rev. 4.0; `docs/design/gld/final_design.md`. |
| 9 | Foto produk dan komponen kunci yang jelas. | Belum terbukti | Tidak ditemukan paket foto identifikasi produk dan komponen kunci yang ditautkan ke konfigurasi final. | Ambil foto terkontrol (tampak keseluruhan, label, enclosure, terminal, cable entry, PCB) beserta serial/revisi. | Belum mulai | Belum ada bukti. |
| 10 | Intended use & lingkungan instalasi: gas group, temperature class, ambient, zone. | Sebagian tersedia | Kegunaan umum ada, tetapi IIA/IIB/IIC, T-class, ambient, dan zona belum ditetapkan. | Tetapkan intended use dan protection concept bersama ExCB; turunkan parameter desain/uji yang sesuai. | Menunggu konfirmasi | Technical Datasheet EN hanya menyatakan fungsi/prototipe, tanpa klasifikasi Ex. |
| 11 | **Payung:** informasi desain dan manufaktur. | Sebagian tersedia | Bukti desain elektronik ada, tetapi file manufaktur dan bukti compliance Ex belum lengkap. | Bentuk design dossier terkendali dari sub-butir 12–17. | Berjalan | Skematik/PCB EasyEDA tersedia pada `docs/wiring/gld-project-ver2-2026-07-01/`. |
| 12 | Gambar lengkap: assembly, komponen, skematik, PCB, enclosure, terminal, grounding; dimensi/toleransi/material. | Sebagian tersedia | Ada skematik dan PCB, tetapi tidak ada paket assembly, enclosure, terminal, grounding, dimensi/toleransi/material lengkap. | Rilis drawing pack ber-revisi dan BOM-linked untuk unit final. | Berjalan | `1-Schematic_GasLeakIntegratedVer2.json`, `1-PCB_PCB_GasLeakIntegratedVer2.json`; README menyatakan ini artefak board impor. |
| 13 | BOM komponen yang memengaruhi keselamatan Ex berikut pabrikan, grade bahan, dan sertifikat/parameter. | Sebagian tersedia | Data komponen dapat ditelusuri dari EDA, tetapi tidak ada BOM safety-critical yang terkontrol maupun bukti sertifikat/grade lengkap. | Buat BOM Ex-critical; ikat setiap part ke datasheet, CoC, dan sertifikat yang relevan. | Belum mulai | Tidak ada BOM sertifikasi mandiri yang ditemukan. |
| 14 | Datasheet material non-logam dan bukti pemasok. | Belum terbukti | Tidak ada datasheet/CoC enclosure, seal, insulator, potting, atau plastik yang mendukung klaim Ex. | Kumpulkan datasheet, traceability lot, deklarasi kesesuaian, dan laporan uji pemasok. | Belum mulai | Belum ada bukti. |
| 15 | Deskripsi proses manufaktur yang kritis bagi keselamatan Ex. | Belum terbukti | Tidak ada SOP proses, kontrol toleransi, inspeksi, welding/potting/bonding record. | Susun dan kendalikan SOP/WI, inspection plan, serta traceability proses. | Belum mulai | Belum ada bukti. |
| 16 | Kalkulasi/penjelasan terkait proteksi ledakan (bila berlaku). | Tidak berlaku—perlu konfirmasi | Protection concept dan tipe proteksi belum ditetapkan; karena itu kebutuhan kalkulasinya belum dapat dipilih. | Konfirmasi konsep proteksi dan standar seri IEC 60079 yang berlaku dengan ExCB; lakukan kalkulasi/analisis yang diminta. | Menunggu konfirmasi | Belum ada bukti. |
| 17 | Kalkulasi temperature group (titik terpanas). | Tidak berlaku—perlu konfirmasi | Tidak ada target T-class, kondisi beban, ambient, atau hasil thermal test. | Tetapkan T-class/ambient target; lakukan analisis dan pengukuran temperatur worst-case oleh lab yang sesuai. | Menunggu konfirmasi | Belum ada bukti. |
| 18 | **Payung:** instruksi penggunaan & instalasi (draft). | Sebagian tersedia | Manual operasi ada, tetapi belum menjadi manual instalasi Ex yang terkendali. | Konsolidasikan sub-butir 19–23 ke draft manual untuk review ExCB. | Berjalan | `docs/manual/gld-operation-manual.md` berisi prosedur operasional; bukan manual Ex yang disetujui. |
| 19 | Peringatan keselamatan jelas. | Sebagian tersedia | Ada troubleshooting/operational caution, namun tidak ada warning Ex spesifik yang disetujui terhadap zona/tipe proteksi final. | Tulis warning berdasarkan risk assessment, proteksi final, dan review ExCB. | Berjalan | `docs/manual/gld-operation-manual.md`; bukti Ex-specific belum ada. |
| 20 | Persyaratan instalasi: cable entry, torque, grounding, cleaning. | Sebagian tersedia | Petunjuk operasi ada, tetapi spesifikasi cable entry, torque, grounding, dan cleaning Ex tidak lengkap. | Buat installation instruction terkendali dengan drawing referensi dan nilai tervalidasi. | Berjalan | Dokumen wiring/manual tersedia, tetapi tidak membuktikan nilai instalasi Ex. |
| 21 | Operasi dan pemeliharaan: frekuensi, isi, pencegahan. | Sebagian tersedia | Prosedur operasi ada; interval/larangan maintenance terkait Ex belum terdefinisi. | Tambahkan preventive-maintenance schedule, inspection criteria, dan batas servis sesuai proteksi final. | Berjalan | `docs/manual/gld-operation-manual.md`. |
| 22 | Informasi nameplate dengan seluruh marking IECEx/ATEX. | Belum terbukti | Tidak ada desain/rekaman nameplate atau marking yang disetujui. | Buat artwork nameplate setelah certificate number, protection marking, ambient, IP, dan serialisation disetujui. | Belum mulai | Belum ada bukti. |
| 23 | Sertifikat ATEX untuk Ex components. | Belum terbukti | Tidak ada daftar komponen Ex maupun sertifikat yang ditautkan ke BOM. | Identifikasi Ex components, kumpulkan sertifikat valid, dan verifikasi kondisi penggunaan. | Belum mulai | Belum ada bukti. |
| 24 | **Payung:** informasi sampel. | Belum terbukti | Tidak ada sample dossier untuk unit yang akan diuji. | Buat register sampel untuk sub-butir 25–26. | Belum mulai | Belum ada bukti. |
| 25 | Model, serial number, dan status operasional sampel. | Belum terbukti | Catatan bench/firmware tidak menggantikan identitas sampel untuk sertifikasi. | Tetapkan unit sampel final, serial/revisi hardware/firmware, konfigurasi, dan status power-on. | Belum mulai | Ada laporan bench/nulling, tetapi bukan sample register ExCB. |
| 26 | Fixture/peralatan bantu uji sampel. | Belum terbukti | Tidak ada daftar fixture dan setup uji yang tervalidasi untuk ExCB/lab. | Inventaris fixture, catu daya, adaptor, load, dan instruksi aman untuk pengujian. | Belum mulai | `GLD2-functional-test-plan-draft.md` hanya merencanakan alat bench; bukan bukti kesiapan lab. |

## Rekap status

| Status ketersediaan | Jumlah |
|---|---:|
| Terbukti tersedia | 0 |
| Sebagian tersedia | 11 |
| Belum terbukti | 12 |
| Tidak berlaku—perlu konfirmasi | 3 |

## Blocker utama sebelum pengajuan

1. Pemohon/manufaktur dan sistem mutu belum terdokumentasi untuk ExCB/QAR/QAN.
2. Konsep proteksi, zona, gas group, temperature class, serta ambient belum diputuskan.
3. Tidak ada design dossier final: enclosure/assembly/terminal/grounding drawings, safety-critical BOM, dan data material.
4. Tidak ada kalkulasi dan laporan uji Ex/thermal/produk dari lab atau ExCB.
5. Tidak ada nameplate/marking, sertifikat komponen Ex, maupun sample dossier yang traceable.

## Bukti yang harus dikumpulkan untuk menutup audit

Prioritas pengumpulan: (1) keputusan scope sertifikasi dan ExCB, (2) legalitas/manufacturing/QMS, (3) configuration baseline dan drawing/BOM/material dossier, (4) intended-use/protection/thermal analysis, (5) manual + marking, kemudian (6) sample register, fixture, dan laporan uji/sertifikat ExCB.

## Catatan bukti repository

- `Technical-Datasheet-GasleakDetector-EN.pdf` sendiri menandai perangkat sebagai **Engineering Prototype**. Angka/versi di dalamnya harus direkonsiliasi terhadap konfigurasi produk yang akan disertifikasi.
- `GLD2-functional-test-plan-draft.md` secara eksplisit adalah **draft rencana uji**, bukan bukti bahwa seluruh butir lulus. Ia juga membedakan ACK/log firmware dari pembuktian fisik.
- Skematik/PCB EasyEDA dan `docs/design/gld/final_design.md` berguna sebagai input technical file, tetapi tidak membuktikan kepatuhan IECEx/ATEX.
