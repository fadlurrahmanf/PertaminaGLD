# GLD3 v0.8.31 — perbaikan diagnostik dan uji COM7

Tanggal: 17 September 2026. Status: patch diagnostik terpasang dan lulus uji yang dirinci di bawah; **bukan pernyataan seluruh perangkat bebas masalah atau siap deteksi gas**.

## Firmware dan perangkat

- Target `gld_v3`, runtime `GLD3 WROOM-1U-N16R8`, versi `0.8.31`.
- COM7, ESP32-S3 rev v0.2, MAC `44:b1:76:a8:0d:80`, flash 16 MB, PSRAM 8 MB.
- ID GLD `0x1001`, target CH `0x0010`, catu terdeteksi 24 V.
- Paket final: `apps/operator-hub/firmware-packages/gld_v3/latest/`.
- Firmware binary 1.047.648 byte; slot aplikasi 6.553.600 byte. Laporan linker: 1.047.277 byte flash dan 136.000 byte RAM statis.
- SHA-256 firmware final: `c30fede0822b4b116883a96df70535452c57406ab5ccfaee2ac26f916970cbdb`.
- SHA-256 manifest final: `eff8873647848a5a123cdb60565b17929423338dc89f091b73727c3fea12d04e`.
- Snapshot firmware: `2aa45780cd6881ce465eac65718b9d781a9152cd97997220c098ebc97c1f9a0a`.

## Yang diperbaiki

1. `RUN_ADS_MCP_SWEEP` GLD3 mengakses satu rail sensor pada satu waktu. DAC dibaca balik pada kode 0, 4000, dan baseline yang dipulihkan; hasil akhir merupakan agregasi hasil kanal dan pemulihan daya.
2. Boot MCP control mengembalikan baseline setiap kanal dan memverifikasi readback, bukan meninggalkan kode uji tinggi.
3. Kegagalan salah satu sampel ADC tidak lagi tertutup oleh sampel terakhir yang berhasil.
4. `RUN_CURRENT_STATE_CHECK` diberi label observational. Hasil scan kondisi semua rail aktif tidak menimpa hasil boot terisolasi.
5. Sweep ditolak saat ada override DAC sementara, mode bukan inference, atau catu eksternal tidak tersedia. Setelah rail diputus/diaktifkan kembali, verifikasi runtime lama dan moving average di-invalidasi.
6. Pada board tanpa profil nulling, reset nol yang tidak dapat dijamin bertahan melewati power-cycle di-skip secara eksplisit: `SKIP_UNSAFE_VOLATILE_NO_PERSIST`. Tidak dibuat kalibrasi nol fiktif dan tidak ditulis kode uji ke EEPROM.
7. Detail log dipecah agar tidak terpotong oleh buffer 256 byte. Perbaikan log diuji dengan `snprintf` C++ aktual.

Baseline pada uji ini adalah nilai **setelah rail tunggal diaktifkan** (`isolated_power_on`), bukan klaim bahwa semua nilai volatile pra-isolasi dapat dipertahankan. MCP memuat ulang nilai nonvolatile ketika catu kembali. Setelah mask akhir dipulihkan, readback per-kanal sebelumnya tidak dipresentasikan sebagai verifikasi live semua rail; status verifikasi di-invalidasi. Jalur pemulihan profil tersimpan yang sudah ada tetap dipertahankan.

## Bukti yang lulus

