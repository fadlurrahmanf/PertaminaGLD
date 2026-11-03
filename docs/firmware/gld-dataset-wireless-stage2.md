# GLD Dataset Wireless — buffer dan replay lima menit

Alur Wizard terbaru, firmware Model1/2/3 dan manual bergambar tersedia pada
[release Dataset Wizard](gld-dataset-workflow-release-20261102.md). Jalur pada
dokumen tahap2 ini tetap tersedia di **Expert > Dataset lama**; wizard baru
memakai paket **Hotspot Wizard Dataset** yang terpisah. Uji fisik protokol3
belum dilakukan.

Pembaruan kompatibilitas 2026-11-02: **Rekam langsung dan Pulih otomatis sekarang dapat memakai firmware hotspot tahap 2 yang sama melalui Operator Hub**. Perbaikan aplikasi sudah lulus simulasi protokol, browser, grafik delapan sensor dan CSV di PC; pengujian revisi adapter ini pada GLD asli masih ditunda karena perangkat tidak tersedia. Tidak perlu compile/upload firmware untuk perubahan aplikasi ini. [Panduan dua mode dan bukti PC](gld-dataset-wireless-dual-mode-pc-20261102.md).

Status 2026-11-02: **tiga model berhasil dibuild oleh tiga agent secara paralel; Model 1 sudah diupload dan diuji pada GLD asli**. Reset NVS OFF dan profil nulling 1 dipertahankan. Grafik delapan sensor, CSV, reconnect/replay, dan batas lima menit lulus. Model 2/3 baru diverifikasi melalui build dan paket, belum diuji pada board fisik.

[Laporan build dan uji perangkat](gld-dataset-wireless-stage2-real-device-20261102.md) mencatat seluruh bukti dan batas pengujian. [Manual operator bergambar, 10 halaman](../../output/pdf/Manual-GLD-Dataset-Wireless.pdf) menjelaskan Connect, Start, grafik, recovery, Stop dan Download CSV dengan kotak bernomor. Hotspot GLD tanpa Internet; aplikasi lokal tetap dapat merekam.

Pembaruan paket password operator: Model 1 serta [Model 2/3 yang dibuild oleh dua agent paralel](../GLD-WIRELESS-MODEL23-PASSWORD-TRACKER.md) sudah tersedia pada masing-masing Hub `latest`, memakai credential pilihan operator yang sama. Implementasi sampling/replay tetap sama; paket lama disimpan terpisah. Uji fisik di laporan sebelumnya menggunakan binary/password lama. [Laporan revisi Model 1](gld-dataset-wireless-model1-password-package-20261102.md) memisahkan build/package dari upload perangkat.

Riwayat diagnosis setelah upload mandiri 17:58 WIB: POST upload tercatat HTTP200, tetapi saat diagnosis perangkat menjalankan inference/LoRa normal sehingga hotspot khusus tidak tersedia. Exact payload upload tersebut tidak disimpan. Setelah pemilihan paket diperbaiki dan pengguna mengupload ulang, sesi Pulih otomatis berhasil menghasilkan CSV lengkap 62 sampel; file tersebut dipertahankan sebagai baseline perbaikan dua mode. Ini bukti historis, bukan pengujian perangkat pada revisi adapter terbaru.

## Perilaku

GLD tetap membaca delapan sensor setiap target 500 ms ketika laptop kehilangan koneksi. Sebanyak 640 record ring di RAM menyediakan ruang untuk 600 record selama lima menit dengan margin. Setiap record memakai 64 byte; storage sampel 40.960 byte. Ketiga build melaporkan RAM statis 162.912/327.680 byte (49,7%). Pengujian Model 1 menunjukkan median interval 500 ms dan overrun 0 pada kedua sesi.

GLD mempertahankan record sampai laptop mengonfirmasi prefix CSV yang sudah ditulis, di-flush, dan di-fsync. Socket send bukan konfirmasi penyimpanan. Ketika laptop kembali ke hotspot, backend menyambung otomatis dan mengirim Resume untuk boot/session/label serta nomor urut yang sama. Record tertua dikirim dahulu; timestamp asli tetap dipakai, baris duplikat tidak ditulis ulang, dan pembacaan baru tetap masuk di belakang backlog.

Jika putus mencapai 300 detik, buffer penuh, atau sensor/power invalid, sampling berhenti dan sesi ditandai tidak lengkap. Record yang masih di RAM tidak ditimpa atau dihapus otomatis; record tersebut tetap dapat ditarik setelah tersambung selama GLD masih menyala. Stop tidak menghapus alasan kegagalan terminal.

