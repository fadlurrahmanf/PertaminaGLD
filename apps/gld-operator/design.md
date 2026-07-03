# GLD Operator Lite Design

Last updated: 2026-07-01

## 1. Ringkasan

GLD Operator Lite adalah aplikasi operator PC untuk mengoperasikan satu GLD
aktif melalui serial COM dan MQTT dataset. Aplikasi ini menggantikan versi
Electron yang terlalu besar dengan stack ringan:

- `index.html` untuk struktur UI.
- `style.css` untuk industrial dark theme.
- `app.js` untuk state UI, parser serial, chart, dataset/nulling workflow, mock,
  dan command orchestration.
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
- Bukan MQTT broker.
- Bukan compiler firmware custom; upload memakai PlatformIO existing.
- Belum mendukung fleet 1-8 GLD paralel di UI lite saat ini. UI sekarang adalah
  satu active GLD slot.

## 3. Lokasi File

```text
apps/gld-operator/
  index.html              UI structure
  style.css               Industrial dark styling
  app.js                  Browser-side app logic
  bridge.py               Local Python bridge and static file server
  requirements.txt        pyserial and paho-mqtt dependencies
  run-gld-operator.bat    Windows launcher
  README.md               Quick run instructions
  design.md               This document
  output/datasets/        Runtime CSV output, gitignored
```

File lama Electron/React/TypeScript sudah dihapus dari working tree untuk
mengecilkan ukuran aplikasi. Penghapusan itu memang bagian dari arah lite app.

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

- Fleet panel: satu active GLD slot.
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
  "targetDeviceId": "F001"
}
```

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

Not stored:

- WiFi password.
- MQTT password.
- `Run nulling before dataset` checkbox.
- Serial logs.
- Dataset rows.

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
- Apply GLD settings asks browser `confirm()`.
- Inject ID asks browser `confirm()`.
- Expert terminal disabled until local `Unlock`.
- Dataset nulling-first default OFF to avoid unintended nulling.

Known safety gaps:

- Expert unlock has no PIN yet.
- Bridge has permissive CORS and is intended for localhost bench only.
- MQTT credentials are not encrypted; password fields are not persisted.
- No authentication on local bridge.

Recommended production hardening:

- Bind bridge to `127.0.0.1` only, keep current default.
- Add one-time local admin PIN for Expert/Firmware.
- Reject upload if manifest device profile does not match connected GLD.
- Add visible COM lock/release state before upload.

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

As of 2026-07-01:

- Bridge can run and `/api/ports` returns COM10 when bridge is alive.
- App source has dataset/nulling UX improvements.
- Firmware source has dataset auto-nulling disabled by default.
- Firmware host tests passed.
- Upload to real GLD was attempted but not completed because COM10 became
  unavailable/busy after flash failure.
- `firmware.bin` was generated during upload attempt, but hardware must be
  reflashed successfully before firmware behavior change is active on the GLD.

## 23. Roadmap

High priority:

- Add bridge status indicator that can restart/reconnect after bridge downtime.
- Add explicit COM lock status before upload.
- Add upload preflight: disconnect serial, verify `mode COMx`, then upload.
- Add stricter manifest validation against actual flash files/checksums.
- Add Expert/Firmware PIN lock.
- Add visible `reject_no_profile` action button: "Run Nulling Now".

Medium priority:

- Persist raw serial logs per session to disk via bridge.
- Add session ID to dataset output.
- Add MQTT broker reachability test button.
- Add firmware upload retry guidance inside UI.
- Add multi-device architecture for 1-8 GLD slots.

Low priority:

- Package as portable folder with Python runtime optional.
- Add service wrapper for bridge.
- Add richer chart downsampling for very long sessions.
- Add app-side settings export/import.

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
