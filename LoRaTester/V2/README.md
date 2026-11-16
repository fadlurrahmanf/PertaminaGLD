# LoRaTester

Firmware khusus pengujian; tidak menjalankan fungsi mesh atau alarm CH operasional.

- `CH/`: firmware CH1 (`lt_ch1`) dan CH2 (`lt_ch2`).
- `Display/`: monitor ESP32 GC9A01 dan tombol GPIO22.
- Area casing display: X=123, Y=120, radius=116.

Proyek CH menggunakan codec AppFrame, definisi pin, dan RadioLib dari `firmware/` tanpa mengubah firmware operasional. Display menggunakan LovyanGFX lokal yang telah tersedia di `tft_gc9a01_test/.pio/libdeps/esp32dev`; siapkan library tersebut bila membangun di mesin lain.

Firmware ini prototipe bench. Paket dummy bertipe khusus masih bisa diteruskan gateway produksi; gunakan lingkungan RF terisolasi. Format AppFrame dummy mewakili framing dan contoh ukuran, bukan keseluruhan protokol atau perilaku jaringan produksi. Kedua arah bergiliran pada satu kanal, dan hasil arah balik diperbarui saat paket balik diterima.

Jangan hapus konfigurasi NVS ketika upload. Versi baru harus diuji timing, kehilangan paket, START/STOP dan pemulihan pada perangkat sebelum digunakan untuk pengukuran lapangan.

Ringkasan PDR menilai setiap arah secara terpisah: minimal 10 sampel, STABIL jika rentang RSSI ≤15 dB dan rentang SNR ≤5 dB, BERFLUKTUASI jika salah satu melampaui batas, dan DATA KURANG jika sampel kurang atau hasil belum final. Ini ambang tampilan praktis, bukan standar atau jaminan kualitas tautan; nilai min/maks sensitif terhadap spike.

Pencarian CH1 baru: bila CH1 lama offline sekurangnya 15 detik dan sesi terakhir aman/idle, pilih ulang mode tes pada display agar peer baru dapat terdeteksi. Saat sesi aktif atau status STOP belum pasti, peer tidak diganti otomatis. ESP-NOW pada alat ini belum diautentikasi.
