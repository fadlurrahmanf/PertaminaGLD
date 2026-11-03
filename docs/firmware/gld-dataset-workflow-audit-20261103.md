# Audit wizard Dataset GLD — 3 November 2026

Scope: kesesuaian terhadap 14 langkah pengguna, protokol firmware 3, backend penyimpanan, UI dan paket Operator Hub. Audit ini menggunakan PC dan perangkat simulasi; tidak menggunakan COM7, GLD asli, upload, perubahan Wi-Fi laptop atau dialog Windows nyata.

## Temuan dan perbaikan

1. **Stop → Unlock → Lock → Continue gagal.** UI mengirim ulang konfigurasi identik ketika Lock, tetapi backend menolak semua Configure setelah CSV dimulai. Backend kini menerima konfigurasi identik secara idempoten. Perubahan kolom/label/mode tetap memerlukan Reset dan file baru agar CSV lama konsisten.
2. **Pemulihan penutupan sesi tidak dapat dijangkau.** Ketika penutupan sesi Direct tertunda dan retry berhenti, Lock ikut menonaktifkan password/Connect. Hanya dua kontrol tersebut sekarang terbuka untuk menghubungkan ulang GLD yang sama; perangkat, file dan skema tetap terkunci. Stop/Reset/Continue tidak berpura-pura tersedia selama cleanup.
3. **CSV tidak valid bisa menawarkan Start.** Setelah verifikasi rusak, tombol kini tetap Continue dan disabled sampai keadaan dapat diselesaikan atau Reset. Tidak menawarkan Start baru terhadap file yang telah dimulai.
4. **Penjelasan kegagalan hilang terlalu cepat.** Error tindakan kini terpisah dari error polling status. Polling yang sukses tidak menghapus penjelasan tindakan yang ditolak; error polling sementara hilang ketika status kembali tersedia.

5. **Tabel pada jendela sempit tidak mempunyai area scroll sendiri.** Wrapper wizard kini memiliki scroll horizontal. Headless Chrome pada viewport 700 px membuktikan wrapper 603 px tetap dapat menelusuri tabel 800 px; CSS fitur lama tidak berubah.

## Kesesuaian 14 langkah

|No.|Permintaan|Implementasi dan bukti|
|---|---|---|
|1|Scan Nearby GLD memperbarui daftar|Hanya kandidat GLD-DATASET-xxxx ditampilkan sebagai GLD-xxxx. Parser unit dan browser dengan platform simulasi diperiksa; scan Windows fisik masih deferred.|
|2|Pilih GLD dari combo box|Pemilihan harus berasal dari scan, identitas perangkat diperiksa saat autentikasi. Browser dan service tests.|
|3|Klik Connect|Password divalidasi sebelum join; setelah join autentikasi WebSocket dan protokol/model/profile harus sesuai. Native WLAN asli belum diuji.|
|4|Indikator Connected|Hijau hanya ketika connected dan ready. Setelah Stop, socket dapat ditutup; tujuh langkah menyimpan keberhasilan setup untuk Continue.|
|5|Pilih lokasi CSV|Pemilih file Windows, nama baru, parent writable; tidak menimpa file lama. Path validation tests dan injected picker pada browser; native dialog asli deferred.|
|6|Checklist kolom|Predicted Class + Confidence, Gain, Status sensor, dan durasi/overrun opsional. Timestamp dan delapan tegangan selalu ada. Prediksi belum valid disimpan kosong dengan status.|
|7|Dua kebijakan putus|Alias **Rekam langsung**: CSV membeku saat putus dan menunggu sesi lama selesai. **Pulih otomatis**: backlog kembali ke sesi/CSV yang sama sampai batas RAM lima menit selama GLD menyala.|
|8|Lock membuat pengaturan terlihat tetapi disabled|Berlaku sebelum rekaman. Setelah CSV dimulai, skema, label, mode, perangkat dan lokasi file tetap konsisten untuk Continue; ubah melalui Reset sesi. Exception hanya password/Connect untuk retry sesi milik aplikasi.|
|9|Tujuh langkah hijau + Lock menampilkan kontrol|Start awal enabled, Pause/Stop disabled. VM dan browser.|
|10|Start merekam|Start disabled, Pause dan Stop enabled. CSV dan ledger fsync sebelum ACK sampel.|
|11|Pause berganti Resume|Menghentikan akuisisi GLD setelah konfirmasi; tidak menambah baris selama jeda. Resume memakai sesi sama tanpa mengisi ulang waktu jeda.|
|12|Stop saat merekam/jeda, verifikasi lalu popup OK|Menunggu ACK/summary/drain, menutup dan memeriksa seluruh kolom/baris terhadap ledger penuh. Popup sukses tidak keluar hanya karena tombol diterima. Sesi incomplete diberi peringatan.|
|13|Setelah Stop tombol Continue|Continue membuat SID/segmen baru, meneruskan CSV yang sama dan row_id global; hash/skema/model/profile diperiksa. Unlock/relock konfigurasi identik kini tetap bisa Continue.|
|14|Reset saat tidak merekam, termasuk Pause|Saat Pause, terlebih dahulu Stop/drain/verifikasi. Setelah berhasil form kembali langkah 1; CSV tetap ada dan NVS tidak disentuh. Cleanup belum selesai mencegah Reset.|

