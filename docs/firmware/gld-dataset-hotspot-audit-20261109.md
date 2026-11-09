# Audit Dataset Hotspot — 9 November 2026

## Pembaruan audit setelah pengujian awal

Audit ulang menemukan bahwa paket awal di bawah belum memantau AP yang hilang
setelah startup. Firmware Workflow kini memeriksa kelangsungan AP tiap detik,
mencoba memulihkannya dengan jeda 5 detik, dan menunggu PG24 stabil pada cold
boot. Mode Dataset yang tersimpan tidak ditimpa oleh pembacaan daya sesaat.
Jika boot sempat masuk Inference karena daya eksternal belum stabil, satu reboot
terjaga mengembalikan mode COM sesuai pilihan tersimpan setelah daya pulih.
Perubahan ini hanya berlaku pada tiga image Workflow Hotspot final.

Tiga image hasil build ulang terakhir yang sudah terpasang sebagai paket final
di Operator Hub memiliki SHA-256 berikut:

| Model | SHA-256 `firmware.bin` baru |
| --- | --- |
| 1 | `5adf808bfbbb88189593bcbd394e718d2cf33ee879b5850cc4b0362d55a25509` |
| 2 | `a490f17be82388ab5e65cfcb4a1e4dcc38fa6f2eec31e6322063b438ba4403d9` |
| 3 | `1a9e0f607ba8168362dd885a66b95da65b7ade8a9fdc43879f7731376571f1ba` |

Hash pada bagian pengujian awal di bawah adalah bukti versi sebelumnya,
bukan identitas paket final ini. Build dan pengujian source lulus; image baru
belum di-upload ke GLD, sehingga cold boot tanpa USB dan replay lima menit
pada image baru masih memerlukan uji fisik. Reset NVS tidak dilakukan.

## Gejala dan batas bukti

Operator melaporkan dua gejala: hotspot tidak selalu terlihat setelah cold boot
24 V tanpa USB, dan PC kedua telah terasosiasi ke `GLD-DATASET-1002` tetapi
Operator Hub menampilkan `network_unreachable`. PC kedua dan cold boot tanpa
USB tidak tersedia untuk pengukuran langsung pada audit ini. Patch terdahulu
`2a74b5b1` memperbaiki batas waktu handshake dan pesan galat; patch itu tidak
menyentuh boot, DHCP, atau rute PC.

## Temuan dan perubahan

1. Pada boot dengan mode tersimpan DATASET, firmware dahulu menunggu koneksi
   router native hingga 15 detik sebelum memulai AP. Firmware Workflow kini
   memulai AP sesudah inisialisasi sensor/nulling dan sebelum percobaan native
   STA/MQTT. Upaya STA Workflow menjadi tidak memblokir loop utama, memiliki
   tenggat 15 detik dan jeda retry. Jalur firmware non-Workflow tidak diubah.
2. Backend Windows dahulu menganggap SSID tersambung sudah cukup dan langsung
   membuka WebSocket. Kini Connect menunggu hingga 8 detik agar adaptor Wi-Fi
   GLD yang dipilih memiliki IPv4 `192.168.4.x` dan rute langsung terbaik ke
   `192.168.4.1`. Jika rute tetap belum tersedia, backend tidak mengirim header
   autentikasi dan menampilkan `wifi_route_not_ready`. Keadaan IP terlambat,
   rute hilang, serta SSID berubah disimulasikan dengan WLAN inert. Probe pada
   PC ini menemukan `InterfaceGuid` Windows berupa string dengan kurung kurawal;
   perbandingan awal dengan objek GUID keliru dan telah diperbaiki. Setelahnya
   asosiasi, rute dan Hello nyata pada GLD1002 berhasil.
3. Tiga image final Model 1/2/3 dibuild paralel pada direktori C: terpisah.
   Build awal pada D: gagal karena ruang D: habis, bukan karena source. Setelah
   ruang tersedia, hanya tiga paket `gld_model_{1,2,3}_dataset_workflow_wifi`
   di Operator Hub yang diperbarui. Paket model biasa tidak berubah.
