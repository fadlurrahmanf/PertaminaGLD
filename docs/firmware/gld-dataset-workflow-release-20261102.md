# GLD Dataset Wizard: firmware, aplikasi dan paket

> Arsip rilis 2 November 2026. Hash firmware dan status upload di bawah ini
> adalah bukti rilis saat itu. Untuk tiga paket final terbaru dan gate uji fisik,
> lihat [audit hotspot 9 November](gld-dataset-hotspot-audit-20261109.md)
> serta [tracker handover aktif](../DATASET-HANDOVER-GOAL-TRACKER.md).

Latest UI revision 2026-11-03: five grouped steps, cumulative readiness, backend-only credentials, timestamp label, shared Running chart and export below table. Current report: gld-dataset-wizard-ux-20261103.md; manual output/pdf/Manual-GLD-Dataset-5-Langkah.pdf. Firmware/protocol/binaries unchanged. Current app Hub6204/GLD12940. Earlier seven-step screenshots/PIDs below are historical; physical release gate remains deferred (95% release).


Status: build, pengujian PC dan aktivasi aplikasi selesai. Firmware belum diupload
dan revisi ini belum diuji pada GLD fisik. Tidak ada COM7, perubahan jaringan
Wi-Fi laptop, pemindaian WLAN nyata atau dialog native yang dijalankan selama
pengujian. Simulator menggunakan GLD dan platform Windows sintetis.

[Manual operator 10 halaman dengan screenshot dan kotak penunjuk](../../output/pdf/Manual-GLD-Dataset-Wizard.pdf)
menjelaskan langkah penggunaan. Semua gambar manual diberi label simulasi PC.
[Tracker release](../GLD-WIRELESS-WORKFLOW-RELEASE-TRACKER.md) memisahkan gate PC
dari gate perangkat yang masih ditunda.

## Alur yang tersedia

Tab **Dataset** sekarang berisi satu wizard. Kartu lama tetap dapat diakses di
**Expert > Dataset lama**, dengan kolektor dan format protokol lamanya dipertahankan.

1. **Scan Nearby GLD** memperbarui daftar kandidat hotspot; pilih misalnya GLD-1002.
2. Isi password dan **Connect**. Indikator hijau memerlukan koneksi, identitas GLD
   yang cocok, serta readiness perangkat; hasil scan saja belum membuktikan koneksi.
3. **Pilih file CSV** menentukan folder dan nama baru melalui pemilih file Windows.
   File yang sudah ada ditolak untuk mencegah penimpaan.
4. Pilih tambahan **Predicted Class + Confidence**, **Gain**, **Status sensor**,
   atau **Durasi pembacaan / overrun**. Delapan tegangan, timestamp dan identitas
   sesi selalu disimpan. Label pengujian dipisahkan dari prediksi model.
5. Pilih **Rekam langsung** atau **Pulih otomatis**, lalu lengkapi label pengujian.
6. Setelah tujuh nomor hijau, aktifkan **Lock pengaturan**. Input tetap terlihat
   tetapi nonaktif; Start/Pause/Stop ditampilkan.
7. **Start** mulai merekam. **Pause** menunggu konfirmasi jeda akuisisi; tombol
   berubah menjadi **Resume**. Waktu jeda tidak diisi sampel buatan.
8. **Stop** menunggu ACK, summary, durable prefix dan pemeriksaan seluruh CSV
   terhadap ledger lengkap. Popup hasil muncul setelah verifikasi; hasil incomplete
   tetap dibedakan. Setelah OK, **Continue** menambah segmen baru pada file yang sama.
9. **Reset sesi** tersedia saat tidak merekam atau saat Pause terkonfirmasi.
   Reset ketika Pause terlebih dahulu menutup dan memverifikasi sesi; file lama
   dipertahankan. Perubahan skema/perangkat/model yang tidak cocok tidak boleh
   disisipkan ke file lama melalui Continue.

Rekam langsung membekukan CSV, grafik dan hitungan publik pada kehilangan koneksi.
Penutupan sesi lama hanya memakai ledger privat. Pulih otomatis mempertahankan
sesi/file dan menarik data tertahan setelah tersambung. Buffer akuisisi lima menit
berada di RAM GLD; data tersisa dipertahankan selama perangkat tetap menyala.
Backend harus tetap hidup. Crash/restart backend dan pemulihan data RAM setelah
GLD mati tidak dijanjikan.

## Firmware dan paket

Gunakan target **Hotspot Wizard Dataset** sesuai Model 1/2/3. Ketiganya memakai
protokol workflow baru, terpisah dari firmware Hotspot/Buffer sebelumnya. Password
operator dipertahankan melalui konfigurasi privat; tidak dicantumkan di dokumen.
Reset NVS tetap OFF. Tidak ada upload dalam pekerjaan ini.

