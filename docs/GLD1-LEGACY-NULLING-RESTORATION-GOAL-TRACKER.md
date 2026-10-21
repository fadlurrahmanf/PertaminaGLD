# GLD1 — Restorasi algoritma nulling deterministik

Last tracker heartbeat: 2026-10-21 12:25:00 +07:00  
Last evidence update: 2026-10-21 12:25:00 +07:00

## Progress dashboard

| Scope | Progress | Status | Note |
|---|---:|---|---|
| **Overall goal** | **100%** | Complete | Alur nulling deterministik tersedia untuk seluruh paket GLD1 Model 1–3; bukti fisik tersedia pada Model 1. |
| Phase 1. Audit dan isolasi | 100% | Done | Guard GLD1 dan pemeriksaan profil terlindungi tersedia. |
| Phase 2. Implementasi GLD1 | 100% | Done | Jalur deterministik GLD1 telah lulus seluruh bukti unit/mock yang diminta. |
| Phase 3. Bukti build dan regresi | 100% | Done | Native GLD1, compile/run GLD2/GLD3, build GLD1, dan audit diff selesai. |
| Phase 4. Paket GLD1 dan bukti COM7 | 100% | Done | Paket Model 1–3 diperbarui; Model 1 terbukti 8/8 di COM7. |

## Progress calculation

`20% × 100 + 45% × 100 + 30% × 100 + 5% × 100 = 100%`

| Phase | Weight | Progress | Status | Closure evidence |
|---|---:|---:|---|---|
| 1. Audit dan isolasi | 20% | 100% | Done | Guard GLD1 model 1 dan compile/run profil GLD2/GLD3 telah diverifikasi. |
| 2. Implementasi GLD1 | 45% | 100% | Done | Jalur deterministik lulus bukti sampel, range, binary, confirm, dan gate 8/8. |
| 3. Bukti build dan regresi | 30% | 100% | Done | Unit/mock, compile profile terlindungi, build GLD1, dan audit diff lulus. |
| 4. Paket GLD1 dan bukti COM7 | 5% | 100% | Done | Full run raw baru selesai, profil tersimpan, dan workbook pengganti tervalidasi. |

## Issue register

| ID | Status | Evidence | Closure / next-evidence gate |
|---|---|---|---|
| LNR-1 | Solved | Sesudah target baseline-negatif diperbaiki menjadi target positif, run COM7 menyimpan profil baru ID 4 dan memverifikasi 8 MCP. | Closed by physical 8/8 run; kualitas jangka panjang tetap dipantau oleh operator. |
| LNR-2 | Open | `GldNullingService` dibagi lintas profile. | Guard GLD1 eksplisit dan regresi GLD2/GLD3 sebelum paket diperbarui. |
| LNR-3 | Accepted risk | Tidak ada pengujian perangkat fisik dalam tugas ini. | Operator melakukan upload/test fisik manual setelah paket siap. |
| LNR-4 | Solved | Reflash ulang dengan urutan `write_flash` Operator Hub memulihkan boot aplikasi. | COM7 membalas `GET_STATUS` dan menyelesaikan nulling 8/8. |

### Phase 1 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 1.1 | Audit struktur `GldNullingService` dan konfigurasi | 100% | Done | Implementasi terisolasi diverifikasi oleh test | Audit independen menyetujui helper GLD1 terpisah; tidak menyentuh NVS/header/main. |
| 1.2 | Rekam baseline GLD2/GLD3 dan cakupan diff | 100% | Done | Hanya compile/run native tanpa paket profile lain | Harness mengompilasi dan menjalankan GLD2 serta GLD3 tanpa macro GLD1; keduanya memakai confirm shared 75 kandidat. |

### Phase 2 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 2.1 | Baseline dan target GLD1 deterministik | 100% | Done | 11×8 baseline dan rumus target diuji | Native harness membuktikan setiap baseline valid memakai tepat 8 read dan target floor/50%. |
| 2.2 | Exponential dan binary GLD1 | 100% | Done | Langkah sampai 2048 serta crossing terendah diuji | Native harness mencapai code 4095 memakai increment maksimum 2048 dan memilih crossing terendah. |
| 2.3 | Confirm dan pemilihan hasil GLD1 | 100% | Done | 10/20 kandidat, 10 sampel, overshoot terendah diuji | Native harness membuktikan confirm 10/20 dengan tepat 10 read, tanpa verify/final bump. |
| 2.4 | Ketahanan profil 8/8 | 100% | Done | Kanal gagal tidak menghasilkan profil valid/simpan | Kanal ketiga dibuat ADC-invalid; hasil 7/8 dan `isNullingProfileValid` false. |
| 2.5 | Terapkan jalur GLD1 pada Model 2 dan 3 | 100% | Done | Guard build GLD1 sama untuk Model 1–3 | `PGL_GLD1_FAST_NULLING=1` ditambahkan hanya pada env `gld_model_2` dan `gld_model_3`; guard sumber tetap mengecualikan GLD2/ATEX. |

