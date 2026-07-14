# GLD Operator Lite Design

Last updated: 2026-07-14 (frontend rebuilt from scratch, see §27)

## 1. Ringkasan

GLD Operator Lite adalah aplikasi operator PC untuk mengoperasikan satu GLD
aktif melalui serial COM dan MQTT dataset. Aplikasi ini menggantikan versi
Electron yang terlalu besar dengan stack ringan:

- `index.html` untuk struktur UI.
- `style.css` (entry) + `css/*.css` untuk instrument-panel theme (lihat §27).
- `js/*.js` (native ES modules, tanpa build step) untuk state UI, parser
  serial, chart, dataset/nulling workflow, mock, dan command orchestration
  (lihat §27 untuk peta modul; sebelumnya satu file `app.js`).
- `bridge.py` untuk fitur lokal yang tidak bisa diakses langsung oleh browser:
  scan COM, serial native, MQTT TCP, WiFi/IP lookup Windows, penyimpanan CSV,
  buka folder output, dan PlatformIO upload orchestration.

Target utama aplikasi ini adalah operator bench Windows yang memakai GLD di
COM port lokal, terutama COM10. UI aplikasi memakai teks English, sedangkan
dokumen teknis dapat memakai Bahasa Indonesia.

## 2. Tujuan

Tujuan V1:

- Menyediakan console operator ringan tanpa bundling Electron/Chromium.
- Menghubungkan PC ke GLD melalui COM serial baud `115200`.
- Menampilkan status GLD, mode, gas, confidence, alarm, power, boot health,
  LoRa, dan telemetry sensor.
- Menjalankan workflow dataset melalui serial mode switch dan MQTT command.
- Menyimpan hasil dataset ke CSV lokal per sesi.
- Menampilkan proses nulling sesuai log firmware: baseline, exponential range,
  binary search, confirm, pass/fail per channel.
- Menyediakan terminal expert untuk command manual.
- Menyediakan upload firmware via PlatformIO yang sudah terpasang di PC.
- Mendukung fallback HTML-only bila bridge tidak aktif, dengan fitur terbatas.

Non-goal V1:

- Bukan aplikasi Electron/desktop bundling besar.
- Bukan database server.
- Bukan Node-RED editor/deployer.
- Bukan MQTT broker penuh untuk produksi (bridge membundel broker QoS0 minimal
  di `local_mqtt_broker.py` khusus untuk bench testing tanpa Node-RED/Mosquitto
  aktif, bukan pengganti broker produksi).
- Bukan compiler firmware custom; upload memakai PlatformIO existing.
- Fleet 1-8 GLD slot didukung sebagai layer ringan (lihat §26): setiap slot
  punya koneksi serial + dataset MQTT sendiri di bridge, tetapi UI tetap
  menampilkan detail penuh hanya untuk satu "active slot" agar operator tidak
  kewalahan mengoperasikan banyak dashboard sekaligus.

## 3. Lokasi File

```text
apps/gld-operator/
  index.html              UI structure
  style.css               Entry point, @imports css/*.css
  css/                    tokens.css, base.css, layout.css, components.css, nulling.css
  js/                     Native ES modules (browser-side app logic), see §27
  bridge.py               Local Python bridge and static file server
  requirements.txt        pyserial and paho-mqtt dependencies
  run-gld-operator.bat    Windows launcher
  README.md               Quick run instructions
  design.md               This document
  output/datasets/        Runtime CSV output, gitignored
  output/logs/            Per-session serial/nulling logs, gitignored
```

File lama Electron/React/TypeScript sudah dihapus dari working tree untuk
mengecilkan ukuran aplikasi. Penghapusan itu memang bagian dari arah lite app.
Per 2026-07-14, `app.js` (satu file monolitik ~3300 baris) juga sudah
dihapus dan digantikan oleh modul-modul di `js/` (lihat §27) — riwayat git
tetap menyimpan versi lama bila diperlukan referensi.

## 4. Cara Menjalankan

Recommended mode:

```powershell
cd D:\PertaminaGLD\apps\gld-operator
python -m pip install -r requirements.txt
.\run-gld-operator.bat
```

Buka:

```text
http://127.0.0.1:5173/
```

Fallback HTML-only:

```powershell
cd D:\PertaminaGLD\apps\gld-operator
python -m http.server 5173 --bind 127.0.0.1
```

Fallback HTML-only hanya cocok untuk UI dasar dan Web Serial. Mode ini tidak
bisa scan COM native, tidak bisa membaca password WiFi Windows, tidak bisa
publish MQTT TCP langsung, tidak bisa menyimpan CSV ke folder app via bridge,
dan tidak bisa upload firmware.

## 5. Arsitektur

```text
Operator
   |
   v
Browser UI: index.html + style.css + app.js
   |
   | HTTP REST + Server-Sent Events
   v
Local Python bridge: bridge.py
   |             |              |              |
   v             v              v              v
Serial COM   MQTT broker    Filesystem     PlatformIO
115200       dataset topics  CSV/logs      firmware upload
   |
   v
GLD firmware
```

### 5.1 Browser UI

Browser UI bertanggung jawab untuk:

- Menyimpan state sementara dalam memory JS.
- Menyimpan field operator non-sensitive di `localStorage`.
- Menggambar chart sensor dengan `<canvas>`.
- Parsing serial JSONL dan legacy logs.
- Mengirim serial command melalui bridge atau Web Serial fallback.
- Membuat CSV telemetry/dataset.
- Menampilkan mock GLD tanpa hardware.

### 5.2 Python Bridge

Bridge bertanggung jawab untuk:

- Serve static UI di `http://127.0.0.1:5173/`.
- Expose REST API lokal.
- Expose Server-Sent Events `/api/events`.
- List COM port via `pyserial`.
- Connect/disconnect/write serial port.
- Publish MQTT dataset command via `paho-mqtt`.
- Subscribe dataset MQTT status/data/summary/ack.
- Simpan dataset CSV ke `output/datasets`.
- Open output folder.
- Jalankan PlatformIO upload di background.

