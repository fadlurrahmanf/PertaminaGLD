---
title: "Manual Book Operasi GLD"
subtitle: "Serial, MQTT, dan LoRa Command"
author: "Pertamina GLD"
date: "2026-06-19"
lang: "id-ID"
---

# Manual Book Operasi GLD

Dokumen ini menjelaskan cara mengoperasikan GLD firmware final dari jalur
Serial, MQTT langsung ke GLD, dan LoRa melalui Gateway/Cluster Head.

Manual ini dibuat dari implementasi repo saat ini, terutama:

- `firmware/gld/src/GldUnifiedMain.cpp`
- `firmware/gld/src/GldCommandParser.cpp`
- `firmware/config/LoraStarConfig.h`
- `firmware/config/LoraMeshConfig.h`
- `firmware/config/ServerConfig.h`
- `firmware/config/GldConfig.h`
- `firmware/config/ChConfig.h`
- `firmware/config/GwConfig.h`
- `firmware/ch/src/ChStarMeshRuntimeMain.cpp`
- `firmware/gateway/src/GatewayMqttMeshMain.cpp`
- `firmware/shared/include/ProtocolConstants.h`
- `server/nodered/README.md`
- `server/nodered/send_dataset_cmd.py`

## 1. Ringkasan Sistem

GLD final memakai satu firmware unified dengan tiga mode operasi:

| Mode | Nilai | Fungsi utama | Jalur kontrol aktif |
|---|---:|---|---|
| `inference` | `0` | Membaca sensor, menjalankan model ML, mengirim hasil via LoRa STAR ke CH | Serial, LoRa downlink setelah TX |
| `dataset` | `1` | Mengambil sample dataset sensor dan publish via MQTT | Serial, MQTT langsung ke GLD |
| `nulling` | `2` | Menjalankan kalibrasi/nulling sensor, menyimpan profile, publish hasil via MQTT | Serial, MQTT setelah nulling selesai |

Mode disimpan di NVS ESP32. Setiap command perubahan mode akan menyimpan mode
baru lalu melakukan restart ESP32.

## 2. Konfigurasi Final

### 2.1 Firmware Version

| Komponen | Firmware | Version |
|---|---|---|
| GLD | `PertaminaGLD-GLD` | `0.8.0` |
| CH | `PertaminaGLD-CH` | `0.6.0` |
| Gateway | `PertaminaGLD-Gateway` | `0.1.3` |
| Protocol | `0.1.0` |  |

### 2.2 PlatformIO Env Final

Main firmware config memakai env final pendek:

```text
firmware/platformio.ini
```

| Target | Env |
|---|---|
| GLD 4D board | `gld` |
| GLD WROOM bench | `gldw` |
| CH ID `0x0064` | `ch1` |
| CH ID `0x0065` | `ch2` |
| CH ID `0x0066` | `ch3` |
| Gateway | `gw` |

Build GLD final:

```powershell
pio run -d firmware -e gld
```

Upload GLD final ke COM10:

```powershell
pio run -d firmware -e gld -t upload --upload-port COM10
```

Env lama per-mode GLD tetap disimpan untuk support/debug di:

```text
firmware/support/platformio.ini
```

### 2.3 Identity dan Network

Konfigurasi aktif GLD:

| Parameter | Nilai |
|---|---|
| GLD node ID | `0xF001` |
| Device ID string | `F001` |
| CH target ID | `0x0064` |
| MQTT client ID | `gld-unified-F001` |
| WiFi SSID | `CHANGE_ME_WIFI_SSID` |
| MQTT host | `CHANGE_ME_MQTT_HOST` |
| MQTT port | `1884` |
| MQTT user | `<mqtt-user>` |

Jangan menaruh secret production di file repo. Untuk production, credential harus
dipindahkan ke provisioning/config yang aman.

## 3. Jalur Operasi

### 3.1 Serial

Serial adalah jalur paling langsung untuk operator/developer.

Default:

- Port GLD bench: `COM10`
- Baudrate: `115200`

Buka monitor:

```powershell
pio device monitor -p COM10 -b 115200
```

Command Serial yang aktif:

```text
SET_MODE inference
SET_MODE dataset
SET_MODE nulling
```

Contoh:

```text
SET_MODE dataset
```

Expected log:

```text
GLD_MODE_SWITCH current=inference new=dataset
```

Setelah command diterima, GLD menyimpan mode ke NVS dan restart. Setelah boot,
cek log:

```text
Pertamina GLD unified firmware
GLD_MODE=dataset
```

