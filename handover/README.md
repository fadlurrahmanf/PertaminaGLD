# Handover seluruh sistem GLD ke PC Windows x64

Paket ini membawa Operator Hub dan bridge GLD/CH/Gateway, tiga firmware final,
runtime Python/Node.js/Node-RED/MariaDB, modul MQTT/database, driver CH340,
konfigurasi aktif, serta histori yang ditemukan pada PC sumber.

## Cara pakai di PC pengganti

1. Pull `master` terbaru dari GitHub di PC pengganti. Gunakan path pendek,
   misalnya `C:\GLD\PertaminaGLD`, agar runtime Node-RED tidak melewati batas
   path Windows. Laporan verifikasi lokal tidak memeriksa GitHub; cocokkan SHA
   commit bila perlu.
2. Jalankan `verifikasi-handover.bat` dari root repository. Jendela menampilkan
   daftar pemeriksaan, tanda centang/silang, hitungan `xx/xx`, dan kesimpulan.
   Tunggu sampai selesai. Pemeriksaan menjalankan salinan stack pada port
   terpisah, tanpa membuka COM atau mengubah GLD.
3. Untuk penggunaan sebenarnya, tutup Hub/stack lama melalui terminalnya
   setelah rekaman selesai, lalu jalankan `start-handover.bat`. Terminal tetap
   terlihat dan browser Hub dibuka. Jangan menjalankan dua launcher sekaligus.
4. Jika Windows meminta izin pemasangan driver CH340 yang belum tersedia,
   izinkan paket driver bertanda tangan yang disertakan. Verifier hanya
   memeriksa paket driver; tidak memasangnya.
5. Sambungkan perangkat, pilih COM yang benar pada PC tersebut, dan periksa
   status perangkat. Untuk Dataset Wi-Fi gunakan catu 24 V dan hotspot GLD.
   Koneksi hotspot lokal tidak menyediakan Internet.
   Jika Connect gagal, sambungkan Wi-Fi ke hotspot GLD lalu jalankan
   `tools\Run-GLD-WiFi-Check.cmd 1002` dengan ID GLD yang sesuai saat Hub
   tidak merekam. Diagnostik baca saja memeriksa SSID, rute, TCP 81 dan Hello;
   hasil tersimpan di `output\diagnostics`.
6. Selesaikan rekaman dengan Stop sebelum menutup aplikasi. Tekan `Ctrl+C`
   pada terminal launcher untuk menghentikan layanan yang dibuat launcher.

Tidak perlu compile firmware atau memasang Node.js/Node-RED/MariaDB global.
Windows, Git untuk pull, browser, akses USB/jaringan, dan izin driver tetap
merupakan prasyarat PC. Pengaturan firewall/router perangkat lapangan mengikuti
jaringan yang dipakai; tidak diubah otomatis oleh verifier.
Jika PC belum memiliki alamat LAN, launcher handover menjalankan broker MQTT
di loopback agar Hub, Dataset lokal, Node-RED dan database tetap dapat dibuka.
Dalam kondisi ini CH/Gateway atau perangkat jaringan lain belum dapat mengakses
broker dari luar PC; sambungkan LAN yang sesuai untuk operasi jaringan penuh.

## Apa yang dibawa

- `runtime/windows-x64`: Node.js 26.5.0, Node-RED 5.0.1, Aedes, dan modul MySQL.
- `runtime/database-windows-x64`: MariaDB 10.4.32, tanpa data server sumber.
- `drivers/ch340-windows-x64`: paket driver CH340 Windows x64 bertanda tangan.
- `state`: snapshot konfigurasi aktif, profil/flow/credential Node-RED dan
  kunci pembukanya, serta 199 CSV dan 10 ledger JSONL (9 November 2026).
- `deployment.json`: konfigurasi database handover dan port lokal.
- `plaintext-authorization.json`: persetujuan pemilik dan hash berkas
  konfigurasi plaintext yang diizinkan ikut Git.
- Firmware/model final tetap berada di
  `apps/operator-hub/firmware-packages`; referensi koneksi ketiga model berada
  di `apps/gld-operator/workflow-connection-profiles.json`.

AES dan password aktif disertakan **plaintext sesuai instruksi pemilik**.
Siapa pun yang dapat membaca repository/bundle ini dapat membaca kredensialnya.
Jangan membagikan isinya di log atau screenshot.

## Histori dan database