4. Aplikasi kini menawarkan **Gunakan folder Dataset bawaan** untuk memilih
   nama CSV baru tanpa dialog Windows. Pemilih file asli tetap tersedia. Export
   mempertahankan CRLF sehingga salinan unduhan identik byte dengan CSV yang
   diverifikasi. Wizard menampilkan label/mode/kolom aktual sesi yang sudah
   terkunci bila state diperbarui melalui klien lokal lain.
5. `run-operator-hub.bat` tetap membuka konsol terlihat dan tidak lagi membuka
   Chrome otomatis. Satu tab GLD Console di browser Codex dapat dipakai untuk
   memantau; bila PC hanya memiliki satu adaptor Wi-Fi, Ethernet atau adaptor
   Internet kedua diperlukan agar Codex tetap online saat Wi-Fi masuk GLD.
6. Selama uji Direct, Windows beberapa kali mencatat putus dari hotspot dengan
   alasan `The network is disconnected by the driver`; SSID GLD masih terlihat.
   Supervisor protokol sebelumnya hanya mengulang WebSocket. Sekarang retry
   sesi aktif terlebih dahulu meminta Windows menyambung ulang SSID GLD yang
   dipilih dan menunggu rute langsung, lalu melanjutkan protokol. Gagal rejoin
   dijadwalkan ulang dengan backoff tanpa mengubah ACK atau kepemilikan sesi.
   UI membedakan sesi yang sudah ditutup dari koneksi yang hilang, dan pesan
   pemulihan menyebut usaha sambung ulang otomatis. Log driver belum cukup
   untuk menentukan apakah pemicunya sinyal radio, adaptor, atau AP.

## Bukti yang lulus

| Pemeriksaan | Hasil |
| --- | --- |
| Simulasi Windows WLAN/rute | 25/25, termasuk format GUID nyata |
| Diagnostik Connect | 11/11 |
| Workflow Dataset, adversarial, replay | 40/40, 19/19, 22/22 |
| Dispatch dan UI wizard | 4/4, skrip UI lulus |
| Kontrak firmware Workflow dan timeout header | 22/22, 7/7 |
| Kredensial, paket native, upload native | 7/7, 4/4, 5/5 |
| Build final Model 1/2/3 | 3/3 sukses; RAM 57,4%, flash 17,2% |
| Validasi paket | 3/3: model blob, protokol 3, hash empat berkas flash, manifest, child/Hub/preflight, batas NVS, credential privat |
| `git diff --check` | Lulus; hanya peringatan konversi line ending Windows |
| Upload GLD1002 | Paket final Model 2 melalui Hub, Reset NVS OFF; ID 1002 dan firmware 0.8.36 terbaca kembali |
| Hello fisik setelah upload | Protokol 3, nulling profil 2, interval 500 ms, retensi 300000 ms, siap; boot ID berubah |
| Hub API + GLD asli | 61 baris, 12 kolom, 48 sampel replay, gap 0, duplikat 0, Stop verified |
| Tombol di satu tab Codex + GLD asli | Scan, pilih, Connect, folder CSV bawaan, prediksi, Pulih otomatis, Lock, Start, Pause, Resume, Stop, popup OK, Export; 63 baris, 12 kolom, gap 0, duplikat 0 |
| Interval dan salinan Export | Interval normal 496–504 ms, median 500 ms; SHA-256 CSV dan file Export sama |
| Continue via tab Codex | Dari 63 menjadi 87 baris di CSV yang sama; Stop memverifikasi 87 baris |
| Direct via tab Codex | Saat Wi-Fi diputus, CSV beku pada 54 baris; setelah sambung ulang dan penutupan sesi, 54 baris terverifikasi sebagai tidak lengkap. Continue ke CSV sama mencapai 72 baris; putus driver kedua dibekukan dan 72 baris terverifikasi setelah sambung ulang |
| Replay dengan rejoin Wi-Fi otomatis | Wi-Fi Windows diputus saat 25 sampel; tanpa perintah sambung manual, Hub mengasosiasikan lagi ke GLD, memulihkan buffer, meneruskan grafik dan Stop memverifikasi 104 baris, 12 kolom, urutan utuh; interval 496–504 ms, median 500 ms |

SHA-256 `firmware.bin` final:

| Model | SHA-256 |
| --- | --- |
| 1 | `e106011e73323ca95fa386416f099444cf9807c592eb5223cd1b812ace221259` |
| 2 | `1b1d0499c63e8bbdb5129a169383f381ba0980176f25844857a8232d9c399a0e` |
| 3 | `fe6f8b6747160ac6c1358fb44b074dba039a913d397aea61a90916fa1c420606` |

