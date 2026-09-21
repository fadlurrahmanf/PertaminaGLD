# GLD3 COM3 — hasil upload dan uji bench, 17 September 2026

## Kesimpulan

**Upload berhasil dan isi flash terverifikasi. Uji seluruh fungsi belum lulus.**
Delapan DAC dan jalur ADC memberi respons saat diuji dengan satu rail sensor aktif.
Pada kondisi semua rail ON, akses I2C/MCP tidak konsisten dan sweep gagal sebagian.
Board belum dinyatakan siap digunakan sebagai detektor gas.

## Identitas dan paket

- Port: COM3, USB-SERIAL CH340 (`VID_1A86`, `PID_7523`).
- Chip saat flash: ESP32-S3 rev v0.2; MAC `44:b1:76:a8:0d:80`.
- Flash terdeteksi 16 MB; embedded PSRAM 8 MB. Ini identifikasi, bukan stress test memori.
- Runtime: `GLD3 WROOM-1U-N16R8`, firmware `0.8.30`, protokol `0.2.0`.
- ID default runtime: GLD `0x1001`, target CH `0x0010`; tidak diubah dalam pengujian.
- Paket: `apps/operator-hub/firmware-packages/gld_v3/latest`.
- SHA-256 firmware: `9238221e0af98a466e750897785c2b9f2cd0cee4ed33e63de759cd4807360f13`.
- Menggunakan paket retained yang hash-nya cocok, tidak rebuild dari working tree sekarang. Paket mencatat dirty source; environment GLD3 pada source aktif telah berubah. Ini hasil bench untuk binary tersebut, bukan bukti release dapat direproduksi dari source sekarang.

## Upload dan pemulihan

Boot awal mengulang `invalid header: 0xffffffff`. Cadangan 64 KiB pertama berhasil
dibaca dan seluruhnya `0xFF`, termasuk area bootloader/partisi/NVS. Backup penuh
16 MB tidak berhasil; jangan menganggap tersedia backup seluruh chip.

Transfer firmware utuh terputus pada 115200 dan 230400 baud. Pemulihan dilakukan
dengan delapan blok 128 KiB (blok terakhir lebih pendek) dari binary yang sama;
blok terakhir berhasil setelah pengulangan pada 115200 baud. Setelah itu,
`verify_flash` memverifikasi keempat berkas lengkap dengan hasil digest cocok:
bootloader, partisi, boot_app0, dan firmware. Penyebab pasti terputusnya transfer
belum diukur pada hardware. Tidak dilakukan erase seluruh chip.

Bukti: `upload.log`, `upload-retry-230400.log`, `upload-block-*.log`,
`upload-block-07-retry.log`, `verify-flash.log`, `preflash-boot-nvs.bin`.

## Matriks hasil

| Fungsi | Hasil dan batas bukti |
|---|---|
| Upload, boot, serial | Lulus: empat digest cocok, APP_PING ACK, identitas GLD3/v0.8.30 sesuai. |
| ADC delapan kanal | Respons langsung diperoleh pada delapan target isolated; bukan bukti akurasi atau sensitivitas gas. |
| PCF8574 / sensor power | Perintah mask all-off, satu kanal, dan all-on diterima. Pola mask sesuai EN mapping. Tidak mengukur tegangan/heater secara eksternal. |
| MCP4725 isolated | Boot edge-write 8/8; session write/readback 0 berhasil 8/8; direct sweep isolated berhasil 8/8. |
| I2C/MCP semua rail ON | **Gagal**: current-state dua sesi menunjukkan 5/8, tiga kanal terakhir tidak ACK. TCA sempat NACK pada manual scan. |
| Sweep DAC semua rail ON | **Gagal sebagian**: MQ8/MQ135/MQ3 berhasil; MQ5 gagal high-write/restore; MQ4/MQ7/MQ6/MQ2 gagal write/restore. |
| SHT40 | Terdeteksi dan sampel valid berubah; sekitar 37 C / 30% RH pada sesi akhir. Tidak diuji terhadap alat referensi. |
| Alarm | MANUAL ON sekitar 2 detik, OFF, lalu AUTO: semua ACK dan perubahan status sesuai. Bunyi/lampu/tegangan fisik belum dikonfirmasi. |
| Fan GPIO7 | Firmware tersedia, runtime mendeteksi eksternal/24 V; putaran fisik belum dikonfirmasi. |
| LoRa | Inisialisasi radio berhasil; tidak ada bukti TX/RX end-to-end. AES key belum diprovisi, counter TX=0. |
| RS485 | Modbus slave ready, unit 1, 9600 8N1. Belum diuji dengan master/transceiver/kabel eksternal. |
| Nulling dan model | Belum dijalankan: tidak ada profil nulling/binding, `inferenceValid=false`. Menunggu konfirmasi udara bersih dan kondisi sensor. |
| Wi-Fi/MQTT/dataset | Belum dikonfigurasi/diuji; runtime masih placeholder dan config invalid. Tidak memakai kredensial asumsi. |
| Baterai / power switching / tombol / watchdog | Belum diuji fisik; baterai tidak terdeteksi pada status. Tidak mengirim perintah yang sengaja memutus suplai. |

