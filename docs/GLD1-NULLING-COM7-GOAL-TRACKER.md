# Uji GLD1 Model 1 dan nulling di COM7

Last evidence update: 2026-10-19 15:03:08 WIB
Last tracker heartbeat: 2026-10-19 15:03:08 WIB

Tujuan: upload paket GLD1 Model 1 terbaru melalui Operator Hub ke COM7, lalu jalankan nulling dan ukur durasi serta hasil pada GLD fisik. Lindungi GLD2/GLD3, alarm, LoRa, dan konfigurasi NVS; jangan melakukan Reset NVS tanpa persetujuan tersendiri.

## Progress dashboard

| Scope | Progress | Status | Note |
|---|---:|---|---|
| **Overall goal** | **100%** | Complete | Upload, nulling dan laporan selesai; binding model adalah tindak lanjut yang belum dijalankan. |
| 1. Preflight | 100% | Complete | COM7 teridentifikasi GLD Model 1; paket cocok dan Hub aktif. |
| 2. Upload firmware | 100% | Complete | Upload melalui Operator Hub dan read-back berhasil tanpa Reset NVS. |
| 3. Nulling dan pengukuran | 100% | Complete | 8/8, save, read-back dan workbook terverifikasi. |

## Progress calculation

`20%×100 + 35%×100 + 45%×100 = 100%`. Fase 3: `85%×100 + 15%×100 = 100%`.

| Phase | Weight | Progress | Status | Closure evidence |
|---|---:|---:|---|---|
| 1. Preflight | 20% | 100% | Complete | COM7/device dan paket GLD1 Model 1 teridentifikasi, reset NVS tidak dipilih. |
| 2. Upload firmware | 35% | 100% | Complete | Operator Hub mengembalikan read-back ID 1001 dan versi 0.8.36. |
| 3. Nulling dan pengukuran | 45% | 100% | Complete | Log mulai/selesai, hasil seluruh kanal, read-back profil dan workbook terverifikasi. |

### Phase 1 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 1.1 | Preflight paket dan board COM7 | 100% | Complete | Paket dan board cocok. | 14:39 WIB: GLD ID 1001, board WROOM-1U-N16R8, profil board 1, paket gld_model_1. |

### Phase 2 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 2.1 | Upload melalui Operator Hub | 100% | Complete | Hasil upload dan reconnect. | 14:40 WIB: read-back ID 1001 dan versi 0.8.36. |

### Phase 3 work items

| ID | Work item | Weight in phase | Progress | Status | Next gate | Last update |
|---|---|---:|---:|---|---|---|
| 3.1 | Jalankan dan ukur nulling | 85% | 100% | Complete | Verifikasi read-back setelah restart. | 15:00:47: profil 2 diterapkan; binding masih profil 1. |
| 3.2 | Breakdown langkah dan workbook | 15% | 100% | Complete | Ekspor dan verifikasi workbook. | Workbook 3 sheet dibuka ulang; 8 kanal, 57 kelompok, 692 observasi; render dan formula dicek. |

## Issue register

| ID | Status | Evidence | Closure / next gate |
|---|---|---|---|
| I-01 | Resolved | Upload API Operator Hub selesai dan read-back ID 1001 serta versi 0.8.36 cocok. | Reset NVS tidak digunakan; profil dan binding terbaca siap. |
| I-02 | Resolved | GLD fisik melaporkan 8/8 OK, durasi service 476.964 detik dan NVS save profileId 2 OK. | Cek read-back setelah restart dan buat rincian. |
| I-03 | Accepted risk | Reset NVS menghapus konfigurasi dan profil. | Tidak dipilih; jika wajib, berhenti dan minta arahan. |
| I-04 | Resolved | Computer Use native pipe tidak tersedia. | Jalur API Operator Hub dan bridge GLD lokal aktif; identitas berhasil dibaca. |
| I-05 | Resolved | Pengguna menyatakan area GLD aman dan tidak ada gas. | Konfirmasi operator diterima untuk memulai. |
| I-06 | Deferred | Read-back menunjukkan profil aktif 2, binding model masih 1, `modelProfileReady=false` dan `inferenceValid=false`. | Operator perlu memutuskan binding model ke profil baru; tidak dilakukan otomatis dan inference belum siap. |
| I-07 | Resolved | Status 14:50:18 Clean_Air/alarm=false; operator kemudian mengonfirmasi area aman tanpa gas. | Tetap pantau; jangan menganggap pembacaan perangkat sebagai verifikasi independen. |

## Current work / agent state

Tidak ada agent aktif saat ini. Upload, nulling dan workbook selesai; binding model menunggu keputusan operator.

## Evidence log

