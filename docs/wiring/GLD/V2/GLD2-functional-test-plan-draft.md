# Draft rencana uji fungsional GLD2

Status: **draft rencana uji** — bukan bukti bahwa seluruh butir sudah lulus.  
Ruang lingkup: board GLD2 berdasarkan `source-GLD2.zip` dan firmware environment `gld_v2`.

## Prinsip penerimaan

- Catatan serial, ACK I2C, dan readback register membuktikan komunikasi firmware; itu **bukan** otomatis bukti tegangan, pulsa, atau beban fisik benar-benar berubah.
- Setiap butir harus menyimpan: versi/paket firmware, mode daya, waktu, perintah, log/telemetri, dan bila diperlukan foto atau hasil osiloskop/multimeter.
- Uji yang dapat memutus catu daya (CLR/TPL) dilakukan paling akhir, tidak saat nulling, upload, atau service hold aktif.
- Satu status `PASS` hanya berlaku untuk kondisi dan bukti yang ditulis pada baris tersebut. Tidak boleh disimpulkan lintas mode 24 V dan baterai.

## Acuan wiring dan mapping sensor

| Header | Sensor | PCF EN | TCA channel | ADS1256 AIN |
|---|---|---:|---:|---:|
| H2 | MQ8 | EN0 / P0 | 7 | AIN0 |
| H1 | MQ135 | EN6 / P6 | 6 | AIN1 |
| H3 | MQ3 | EN7 / P7 | 5 | AIN2 |
| H4 | MQ5 | EN3 / P3 | 4 | AIN3 |
| H5 | MQ4 | EN4 / P4 | 3 | AIN4 |
| H6 | MQ7 | EN5 / P5 | 2 | AIN5 |
| H7 | MQ6 | EN2 / P2 | 1 | AIN6 |
| H8 | MQ2 | EN1 / P1 | 0 | AIN7 |

Alamat root I2C yang diharapkan: PCF8574 `0x20`, SHT40 `0x44`, dan TCA9548A `0x71`. MCP4725 beralamat `0x60` setelah TCA memilih satu cabang dan rail sensor pasangannya aktif.

## Peralatan minimum

| Kelompok uji | Peralatan minimum |
|---|---|
| Firmware/serial | Operator Hub atau terminal serial, paket firmware yang dicatat versinya |
| I2C/ADC/DAC | Tidak perlu alat tambahan untuk ACK/readback; multimeter atau osiloskop bila perlu membuktikan tegangan fisik |
| Power/TPL | Catu 24 V terkontrol, sumber baterai yang sesuai, multimeter, dan osiloskop/logic analyzer untuk DONE serta CLR |
| Alarm | Beban alarm yang memang digunakan, multimeter/osiloskop; proteksi pendengaran bila buzzer terpasang |
| LoRa | Minimal satu CH/Gateway lawan dengan konfigurasi yang dicatat |
| Modbus | Master RS-485/USB-RS485 dengan terminasi dan register map yang disetujui |

## Urutan uji yang direkomendasikan

1. Catat versi firmware dan kondisi board; jalankan boot check pada mode 24 V.
2. Selesaikan I2C, PCF/TPS22919, TCA/MCP, ADS, SHT40, dan nulling sebelum menguji inference.
3. Uji alarm manual terlebih dahulu, lalu alarm otomatis dari inference hanya dengan stimulus yang disetujui.
4. Uji Modbus dan LoRa menggunakan perangkat lawan.
5. Setelah semua uji non-destruktif lulus, uji TPL/DONE/CLR serta siklus baterai.

## Checklist uji