Pencarian pada MySQL/XAMPP lokal, arsip GLD 15 Oktober, dan lokasi backup
umum tidak menemukan database atau dump SQL GLD. Karena itu paket ini bukan
dump database lama. Seluruh histori sensor yang teridentifikasi disalin:
**209 berkas, 256.605 baris**. Ini mencakup 140 CSV sensor unik dari arsip lama;
CSV diagram/esptool dan satu file kosong tidak dimasukkan.
Database handover merekonstruksi CSV/ledger tersebut dengan provenance dan
menyimpan byte asli setiap berkas; pengujian mendapatkan **0 perbedaan byte**.
Impor bersifat idempoten. MySQL sumber pada port 3306 tidak dipakai atau diubah.
Baris lama tersedia di tabel arsip `handover_files` dan `handover_rows`.
Tabel operasional `gld_dataset` mulai kosong dan menerima rekaman baru dari
Node-RED. Karena database GLD lama tidak ditemukan, riwayat arsip belum dapat
dianggap sebagai pemulihan seluruh tabel operasional atau data dashboard lama.

## Port dan penyimpanan lokal

Penggunaan normal: Hub 5173; bridge GLD/CH/Gateway 5174/5273/5373;
Node-RED 1880; MQTT 1884; database handover 33306.
Alamat Hub: `http://127.0.0.1:5173`.

Runtime, database kerja, profil hasil restore dan log disimpan di
`archive/apps/runtime/handover` yang diabaikan Git. Verifikasi memakai salinan
baru di `output/handover-verification/<waktu>/clean-checkout`, port bertambah
10000, dan meninggalkan laporan/diagnostik untuk diperiksa. File sumber tidak
ditimpa. Port yang telah dipakai menyebabkan launcher berhenti; launcher tidak
mengambil alih proses asing.

Folder `tmp/` dan profil browser uji di `output/mockups/` sengaja tidak ikut
Git. Keduanya artefak sementara; profil browser lama memiliki path yang
menyebabkan checkout Windows gagal. Screenshot mockup tetap ikut Git.

Snapshot Git merupakan kondisi saat ekspor, bukan sinkronisasi data langsung.
Rekaman baru setelah snapshot harus diekspor lagi untuk handover berikutnya.
Saat pull versi baru, launcher membuat profil Node-RED berversi dan menjaga
profil serta CSV kerja sebelumnya. Jika konfigurasi lama tidak dapat divalidasi,
launcher berhenti dengan diagnostik tanpa menimpa profil lama.
`tools/handover_snapshot.py export` adalah alat ekspor dari PC sumber dan
memerlukan manifest `--csv-discovery` yang eksplisit dan terkini. Alat ini
tidak diperlukan untuk menjalankan Hub di PC pengganti.

## Bukti dan batas pengujian

Clone langsung dari GitHub pada Windows berhasil, lalu uji stack dari commit clone
lulus 24/24: Hub dan ketiga bridge,
autentikasi MQTT, AES melalui decoder Node-RED, penulisan/pembacaan database,
penulisan CSV, integritas histori, dan penghentian layanan milik pengujian.
Verifier menghapus ketergantungan konfigurasi tersembunyi dari lingkungan PC
pengembang. Semua pemeriksaan wajib harus lulus agar kesimpulannya LULUS.

Informasi Git dan hardware ditampilkan terpisah dari hitungan pemeriksaan
wajib. Snapshot histori 9 November telah di-push dan diuji dari clone langsung
GitHub pada Windows: 24/24, termasuk 209 berkas histori dan 0 beda byte.
Uji source firmware dari clone lulus 22/22. Setiap snapshot baru tetap perlu
push, clone, dan uji ulang. Pengujian ini belum
membuktikan operasi pada PC kedua atau USB/radio fisik di sana. Jalankan
verifier kembali pada PC pengganti dan uji perangkat pada jaringan yang dipakai.

Proses ekspor dan verifikasi handover tidak mengubah firmware, model, NVS,
nulling/binding, atau alur COM/Dataset pada perangkat yang sedang dipakai.

Lihat `status.json`, [tracker terkini](../docs/DATASET-HANDOVER-GOAL-TRACKER.md), dan
[panduan portabilitas GLD](../docs/firmware/gld-pc-portability.md).
Lisensi runtime disertakan pada arsip masing-masing; Node LICENSE berasal dari
tag resmi v26.5.0.
