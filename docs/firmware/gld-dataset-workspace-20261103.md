# Dataset Workspace - Operator Hub

Revisi 3 November 2026. Tampilan ini sudah menjadi bagian aplikasi GLD Operator,
bukan halaman mock. Grafik memakai renderer yang sama dengan Running.

## Cara memakai

1. Nyalakan GLD dengan catu eksternal 24 V. Firmware harus **Hotspot Wizard
   Dataset**, sesuai Model 1/2/3. Profil nulling harus valid; saat upload,
   **Reset NVS OFF**. Hotspot/Replay protokol 1/2 lama tidak mendukung alur ini.
2. Buka Operator Hub, masuk GLD, lalu tab Dataset. Klik **Scan Nearby GLD**.
   Pilih ID yang benar, misalnya **GLD-1002**, lalu **Connect**. Backend memakai
   password otomatis. Pastikan koneksi serial COM sudah dilepas. Hotspot GLD
   tidak menyediakan Internet.
3. Setelah indikator Connected, klik **Pilih file CSV** dan tentukan nama baru
   dalam folder yang dapat ditulis. File lama tidak ditimpa.
4. CSV utama berisi **12 kolom**: waktu, label pengujian, delapan tegangan,
   Predicted Class dan Confidence. Gain dan Status sensor tidak dicentang
   secara default; masing-masing menambah delapan kolom jika dipilih.
   Aktifkan Predicted Class + Confidence untuk mengisi hasil inferensi.
   Pilihan ini hanya aktif ketika model, binding dan kalibrasi siap; kolom
   prediksi tetap ada tetapi kosong bila tidak dipilih atau hasil belum valid.
   Pada rilis tiga model terbaru, Model 2 sudah diaktifkan berdasarkan konfirmasi validasi dan persetujuan operator. Durasi/overrun dan metadata sesi
   disimpan internal, tanpa menambah kolom Excel.
5. Pilih satu kebijakan putus: **Rekam langsung** atau **Pulih otomatis**.
   Isi label kondisi pengujian. Timestamp otomatis memakai format
   `HH:mm Hari dd/mm/yy` di awal label lengkap.
6. Setelah kelima nomor hijau, aktifkan **Lock**. Pengaturan tetap terlihat
   tetapi tidak dapat diedit. Tombol rekaman muncul.
7. Klik **Start**. Tombol yang sama berubah menjadi **Pause**, lalu **Resume**
   jika dijeda. Pause menghentikan akuisisi setelah GLD mengonfirmasi. Inferensi
   membutuhkan 10 sampel pemanasan, sekitar 5 detik, setelah Start/Resume.
8. Klik **Stop**, termasuk saat Pause, lalu tunggu verifikasi seluruh CSV.
   Baca popup, kemudian klik **OK**. **Continue** menambah segmen baru pada file
   yang sama. **Resume** melanjutkan sesi yang sedang dijeda.
9. Di bawah tabel, klik **Export CSV** untuk mengunduh salinan file rekaman.
   Tabel menampilkan 10 baris terakhir; CSV berisi seluruh baris.
10. **Reset sesi** kembali ke pengaturan awal tanpa menghapus CSV/NVS. Reset
    tidak aktif ketika merekam. Reset saat Pause harus menyelesaikan Stop dan
    verifikasi dahulu. Setelah CSV dimulai, gunakan file baru untuk mengganti
    konfigurasi.

## Saat koneksi terputus

- **Rekam langsung:** CSV, hitungan dan grafik lama berhenti bertambah. Sesi
  ditandai tidak lengkap; tunggu backend menutup sesi lama sebelum melanjutkan.
- **Pulih otomatis:** sambungkan laptop ke hotspot GLD dengan ID yang sama.
  Sampel tertunda kembali ke CSV yang sama menggunakan timestamp aslinya.
  Tidak perlu menekan Start baru.
- Buffer berada di RAM GLD sampai batas lima menit. Pada batas retensi, GLD
  menghentikan sampling sebagai incomplete. GLD harus tetap menyala. Reboot
  menghilangkan buffer; restart backend/laptop bukan pemulihan yang dijamin.
- Pertahankan backend Operator Hub tetap berjalan selama merekam atau pulih.

## Bukti dan batas pengujian

### Pembaruan CSV ringkas

|Pilihan|Jumlah kolom CSV|
|---|---:|
|Default|12|
|Gain saja / Status sensor saja|20|
|Gain dan Status sensor|28|

Urutannya: `Waktu (ms)`, `Label pengujian`, `MQ8 (V)`, `MQ135 (V)`,
`MQ3 (V)`, `MQ5 (V)`, `MQ4 (V)`, `MQ7 (V)`, `MQ6 (V)`, `MQ2 (V)`,
`Predicted Class`, `Confidence`. Kolom Gain/Status ditambahkan setelahnya.
Waktu adalah timestamp GLD dalam milidetik; label lengkap tetap memiliki
awalan jam/hari/tanggal. Nilai confidence tetap 0..1, dapat diformat sebagai
persentase di Excel. Kelas tetap indeks model seperti sebelumnya.

Identitas perangkat/boot/sesi, nomor urut/segmen, profil/model, gain/status,
waktu akhir scan, overrun, dan detail inferensi lengkap tetap ada pada ledger
internal untuk pemeriksaan, meskipun kolom opsional tidak dipilih. ACK tetap
diberikan setelah CSV dan ledger tersimpan; Stop tetap memeriksa semua baris.
Gunakan sesi/file baru untuk format ringkas. CSV lama tidak diubah.

