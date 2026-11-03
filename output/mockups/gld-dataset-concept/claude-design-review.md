# Tinjauan Desain: Operator Hub GLD Dataset

## Kritik singkat

Layar saat ini menonjolkan **langkah konfigurasi**, padahal yang paling penting bagi operator adalah **status rekaman dan data yang sedang berjalan**.

- **Kartu langkah terlalu tinggi.** Kartu bergaris tebal, margin lebar, dan kartu sensor raksasa membuat operator harus menggulir untuk tahu apakah sistem siap.
- **Grafik terdorong ke bawah.** Grafik tidak lagi menjadi pusat perhatian.
- **Kesiapan sulit dibaca.** Status hijau kumulatif tersebar di lima kartu besar, sehingga tidak bisa dipahami dalam satu pandangan.

**Perbandingan dua alternatif pada lebar 1024px:**

| | Terpusat | Workspace |
|---|---|---|
| Kelebihan | Grafik mendapat lebar penuh | Kelima input tetap terlihat, monitor tetap dominan |
| Kekurangan | Lima blok konfigurasi di atas akan menghabiskan sekitar 40% tinggi layar. Saat terkunci dan merekam, blok tersebut menjadi "beban mati" di atas data. | Lebar grafik sedikit berkurang |

## Rekomendasi: **Workspace**

**Tata letak pada 1024px:**
- **Inspector kiri:** lebar tetap 300–320px, dapat digulir sendiri.
- **Monitor kanan:** sekitar 680px, berisi urutan berikut dari atas ke bawah:
  1. Bilah kontrol
  2. Kelas + confidence
  3. Grafik
  4. Tabel sampel
  5. Tombol Ekspor
- **Saat jendela diperluas (≥1280px):** inspector tetap 320px, dan seluruh ruang tambahan diberikan ke grafik.

**Reflow layar sempit (<900px):**
- Inspector ditumpuk di atas monitor, dengan kelima langkah tetap terbuka penuh (jangan diciutkan saat terkunci).
- Bilah kontrol Start/Pause/Stop dibuat *sticky* di atas.
- Grafik minimal setinggi 240px.

## Rekomendasi konkret

**1. Ubah kartu langkah menjadi baris "rail" yang padat.**
- Setiap langkah: lencana nomor (20px), judul 13px semibold, chip status di kanan (*Siap* / *Belum lengkap* / *Menunggu langkah 1*), lalu input langsung di bawahnya.
- Gunakan grid 8px dengan jarak antarlangkah 12–16px. Garis vertikal tipis di kiri berubah hijau secara kumulatif.
- Jangan pakai kotak bergaris di tiap langkah. Pemisah 1px sudah cukup.
- Langkah 1 cukup satu baris: `[Pindai GLD] [dropdown GLD-1002] [Hubungkan]`. Tidak ada kolom kata sandi, dan tidak perlu teks penjelasan soal sandi.

**2. Tambahkan bilah status global di atas monitor.**
Satu baris berisi: perangkat dan status koneksi · mode (Rekam langsung / Pulih otomatis) · nama file CSV (dipotong di tengah, path lengkap di tooltip) · status kunci · status rekaman (*Siaga / Merekam / Dijeda / Memverifikasi / Selesai*).
Operator harus bisa menjawab "apa yang terjadi sekarang?" tanpa melihat inspector.

**3. Buat status terkunci tetap terbaca, bukan sekadar pudar.**
- Input nonaktif tetap menampilkan nilainya dengan kontras teks ≥4.5:1. Cukup ganti latar menjadi navy redup dan tambahkan ikon gembok kecil.
- Jangan pakai opacity 40% pada seluruh blok.
- Di bawah langkah 3 dan 5, tampilkan keterangan setelah CSV dimulai: *"Skema & label terkunci hingga Reset."*
- Tombol Kunci/Buka Kunci diletakkan di dasar inspector, sebagai satu tombol lebar penuh.