Catatan:

- `GET_MODE` belum di-handle oleh firmware saat ini.
- String mode selain `inference`, `dataset`, dan `nulling` akan jatuh ke
  default `inference`.
- Command harus diakhiri newline atau Enter.

### 3.2 MQTT Langsung ke GLD

MQTT langsung ke GLD aktif ketika GLD berada di mode yang memakai WiFi/MQTT,
terutama `dataset` dan `nulling`.

Broker:

```text
CHANGE_ME_MQTT_HOST:1884
user: <mqtt-user>
pass: <mqtt-pass>
```

Topic GLD:

| Topic | Arah | Fungsi |
|---|---|---|
| `gas-leak-detector/F001/cmd` | Subscribe | Command umum, terutama `SET_MODE` |
| `gas-leak-detector/F001/dataset` | Subscribe | `START_DATASET`, `STOP_DATASET`, dan `SET_MODE` saat mode dataset |
| `gas-leak-detector/F001/cmd/ack` | Publish | ACK command |
| `gas-leak-detector/F001/dataset/data` | Publish | Record dataset sensor |
| `gas-leak-detector/F001/dataset/status` | Publish | Status dataset |
| `gas-leak-detector/F001/dataset/summary` | Publish | Ringkasan dataset |
| `gas-leak-detector/F001/nulling/result` | Publish retained | Hasil nulling profile |
| `gas-leak-detector/F001/nulling/status` | Publish retained | Status nulling |

#### 3.2.1 MQTT SET_MODE

Publish ke:

```text
gas-leak-detector/F001/cmd
```

Payload:

```json
{"cmd":"SET_MODE","mode":"dataset"}
```

Mode valid:

```text
inference
dataset
nulling
```

Contoh dengan `mosquitto_pub`:

```powershell
mosquitto_pub -h CHANGE_ME_MQTT_HOST -p 1884 -u <mqtt-user> -P <mqtt-pass> -t "gas-leak-detector/F001/cmd" -m "{\"cmd\":\"SET_MODE\",\"mode\":\"dataset\"}"
```

ACK akan dipublish ke:

```text
gas-leak-detector/F001/cmd/ack
```

Contoh ACK:

```json
{"device_id":"F001","cmd":"SET_MODE","result":"ok","timestamp_ms":12345}
```

#### 3.2.2 MQTT START_DATASET

Syarat:

- GLD berada di mode `dataset`.
- WiFi dan MQTT connected.
- Nulling profile sudah ada. Jika belum ada, firmware akan reject dengan
  `reject_no_profile`.

Publish ke:

```text
gas-leak-detector/F001/dataset
```

Payload minimum:

```json
{
  "cmd": "START_DATASET",
  "label": "clear_air_test",
  "target_samples": 0,
  "sample_interval_ms": 1000,
  "max_duration_ms": 0,
  "use_fan_intake": false,
  "fan_on_ms": 1000,
  "post_fan_settle_ms": 0
}
```

Field:

| Field | Tipe | Default firmware | Keterangan |
|---|---:|---:|---|
| `label` | string | `unknown` | Label kondisi gas/test |
| `target_samples` | number | `0` | `0` berarti unlimited |
| `sample_interval_ms` | number | `1000` | Jeda sample |
| `max_duration_ms` | number | `0` | `0` berarti unlimited |
| `use_fan_intake` | bool | `true` | Nyalakan fan sebelum sample |
| `fan_on_ms` | number | `1000` | Lama fan ON |
| `post_fan_settle_ms` | number | `0` | Jeda setelah fan OFF sebelum scan |

Contoh dengan script repo:

```powershell
python server\nodered\send_dataset_cmd.py start clear_air_test
```

Contoh dengan `mosquitto_pub`:

```powershell
mosquitto_pub -h CHANGE_ME_MQTT_HOST -p 1884 -u <mqtt-user> -P <mqtt-pass> -t "gas-leak-detector/F001/dataset" -m "{\"cmd\":\"START_DATASET\",\"label\":\"clear_air_test\",\"target_samples\":100,\"sample_interval_ms\":1000,\"max_duration_ms\":0,\"use_fan_intake\":false,\"fan_on_ms\":1000,\"post_fan_settle_ms\":0}"
```

Expected serial log:

```text
DATASET_START label=clear_air_test target=100 interval=1000
DATASET_RECORD seq=0 ok=1 len=...
```

Dataset data akan muncul di:

```text
gas-leak-detector/F001/dataset/data
```

Contoh record:

