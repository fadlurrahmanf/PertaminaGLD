# GLD2 nulling — temuan live COM3 (2026-08-19)

## Lingkup dan bukti

- Perangkat: GLD2 pada `COM3`, ESP32-S3 MAC `44:b1:76:d7:28:14`.
- Firmware: environment `gld_v2` versi `0.8.18`; image aplikasi berhasil di-flash dan diverifikasi oleh esptool.
- Ini adalah hasil uji runtime pada board tersebut, bukan hanya pembacaan skematik.

## Urutan header yang dipakai firmware GLD2

| Header | Sensor | EN (PCF8574) | TCA channel | ADS channel |
|---|---|---:|---:|---:|
| H2 | MQ8 | EN0 | 7 | 0 |
| H1 | MQ135 | EN6 | 6 | 1 |
| H3 | MQ3 | EN7 | 5 | 2 |
| H4 | MQ5 | EN3 | 4 | 3 |
| H5 | MQ4 | EN4 | 3 | 4 |
| H6 | MQ7 | EN5 | 2 | 5 |
| H7 | MQ6 | EN2 | 1 | 6 |
| H8 | MQ2 | EN1 | 0 | 7 |

## Temuan dan hasil

| Item | Hasil live | Makna |
|---|---|---|
| Root I2C | `0x20`, `0x44`, `0x71` terdeteksi | PCF8574, SHT40, dan TCA9548A merespons di bus utama. |
| TCA dengan semua sensor ON | `tcaOk=true`, PCF output mask `0xFF` | Menyalakan semua sensor tidak dengan sendirinya menghilangkan ACK `0x71`. |
| MCP per cabang | Semua delapan cabang menemukan `0x60` saat EN dan channel TCA pasangannya dipilih satu per satu | Jalur I2C setiap MCP dapat dijangkau dengan pasangan header/EN/TCA yang benar. |
| Kontrol DAC | `mcpControlOkCount=8`, `dacReady=true` | Kedelapan MCP dapat menerima perintah DAC pada uji kontrol. |
| Nulling | `NULLING_SERVICE_DONE status=Ok successCount=8/8` | Kalibrasi nulling delapan kanal selesai. |
| Penyimpanan profil | `NULLING_NVS_SAVE=OK profileId=1` | Hasil nulling tersimpan. |
| Boot setelah nulling | `BOOT_NULLING_PROFILE_APPLY=OK profileId=1`, mode `inference` | Profil yang tersimpan berhasil diterapkan kembali setelah reboot. |

## Perubahan perilaku firmware yang membuat nulling berhasil

Setiap penulisan MCP sekarang:

1. mematikan seluruh switch TPS22919;
2. menyalakan tepat satu EN milik sensor tujuan;
3. memilih channel TCA pasangan sensor tersebut;
4. menulis MCP `0x60`;
5. melanjutkan ke sensor berikutnya.

Ini diperlukan karena seluruh MCP memakai alamat I2C yang sama (`0x60`). Pemilihan TCA saja belum cukup bila jalur modul lain masih aktif atau mask TCA sebelumnya tersisa.

## Catatan yang belum boleh disalahartikan

- `mcpOkCount` pada boot pernah tampil `7/8` walau uji DAC dan nulling berikutnya sukses `8/8`. Nilai boot tersebut adalah probe diagnostik, bukan bukti bahwa satu MCP tidak dapat dikendalikan. Bukti yang lebih kuat adalah `mcpControlOkCount=8` dan `successCount=8/8` saat nulling.
- Model inferensi saat ini belum valid karena binding profil model terhadap profil nulling masih belum dibuat (`modelProfileReady=false`, `bindingValid=false`). Ini terpisah dari keberhasilan nulling.
- Perintah diagnostik manual `RUN_TCA_CHANNEL_SCAN` pada uji sebelumnya pernah menyebabkan `stack overflow in task loopTask`; perintah tersebut tidak dipakai oleh boot dan nulling yang sukses di atas dan masih perlu diperbaiki sebelum dipakai lagi.
