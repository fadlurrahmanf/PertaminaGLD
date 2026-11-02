# GLD Dataset Wireless — simulasi end-to-end PC

Tanggal: 2026-11-02, Asia/Jakarta. Hasil: **PASS untuk scope simulasi PC**.

UI GLD Operator yang dipakai Operator Hub, bridge/API/SSE, client WebSocket,
recorder CSV, dan tombol Download CSV menggunakan source aplikasi asli.
Sumber perangkat diganti peer WebSocket sintetis di loopback, pada port terpisah.
Interaksi UI dilakukan melalui browser bawaan Codex. Tidak ada kontrol aplikasi
Windows, pembukaan COM7, upload/reset, atau penggantian service produksi.

## Hasil

| Pemeriksaan | Bukti | Hasil |
|---|---|---|
| Connect, Start, ACK/status | Identitas/sesi dan ACK sebelum sampel pertama seq0 | PASS |
| Grafik delapan sensor | Delapan kurva berbeda dan legend MQ8/MQ135/MQ3/MQ5/MQ4/MQ7/MQ6/MQ2 terlihat | PASS |
| Sesi normal |153 sampel dikirim,153 tersimpan; gap0/duplikat0 | PASS |
| Browser ditutup | Counter24 sebelum tutup →59 saat tab tertutup →119 setelah buka; sesi tetap recording | PASS |
| Stop/summary | Status complete, total153 cocok dengan file | PASS |
| Koneksi putus saat merekam | Socket benar-benar ditutup;53 sampel tersimpan; incomplete/connected=false | PASS |
| Setelah putus | Counter tetap53 setelah observasi2detik; Start/Stop disabled, Connect/Download tersedia | PASS |
| CSV unduhan | Semua header/field dari kedua file unduhan cocok dengan file backend | PASS |

Validator independen membandingkan **seluruh206 baris**, termasuk delapan
tegangan, gain/status, urutan fitur, label, profil, session/sequence, dan timestamp,
terhadap sampel yang benar-benar dikeluarkan peer tiruan. Kedua CSV memiliki34 kolom.
CSV backend memakai newline Windows; file unduhan menormalkan newline. Nilai
dan hasil parsing sama walaupun hash byte file berbeda.

Timestamp pengukuran sintetis berselisih tepat500ms. Interval pengiriman pada
host tercatat453–547ms, median500ms. Waktu kedatangan client tidak diinstrumentasi.
Nilai scan10ms pada screenshot adalah nilai sintetis; bukan hasil pengukuran ADS.

## Artifact

- [Laporan validator JSON](D:/Github/PertaminaGLD/tmp/wireless-stage1/e2e/verification-report.json)
- [Evidence yang dibekukan sebelum cleanup](D:/Github/PertaminaGLD/tmp/wireless-stage1/e2e/validated-evidence.json)
- [CSV sesi normal153baris](D:/Github/PertaminaGLD/tmp/wireless-stage1/e2e/downloads/clean.csv)
- [CSV sesi putus53baris](D:/Github/PertaminaGLD/tmp/wireless-stage1/e2e/downloads/drop.csv)
- [Grafik setelah browser dibuka kembali](D:/Github/PertaminaGLD/tmp/wireless-stage1/e2e/screenshots/02-clean-recording-restored.jpg)
- [UI setelah koneksi putus](D:/Github/PertaminaGLD/tmp/wireless-stage1/e2e/screenshots/03-disconnected-incomplete.jpg)

## Temuan dan batas bukti

Run pertama berakhir tidak terencana setelah105 sampel dan diarsipkan di
`tmp/wireless-stage1/e2e/attempt1/`. Probe Windows mereproduksi PermissionError
saat file trace diganti sementara sedang dibaca. Karena exception historis sempat
ditelan fixture, atribusi run pertama tetap inferensi. Fixture diperbaiki agar
kegagalan penulisan trace tidak memutus transport;2 tes regresi fixture lulus.
Run bersih berikutnya melewati153 sampel tanpa kejadian tersebut.

Wrapper simulator sempat mengalami error observer pada browser. Pengujian final
dilakukan pada halaman GLD Operator asli secara langsung, sebagaimana console
yang dibuka dari Hub. Bootstrap/driver/launcher Hub produksi tidak diuji ulang.
Browser final tidak mencatat error/warning console. Tujuh kontrol negatif validator
lulus, termasuk penolakan data sensor salah, total palsu, dan bukti continuity hilang.

Tidak ada perubahan source produksi atau firmware untuk menuntaskan simulasi ini.
Hash source firmware dan ketiga binary produksi tetap sama. Browser ditutup dan
kedua service simulator dihentikan; port54016/54017 tidak lagi listening dan
PID simulator25636 telah berakhir. Evidence valid dibekukan sebelum shutdown.

Hasil ini belum membuktikan hotspot/RF, pembacaan ADS/nulling, waktu scan nyata,
queue/backpressure firmware, maupun operasi24V. COM7 hanya dicatat sebagai target
yang tersedia; belum diakses. Uji GLD nyata dan upload memerlukan instruksi terpisah.