Pembaruan ini diuji di PC melalui UI/HTTP/SSE/WebSocket dan unduhan browser,
termasuk Pause/Resume, Stop/Continue, Direct cutoff dan Replay. Tidak memerlukan
compile atau upload firmware; pengujian fisik di bawah adalah bukti revisi
firmware/UI sebelumnya, bukan klaim uji GLD baru untuk perubahan kolom ini.

Tampilan diuji pada delapan kondisi lebar layar/tema. Pemeriksaan PC meliputi
API, SSE, WebSocket, CSV, kontrol, cut-off Direct, replay dan batas 300 detik
dengan peer sintetis. Pada GLD1002 asli, grafik delapan kanal, interval median
500 ms, Pause/Resume, Stop/Continue, download CSV dan putus-sambung singkat telah
terbukti. Uji otomatis memasok lokasi CSV unik agar tidak memerlukan kendali
dialog Windows; radio, data, kontrol dan penyimpanan memakai jalur asli.

Pada uji pertama ditemukan bug pemeriksaan input inferensi (8 versus total
8+7). Perbaikan hanya menyentuh gerbang inisialisasi ML pada varian Workflow;
approval, binding model, kalibrasi dan validasi output tetap diberlakukan.
Uji ulang firmware berhasil: Predicted Class + Confidence aktif, 119 baris CSV cocok dengan ledger, termasuk 81 hasil prediksi valid dan 38 sampel pemanasan. Median interval tetap 500 ms (496-504 ms pada pengukuran awal), durasi inferensi 1-2 ms. Pulih otomatis mengembalikan 61 sampel tanpa gap/duplikat. Uji pesan pemulihan tambahan juga lulus dan menghasilkan CSV terverifikasi.

Panduan bergambar terbaru: [Manual Dataset - CSV 12 kolom](../../output/pdf/Manual-GLD-Dataset-Workspace-12-Kolom.pdf).
Manual 14 halaman berisi screenshot, kotak dan nomor petunjuk, pilihan tiga
paket final, rekaman, CSV, serta pemulihan koneksi. Gambar kontrol dan grafik
berasal dari pengujian GLD1002 sebelumnya; gambar pilihan paket/kolom diambil
dari UI terbaru tanpa mengoperasikan perangkat.

Pembersihan daftar paket sudah diterapkan. Revisi firmware yang mempertahankan
fitur normal melalui COM masih dalam review source dan belum dikompilasi,
dipaketkan atau di-upload. Paket yang sekarang tersedia tetap revisi sebelumnya.
Untuk kembali ke kontrol COM, Stop dan selesaikan verifikasi CSV lalu Disconnect
Dataset terlebih dahulu. Manual versi 12 halaman dan panduan lima langkah lama
tetap disimpan sebagai arsip.

Catatan revisi firmware baru (belum build): hotspot dimulai setelah inisialisasi
normal. Mode Dataset tersimpan dapat menunggu koneksi router sekitar 15 detik,
di luar diagnostik awal; mode Nulling dapat menunggu kalibrasi. Tunggu boot
selesai sebelum Scan. Lama total harus diukur pada GLD. Saat Pause/pemulihan,
akuisisi berhenti dan alarm menyimpan hasil valid terakhir. LoRa kembali
tersedia setelah sesi wireless selesai, data terverifikasi dan Disconnect.

## Pembaruan paket fitur normal + hotspot

Model 1/2/3 sudah dicompile paralel dan tiga paket final Hub diperbarui.
Fitur normal melalui COM dan Dataset melalui Wi-Fi ada pada image yang sama.
Alur upload baru melakukan reconnect COM serta pemeriksaan versi/ID untuk
paket yang memiliki penanda nativeSerial. Paket normal dan paket lama tetap
disimpan. Tidak ada upload GLD atau Reset NVS pada pembaruan ini.

Backend Hub dan bridge GLD yang masih berjalan perlu restart sebelum upload
paket baru. Restart otomatis yang disetujui pengguna ditolak pemeriksaan
persetujuan otomatis sebelum berjalan; COM7 tetap terhubung. PDF 14 halaman
sebelumnya masih mencatat status sebelum compile ini; alur operator tetap
berlaku, sedangkan status build terbaru mengikuti bagian ini.

Aktivasi backend sudah diselesaikan setelah proses GLD lama yang tertinggal
ditutup pengguna. Backend baru berhasil menerima format capabilities untuk
ketiga model; pilihan Model 2 pada browser juga diperiksa tanpa upload.
Pengaman port Windows kini mencegah listener ganda. Catatan restart yang
terblokir sebelumnya adalah riwayat; backend saat ini sudah aktif.

## Rilis tiga model dan sync terbaru

Ketiga paket Hotspot Wizard Dataset Model1/2/3 sudah diperbarui bersama,
dengan fitur sama dan model/scaler/kelas masing-masing. Compile memakai
tiga agent dengan428detik overlap; seluruh paket dan byte yang disajikan
Hub sudah diverifikasi. Model2 kini diaktifkan berdasarkan validasi
board/gas yang dilaporkan dan disetujui operator; tidak ada uji gas baru
oleh agent. Catatan lama tentang approvalModel2tertunda adalah riwayat.

Refresh browser sebelum upload. UntukGLD1002yang memakaiModel2: upload
Model2HotspotWizardDataset dengan24V danResetNVS OFF. Pastikan GET_STATUS
segar menyatakan productionApproved=true dan profil aktif tetap2. Lalu
Running→Settings→Model&NullingProfile→UseLatestNullingProfile, konfirmasi
bindingNVS, RefreshStatus. Target: model/bindingcocok, bound==active,
profileReady=true; inferenceValid menyusul saat sampel baru valid.
Kalibrasi dan dataCSV lama tetap dipertahankan. Hub tidak diluncurkan
ulang pada rilis ini; bila perlu startup, gunakan terminal yang terlihat.
