# Model 1 Replay - paket password operator

Status 2026-11-02: compile dan paket Hub selesai; **belum diupload ke GLD**. Pengguna akan melakukan upload dan uji sendiri. Password yang dipilih pengguna disimpan hanya di konfigurasi privat/build, tidak dicantumkan pada dokumen atau manifest ini. Password firmware lama masih berlaku sampai upload baru selesai.

## Perubahan dan perlindungan

Preparer Replay sekarang menerima credential lokal eksplisit sepanjang 8..63 karakter. Password acak default, aturan karakter dan penolakan rotasi diam-diam tidak diubah. Dua test fixture tambahan memastikan credential delapan karakter dipertahankan serta panjang 7/64 ditolak tanpa overwrite; 18 test source/credential lulus. Implementasi pembacaan sensor, buffer/replay, backend/UI dan pin/model/nulling tidak diubah.

Hanya Model 1 Replay dibuild. Build memakai cache tanpa perintah clean, tetapi SCons membangun ulang sejumlah dependency. Hasil sukses 17:40:02-17:41:40 WIB, PIO 96,935 detik, nol warning, RAM 162.912/327.680 byte (49,7%). Binary 1.047.008 byte, SHA256 `792638eb8af70252b02b6a0887a651e01f0df58950b6c5b123bb688fa70cb2b6`.

Credential lama dibackup privat; kecocokan credential pilihan, header dan binary diperiksa melalui boolean tanpa mengekspos nilai. Binary baru tidak mengandung credential lama. Model blob 9.632 byte sesuai source dan tidak berubah. Tiga image boot/partition identik dengan paket lama; NVS tetap offset 0x9000 + 0x5000 dan tidak bersinggungan dengan wilayah flash paket.

## Paket yang disediakan

- Env: `gld_model_1_dataset_replay_wifi`, firmware GLD1 v0.8.36.
- Artefak bernama: `firmware/.pio/artifacts/gld-dataset-replay-wifi-20261102-operator-password/gld_model_1_dataset_replay_wifi/`.
- Paket Hub: `apps/operator-hub/firmware-packages/gld_model_1_dataset_replay_wifi/latest/`.
- Paket Hub sebelumnya disimpan utuh pada sibling `previous-20261102-before-operator-password/`; artefak asli bernama tanggal sebelumnya tetap utuh.
- Manifest final SHA256 `ece0dda563d31df889a0bb9b6cc873d50e1a6d70c403c8951a51183a85a8f8ec`.

Strict child/Hub/preflight validation lulus. Endpoint nyata bridge mengembalikan manifest versi/hash yang sama dan keempat binary cocok. Semua paket model lain dan sepuluh source runtime/config yang dilindungi tetap sesuai baseline. Tidak ada restart service, akses COM, perubahan Wi-Fi, reset NVS atau upload dalam pekerjaan ini.

Pemeriksaan semantik menemukan generator awal memakai label versi GLD bersama 0.8.30. Manifest diperbaiki memakai header GLD1 0.8.36 sebelum handoff; dialog ditutup selama koreksi dan tidak ada upload. Binary dan hasil compile tidak berubah karena perbaikan label.

## Upload dan uji mandiri

1. Buka Hub -> GLD -> Expert Console -> Firmware Upload. Jalur Expert diperlukan karena firmware hotspot khusus tidak menyediakan identifikasi serial untuk wizard biasa.
2. Firmware environment GLD1; Model **GLD1 Model 1 - Hotspot buffer 5 menit (tahap 2)**; COM7; target ID pada formulir 1002; **Reset NVS OFF**. Formulir sudah disiapkan tanpa mengirim Inject ID.
3. Klik Upload sendiri. Jika diminta, buat/masukkan PIN lokal operator. PIN aplikasi berbeda dari password hotspot.
4. Setelah flash selesai, sambungkan laptop ke GLD-DATASET-1002 menggunakan password baru yang disepakati. Jika Windows menyimpan credential lama, Forget jaringan GLD tersebut lalu sambungkan lagi. Hotspot tidak menyediakan Internet.
5. Dataset -> Buffer 5 menit tahap 2 -> isi password baru -> Connect GLD -> ready -> Start Wireless. Pastikan delapan sensor dan jumlah sampel bertambah; Stop -> complete -> Download CSV.

Bukti: `tmp/wireless-password/model1-build-receipt.json`, `package-placement.json`, `live-package-check.json`, `operator-upload-ready.png`, dan artefak `offline-package-validation.json`. [Tracker paket](../GLD-WIRELESS-PASSWORD-PACKAGE-TRACKER.md). Bukti uji fisik tahap 2 sebelumnya tetap historis untuk binary lama; revisi password ini belum memiliki hasil uji fisik baru.

Kelanjutan 18:11 WIB: [Model 2 dan 3 juga selesai dibuild paralel dan paket Hub diperbarui](../GLD-WIRELESS-MODEL23-PASSWORD-TRACKER.md). All three Replay packages match the same operator-selected credential. Upload pengguna pada 17:58 tercatat berhasil secara HTTP, tetapi bukti serial/UI saat diagnosis menunjukkan firmware inference/LoRa normal. Pilihan formulir sebelumnya pada Chrome terpisah dari panel Codex yang disiapkan. Root kini menyiapkan **tab Chrome pengguna** dengan Model 1 Replay/COM7/target1002/NVS OFF, tanpa menekan Upload. Jangan menganggap revisi Replay sudah terpasang sampai upload paket khusus dan verifikasi hotspot selesai.