```json
{
  "device_id": "F001",
  "node_id": 61441,
  "mode": "DATASET",
  "seq": 0,
  "timestamp_ms": 123456,
  "label": "clear_air_test",
  "nulling_profile_id": 1,
  "sensor_voltage": [0.01,0.02,0.03,0.04,0.05,0.06,0.07,0.08],
  "sensor_gain": [64,64,64,64,64,64,64,64],
  "feature_order": ["MQ8","MQ2","MQ4","MQ6","MQ7","MQ135","MQ136","MQ137"]
}
```

#### 3.2.3 MQTT STOP_DATASET

Publish ke:

```text
gas-leak-detector/F001/dataset
```

Payload:

```json
{"cmd":"STOP_DATASET"}
```

Script repo:

```powershell
python server\nodered\send_dataset_cmd.py stop
```

Expected serial log:

```text
DATASET_STOP totalSeq=...
```

Setelah stop, firmware publish:

- `gas-leak-detector/F001/dataset/summary`
- `gas-leak-detector/F001/dataset/status`

#### 3.2.4 MQTT Nulling Result

Masuk mode nulling:

```powershell
mosquitto_pub -h CHANGE_ME_MQTT_HOST -p 1884 -u <mqtt-user> -P <mqtt-pass> -t "gas-leak-detector/F001/cmd" -m "{\"cmd\":\"SET_MODE\",\"mode\":\"nulling\"}"
```

Atau lewat Serial:

```text
SET_MODE nulling
```

Saat boot di mode `nulling`, firmware menjalankan nulling service, menyimpan
profile ke NVS, lalu publish retained result ke:

```text
gas-leak-detector/F001/nulling/result
```

Expected serial log:

```text
NULLING_RUN=start
NULLING_RUN_DONE status=...
NULLING_NVS_SAVE=OK profileId=...
NULLING_RUNTIME_RESULT=PASS
```

## 4. LoRa Operation

### 4.1 Radio Topology

| Link | Arah | Frekuensi | SF | BW | Sync word |
|---|---|---:|---:|---:|---:|
| STAR | GLD <-> CH | `920.0 MHz` | `7` | `125 kHz` | `0x12` |
| MESH | CH <-> Gateway | `921.0 MHz` | `9` | `125 kHz` | `0x34` |

GLD inference mengirim `MSG_SENSOR_DATA` ke CH via STAR. CH menyimpan cache node
dan meneruskan data ke Gateway via MESH. Gateway publish ke MQTT server.

### 4.2 GLD Uplink

Message type:

```text
MSG_SENSOR_DATA = 0x10
```

`typeFlags`:

| Kondisi | typeFlags |
|---|---:|
| Normal battery | `0x10` |
| Normal external power | `0x90` |
| Alarm battery | `0x50` |
| Alarm external power | `0xD0` |

Payload GLD encrypted phase-1 panjangnya 29 byte. Plaintext di dalam AES-GCM
adalah 4 byte:

| Byte | Field |
|---:|---|
| 0 | gasClass |
| 1 | confidence |
| 2..3 | batteryMv big-endian |

### 4.3 LoRa Downlink Final ke GLD

Downlink final yang diterima GLD adalah:

```text
MSG_NODE_DOWNLINK = 0x14
```

Syarat frame:

- AppFrame valid.
- `dstId` sama dengan GLD node ID `0xF001`.
- Payload minimal 2 byte.
- Payload byte 0 adalah `cmdType`.
- Untuk mode switch, `cmdType = 0x01`.
- Payload byte 1 adalah mode.

Payload mode switch:

| Tujuan | Payload hex |
|---|---|
| Set `inference` | `0100` |
| Set `dataset` | `0101` |
| Set `nulling` | `0102` |

Setelah GLD menerima downlink valid, log yang diharapkan:

```text
GLD_LORA_DOWNLINK_RX state=0 len=...
GLD_LORA_DOWNLINK_CMD mode=dataset
GLD_MODE_SWITCH current=inference new=dataset
```

### 4.4 Timing Downlink

Battery mode:

- GLD membuka RX window hanya setelah mengirim `SENSOR_DATA`.
- RX window default: `2000 ms`.
- CH menyimpan pending downlink dan mengirim saat RX window setelah uplink GLD.

External power mode:

- CH boleh mengirim pending downlink langsung jika cache node terakhir
  menunjukkan `NC_FLAG_EXT_POWER`.

Alarm:

