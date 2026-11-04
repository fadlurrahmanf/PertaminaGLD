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
