# GLD1 Dataset Wireless — tahap 1

Status: **Model 1 sudah diupload dan diuji dengan GLD asli pada 2026-11-02**, setelah izin pengguna. Ketiga varian Model 1/2/3 berhasil compile paralel. Model 1 menghasilkan 29 sampel delapan sensor pada 496–503 ms (median/rata-rata 500 ms), tanpa overrun. Uji putus Wi-Fi fisik juga PASS: 9 record tetap tersimpan, status incomplete terdeteksi sekitar 1,7 detik, hitungan stabil, dan CSV sebelumnya utuh. Model 2/3 belum diuji fisik. Lihat [laporan perangkat asli](gld-dataset-wireless-real-device-20261102.md).

## Ruang lingkup dan varian

Satu GLD1 pada catu eksternal/24 V membuat hotspot. Laptop terhubung; backend GLD Operator di Operator Hub membuka WebSocket, merekam CSV, dan meneruskan sampel ke panel Wireless di tab Dataset.

| Model | Environment baru | Parent yang dilindungi |
|---|---|---|
| 1 | `gld_model_1_dataset_wifi` | `gld_model_1` |
| 2 | `gld_model_2_dataset_wifi` | `gld_model_2` |
| 3 | `gld_model_3_dataset_wifi` | `gld_model_3` |

Varian khusus ini boot ke Dataset di RAM, tanpa mengonsumsi boot intent NVS. Serial/MQTT/Running/LoRa/nulling/inference tetap pada environment sebelumnya. Build baru tidak memperbarui paket produksi.

## Alur operator setelah build dan upload disetujui

1. Gunakan GLD1 dengan profil nulling lengkap yang valid dan catu eksternal/24 V. Varian hotspot tidak menjalankan kalibrasi otomatis.
2. Upload varian sesuai model hanya setelah izin upload terpisah; pertahankan NVS. Izin compile bukan izin upload.
3. Hubungkan laptop ke `GLD-DATASET-<deviceId>` dan tunggu IP `192.168.4.x/24` tersedia. Pada bench ini DHCP membutuhkan sekitar 12 detik setelah asosiasi. Password privat dibuat saat build pertama yang disetujui, di `firmware/.pio/gld-dataset-wifi/<environment>/credentials.local.json`. Jangan commit atau membagikan credential. Password tidak dicetak ke log.
4. Jalankan backend Operator Hub dengan source baru. Buka GLD → Dataset → **Dataset Wireless · Hotspot GLD1**. Putuskan COM jika aktif.
5. Masukkan password hotspot lalu **Connect GLD**. Endpoint tetap `ws://192.168.4.1:81/dataset`; Basic username `gld` memakai password hotspot yang sama.
6. Pilih label ASCII yang aman untuk CSV (1–31 karakter), lalu **Start Wireless**. Backend menunggu ACK dan status running sebelum menerima sampel.
7. **Stop** menunggu ACK dan summary serta mencocokkan jumlah sampel. **Download CSV** membaca file backend, bukan hanya titik grafik.

CSV berada di `apps/gld-operator/output/datasets/wireless_<deviceId>_<sessionId>.csv`. Browser dapat ditutup; backend harus tetap berjalan. Snapshot memulihkan tampilan setelah refresh. History dibatasi 7.200 sampel; file dan hitungan sesi terus bertambah.

## Akuisisi dan batas tahap 1

- Record memuat delapan tegangan/gain/status, urutan fitur, profile ID, session ID, sequence, serta waktu awal/akhir scan GLD.
- Urutan tetap MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2. Kanal dibaca berurutan, bukan serempak.
- Sampler terpisah dari socket, menargetkan deadline 500 ms dan melaporkan overrun. Model 1 bench menghasilkan 29 record pada 496–503 ms, scan 224–236 ms, overrun 0. Ini bukti bench singkat, belum uji durasi panjang atau Model 2/3. Tidak ada siklus fan satu detik per record pada jalur baru.
- Queue 32 pesan. Putus koneksi, sensor invalid, atau queue penuh menghentikan sesi dan melaporkan hasil tidak lengkap. Sesi lengkap yang sudah direkonsiliasi tetap lengkap jika koneksi kemudian putus.
- Tidak ada retry perintah diam-diam, reconnect otomatis, atau replay lima menit. Buffer ≥600 record plus cadangan dan mode router tetap tahap 2.
- Tidak mengubah service hold/battery sleep; sesi ini memerlukan catu eksternal/24 V.