Bridge bukan service permanen Windows. Ia hidup selama `run-gld-operator.bat`
atau proses `python bridge.py` berjalan.

## 6. Runtime Dependencies

Required untuk full feature:

```text
Python 3
pyserial>=3.5
paho-mqtt>=2.1.0
PlatformIO CLI, untuk firmware upload
Browser modern, direkomendasikan Chrome/Edge/Opera
```

MQTT broker harus berjalan terpisah. Default yang dipakai UI:

```text
host: 127.0.0.1
port: 1884
topicRoot: gas-leak-detector
```

## 7. UI Layout

### 7.1 Topbar

Topbar menampilkan:

- Connection badge: `disconnected`, `bridge ready`, `connected`, `mock`, atau
  error state.
- Port aktif.
- Device ID.
- Mode.
- Gas.
- Confidence.
- Alarm badge.
- Tombol `Port Setup`.
- Tombol `Mute Alarm` untuk local sound mute tanpa mengirim clear ke GLD.
- Tombol `Mock GLD`.

### 7.2 Sidebar

Sidebar berisi:

- Fleet panel: kartu "Active GLD" untuk slot yang sedang aktif, ditambah
  daftar dinamis slot lain (1-8 total, lihat §26) dengan ringkasan
  device/port/mode/alarm, tombol "Make Active" dan "Remove" per slot, dan
  tombol "+ Add Slot".
- Commands: `Ping`, `Info`, `Status`, `Poll 1s`.
- Mode: `Running`, `Dataset`, `Nulling`.

### 7.3 Tabs

Tabs utama:

- `Running`
- `Sensor Check`
- `Dataset`
- `Nulling`
- `Log`
- `Expert`
- `Firmware`

## 8. Port Setup dan Serial

Port setup dibuka dari tombol `Port Setup`.

Controls:

- Dropdown COM port.
- `Scan`: memanggil `/api/ports`.
- Manual COM input: default `COM10`, menambahkan option manual saat scan tidak
  menemukan port USB.
- `Use Manual`: memilih manual COM override.
- `Connect Serial`: memanggil `/api/serial/connect`.
- `Disconnect`: memanggil `/api/serial/disconnect`.

Default:

```text
baud: 115200
preferred port: COM10, jika ada
manual fallback: COM10
```

Setelah connect, app mengirim handshake ringan:

```text
APP_PING
GET_INFO
GET_STATUS
```

Jika bridge mati, `Scan` akan mencoba `initBridge()` ulang. Jika tetap gagal,
log akan menampilkan:

```text
PORT_SCAN_SKIPPED bridge is not reachable at http://127.0.0.1:5173
```

## 9. Serial Protocol yang Dipakai App

App memprioritaskan prefixed JSONL:

```text
GLD_INFO_JSON {...}
GLD_STATUS_JSON {...}
GLD_CMD_ACK_JSON {...}
```

Command yang dikirim app:

```text
APP_PING
GET_INFO
GET_STATUS
SET_MODE inference
SET_MODE dataset
SET_MODE nulling
SET_APP_CONFIG_JSON {...}
SET_DEVICE_ID_JSON {...}
```

Parser juga mendukung legacy line:

```text
GLD_MODE=...
GLD_ML_RESULT ... gasClass=... confidence=...
DATASET_...
NULLING_...
```

## 10. Running View

Running view menampilkan:

- Device ID dan firmware.
- Mode dan power mode.
- Gas dan confidence.
- LoRa status dan battery.
- Chart sensor telemetry.
- Power detail.
- Boot health: ADS, MCP, DAC, ML.

Chart:

- Source: `GLD_STATUS_JSON.telemetry.sensorVoltage`.
- Label channel dari `featureOrder`, fallback `MQ8`, `MQ135`, `MQ3`, `MQ5`,
  `MQ4`, `MQ7`, `MQ6`, `MQ2`.
- Range pilihan:
  - 10 sec
  - 30 sec
  - 1 min
  - 5 min
  - 10 min
  - 30 min
  - 1 hour
- Data lama dipruning sesuai selected range.
- `Clear` menghapus history chart.
- `Export CSV` mengekspor telemetry running dari memory browser.

Running CSV columns:

```text
timeIso, deviceId, mode, gasName, gasClass, confidence, alarm,
MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2
```

Running CSV memakai sensor order eksplisit yang sama dengan firmware default.

## 10A. Sensor Check View

Sensor Check tab menampilkan visual kartu CH1-CH8 seperti Nulling, tetapi
fokusnya mengecek apakah sensor MQ terpasang/terbaca.

Input utama:

- `GLD_STATUS_JSON.telemetry.sensorVoltage[8]`
- `GLD_STATUS_JSON.telemetry.sensorGain[8]`
- `GLD_STATUS_JSON.telemetry.sensorStatus[8]`
- `GLD_STATUS_JSON.telemetry.featureOrder[8]`
- `GLD_STATUS_JSON.bootHealth.adsReady`
- `GLD_STATUS_JSON.bootHealth.mcpOkCount`
- Optional future fields: `bootHealth.sensorPresent`, `bootHealth.mqPresent`,
  `bootHealth.sensorHealth`, atau field sejenis di root status.

Status kartu:

```text
Present   firmware reports present, or voltage+gain readable while ADS ready
Missing   firmware reports missing/not installed
Fault     firmware reports fault/error
Check     MCP ready count is below that channel
Read Only voltage seen but ADS health is not ready
Unknown   no usable status yet
```

Firmware `sensorStatus` mapping dari `GldAds1256Status`:

```text
0 Ok             -> Present
1 NotReady       -> Not Ready
2 DrdyTimeout    -> Fault
3 InvalidChannel -> Fault
```

Controls:

- `Refresh Status`: mengirim `GET_STATUS`.
- `Clear`: menghapus status lokal sensor check.

## 11. Dataset Workflow

Dataset tab terdiri dari:

