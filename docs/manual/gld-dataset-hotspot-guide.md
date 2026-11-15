# Panduan Dataset GLD via hotspot — draf untuk verifikasi aplikasi

Panduan ini mengikuti wizard Dataset Operator Console. Gambar final dan penomoran kotak akan ditambahkan setelah tampilan aplikasi final diuji pada GLD asli. Jangan gunakan manual serial/MQTT lama untuk alur hotspot ini.

## Sebelum mulai

1. Nyalakan GLD dengan catu eksternal 24 V. Sambungkan USB ke laptop jika kontrol Running, Nulling, atau upload firmware lewat COM diperlukan. Perekaman Dataset menggunakan Wi-Fi lokal GLD.
2. Jalankan `apps/operator-hub/run-operator-hub.bat` pada jendela yang bisa dilihat operator. Buka Operator Console dari Hub.
3. Sambungkan Wi-Fi laptop ke `GLD-DATASET-<ID>`. Status Windows **No internet** pada jaringan ini wajar: hotspot GLD adalah jaringan lokal. Jika perlu akses Internet bersamaan, gunakan Ethernet yang terpisah.
4. Pastikan firmware yang terpasang adalah paket hotspot final untuk model board yang benar. Jangan centang Reset NVS saat profil, ID, dan nulling yang ada ingin dipertahankan.

## Menyiapkan sesi

1. Di tab **Dataset**, klik **Scan Nearby GLD**, pilih GLD yang sesuai, lalu klik **Connect**. Tunggu indikator **Terhubung**. Koneksi Wi-Fi Windows saja belum membuktikan layanan data GLD dapat dijangkau; perhatikan indikator dalam aplikasi.
2. Pada **Lokasi CSV**, pilih file CSV baru atau folder Dataset bawaan. File lama tidak ditimpa.
3. Pada **Kolom tambahan**, pilih Predicted Class + Confidence bila inferensi GLD tersedia. CSV dasar selalu memiliki 12 kolom: waktu, label, delapan tegangan sensor, Predicted Class, dan Confidence. Ceklis prediksi mengisi dua kolom terakhir saat hasilnya valid; tanpa ceklis, nilainya kosong. Gain dan Status sensor menambah kolom hanya jika dipilih. Metadata teknis disimpan dalam catatan internal.
4. Pada **Saat koneksi putus**, pilih **Rekam langsung** untuk menghentikan penambahan CSV ketika koneksi terputus, atau **Pulih otomatis** untuk menahan sampel di GLD hingga lima menit dan mengirimkannya setelah koneksi pulih. Pilih sebelum sesi dimulai.
5. Isi **Label pengujian**. Aplikasi menambahkan cap waktu awal dalam format jam 24 jam dan tanggal `dd/mm/yy`.
6. Pastikan kelima langkah sudah hijau. Nyalakan **Lock pengaturan** agar input sesi tidak berubah saat merekam.

## Merekam dan memeriksa data

1. Klik **Start**. Status harus berubah menjadi merekam dan jumlah sampel tersimpan mulai naik sekitar tiap 500 ms. Periksa grafik delapan sensor, nilai sensor, tabel sampel terbaru, serta Predicted Class/Confidence bila dipilih dan tersedia.
2. Tombol utama berubah menjadi **Pause** saat merekam. Klik untuk jeda, lalu **Resume** untuk melanjutkan. **Stop** dapat dipakai baik saat merekam maupun jeda.
3. Saat **Stop**, tunggu aplikasi menutup sesi dan mencocokkan isi CSV dengan sampel yang tercatat. Periksa hasil verifikasi sebelum menekan OK. Setelah sesi selesai, **Continue** melanjutkan CSV yang sama; **Reset sesi** memulai pengaturan baru saat perangkat sudah tidak merekam.
4. Gunakan **Export CSV** di bawah tabel untuk mengambil salinan file yang dipilih. Simpan juga laporan diagnostik bila aplikasi menunjukkan sesi tidak lengkap.

## Average pada grafik

Tombol **Average** di atas grafik adalah sakelar.

- **Mati:** grafik menampilkan tegangan mentah.
- **Aktif:** pilih **Jumlah data**, misalnya `10` untuk rata-rata bergerak sepuluh sampel terakhir per sensor; atau **Durasi**, lalu isi jam dan menit, misalnya `1 jam 15 menit`.
- Status di atas grafik menunjukkan **Grafik mentah** atau jendela Average yang sedang dipakai. Klik **Average** lagi untuk mematikannya.
- Batas jendela adalah 172.800 sampel atau 24 jam. Jika riwayat yang tersedia belum cukup, grafik memakai sampel yang ada dan menampilkan keterangannya.
- Rata-rata dimulai ulang jika sesi atau boot GLD berubah, atau ada celah urutan/waktu sampel. Nilai sebelum celah tidak dicampur dengan nilai sesudahnya.
- Average hanya mengubah delapan garis pada grafik. Angka sensor, tabel, CSV, hasil inferensi, dan data yang direkam tetap mentah.

## Jika koneksi bermasalah

- Jika hotspot terlihat tetapi aplikasi menyatakan alamat data tidak terjangkau, periksa lagi Wi-Fi laptop, alamat/rute lokal ke GLD, lalu gunakan **Scan Nearby GLD** dan **Connect**. Status **No internet** saja bukan galat.
- Jika **Start** ditolak, baca alasan yang muncul. Penolakan sebelum sampel pertama tidak berarti ada data CSV yang hilang. Jangan memulai sesi baru sampai status perangkat dan CSV jelas.
- Dalam mode **Pulih otomatis**, tunggu koneksi kembali dan perhatikan jumlah sampel tersimpan serta hasil verifikasi akhir. Buffer GLD menahan hingga lima menit selama GLD tetap menyala; pemadaman daya menghapus sampel yang masih berada di RAM perangkat.
- Bila aplikasi menunjukkan **Sesi tidak lengkap**, gunakan penyebab, jumlah dari perangkat, dan hasil rekonsiliasi yang ditampilkan sebagai dasar tindak lanjut. Jangan menganggap CSV lengkap sebelum verifikasi menyatakan cocok.

## Bukti uji yang akan ditambahkan

- [ ] Tangkapan layar wizard langkah 1–5, kotak nomor dan indikator koneksi.
- [ ] Tombol Start/Pause/Resume/Stop/Continue serta verifikasi CSV.
- [ ] Grafik mentah delapan sensor; Average aktif berdasarkan jumlah dan durasi; Average dimatikan kembali.
- [ ] Tabel dan Export CSV.
- [ ] Koneksi putus/pulih pada GLD asli, jika sesi uji aman dilakukan.
