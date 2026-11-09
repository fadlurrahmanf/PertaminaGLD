# Handover seluruh sistem GLD ke PC Windows x64

Paket ini membawa Operator Hub dan bridge GLD/CH/Gateway, tiga firmware final,
runtime Python/Node.js/Node-RED/MariaDB, modul MQTT/database, driver CH340,
konfigurasi aktif, serta histori yang ditemukan pada PC sumber.

## Cara pakai di PC pengganti

1. Commit dan push seluruh perubahan handover dari PC sumber, lalu pull commit
   tersebut di PC pengganti. Laporan verifikasi lokal tidak membuktikan push.
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
6. Selesaikan rekaman dengan Stop sebelum menutup aplikasi. Tekan `Ctrl+C`
   pada terminal launcher untuk menghentikan layanan yang dibuat launcher.

Tidak perlu compile firmware atau memasang Node.js/Node-RED/MariaDB global.
Windows, Git untuk pull, browser, akses USB/jaringan, dan izin driver tetap
merupakan prasyarat PC. Pengaturan firewall/router perangkat lapangan mengikuti
jaringan yang dipakai; tidak diubah otomatis oleh verifier.

## Apa yang dibawa

- `runtime/windows-x64`: Node.js 26.5.0, Node-RED 5.0.1, Aedes, dan modul MySQL.
- `runtime/database-windows-x64`: MariaDB 10.4.32, tanpa data server sumber.
- `drivers/ch340-windows-x64`: paket driver CH340 Windows x64 bertanda tangan.
- `state`: snapshot konfigurasi aktif, profil/flow/credential Node-RED dan
  kunci pembukanya, serta 59 CSV dan 10 ledger JSONL (9 November 2026).
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

Pencarian pada PC sumber tidak menemukan database proyek aktif atau backup SQL
proyek. Karena itu paket ini tidak diklaim sebagai dump database lama.
Seluruh histori yang teridentifikasi disalin: **69 berkas, 90.235 baris**.
Database handover merekonstruksi CSV/ledger tersebut dengan provenance dan
menyimpan byte asli setiap berkas; pengujian mendapatkan **0 perbedaan byte**.
Impor bersifat idempoten. MySQL sumber pada port 3306 tidak dipakai atau diubah.

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

## Bukti dan batas pengujian

Clone langsung dari GitHub pada Windows berhasil, lalu uji stack dari commit clone
lulus 24/24: Hub dan ketiga bridge,
autentikasi MQTT, AES melalui decoder Node-RED, penulisan/pembacaan database,
penulisan CSV, integritas histori, dan penghentian layanan milik pengujian.
Verifier menghapus ketergantungan konfigurasi tersembunyi dari lingkungan PC
pengembang. Semua pemeriksaan wajib harus lulus agar kesimpulannya LULUS.

Informasi Git dan hardware ditampilkan terpisah dari hitungan pemeriksaan
wajib. Hasil ini tidak mengklaim sudah push ke GitHub, sudah berjalan pada PC
kedua, atau sudah menguji USB/radio fisik. Jalankan verifier kembali pada PC
pengganti dan uji perangkat pada jaringan yang akan dipakai.

Proses ekspor dan verifikasi handover tidak mengubah firmware, model, NVS,
nulling/binding, atau alur COM/Dataset pada perangkat yang sedang dipakai.

Lihat `status.json`, [tracker](../docs/GLD-FULL-HANDOVER-TRACKER.md), dan
[panduan portabilitas GLD](../docs/firmware/gld-pc-portability.md).
Lisensi runtime disertakan pada arsip masing-masing; Node LICENSE berasal dari
tag resmi v26.5.0.