- Dataset Parameters.
- WiFi and MQTT config.
- Dataset Session Monitor.
- Latest rows table.

### 11.1 Parameter Dataset

Field:

```text
label
target_samples
sample_interval_ms
max_duration_ms
use_fan_intake = true
fan_on_ms
post_fan_settle_ms
run_nulling_first
```

UI field:

```text
Label
Target Samples
Interval Ms
Max Duration Ms
Fan On Ms
Post Fan Settle Ms
Run nulling before dataset
```

Default `Run nulling before dataset` adalah OFF dan sengaja tidak disimpan ke
`localStorage`, supaya setiap reload kembali ke OFF.

### 11.2 Nulling Before Dataset

Keputusan desain terbaru:

- `Start Dataset` default tidak menjalankan nulling.
- Jika checkbox OFF, app mengirim `SET_MODE dataset`, memberi waktu mode switch,
  lalu publish `START_DATASET` dengan `run_nulling_first=false`.
- Jika checkbox ON, app switch ke mode nulling:

```text
SET_MODE nulling
```

Lalu app tidak publish `START_DATASET` dulu. Operator menunggu nulling PASS,
lalu start dataset lagi dengan checkbox OFF.

Firmware GLD dataset mode juga sudah diubah agar tidak auto-run nulling saat
masuk dataset mode. Jika nulling profile kosong, firmware akan menolak
`START_DATASET` dengan:

```text
reject_no_profile
```

Operator harus menjalankan nulling eksplisit terlebih dahulu.

### 11.3 WiFi and MQTT Config

WiFi/MQTT is dataset-only. Running/Inference must stay on serial + LoRa and the
firmware explicitly turns WiFi off in that mode. Nulling is also offline. These
fields therefore live only in the Dataset tab and are applied for the next
dataset workflow.

Field:

```text
WiFi SSID
WiFi Password
MQTT Host
MQTT Port
MQTT User
MQTT Password
Topic Root
```

`Use this PC`:

- Dengan bridge aktif: membaca SSID aktif, password WiFi tersimpan Windows, dan
  IPv4 lokal via `/api/network`.
- Tanpa bridge: fallback mengisi MQTT host dari hostname browser, tapi tidak
  bisa membaca SSID/password Windows.

`Apply GLD Settings` mengirim:

```text
SET_APP_CONFIG_JSON {
  "ssid": "...",
  "password": "...",
  "mqttHost": "...",
  "mqttPort": 1884,
  "mqttUser": "...",
  "mqttPass": "...",
  "topicRoot": "gas-leak-detector",
  "reboot": true
}
```

GLD diharapkan menyimpan config dan reboot.

### 11.4 Publish START/STOP Dataset

Bridge publish ke topic:

```text
{topicRoot}/{deviceId}/dataset
```

Payload START:

```json
{
  "cmd": "START_DATASET",
  "label": "clear_air_test",
  "target_samples": 100,
  "sample_interval_ms": 1000,
  "max_duration_ms": 0,
  "run_nulling_first": false,
  "use_fan_intake": true,
  "fan_on_ms": 1000,
  "post_fan_settle_ms": 0
}
```

Payload STOP:

```json
{
  "cmd": "STOP_DATASET"
}
```

### 11.5 Dataset MQTT Monitor

Saat START dipublish, bridge juga subscribe:

```text
{topicRoot}/{deviceId}/cmd/ack
{topicRoot}/{deviceId}/dataset/status
{topicRoot}/{deviceId}/dataset/data
{topicRoot}/{deviceId}/dataset/summary
```

Event dikirim ke UI melalui Server-Sent Events:

```text
dataset_monitor
dataset_mqtt
mqtt_publish
dataset_saved
```

### 11.6 Dataset Session Monitor

Monitor menampilkan:

- Status.
- Phase/detail.
- Progress.
- Elapsed time.
- Row count.
- Last sample time.
- Output filename.
- Output path.
- Last event.
- Operator hint.
- Latest 20 rows.

Status penting:

```text
Idle
Starting
Command Sent
Command ACK
Capturing
Waiting Data
Needs Nulling
Nulling First
Stopping
Done
Error
```

`Waiting Data` muncul bila session aktif tapi belum ada rows setelah beberapa
detik, atau GLD melaporkan dataset `idle`. Hint mengarahkan operator untuk
mengecek:

- START_DATASET ACK.
- Device ID.
- Topic root.
- MQTT host.
- Nulling profile.
- Mode GLD dataset.

### 11.7 Dataset Row Sources

Dataset row bisa masuk dari:

- MQTT `dataset/data`.
- Serial fallback `DATASET_RECORD`.
- Serial status fallback `GLD_STATUS_JSON` ketika mode dataset dan telemetry
  valid.

Normalized row fields:

```text
timeIso
source
device_id
node_id
mode
seq
timestamp_ms
label
nulling_profile_id
sensor_voltage[8]
sensor_gain[8]
feature_order[8]
```

Dedup key:

```text
source:device_id:seq
```

Jika `seq` kosong, fallback key memakai timestamp dan row index.

### 11.8 Dataset CSV

CSV headers:

```text
timeIso
source
device_id
node_id
mode
seq
timestamp_ms
label
nulling_profile_id
sv_MQ8
sv_MQ135
sv_MQ3
sv_MQ5
sv_MQ4
sv_MQ7
sv_MQ6
sv_MQ2
gain_MQ8
gain_MQ135
gain_MQ3
gain_MQ5
gain_MQ4
gain_MQ7
gain_MQ6
gain_MQ2
feature_1
feature_2
feature_3
feature_4
feature_5
feature_6
feature_7
feature_8
```

Output folder default:

```text
D:\PertaminaGLD\apps\gld-operator\output\datasets
```

Filename:

```text
{DeviceId}_{Label}_{YYYYMMDDTHHMMSS}.csv
```

Controls:

- `Save CSV`: simpan via bridge ke output folder.
- `Download CSV`: browser download.
- `Open Folder`: buka output folder via OS.
- `Clear Session`: reset state monitor.

