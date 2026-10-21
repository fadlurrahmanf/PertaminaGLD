# Optimasi nulling GLD1 Model 1

Last updated: 2026-10-19 16:03:52 +07:00
Last tracker heartbeat: 2026-10-19 16:03:52 +07:00
Last evidence update: 2026-10-19 16:03:52 +07:00

## Progress dashboard

| Scope | Progress | Status | Note |
|---|---:|---|---|
| **Overall goal** | **98%** | Waiting for external evidence | Satu run terukur dan firmware acuan dikembalikan; akurasi independen belum terbukti. |
| 1. Baseline dan kandidat | 100% | Done | Rekaman, ukuran kandidat, serta batas ADC dianalisis. |
| 2. Implementasi dan uji host | 100% | Done | Flag eksperimen dibuat dan 7 uji host lulus. |
| 3. Build dan batas validasi | 90% | Waiting for external evidence | Laporan selesai; pengujian akurasi independen dan berulang belum tersedia. |

## Issue register

| ID | Status | Evidence / risk | Next evidence gate |
|---|---|---|---|
| I-01 | Open | 19 Oktober: nulling 8/8 memerlukan 476.964 detik; confirm mencakup 289.901 detik observasi. Eksperimen akan menghapus lima evaluasi exponential yang tidak dapat menjadi bracket; hemat observasi sekitar 23 s pada satu rekaman. | Implementasi opt-in terisolasi; verifikasi host serta nanti A/B fisik. |
| I-02 | Open | Keakuratan hasil kalibrasi tidak dapat dibuktikan dari satu rekaman atau hanya dengan simulasi. ±10 DAC melewatkan kandidat terverifikasi MQ6; ±15 dan ±20 mempertahankannya pada satu rekaman saja. | Tentukan validasi fisik/independen yang diperlukan; jangan klaim replay sebagai bukti kalibrasi. |
| I-03 | Deferred | Profil nulling aktif 3 masih terikat dengan profil model lama 1; inference belum siap pada pembacaan terakhir. | Binding memerlukan keputusan operator terpisah setelah kualitas kalibrasi dinilai layak. |
| I-04 | Open | Baseline 335/398 dan eksperimen 269/343 observasi confirm `stable=0`; semua 8 observasi final kedua run `stable=0`. Kode memakai `valid` dan ambang, bukan `stable`, sebagai syarat kandidat. Ini sendiri tidak membuktikan hasil salah atau benar. | Evaluasi kestabilan dan akurasi dengan pengukuran pembanding independen sebelum deployment. |
| I-05 | Solved | Build kandidat awal gagal saat linker memakai file sementara di `C:\WINDOWS\TEMP`. Mengatur direktori file sementara lokal hanya untuk proses build menghasilkan link sukses; penyebab sistem dasarnya tidak dipastikan. | Build berhasil pada path terisolasi; package baseline tetap sama. |

## Progress calculation

`35%×100 + 40%×100 + 25%×(270/3) = 97.5%` (dibulatkan 98%). Persentase kegiatan, bukan bukti keselamatan.

| Phase | Weight | Progress | Status | Closure evidence |
|---|---:|---:|---|---|
| 1. Baseline dan kandidat | 35% | 100% | Done | Algoritma dan rekaman dianalisis; risiko kandidat didokumentasikan. |
| 2. Implementasi dan uji host | 40% | 100% | Done | Kandidat dibenarkan dan diuji; atau keputusan tidak mengubah tercatat berdasar bukti. |
| 3. Build dan batas validasi | 25% | 90% | Waiting for external evidence | Pembanding akurasi, batas penerimaan, dan run A/B berulang masih diperlukan. |

### Phase 1 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 1.1 | Audit kode dan baseline fisik | 100% | Done | Temukan biaya per pemeriksaan dan perlindungannya. | 398 titik confirm; ADC menulis MUX berulang; final check tetap ada. |
| 1.2 | Bandingkan kandidat memakai data yang tersedia | 100% | Done | Pengukuran dan risiko jelas, tanpa menganggap replay sebagai bukti fisik. | ±5 menyertakan 4/8 kandidat, ±10 7/8, ±15 8/8 pada satu rekaman. |