Buffer hilang saat GLD mati/reboot. Browser boleh ditutup, tetapi proses backend harus tetap hidup. Pemulihan sesudah backend PC crash/restart dan mode router berada di luar fase ini. Backend tidak memindahkan Wi-Fi Windows; laptop perlu kembali terhubung ke hotspot GLD.

## Pemisahan dari fitur yang sudah terbukti

| Jalur | Perlakuan |
|---|---|
| Dataset Wireless tahap 1 | Protokol, modul firmware, collector, credential preparer dan tiga env lama dipertahankan |
| Dataset serial/MQTT, Running/LoRa, nulling/inference | Env, pin, konfigurasi model dan format NVS sebelumnya dipertahankan |
| Firmware tahap 2 | Tiga env baru, modul dan private credentials terpisah; tidak memanggil production package hook |
| Backend | Collector dan namespace API/event replay terpisah; default UI Rekam langsung mengenali protokol tahap 1/2 melalui adapter tambahan |
| Upload | Target replay eksplisit; Reset NVS/initial erase ditolak; hasil flash masih memerlukan verifikasi hotspot |
| Akses perangkat | Saat mode wireless aktif/recovering atau penutupan sesi langsung masih tertunda, mode lain, COM, probe port dan upload diblokir sebelum akses perangkat |

Environments baru: `gld_model_1_dataset_replay_wifi`, `gld_model_2_dataset_replay_wifi`, `gld_model_3_dataset_replay_wifi`. Semuanya mewarisi target tahap 1 yang sesuai, memakai `PGL_GLD_DATASET_REPLAY=1`, dan tidak mengubah paket/binary lama. Ketiga paket replay telah divalidasi dan ditempatkan hanya pada direktori env baru dalam katalog Hub.

Kredensial privat baru hanya dibuat saat build yang disetujui, di `firmware/.pio/gld-dataset-replay-wifi/<environment>/credentials.local.json`. Tidak dimasukkan ke manifest, source, screenshot atau log. Credential tahap 1 tidak dibaca/dirotasi oleh preparer tahap 2.

## Alur operator

1. GLD memakai catu 24 V, profil nulling valid, dan firmware replay yang sesuai model. Reset NVS tetap OFF.
2. Laptop masuk `GLD-DATASET-<id>` dan menunggu IP hotspot tersedia.
3. Di Dataset Wireless pilih **Pulih otomatis**, lalu Connect GLD dan Start Wireless. Nama sebelumnya pada screenshot manual adalah **Buffer 5 menit · tahap 2**. **Rekam langsung** juga dapat memakai firmware yang sama setelah perbaikan aplikasi; lihat panduan dua mode di atas untuk perbedaan perilaku ketika putus.
4. Saat putus, status menjadi recovering; sesi, file CSV dan urutan tetap dipertahankan. Mode/Start dikunci. Stop dapat diminta dan akan menunggu koneksi serta konfirmasi GLD.
5. Setelah tersambung, status replaying menunjukkan pengiriman backlog; setelah mengejar record terbaru, status kembali recording. Stop menunggu ACK dan summary serta mencocokkan semua record sebelum menyatakan lengkap.

Disconnect adalah pembatalan lokal yang menghentikan reconnect. Jika GLD sedang offline, backend tidak dapat menjamin perintah stop sampai ke GLD; UI/hasil tidak boleh dianggap sebagai penghentian sampling remote yang sudah terkonfirmasi.

## Bukti source dan host

- 16 gate firmware source/credential dan 7 gate tahap 1 lulus: seluruh env sebelumnya, modul/preparer tahap 1, perilaku Unified tanpa flag replay, serta 184 berkas paket sebelumnya terlindungi.
- 22 fault test collector deterministik lulus: ACK hilang, pengiriman ulang duplikat, kegagalan ACK sesudah fsync, putus di tengah replay, Start ambigu tanpa resend, Stop dengan command ID yang sama, cancel/backoff, disk failure sebelum ACK, identitas berubah, malformed/gap, serta batas 300/301 detik dan kapasitas 640.
- Model clock test mengikuti progress ACK firmware. Skenario unit >600 menahan 603 record setelah 299,5 detik sejak progress ACK terakhir dan menghasilkan 604 baris setelah drain. Ini bukan eksekusi state machine C++.
- 12 test API dan VM UI lulus untuk otorisasi, mode terpisah, mutual exclusion/race, pemulihan sesi aktif setelah reload, Stop tertunda, dan snapshot lama yang tidak boleh mengganti mode baru. Pemilihan/pengamanan upload tahap 1 dan replay diuji untuk ketiga model melalui 18 test Python dan test Node.
- Regresi collector tahap 1 (18), API tahap 1 (6), serta model/history/race UI lulus. Review lintas komponen menemukan race control-versus-sample FIFO; pemilihannya sekarang berada dalam satu mutex, dengan I/O jaringan tetap di luar mutex. Gate source serta peer review fix lulus.

