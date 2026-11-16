# Rancangan uji LoRa CH V3 — prototipe terisolasi

Dokumen ini adalah rancangan; pelaksanaan radio dua arah dan penanganan
timeout/STOP perlu diuji pada bench sebelum digunakan sebagai alat ukur.

## Lingkup dan bukti

- CH1 ID `0010`, CH2 ID `00F2`. Nilai ID ini teramati pada bench, bukan alokasi jaringan permanen yang terbukti bebas konflik.
- Firmware CH V3 menggunakan dua SX1262. Radio MESH yang sudah ada berbagi antrean, alarm, transaksi ACK, dan routing. Pada penerimaan yang berhasil, `handleMeshPacketReceived` memperoleh RSSI dan SNR dan memvalidasi AppFrame; `GET_STATUS` menunjukkan metrik ke **parent**, bukan sembarang peer. `SEND_HELLO` menjadwalkan hello ke parent dan bukan ping CH1–CH2.
- `transmitRadio` saat ini melakukan transmit yang blocking, menonaktifkan callback RX dan mengaktifkan kembali penerimaan setelahnya. Memakai radio yang sama untuk uji berarti tetap ada waktu buta RX; tidak boleh mengklaim zero impact terhadap alarm.
- Firmware CH asli belum mengirim metrik lewat Wi-Fi/ESP-NOW. Tester terpisah
  dan monitor sekarang memiliki implementasi ESP-NOW prototipe; keberhasilan
  end-to-end harus dinilai berdasarkan hasil uji aktual.

## Batas arsitektur

Pilih mode khusus tes yang dinyalakan secara eksplisit dan mati secara default. Untuk validasi awal gunakan dua perangkat terisolasi dari jaringan operasional, dengan rencana kanal serta daya yang disetujui. Jangan secara otomatis mengubah konfigurasi mesh tersimpan, ID, parent, atau NVS; jangan mengasumsikan mengubah kanal sementara aman pada instalasi produksi. Pertahankan firmware reguler sebagai paket terpisah yang dapat dipulihkan. Pemakaian bersama sistem alarm aktif memerlukan validasi waktu buta, airtime, prioritas, dan risiko terlebih dahulu.

## Kontrak tes yang diusulkan

Firmware LoRaTester CH1 dan CH2 berupa varian terpisah dari firmware CH asli. Monitor memulai tes melalui CH1; CH2 mengirim 100 paket ke CH1, lalu CH1 mengirim 100 paket ke CH2. Inti penghitung penerima terisolasi ada di `firmware/loratester/include/LoRaTesterSession.h`.

1. Monitor membuat ID sesi acak dan mengirim START ke CH1 lewat 2,4 GHz; CH1 memerintahkan CH2 dengan ID sesi dan jumlah 100. Tes dibatasi waktu dan tidak aktif setelah reset sampai diperintahkan lagi.
2. CH2 mengonfirmasi START, lalu mengirim 100 paket berurutan dengan ID sesi dan nomor 0–99 pada interval terbatas. Nomor urut, sesi, identitas sumber/tujuan, versi dan CRC diperiksa oleh CH1. Duplikat, sesi salah, paket cacat, maupun nomor di luar rentang tidak dihitung.
3. CH1 mengukur RSSI/SNR **di penerima CH1**, sehingga nilai tersebut menggambarkan arah CH2→CH1. Hitung nomor unik yang diterima; sebelum sesi berakhir tampilkan paket yang belum diterima, bukan hilang. Setelah tenggat tampilkan yang tidak diterima dari 100, sambil membedakan kegagalan pengiriman lokal CH2 jika laporan transmitter tersedia. Paket tidak diterima tidak otomatis berarti gangguan propagasi.
   Pada fase kedua CH2 mengukur RSSI/SNR untuk CH1→CH2 dan mengirim snapshot serta laporan akhirnya ke CH1.
4. Jika START atau konfirmasinya gagal, jangan menganggap tes sudah berjalan. CH2 dapat melaporkan jumlah yang berhasil diserahkan ke radio dan hasil pengiriman lokal; CH1 mencatat timeout bila laporan tidak diterima. Pembatalan harus menghentikan sesi tanpa mengubah NVS atau firmware CH asli.
5. Mode tes memakai radio sendiri pada varian firmware tersendiri; jamin bahwa kedua unit yang dimuat memang firmware tes, periksa antena serta alokasi kanal/daya, dan hindari lingkungan operasional aktif. Tidak ada jaminan zero impact apabila memakai kanal yang sama dengan mesh yang sudah aktif.

Prototipe menggunakan format paket tes terpisah, bukan jenis pesan AppFrame mesh produksi. Filter ID dan sesi bukan autentikasi; kompatibilitas dan dampak kanal bersama belum tervalidasi.

## Tampilan monitor

- ESP-NOW dipakai sebagai telemetri lokal CH1→ESP32 monitor pada kanal 1. Pairing sementara berdasarkan MAC dan sesi tidak terenkripsi dan bukan autentikasi yang tahan pemalsuan.
- Kirim hanya snapshot hasil tes dengan versi, sesi, sequence, waktu/umur, status tes, jumlah, metrik arah, dan flag validitas; lampirkan identitas CH1/CH2. Bedakan **RSSI LoRa** dan kualitas koneksi 2,4 GHz. Data kedaluwarsa atau link monitor putus harus ditampilkan sebagai tidak tersedia, bukan angka lama seakan baru.
- Jangan mengirim dari callback radio atau memblokir loop CH: callback hanya menyimpan event dalam antrean terbatas, tugas telemetri melakukan pengiriman terpisah; tentukan kebijakan antrean penuh dan pengaruh Wi-Fi pada kinerja radio/watchdog. Jangan menaruh secret dalam kode atau log.
- Batas tampilan monitor yang sudah disepakati: pusat (123,120), jari-jari 116 piksel; isi teks tetap dalam margin aman di dalamnya.

## Tes dan penerimaan

1. Host: codec batas payload, checksum, paket cacat, frame salah tujuan, versi/sesi salah, nomor urut wrap, ACK duplikat/terlambat, timeout dan timer rollover, counters 32-bit, ACK hilang versus PROBE hilang, freshness dan restart.
2. Host/simulasi: test mode default off; alarm/ACK/retry, RX re-arm, watchdog dan antrean tetap bekerja pada mode off dan saat mode tes diantrikan/dihentikan. Uji backwards compatibility perangkat lama dan gateway dengan tipe paket yang dipilih.
3. Build terpisah untuk CH V3 dan monitor; simpan paket yang sudah terbukti. Jangan mengganti versi produksi atau flash perangkat sampai target, efek jaringan dan prosedur test disetujui.
4. Bench terisolasi: periksa kedua ID dan antena, lakukan tes per arah dengan daya dan jarak yang sesuai, catat packet sequence dan ground truth hitungan. Putuskan CH2 dan 2,4 GHz bergantian untuk memvalidasi timeout dan indikator data usang. Periksa waktu buta RX serta respons alarm dibanding baseline.

## Keputusan yang masih dibutuhkan

- Apakah pengujian berlangsung pada kanal yang sama dengan mesh aktif atau di bench terisolasi, dan batas airtime yang diperbolehkan?
- Firmware tester sudah diputuskan sebagai varian terpisah, sehingga tidak menjalankan alarm/mesh asli saat tester dipasang.
- Bagaimana antena 2,4 GHz CH1, pairing, dan konfigurasi kanal pada monitor disediakan?
- Kedua arah telah diminta, masing-masing 100 paket; hasil akhir perlu validasi bench dan penetapan kriteria penerimaan.
