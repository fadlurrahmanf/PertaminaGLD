# GLD Model 1 — uji hotspot dengan perangkat asli

Tanggal: 2026-11-02, selesai sekitar 14:41 WIB. Hasil: **PASS untuk bench tahap 1 Model 1**.

## Perangkat dan upload

Pengguna mengizinkan restart Operator Hub, upload Model 1 Hotspot ke COM7, dan uji data asli dengan Reset NVS OFF. Root melakukan seluruh akses hardware/jaringan secara berurutan; agent lain hanya menyiapkan runner atau memvalidasi artefak.

- GLD1 Model 1, device `1002`, external 24 V, firmware `0.8.36`, environment `gld_model_1_dataset_wifi`.
- Baseline profil nulling aktif/bound `1`, sensor/peripheral valid. Backup NVS privat 20.480 byte dibuat sebelum upload.
- Upload satu kali melalui Hub, Reset NVS tidak dicentang. Esptool melaporkan hash terverifikasi dan exit 0. Aktivitas backend mencatat environment yang benar, NVS preserved, dan verifikasi hotspot pending.
- Firmware SHA256: `bf8cd128c39b2ac277b153830b86eafb123c73b8df6e572409b30cb9f1030228`.
- Hotspot asli `GLD-DATASET-1002`; laptop mendapat `192.168.4.2/24`, gateway/server `192.168.4.1`. Data menggunakan WebSocket port 81 dengan autentikasi. COM tidak digunakan untuk pengambilan sampel.

## Hasil aktual

| Pemeriksaan | Hasil |
|---|---|
| Sesi normal | 29 record, sequence 0–28, Stop/summary lengkap |
| Delapan sensor | MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2; tegangan finite, gain valid, status 0 |
| Nulling setelah upload | Semua record menggunakan profile 1, sesuai baseline |
| Cadence GLD | 496–503 ms; median dan rata-rata 500 ms; 2 Hz |
| Durasi scan delapan kanal | 224–236 ms; overrun 0 |
| Integritas sesi normal | Gap 0, duplikasi 0; semua field export API dan download browser cocok dengan backend |
| Grafik | Delapan kurva asli terlihat di Dataset Wireless pada browser Codex |
| Putus radio | Laptop kembali ke Wi-Fi asal saat recording, sesudah minimal 8 record |
| Deteksi putus | Sekitar 1,703 detik; 9 record tersimpan, status incomplete, complete=false |
| Stabil sesudah putus | Hitungan tidak bertambah selama pemeriksaan 2 detik; CSV parsial cocok dengan download browser |
| Perlindungan CSV sebelumnya | SHA256 CSV sesi normal tidak berubah |
| Pemulihan jaringan | Wi-Fi laptop semula terhubung kembali dan terverifikasi |

Perbedaan hash antara unduhan browser dan file backend hanya berasal dari newline; header, seluruh baris, dan seluruh field cocok setelah parsing. Gap 0 pada CSV parsial hanya menggambarkan prefix yang diterima; jumlah sampel yang tidak diterima setelah radio putus tidak dinyatakan nol.

## Temuan dan perbaikan

Pemeriksaan pertama berhasil berasosiasi tetapi belum memperoleh koneksi TCP dalam lima detik. Runner berikutnya menunggu DHCP/rute/TCP hingga 20 detik; bukti menunjukkan sekitar 11,86 detik dari observasi awal tanpa IPv4 hingga TCP siap. Tidak ada Start yang dikirim pada percobaan awal tersebut.

Browser sempat memakai `hub.js?v=38` lama sehingga menampilkan VERIFIED dan menjalankan Test Device setelah flash khusus hotspot. Aktivitas backend membuktikan respons sebenarnya sudah pending hotspot. Versi asset diperbarui, halaman dimuat ulang, dan tes guard lulus; tidak ada upload ulang.

Pesan timeout sinkronisasi Wireless sempat bertahan setelah jaringan pulih. Modul Wireless kini menghapus pesan sinkronisasi sementara pada snapshot/event baru, mempertahankan error aksi, serta menampilkan status sesi lengkap/tidak lengkap. Tes race/model UI dan pemeriksaan browser lulus. Jalur Dataset serial dan environment firmware sebelumnya tetap terpisah.

## Artefak lokal

- CSV lengkap: `apps/gld-operator/output/datasets/wireless_1002_16915d55e0bf40d5a0bcb768789b9221.csv`.
- CSV putus: `apps/gld-operator/output/datasets/wireless_1002_ed0a954353c44be295d7e3c0251be59e.csv`.
- Bukti dan validator privat: `firmware/.pio/gld-real-test-20261102/validation/actual-capture-report.json`, `actual-drop-report.json`, bukti download browser, dan aktivitas upload yang sudah dihilangkan tokennya.
- Screenshot lengkap/panel: `firmware/.pio/gld-real-test-20261102/actual-eight-sensor-full.jpg`, `actual-wireless-panel.jpg`, `actual-drop-panel.jpg`.

Kredensial serta backup NVS tetap privat dan tidak disertakan dalam laporan ini. Hub/GLD bridge tetap berjalan pada localhost 5173/5174; firmware hotspot tetap terpasang. Rekaman sudah dihentikan, dan laptop berada pada Wi-Fi asal sehingga status Wireless disconnected/incomplete dari uji putus memang diharapkan.

## Batas bukti

Ini bench singkat pada Model 1; Model 2/3 baru memiliki bukti build, belum uji fisik. Tidak ada klaim soak test, seluruh variasi gain, atau pengujian ulang fisik semua mode lama. Paket produksi lama dipertahankan. Replay lima menit dan mode router tetap tahap 2; tahap 1 berhenti dan melaporkan incomplete ketika koneksi putus.