### Phase 3 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 3.1 | Unit/mock GLD1 | 100% | Done | Semua skenario wajib lulus | `run_test.py` lulus GLD1: 8/10 sampel, 2048, binary, confirm 10/20, overshoot, 8/8. |
| 3.2 | Build GLD1 | 100% | Done | `gld_model_1` build lulus | PlatformIO `pio run -e gld_model_1` lulus dalam 19,377 s; RAM 41,5%, flash 15,8%. |
| 3.3 | Regresi GLD2/GLD3 | 100% | Done | Pengecekan behavior/source dan build/check fokus lulus | Compile/run native GLD2 + GLD3 lulus tanpa macro GLD1 dan menunjukkan confirm shared 75 kandidat. |
| 3.4 | Verifikasi diff hard-scope | 100% | Done | Diff jalur tugas hanya file nulling/test/paket GLD1 | Perubahan tugas berada pada `GldNullingService.cpp`, native test baru, tracker, dan `gld_model_1/latest`; worktree juga memiliki perubahan lama di luar scope yang tidak disentuh oleh tugas ini. |

### Phase 4 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 4.1 | Paket firmware GLD1 Model 1–3 | 100% | Done | Ketiga paket GLD1 berubah dan valid | Build `gld_model_1`, `gld_model_2`, dan `gld_model_3`, termasuk hook paket, lulus. |
| 4.2 | Bukti COM7 pasca-koreksi target | 100% | Done | Full raw capture 8/8, profil tersimpan, dan workbook baru diverifikasi | `NULLING_RUNTIME_RESULT=PASS`, `NULLING_NVS_SAVE=OK profileId=5`; GET_STATUS menampilkan 8/8 MCP read-back cocok/verified. |

## Protected baseline

Tidak disentuh: GLD2, GLD3, profile selain GLD1, alarm, LoRa, AES/provisioning, runtime sensor/model/inference/dataset, upload firmware, Operator Hub selain artefak paket `gld_model_1` yang dihasilkan build, UI, serial protocol, NVS selain profil/config nulling GLD1 yang sudah ada, board pin, dan hardware driver.

## Current work / agent state

| Sub-agent / worker | Active work item | Started at | Elapsed | Progress | Activity / state |
|---|---|---:|---:|---:|---|
| Tidak ada agent aktif saat ini. |

## Evidence log

- 2026-10-21 11:25 +07:00 — User meminta pengulangan seluruh nulling COM7 dan workbook pengganti dari data baru agar MQ2 juga memiliki penanda X=MCP yang berasal dari run yang sama. Run akan direkam penuh ke file; tidak ada perubahan firmware atau profil non-GLD1.
- 2026-10-21 11:26 +07:00 — Full nulling raw capture selesai `Ok successCount=8/8`, lalu firmware menyimpan profil ID 5. GET_STATUS pasca-run membuktikan runtime MCP code/readback/verified sama untuk semua kanal: MQ8=537, MQ135=636, MQ3=922, MQ5=841, MQ4=794, MQ7=1003, MQ6=841, MQ2=169. Workbook pengganti dibuat dari 384 titik raw baseline/exponential/binary/confirm; MQ2 memuat confirm MCP 169 pada `0.016575884 V` melampaui target `0.016091408 V`, sehingga garis X ungu memiliki titik sumber pada run yang sama.
- 2026-10-21 12:25 +07:00 — Atas persetujuan user, flag deterministik GLD1 diperluas dari paket Model 1 ke GLD1 Model 2 dan Model 3. Guard sumber tetap mengharuskan board GLD1 dan secara eksplisit mengecualikan GLD2/ATEX. Native nulling test, build tiga paket, dan 20 test paket/profile lulus. Paket Operator Hub untuk Model 1–3 diperbarui. Bukti perangkat fisik 8/8 tetap hanya dari Model 1 COM7; belum mengklaim hasil fisik Model 2 atau 3.

