# GLD1 Model 1 — kandidat pengaman nulling

Dokumen ini membedakan pengujian perangkat lunak dari kalibrasi fisik. Kandidat
ini **belum dibuktikan aman atau akurat untuk operasi keselamatan gas** hanya
karena build atau tes tiruan lulus. Jangan menjadikan GLD sebagai satu-satunya
alat keselamatan saat kualitas kalibrasi dan inference belum dibuktikan.

## Perubahan

- Hanya build GLD1 Model 1 dengan `PGL_GLD1_FAST_NULLING` yang memakai gerbang
  baru: crossing, verifikasi kandidat, dan pembacaan akhir harus valid **dan**
  stabil. Sebanyak-banyaknya tiga jendela diambil pada kode DAC yang sama;
  ambang stabilitas tidak dinaikkan otomatis agar terlihat lulus.
- Jika akhir belum stabil, kanal gagal dan profil lengkap tidak diluluskan.
  Data baseline yang tidak lengkap juga ditolak. Pencarian di batas DAC tidak
  dibiarkan berulang tanpa akhir. Penulisan NVS diperiksa dengan read-back;
  ini **tidak** menjamin atomicity bila listrik mati saat penulisan.
- Crossing yang valid tetapi tidak stabil dapat ditolak dan pencarian
  dilanjutkan pada bracket berikut, maksimal empat bracket yang ditolak.
  Kandidat yang tidak stabil pada verifikasi dilewati. Sejak revisi Confirm 30,
  maksimum 30 titik discan per bracket: untuk jendela panjang, 29 kode dekat
  hasil binary dan titik ujung bracket yang sudah diperiksa ulang. Titik di
  antaranya dapat terlewat, sehingga kanal yang seharusnya dapat menemukan
  kandidat pada jendela lama mungkin kini gagal. Pembacaan
  verifikasi dan akhir yang diterima tetap harus valid, stabil dan memenuhi
  ambang. Jendela pembacaan invalid atau penulisan DAC gagal menghentikan
  kanal, bukan disamarkan sebagai noise. Waktu dapat bertambah saat banyak
  kandidat harus dicoba; belum ada estimasi durasi dari perangkat fisik.
- Log saat nulling memuat `NULLING_STABILITY_GUARD=ON`, dan log per kanal
  menunjukkan `NULLING_DECISION_OBSERVE` dan alasan bila gagal. Halaman
  Nulling menerjemahkan alasan baru agar lebih mudah dibaca.
- Revisi pencarian kandidat menampilkan `NULLING_RECOVERY=ON` saat proses
  nulling dimulai; penanda guard saja juga ada pada firmware sebelumnya dan
  tidak cukup untuk membedakan revisi ini.
- Revisi terbaru juga mencetak `NULLING_CONFIRM_SCAN_MAX_POINTS=30` saat mulai; log
  `NULLING_CONFIRM_LIMIT` menunjukkan jika jendela dipotong dan titik mana
  yang tetap dicoba. Batas itu hanya untuk titik scan; verifikasi kandidat
  dapat menambah pembacaan ADC. Bukan jaminan durasi atau 8/8.
- Eksperimen melewati lima kode DAC awal **tidak diaktifkan** di paket ini:
  bukti sebelumnya belum cukup untuk membuktikan kualitasnya. Pengukuran
  6 menit 50 detik sebelumnya bukan janji durasi versi pengaman ini.

## Batas dan uji mandiri

1. Pengujian host memakai firmware C++ dengan ADC/DAC/NVS tiruan, bukan GLD
   fisik. Hasilnya tidak membuktikan kestabilan analog, akurasi, konsistensi
   antar-run, deteksi gas, alarm, atau sertifikasi.
2. Firmware baru tidak menguji ulang profil nulling lama secara otomatis.
   Setelah upload tanpa Reset NVS, hasil profil sebelumnya tetap perlu dinilai;
   jalankan nulling baru bila hendak menguji gerbang ini.
3. Jalankan nulling lewat Operator Hub, amati hasil 8 kanal dan alasan gagal.
   Jika gagal, simpan log dan jangan menganggap profil baru layak. Jika PASS,
   itu berarti lolos pemeriksaan firmware, **bukan** bukti akurasi referensi.
4. Gunakan GET_STATUS/Expert untuk memastikan profil yang aktif, binding model,
   dan inference benar-benar siap. Nulling baru dapat mengganti ID profil dan
   membuat binding lama tidak cocok; jangan mengubah binding secara membabi
   buta. Perlu pembuktian akurasi serta repeatability memakai referensi dan
   metode penerimaan yang sesuai sebelum penggunaan operasional keselamatan.
5. Kegagalan setelah memulai nulling atau mati listrik dapat memerlukan
   pemulihan dan verifikasi profil/DAC; jangan menganggap profil lama pasti
   masih diterapkan hanya karena data NVS sebelumnya tidak dihapus.

Paket GLD1 Model 1 sebelum pekerjaan ini dicadangkan lengkap dan hash-verified
di `tmp/gld1-model1-pre-stability-20261019`. Riwayat pengujian sebelumnya:
[eksperimen](GLD1-NULLING-EXPERIMENT.md) dan
[tracker](GLD1-NULLING-STABILITY-GOAL-TRACKER.md).