### Phase 2 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 2.1 | Pilih atau tolak perubahan secara konservatif | 100% | Done | Perubahan punya alasan dan batas validasi. | Eksperimen skip exponential 1–31 dipilih; confirm dan ADC tidak dipangkas. |
| 2.2 | Uji host dan regresi GLD1/non-target | 100% | Done | Bukti uji atau alasan tidak melakukan perubahan. | 7 uji host lulus; eksperimen dimatikan di konfigurasi produksi. |

### Phase 3 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 3.1 | Build terpisah jika diperlukan | 100% | Done | Build dan artefak tidak menggantikan baseline. | Build eksperimen sukses, SHA `995d825986a526788e8048e00336d79285a5aa19783b344edc98af2364c4f3db`; package baseline tidak berubah. |
| 3.2 | Laporkan batas validasi dan langkah fisik | 100% | Done | Hasil/risiko disampaikan tanpa klaim keselamatan. | Dokumen eksperimen dan batas hasil diperbarui. |
| 3.3 | Validasi fisik dan akurasi A/B | 70% | Waiting for external evidence | Dapatkan alat/protokol pembanding dan batas penerimaan; lakukan A/B berulang jika diotorisasi. | Satu run eksperimen 8/8 PASS; firmware acuan kembali; akurasi belum terbukti. |

## Current work / agent state

Tidak ada agent aktif saat ini. Menunggu alat dan protokol pembanding akurasi
serta batas penerimaan untuk melanjutkan validasi fisik.

## Protected baseline

- GLD1 Model 1 firmware 0.8.36, package SHA `9a4ed309ed4b91695cf6893d3e1863e569a8b835276250818e0f2ded0d20b608`: baseline harus dipertahankan dan dibackup sebelum uji firmware baru.
- GLD2, GLD3, model dan profil lain, kode alarm, LoRa dan alur upload: tidak berubah. NVS tidak dihapus, tetapi profil nulling GLD1 ditulis ulang oleh run yang diotorisasi.
- User mengizinkan upload dan nulling GLD1 dan mengonfirmasi udara bersih saat ini. Hanya satu owner COM7. Reset NVS dan binding model tidak diotorisasi oleh izin ini; nulling yang berhasil otomatis mengganti profil dan dapat membuat binding lama tidak cocok.

## Evidence log