Jika bridge tidak aktif, `Save CSV` tidak bisa menyimpan ke folder app, tetapi
`Download CSV` tetap bisa berjalan dari browser.

## 12. Nulling Workflow

Nulling tab harus mempertahankan tampilan visual, bukan hanya terminal log.

View terdiri dari:

- Tombol `Switch to Nulling`.
- Tombol `Clear`.
- Summary line.
- Retry/attempt metadata.
- 8 channel cards.
- Raw Nulling Log.

Firmware log yang diparse:

```text
NULLING_SERVICE_START
NULLING_CH_START
NULLING_BASELINE_START
NULLING_BASELINE_STEP
NULLING_BASELINE_DONE
NULLING_EXP_START
NULLING_EXP_STEP
NULLING_EXP_RANGE
NULLING_BIN_START
NULLING_BIN_STEP
NULLING_BIN_DONE
NULLING_CONFIRM_START
NULLING_CONFIRM_STEP
NULLING_CONFIRM_OK
NULLING_CH_OK
NULLING_CH_FAIL
NULLING_SERVICE_DONE
NULLING_RUN_DONE
NULLING_RUNTIME_RESULT
NULLING_AUTO_MODE_SWITCH
```

Card per channel menampilkan:

- Channel `CH1..CH8`.
- Sensor name dari `featureOrder`, fallback sensor order default.
- Stage:
  - Waiting
  - Start
  - Baseline
  - Exponential
  - Binary
  - Confirm
  - Done
  - Failed
- Detail singkat.
- DAC code.
- Baseline.
- After voltage.

Tone visual:

```text
idle
active
pass
fail
```

Mock GLD mengemulasi proses nulling bertahap untuk semua 8 channel agar UI bisa
dites tanpa hardware.

### 12.1 Per-Channel Stage Detail (added 2026-07-14)

Setiap channel card punya `<details>` "Stage detail" (collapsed by default,
expand state persists across re-render via `state.nullingExpandedChannels`)
yang menjabarkan tiap tahap secara terpisah, bukan hanya satu baris ringkasan:

- **Baseline**: jumlah sample rata-rata per code, rentang code yang di-scan,
  jumlah step yang tercatat, nilai baseline akhir, jumlah sample valid.
- **Exponential**: baseline referensi, threshold target, jumlah step
  (doubling code), code terakhir yang dicoba, dan bracket `[low, high]` yang
  ditemukan (atau pesan FAILED dengan code terakhir/maksimum jika gagal).
- **Binary search**: bracket awal, jumlah step penyempitan, code terpilih.
- **Confirm**: jendela code yang di-scan (`start`-`end`, wide/normal),
  jumlah kandidat threshold ditemukan, code+voltage terpilih, dan penjelasan
  mode (`baseline_threshold_verified`) dalam bahasa biasa.
- **DAC source**: baris eksplisit menandai dari tahap mana kode DAC final
  berasal, misalnya "Confirm stage chose code 451 (baseline-relative threshold,
  re-verified) -> final DAC code 451", termasuk jumlah *final bump* (+1 LSB)
  jika firmware melakukan penyesuaian setelah confirm.

Semua data ini diparse dari field yang sudah dikirim firmware
(`GldNullingService.cpp`) tapi sebelumnya tidak ditampilkan terstruktur di
UI, hanya ada di Raw Nulling Log mentah. Mock GLD tidak mengirim semua field
(mis. `threshold`, `baseline` di `NULLING_EXP_START`), jadi field yang hilang
tampil sebagai `?` saat mode mock — ini normal, bukan bug.

## 13. Expert Terminal

Expert terminal menyediakan raw command input.

Saat awal:

- Input disabled.
- Tombol `Send` disabled.

Operator klik `Unlock` untuk mengaktifkan input. Saat ini unlock masih local
UI-only, belum memakai PIN.

Contoh command manual:

```text
APP_PING
GET_INFO
GET_STATUS
SET_MODE inference
SET_MODE dataset
SET_MODE nulling
```

Catatan keamanan: karena belum ada PIN, terminal expert harus dianggap fitur
bench/debug, bukan final production lock.

## 14. Firmware and ID Tab

Firmware tab menyediakan:

- `Load Manifest`: membaca file `.json` lokal, mengisi env/package ID, dan
  menampilkan preview.
- `Upload Firmware`: memanggil bridge `/api/firmware/upload`.
- `Inject ID`: mengirim `SET_DEVICE_ID_JSON`.

Fields:

```text
PlatformIO Env
Target GLD ID
Package Device ID
Manifest File
Manifest Preview
```

Upload command bridge:

```powershell
pio run -e {env} -t upload --upload-port {port}
```

Jika manifest dimuat, UI dan bridge memvalidasi:

- `env` atau `environment` harus sesuai field `PlatformIO Env`.
- `deviceId` manifest boleh `F000` sebagai package dummy, atau harus sama
  dengan `Target GLD ID`.
- `chip` atau `chipFamily` harus ESP32-S3.
- `flashFiles`, jika ada, harus berupa list.

Setelah upload sukses dan target ID valid, bridge mencoba reconnect serial dan
mengirim:

```text
SET_DEVICE_ID_JSON {"deviceId":"F001","reboot":true}
```

Current known issue:

- Upload ke COM10 pernah gagal karena chip stopped responding dan kemudian
  COM10 locked/busy. Port harus dilepas/replug sebelum retry.
- `firmware/platformio.ini` sudah diturunkan ke `upload_speed = 57600` untuk
  env `gld` agar CH340 lebih stabil.
- Upload belum dianggap sukses sampai PlatformIO mengembalikan code `0`.

## 15. Bridge REST API

### 15.1 GET `/api/health`

Response:

```json
{
  "ok": true,
  "version": "0.2.0-lite-bridge",
  "features": {
    "serial": true,
    "mqtt": true,
    "datasetMonitor": true,
    "datasetOutput": true,
    "networkInfo": true,
    "firmwareUpload": true
  },
  "errors": {
    "serial": "",
    "mqtt": ""
  }
}
```