- Jika uplink GLD adalah alarm, CH mengirim compact ACK lebih dulu.
- Setelah ACK alarm, CH baru mengirim pending `NODE_DOWNLINK`.

### 4.5 MQTT ke Gateway untuk Command LoRa

Gateway subscribe:

```text
gld/gateway/cmd/node
```

Payload JSON yang dipakai Gateway:

```json
{
  "cluster": "0x0064",
  "node": "0xF001",
  "id": 1,
  "ttl": 600,
  "hex": "0101"
}
```

Field:

| Field | Keterangan |
|---|---|
| `cluster` | CH target, default `0x0064` |
| `node` | GLD target, default `0xF001` |
| `id` | command ID |
| `ttl` | TTL detik menurut Gateway payload |
| `hex` | command payload untuk GLD, contoh `0101` set mode dataset |

Contoh publish:

```powershell
mosquitto_pub -h CHANGE_ME_MQTT_HOST -p 1884 -u <mqtt-user> -P <mqtt-pass> -t "gld/gateway/cmd/node" -m "{\"cluster\":\"0x0064\",\"node\":\"0xF001\",\"id\":1,\"ttl\":600,\"hex\":\"0101\"}"
```

Expected Gateway log:

```text
GW_MQTT_CMD topic=gld/gateway/cmd/node len=...
GW_MESH_TX purpose=node-command state=0 len=...
```

Expected CH log:

```text
CH_MESH_RX state=0 len=...
CH_DOWNLINK_STORED nodeId=0xF001 commandId=1 ttlSec=600 payloadLen=2
CH_NODE_DOWNLINK_TX nodeId=0xF001 encStatus=0 frameSize=...
```

Important compatibility note:

Repo saat ini menunjukkan Gateway membentuk payload `SERVER_NODE_COMMAND`
dengan format:

```text
nodeId:uint16 + commandId:uint16 + ttlSec:uint16 + commandLen:uint8 + commandBytes
```

Parser CH sekarang membaca format yang sama. Command `gld/gateway/cmd/node`
berjalan lewat jalur:

```text
Gateway MQTT -> MSG_SERVER_NODE_COMMAND -> CH pending downlink -> MSG_NODE_DOWNLINK -> GLD
```

`ttlSec` menjadi expiry pending downlink di CH; nilai `0` memakai TTL default CH.

## 5. Node-RED Server

Flow server memakai broker lokal Aedes di port `1884` untuk bench saat ini.

Deploy flow site:

```powershell
node .\server\nodered\apply-pertamina-gld-flow.js `
  --node-red-url "http://127.0.0.1:1880" `
  --gateway-status-url "http://0.0.0.0/disabled-until-gateway-ip-known" `
  --gateway-base-url "http://0.0.0.0" `
  --mqtt-host "127.0.0.1" `
  --mqtt-port 1884
```

Deploy dataset flow:

```powershell
powershell -ExecutionPolicy Bypass -File .\server\nodered\apply-pertamina-gld-dataset-flow.ps1 `
  -NodeRedUrl "http://127.0.0.1:1880" `
  -MqttHost "127.0.0.1" `
  -MqttPort 1884
```

Dataset flow menyediakan inject operator `START_DATASET clear_air_test` dan
`STOP_DATASET`. Keduanya publish ke `gas-leak-detector/F001/dataset`; hasil
command terlihat di debug `cmd/ack` dari topic `gas-leak-detector/+/cmd/ack`.

Topic server/Gateway:

| Topic | Fungsi |
|---|---|
| `gld/gateway/uplink` | Gateway publish AppFrame/record uplink |
| `gld/gateway/status` | Status Gateway |
| `gld/gateway/events` | Envelope hasil parse |
| `gld/server/decoded` | Event GLD decoded normal |
| `gld/server/alarm` | Event alarm |
| `gld/gateway/error` | Error parse/decode |
| `gld/gateway/cmd/pull` | Server pull request ke CH |
| `gld/gateway/cmd/node` | Server command ke GLD via CH |

Pull request contoh:

```json
{"requestId":1,"hopList":["0x0064"]}
```

Publish:

```powershell
mosquitto_pub -h CHANGE_ME_MQTT_HOST -p 1884 -u <mqtt-user> -P <mqtt-pass> -t "gld/gateway/cmd/pull" -m "{\"requestId\":1,\"hopList\":[\"0x0064\"]}"
```

## 6. Prosedur Operasional

### 6.1 Boot dan Cek Mode