CSV hasil uji tombol aplikasi awal:
`apps/gld-operator/output/datasets/dataset-GLD-1002-20261109-212832-56ba7d17.csv`.
Salinan Export 63 baris ada di `C:/Users/MSI/Downloads/` dengan nama yang sama.
Saat diunduh, SHA-256 CSV dan Export cocok:
`c0397e31ce7c44603f8fbd248d08259ae540db4e3b37dba7bd65f6dc281b3988`.
Setelah Continue, CSV sumber bertambah menjadi 87 baris dan SHA-256-nya berubah
menjadi `f51715a195e495c28898b586130fa6956f1fb4227033ab6ecbb6adad84e74cc9`;
salinan lama tetap merupakan snapshot 63 baris.

CSV uji rejoin otomatis terakhir:
`apps/gld-operator/output/datasets/dataset-GLD-1002-20261109-214555-69e7fc19.csv`.
CSV dan ledger sama-sama memiliki 104 baris, ID baris dan sequence utuh, seluruh
baris memiliki prediksi; SHA-256 CSV:
`86f1cc5dc1eb399ab0043f9fd48624687823f3a62348a373cac92dc1d19582a0`.
Hub berjalan di konsol terlihat dan satu tab Codex menampilkan hasil Stop 104
baris. Ethernet menyediakan Internet saat Wi-Fi digunakan untuk GLD.

## Hal yang belum terbukti

- Kegagalan cold boot tanpa USB mungkin melibatkan pembacaan PG24, reset,
  catu daya, atau AP yang hilang setelah startup. Perubahan di atas mengatasi
  penundaan router, tetapi tidak membuktikan penyebab fisiknya. Firmware hanya
  mencoba memulai AP saat `batteryPowerMode == false` dan PG24 HIGH; status
  `available()` belum memeriksa kelangsungan AP sesudah startup.
- Penyebab `network_unreachable` di PC kedua belum diketahui. Uji nyata PC ini
  membuktikan jalur DHCP/rute berfungsi; konflik rute VPN di PC kedua,
  kegagalan DHCP permanen, atau layanan port 81 di GLD tetap memerlukan data
  dari PC itu. Hotspot firmware mengizinkan satu klien Wi-Fi; saat pindah PC,
  lepaskan koneksi PC lama terlebih dahulu.
- Hanya Model 2 di GLD1002 yang di-upload dan diuji fisik. Model 1/3 telah
  dibuild serta divalidasi sebagai paket, tetapi belum di-upload ke boardnya.
  Reset NVS tidak dilakukan. Buffer RAM tetap hilang jika GLD mati.
- Uji putus/replay nyata berlangsung puluhan detik, belum mengukur retensi penuh
  lima menit. Penyebab radio/driver putus spontan masih memerlukan pengukuran
  sinyal dan catu saat kejadian; auto rejoin telah dibuktikan memulihkan sesi
  yang sama pada PC ini.

## Uji penerimaan fisik berikutnya

Dengan catu 24 V saja dan USB terlepas, lakukan cold boot berulang, ukur waktu
hingga SSID terlihat, lalu catat `GLD_POWER`, `DATASET_WIFI_SERVER`, mode
tersimpan, serta sinyal PG24/reset tanpa mengandalkan USB sebagai pemicu.
Pada PC kedua, jalankan diagnostik baca saja yang ikut Git,
`tools/Run-GLD-WiFi-Check.cmd 1002` (ganti ID sesuai GLD) ketika tersambung
ke hotspot GLD dan Hub tidak merekam. Hasil ada di `output/diagnostics/`;
periksa asosiasi, rute, TCP 81 dan Hello. Skrip tidak mengubah Wi-Fi,
menjalankan rekaman, atau membuka COM.
Uji Start, delapan sensor 500 ms, putus Wi-Fi, replay, Stop, dan CSV telah
lulus pada GLD1002 PC ini. Ulangi di PC kedua setelah pull untuk membuktikan
rute, port 81 dan perilaku adaptor PC tersebut; tutup sesi sebelum menguji
Running/Nulling lewat COM.