### 15.2 GET `/api/ports`

Returns:

```json
{
  "ports": [
    {
      "path": "COM10",
      "description": "USB-SERIAL CH340 (COM10)",
      "manufacturer": "wch.cn",
      "serialNumber": "",
      "vendorId": 6790,
      "productId": 29987
    }
  ]
}
```

### 15.3 GET `/api/network`

Windows-only helper:

```json
{
  "ssid": "...",
  "password": "...",
  "ipv4": "192.168.x.x"
}
```

### 15.4 GET `/api/dataset/output-dir`

Returns output folder path and creates it if needed.

### 15.5 GET `/api/events`

Server-Sent Events stream.

Events:

```text
serial_line
serial_tx
serial_status
serial_error
upload_start
upload_line
upload_done
upload_error
mqtt_publish
dataset_monitor
dataset_mqtt
dataset_saved
```

### 15.6 POST `/api/serial/connect`

Request:

```json
{
  "port": "COM10",
  "baud": 115200
}
```

### 15.7 POST `/api/serial/disconnect`

Disconnect current serial.

### 15.8 POST `/api/serial/write`

Request:

```json
{
  "line": "GET_STATUS"
}
```

Bridge appends newline if needed.

### 15.9 POST `/api/mqtt/dataset`

Publishes START/STOP dataset command and starts dataset monitor for START.

### 15.10 POST `/api/mqtt/dataset-monitor/stop`

Stops current dataset MQTT monitor.

### 15.11 POST `/api/dataset/save`

Request:

```json
{
  "filename": "F001_clear_air_test_20260701T120000.csv",
  "csv": "..."
}
```

### 15.12 POST `/api/dataset/open-folder`

Opens dataset output folder in OS file explorer.

### 15.13 POST `/api/firmware/upload`

Request:

```json
{
  "env": "gld",
  "port": "COM10",
  "targetDeviceId": "F001",
  "slot": 1
}
```

### 15.14 GET `/api/serial/port-status?port=COM10`

Preflight check: returns `{port, free, lockedByApp, message}`. Used before
firmware upload and by the Firmware tab's "Check COM Lock" button.

### 15.15 POST `/api/mqtt/test`

Body `{host, port, username, password}`. Attempts a short-lived MQTT connect
and reports `{ok, host, port, latencyMs}` or `{ok:false, message}`.

### 15.16 POST `/api/session/log`

Body `{filename, text}`. Appends a session's accumulated serial or nulling log
to `output/logs/<filename>`. Called automatically when a dataset session ends
and when nulling reports a final result; also available via the Log tab's
"Save Log to Disk" button.

Endpoints marked in §15.6-§15.13 as acting on serial/MQTT/firmware all accept
an optional `slot` field (default `1`) — see §26 for the multi-slot bridge
architecture.

## 16. Local Storage

Browser stores non-sensitive operational fields:

```text
datasetLabel
targetSamples
sampleIntervalMs
maxDurationMs
fanOnMs
postFanSettleMs
wifiSsid
mqttHost
mqttPort
mqttUser
topicRoot
firmwareEnv
targetDeviceId
```

Also stored (added 2026-07-14):

- `gldOperatorWeb.pinHash` — SHA-256 hex of the local Expert/Firmware PIN
  (never the PIN itself).
- `gldOperatorWeb.timeouts` — JSON `{serialResponseMs, datasetReadyMs,
  datasetStuckMs}` overrides for the Timeout Settings panel (Expert tab).

Not stored:

- WiFi password.
- MQTT password.
- `Run nulling before dataset` checkbox.
- Serial logs (persisted to disk per-session instead, see §15.16).
- Dataset rows.
- Expert/Firmware unlock state (PIN must be re-entered each page load).

## 17. Mock GLD

Mock mode is built into `app.js` for UI testing without hardware.

Mock supports:

- `GET_INFO`
- `APP_PING`
- `GET_STATUS`
- `SET_MODE`
- `SET_DEVICE_ID_JSON`
- `SET_APP_CONFIG_JSON`
- Dataset capture when `START_DATASET` is clicked.
- Nulling staged logs when mode is `nulling`.

Mock limitations:

- Does not use real serial.
- Does not use real MQTT.
- Does not validate firmware timing.
- Does not prove hardware behavior.

## 18. Security and Safety

Current safety controls:

- Serial connect/disconnect explicit.
- Firmware upload asks browser `confirm()`.
- Firmware upload validates loaded manifest against selected env, target ID,
  chip family, and `flashFiles` shape.
- Firmware upload preflight: disconnects serial, re-probes the target COM
  port, and aborts with guidance if it is still busy after disconnect (§15.14,
  §20.4).
- Apply GLD settings asks browser `confirm()`.
- Inject ID asks browser `confirm()`.
- Expert terminal and Firmware Upload/Inject ID are locked behind a local PIN
  (SHA-256 hash in `localStorage`, set on first use, re-verified every page
  load — see §16). Not enterprise auth, a deterrent against accidental bench
  mistakes.
- Dataset nulling-first default OFF to avoid unintended nulling.
- Cross-slot COM port conflicts are rejected by the bridge (§26): two slots
  cannot claim the same physical port.

Known safety gaps:

- Bridge has permissive CORS and is intended for localhost bench only.
- MQTT credentials are not encrypted; password fields are not persisted.
- No authentication on local bridge (the PIN lock is UI-side only; the bridge
  REST API itself still trusts any same-origin caller).
- Firmware manifest validation checks shape/identity fields, not actual flash
  file checksums.

Recommended production hardening:

- Bind bridge to `127.0.0.1` only, keep current default.
- Reject upload if manifest device profile does not match connected GLD.
- Add checksum validation of manifest `flashFiles` against the actual files
  on disk.
- Consider bridge-level auth (e.g. a session token) if the bridge is ever
  exposed beyond localhost.

## 19. Operational Flows