| Target | Ukuran firmware | SHA256 firmware |
|---|---:|---|
| gld_model_1_dataset_workflow_wifi | 1.103.984 byte | 74e822e4cff5f65918281e2f926b7be96f454b879461da1cb72023a18ff032fe |
| gld_model_2_dataset_workflow_wifi | 1.103.024 byte | 83c54872a7595726c446ead51382dfa78bb812d7765ebfe9544e132b99562704 |
| gld_model_3_dataset_workflow_wifi | 1.103.984 byte | fae547808d233ef241c6d03e8d7b456b2a3897cf1fa7829ac90cb98f692ebf19 |

Build ketiganya memiliki RAM statis 173.272/327.680 byte (52,9%) dan flash16,8%.
Model1/2 memakai direktori build dan libdeps terpisah setelah percobaan awal
menemukan benturan pembersihan direktori PIO. Ketiga compile berhasil dengan
overlap nyata 22:45:18–22:49:53 WIB, sekitar275,5 detik. Log gagal dan hasil retry
dipertahankan; tidak ada perubahan C++ untuk mengatasi benturan direktori tersebut.

Paket berada pada masing-masing direktori baru
`apps/operator-hub/firmware-packages/<target>/latest/`. Empat image, manifest,
SHA256 dan provenance model lulus validator child, pemilihan paket Hub dan
preflight. Identitas model/scaler, blob model, GLD1v0.8.36 serta batas/sektor NVS
diverifikasi. Paket dan artefak lama tidak diganti.

Firmware menjalankan prediksi opsional dari frame sensor yang sama, memakai
moving average dan preprocessing model. Readiness model, approval dan binding
profil diperiksa. Warmup/not_ready/error mengirim kelas dan confidence null;
hasil prediksi asli disimpan bersama frame dan tidak dihitung ulang saat replay.
Timing500ms dan penggunaan heap pada GLD tetap memerlukan pengujian perangkat.

## Bukti yang diperoleh

| Gate | Hasil |
|---|---|
| Tes aplikasi Python | 135 lulus, termasuk22 service dan17 adversarial |
| Tes Operator Hub | 90 lulus |
| Source/kredensial firmware | 37 lulus; file privat nyata tidak diinspeksi tes |
| Tes UI Node | Seluruh tujuh file lulus |
| WebSocket peer | Lima tes kontrak RFC6455; tujuh skenario HTTP/SSE/WS lengkap lulus |
| Browser nyata | Tujuh langkah, Lock, delapan trace, Pause/Resume, Stop/OK, Continue, Reset, dua mode dan empat unduhan lulus |
| Unduhan | 20 baris snapshot awal, lalu28/8/50 baris cocok; snapshot20 adalah prefix sah dari file yang kemudian bertambah menjadi28 |
| Uji independen | 14 SID,305 sampel asli sintetis:245 publik+60 privat; seluruh kolom cocok;305ACK sesudah fsync yang diidentifikasi melalui file descriptor |
| SSE | 143 event:45sample+98state; tidak ada sampel cleanup privat dipublikasikan |
| Verifikasi panjang | 7.205 baris diperiksa seluruhnya walaupun history UI hanya7.200 |
| Proteksi | 233 fingerprint source/paket dan CSV pengguna62baris cocok;321file paket/artefak lama tidak berubah |
| Manual | 10 halaman dirender Poppler dan ditinjau; PNG asli, anotasi vektor; kotak yang tertutup header tidak digunakan |

Pengujian mencakup Pause ambigu, Stop tertunda, akhir retensi300s, kapasitas,
fsync/write/close gagal, rollback transaksi CSV+ledger, perubahan file/model,
identitas asing, Reset saat Pause dan cleanup langsung. Ini pengujian transport,
aplikasi dan disk PC nyata dengan peer sintetis; bukan bukti eksekusi state machine
C++ atau pembacaan sensor/radio/inferensi GLD fisik.

## Aktivasi dan sisa gate

Hub lokal5173 dan GLD bridge5174 telah diaktifkan dari source terbaru setelah
kolektor lama/COM dipastikan idle. Health menyatakan `datasetWorkflow=true`;
wizard disconnected/unlocked/count0. Katalog Hub menampilkan ketiga paket baru,
dan API paket hidup mengembalikan empat image dengan hash yang cocok. Simulator
dan kedua port uji telah ditutup. Tidak ada koneksi perangkat dibuat saat aktivasi.

Masih perlu: upload yang diizinkan saat GLD tersedia, uji Windows Scan/join dan
dialog file pada sesi operator sebenarnya, interval/inferensi/heap pada perangkat,
serta putus-sambung Wi-Fi fisik. Source ABI platform Windows sudah direview dan
parser/validasi lokasi sudah diuji; konfigurasi beberapa adaptor belum dibuktikan.

Bukti rinci lokal berada pada `tmp/wireless-workflow-release/`: build receipts,
`backend-review.md`, `e2e/final-verification-report.json`,
`browser-output/browser-evidence.json`, dan `app-activation.json`. QA PDF berada
di `tmp/pdfs/gld-workflow-manual/final-qa.json`. Seluruh keterbatasan tersebut
tetap terpisah dari status build dan pengujian PC yang sudah selesai.