## Respons analog isolated

Metode: semua rail OFF, hidupkan satu target, jalankan direct ADS/MCP sweep,
nilai hanya baris target, tulis/baca balik target ke 0, lalu matikan rail target.
Tujuh kanal yang tidak diberi daya boleh NACK dan tidak dinilai pada sweep tersebut.
Semua delapan baris target memiliki `write0=1`, `write4000=1`, `restoreOk=1`,
`st0=Ok`, `st4000=Ok`, dan zero readback berhasil.

| CH | Header | Sensor | V pada kode 0 | V pada kode 4000 | Delta V |
|---|---|---|---:|---:|---:|
| 0 | H2 | MQ8 | 0.001794 | 2.677214 | 2.675421 |
| 1 | H1 | MQ135 | 0.001388 | 2.394232 | 2.392844 |
| 2 | H3 | MQ3 | 0.001911 | 1.541393 | 1.539482 |
| 3 | H4 | MQ5 | 0.001625 | 2.464304 | 2.462679 |
| 4 | H5 | MQ4 | 0.002759 | 2.558357 | 2.555598 |
| 5 | H6 | MQ7 | 0.002405 | 2.239059 | 2.236654 |
| 6 | H7 | MQ6 | 0.001983 | 2.884610 | 2.882627 |
| 7 | H8 | MQ2 | 0.179560 | 3.033124 | 2.853565 |

Ini respons rangkaian terhadap DAC, bukan hasil nulling, kalibrasi konsentrasi gas,
uji selektivitas, atau jaminan linearitas. Terutama nilai kode 0 tidak berarti
semua kanal sudah berada pada nol volt. Sampel moving-average pada uji pendahuluan
`isolated-analog-results.json` tidak digunakan sebagai acceptance analog;
hasil langsung ada di `isolated-direct-results.json` dan `isolated-direct.log`.

## Temuan yang harus ditindaklanjuti

1. Isolated berhasil, all-on gagal: bukan bukti ketiga modul hilang/rusak permanen.
   Current-state tidak menemukan MQ7/H6 (mux2), MQ6/H7 (mux1), MQ2/H8 (mux0),
   sementara isolated menulis dan membaca ketiganya dengan benar. Penyebab fisik
   tepat antara kondisi bus, cabang TCA, atau rail/load belum dibuktikan.
2. Marker firmware `ADS_MCP_SWEEP_DONE status=ok` bukan acceptance seluruh kanal.
   Log memiliki marker tersebut walaupun beberapa `RESULT ok=0` dan restore gagal.
3. Setelah rangkaian diagnostik, scan reguler sempat `allValid=0`, telemetri invalid,
   dan ADS recovery aktif. Dilakukan satu `RESTART` terkendali untuk membersihkan
   state sesi. Pada uptime 32.098 detik, telemetri kembali valid, delapan status ADC
   = 0/OK, tegangan sekitar 1.42–2.28 V; scan tetap allValid=1/primed=1 hingga
   akhir rekaman sekitar 48 detik. Ini bukan bukti masalah all-on telah hilang.
   Hasil final dicatat di `restart-and-final.log`.
4. `gasName=CO2` bersama confidence 0 / inference invalid adalah output tidak valid,
   **bukan bukti deteksi CO2**. Jangan memakai board untuk alarm keselamatan saat ini.
5. Readback DAC isolated membuktikan nilai saat dibaca. Perpindahan rail dapat
   memuat ulang nilai EEPROM; tidak mengklaim nilai volatile tetap tersimpan setelah
   rail dimatikan/dihidupkan. Pengujian tidak menulis profil nulling atau binding.

## Handoff

Perintah uji selesai dengan rail diminta all-on (`0xFF`), alarm AUTO/OFF, dan
serial ditutup. Sesudah restart, verifikasi DAC sesi sebelumnya tidak dianggap
masih berlaku (`dacVerified=false`); profil nulling tetap kosong dan inference
tetap invalid. Uji elektronik tidak menggantikan pengamatan fisik fan/alarm,
fixture CH/RS485, udara bersih untuk nulling, serta pengujian gas terkontrol.
Belum ada perubahan implementasi firmware untuk memperbaiki temuan ini.
Prioritas berikutnya adalah diagnosis I2C/DAC saat semua rail ON dan regresi
scan ADC, kemudian nulling/binding dan pengujian end-to-end dengan fixture.