- Build `gld_v3` berhasil; 22 tes host lulus, termasuk injeksi kegagalan sampel ADC C++, pemilihan GPIO7 fan, batas log, dan perbandingan hasil preprocessor GLD1/GLD2 dengan baseline.
- Empat image flash lengkap lulus `verify_flash`: bootloader, partitions, boot_app0, firmware.
- NVS `0x9000..0xDFFF` identik sebelum upload dan sesudah penulisan/sebelum boot normal. SHA-256: `8334130951c93003722cefb019c570cc70a091ce121f133a9bf099f758b12fbc`.
- Identitas serta konfigurasi yang dilaporkan `GET_INFO` tetap sama setelah restart akhir.
- Dua sweep berturut-turut pada binary final: **8/8 lulus pada masing-masing sweep**; tidak ada reset selama sweep.
- Semua 16 hasil kanal mempunyai readback DAC 0 dan 4000 yang cocok; pemulihan baseline 2048 cocok. Baseline berulang sama pada sweep kedua.
- Respons analog teramati pada semua kanal, delta sekitar **2,547–3,156 V**. Pemeriksaan bench `abs(delta) > 0,05 V` hanya mendeteksi perubahan listrik yang nyata; bukan spesifikasi toleransi/akurasi gas. Firmware sendiri melabeli `analogResponse=not_graded`.
- Mask PCF sebelum/sesudah setiap sweep `0xFF`; readback akhir cocok. Ini bukti port PCF, bukan pengukuran langsung seluruh tegangan TPS22919.
- Tes negatif: pengaturan DAC sementara kanal 0 ke baseline 2048 diikuti sweep menghasilkan `blocked reason=active_session_mcp_override`. Board direstart sesudahnya; tidak ada override yang ditinggalkan.
- Boot akhir MCP discovery/control 8/8; ADC delapan kanal valid, SHT40 valid; alarm AUTO dengan perintah output OFF.
- Verifier bench: 16/16 pemeriksaan lulus. Source firmware main dan paket non-GLD3 tidak berubah: 1.016 hash file yang dilindungi tetap sama.

## Yang masih belum selesai / tidak terbukti

- Scan **semua rail aktif** tetap menemukan MCP **5/8**, sedangkan uji terisolasi 8/8 lulus. Kondisi ini belum diperbaiki secara fisik; bukan bukti cukup bahwa tiga MCP rusak. Kesamaan alamat 0x60 saja tidak membuktikan benturan, karena perangkat dipisahkan TCA.
- Flashing masih mengalami `chip stopped responding`/gangguan serial, termasuk pada 115200 baud. Upload final selesai melalui blok 128 KiB dan pengulangan, lalu diverifikasi lengkap. Penyebab fisik/USB/watchdog belum dipastikan; jangan menyebut masalah upload sudah hilang. Kecepatan nominal manifest bukan bukti full-image upload stabil pada board ini.
- Profil nulling masih tidak ada (`activeNullingProfileId=0`); inference tetap tidak valid/fail-closed. Tidak dilakukan nulling, binding model, clean-air acknowledgement, atau uji gas karena kondisi udara bersih belum dikonfirmasi.
- Tidak membuktikan RF end-to-end, MQTT/backend, RS485 dengan master eksternal, perpindahan daya baterai, atau gerakan fan/alarm fisik. `radioReady`/`modbusReady` bukan bukti komunikasi eksternal.

## Source, backup, dan pengulangan

Source ada di worktree terpisah `D:/Github/PertaminaGLD-GLD3-Diagnostics`, branch `codex/gld3-diagnostics`, base `dfba98f237b6b1f83c139f49e0e8a1c2e683e5af`. Tidak dilakukan commit/push. Source main yang berisi pekerjaan GLD1 sengaja tidak ditimpa; jangan membangun GLD3 dari source main yang belum memiliki integrasi ini.

Arsip perubahan source: `docs/wiring/GLD3-v0.8.31-source-changes.zip`. Arsip berisi tujuh file yang berubah/baru, diff tracked, dan petunjuk base; bukan repository lengkap. Jangan overlay sembarang pada dirty main.

Build dari folder `firmware/` worktree: `pio run -e gld_v3 -j 1`. Pada Windows, build pertama gagal karena response-file linker di TEMP. Build berhasil dengan TEMP/TMP/TMPDIR proses diarahkan ke path lokal berseparator `/`: `D:/Github/PertaminaGLD/tmp/gld3-diagnostics-20260917/link-temp`.

Paket GLD3 v0.8.30 sebelumnya dicadangkan di `tmp/gld3-diagnostics-20260917/previous-gld3-0.8.30/`. Percobaan v0.8.31 pertama dengan log terpotong juga disimpan, terpisah dari binary final. Tidak dilakukan full-chip erase atau reset konfigurasi/NVS.

Bukti final berada di `tmp/gld3-diagnostics-20260917/r2/`: `build.log`, `host-tests.log`, `upload-summary.json`, `verify-all-four.log`, `backup.log`, `read-nvs-after.log`, `postflash-runtime.log`, `sweep-twice.log`, `observation.log`, `guard-and-restart.log`, `final-status.log`, dan `bench-verdict.json`. Script verifikasi/publikasi ada satu tingkat di atasnya. Semua sesi COM7 telah ditutup setelah uji; board dibiarkan menjalankan firmware final.
