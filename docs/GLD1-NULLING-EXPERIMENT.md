# Eksperimen percepatan nulling GLD1 Model 1

**Status: satu percobaan pada GLD1 COM7 telah dilakukan, tetapi akurasi dan
keamanan kalibrasi belum tervalidasi. Jangan deploy hasil ini sebagai
kalibrasi produksi berdasarkan dokumen ini.** Setelah percobaan firmware acuan
dikembalikan, tanpa Reset NVS. Paket Operator Hub tidak diganti.

## Hasil fisik 19 Oktober 2026

- User mengonfirmasi udara bersih. Firmware eksperimen ditulis ke app0; flash
  memverifikasi hash. Pengujian selesai `Ok 8/8`, profil 3 tersimpan, dan
  `NULLING_RUNTIME_RESULT=PASS`.
- Pengamatan waktu PC: 409,524 detik versus baseline 476,964 detik; selisih
  67,440 detik (14,1%) pada masing-masing satu run. Jumlah pengamatan confirm
  berubah dari 398 menjadi 343, sehingga hasil ini bukan bukti bahwa perubahan
  lima pembacaan sendiri selalu menghemat 14,1%.
- Pembacaan final seluruh 8 kanal eksperimen dan baseline bertanda `stable=0`.
  Pada baseline semua 14 pembacaan verify demikian, dan pada eksperimen semua
  11 pembacaan verify demikian. Flag ini tidak menjadi syarat lolos yang
  diterapkan firmware; hasil PASS tidak membuktikan kualitas atau akurasi.
- Firmware acuan SHA `9a4ed309ed4b91695cf6893d3e1863e569a8b835276250818e0f2ded0d20b608`
  dikembalikan dan hash flash diverifikasi. Profil 3 tetap diterapkan, tetapi
  binding model masih profil 1: `profileReady=false`, `inferenceValid=false`.
  Tidak melakukan binding otomatis. Jangan andalkan unit sebagai satu-satunya
  pengaman gas selama inference belum siap dan kalibrasi belum dinilai layak.
- [Laporan perbandingan](../outputs/gld1-nulling-eksperimen-20261019/Perbandingan_Nulling_GLD1.xlsx)
  memuat waktu per kanal, tahap, dan observasi langkah.

## Baseline dan hipotesis

Pada 19 Oktober 2026, nulling GLD1 Model 1 pada COM7 berhasil 8/8 dan memakan
476,964 detik. Rekaman berisi 40 pembacaan exponential pada DAC 1, 3, 7, 15,
dan 31 (lima pembacaan pada masing-masing dari delapan kanal); total waktu
observasi yang dilaporkan firmware untuk pembacaan tersebut 23,318 detik.

Firmware hanya dapat menerima bracket exponential mulai DAC 100. Kandidat
eksperimen memulai pencarian pada DAC 63, lalu 127, 191, dan seterusnya.
Urutan pasangan bracket yang memenuhi syarat sama secara aritmetis; pemindaian
confirm, verifikasi kandidat dan pemeriksaan akhir tidak dikurangi. Lima
pembacaan dan lima operasi DAC awal benar-benar dihilangkan, sehingga urutan,
durasi, AGC, dan settling analog bisa berubah. Kesetaraan matematis bracket
bukan bukti kesetaraan fisik.

Jika seandainya satu-satunya perubahan adalah penghilangan waktu observasi yang
terekam, penghitungan kasar menjadi 453,646 detik (sekitar 7 menit 34 detik),
atau 4,9% lebih singkat. **Ini ilustrasi aritmetis, bukan prediksi terukur**:
perubahan settling, gain, retry, dan overhead dapat mengubah hasil.

Salah satu temuan penting pada baseline: 335 dari 398 pengamatan confirm
bertanda `stable=0`. Pemilihan kandidat saat ini menggunakan validitas dan
ambang, bukan field `stable`, sebagai syarat. Ini tidak membuktikan hasil
kalibrasi salah, tetapi berarti PASS 8/8 tidak cukup untuk membuktikan
kestabilan atau keakuratan kalibrasi.

## Isolasi

- Flag `PGL_GLD1_EXPERIMENT_EARLY_EXP_SKIP=1` hanya diterima bersama flag fast
  GLD1 Model 1 dan guard board GLD1. Flag tidak terpasang di konfigurasi biasa.
- Build memakai `firmware/platformio.gld1-nulling-experiment.ini`, environment
  `gld1_nulling_experiment`, dan direktori build terpisah; post-script package
  Operator Hub dinonaktifkan. Output dipakai sekali untuk pengukuran teknis.
- GLD2, GLD3, profil model lain, kode alarm, LoRa, dan alur upload tidak
  diubah. NVS tidak dihapus, tetapi profil nulling di NVS diperbarui ke 3 oleh
  run yang diotorisasi.
- Rekaman dan hitung ulang hanya menyaring sampel lama. Ia bukan simulasi
  analog, bukan uji sensor fisik, dan tidak dapat mengukur efek penghilangan
  waktu tunggu atau menjamin nilai DAC yang sama.

## Gerbang sebelum dipakai

1. Operator dan penanggung jawab keselamatan menetapkan kondisi udara bersih,
   metode pengukuran pembanding yang sesuai, dan batas penerimaan akurasi serta
   repeatability sebelum pengujian. Jangan menyimpulkan aman dari log saja.
2. Simpan dan verifikasi cara pemulihan firmware dan profil; pastikan konsekuensi
   profil nulling baru pada binding model dipahami. Jangan Reset NVS otomatis.
3. Bandingkan baseline dan kandidat secara berulang dan terkendali pada GLD1,
   dengan kondisi yang dapat dibandingkan. Catat waktu total, hasil 8/8, nilai
   DAC, tegangan akhir, gain, status kestabilan, retry, dan hasil alat rujukan.
4. Tolak penggunaan bila pemeriksaan gagal, hasil di luar batas penerimaan,
   data tidak cukup, atau ada perubahan yang tidak dapat dijelaskan.
5. Barulah pertimbangkan paket Operator Hub setelah bukti fisik dan keputusan
   operator. Jangan mengubah GLD2/GLD3 atau perangkat lain.