- 14:37 WIB: Pengguna mengizinkan upload GLD1 dan uji nulling di COM7. Reset NVS tidak termasuk izin ini.
- 14:38 WIB: Windows mendeteksi USB-SERIAL CH340 pada COM7. Computer Use native pipe tidak tersedia setelah retry/reset; belum ada koneksi atau perubahan pada board.
- 14:39 WIB: Kode UI nulling meminta konfirmasi clean air secara fisik; pengujian tidak akan melewati syarat tersebut tanpa konfirmasi operator.
- 14:39 WIB: Hub lokal dan bridge GLD dimulai; COM7 teridentifikasi sebagai ID 1001, profil model `cnn-dualbranch-board-1-2class-v2`. Paket `gld_model_1` v0.8.36 SHA-256 firmware `9a4ed309ed4b91695cf6893d3e1863e569a8b835276250818e0f2ded0d20b608`.
- 14:40 WIB: Respons upload Operator Hub diterima; read-back firmware v0.8.36 dan ID 1001 cocok. Status pasca-upload: ADS, radio, ML, profil nulling 1 dan binding model siap. Tidak ada Reset NVS. Nulling belum dimulai karena menunggu konfirmasi clean air.
- 14:40 WIB: Status terbaru menunjukkan inference valid, kelas LPG confidence 99 dan `telemetry.alarm=true` (alarmLatched=false). Status ini bukan pembuktian adanya atau tidak adanya gas. Nulling dan acknowledgement clean air tidak dikirim.
- 14:50 WIB: Koreksi presentasi tracker: worker sebelumnya semestinya sudah dikeluarkan selama menunggu pengguna sejak 14:40. Pekerjaan baru untuk mengecek status dimulai kembali sekarang; periode menunggu bukan eksekusi aktif.
- 14:50:18 WIB: GLD COM7 terhubung; inference valid, `Clean_Air`, confidence 80, alarm false. Ini tidak menggantikan pemeriksaan fisik untuk konfirmasi clean air; nulling tetap belum dimulai.
- 14:52 WIB: Pengguna mengonfirmasi area GLD aman dan tidak ada gas. Persiapan untuk memulai nulling atas instruksi pengguna.
- 14:52:32.904 WIB: Perintah mode nulling dikirim sekali; acknowledgement clean-air dan SET_MODE keduanya `ok`. 14:52:36.526: `NULLING_SERVICE_START`, 8 kanal, `avgCount=6`, `confirmCount=8`, `settleMs=5`, `stabilityGapMs=5`. Pengukuran waktu dicatat dari penerimaan log oleh komputer.
- 14:53 WIB: Kanal MQ8 berada di tahap konfirmasi: rentang DAC 464–511 (48 titik); beberapa sampel log memiliki `observeMs=727–729`. Waktu observasi mencakup pembacaan ADC, bukan sekadar jeda 5 ms.
- 14:53:32.553 WIB: MQ8 `NULLING_CH_OK`, DAC 474, setelah sekitar 55,8 detik; MQ135 mulai. Durasi berbasis penerimaan log, bukan waktu MCU yang presisi.
- 14:54:10.970 WIB: MQ135 `NULLING_CH_OK`, DAC 567, setelah sekitar 38,4 detik; MQ3 mulai.
- 14:55:02.766 WIB: MQ3 `NULLING_CH_OK`, DAC 677, setelah sekitar 51,8 detik; MQ5 mulai.
- 14:56:04.754 WIB: MQ5 `NULLING_CH_OK`, DAC 793, setelah sekitar 62,0 detik; MQ4 mulai.
- 14:57:12.697 WIB: MQ4 `NULLING_CH_OK`, DAC 790, setelah sekitar 67,9 detik; MQ7 mulai.
- 14:58:25.272 WIB: MQ7 `NULLING_CH_OK`, DAC 979, setelah sekitar 72,6 detik; MQ6 mulai.
- 14:58 WIB: Pengguna meminta breakdown per kanal dan langkah dalam Excel; fase 3 dikoreksi dengan bobot 85% uji dan 15% workbook.
- 14:59:19.575 WIB: MQ6 `NULLING_CH_OK`, DAC 812, setelah sekitar 54,3 detik; MQ2 mulai. Log nulling tersimpan untuk analisis; timestamp per baris yang telah lampau tidak tersedia, namun `observeMs` MCU tetap tercatat.
- 15:00:33.490 WIB: MQ2 `NULLING_CH_OK` setelah sekitar 73,9 detik; `NULLING_SERVICE_DONE status=Ok successCount=8/8`, `NULLING_NVS_SAVE=OK profileId=2`, `NULLING_RUNTIME_RESULT=PASS`. Durasi service dari penerimaan log PC 476.964 detik; dari perintah sampai hasil sekitar 480.590 detik.
- 15:00:47 WIB: Board kembali ke mode inference dan menerapkan profil ID 2. Binding masih ke ID 1; `modelProfileReady=false`, `inferenceValid=false`. Tidak ada perintah bind otomatis atau Reset NVS.
- 15:01 WIB: Log memuat 692 observasi stabilitas di 57 kelompok kanal/tahap. Total `observeMs` tahap confirm sekitar 289.901 detik; jumlah ini tidak mencakup semua overhead atau merepresentasikan durasi wall-clock lengkap.
- 15:03 WIB: Workbook `outputs/gld1-nulling-com7-20261019/Laporan_Nulling_GLD1_COM7.xlsx` diekspor, tiga sheet dirender dan diperiksa, pemeriksaan formula tidak menemukan error, pembacaan ulang menghitung 57 kelompok tahap dan 692 observasi. Binding model tetap belum dilakukan.