### 19.1 Normal Connect

```text
Start bridge
Open http://127.0.0.1:5173/
Port Setup
Scan
Select COM10
Connect Serial
APP_PING / GET_INFO / GET_STATUS sent automatically
Start Poll 1s if continuous status is needed
```

### 19.2 Running Monitor

```text
Connect Serial
Poll 1s
Open Running tab
Select chart range
Clear chart if needed
Export CSV if needed
```

### 19.3 Dataset Without Nulling

```text
Connect Serial
Apply GLD Settings if WiFi/MQTT changed
Switch to Dataset
Confirm GLD returns DATASET_READY or status dataset
Keep Run nulling before dataset OFF
Start Dataset
Watch ACK/status/data rows
Stop Dataset or wait autostop
Save CSV
Open Folder
```

If monitor shows `Needs Nulling` or ACK `reject_no_profile`, run nulling once.

### 19.4 Dataset With Explicit Nulling First

```text
Connect Serial
Open Dataset tab
Enable Run nulling before dataset
Start Dataset
App switches to Nulling tab and sends SET_MODE nulling
Wait for PASS/PARTIAL/FAIL
After PASS, return to Dataset tab
Disable Run nulling before dataset
Start Dataset
```

### 19.5 Firmware Upload

```text
Close/disconnect any serial monitor or app serial connection
Select COM10
Select env gld
Optional: set Target GLD ID
Upload Firmware
Watch Log tab
Wait for UPLOAD_DONE code=0
```

If upload fails with COM busy:

```text
Close GLD Operator browser tab or click Disconnect
Stop bridge if needed
Unplug/replug GLD USB
Confirm pio device list shows COM10
Retry upload
```

## 20. Failure Modes

### 20.1 Scan COM Tidak Muncul

Likely causes:

- Bridge not running.
- Browser opened fallback static server instead of bridge.
- `/api/health` unreachable.
- `pyserial` missing.

Checks:

```powershell
Invoke-RestMethod http://127.0.0.1:5173/api/health
Invoke-RestMethod http://127.0.0.1:5173/api/ports
```

Fix:

```powershell
cd D:\PertaminaGLD\apps\gld-operator
.\run-gld-operator.bat
```

Then reload browser page.

### 20.2 COM10 Busy

Likely causes:

- Browser Web Serial still holds port.
- Bridge serial still connected.
- PlatformIO upload process still running.
- Driver did not release after failed flash.

Checks:

```powershell
mode COM10
pio device list
Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'pio|python|esptool|platformio' }
```

Fix:

```text
Click Disconnect in app.
Close GLD Operator browser tab.
Stop bridge process.
Unplug/replug GLD USB if Windows still says Access denied.
```

### 20.3 Dataset Tidak Maju

Likely causes:

- GLD not in dataset mode.
- MQTT broker not reachable from GLD.
- Topic root or device ID mismatch.
- START_DATASET ACK not received.
- Nulling profile missing, ACK `reject_no_profile`.
- Firewall blocks MQTT port.

App signs:

```text
Waiting Data
Needs Nulling
No dataset samples yet
GLD reports dataset idle
```

### 20.4 Firmware Upload Fails Mid Flash

Observed error:

```text
A fatal error occurred: The chip stopped responding.
```

Mitigations:

- Lower upload speed.
- Use shorter USB cable.
- Avoid USB hub.
- Ensure board power is stable.
- Manually hold BOOT if connection phase fails.
- Replug board if COM locks after failure.

Current `env:gld` upload speed:

```text
upload_speed = 57600
```

## 21. Test Strategy

### 21.1 Static Checks

```powershell
node --check apps\gld-operator\app.js
python -m py_compile apps\gld-operator\bridge.py
```

### 21.2 Firmware Host Tests

```powershell
python firmware\tests\run_tests.py
```

Last known result during app changes:

```text
31/31 tests passed
```

### 21.3 Bridge Checks

```powershell
Invoke-RestMethod http://127.0.0.1:5173/api/health
Invoke-RestMethod http://127.0.0.1:5173/api/ports
Invoke-RestMethod http://127.0.0.1:5173/api/dataset/output-dir
```

### 21.4 Browser Mock Acceptance

Expected:

- App loads without console error.
- Checkbox `Run nulling before dataset` default OFF.
- Mock GLD ON.
- Start Dataset with checkbox OFF captures rows.
- Start Dataset with checkbox ON switches to Nulling First and does not add
  dataset rows.
- Nulling tab shows 8 channel cards.
- Chart range/clear work.
- No horizontal overflow at 1280px width.

### 21.5 Hardware Acceptance

Requires explicit operator approval and free COM10:

- `pio device list` sees COM10.
- App scan sees COM10.
- Connect serial.
- `GET_INFO` returns `GLD_INFO_JSON`.
- `GET_STATUS` returns `GLD_STATUS_JSON`.
- Running chart receives telemetry.
- Switch dataset.
- Start dataset with nulling-first OFF.
- If `reject_no_profile`, run nulling explicitly.
- Dataset rows arrive.
- Save CSV.
- Verify CSV file in output folder.

## 22. Current Known State

As of 2026-07-14:

- Bridge can run and `/api/ports` returns COM9/COM10 (bench-dependent) when
  bridge is alive; verified live against a real GLD on COM9.
- Bridge is now multi-slot (see §26): `serial_bridges`/`dataset_monitors` are
  keyed by slot id 1-8 instead of a single global instance. Slot 1 remains the
  default for all existing single-device flows.
- Bridge status indicator, Expert/Firmware PIN lock, upload preflight + COM
  lock visibility, dataset session ID + per-session log persistence,
  configurable timeouts, MQTT reachability test, and a real Fleet panel
  (add/remove/switch up to 8 slots) are implemented (§23 High/Medium priority
  items below are now done).
- Firmware host tests pass 34/34.

## 23. Roadmap

Done (2026-07-14 overhaul):

- Bridge status indicator with reconnect-after-downtime (topbar `bridge: ok /
  unreachable / reconnecting` badge, auto re-init on recovery).