## Kontrak aplikasi

Protokol `gld-dataset-wifi/1` diawali hello: identitas, urutan fitur, interval 500 ms, kesiapan sensor/profile/power. Start/Stop membawa `command_id` dan `session_id`. Sample mulai `seq=0`; summary `total_samples=N` mengakhiri sesi. Backend memvalidasi kualitas kanal, sesi, duplikat, dan gap sebelum menulis.

API memakai token/origin bridge yang sama, tanpa membuka bridge PC ke LAN: GET `/api/wireless-dataset/state`; POST `/api/wireless-dataset/connect`, `/start`, `/stop`, `/disconnect`, `/export`. Endpoint perangkat tetap; proxy dan redirect dinonaktifkan. Snapshot/event/localStorage tidak menyimpan password. Dependency Python opsional tersedia offline di `apps/gld-operator/vendor/wireless/` beserta lisensi. Kegagalan wireless tidak menghentikan bootstrap lama.

## Bukti dan gate berikutnya

Host tests mencakup collector/API/UI, CSV tanpa browser, ACK, malformed/stale/duplicate records, disconnect, disk failure, snapshot race, dan fake peer WebSocket loopback dengan Basic auth. Source guard membandingkan seluruh env lama dan Unified tanpa flag baru terhadap HEAD. Ketiga binary Model 1/2/3 tidak diubah.

Tiga kegagalan regresi lama telah direproduksi dengan input HEAD: dua assertion nulling masih mengharapkan flag hanya pada Model 1 (baseline sudah tiga model), serta satu test mock alarm tidak menyediakan helper `mockLoraMode`. Tidak diperbaiki dalam scope ini.

User sudah menyetujui compile dengan tiga agent paralel. Ketiga environment berhasil; artifact terpisah berada di firmware/.pio/artifacts/gld-dataset-wifi-20261102/ (bootloader, partitions, boot_app0, firmware, serta build-evidence.json permodel dan build-summary.json). Semua hasil copy cocok SHA256 terhadap output build. RAM37.2%,Flash15.9%; binary Model1/3 masing-masing1043392byte, Model2 1042512byte. Paket produksi lama tetap utuh.

Dua perbaikan compile hanya menyentuh varian baru: include framework WiFiClientSecure secara eksplisit pada modul hotspot dan lib_ldf_mode=deep pada tiga env hotspot. Parent env tidak berubah.

Dengan izin pengguna, Hub/GLD bridge direstart dan Model 1 Hotspot diupload sekali ke COM7, Reset NVS OFF. Flash hash terverifikasi/exit 0. GLD asli device 1002 tetap menggunakan nulling profile 1; hotspot/login, Start/Stop tanpa COM, grafik delapan sensor, CSV browser cocok backend, dan uji putus Wi-Fi fisik sudah PASS. Backup NVS privat dibuat sebelum upload. Laptop dikembalikan ke Wi-Fi asal dan rekaman sudah berhenti.

Simulasi PC end-to-end pada 2026-11-02 sudah PASS: grafik delapan sensor,
rekaman berlanjut saat browser ditutup,153 sampel sesi normal dan53 sampel sesi
putus koneksi, serta kedua unduhan CSV cocok dengan backend. Lihat
[laporan browser/CSV/disconnect](D:/Github/PertaminaGLD/docs/firmware/gld-dataset-wireless-pc-simulation-20261102.md).
Laporan tersebut memakai peer sintetis. Bukti GLD asli terpisah berada di `firmware/.pio/gld-real-test-20261102/validation/actual-capture-report.json`; file privat/kredensial tetap diabaikan Git.
