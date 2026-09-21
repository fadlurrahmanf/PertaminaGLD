# GLD2 - Diagram blok dari schematic

Buka `index.html` untuk melihat 10 diagram dengan pilihan halaman dan zoom, atau `../../pdf/GLD2-Block-Diagram.pdf` untuk versi PDF vector.
SVG dapat diedit dengan Inkscape/Illustrator atau editor teks. Tata letak dan isi sumber ada di `build_diagram.py`.

## Sumber dan cakupan

- Satu lembar motherboard (Sheet_1), seluruh 204 komponen/simbol, dan net pad PCB dari ZIP yang diberikan pengguna.
- Gambar referensi modul sensor dibaca terpisah; designator komponen pada gambar modul tidak identik dengan motherboard.
- `source-net-evidence.json` menyimpan nama pin simbol, net pad PCB, koordinat pin schematic, dan label net hasil penelusuran wire. Nol perbedaan ditemukan pada pin yang mempunyai label net. Ini bukan electrical rules check penuh atau validasi routing PCB.
- `component-pins.csv` memuat setiap pin komponen termasuk komponen pasif. Baris casing tidak memiliki pin elektrik.
- Identitas sensor per kanal tidak diasumsikan dari firmware. Nama MQ2 hanya contoh yang tertulis pada gambar modul.
- +5VA motherboard tidak mempunyai sumber yang terlihat; +5VA lokal modul sensor mempunyai filter L1 dari +5V. Keduanya tidak digabung tanpa bukti.
- Pin modul referensi berbeda dari header motherboard. Tabel halaman 06 menunjukkan padanan fungsi, bukan instruksi memasang kabel tanpa pemeriksaan orientasi.
- Tidak ada perubahan firmware, build, upload, COM, atau pengukuran hardware.

## Regenerasi

Jalankan dengan Python yang mempunyai reportlab: `python output/diagrams/gld2/build_diagram.py` dari root repository. Font menggunakan Arial Windows.
Generator mengeluarkan PDF, 10 SVG, HTML, CSV, dan README. Input utamanya adalah `source-net-evidence.json` hasil ekstraksi sumber.

SHA-256 arsip sumber: `aeb3d54180c596c5ee7fbc9adbb51e434651a238b19a31429d8cf5c82ec985f1`
