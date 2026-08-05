# MQ8 Test Console

Panel lokal khusus untuk uji duty-cycle MQ8. Aplikasi ini terpisah dari
Operator Hub dan tidak membuka port serial sebelum operator menekan **Mulai
Baseline 100%**.

Alur yang dijalankan: `100 -> 15 -> 100 -> 20 -> ... -> 95 -> 100 akhir`.
Perpindahan fase hanya terjadi setelah operator menekan **Stabil - fase
berikutnya**. Semua output sesi disimpan di `apps/mq8-test-console/output/`.

Jalankan `run-mq8-test-console.bat`, lalu buka `http://127.0.0.1:5188/`.
GLD Operator harus tetap aktif dan terhubung ke COM3; console membaca telemetry
melalui bridge GLD tersebut. Wrapper console memastikan runner tidak membuka
COM3 secara langsung. COM5 untuk Uno harus bebas.

Menjalankan batch lagi saat console sudah hidup hanya membuka halaman yang sama;
ia tidak membuat server kedua dan tidak mengubah eksperimen aktif.

## Running

- **Durasi fase** menunjukkan lama fase yang sedang direkam.
- Baris **MQ8 aktif** menampilkan nilai saat ini, perubahan dari awal tampilan,
  arah, peak-to-peak 60 detik, tren satu menit, dan status dari gate runner.
  Kolom **Gain** akan `-` karena runner telemetry GLD saat ini tidak mengirim
  field gain; console tidak mengisi nilai tebakan.
- Halaman membaca status setiap **500 ms** dan runner memperbarui `live.csv`
  pada setiap sampel telemetry valid. Kecepatan titik nyata tetap mengikuti
  laju telemetry GLD yang diterima.
- Slider **Range grafik** hanya memotong tampilan 1–60 menit; CSV tidak
  dikurangi. **Clear tampilan** membuang riwayat grafik yang sudah terlihat,
  tetapi titik valid baru tetap langsung muncul; ia tidak menghentikan atau
  menghapus rekaman.
- **Export CSV** mengunduh seluruh `live.csv` valid-only pada sesi aktif.

Grafik selalu menyertakan garis referensi **0 mV** kuning putus-putus. Tombol
**Reset** hanya memulai ulang observasi pada browser: grafik, durasi tampilan,
dan sampel tampilan kembali dari nol, sementara duty, fase, CSV, dan rekaman
hardware tidak berubah. Kolom **Saat ini** menampilkan `mV (V)` dan **Gain**
dibaca dari `telemetry.sensorGain` GLD. Status memakai kalkulasi Running GLD:
jendela tren satu menit serta baseline lima menit sebelum dapat menyatakan
Stabil.
