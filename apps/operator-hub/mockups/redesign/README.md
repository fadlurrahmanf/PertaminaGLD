# Operator Hub — konsep desain baru (mockup)

`operator-hub-redesign.html` adalah mockup **desain visual baru** Operator Hub:
satu file HTML mandiri (tanpa server, tanpa build, tanpa dependensi selain font
IBM Plex opsional). UI produksi di `apps/operator-hub/public` tidak dipakai dan
tidak diubah; alur dan fungsinya direpresentasikan ulang dengan data simulasi.

## Konsep

| Produksi saat ini | Konsep baru |
|---|---|
| Satu kolom tengah, stepper horizontal 3 tahap | Sidebar armada perangkat + checklist vertikal 4 tahap dengan progres |
| Gelap teal/oranye | Terang slate/indigo + mode gelap |
| Connect sebagai tahap terpisah | COM + Connect selalu ada di bar perintah atas |
| Expert Console = aplikasi terpisah per port | Mode **Expert** di aplikasi yang sama (tab per perangkat) |
| Dialog bawaan browser / notice tunggal | Drawer firmware, modal konfirmasi, toast, jejak aktivitas |

## Alur yang direpresentasikan

- Pilih GLD / CH / Gateway, pilih COM, Connect / Disconnect (COM1 = port sistem → gagal)
- Board tanpa firmware → pasang firmware awal (NVS wajib reset)
- Uji kesiapan otomatis setelah connect: GLD 6 cek, CH 4 cek, Gateway 4 cek; lulus / gagal / menunggu; uji ulang
- Konfigurasi terkunci sampai uji lulus: Device ID, STAR frequency, Target CH (GLD), Root Gateway (CH), Wi-Fi + MQTT non-TLS/TLS (Gateway) dengan validasi rentang
- Alarm fisik GLD: AUTO/MANUAL (ketik `MANUAL`), Test ON/OFF, 3 varian output, kontrak terkunci; restart → AUTO
- Upload firmware: paket GLD, bentuk board CH/GW, transport GW, Reset NVS, downgrade v0.8.38 wajib reset, hotspot dilarang reset, progres + log, gagal, verifikasi hotspot
- Expert GLD: live telemetri 8 sensor, nulling 8/8, dataset, QC, terminal (PIN `0000`)
- Expert CH: ringkasan, node GLD live, mesh/parent (HELLO, failover, hapus parent NVS), terminal
- Expert Gateway: ringkasan, uplink live, topologi, Server Pull / perintah node, terminal

Tombol **Skenario simulasi** di sidebar mengubah kondisi (board baru, test gagal,
TLS, upload gagal, varian alarm, kecepatan) tanpa memuat ulang halaman.
Tidak ada port COM, firmware, NVS, MQTT, data, atau perangkat yang disentuh.