- 2026-10-21 11:15 +07:00 — Koreksi GLD1-only dibuat agar baseline negatif memakai `0 + threshold` sebagai target positif. Harness native lulus untuk target positif, kandidat confirm, dan gate profil 8/8; build `gld_model_1` serta paket GLD1 terbaru lulus. COM7 dikenali sebagai CH340, tetapi sesudah flash awal yang memakai parameter flash eksplisit perangkat menampilkan reset ROM berulang sebelum aplikasi merespons. Tidak ada nulling dijalankan dalam kondisi itu; pemulihan boot sedang dilakukan menggunakan urutan flash yang sama seperti Operator Hub dan tanpa reset NVS.
- 2026-10-21 11:11 +07:00 — Reflash ulang yang mengikuti urutan `write_flash` Operator Hub memverifikasi seluruh hash dan memulihkan boot aplikasi. Full nulling GLD1 dimulai setelah konfirmasi clean-air yang telah diotorisasi pengguna; MQ8 membuktikan target baru: baseline `-0.001166046`, target positif `+0.000583023`, MCP 539 pada `+0.003858960`. Run 8 kanal masih berjalan; belum ada klaim untuk kanal lain maupun profil 8/8.
- 2026-10-21 11:14 +07:00 — Full nulling COM7 selesai dan reboot normal. `GET_STATUS` pasca-run membuktikan `activeNullingProfileId=4`, `nullingProfileApplied=true`, dan delapan runtime MCP read-back cocok/verified: MQ8=539, MQ135=639, MQ3=918, MQ5=843, MQ4=794, MQ7=1006, MQ6=840, MQ2=170. Karena firmware hanya menyimpan profil baru ketika 8/8 kanal sukses, ini adalah bukti fisik 8/8. Tidak ada perubahan GLD2/GLD3 atau subsistem lain.