**4. Jadikan bilah kontrol sebagai mesin status yang eksplisit.**
- Start/Pause/Stop baru muncul setelah semua langkah hijau dan terkunci. Sebelum itu, tampilkan placeholder: *"Lengkapi 5 langkah lalu Kunci untuk mulai."* Placeholder ini membuat tata letak tidak melompat.
- Pause berganti label menjadi **Lanjutkan Rekam** di posisi yang sama.
- Beri jarak ≥16px atau pemisah antara Stop (gaya destruktif) dan tombol lain.
- Setelah Stop, tampilkan status *"Memverifikasi CSV…"* dengan indikator berjalan. Notifikasi sukses hanya muncul setelah verifikasi selesai.
- Label **Continue** dibuat eksplisit: *"Lanjutkan — tambah ke CSV yang sama"*.
- **Reset** hanya aktif saat siaga atau dijeda. Saat nonaktif, tampilkan alasannya. Dialog konfirmasi berbunyi: *"File CSV tidak dihapus."*

**5. Bedakan kehilangan koneksi per mode.**
- **Rekam langsung:** banner merah di monitor, *"Koneksi GLD terputus — CSV dibekukan, pembersihan tertunda."*
- **Pulih otomatis:** banner amber, *"Memutar ulang backlog (maks. 5 menit, di RAM)"*, ditambah peringatan tetap: *"Buffer hilang bila perangkat mati."*
- Tampilkan hanya angka yang memang disediakan backend. Jangan menambahkan persentase atau perkiraan waktu buatan.
- Selain warna, gunakan juga ikon dan teks.

**6. Grafik menjadi pusat layar.**
- Kelas + confidence ditampilkan dalam satu baris di atas grafik: nama kelas 16px semibold, confidence dengan angka monospace (contoh: `87,4%`).
- Grafik harus identik dengan versi Running: 8 warna trace tetap, grid halus, sumbu nol lebih tegas, dan label rentang Y serta jendela waktu.
- Ganti kartu sensor raksasa dengan **legenda-nilai** ringkas di bawah atau samping grafik. Setiap item berisi swatch warna, `MQ-x`, dan nilai terkini (misalnya `1,284 V`). Buat 2 baris × 4 kolom pada 1024px.

**7. Tabel sampel yang padat dan teknis.**
- Tinggi baris 28px dengan header sticky.
- Angka menggunakan font monospace dengan *tabular figures*, rata kanan, dan jumlah desimal yang konsisten.
- Kolom opsional (kelas, confidence, gain, status sensor, timing) hanya muncul jika dicentang di langkah 3, sehingga tabel mencerminkan skema CSV yang sebenarnya.
- Tombol **Ekspor** diletakkan di bawah tabel, rata kanan.

**8. Tipografi dan warna.**
- **Teks UI:** Segoe UI (bawaan Windows).
- **Angka dan bacaan sensor:** Consolas atau JetBrains Mono.
- **Permukaan:** navy berlapis, misalnya latar #0F1B2D, panel #16243A, garis #24344D.
- **Oranye Pertamina:** hanya untuk aksi utama (Start, Kunci) dan langkah aktif. Jangan dipakai sebagai warna trace atau warna peringatan, agar maknanya tidak bercampur dengan amber.
- **Warna status:** hijau = siap, amber = pemulihan, merah = putus atau gagal.

**9. Langkah 5: prefix sebagai bagian input.**
- Prefix `HH:mm Hari dd/mm/yy` ditampilkan sebagai segmen abu di sisi kiri input yang sama, monospace, dan tidak bisa difokuskan.
- Di bawahnya, tampilkan pratinjau label lengkap, misalnya: *"14:05 Selasa 03/11/26 Uji LPG-A"*.

**10. Kejujuran mock.**
- Tampilkan badge kecil yang selalu terlihat di header: *"Mock — data sintetis, tidak terhubung ke perangkat."*
- Tombol Pindai/Hubungkan hanya menyimulasikan status.

## Hal yang perlu dihindari

- Menyembunyikan atau menciutkan input saat terkunci. Ini melanggar kontrak.
- Status hijau per langkah yang tidak kumulatif, misalnya langkah 3 hijau padahal langkah 2 belum.
- Notifikasi "berhasil" yang muncul sebelum verifikasi CSV selesai.
- Mengubah urutan atau warna trace antara mock dan versi Running.
- Menambahkan metrik baru seperti laju sampel, kesehatan sinyal, atau estimasi ukuran file.
- Tata letak yang melompat saat bilah kontrol muncul. Sediakan ruangnya sejak awal.
- Teks campuran Inggris–Indonesia. Gunakan istilah yang konsisten: *Rekam, Jeda, Lanjutkan, Hentikan, Atur Ulang, Ekspor*.