- Explicit COM lock status before upload (`GET /api/serial/port-status`,
  "Check COM Lock" button on Firmware tab).
- Upload preflight: disconnect serial, re-probe the port, abort with guidance
  if still busy.
- Expert/Firmware PIN lock (local SHA-256 PIN via `window.prompt`, gates
  Expert terminal unlock and Firmware Upload/Inject ID).
- Visible `reject_no_profile` action button: "Run Nulling Now" on the Dataset
  tab, switches to Nulling and sends `SET_MODE nulling`.
- Persist raw serial/nulling logs per session to disk (`POST /api/session/log`
  -> `output/logs/`).
- Session ID added to dataset CSV rows and the `START_DATASET` MQTT payload
  (`session_id`, additive field).
- MQTT broker reachability test button (`POST /api/mqtt/test`) on the Dataset
  tab.
- Multi-device architecture for 1-8 GLD slots (§26): bridge-side real,
  frontend uses a lightweight Fleet registry + single "active slot" detail
  view rather than N parallel dashboards, by design (see §26 rationale).

Remaining / not yet done:

- Stricter manifest validation against actual flash files/checksums (still
  only validates env/deviceId/chip/flashFiles shape, not checksums).
- Package as portable folder with Python runtime optional.
- Add service wrapper for bridge.
- Add richer chart downsampling for very long sessions.
- Add app-side settings export/import.
- Firmware upload retry guidance is partially covered by the preflight error
  message; a dedicated in-UI retry wizard is not implemented.

## 24. Design Decisions

- Browser + Python bridge was chosen to keep app far below 200 MB and avoid
  Electron bundle size.
- The bridge owns native OS features; UI remains static and simple.
- Dataset nulling-first is explicit and default OFF because automatic nulling
  surprised the operator and can delay dataset capture.
- Dataset CSV is file-based, no SQLite in V1.
- MQTT is used only for dataset command/data path in V1.
- Raw serial log remains in memory/browser download for now.
- Mock GLD remains built-in because it catches UI regressions quickly without
  hardware.

## 25. Acceptance Definition for V1 Lite

V1 lite is acceptable when:

- App starts from `run-gld-operator.bat`.
- `/api/health` is OK.
- `/api/ports` sees COM10.
- UI can connect serial and request `GET_INFO`/`GET_STATUS`.
- Running chart updates from telemetry.
- Dataset workflow gives clear status, rows, and CSV output.
- Nulling workflow shows visual CH1-CH8 progress.
- Expert terminal can send manual commands after unlock.
- Firmware tab can launch PlatformIO upload when COM port is free.
- Documentation describes current limitations honestly.

## 26. Multi-Device Architecture (1-8 GLD Slots)

Added 2026-07-14. Two design options were considered: (a) a full rewrite where
every tab renders N independent GLD dashboards side by side, or (b) keep the
existing single-detail-view UX and back it with a slot-indexed connection
layer. Option (b) was chosen: rendering 8 full dashboards at once would work
against the "efficient, not rumit" requirement this overhaul was scoped
around, and a full state-model rewrite of `app.js` (one flat global `state`
object touched by ~150 functions) carried much higher regression risk for a
tool that bench operators depend on daily, with only one physical GLD unit
available to validate against.

### Bridge (`bridge.py`)

- `SerialBridge` and `DatasetMqttMonitor` are no longer module-level
  singletons. `serial_bridges: dict[int, SerialBridge]` and
  `dataset_monitors: dict[int, DatasetMqttMonitor]` hold one instance per slot
  (1-8), created lazily via `get_serial_bridge(slot)` / `get_dataset_monitor(slot)`.
- Every event a `SerialBridge`/`DatasetMqttMonitor` emits is tagged with
  `"slot": <id>` so the frontend can demux `/api/events` SSE traffic per slot.
- REST endpoints that act on serial/MQTT/firmware (`/api/serial/connect`,
  `/api/serial/disconnect`, `/api/serial/write`, `/api/mqtt/dataset`,
  `/api/mqtt/dataset-monitor/stop`, `/api/firmware/upload`) accept an optional
  `slot` field in the JSON body, defaulting to `1` for backward compatibility.
- `/api/serial/connect` rejects connecting a second slot to a COM port already
  held by another slot (`"<port> is already connected on slot <n>"`).
- `/api/health` reports `maxSlots: 8` and `slots: {"<id>": {...status}}` for
  every currently-connected slot.
- `firmware_upload` resolves whichever slot currently holds the target port
  (falling back to the requesting slot) so upload preflight/reconnect acts on
  the right serial instance.

### Frontend (`app.js`)

- The existing flat `state` object is unchanged and continues to represent
  the currently **active slot** exactly as before Phase 4 — every existing
  render/parse function keeps working against it with zero modification.
- A separate, lightweight `state.fleet[slot] = {port, deviceId, mode, gas,
  alarm, connected}` registry tracks summary info for every slot the operator
  has added, including backgrounded ones.
- `serial_line`/`serial_status`/`serial_tx`/`serial_error` SSE listeners check
  the event's `slot` field: events for the active slot flow through the full
  existing pipeline (`handleLine`, etc.) unchanged; events for background
  slots update only `state.fleet` via the lightweight `updateFleetFromLine()`.
- The sidebar Fleet panel (`index.html`) shows the active slot's existing
  "Active GLD" card plus a dynamic list of other slots with a
  device/port/mode/alarm summary, a "Make Active" button (calls
  `setActiveSlot()`, which resets the detail view via the existing
  `resetDeviceSnapshot()` and re-requests `GET_INFO`/`GET_STATUS` for the new
  active slot), and a "Remove" button. "+ Add Slot" (up to 8) creates a new
  slot, makes it active, and opens Port Setup so the operator can connect a
  GLD to it.
- A background slot's alarm is visually surfaced (`.fleet-card.alarm`, red
  accent) in the sidebar even while a different slot is active, so an alarm
  on a backgrounded GLD is not missed.
