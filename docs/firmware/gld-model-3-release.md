# Model 3 - Board 3: siap upload melalui Operator Hub

Diterbitkan 2026-09-29 dari `C:/Users/MSI/Downloads/BOARD GLD 3.zip`. Targetnya **Model 3 pada board GLD/GLD1**, environment `gld_model_3`, bukan board GLD3 (`gld_v3`). Pengguna menyetujui basis GLD1 aktif v0.8.38 dan mengaktifkan inferensi untuk uji board setelah nulling/bind. Ini bukan pernyataan bahwa akurasi deteksi gas sudah tervalidasi.

## Cara upload

1. Buka ulang Operator Hub agar backend terbaru dimuat; refresh halaman Simple Hub atau Expert Console dengan Ctrl+F5.
2. Pilih **GLD1**, lalu **Model 3 - Board 3**. Periksa paket `gld_model_3` versi **0.8.38**.
3. Simpan konfigurasi/provisioning yang diperlukan. Pilih COM board yang benar dan centang **Reset NVS** secara eksplisit. Tindakan ini menghapus konfigurasi, hasil nulling dan binding; default device ID adalah 1001.
4. Jalankan upload sendiri, lalu pulihkan konfigurasi/provisioning yang benar. Jalankan full nulling dalam udara bersih yang dipastikan, syarat **8/8 pass**, kemudian **Bind Model**.
5. Periksa versi firmware 0.8.38, penanda `GLD1_BASE_COMMIT=69a493c`, dan profil model `cnn-dualbranch-board-3-2class-v1`. Pemilihan paket saja tidak membuktikan firmware itu sudah berjalan pada board.
6. Lakukan uji penerimaan board/gas sebelum penggunaan operasional. Kelulusan build, host inference, dan upload tidak membuktikan akurasi deteksi gas.

## Model dan asal build

- INT8 dual-input: 8 kanal ADC + 7 evidence; 2 keluaran `Clean_Air, LPG`, dipetakan ke protocol `{0, 1}`. Model ini tidak memiliki keluaran H2 tersendiri.
- Model 9.632 byte; profil model/scaler `cnn-dualbranch-board-3-2class-v1` membedakannya dari model lama dan memerlukan binding baru.
- Tiga header weights/normalisasi/sensitivitas disalin persis dari ZIP ke nama kanonik dalam `firmware/gld/models/model_3/`. `.keras`, notebook dan data pelatihan tidak dikompilasi ke firmware. Adapter simbol, metadata kelas/profil, build dan publikasi paket juga diperlukan; mengganti header saja tidak memperbarui paket Hub.
- ZIP SHA-256: `ac63f96a4a375c644933c3528322df6db35acd14b57a55671e395ec551cf7602`.
- Model INT8 SHA-256: `ec636bb559dec26acdf5d5ebe3a4f75dc6644023d9e483b42b1e53d9518c9890`.
- Firmware SHA-256: `a9cf9cde9d5507b21ae05513d4638d4e10f200d5099e8ebfb23d9773edaed81a`.
- Build hanya `gld_model_3` dari `D:/Github/PertaminaGLD-GLD1-69a493c`, branch `codex/gld1-69a493c-alarm`, base `69a493c32d2500134a21e029820cd4addea1794a`. Runtime/nulling/alarm tidak diubah. **Jangan rebuild rilis ini dari main firmware/** yang memiliki baseline berbeda.
- Model3 sebelumnya v0.8.34; migrasi ke v0.8.38 ini disetujui pengguna. Nulling mempertahankan settle 5 ms dan algoritme asli tanpa warm-up nulling 30 detik; 5 ms bukan durasi total nulling.
- Ukuran `firmware.bin` 1.021.216 byte; RAM 134.056/327.680 byte; penggunaan flash aplikasi 1.020.837/6.553.600 byte.
- Paket aktif: `apps/operator-hub/firmware-packages/gld_model_3/latest/`. Empat flash image, manifest dan checksum tervalidasi; `model-provenance.json` adalah bukti asal/hash dan tidak di-flash.

## Guard migrasi dan bukti verifikasi

Guard hanya berlaku untuk `gld`, `gld_model_1`, atau `gld_model_3` versi 0.8.38 dengan base commit penuh di atas. Backend mewajibkan persetujuan Reset NVS sebelum serial digunakan, lalu menghapus hanya region NVS terverifikasi `0x9000/0x5000` dengan `--after no_reset`; write memakai `--before no_reset`, baru reset normal setelah sukses. Model3 lama v0.8.34 dan paket lain tetap mengikuti perilaku sebelumnya. Jika flash gagal setelah erase, konfigurasi sudah hilang dan perlu pemulihan.

Build, uji baseline/alarm, 68 tes backend Hub, regresi executable UI Simple Hub/Expert, validator upload aktual, hash seluruh image dan kecocokan binary terhadap build/ZIP lulus. TFLM dan NeuralNetwork asli berhasil AllocateTensors/Invoke empat vektor sintetis pada host dalam arena 40 KiB. HTTP handler aktual serta proxy Hub berhasil mengambil paket terbit dengan byte yang benar. Server uji loopback ditutup sesudahnya; tidak ada service persisten yang dijalankan/restart.

Seluruh 1.052 file firmware/paket lain yang dilindungi di main tetap cocok dengan hash awal, termasuk Model1/2. Dari 867 file firmware release yang dilindungi, hanya packaging hook dan allowlist tes baseline yang diizinkan berubah. ZIP Model2 baru belum dipublikasikan oleh pekerjaan ini. Tidak ada akses COM, upload fisik, erase NVS, reset board, uji gas, commit atau push.

Backup model/paket lama dan bukti uji: `tmp/model3-20260929/`. Ulangi pemeriksaan paket/HTTP dari main dengan `C:/Users/MSI/.platformio/penv/Scripts/python.exe tmp/model3-20260929/verify_model_release.py --published`; tes UI dengan `node apps/operator-hub/tests/test_model3_upload_ui.cjs`.