1. Hubungkan GLD ke USB.
2. Buka serial monitor `COM10` baud `115200`.
3. Reset GLD.
4. Pastikan boot log muncul.
5. Catat `GLD_MODE=...`.
6. Catat `GLD_POWER mode=... externalPower=... batteryMv=...`.

Log sehat mode inference:

```text
Pertamina GLD unified firmware
GLD_MODE=inference
ADS_BEGIN_RESULT=PASS
GLD_ML_INIT initialized=1 outputSize=...
GLD_INFERENCE_READY adsReady=1 radioReady=1 mlReady=1
```

### 6.2 Menjalankan Nulling

Gunakan saat kalibrasi atau sebelum dataset jika belum ada profile.

Serial:

```text
SET_MODE nulling
```

Tunggu reboot dan proses nulling selesai.

Expected result:

```text
NULLING_RUNTIME_RESULT=PASS
```

Jika hasil `PARTIAL`, sebagian channel gagal tetapi profile tetap bisa tersimpan.
Jika hasil `FAIL`, cek wiring ADS1256/DAC/MUX dan external power.

### 6.3 Menjalankan Dataset

1. Pastikan nulling profile valid.
2. Masuk mode dataset:

```text
SET_MODE dataset
```

3. Tunggu WiFi dan MQTT:

```text
WIFI_CONNECTED ip=...
MQTT_CONNECT_RESULT=OK
DATASET_READY adsReady=1 dacReady=1 nullingProfileId=...
```

4. Start dataset:

```powershell
python server\nodered\send_dataset_cmd.py start clear_air_test
```

5. Monitor data topic:

```powershell
mosquitto_sub -h CHANGE_ME_MQTT_HOST -p 1884 -u <mqtt-user> -P <mqtt-pass> -t "gas-leak-detector/F001/dataset/#" -v
```

6. Stop dataset:

```powershell
python server\nodered\send_dataset_cmd.py stop
```

### 6.4 Menjalankan Inference/Running Mode

Serial:

```text
SET_MODE inference
```

Expected runtime log:

```text
GLD_SENSOR_SCAN seq=... gasClass=0(clearGas) confidence=... alarm=0
GLD_TX_HEADER status=Ok seq=...
GLD_STAR_TX_STATE=0 seq=...
GLD_LORA_TX_RESULT=PASS
```

Jika gas terdeteksi dengan confidence melewati threshold:

```text
alarm=1
```

Lampu alarm dan buzzer akan mengikuti status alarm.

### 6.5 Monitor Gateway dan Server

Subscribe uplink Gateway:

```powershell
mosquitto_sub -h CHANGE_ME_MQTT_HOST -p 1884 -u <mqtt-user> -P <mqtt-pass> -t "gld/gateway/uplink" -v
```

Subscribe decoded server:

```powershell
mosquitto_sub -h CHANGE_ME_MQTT_HOST -p 1884 -u <mqtt-user> -P <mqtt-pass> -t "gld/server/#" -v
```

Subscribe semua GLD dataset/nulling:

```powershell
mosquitto_sub -h CHANGE_ME_MQTT_HOST -p 1884 -u <mqtt-user> -P <mqtt-pass> -t "gas-leak-detector/F001/#" -v
```

## 7. Troubleshooting

### 7.1 Serial Tidak Muncul

Checklist:

- Pastikan port benar, untuk bench biasanya `COM10`.
- Pastikan baud `115200`.
- Cek `pio device list`.
- Cabut pasang USB jika port terkunci.

### 7.2 `SET_MODE` Tidak Bereaksi

Checklist:

- Pastikan command diakhiri Enter/newline.
- Pakai lowercase mode: `inference`, `dataset`, `nulling`.
- Lihat log `GLD_MODE_SWITCH`.
- Jika tidak ada log, pastikan monitor benar-benar mengirim input ke port.

### 7.3 MQTT Tidak Connect

Expected log gagal:

```text
WIFI_CONNECT_FAILED
MQTT_CONNECT_RESULT=FAIL state=...
```

Checklist:

- Pastikan GLD berada di mode `dataset` atau `nulling`.
- Pastikan SSID `CHANGE_ME_WIFI_SSID` tersedia.
- Pastikan broker `CHANGE_ME_MQTT_HOST:1884` hidup.
- Pastikan username/password benar.
- Cek firewall Windows untuk port `1884`.

### 7.4 Dataset Reject `reject_no_profile`

Artinya nulling profile belum ada. Jalankan:

```text
SET_MODE nulling
```

Tunggu `NULLING_NVS_SAVE=OK`, lalu masuk lagi ke:

```text
SET_MODE dataset
```