## Simulasi browser dan WebSocket aktual di PC

Fixture hanya memakai port loopback dinamis 52757/52758, peer GLD sintetis, UI/bridge/collector asli, serta WebSocket client vendored asli. Factory khusus fixture mengarahkan endpoint perangkat ke loopback; semua jalur tulis COM/firmware/MQTT diblokir. Akuisisi peer menggunakan clock virtual; koneksi, CSV flush/fsync, UI dan download menggunakan proses PC nyata.

| Skenario | Hasil |
|---|---|
| Putus dengan backlog lima menit | 608 record tertahan setelah gap virtual 299,5 detik; sampling sintetis masih berjalan |
| Reconnect/Resume | CSV/session yang sama; 608 record replay; akhir 814 baris lengkap, gap/duplikat 0 |
| Browser ditutup/dibuka | UI 734 record sebelum ditutup; backend checkpoint 766 tetap recording; UI kembali pada mode replay aktif dengan 813, lalu Stop 814 lengkap |
| Tekanan kapasitas | 640 record ring dipertahankan; 20 record sebelumnya sudah tersimpan; akhir CSV 660 baris incomplete/buffer_full tanpa overwrite |
| Download | Kedua unduhan browser cocok dengan CSV backend setelah parsing |
| Verifikasi independen | Seluruh 1.474 baris cocok pada seluruh scalar, delapan tegangan/gain/status dan urutan fitur; audit fsync mendahului ACK; lima kontrol negatif verifier lulus |

Tekanan kapasitas adalah injeksi fault buatan, bukan bukti timing sensor. Dua test WebSocket normal/EOF dan dua skenario wire backlog/overflow juga lulus. Cutoff awal test backlog 15 detik terlalu pendek untuk fsync per record; diagnostik menunjukkan progress sehat, sehingga hanya batas fixture test diperpanjang menjadi 30 detik. Timeout unduh dari wrapper iframe browser dipulihkan memakai konsol langsung; tidak membutuhkan perubahan produk atau pengulangan operasi perangkat.

Artefak lokal: `tmp/wireless-stage2/e2e/validated-evidence.json`, `verification-report.json`, `validation-report.json`, `browser-downloads.json`, screenshot recovering/replaying/complete/overflow, serta kedua CSV di subfolder `output/`. Fixture sudah dihentikan dan kedua port ditutup. Pernyataan perlindungan proses pada bukti fase PC bersifat historis; layanan produksi kemudian direstart dengan persetujuan pengguna untuk mengaktifkan tahap 2.

## Hasil uji GLD asli dan batas yang tersisa

Build pertama ketiga model berhasil dengan overlap nyata 15:53:57-16:01:52 WIB. Model 1 diupload sekali melalui Expert API ke COM7 tanpa reset NVS. Dengan hotspot GLD yang tidak menyediakan Internet, skrip lokal dan watchdog pemulihan Wi-Fi menjalankan pengujian tanpa bergantung pada koneksi Codex.

| Skenario GLD asli | Hasil |
|---|---|
| Putus 260 detik sebelum perintah rejoin | 528 sampel dipulihkan; 559 baris complete, gap/duplikat 0 |
| Putus 305 detik sebelum perintah rejoin | 600 sampel dipulihkan; 613 baris incomplete / retention_limit, sampling berhenti sesuai batas |
| Grafik dan CSV | Delapan sensor tampil; seluruh 1.172 baris dan kedua unduhan browser divalidasi independen |
| Identitas dan interval | Device 1002, profil 1 dan boot tetap sama; median 500 ms, overrun 0 |

Satu timeout TCP awal terjadi sebelum Start dan sebab pastinya belum diisolasi. Setelah controlled reset, kedua sesi aktual pada boot yang sama berhasil tanpa reflash. Model 2/3 fisik, soak test, jarak RF, mode router dan pemulihan setelah power cycle/backend restart belum termasuk hasil ini. Fitur lama dilindungi oleh pemisahan target, source/package fingerprint dan regresi host; seluruh mode lama tidak diuji ulang secara fisik.

[Kontrak protokol](gld-dataset-wireless-replay-contract.md) · [Tracker](../GLD-WIRELESS-REPLAY-GOAL-TRACKER.md)