## Firmware dan baseline

Audit GLD terpisah: 37 tes source/credentials/protected-baseline lulus. Source publik saat ini cocok dengan tiga compile sukses; empat image flash setiap paket Model 1/2/3 cocok dengan artefak dan manifest. Tidak ada perubahan firmware, compile ulang atau penggantian paket pada audit ini.

Kode baru tetap terpisah dari collector lama, kartu lama di Expert, fitur COM/nulling/LoRa/model/pin dan file pengguna tetap dilindungi. Bukti lama tidak dianggap sebagai bukti perangkat untuk firmware protokol 3.

## Verifikasi

Final: **264 tes Python lulus** (137 GLD, 90 Hub, 37 firmware source/credentials), **6 berkas tes Node lulus**, **7 skenario HTTP/WebSocket lulus**. Browser terbaru membuktikan delapan trace, Pause/Resume, Stop, Unlock/relock/Continue, retry cleanup melalui UI, empat download CSV (20/28/8/50 baris), dan 12 screenshot. Verifikasi independen mencocokkan seluruh nilai asli pada 13 SID: 798 baris canonical =770 public +28 private cleanup; 798 ACK sesuai data yang sudah fsync. Delapan baris public adalah kontrol tamper yang sengaja diubah setelah Stop; append ditolak. Semua empat download cocok dengan prefix file dan sampel asli.

Fixture retention test initially exceeded its 60-second drain deadline while auditing every actual fsync and all retained file prefixes. It subsequently drained all 607 rows and verified the file as incomplete, with retention_limit preserved. The first attempt and resolution are retained; a fresh isolated fixture uses a bounded 180-second drain deadline without changing product code.

## Batas bukti

Belum ada bukti perangkat asli untuk native Windows WLAN scan/join/file picker, AP startup/reconnect, interval ADS 500 ms bersamaan inferensi, heap/stack, RF dan pemulihan lima menit. Semua simulasi memakai data contoh, bukan data GLD asli. Tidak ada jaminan retensi RAM setelah GLD reboot atau backend/laptop berhenti.

Lihat `docs/GLD-WIRELESS-WORKFLOW-AUDIT-TRACKER.md` dan laporan independent di `tmp/workflow-audit-20261103/`.

## Handoff 2026-11-03 07:11:57 Asia/Jakarta

Operator Hub http://127.0.0.1:5173/ dan GLD http://127.0.0.1:5174/ aktif, sehat, wizard idle/disconnected. Proses lama dari hari sebelumnya sudah tidak ada dan port awalnya tertutup; audit ini memulai layanan baru, tidak menghentikan sesi pengguna. Semua tiga API paket tersedia. Refresh halaman untuk memuat JS/CSS terbaru. Dua fixture audit ditutup; port akhir 50893/50892 sudah tertutup. Tidak ada agent aktif.

Bukti final: `tmp/workflow-audit-20261103/audit-verification.json`, `e2e/verification-report.json`, `browser-output-final/browser-evidence.json`, dan dua laporan agent independen. Manual sebelumnya tetap menjelaskan alur yang sama; rincian penguncian skema serta retry cleanup diperjelas pada laporan ini.