| No. | Area | Prosedur/bukti yang dicari | Kelas bukti | Kriteria lulus |
|---:|---|---|---|---|
| 1 | Identitas firmware | Ambil `GET_INFO`/`GET_STATUS`; cocokkan environment `gld_v2`, versi, dan paket yang diuji. | Firmware | Identitas board dan paket tercatat, tidak ambigu. |
| 2 | Boot sehat | Boot pada 24 V lalu simpan `[BOOT_IC_REPORT]`, `MODE_READY`, dan restart counter. | Firmware | Tidak ada restart berulang; detail kegagalan bila ada tidak disembunyikan. |
| 3 | Deteksi sumber daya | Uji 24 V dan, terpisah, baterai; cocokkan `ST_P` (HIGH=24 V, LOW=baterai) serta nilai tegangan yang dilaporkan. | Firmware + fisik | Status sumber sesuai catu nyata; pembacaan tegangan masuk akal terhadap multimeter. |
| 4 | I2C root | Scan/probe non-destruktif bus GPIO8/9. | Firmware | `0x20`, `0x44`, `0x71` ACK secara konsisten; kegagalan tidak membuat loop/restart. |
| 5 | PCF8574 | Tulis mask satu bit lalu baca/telemetri kembali; ulang P0–P7. | Firmware | Mask dan mapping EN sesuai tabel; status UI konsisten dengan `outputMask`. |
| 6 | TPS22919/rail sensor | Untuk tiap EN, ukur rail/header saat OFF lalu ON dan kembali OFF. | **Fisik wajib** | Rail sensor benar-benar berubah sesuai EN; tidak cukup hanya PCF readback. |
| 7 | TCA9548A | Pilih channel satu per satu dengan sensor pasangan aktif, kemudian pindai cabang. | Firmware | Setiap channel hanya mengekspos MCP `0x60` pasangannya; tidak ada channel tertukar. |
| 8 | MCP4725 | Tulis kode rendah, tinggi, lalu nilai awal ke semua delapan MCP; baca balik sesudah tiap tulis. | Firmware | Kode baca balik sama dengan kode yang diperintahkan untuk seluruh kanal. |
| 9 | Respons DAC fisik | Untuk setiap header, ubah DAC terukur dan catat respons bridge/ADS setelah settle. | Firmware + fisik | Ada respons yang masuk akal; anomali dicatat tanpa menyatakan sensor rusak hanya dari satu sampel. |
| 10 | ADS1256 | Verifikasi SPI/DRDY, baca AIN0–AIN7, status, gain, dan saturasi. | Firmware | Semua kanal valid atau kegagalannya bernama jelas; gain yang dipakai dicatat. |
| 11 | SHT40 | Ambil beberapa pembaruan suhu/RH dengan interval runtime, cek umur sampel. | Firmware | `0x44` terdeteksi dan nilai baru masuk ke status; bukan nilai cache statis. |
| 12 | Pemetaan header | Pasang/modul sensor satu per satu sesuai tabel, lalu verifikasi TCA/MCP/ADS yang muncul. | Firmware + fisik | Header, EN, TCA, dan AIN cocok untuk delapan sensor. |
| 13 | Nulling | Jalankan `baseline → exponential → binary search → confirm` pada seluruh kanal. | Firmware + analog | Profil hanya aktif bila 8/8 lulus; baseline, code, gain, threshold adaptif, stabilitas, dan alasan gagal tersimpan. |
| 14 | Terapkan profil nulling | Reboot setelah profil sukses, lalu baca kembali kode MCP pada 8 kanal. | Firmware | Profil yang sama diterapkan dan tiap readback DAC cocok; inference tetap fail-closed bila profil/binding tidak sah. |
| 15 | Mode sensor | Uji manual ON/OFF, auto-control, inference, dataset, dan nulling sesuai wewenang operator. | Firmware + fisik untuk rail | Tidak ada perubahan PCF tak terduga; perintah OFF manual tetap tersedia di semua mode sesuai kebijakan. |
| 16 | Alarm manual | Jalankan OFF lalu ON lalu OFF: EN_BOOST HIGH → ALARM GPIO40 HIGH → GPIO40 LOW → EN_BOOST LOW. | Firmware + **fisik wajib** | Urutan log benar dan beban alarm benar-benar ON/OFF; kondisi akhir aman OFF. |
| 17 | Alarm inference | Dengan stimulus/model profile yang telah disetujui, amati transisi alarm otomatis dan fail-safe. | Firmware + fisik | Alarm hanya aktif untuk inference valid sesuai policy; sensor/inference fault tidak memicu alarm palsu. |
| 18 | LoRa SX1262 | Inisialisasi, TX ke perangkat lawan, dan RX/downlink atau ACK yang valid bila fitur dipakai. | Firmware + perangkat lawan | Bukan hanya `begin` sukses: frame benar diterima lawan dan/atau balasan diterima GLD. |
| 19 | RS-485/Modbus RTU | Hubungkan master; baca register read-only pada unit ID/baud yang dicatat. | Firmware + perangkat lawan | Master membaca nilai konsisten; arah `DIR`, TX2/RX2, format serial, dan timeout benar. |
| 20 | TPL5010 DONE | Pada 24 V dan baterai, amati GPIO17 dengan logic analyzer saat keepalive dan perintah uji terkontrol. | **Fisik wajib** | Bentuk dan interval pulsa DONE nyata sesuai desain/firmware; log saja tidak cukup. |
| 21 | Power latch CLR | Dengan mode baterai dan operator siap menghadapi power cut, uji pulsa GPIO16/CLR (`INJECT_TPL_CLR` atau alur sesi) termasuk guard service hold/CFG. | **Fisik wajib, berisiko** | CLR memutus latch hanya saat diizinkan; saat service hold/CFG blok aktif, CLR tidak boleh mematikan board. |
| 22 | Siklus baterai TPL | Jalankan satu sesi baterai lengkap: kerja → DONE → CLR → board OFF → wake TPL berikutnya. | **Fisik wajib, berisiko** | Board benar-benar power-off lalu wake kembali sesuai interval; tidak ada data/profil korup. |
| 23 | Ketahanan/fail-safe | Lepas satu perangkat I2C/rail secara terkendali atau gunakan fault-injection software; pantau status dan alarm. | Firmware + fisik sesuai fault | Inference/alarm fail-closed, alasan fault jelas, tidak ada reset loop atau profil parsial. |