- Only one physical GLD unit was available to validate this against; slot 1
  was exercised against real hardware on COM9, and additional-slot behavior
  (fleet rendering, active-slot switching, alarm surfacing, cross-slot port
  conflict rejection) was verified via direct function calls and a second
  bridge-level connect attempt to the same port, not a second physical unit.

## 27. Frontend Rebuild From Scratch (2026-07-14)

The user asked for the frontend (`index.html`/`app.js`/`style.css`) to be
rebuilt from zero with a distinctive visual design, keeping full feature
parity with everything above (§1-§26) and the exact same `bridge.py` REST/SSE
contract. `bridge.py`, `local_mqtt_broker.py`, `requirements.txt`, and
`run-gld-operator.bat` were **not** touched — only the browser-side code and
its visual language changed.

### 27.1 Why a new visual design

The previous theme (near-black background + a single acid-green accent) is
one of the generic "AI-default" looks — not wrong, but not motivated by this
app's actual subject. The rebuild instead draws from real gas-detector
instrument panels and lab oscilloscopes, since this is literally a bench
diagnostic console for a gas-leak sensor:

- **Color** — warm near-black chassis (`--panel-black #14110d`), amber
  phosphor accent for live/active state (`--phosphor-amber #ffa400`, the
  color of 7-segment gas meters and CRT phosphor), a cool cyan for passive
  data (`--signal-cyan #4fd8e0`), and `--hazard-red #ff3b30` reserved
  **exclusively** for alarms — never used decoratively, so the operator's
  eye stays trained to react to it (mirrors real safety-equipment
  convention: red = alarm only).
- **Type** — `Bahnschrift` for display/labels (a condensed variable font that
  ships with every Windows 10/11 machine, this app's documented target OS —
  distinctive and zero-cost, no bundled/CDN fonts), `Cascadia Mono`/
  `ui-monospace` for telemetry/DAC-code readouts (tabular figures, reads like
  a real instrument display), system `Segoe UI` for body chrome.
- **Signature element** — each Nulling channel card has a "sweep meter": a
  live horizontal bar showing the DAC code's position within its current
  search bracket (exponential range / binary bisection / confirm window),
  with a thin amber needle at the most recently tried code. This visualizes
  the actual binary-search algorithm rather than decorating the card; see
  `.sweep-meter` in `css/nulling.css` and `sweepMeterState()`/
  `renderSweepMeter()` in `js/nulling.js`.
- Everything else stays disciplined: hairline borders, no gradients/
  glassmorphism, motion limited to the alarm-badge pulse and the sweep meter
  itself.

### 27.2 Why native ES modules, no build step

The "keep it light, no build tooling, stays easy to `git push`" constraint
from the earlier overhaul carried over. Browsers load `<script type="module">`
and `import`/`export` natively; `bridge.py`'s `SimpleHTTPRequestHandler`
already serves any static path under `APP_DIR`, so a `js/` and `css/`
subfolder needed zero backend changes. No `npm install`/build step exists or
is required to run the app.

### 27.3 Module map

```text
apps/gld-operator/js/
  state.js             Central mutable `state`/`elements` + shared constants (single source of truth)
  ui.js                $, setText/setBadge, showBanner/hideBanner, withBusy, tab switching, form save/load
  bridge-client.js      bridgeFetch, SSE wiring, health poll+reconnect, port scan/select, connect/disconnect
  security.js           Local PIN lock (SHA-256, gates Expert + Firmware actions)
  serial-protocol.js    handleLine + JSONL/legacy parsing, boot diagnostics, Sensor Check rendering, alarm, sendCommand/poll
  chart.js              Canvas telemetry chart, legend, CSV export
  nulling.js            Nulling log parsing, per-stage detail, signature sweep meter
  dataset.js            Dataset session state machine, CSV building, MQTT publish, session log persistence
  firmware.js           Manifest load/validate, upload flow, COM-lock preflight, device ID injection
  fleet.js              Multi-slot state.fleet registry, Fleet panel rendering, slot add/switch/remove
  mock.js               Mock GLD simulator (feature parity; not used to verify this rebuild)
  main.js               Entry point (`type="module"`): wires DOM events, bootstrap()
```

Every module exports what other modules need and imports `state`/`elements`
from `state.js` (both are plain objects, so the same reference is shared
everywhere they're imported). Several module pairs import each other
(e.g. `bridge-client.js` <-> `serial-protocol.js`, `serial-protocol.js` <->
`nulling.js`/`dataset.js`) — this is safe in ES modules as long as the
circular bindings are only used inside function bodies, never at a module's
top-level evaluation, which holds throughout this codebase (every export here
is a function declaration or a plain data constant).

The rebuild ported existing, already-proven logic (serial JSONL parsing,
dataset state machine, nulling log parsing, PIN hashing, multi-slot wiring)
into its new module home essentially verbatim — the actual rebuild effort
went into module boundaries, `index.html` markup, and the new `css/*.css`
design system, not reinventing business logic. `firmware/tests/test_shared_
protocol.py::test_gld_unified_runtime_scaffolds_present` hardcodes literal
snippets from the old `app.js`; it now concatenates every file under `js/` so
the same contract checks still hold regardless of which module owns a given
line.

### 27.4 Verification

Every milestone was verified against the **real GLD on COM9** (per explicit
user instruction, not Mock GLD): bridge health/port scan/connect/disconnect,
live Running-tab telemetry and boot health, Sensor Check tab, a full 8-channel
real nulling run (sweep meter + stage detail confirmed against genuine
firmware output), a real dataset start/stop cycle with session ID + auto-
saved CSV/log, PIN lock set/verify/reject, raw Expert command with real ACK,
timeout settings persistence, Firmware tab's COM-lock preflight (upload
itself intentionally not exercised, to avoid an unnecessary reflash), and
multi-slot add/switch/remove/alarm-surfacing mechanics. `python firmware/
tests/run_tests.py` stayed at 34/34 throughout.