### 7.5 LoRa TX Gagal

Log:

```text
GLD_LORA_TX_RESULT=FAIL
```

Checklist:

- Cek wiring SX1262 GLD.
- Cek pin CS/RST/BUSY/DIO1/RXEN/TXEN.
- Cek radio CH menyala dan STAR berada di `920 MHz`, SF7, BW125, sync `0x12`.
- Cek supply power.

### 7.6 Gateway Command Tidak Mengubah Mode GLD

Validasi jalur Gateway -> CH -> GLD dengan urutan log:

```text
GW_MQTT_CMD topic=gld/gateway/cmd/node
GW_MESH_TX purpose=node-command
CH_DOWNLINK_STORED nodeId=0xF001 commandId=1 ttlSec=600 payloadLen=2
CH_NODE_DOWNLINK_TX nodeId=0xF001
GLD_LORA_DOWNLINK_CMD mode=...
GLD_MODE_SWITCH current=... new=...
```

Jika `CH_DOWNLINK_STORED` muncul tetapi `CH_NODE_DOWNLINK_TX` tidak muncul, cek apakah target GLD terakhir terdeteksi external power atau tunggu uplink GLD berikutnya untuk membuka RX window battery mode.

## 8. Quick Command Reference

### Serial

```text
SET_MODE inference
SET_MODE dataset
SET_MODE nulling
```

### MQTT GLD Direct

Set mode:

```powershell
mosquitto_pub -h CHANGE_ME_MQTT_HOST -p 1884 -u <mqtt-user> -P <mqtt-pass> -t "gas-leak-detector/F001/cmd" -m "{\"cmd\":\"SET_MODE\",\"mode\":\"dataset\"}"
```

Start dataset:

```powershell
python server\nodered\send_dataset_cmd.py start clear_air_test
```

Stop dataset:

```powershell
python server\nodered\send_dataset_cmd.py stop
```

Monitor GLD topics:

```powershell
mosquitto_sub -h CHANGE_ME_MQTT_HOST -p 1884 -u <mqtt-user> -P <mqtt-pass> -t "gas-leak-detector/F001/#" -v
```

### MQTT Gateway/LoRa

Set GLD to dataset through Gateway/CH, intended final payload:

```powershell
mosquitto_pub -h CHANGE_ME_MQTT_HOST -p 1884 -u <mqtt-user> -P <mqtt-pass> -t "gld/gateway/cmd/node" -m "{\"cluster\":\"0x0064\",\"node\":\"0xF001\",\"id\":1,\"ttl\":600,\"hex\":\"0101\"}"
```

Set GLD to inference through Gateway/CH:

```powershell
mosquitto_pub -h CHANGE_ME_MQTT_HOST -p 1884 -u <mqtt-user> -P <mqtt-pass> -t "gld/gateway/cmd/node" -m "{\"cluster\":\"0x0064\",\"node\":\"0xF001\",\"id\":2,\"ttl\":600,\"hex\":\"0100\"}"
```

Set GLD to nulling through Gateway/CH:

```powershell
mosquitto_pub -h CHANGE_ME_MQTT_HOST -p 1884 -u <mqtt-user> -P <mqtt-pass> -t "gld/gateway/cmd/node" -m "{\"cluster\":\"0x0064\",\"node\":\"0xF001\",\"id\":3,\"ttl\":600,\"hex\":\"0102\"}"
```

Current note: validate the full Gateway -> CH -> GLD LoRa mode switch path on
the target hardware before relying on it in field operation.

## 9. Acceptance Checklist

GLD is ready for operation when:

- GLD boots and shows firmware `0.8.12`.
- `GLD_MODE` is readable from serial boot log.
- Serial `SET_MODE inference|dataset|nulling` works and reboots into target mode.
- Nulling can produce `NULLING_RUNTIME_RESULT=PASS` or acceptable `PARTIAL`.
- Dataset mode connects WiFi/MQTT and publishes data to
  `gas-leak-detector/F001/dataset/data`.
- Inference mode publishes LoRa uplink and CH/Gateway/Node-RED receives it.
- Gateway publishes received frame to `gld/gateway/uplink`.
- Node-RED decodes normal data to `gld/server/decoded`.
- Alarm path publishes alarm data to `gld/server/alarm`.
- Gateway->CH->GLD LoRa downlink is retested on target hardware with
  `CH_DOWNLINK_STORED`, `CH_NODE_DOWNLINK_TX`, and `GLD_LORA_DOWNLINK_CMD`.
