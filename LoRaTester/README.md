# LoRaTester

Firmware khusus pengujian; tidak menjalankan fungsi mesh atau alarm CH operasional.

## Versi firmware

- `V1/CH` dan `V1/Display`: salinan checkpoint `5331e482`; lokasi referensi build disesuaikan setelah dipindah ke subfolder.
- `V2/CH` dan `V2/Display`: pengembangan terpisah untuk kesiapan CH, baterai, dan tampilan baru. Ketiga perangkat harus memakai V2 bersama; protokol V2 tidak kompatibel dengan V1.
- `CH/` dan `Display/`: direktori sebelumnya tetap disimpan dan tidak diganti oleh versi baru.

V2 telah disiapkan untuk uji perangkat, tetapi pembacaan baterai dinonaktifkan sampai rangkaian dan kalibrasi masing-masing perangkat diverifikasi. Lihat `V2/CH/README.md` dan `V2/Display/README.md` untuk wiring, build, dan batasannya. V2 CH mengirim polling LoRa otomatis ketika idle; belum dibuktikan aman terhadap perangkat produksi di lingkungan nyata. Build tidak melakukan upload.

- `CH/`: firmware CH1 (`lt_ch1`) dan CH2 (`lt_ch2`).
- `Display/`: monitor ESP32 GC9A01 dan tombol GPIO22.
- Area casing display: X=123, Y=120, radius=116.

Proyek CH menggunakan codec AppFrame, definisi pin, dan RadioLib dari `firmware/` tanpa mengubah firmware operasional. Display menggunakan LovyanGFX lokal yang telah tersedia di `tft_gc9a01_test/.pio/libdeps/esp32dev`; siapkan library tersebut bila membangun di mesin lain.

Firmware ini prototipe bench. Paket dummy bertipe khusus masih bisa diteruskan gateway produksi; gunakan lingkungan RF terisolasi. Format AppFrame dummy mewakili framing dan contoh ukuran, bukan keseluruhan protokol atau perilaku jaringan produksi. Kedua arah bergiliran pada satu kanal, dan hasil arah balik diperbarui saat paket balik diterima.

Jangan hapus konfigurasi NVS ketika upload. Versi baru harus diuji timing, kehilangan paket, START/STOP dan pemulihan pada perangkat sebelum digunakan untuk pengukuran lapangan.

Pada firmware V1, ringkasan PDR memberi indikasi STABIL bila tiap arah memiliki minimal 10 sampel, rentang RSSI maksimal 6 dB, dan rentang SNR maksimal 3 dB. Ambang V2 dijelaskan di `V2/README.md`. Ini ambang tampilan praktis, bukan standar atau jaminan kualitas tautan; nilai min/maks sensitif terhadap spike.

Pencarian CH1 baru: bila CH1 lama offline sekurangnya 15 detik dan sesi terakhir aman/idle, pilih ulang mode tes pada display agar peer baru dapat terdeteksi. Saat sesi aktif atau status STOP belum pasti, peer tidak diganti otomatis. ESP-NOW pada alat ini belum diautentikasi.
