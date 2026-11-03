# Mock Dataset GLD

Dua konsep interaktif, dibuat pada 3 November 2026. Tidak mengganti aplikasi yang berjalan.

- **Workspace (rekomendasi):** lima langkah padat di kiri, kontrol dan monitor di kanan. Class/confidence di atas grafik; nilai delapan sensor berupa legenda ringkas; export di bawah tabel.
- **Terpusat:** lima blok konfigurasi di atas, diikuti grafik dan tabel selebar area kerja. Lebih lebar untuk grafik, lebih banyak ruang vertikal untuk persiapan.

Claude Code benar-benar dikonsultasikan melalui CLI memakai brief teks yang telah dibatasi pada kebutuhan desain. `--safe-mode --tools= --strict-mcp-config --no-session-persistence` memastikan tidak ada tool, akses proyek, atau pekerjaan edit yang didelegasikan. Konsultasi berhasil; rekomendasi tersimpan pada `claude-design-review.md`. Tidak ada kredensial atau data rekaman pengguna dalam brief.

Masukan yang diterapkan: prioritas grafik/status, input terkunci tetap terbaca, langkah berupa rail dengan pemisah, legenda-nilai menggantikan kartu sensor besar, radio eksklusif dan timestamp di dalam kelompok input label. Penamaan Start/Pause/Resume/Stop/Continue tetap mengikuti alur pengguna.

Interaksi adalah simulasi lokal: mock dimulai dalam keadaan Merekam dengan64 sampel contoh. Pause/Resume dan Stop/Continue dapat dicoba. Reset memperlihatkan alur kumulatif dari awal. Scan dan pemilih lokasi CSV tidak mengakses perangkat/jaringan/filesystem. Export menyiapkan CSV contoh; sandbox preview dapat membatasi download. Range/legenda hanya mengubah tampilan. Tidak ada pengambilan sampel500ms nyata, pemeriksaan disk nyata atau pemulihan RF nyata.

`preview.html` adalah wrapper inspeksi lokal dari sumber visualisasi; tidak dipublikasikan. Sumber interaktif ditampilkan langsung dalam percakapan. Dua desain memakai stage carousel dengan tinggi yang sama pada setiap lebar agar navigasinya tidak bergeser.

QA: `qa-report.json`. Browser baru memeriksa Pause/Resume, Stop/verifikasi simulasi, Continue, Reset, lima gerbang berurutan, radio, Lock, delapan seri, export contoh serta lebar1024/736/320 dalam terang/gelap. Tidak ada overflow horizontal halaman; tabel lebar mempunyai scroll sendiri. Screenshot di `browser/` telah diperiksa. Hash enam sumber produksi sebelum/sesudah identik; tidak ada COM/WLAN/firmware/build/restart layanan atau perubahan CSV pengguna.
