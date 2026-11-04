# Operator Hub — mockup mandiri

`../operator-hub-full-mockup.html` adalah satu file HTML mandiri (tanpa server,
tanpa dependensi) yang merepresentasikan seluruh Simple Hub Operator Hub.
Buka langsung di browser.

## Cara kerja

- `build.py` membaca `apps/operator-hub/public/` (index.html, 3 CSS, `js/hub.js`)
  **tanpa mengubahnya** dan meng-inline semuanya ke satu file.
- `mock-backend.js` dijalankan lebih dulu dan mengganti `fetch` (`/api/simple/*`)
  serta `EventSource` (log upload) dengan model in-memory. Bentuk respons dan
  pesan validasi mengikuti `bridge.py`.
- `mock-panel.js` / `mock-panel.css` menambah banner MOCKUP, panel peninjau
  (preset dan kondisi kustom; berganti skenario di tempat tanpa reload, jadi juga berjalan di pratinjau sandbox), dan mencegat tautan yang keluar
  dari Hub (Expert Console, verifikasi hotspot GLD Operator).

## Expert Console

Tombol **Expert Console** (dan tautan verifikasi hotspot) membuka konsol
operator yang sesuai dengan perangkat aktif dalam overlay. Konsol yang dibuka
adalah UI asli masing-masing, dibundel saat build oleh `expert_bundle.py`
(setiap ES module tetap modul tersendiri, dimuat lewat import map + data: URL):

| Perangkat | Konsol asli | Simulasi |
|---|---|---|
| GLD | `apps/gld-operator` | Simulator bawaan konsol (`js/mock.js`, mode Mock) aktif otomatis; koneksi COM juga dijawab simulator yang sama |
| CH | `apps/ch-operator` | `expert/ch-device.js`: firmware CH tiruan (CH_INFO/STATUS/NODES/PARENTS JSON, ACK, HELLO, STAR RX, failover, restart) |
| Gateway | `apps/gw-operator` | `expert/gw-device.js`: firmware Gateway + broker MQTT tiruan (Wi-Fi, MQTT, status, uplink, topologi, pull/node command, Mesh LoRa, Gateway ID) |

Pendukung bersama di `expert/`: `bridge-mock.js` (bridge lokal: health/token,
port COM, serial + SSE, paket firmware, upload), `storage-shim.js`
(localStorage dan SHA-256 cadangan untuk pratinjau sandbox), dan `nav-shim.js`
("← Simple Hub" kembali ke Hub; dialog `confirm/prompt` yang diblokir sandbox
disetujui otomatis, PIN Expert lokal = `0000`). Manifest paket firmware asli
dari `firmware-packages/` disematkan (metadata saja, tanpa file `.bin`).
Satu-satunya penyesuaian kode konsol: GLD Operator memulai mode Mock tanpa
`?mock=1`.

Tidak ada port COM, firmware, NVS, MQTT, data, atau perangkat yang disentuh.

## Skenario (URL hash)

| Kunci | Nilai |
|---|---|
| `gld` | `normal`, `fresh`, `fail`, `pending`, `alarm-locked` |
| `ch` / `gw` | `normal`, `fresh`, `fail` |
| `gwfw` | `non_tls`, `tls`, `legacy` |
| `drive` | `steady_24v`, `gpio41_high`, `gpio41_pullup` |
| `inference` | `0`, `1` |
| `upload` | `success`, `error` |
| `speed` | `normal`, `fast` |
| `preset` | `gld-config`, `gld-test`, `gld-connect`, `ch-config`, `ch-connect`, `gw-config`, `gw-test` |

Contoh: `operator-hub-full-mockup.html#gwfw=tls&preset=gw-config`.
Mode bawaan aplikasi `?simulate=ch-com6` dan `?simulate=ch-com6-new` tetap berfungsi.

## Rebuild

```text
python apps/operator-hub/mockups/full-mockup/build.py
```

Jalankan ulang setelah UI produksi berubah agar mockup tetap sinkron.