- 2026-10-20 12:17:29 +07:00 — User menetapkan scope mutlak: hanya algoritma/proses nulling firmware GLD1. Tidak ada flash/upload fisik. Tugas dimulai dengan audit read-only terhadap `GldNullingService` dan konfigurasi nulling yang diperlukan.
- 2026-10-20 12:20:16 +07:00 — Audit menemukan semua perilaku yang akan diganti berada pada jalur `PGL_GLD1_FAST_NULLING` di `GldNullingService.cpp`: stability window/retry, noise threshold, recheck/recovery bracket, confirm cap/verify dan final bump. Jalur model lain tidak menerima macro ini. Test native sudah memiliki compile mode GLD2; akan ditambah pemeriksaan model GLD3 tanpa menjalankan atau mengemas profile lain.
- 2026-10-20 12:24:13 +07:00 — Audit independen selesai dan menyetujui permukaan minimum: `GldNullingService.cpp` dengan guard gld_model_1 yang sudah eksklusif. Ditambahkan helper deterministik GLD1: direct DAC write, rata-rata tepat 8/10, target `baseline + max(abs(baseline)*0.5, floor)`, exponential maksimum 2048, binary, confirm 10/20, dan tanpa recheck/verify/final-bump. Jalur shared GLD2/GLD3, `GldUnifiedMain`, header/NVS/UI/protocol tidak diubah. Uji belum lulus; panggilan awal gagal hanya karena alias `python` tidak ada di shell, bukan bukti firmware.
- 2026-10-20 12:27:57 +07:00 — Harness native dipersempit menjadi bukti algoritma yang diminta dan ditambah compile/run profile GLD3 tanpa macro fast. Run pertama mencapai assertion confirm baseline-negatif: fixture menghasilkan nilai di bawah `minFinalV=0`, sehingga kandidat memang tidak valid menurut spesifikasi. Fixture diperbaiki untuk menyediakan kandidat >= `minFinalV`; belum ada hasil test lulus. Heartbeat SLA breach: 03:44 sejak heartbeat sebelumnya saat penggantian harness dan run pertama; tidak ada timestamp dibackdate.
- 2026-10-20 12:35:00 +07:00 — Native harness lulus: baseline/search valid tepat 8 read, baseline 11 titik, target `max(abs(baseline)*0.5, floor)`, langkah eksponensial hingga 2048, binary crossing terendah, confirm positif 10/negatif 20 dengan tepat 10 read, overshoot minimum, tanpa stability/recheck/verify/final-bump, dan profil 7/8 invalid. Harness juga compile/run GLD2 serta GLD3 tanpa macro GLD1 dan keduanya mempertahankan confirm shared 75 kandidat. Build `gld_model_1` sedang berjalan sebagai satu proses latar; tidak ada flash/upload fisik.
- 2026-10-20 12:39:25 +07:00 — Build pertama berhenti pada linker karena response file sementara Windows hilang; tidak ada error kode. Build diulang dengan direktori sementara khusus dan sukses: `pio run -e gld_model_1` (19,377 s; RAM 41,5%; flash 15,8%). Hook build memperbarui hanya paket `gld_model_1`; metadata `model-provenance.json` dipertahankan dengan checksum firmware baru. Validasi manifest/hash flash/provenance/marker legacy lulus. Tidak ada target GLD2/GLD3, flash, atau upload perangkat fisik pada tugas ini.
- 2026-10-20 12:48 +07:00 — Validasi fisik pasca-tugas atas otorisasi user: paket `gld_model_1` di-upload ke COM7 dengan `resetNvs=false`; device read-back GLD1 ID 1001 boot normal. Satu full nulling menjalankan marker `algorithm=gld1_legacy_deterministic`, lalu selesai `PartialSuccess 1/8`: MQ8/MQ135/MQ3/MQ5/MQ4/MQ6 gagal tahap exponential karena `adc_invalid` pada DAC 1023; MQ2 gagal confirm tanpa kandidat valid; hanya MQ7 sukses. Sesuai gate 8/8, tidak ada profil parsial disimpan dan boot berikutnya memulihkan profil lengkap sebelumnya ID 3. Ini bukti perangkat nyata tentang hasil tersebut, bukan keberhasilan 8/8.
- 2026-10-20 13:14 +07:00 — Diagnostik GLD1-only ditambahkan, dibangun, divalidasi native, dipaketkan, lalu di-upload ke COM7 dengan `resetNvs=false`. Full nulling ulang membuktikan `status=0`, `saturated=1`, `finite=1`, `voltage=0.156062484` pada pembacaan pertama dari 8 di DAC 1023 untuk MQ8, MQ135, MQ3, MQ5, MQ4, dan MQ6. Jadi penyebab terkonfirmasi adalah saturasi ADC, bukan timeout atau nilai non-finite. MQ7 tetap sukses; MQ2 masih tidak memiliki kandidat confirm valid. Hasil akhir tetap `PartialSuccess 1/8`, tanpa profil parsial disimpan.
- 2026-10-20 13:19 +07:00 — Koreksi GLD1-only: urutan probe exponential sebelumnya keliru kumulatif (`1,3,7,…`). Kini tepat `1,2,4,…,2048`, diikuti probe akhir DAC 4095 hanya bila target masih belum tercapai. Native test membuktikan urutan itu serta semua test GLD1/GLD2/GLD3 protected lulus; build `gld_model_1` lulus dan paket GLD1 diperbarui. Paket koreksi ini belum di-upload ke COM7.
- 2026-10-20 13:23 +07:00 — Paket sequence powers-of-two di-upload ke COM7 dengan `resetNvs=false`; full nulling fisik selesai `PartialSuccess 2/8`. MQ8 membuktikan alur yang diharapkan: exponential `256=-0.001109343` (belum target), `512=0.004093132` (target tercapai valid), binary range `256..512`, lalu memilih DAC 509 dan confirm memilih DAC 510. MQ7 juga sukses. MQ135/MQ3/MQ5/MQ4/MQ6 tetap ADC-saturasi pada DAC 1024; MQ2 tetap gagal confirm tanpa kandidat. Tidak ada profil parsial disimpan.
- 2026-10-20 13:31 +07:00 — Perbaikan semantics exponential GLD1: pembacaan status-OK, finite, tetapi saturated dipakai hanya sebagai batas atas crossing; baseline, binary, dan confirm tetap menolak pembacaan jenuh. Unit/mock dan build lulus; paket GLD1 di-upload ke COM7 dengan `resetNvs=false`. Full nulling fisik mencapai `PartialSuccess 7/8`: MQ8/MQ135/MQ3/MQ5/MQ4/MQ7/MQ6 sukses. Untuk lima kanal yang sebelumnya berhenti, log membuktikan `upper=saturated` pada range `512..1024`, lalu binary dan confirm menemukan DAC non-saturasi. Hanya MQ2 gagal confirm tanpa kandidat dari 20 kandidat. Tidak ada profil parsial disimpan.
- 2026-10-20 13:58 +07:00 — Data karakterisasi MCP/ADC GLD1 dibuat sebagai `outputs/gld1-mcp-sweep-20261020/gld1_mcp_response.xlsx`: delapan sheet (MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2), total 378 titik ukur perangkat nyata dari run nulling terakhir. Setiap sheet memuat baseline DAC 0–10, titik exponential, binary, dan confirm sampai/sekitar crossing beserta tegangan, target, delta, dan jumlah sampel. Ini bukan full-scale linear semua kode DAC: dua probe diagnostik linear dihentikan karena sangat lambat dan firmware mengonfirmasi DAC dipulihkan (MQ8=502; MQ2=54). Tidak ada firmware, NVS, atau profil nulling yang diubah oleh pekerjaan ekspor data ini.