## Catatan khusus TPL5010

TPL5010 harus diuji. Firmware menyediakan jalur DONE di GPIO17 dan CLR latch di GPIO16, tetapi tidak memiliki ACK dari IC TPL. Karena itu, **perintah serial atau log `DONE`/`CLR` tidak membuktikan** sinyal sampai ke IC maupun catu daya benar-benar berubah.

Pisahkan dua penerimaan berikut:

1. **24 V:** pulsa DONE/keepalive hadir dan board tidak mati tak terduga melewati periode watchdog.
2. **Baterai:** alur sesi menyelesaikan pekerjaan, mengirim DONE, memicu CLR bila tidak diblok, board benar-benar OFF, lalu hidup kembali lewat jadwal TPL.

## Format catatan hasil per butir

| No. | Tanggal/waktu | Mode catu | Firmware/paket | Perintah/stimulus | Hasil log | Bukti fisik | PASS/FAIL/BLOCKED | Catatan/temuan |
|---:|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |  |

## Status temuan yang sudah tersedia dari percakapan bench

Hasil bench sebelumnya dapat dipakai sebagai **evidence historis**, bukan pengganti pengulangan setelah firmware algoritme nulling berubah:

- Root I2C, PCF8574, TCA9548A, SHT40, dan 8 MCP pernah terdeteksi/terkendali pada COM3 dengan mapping di atas.
- Uji write/readback DAC dan ON/OFF sensor pernah berhasil untuk seluruh kanal; pembuktian rail TPS22919 secara alat ukur tetap belum tersubstitusi oleh bukti tersebut.
- Nulling sedang menjadi gate aktif. Karena algoritmenya berubah, hasil profil atau keberhasilan nulling terdahulu tidak otomatis memvalidasi firmware baru.
- TPL5010 DONE/CLR, pengukuran rail fisik, alarm beban fisik, LoRa end-to-end, serta Modbus melalui master tetap memerlukan sesi uji khusus.

