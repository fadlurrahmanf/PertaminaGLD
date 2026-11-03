# Workspace — revisi kontrol rekaman

Pilihan pengguna: hanya Workspace. Tulisan Siap, status Siap per langkah, dan penghitung5/5siap dihapus; nomor hijau kumulatif tetap digunakan. Tidak ada carousel alternatif.

Satu tombol utama memakai ikon Lucide dan label sesuai keadaan:

- Sebelum rekaman: Play + Start.
- Saat merekam: Pause + Pause.
- Saat jeda: Play + Resume.
- Setelah Stop terverifikasi: Play + Continue, meneruskan CSV yang sama.

Stop tetap berupa tombol terpisah dengan ikon Square dan label. Saat verifikasi berjalan kedua tombol disabled. Tooltip dan aria-label mengikuti aksi agar ikon tetap jelas dan dapat diakses.

Semua interaksi menggunakan data contoh. `qa-report.json` membuktikan penggabungan tombol, Stop dari Pause, Continue, Reset/lima langkah, perubahan ikon dan layout1024/736/320. Screenshot terang dan gelap diperiksa. Tidak ada perubahan pada Operator Hub, firmware, perangkat atau data asli.
