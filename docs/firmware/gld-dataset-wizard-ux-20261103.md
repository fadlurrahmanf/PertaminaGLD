# Dataset GLD — revisi lima langkah

Tanggal: 3 November 2026, Asia/Jakarta. Mengikuti koreksi pengguna setelah audit pagi; rincian UI pada laporan sebelumnya merupakan riwayat.

## Perubahan sesuai permintaan

|Permintaan|Hasil|
|---|---|
|Nomor hijau berurutan|Readiness API dan UI kumulatif. Semua nomor awal abu-abu; koneksi saja membuat nomor1 hijau; kolom/mode/label menunggu lokasi CSV siap. Nilai bawaan yang valid baru hijau setelah prasyaratnya terpenuhi.|
|Gabungkan langkah1/2/3|Satu kartu **1. Hubungkan GLD** berisi Scan Nearby GLD, combo perangkat, Connect, Disconnect dan indikator. Total menjadi lima langkah.|
|Tanpa input password|Connect mengambil kredensial workflow lokal di backend. Nilai tidak dikembalikan ke browser, snapshot, event atau log. Konfigurasi tiga model harus valid dan sepakat; tidak ada password tebakan/fallback atau rotasi. Resolusi konfigurasi nyata berhasil diperiksa tanpa menjalankan WLAN.|
|Predicted Class + Confidence bisa dicentang|Aktif setelah koneksi/ready dan file CSV dipilih, jika perangkat menyediakan prediksi. Alasan saat belum tersedia ditampilkan. Tidak memalsukan prediksi atau memaksa model yang belum siap.|
|Mode berupa pilihan bulat|Dua radio dengan satu nama grup: **Rekam langsung** / **Pulih otomatis**. Hanya satu bisa dipilih. Kebijakan CSV/cleanup/replay tetap sama.|
|Timestamp sebelum label|Contoh **07:35 Selasa 03/11/26 clear_air_test**. Jam24h/WIB; timestamp ditetapkan saat memilih file dan tetap selama Continue. Reset mengosongkannya.|
|Grafik seperti Running|Renderer `drawOneChart` yang sama: grid, sumbu nol, warna, label, tinggi responsif dan range. Feed Dataset eksplisit, tidak mengganti history/clock/pilihan kanal Running. Delapan kartu sensor memakai voltage/gain/status asli. Pause/pergantian SID memutus garis.|
|Prediksi di atas grafik|Class yang diprediksi, nama gas dan confidence dari sampel terakhir yang benar-benar tersimpan. Warmup/not_ready/error tidak mempertahankan confidence lama. Pause, menunggu koneksi, selesai dan incomplete dibedakan.|
|Export di bawah tabel|Satu tombol **Export CSV** berada setelah tabel sampel; mengunduh salinan file yang sama. Empat download browser diperiksa terhadap file dan sampel asli.|

Label wire firmware tetap maksimal31 karakter dan tidak berubah. CSV/canonical baru menyertakan `label_timestamp` dan `display_label` lengkap selain `label` asli. Header/identitas/hash tetap dilindungi ketika Continue. Tidak mengubah CSV lama atau membutuhkan compile firmware baru.

## Bukti pengujian

- **274 Python PASS:**147 GLD,90 Hub,37 firmware source/credentials/baseline. **7 berkas Node PASS**, termasuk golden canvas Running sebelum ekstensi, feed/time isolation dan transisi UI.
- **7 skenario HTTP/WebSocket PASS:**Pause/Resume, Continue, Direct cutoff/private cleanup, replay, batas retensi607baris, Reset saat Pause, proyeksi minimal dan penolakan tamper.
- Browser headless baru: lima nomor awal abu-abu, hanya koneksi hijau sebelum file, tanpa password input, radio eksklusif, timestamp, prediksi87.5%, delapan trace, Lock/Pause/Stop/Continue/Reset, retry cleanup dan empat download20/28/8/50baris.
- Verifikasi independen seluruh acquisition pada22SID: **901canonical =865public +36private**;901ACK cocok dengan prefix yang sudah fsync. Delapan baris public adalah kontrol tamper yang sengaja diubah setelah Stop; append ditolak. Kolom timestamp/label lengkap juga diperiksa tanpa memakai projector produksi.
- Hasil awal harness disimpan: perbandingan Canvas1.8 harus memakai toleransi float32; auto_capture simulasi harus dinonaktifkan sebelum Start/Continue; screenshot harus menunggu jumlah/status backend yang tepat. Perbaikan harness tidak mengubah firmware/transport produksi.
- Semua source/paket firmware Model1/2/3 tetap sama. Tidak ada compile, upload, COM7, resetNVS, koneksi WLAN asli atau dialog native pada pekerjaan ini.

## Manual dan aplikasi aktif

Manual baru: `output/pdf/Manual-GLD-Dataset-5-Langkah.pdf` —10halaman, screenshot simulasi asli, kotak/nomor dari koordinat DOM dan anotasi vektor. Semua halaman dirender Poppler dan diperiksa; screenshot tidak diedit. Manual lama dipertahankan sebagai riwayat. SHA256 baru tercatat pada `tmp/pdfs/gld-five-step/final-qa.json`.

Hub http://127.0.0.1:5173/ tetap berjalan padaPID6204. Hanya bridge GLD lama yang terbukti idle diganti; PIDbaru12940 diport5174 sehat, lima wizard_steps awal false dan tidak ada password pada snapshot. Refresh halaman untuk memuat aset baru. Fixture26540 telah ditutup dan port63140/63139 sudah tertutup.

## Batas bukti

Ini bukti PC dengan data contoh dan platform Windows yang diinjeksi. Native scan/join/picker Windows, AP GLD, ADS500ms bersama inferensi, heap/stack dan RF lima menit masih memerlukan GLD asli. Gate fisik rilis tetap deferred; source/build atau simulator bukan bukti perangkat. Tidak ada jaminan retensi setelah GLD/backend/laptop reboot.

Tracker: `docs/GLD-WIZARD-UX-TRACKER.md`. Bukti utama: `tmp/workflow-ux-20261103/e2e/verification-report.json`, `browser-output-final/browser-evidence.json`, `manual-capture.json`, `app-activation.json`, serta `verification.json`.
