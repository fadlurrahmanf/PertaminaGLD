# GLD3 — upload ulang COM7, 17 September 2026

**Hasil: berhasil.** Paket yang sama di-upload ulang tanpa perubahan kode diagnostik.

- Identitas chip terverifikasi: ESP32-S3 rev v0.2, MAC `44:b1:76:a8:0d:80`, flash 16 MB.
- Paket `gld_v3`, firmware `0.8.30`, runtime `GLD3 WROOM-1U-N16R8`.
- SHA-256 aplikasi: `9238221e0af98a466e750897785c2b9f2cd0cee4ed33e63de759cd4807360f13`.
- Empat image lengkap lulus `verify_flash`: bootloader, partitions, boot_app0, firmware.
- Area NVS `0x9000..0xDFFF` dibandingkan sebelum boot normal: identik byte-per-byte.
- Tidak ada erase seluruh flash, perubahan konfigurasi, nulling, binding, atau perubahan source firmware.
- Transfer dilakukan per blok; blok aplikasi terakhir memerlukan satu pengulangan karena error saat upload stub. Percobaan ulang dan verifikasi lengkap berhasil.

## Pemeriksaan setelah boot

- APP_PING: ACK OK; GET_INFO/GET_STATUS/GET_TELEMETRY merespons.
- ID GLD `0x1001`; target CH `0x0010`.
- Boot isolated MCP discovery dan DAC control: 8/8.
- Pada uptime 57.819 detik, telemetry valid, seluruh 8 status ADC = 0/OK; tegangan sekitar 1.35–2.21 V.
- SHT40 valid; mask daya sensor `0xFF`; alarm AUTO dengan output OFF.
- Profil nulling tetap kosong (`0`), inference invalid. Belum siap dinyatakan lulus deteksi gas.
- COM7 ditutup setelah pemeriksaan. Tidak ada monitor/upload yang ditinggal berjalan.

Ini verifikasi upload dan boot, bukan pengujian ulang seluruh fungsi, RF, RS485, fan/alarm fisik, atau perbaikan diagnostik all-on.

Bukti: `upload-summary.json`, `verify-all-four.log`, `backup.log`, `read-nvs-after.log`, `chip-identity.log`, dan `postflash-runtime.log` dalam folder ini.