- 2026-10-19 15:36:41 +07:00: Pekerjaan dimulai; data awal satu kali pengukuran fisik. Estimasi bukan jaminan keselamatan.
- 2026-10-19 15:37:24 +07:00: Tahap confirm memindai kandidat berurutan, memverifikasi sebagian kandidat lalu melakukan pemeriksaan akhir. ADC menulis MUX dengan delay 10 ms berulang di setiap pembacaan; implikasi timing/perilaku belum divalidasi hardware.
- 2026-10-19 15:38:13 +07:00: Replay subset atas satu rekaman: ±5 memuat 4/8 kandidat terverifikasi, ±10 memuat 7/8 (MQ6 hilang), ±15 memuat 8/8. Pengurangan observasi ±15 = 142.177 s secara aritmetika saja, bukan prediksi waktu atau bukti akurasi, karena urutan dan waktu pembacaan berubah.
- 2026-10-19 15:38:13 +07:00: Heartbeat SLA breach: jeda 49 detik dari 15:37:24; pemeriksaan waktu terlambat saat analisis rekaman. Tidak ada progres yang direkayasa.
- 2026-10-19 15:39:48 +07:00: Tes source-scope GLD1 lulus 3/3; SHA package aktif tetap `9a4ed309ed4b91695cf6893d3e1863e569a8b835276250818e0f2ded0d20b608`. Datasheet TI mensyaratkan timing perintah ADC dan data-ready yang benar; memotong 10 ms tanpa validasi dapat mengubah interval sampling/stabilitas. Belum ada firmware baru.
- 2026-10-19 15:39:48 +07:00: Heartbeat SLA breach: jeda 52 detik dari 15:38:56; pemeriksaan waktu terlambat saat konsultasi datasheet dan pemeriksaan host.
- 2026-10-19 15:40:21 +07:00: Review GLD_Agent read-only selesai. Opsi terendah risiko adalah melewati 5 observasi exponential 1, 3, 7, 15, 31 (tidak dapat memenuhi batas bracket >=100), tetap mulai pada 63. Estimasi ±23 detik hanya berasal dari replay; analog settling dan AGC berbeda, sehingga eksperimen tidak siap deployment tanpa pengujian A/B nyata.
- 2026-10-19 15:41:06 +07:00: Eksperimen di source hanya dapat aktif dengan flag khusus dan flag GLD1 Model 1; 7 source/host tests lulus. Build terpisah belum berhasil dikonfigurasi; package baseline tetap tidak diubah.
- 2026-10-19 15:41:51 +07:00: Build eksperimen ternyata dapat memuat konfigurasi alternatif; opsi `--list-targets` sebelumnya memakai daftar env default sehingga memberi diagnosis palsu. Build nyata sedang berjalan dalam tmp dengan post-script package dinonaktifkan. Rekaman berisi tepat 40 observasi exponential yang akan dilewati, jumlah `observeMs` 23.318 detik; perubahan urutan membuatnya bukan prediksi waktu aktual.
- 2026-10-19 15:42:33 +07:00: `envdump` memverifikasi flag FAST dan flag EXPERIMENT aktif hanya pada build eksperimen; output tidak memuat operator package post-script. Kompilasi masih berjalan.
- 2026-10-19 15:43:04 +07:00: Tercatat 335 dari 398 observasi confirm `stable=0` dalam baseline; algoritma tidak menjadikan field itu syarat kelulusan. Belum diketahui dampaknya pada akurasi. Source contract alarm lulus; tidak ada perubahan alarm.
- 2026-10-19 15:43:42 +07:00: Dokumen `docs/GLD1-NULLING-EXPERIMENT.md` menyimpan metode, batas replay, risiko dan gerbang A/B fisik. Kompilasi library masih berlangsung.
- 2026-10-19 15:44:57 +07:00: Build pertama gagal pada linker `cannot find @C:\WINDOWS\TEMP\cc...: Invalid argument`; penyebab belum dipastikan. Uji source tetap 7/7 dan baseline package SHA tidak berubah.
- 2026-10-19 15:46:04 +07:00: Build eksperimen sukses setelah variabel direktori sementara khusus untuk proses build diarahkan ke folder task, tanpa mengubah pengaturan Windows. RAM 41.5%, flash 15.9%; artefak `tmp/gld1-nulling-exp-build/gld1_nulling_experiment/firmware.bin`; SHA `995d825986a526788e8048e00336d79285a5aa19783b344edc98af2364c4f3db`. Package Operator Hub tetap SHA `9a4ed309ed4b91695cf6893d3e1863e569a8b835276250818e0f2ded0d20b608`. Tidak ada upload, COM, atau hasil A/B fisik.
- 2026-10-19 15:46:04 +07:00: Heartbeat SLA breach: 67 detik sejak 15:44:57 saat tiga percobaan link berlangsung; hasil keberhasilan dicatat pada waktu ini, tidak dibackdate.
- 2026-10-19 15:49:34 +07:00: User menyetujui upload firmware dan nulling GLD1 untuk membandingkan optimasi fisik. Preflight dimulai; konfirmasi udara bersih untuk saat ini diminta dan validasi referensi/kriteria belum tersedia. Tidak menjamin kualitas atau kecepatan minimum hanya dari satu run.
- 2026-10-19 15:52:02 +07:00: User mengonfirmasi area dan semua sensor berada dalam udara bersih. Preflight menemukan GLD ID 1001, COM7, profil aktif 2 dan bound profil 1; inference belum siap. Review menegaskan tiap nulling sukses mengganti profil, dan rollback firmware tidak memulihkan profil NVS lama.
- 2026-10-19 15:52:02 +07:00: Heartbeat SLA breach: jeda 148 detik dari 15:49:34 selama beberapa pemeriksaan preflight read-only dan review. Tidak ada status perangkat yang direkayasa.
- 2026-10-19 15:52:41 +07:00: GET_INFO mengonfirmasi ID 1001 dan board GLD1 WROOM-1U-N16R8 di COM7. Snapshot GET_QC_STATUS profil 2 disimpan tanpa kunci; bukan backup NVS yang dapat dipulihkan. NVS 0x9000–0xDFFF terpisah dari app0 pada 0x10000; kedua SHA firmware diperiksa. Firmware eksperimen dilaporkan sebagai eksperimen, bukan package resmi Operator Hub.
- 2026-10-19 15:53:15 +07:00: Flash aplikasi eksperimen ke COM7 selesai dengan `Hash of data verified`; alamat yang dihapus 0x10000–0x10EFFF, tidak mencakup NVS. Bridge kembali terhubung; GET_STATUS melihat ID 1001, mode inference, ADS ready dan profil 2 masih diterapkan. Binding lama 1 dan inference belum siap. Belum memulai nulling atau membuktikan akurasi.
- 2026-10-19 15:53:50 +07:00: Firmware mengakui konfirmasi udara bersih (`status=ok`, tidak ada alarm latch) dan `SET_MODE nulling`; `NULLING_RUN=start` diamati 15:53:46.262 waktu polling PC. Perekaman berjalan, MQ8 baseline dimulai. Settle dan gap 5 ms, total 8 kanal; belum ada hasil.
- 2026-10-19 15:54:29 +07:00: MQ8 `NULLING_CH_OK`, DAC 502, after 0.002055353 V; observasi final berlabel `stable=0`. Kanal berikutnya MQ135 aktif. Status OK firmware bukan bukti akurasi independen.
- 2026-10-19 15:55:07 +07:00: MQ135 `NULLING_CH_OK`, DAC 623, after 0.008386155 V; MQ3 berjalan. MQ8 ~32.962 s dibandingkan sebelumnya 55.766 s, MQ135 ~38.525 s dibandingkan 38.417 s; waktu PC, satu sampel dan kondisi tidak terkontrol, bukan estimasi peningkatan keseluruhan.
- 2026-10-19 15:55:39 +07:00: MQ3 masih confirm; capture berlangsung tanpa hasil final seluruh kanal. Alat pembanding durasi/tahap disiapkan, workbook menunggu hasil eksperimen.
- 2026-10-19 15:56:04 +07:00: MQ3 `NULLING_CH_OK` dalam ~66.295 s, DAC 721; dua kandidat confirm gagal verifikasi sebelum kandidat lain lulus. MQ5 dimulai. Jika akurasi independen belum terbukti, rencana kembalikan firmware acuan setelah run; profil baru tidak otomatis dipulihkan atau dibind.
- 2026-10-19 15:56:33 +07:00: MQ5 masih tahap confirm; perekam tetap aktif. Uji host ruang lingkup dan penjagaan 7/7 lulus ulang; uji source tidak menggantikan pembuktian analog.
- 2026-10-19 15:57:01 +07:00: MQ5 OK dalam ~36.010 s; MQ4 berlangsung. Hasil sementara 4 kanal OK menurut firmware, durasi total dan akurasi belum ada.
- 2026-10-19 15:57:32 +07:00: MQ4 tahap confirm; banyak observasi `stable=0` tetap diterima sebagai `valid` berdasarkan logika firmware yang sudah ada. Tidak cukup untuk menyatakan kalibrasi akurat.
- 2026-10-19 15:57:56 +07:00: MQ4 `NULLING_CH_OK` dalam ~65.366 s, DAC 787. MQ7 dimulai; total sementara 5/8 kanal selesai menurut firmware.
- 2026-10-19 15:58:24 +07:00: MQ7 tahap confirm; belum ada hasil total. Perhitungan durasi per tahap mencatat `observeMs` sebagai waktu observasi saja, bukan keseluruhan wall-clock.
- 2026-10-19 15:58:50 +07:00: MQ7 OK ~58.671 s; MQ6 berjalan. Sementara semua 6 pengamatan final eksperimen `stable=0`; pada baseline semua 8 final dan semua 14 verify juga `stable=0`. Field ini tidak jadi gate penerimaan dalam kedua firmware, sehingga kemampuan memenuhi kualitas belum terbukti.
- 2026-10-19 15:59:20 +07:00: MQ6 confirm sedang berjalan; penilaian akhir menunggu semua kanal dan penyimpanan profil.
- 2026-10-19 15:59:45 +07:00: MQ6 `NULLING_CH_OK` ~42.539 s, DAC 823. MQ2 kanal terakhir telah dimulai; sementara 7 kanal OK firmware.
- 2026-10-19 16:00:18 +07:00: MQ2 mencapai confirm; log exponential memuat DAC 63 dan 127 sebagaimana desain eksperimen. Menunggu hasil akhir.
- 2026-10-19 16:00:43 +07:00: `SERVICE_DONE Ok 8/8`, `NVS_SAVE=OK profileId=3`, `RUNTIME_RESULT=PASS`. Durasi log PC 409.524 s versus baseline 476.964 s, selisih 67.440 s (~14.1%) pada masing-masing satu run; 343 observasi confirm eksperimen vs 398 baseline menunjukkan variasi lintasan sehingga selisih bukan bukti kausal. Semua 8 observasi final `stable=0`, seperti baseline. Tidak membuktikan kualitas/akurasi.
- 2026-10-19 16:01:15 +07:00: Firmware acuan SHA `9a4ed309...` ditulis kembali ke app0, flash hash diverifikasi, NVS tidak dihapus. GET_INFO/STATUS/QC setelah reboot: ID 1001, mode inference, profil 3 tersimpan dan diterapkan, binding tetap 1, profileReady=false dan inferenceValid=false; AES masih terprovision. Perangkat belum siap sebagai detektor; tidak melakukan binding otomatis.
- 2026-10-19 16:02:05 +07:00: Workbook perbandingan dibuat dari dua rekaman; pemeriksaan rumus tidak menemukan error. Sedang diperiksa tata letak dan menyusun kesimpulan; tanpa pembanding independen optimasi tidak dinyatakan aman.
- 2026-10-19 16:02:05 +07:00: Heartbeat SLA breach: jeda 50 detik dari 16:01:15 saat pembuatan workbook dan pemeriksaan visual; tidak ada hasil tambahan yang direkayasa.
- 2026-10-19 16:02:46 +07:00: Workbook perbandingan tiga sheet sudah dirender dan angka dicek terhadap rekaman; sumber dan keterbatasan dicantumkan. Dokumentasi eksperimen diperbarui untuk mencerminkan uji fisik dan pengembalian firmware acuan.
- 2026-10-19 16:03:35 +07:00: Timestamp observasi eksperimen di workbook diperbaiki menjadi nilai tanggal-waktu Excel dan tampilan diverifikasi. Pemeriksaan error rumus kosong.
- 2026-10-19 16:03:35 +07:00: Heartbeat SLA breach: jeda 49 detik dari 16:02:46 saat koreksi dan render workbook; tidak ada status perangkat yang direkayasa.
- 2026-10-19 16:03:52 +07:00: Read-back akhir COM7: GLD 1001 dalam mode inference, ADS ready, activeProfile=3, boundProfile=1, profileReady=false dan inferenceValid=false. Tidak ada worker aktif; pengujian akurasi menunggu bukti eksternal dan tidak dinyatakan selesai.
