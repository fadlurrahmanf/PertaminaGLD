# Pertamina GLD Node-RED Flow

Flow ini adalah server-side bridge untuk tahap bench GLD -> CH -> Gateway -> Node-RED.
Jalur utama kasus sebenarnya adalah MQTT/LAN dari Gateway ke server, bukan AP.

## Isi

- `functions/pertamina-gld-decode.js`
  - Function Node decoder.
  - Bisa membaca output Gateway `/api/status`.
  - Bisa decode `GLDRecord` kontrak baru.
  - Bisa decrypt AES-128-GCM payload 29 byte.
- `apply-pertamina-gld-flow.js`
  - Membuat tab `Pertamina GLD Server` di Node-RED lokal.
  - Backup flow existing sebelum deploy.
  - Apply lewat Node-RED Admin API.
- `apply-pertamina-gld-flow.ps1`
  - Wrapper PowerShell ke generator JS utama supaya hanya ada satu definisi flow.
- `.env.example`
  - Contoh variabel lokal. Jangan commit `.env` berisi secret produksi.

## Jalur Input

Flow menyediakan:

- MQTT uplink dari Gateway:
  - `gld/gateway/uplink`
  - `gld/gateway/raw`
  - `pertamina/gld/uplink`
- HTTP polling Gateway:
  - opsional/debug saja jika firmware Gateway nanti memang expose endpoint status.
  - default flow generator tidak mengaktifkan polling HTTP.
- MQTT command bridge:
  - inject/publish `gld/gateway/cmd/pull`
  - high-level GLD command input `gld/server/cmd/node`
  - signed Gateway command output `gld/gateway/cmd/node`
- Test vectors run through the checked-in automated harness, not a production
  flow inject node.

## Jalur Output MQTT

- `gld/gateway/status`
- `gld/gateway/events`
- `gld/server/decoded`
- `gld/server/alarm`
- `gld/server/integrity` untuk record yang gagal autentikasi/validasi
- `gld/server/replay` untuk duplicate atau sequence di luar replay window
- `gld/server/test` untuk input HTTP manual/test yang terautentikasi tetapi
  tidak boleh masuk alarm produksi
- `gld/gateway/error`
- command inject:
  - `gld/gateway/cmd/pull`
  - `gld/server/cmd/node`
  - `gld/gateway/cmd/node`

Pull command mengikuti kontrak CH `SERVER_PULL_REQUEST`: payload berisi
`hopList[]`, bukan GLD `nodeId`. Contoh direct CH bench:

```json
{"requestId":1,"hopList":["0x0064"]}
```

Command GLD/downlink high-level masuk ke `gld/server/cmd/node` dengan `mode`,
`cluster`, `node`, `id`, dan `authorization`. Nilai authorization harus sama
dengan secret `PGL_COMMAND_AUTH_TOKEN` (minimal 32 karakter). Flow menolak ID
hilang/tidak valid, menghapus token sebelum output, menandatangani payload
memakai `GLD_AES128_KEY_HEX`, lalu publish hasil authenticated ke
`gld/gateway/cmd/node`.

## Dataset Flow Controls

`apply-pertamina-gld-dataset-flow.ps1` membuat tab `GLD Dataset Server` untuk recorder dan kontrol operator. Flow dataset memiliki inject:

- `START_DATASET clear_air_test` publish ke `gas-leak-detector/F001/dataset`.
- `STOP_DATASET` publish ke `gas-leak-detector/F001/dataset`.

Flow dataset juga listen ke `gas-leak-detector/+/cmd/ack`, `gas-leak-detector/+/dataset/status`, `gas-leak-detector/+/dataset/summary`, `gas-leak-detector/+/dataset/data`, dan `gas-leak-detector/+/nulling/result`.

Record disimpan hanya bila topic/device cocok, mode `DATASET`, delapan voltage
finite, gain valid, seluruh `sensor_status` bernilai `0`, dan `feature_order`
sama dengan urutan model canonical. MySQL menjadi gate idempotensi sebelum CSV,
sehingga duplicate tidak dihitung atau ditulis dua kali. Saat deploy, script
membuat header CSV hanya untuk file baru dan menolak schema file lama.

## Apply Lokal

Contoh dari repo root:

```powershell
node .\server\nodered\apply-pertamina-gld-flow.js `
  --node-red-url "http://127.0.0.1:1880" `
  --gateway-status-url "http://0.0.0.0/disabled-until-gateway-ip-known" `
  --gateway-base-url "http://0.0.0.0" `
  --mqtt-host "127.0.0.1" `
  --mqtt-port 1884 `
  --replay-state-path "C:\ProgramData\PertaminaGLD\replay-state.json"
```

Wrapper PowerShell lama tetap bisa dipakai dan meneruskan argumen ke generator JS:

```powershell
.\server\nodered\apply-pertamina-gld-flow.ps1 `
  -NodeRedUrl "http://127.0.0.1:1880" `
  -GatewayStatusUrl "http://0.0.0.0/disabled-until-gateway-ip-known" `
  -GatewayBaseUrl "http://0.0.0.0" `
  -MqttHost "127.0.0.1" `
  -MqttPort 1884
```

Jika broker MQTT butuh auth, pass username/password saat apply lokal. Untuk host
non-loopback generator mewajibkan credentials dan TLS (`--mqtt-tls`), kecuali
operator secara eksplisit memilih `--allow-insecure-mqtt` untuk jaringan bench
yang benar-benar terisolasi. Flow tidak lagi membuat broker Aedes anonim.

## Catatan Keamanan

Flow wajib menerima `GLD_AES128_KEY_HEX`, `PGL_COMMAND_AUTH_TOKEN`, dan token
Admin API Node-RED dari environment/secret store. Jika key kosong, decrypt GLD
dan builder downlink authenticated ditolak eksplisit. Replay state disimpan
atomik ke `PGL_REPLAY_STATE_PATH` agar restart Node-RED tidak membuka replay
window kembali. Deploy memakai API v2/revision checking dan tidak menimpa
credential node lain; credential baru hanya dikirim inline ke node miliknya.

Gunakan `node server/nodered/apply-pertamina-gld-flow.js --check` dan
`powershell -ExecutionPolicy Bypass -File server/nodered/apply-pertamina-gld-dataset-flow.ps1 -Check`
untuk mendeteksi drift antara generator dan flow JSON yang disimpan.

## Compatibility Notes

Sebagian reference Gateway lama tidak sama dengan kontrak final. Jalur final yang dipakai sistem sebenarnya adalah Gateway publish MQTT/LAN ke server, bukan CH/Gateway sebagai AP. Flow ini tetap punya parser untuk bentuk `gateway-event`, tetapi decrypt hanya berjalan bila `payload_hex` berisi:

- encrypted payload 29 byte dengan metadata `node_id`, `seq`, `flags`, atau
- `GLDRecord` lengkap 34 byte, atau
- `AppFrame` lengkap dari kontrak baru.
