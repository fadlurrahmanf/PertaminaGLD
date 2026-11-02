# Stage 2 — build paralel dan uji replay GLD asli

Tanggal: 2 November 2026. Hasil: **tiga build PASS; dua uji fisik Model 1 PASS**. Manual bergambar menjadi deliverable terpisah.

## Build yang benar-benar bersamaan

| Model / environment | Mulai WIB | Selesai WIB | Binary / SHA256 |
|---|---|---|---|
| 1 / gld_model_1_dataset_replay_wifi | 15:52:49.917 | 16:01:52.252 | 1.047.024 byte / `491e060eefb30b5db51b2801332fc4e3803fef9fdcf185be6de0a9e2ab698166` |
| 2 / gld_model_2_dataset_replay_wifi | 15:53:29.789 | 16:02:11.907 | 1.046.176 byte / `84106875d725aa60a978f8fedcd19499b42a82ad24d48be491d07f07e4daf954` |
| 3 / gld_model_3_dataset_replay_wifi | 15:53:57.533 | 16:02:13.042 | 1.047.024 byte / `f3f5cc924ce1ce4e439e53908e4ec9651dfdc1219ce2ad9fd35029c577619f12` |

Tiga agent memakai direktori build/libdeps/log terpisah. Ketiganya overlap dari 15:53:57 sampai 16:01:52 WIB, tanpa menunggu giliran. Semua berhasil pada attempt pertama, compiler warning 0, RAM 162.912/327.680 byte (49,7%), flash sekitar 16%. Source masing-masing tidak berubah selama build.

Keempat file flash per model, manifest, provenance model dan bukti build berada di `firmware/.pio/artifacts/gld-dataset-replay-wifi-20261102/`. Validator GLD/Hub, checksum/digest ESP, model embedded yang sesuai, partisi identik dan tidak adanya overlap erase sector NVS lulus. Hanya tiga direktori paket replay baru ditempatkan di Hub; 184 berkas paket lama dipertahankan.

## Deployment yang disetujui pengguna

Pengguna mengizinkan compile tiga agent paralel lalu upload/uji GLD asli. Root menjadi satu-satunya pemegang COM7 dan kontrol jaringan.

- GLD1 Model 1, COM7, device `1002`, catu eksternal 24 V, firmware `0.8.36`, protocol wireless `gld-dataset-wifi/2`.
- Backup NVS privat 20.480 byte dibuat sebelum upload. Tidak ada erase/reset NVS, nulling, perubahan binding, atau kalibrasi otomatis.
- Upload Model 1 dilakukan **sekali** melalui API Expert yang memvalidasi paket offline. Target identity `1002`, Reset NVS false; respons sukses menyatakan empat file verified, NVS tidak direset. Durasi 14,188 detik, selesai 16:10:44 WIB.
- Jalur Expert dipakai karena firmware hotspot tahap 1 yang sudah terpasang tidak menyediakan command loop serial untuk identifikasi Simple Hub. Pengambilan data berikutnya seluruhnya melalui hotspot/WebSocket, bukan COM.
- Hub/GLD bridge diaktifkan dari source baru; proses aktif setelah restart masing-masing PID 21752/36360.

## Temuan startup yang tetap dicatat

Percobaan awal berasosiasi dan memiliki IPv4/rute yang benar tetapi TCP port 81 timeout selama 20 detik, sebelum Connect collector atau Start. Wi-Fi asal berhasil dipulihkan. Root mengambil log dengan satu reset EN terkontrol saat belum ada sesi/RAM data. Log menunjukkan `DATASET_WIFI_SERVER ready=1`, tanpa panic/brownout yang ditemukan pada capture tersebut.

Sesudah itu diagnostik target ARP, ICMP dan TCP lulus, disusul hello protocol 2: ID 1002, profil nulling 1, ready true. Tidak ada reflash atau perubahan source untuk pemulihan ini. Penyebab pasti timeout awal belum terisolasi; tidak dinyatakan sebagai bug firmware yang sudah diperbaiki. Kedua sesi berikut beserta kunjungan hotspot awal/rejoin berhasil pada boot yang sama.

## Metode aman ketika hotspot tidak memiliki Internet

Skrip acceptance berjalan lokal dan tersembunyi. Setiap kunjungan hotspot dilindungi watchdog pemulihan Wi-Fi 90 detik. Saat periode offline panjang, laptop kembali ke Wi-Fi asal yang berinternet sementara GLD terus menyimpan data di RAM. Backend tetap hidup dan mencoba reconnect secara terbatas intervalnya. Start hanya dikirim sekali per sesi; Resume dilakukan oleh collector, tanpa Start baru. Pada akhir uji, jaringan laptop dipulihkan dan diverifikasi.

Durasi offline di bawah adalah jarak monotonic antara perintah pindah ke Wi-Fi asal dan perintah rejoin hotspot. Bukti juga mencatat asosiasi/IPv4/rute/TCP, status recovering, identitas boot, dan timestamp akuisisi GLD; durasi radio yang tepat sampai level frame tidak diklaim.

