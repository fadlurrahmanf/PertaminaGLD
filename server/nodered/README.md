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
  - inject/publish `gld/gateway/cmd/node`
- Inject test vector:
  - `GLD AES-GCM test vector`

## Jalur Output MQTT

- `gld/gateway/status`
- `gld/gateway/events`
- `gld/server/decoded`
- `gld/server/alarm`
- `gld/gateway/error`
- command inject:
  - `gld/gateway/cmd/pull`
  - `gld/gateway/cmd/node`

Pull command mengikuti kontrak CH `SERVER_PULL_REQUEST`: payload berisi
`hopList[]`, bukan GLD `nodeId`. Contoh direct CH bench:

```json
{"requestId":1,"hopList":["0x0064"]}
```

Command GLD/downlink tetap memakai topic berbeda `gld/gateway/cmd/node` dan
boleh membawa `node`.

## Dataset Flow Controls

`apply-pertamina-gld-dataset-flow.ps1` membuat tab `GLD Dataset Server` untuk recorder dan kontrol operator. Flow dataset memiliki inject:

- `START_DATASET clear_air_test` publish ke `gas-leak-detector/F001/dataset`.
- `STOP_DATASET` publish ke `gas-leak-detector/F001/dataset`.

Flow dataset juga listen ke `gas-leak-detector/+/cmd/ack`, `gas-leak-detector/+/dataset/status`, `gas-leak-detector/+/dataset/summary`, `gas-leak-detector/+/dataset/data`, dan `gas-leak-detector/+/nulling/result`.

## Apply Lokal

Contoh dari repo root:

```powershell
node .\server\nodered\apply-pertamina-gld-flow.js `
  --node-red-url "http://127.0.0.1:1880" `
  --gateway-status-url "http://0.0.0.0/disabled-until-gateway-ip-known" `
  --gateway-base-url "http://0.0.0.0" `
  --mqtt-host "127.0.0.1" `
  --mqtt-port 1884
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

Jika broker MQTT butuh auth, pass username/password saat apply lokal. Jangan simpan password produksi di file repo.

Untuk bench 2026-06-17, flow Pertamina membuat broker Aedes sendiri di port `1884`.
Port `1883` di laptop ini sedang dipakai service Mosquitto lama, jadi Gateway firmware
bench `v0.1.2` diarahkan ke `CHANGE_ME_MQTT_HOST:1884`.

## Catatan Keamanan

Flow memakai test key `000102030405060708090A0B0C0D0E0F` jika `GLD_AES128_KEY_HEX` tidak diisi. Ini hanya untuk bench/selftest. Untuk produksi, set key dari environment/secret store.

## Compatibility Notes

Sebagian reference Gateway lama tidak sama dengan kontrak final. Jalur final yang dipakai sistem sebenarnya adalah Gateway publish MQTT/LAN ke server, bukan CH/Gateway sebagai AP. Flow ini tetap punya parser untuk bentuk `gateway-event`, tetapi decrypt hanya berjalan bila `payload_hex` berisi:

- encrypted payload 29 byte dengan metadata `node_id`, `seq`, `flags`, atau
- `GLDRecord` lengkap 34 byte, atau
- `AppFrame` lengkap dari kontrak baru.