## Hasil fisik dan CSV

| Pemeriksaan | Pulih sebelum batas | Melewati batas |
|---|---|---|
| Periode sebelum perintah rejoin | 260,000 detik | 305,000 detik |
| Sampel PC sebelum putus | 13 | 13 |
| Sampel dipulihkan | 528 | 600 |
| Total CSV | 559, seq 0–558 | 613, seq 0–612 |
| Hasil akhir | complete / sesi lengkap | incomplete / retention_limit |
| Gap / duplikasi | 0 / 0 | 0 / 0 |
| Interval aktual GLD | 488–510 ms; mean 499,9982 ms | 496–504 ms; mean 500,0033 ms |
| Median interval | 500 ms | 500 ms |
| Durasi scan delapan kanal | 218–235 ms | 222–237 ms |
| Overrun | 0 | 0 |
| Identitas | ID 1002 / profil 1 / boot sama | ID 1002 / profil 1 / boot sama |
| Kontinuitas file | Session dan CSV sama sebelum/sesudah putus | Session dan CSV sama sebelum/sesudah putus |
| Penyelesaian | Stop ACK + summary + exact count | Summary retention_limit; sampling berhenti, buffer berhasil dikuras |

Seluruh baris, delapan tegangan/gain/status, canonical feature order, sequence, dan setiap tuple historis yang sempat diamati diperiksa independen. Nilai finite, status kanal 0, gain valid, profil tidak berubah, dan cumulative ACK prefix sesuai record tersimpan. Semua record yang diterima dan dinyatakan pada summary tersedia; hasil incomplete tidak disamakan dengan pengukuran berkelanjutan sesudah batas retention.

Kedua unduhan browser cocok seluruh field/header/baris dengan file backend. Perbedaan raw hash hanya newline. CSV positif tidak berubah setelah uji expiry. Fsync-before-ACK terbukti oleh source dan fault/wire host tests; uji hardware mengkoroborasi implementasi default, prefix dan hasil persisten, bukan packet trace yang memisahkan setiap syscall fsync terhadap frame ACK di udara.

## Bukti lokal

- Positive: `firmware/.pio/gld-real-test-20261102/stage2/output/20261102T093208Z-1334ef/real-evidence.json`.
- Expiry: `firmware/.pio/gld-real-test-20261102/stage2/output/20261102T094031Z-2c0726/real-evidence.json`.
- Validasi: `firmware/.pio/gld-real-test-20261102/stage2/validation/actual-positive-report.json` dan `actual-expiry-report.json`, termasuk bukti dua browser download.
- CSV lengkap: `apps/gld-operator/output/datasets/wireless_replay_1002_2c4e350dc7354574b85c0a72238b5bb4.csv`.
- CSV batas: `apps/gld-operator/output/datasets/wireless_replay_1002_3eba1bc5cb0c43a7b14025cd1cda31e4.csv`.
- Upload: `firmware/.pio/gld-real-test-20261102/stage2/upload-receipt.json`. Ini respons verified upload API; tidak ada klaim raw log esptool lengkap disimpan bila tidak tersedia.

## Batas dan handoff

Model 2/3 baru memiliki bukti compile/package, belum dipasang pada board fisik. Mode normal lama dilindungi oleh source/artefak/regresi host; tidak dilakukan pengujian ulang fisik seluruh mode serial/MQTT/LoRa/nulling pada fase ini. Tidak ada klaim soak test, RF range atau RAM bertahan melewati power cycle.

Model 1 replay tetap terpasang. Rekaman uji sudah berhenti dan laptop berada pada Wi-Fi asal. Untuk sesi baru, operator masuk hotspot lalu Connect dan Start di mode Buffer 5 menit. Backend lokal harus tetap hidup. Jangan mematikan/reboot GLD selama data masih tertahan.

Manual menggunakan screenshot langsung dari UI asli untuk navigasi, recovery dan hasil akhir. Status singkat saat hotspot memutus Internet dapat ditampilkan melalui viewer read-only dari snapshot uji asli yang utuh; gambar tersebut diberi banner dan caption tampilan ulang, bukan diklaim sebagai screenshot koneksi langsung.

Manual final: [Panduan operator bergambar, 10 halaman](../../output/pdf/Manual-GLD-Dataset-Wireless.pdf). Delapan screenshot diberi kotak bernomor; tiga tampilan ulang log asli ditandai eksplisit. Seluruh halaman telah dirender dan diperiksa visual, termasuk legenda delapan sensor, langkah Stop/Download dan perbedaan complete/retention_limit. SHA256 `155131567631caa228449bc139832dccf3873aa7b6ea8dc18f9980cf9d065545`; bukti QA `tmp/pdfs/gld-wireless-manual/final-qa.json`.

Handoff 17:10 WIB: Hub PID 21752 / GLD bridge PID 36360 tetap berjalan; state terakhir incomplete/retention_limit berasal dari uji batas yang disengaja, sampling dan recovery tidak aktif. Laptop kembali ke Wi-Fi asal. Viewer arsip PID 36860 dan port 57308 sudah ditutup.
