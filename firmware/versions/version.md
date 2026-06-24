# Firmware Version History

This file tracks official firmware versions for the Pertamina GLD project.

Build date format:

```text
YYYY-MM-DD HH:mm:ss Asia/Jakarta
```

---

## GLD v0.8.0 / CH v0.7.0 / Gateway v0.1.3 - 2026-06-22 Asia/Jakarta

**Summary:** CH reliability upgrade — state machine, battery guard, watchdog, alarm ACK retry, failover parent, NVS persistence, CH_HELLO, parent discovery, TTL downlink, NodeCache expiry.

### Changed Files

- firmware/shared/include/FirmwareVersion.h (CH 0.6.0→0.7.0)
- firmware/ch/include/ChBoardPins.h (tambah PIN_BATMON=GPIO4)
- firmware/config/ChConfig.h (NODE_CACHE_CAPACITY 16→32, DOWNLINK_STORE_CAPACITY 8→16, tambah battery/failover/hello/TTL/housekeeping constants)
- firmware/ch/include/ChRuntime.h (tambah markAlarmAcked())
- firmware/ch/src/ChRuntime.cpp (AlarmPush tidak lagi dihapus dari queue di markChTxSuccess; tambah markAlarmAcked())
- firmware/ch/src/ChStarMeshRuntimeMain.cpp (rewrite besar — state machine + semua fitur baru)
- firmware/versions/version.md

### Behavior

- **State machine**: BOOT→WAIT_BATT→RADIO_INIT→JOINING→JOINED→(LOW_POWER/PARENT_FAILOVER/RECOVERY)
- **Battery guard**: baca ADC GPIO4, 16-sample avg, formula `(avg×3)+200mV`. Harus stabil ≥3500mV (8x berturut) sebelum radio init.
- **Watchdog**: `esp_task_wdt` 60 detik. Feed di setiap iterasi loop.
- **Alarm ACK wait**: 1500ms timeout. Exponential backoff 200ms×2^n, max 5 retry, lalu alarm dibuang + parentFailCnt++.
- **Failover parent**: setelah 3 kegagalan alarm ACK (dengan cooldown 60s) → swap parentId↔parentAlt, simpan ke NVS, kirim CH_CONFIG_REQUEST broadcast. Setelah 5 kegagalan berturut-turut → restart.
- **NVS persistence**: parentId + parentAlt disimpan via Preferences. Saat boot, langsung load dan proceed ke JOINED.
- **CH_HELLO** (0x33): setiap 5 menit, payload: clusterId(2)+parentId(2)+battMv(2)+uptimeSec(2).
- **Parent discovery**: CH_CONFIG_REQUEST (0x34) broadcast saat JOINING/FAILOVER; update parentId dari CH_CONFIG_RESPONSE (0x35).
- **TTL downlink**: pending command > 30 menit dibuang di housekeeping() setiap 60 detik.
- **NodeCache expiry**: entry > 1 jam di-clear di housekeeping().
- **Low power mode**: jika battMv < 3150mV → ST_LOW_POWER; jika battMv < 3100mV → blokir TX.

### Wire Format

Wire format tidak berubah: `SERVER_NODE_COMMAND` tetap 5-byte (`nodeId+commandId+len+payload`). Alarm upstream tetap GLDRecord format.

---

## GLD v0.8.0 / CH v0.6.0 / Gateway v0.1.3 - 2026-06-19 Asia/Jakarta

**Summary:** Unified GLD firmware (3 mode dalam 1 binary) + LoRa downlink untuk mode switch dari server.

### Changed Files

- firmware/shared/include/FirmwareVersion.h (GLD 0.7.0→0.8.0, CH 0.5.3→0.6.0)
- firmware/shared/include/ProtocolConstants.h (tambah MSG_GLD_DOWNLINK_CMD=0x20)
- firmware/gld/include/GldModeManager.h (NEW — NVS mode persistence)
- firmware/gld/src/GldModeManager.cpp (NEW)
- firmware/gld/include/GldCommandParser.h (NEW — parse Serial + LoRa downlink command)
- firmware/gld/src/GldCommandParser.cpp (NEW)
- firmware/gld/src/GldUnifiedMain.cpp (NEW — unified inference/dataset/nulling main)
- firmware/platformio.ini (tambah env gld_unified_esp32s3)
- firmware/ch/src/ChStarMeshRuntimeMain.cpp (tambah MSG_GLD_DOWNLINK_CMD handler)
- firmware/versions/version.md

### Behavior

- `gld_unified_esp32s3` menggabungkan 3 firmware GLD (inference, dataset, nulling) jadi 1 binary.
- Mode disimpan di NVS. Boot → baca NVS → init hardware sesuai mode.
- Mode switch via Serial: `SET_MODE inference|dataset|nulling\n` (semua mode)
- Mode switch via MQTT: publish `{"cmd":"SET_MODE","mode":"dataset"}` ke topic `gas-leak-detector/F001/cmd` (dataset/nulling mode)
- Mode switch via LoRa downlink (inference mode): CH forward MSG_GLD_DOWNLINK_CMD via STAR, GLD buka 2-detik RX window setelah tiap TX (LoRa Class A pattern)
- 3 env lama (gld_inference, gld_dataset, gld_nulling_runtime) tetap ada untuk debugging per-mode.

### Protocol Addition

- `MSG_GLD_DOWNLINK_CMD = 0x20` — AppFrame baru untuk CH→GLD mode switch command
- Payload: nodeIdHi(1) nodeIdLo(1) cmdType(1=SET_MODE) mode(1=0/1/2)
- CH menerima dari MESH, forward ke STAR setelah validasi
- GLD buka RX window 2 detik setelah setiap STAR TX

### Test Result

- Build: TBD (sedang build)

### Rollback

Restore `firmware/shared/include/FirmwareVersion.h`, `ProtocolConstants.h`, `platformio.ini`, dan `ChStarMeshRuntimeMain.cpp` dari backup v0.7.0. Delete file baru: `GldModeManager.h/cpp`, `GldCommandParser.h/cpp`, `GldUnifiedMain.cpp`.

---

## GLD v0.7.0 / CH v0.5.3 / Gateway v0.1.3 - 2026-06-19 Asia/Jakarta

**Summary:** Step 12 — Integrate TFLite Micro ML inference pipeline into GLD. Placeholder model from ApplyGasleak project. `firmware/gld/model/` ready for drop-in replacement when Pertamina-trained model is available.

### Changed Files

- firmware/shared/include/FirmwareVersion.h
- firmware/gld/src/GldInferenceMain.cpp (rewrite: threshold classifier → NeuralNetwork)
- firmware/gld/model/NeuralNetwork.h (new)
- firmware/gld/model/NeuralNetwork.cpp (new)
- firmware/gld/model/scaler_params.h (new)
- firmware/gld/model/scaler_params.cpp (new)
- firmware/gld/model/model_data.h (new)
- firmware/gld/model/model_data.cpp (new — 31KB TFLite flatbuffer)
- firmware/lib/tfmicro/ (new — vendored TFLite Micro)
- firmware/platformio.ini (gld_inference_esp32s3 updated)
- firmware/versions/version.md

### Behavior

- `gld_inference_esp32s3` sekarang menggunakan NeuralNetwork (TFLite Micro) menggantikan GldThresholdClassifier.
- Input pipeline: ADS1256 → moving average → channel remapping (HW→model index) → StandardScaler → TFLite Micro inference.
- Channel remapping `HW_TO_MODEL[8] = {0,2,5,3,4,6,1,7}` sesuai ApplyGasleak `takeDataMQ()`.
- Output: `gasClass` (0=clear, 1=LPG, 2=methane, 3=propane, 4=butane) + `confidence` (0-100).
- Alarm rule tidak berubah: `gasClass != 0 && confidence >= 30`.
- Model saat ini adalah placeholder — tidak ditraining dengan data Pertamina.
- Untuk replace model: overwrite `firmware/gld/model/model_data.cpp`, `scaler_params.cpp`, `scaler_params.h`, lalu rebuild.

### Test Result

- `pio run -d firmware -e gld_inference_esp32s3` → SUCCESS 57.67s, Flash 7.0%, RAM 24.0%
- Upload COM10 → success
- Serial verified: `GLD_ML_INIT initialized=1 outputSize=5`
- Serial verified: `GLD_INFERENCE_READY adsReady=1 radioReady=1 mlReady=1`
- Serial verified: `GLD_ML_RESULT predictedClass=0 gasClass=0(clearGas) confidence=99` (steady, clean air)

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.6.4/`. Remove `firmware/gld/model/` dan `firmware/lib/tfmicro/` jika rollback penuh ke threshold classifier.

---

## GLD v0.6.4 / CH v0.5.3 / Gateway v0.1.3 - 2026-06-18 Asia/Jakarta

**Summary:** Add MQTT connection diagnostics and stale-session mitigation for GLD dataset runtime after COM10 showed repeated `MQTT_CONNECT_RESULT=FAIL`.

### Changed Files

- firmware/shared/include/FirmwareVersion.h
- firmware/gld/src/GldDatasetMain.cpp
- firmware/tests/test_shared_protocol.py
- firmware/README.md
- server/nodered/deploy-dataset-flow.py
- docs/progress.md
- firmware/versions/version.md

### Behavior

- Dataset MQTT client ID changed to `gld-dataset-F001-v064`.
- MQTT connect log now includes PubSubClient state, local IP, and RSSI.
- Failed MQTT connect explicitly stops the underlying `WiFiClient` before retry.
- Dataset command/data schema is unchanged.
- Node-RED dataset deploy is now idempotent against an existing `GLD Dataset Server`
  tab whose id was generated by Node-RED.
- Node-RED MySQL config now supplies `credentials` for `node-red-node-mysql`.
- Node-RED CSV row formatter now receives the raw MQTT dataset record in parallel,
  before the MySQL parser converts `msg.payload` into SQL bind parameters.

### Test Result

- `python firmware/tests/run_tests.py` -> `27/27 tests passed`
- `pio run -d firmware -e gld_dataset_esp32s3 -t upload --upload-port COM10` -> success
- COM10 boot verified:
  - `Firmware version: 0.6.4`
  - `ADS_BEGIN_RESULT=PASS`
  - `DAC_MUX_BEGIN_RESULT=PASS`
  - `NULLING_NVS_LOAD=found profileId=2`
  - `DATASET_READY adsReady=1 dacReady=1 nullingProfileId=2`
- MQTT command verified:
  - topic `gas-leak-detector/F001/dataset`
  - payload `{"cmd":"START_DATASET","label":"clear_air_test",...}`
  - ack topic `gas-leak-detector/F001/cmd/ack`
  - ack result `ok`
- MQTT data verified:
  - topic `gas-leak-detector/F001/dataset/data`
  - fields `device_id`, `node_id`, `mode`, `seq`, `timestamp_ms`, `label`,
    `nulling_profile_id`, `sensor_voltage[8]`, `sensor_gain[8]`,
    `feature_order[8]`
  - `feature_order=["MQ8","MQ135","MQ3","MQ5","MQ4","MQ7","MQ6","MQ2"]`
- Recorder verified:
  - MySQL `gld_dataset`: `COUNT=69`, `MIN(seq)=0`, `MAX(seq)=68`, `MAX(nulling_profile_id)=2`
  - CSV `C:\Users\asus\gld-dataset.csv`: 69 rows
- Node-RED Step 11c final verification:
  - `python server/nodered/deploy-dataset-flow.py` -> success
  - active `GLD Dataset Server` tab uses design fields, not old `ch/ts_ms/profileId/ok` fields
  - bounded capture `target_samples=2` auto-stopped with serial
    `DATASET_AUTOSTOP target_reached total=2`
  - Node-RED MySQL `gld_dataset`: 2 rows for label `step11_final_2`
  - Node-RED CSV `C:\Users\asus\gld-dataset.csv`: 2 rows for label `step11_final_2`
  - summary topic verified with label `summary_final_1`, `total_samples=1`,
    `nulling_profile_id=2`
  - final sink check after summary test: MySQL count `3`, CSV count `3`

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.6.3/`.

---

## GLD v0.6.3 / CH v0.5.3 / Gateway v0.1.3 - 2026-06-18 Asia/Jakarta

**Summary:** Fix dataset command parsing and dataset publish buffer sizes after live COM10 test found `DATASET_CMD_PARSE_ERROR NoMemory`.

### Changed Files

- firmware/shared/include/FirmwareVersion.h
- firmware/gld/src/GldDatasetMain.cpp
- firmware/tests/test_shared_protocol.py
- firmware/README.md
- docs/progress.md
- firmware/versions/version.md

### Behavior

- `START_DATASET` JSON command capacity increased from 256 to 512 bytes.
- MQTT client buffer increased from 512 to 1024 bytes.
- Dataset record JSON document increased to 1024 bytes.
- Dataset publish payload buffer increased to 896 bytes.
- Wire/schema contract is unchanged.

### Test Result

- `python firmware/tests/run_tests.py` -> `27/27 tests passed`
- `pio run -d firmware -e gld_dataset_esp32s3 -t upload --upload-port COM10` -> success
- COM10 verified the `NoMemory` parse error was fixed, but this version was
  superseded by GLD v0.6.4 to add MQTT connection diagnostics after repeated
  MQTT connect failures were observed during the same bench run.

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.6.2/`.

---

## GLD v0.6.2 / CH v0.5.3 / Gateway v0.1.3 - 2026-06-18 Asia/Jakarta

**Summary:** Step 11b design compliance — dataset firmware, send script, recorder, and Node-RED flow updated to match `design.updated.draft.md` Section 6.2 / 10.2.
- Subscribe topic: `/dataset/cmd` → `/dataset`
- Record fields: `nodeId/ts_ms/profileId/ch/gain` → `device_id/node_id/mode/timestamp_ms/nulling_profile_id/sensor_voltage/sensor_gain/feature_order`
- Removed `ok[8]` from record (not in design)
- Added `cmd/ack` publish on every command received
- Added `dataset/summary` publish on STOP_DATASET
- Added full START_DATASET param parsing: `target_samples`, `sample_interval_ms`, `max_duration_ms`, `use_fan_intake`, `fan_on_ms`, `post_fan_settle_ms`
- Added non-blocking fan intake state machine (SampleStep)
- Added auto-stop on `target_samples` / `max_duration_ms`

### Changed Files

- firmware/shared/include/FirmwareVersion.h
- firmware/gld/src/GldDatasetMain.cpp
- server/nodered/send_dataset_cmd.py
- server/nodered/gld_dataset_recorder.py
- server/nodered/deploy-dataset-flow.py
- firmware/versions/version.md

---

## GLD v0.6.1 / CH v0.5.3 / Gateway v0.1.3 - 2026-06-18 Asia/Jakarta

**Summary:** Step 11a — nulling runtime service. GLD runs nulling algorithm (TCA9548A + MCP4725, per-channel binary search), saves NullingProfile to NVS, connects WiFi + MQTT, publishes profile to `gas-leak-detector/F001/nulling/result`.

### Changed Files

- firmware/shared/include/FirmwareVersion.h
- firmware/gld/include/GldNullingProfile.h (new)
- firmware/gld/include/GldNullingService.h (new)
- firmware/gld/src/GldNullingService.cpp (new)
- firmware/gld/src/GldNullingRuntimeMain.cpp (new)
- firmware/platformio.ini (added gld_nulling_runtime_esp32s3 env)
- firmware/versions/version.md

### Test Result

- `pio run -d firmware -e gld_nulling_runtime_esp32s3` → BUILD SUCCESS
- Upload to COM10 → NULLING_RUNTIME_RESULT=PASS, successCount=8, NVS profileId=2, MQTT_PUBLISH ok=1 len=322

---

## GLD v0.6.0 / CH v0.5.3 / Gateway v0.1.3 - 2026-06-18 13:19:59 Asia/Jakarta

**Summary:** Step 10 — threshold-based inference runtime. GLD now reads real ADS1256 sensor data, captures boot baseline per channel, and classifies gas via delta-from-baseline threshold.

### Changed Files

- firmware/shared/include/FirmwareVersion.h
- firmware/gld/include/GldThresholdClassifier.h (new)
- firmware/gld/src/GldThresholdClassifier.cpp (new)
- firmware/gld/src/GldInferenceMain.cpp (new)
- firmware/platformio.ini (added gld_inference_esp32s3 env)
- firmware/versions/version.md

### Test Result

- `pio run -d firmware -e gld_inference_esp32s3` → BUILD SUCCESS, 5.6% Flash, 9.9% RAM
- Upload to COM10 → ADS_BEGIN_RESULT=PASS, GLD_STAR_READY=1
- GLD_BASELINE_CALIBRATED at seq=9 (~10s after boot)
- GLD_LORA_TX_RESULT=PASS every 10s with real gasClass/confidence

---

## v0.5.9 / CH v0.5.3 / Gateway v0.1.3 - 2026-06-18 11:41:20 Asia/Jakarta

**Summary:** Align Node-RED and Gateway pull command with CH design section 11.1 `SERVER_PULL_REQUEST` payload format.

### Changed Files

- firmware/README.md
- firmware/shared/include/FirmwareVersion.h
- firmware/gateway/src/GatewayMqttMeshMain.cpp
- firmware/ch/include/ChPullRequest.h
- firmware/ch/src/ChPullRequest.cpp
- firmware/tests/test_shared_protocol.py
- firmware/versions/version.md
- docs/progress.md
- docs/design/ch-ch/design.md
- docs/design/ch-gw/design.md
- docs/design/gw/design.md
- docs/design/gw-server/design.md
- docs/design/server/design.md
- server/nodered/README.md
- server/nodered/apply-pertamina-gld-flow.js
- server/nodered/apply-pertamina-gld-flow.ps1
- server/nodered/pertamina-gld-server.flow.json

### Behavior

- Canonical Node-RED/Gateway pull command is now:

```json
{"requestId":1,"hopList":["0x0064"]}
```

- Gateway builds wire payload `requestId:uint16BE + hopList:uint16BE[]`.
- Direct Gateway -> CH bench remains 4 bytes: `requestId + hopList[0]`.
- Field `cluster` is kept only as a legacy fallback alias for `hopList[0]`.
- Field `node` is not used for pull; it remains valid only for `gld/gateway/cmd/node`.
- CH validates `decoded.dstId == localChId` and `hopList[0] == localChId`.
- CH direct phase rejects `hopCount != 1` with `UnsupportedHopCount` until CH-CH relay logic is implemented.

### Test Result

- `python firmware/tests/run_tests.py` -> `27/27 tests passed`

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.5.9-ch0.5.2-gw0.1.2/`.

---

## v0.5.9 / CH v0.5.2 / Gateway v0.1.2 - 2026-06-18 11:27:33 Asia/Jakarta

**Summary:** Add GLD alarm LoRa self-test target and validate live alarm push delivery through CH, Gateway, and Node-RED.

### Changed Files

- firmware/README.md
- firmware/platformio.ini
- firmware/shared/include/FirmwareVersion.h
- firmware/gld/include/GldSelfTestConfig.h
- firmware/gld/src/GldLoRaTxSelfTestMain.cpp
- firmware/tests/test_shared_protocol.py
- firmware/versions/version.md
- docs/progress.md

### Behavior

- GLD normal LoRa self-test remains `gld_lora_tx_selftest_esp32s3`.
- New GLD alarm target `gld_lora_alarm_selftest_esp32s3` uses the same STAR TX path with `GLD_SELFTEST_ALARM_FRAME=1`.
- Alarm self-test sends LPG confidence `30`, threshold `30`, encrypted payload length `29`, and `typeFlags=0xD0`.
- GLD self-test destination CH ID is corrected to `0x0064` to match the active CH runtime.
- After the live alarm proof, COM10 was returned to the normal GLD LoRa TX self-test target.

### Test Result

- `python firmware/tests/run_tests.py` -> `26/26 tests passed`
- `pio run -d firmware -e gld_lora_alarm_selftest_esp32s3 -t upload --upload-port COM10` -> success
- MQTT alarm proof:
  - topic `gld/server/alarm`
  - `outer.msgType=16`
  - `outer.typeFlags=208`
  - `outer.srcIdHex=0x0064`
  - `outer.dstIdHex=0x006F`
  - `nodeIdHex=0xF001`
  - `flags=17`
  - `alarm=true`
  - `decryptOk=true`
  - `gasClass=1 LPG`
  - `confidence=30`
  - `batteryMv=65535`
- `pio run -d firmware -e gld_lora_tx_selftest_esp32s3 -t upload --upload-port COM10` -> success after the alarm proof

### Notes

- This validates alarm push delivery end-to-end for bench.
- This does not yet validate production MESH ACK/retry behavior: Gateway sends compact ACK, but CH does not yet consume Gateway compact ACK frames and currently marks alarm sent after local MESH TX success.

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.5.8-ch0.5.2-gw0.1.2/`.

---

## v0.5.8 / CH v0.5.2 / Gateway v0.1.2 - 2026-06-17 17:20:00 Asia/Jakarta

**Summary:** Fix CH server-pull returning empty cache by changing CH STAR+MESH runtime from blocking alternating receive to non-blocking packet callbacks on both radios.

### Changed Files

- firmware/README.md
- firmware/shared/include/FirmwareVersion.h
- firmware/ch/src/ChStarMeshRuntimeMain.cpp
- firmware/tests/test_shared_protocol.py
- firmware/versions/version.md
- docs/progress.md

### Behavior

- CH Radio A STAR and Radio B MESH are both armed with `startReceive()` after boot.
- CH uses `setPacketReceivedAction(...)` callbacks to process STAR and MESH packets instead of blocking alternately on each radio.
- GLD periodic STAR frames should no longer be missed just because CH is waiting on MESH.
- Server pull should return cached GLD records once GLD has updated CH cache.

### Test Result

- `python firmware/tests/run_tests.py` -> `26/26 tests passed`
- `pio run -d firmware -e ch_star_mesh_runtime_esp32s3 -t upload --upload-port COM3` -> success
- CH serial verified STAR cache after non-blocking receive:
  - `CH_STAR_RX state=0 len=39`
  - `CH_CACHE_SUMMARY reason=star-rx used=1`
- Server-pull resimulation verified:
  - `gld/gateway/uplink` frameLen `50`, response status `0`, recordCount `1`
  - `gld/server/decoded` decryptOk `true`, node `0xF001`, gas `clearGas`, confidence `100`

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.5.8-ch0.5.1-gw0.1.2/`.

---

## v0.5.8 / CH v0.5.1 / Gateway v0.1.2 - 2026-06-17 16:35:00 Asia/Jakarta

**Summary:** Make GLD/CH serial monitors functional: GLD TX interval is 10 seconds, encrypted payload hex is hidden, and CH prints GLD cache summaries.

### Changed Files

- firmware/README.md
- firmware/shared/include/FirmwareVersion.h
- firmware/gld/src/GldLoRaTxSelfTestMain.cpp
- firmware/ch/src/ChStarMeshRuntimeMain.cpp
- firmware/tests/test_shared_protocol.py
- firmware/versions/version.md
- docs/progress.md

### Behavior

- GLD sends STAR self-test frames every `10000 ms`.
- GLD serial shows frame header/status only:
  - source/destination,
  - sequence,
  - `typeFlags`,
  - alarm/external power flags,
  - frame size and encrypted payload length.
- GLD no longer prints `GLD_STAR_TX_HEX`.
- CH serial no longer prints `CH_STAR_RX_HEX`.
- CH prints:
  - `CH_CACHE_SUMMARY`
  - `CH_CACHE_ENTRY`
  with node id, current/sent sequence, flags, alarm/external power, payload length, age, and unsent state.

### Test Result

- `python firmware/tests/run_tests.py` -> `26/26 tests passed`
- `pio run -d firmware -e gld_lora_tx_selftest_esp32s3 -t upload --upload-port COM10` -> success
- `pio run -d firmware -e ch_star_mesh_runtime_esp32s3 -t upload --upload-port COM3` -> success
- GLD serial verified: `GLD_TX_HEADER ... frameSize=39 payloadLen=29`, no encrypted payload hex dump.
- CH serial verified: `CH_CACHE_SUMMARY reason=star-rx used=1`, `CH_CACHE_ENTRY node=0xF001`.
- Gateway unchanged for this version; no Gateway upload required.

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.5.7-ch0.5.0-gw0.1.2/`.

---

## v0.5.7 / CH v0.5.0 / Gateway v0.1.2 - 2026-06-17 16:15:00 Asia/Jakarta

**Summary:** Add CH STAR+MESH runtime and Gateway MESH+MQTT runtime, then validate normal GLD data path through Node-RED Aedes.

### Changed Files

- firmware/README.md
- firmware/platformio.ini
- firmware/shared/include/FirmwareVersion.h
- firmware/ch/src/ClusterResponse.cpp
- firmware/ch/src/ChStarMeshRuntimeMain.cpp
- firmware/gateway/include/GatewayBoardPins.h
- firmware/gateway/src/GatewayMqttMeshMain.cpp
- firmware/tests/test_shared_protocol.py
- firmware/versions/version.md
- server/nodered/README.md
- server/nodered/apply-pertamina-gld-flow.js
- server/nodered/pertamina-gld-server.flow.json

### Test Result

- `python firmware/tests/run_tests.py` -> `26/26 tests passed`
- `pio run -d firmware -e gateway_mqtt_mesh_esp32s3 -t upload --upload-port COM38` -> success
- `pio run -d firmware -e ch_star_mesh_runtime_esp32s3 -t upload --upload-port COM3` -> success
- `pio run -d firmware -e gld_lora_tx_selftest_esp32s3 -t upload --upload-port COM10` -> success
- Node-RED flow deploy -> success, 36 Pertamina nodes applied

### Board / System Result

- Gateway COM38:
  - `GW_MESH_READY=1`
  - `GW_MQTT_CONNECT host=CHANGE_ME_MQTT_HOST port=1884 ok=1`
  - `GW_MQTT_SUB topic=gld/gateway/cmd/# ok=1`
  - `GW_MESH_TX reason=server-pull state=0 len=14`
  - `GW_MESH_RX state=0 len=50`
  - `GW_MQTT_PUBLISH topic=gld/gateway/uplink ok=1 frameLen=50 parseStatus=0`
- CH COM3:
  - `CH_RUNTIME_READY star=1 mesh=1`
- Node-RED / MQTT:
  - Aedes broker on `1884` was used because `1883` is occupied by the existing Mosquitto service on this laptop.
  - End-to-end normal pull produced `gld/server/decoded`.
  - Decoded event:
    - CH outer frame `MSG_CLUSTER_DATA_RESPONSE`, `srcId=0x0064`, `dstId=0x006F`
    - GLD `nodeId=0xF001`
    - `decryptOk=true`
    - plaintext `0064FFFF`
    - `gasClass=0 clearGas`
    - `confidence=100`
    - `batteryMv=65535`

### Notes

- This validates the normal/pull path: GLD STAR TX -> CH cache -> Gateway pull command -> CH MESH response -> Gateway MQTT uplink -> Node-RED decode.
- Gateway uses MQTT/LAN, not AP mode.
- Alarm push path is implemented in CH/Gateway runtime but still needs a live alarm-frame board test.
- Port `1884` is a bench workaround for this laptop's current Mosquitto conflict on `1883`.

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.5.7-ch0.4.3/`, then remove the new `firmware/gateway/` files and `firmware/ch/src/ChStarMeshRuntimeMain.cpp` if rolling back manually.

---

## v0.5.7 / CH v0.4.3 - 2026-06-17 14:30:12 Asia/Jakarta

**Summary:** Add and validate GLD-to-CH STAR LoRa link self-test with contract-compatible 39-byte GLD uplink frames.

### Changed Files

- firmware/README.md
- firmware/platformio.ini
- firmware/shared/include/FirmwareVersion.h
- firmware/ch/include/ChBoardPins.h
- firmware/ch/src/ChStarRxSelfTestMain.cpp
- firmware/gld/src/GldLoRaTxSelfTestMain.cpp
- firmware/tests/test_shared_protocol.py
- firmware/versions/version.md

### Test Result

- `python firmware/tests/run_tests.py` -> `26/26 tests passed`
- `pio run -d firmware -e ch_star_rx_selftest_esp32s3 -t upload --upload-port COM9` -> success
- `pio run -d firmware -e gld_lora_tx_selftest_esp32s3 -t upload --upload-port COM10` -> success

### Board Result

- GLD TX self-test built a valid `SENSOR_DATA` AppFrame:
  - `frameSize=39`
  - `typeFlags=0x90`
  - `alarm=0`
  - `recordFlags=0x10`
  - encrypted payload length `29`
  - `GLD_LORA_TX_RESULT=PASS`
- CH Radio A / U1 used the proven init pattern from `C:\Users\asus\Downloads\Implementasi Sistem\Implementasi Sistem\ClusterHead_DualLoRa` while keeping the pin map and STAR settings aligned with `docs/design/ch/design.md`.
- CH Radio A / U1 init result:
  - `CH_STAR_PROBE radio=A/U1 beginState=0`
  - `CH_STAR_ACTIVE_RADIO=A/U1`
  - `CH_STAR_RX_READY=1`
- CH received and parsed one GLD frame:
  - `CH_STAR_RX_STATE=0 radio=A/U1 len=39 rssi=-97.00 snr=11.25`
  - `CH_STAR_PARSE status=Ok nodeId=0xF001 chId=0x0001 seq=12 typeFlags=0x90 alarm=0 externalPower=1 payloadLen=29`
  - `CH_LORA_RX_RESULT=PASS`

### Notes

- This self-test validates the physical GLD-to-CH STAR link and CH uplink parser.
- It does not yet validate alarm ACK/retry, production inference, MESH forwarding, gateway, or server delivery.
- The initial CH init failed with `RADIOLIB_ERR_CHIP_NOT_FOUND` until the proven CH init details were adapted: global `SPI`, `SPISettings(2000000, MSBFIRST, SPI_MODE0)`, explicit reset low/high timing, and `begin(..., false)`.

### Rollback

Restore changed existing files from:

- `firmware/versions/backups/v0.5.6-ch0.4.0/`
- `firmware/versions/backups/v0.5.7-ch0.4.1/`
- `firmware/versions/backups/v0.5.7-ch0.4.2/`

Remove new `ChBoardPins`, `ChStarRxSelfTestMain`, and `GldLoRaTxSelfTestMain` files if rolling back manually.

---

## Policy Checkpoint - 2026-06-16 10:11:22 Asia/Jakarta

**Summary:** Initialize firmware versioning and storage-efficient rollback policy before firmware coding starts.

### Decisions

- Firmware versions use `MAJOR.MINOR.PATCH`.
- Any official firmware source/config change bumps at least `PATCH`.
- Build metadata includes full date and time.
- Backups store only files changed by a version.
- Backup folders preserve original relative paths.
- Full binary artifacts are kept only for milestone or deployed releases.

### Initial Planned Versions

- GLD: `v0.1.0`
- CH: `v0.1.0`

### Rollback

No firmware rollback exists yet because firmware source has not been implemented.

---

## v0.5.6 / CH v0.4.0 - 2026-06-17 13:56:00 Asia/Jakarta

**Summary:** Retest GLD nulling self-test with `0.0001V` threshold and document that the current algorithm validates DAC response but does not yet optimize toward zero.

### Changed Files

- firmware/README.md
- firmware/shared/include/FirmwareVersion.h
- firmware/gld/src/GldNullingSelfTestMain.cpp
- firmware/tests/test_shared_protocol.py
- firmware/versions/version.md

### Test Result

- `python firmware/tests/run_tests.py` -> `25/25 tests passed`
- `pio run -d firmware -e gld_nulling_selftest_esp32s3 -t upload --upload-port COM10` -> success
- `pio device monitor -p COM10 -b 115200 --raw` -> timed out after capturing final result; serial log included `NULLING_SELFTEST_RESULT=PASS`

### Board Result

- `NULLING_CONFIG thresholdV=0.000100`
- `POWER_SELFTEST_RESULT=PASS`, `ADS_BEGIN_RESULT=PASS`, and `DAC_MUX_BEGIN_RESULT=PASS`
- Final result: `NULLING_SELFTEST_RESULT=PASS`

| Channel | Sensor | Before V | DAC Code | After V | Closer To Zero |
|---|---:|---:|---:|---:|---|
| 0 | MQ8 | 0.000803 | 418 | 0.000804 | NO |
| 1 | MQ135 | 0.000279 | 956 | 0.000635 | NO |
| 2 | MQ3 | 0.000121 | 860 | 0.000217 | NO |
| 3 | MQ5 | -0.001225 | 967 | -0.000958 | YES |
| 4 | MQ4 | 0.000206 | 584 | 0.000487 | NO |
| 5 | MQ7 | -0.000381 | 271 | -0.000065 | YES |
| 6 | MQ6 | 0.000711 | 337 | 0.001342 | NO |
| 7 | MQ2 | 0.000245 | 448 | 0.000588 | NO |

### Interpretation

- `PASS` means ADS1256, TCA9548A, MCP4725, and per-channel DAC response were validated under external power.
- It does not mean production-quality zero nulling.
- The current algorithm searches for `abs(voltage - baseline) >= threshold`; production nulling must search for the DAC code that minimizes `abs(voltage)`.

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.5.5-ch0.4.0/`.

---

## v0.5.5 / CH v0.4.0 - 2026-06-17 13:20:00 Asia/Jakarta

**Summary:** Add GLD nulling self-test target for external-power before/after DAC nulling bring-up without LoRa TX or production profile persistence.

### Changed Files

- firmware/README.md
- firmware/platformio.ini
- firmware/shared/include/FirmwareVersion.h
- firmware/gld/include/BoardPins.h
- firmware/gld/include/GldDacMux.h
- firmware/gld/src/GldDacMux.cpp
- firmware/gld/src/GldNullingSelfTestMain.cpp
- firmware/tests/test_shared_protocol.py
- firmware/versions/version.md

### Test Result

- `python firmware/tests/run_tests.py` -> `25/25 tests passed`
- `pio run -d firmware -e gld_nulling_selftest_esp32s3` -> success
- `pio run -d firmware -e gld_nulling_selftest_esp32s3 -t upload --upload-port COM10` -> success
- `pio device monitor -p COM10 -b 115200 --raw` -> timed out after capturing final result; serial log included `NULLING_SELFTEST_RESULT=PASS`

### Board Result

- Power: `mode=5v`, `externalPower=1`, `pg24=0`, `POWER_SELFTEST_RESULT=PASS`.
- ADS1256: `ADS_BEGIN_RESULT=PASS`.
- DAC mux: `DAC_MUX_BEGIN_RESULT=PASS`.
- Nulling: all 8 channels produced valid before readings, successful DAC search, valid after readings, and final `NULLING_SELFTEST_RESULT=PASS`.

| Channel | Sensor | Before V | DAC Code | After V | Result |
|---|---:|---:|---:|---:|---|
| 0 | MQ8 | 0.000806 | 419 | 0.005827 | PASS |
| 1 | MQ135 | 0.000280 | 957 | 0.001203 | PASS |
| 2 | MQ3 | 0.000119 | 861 | 0.000360 | PASS |
| 3 | MQ5 | -0.001223 | 968 | -0.000175 | PASS |
| 4 | MQ4 | 0.000206 | 585 | 0.001855 | PASS |
| 5 | MQ7 | -0.000382 | 275 | 0.001161 | PASS |
| 6 | MQ6 | 0.000712 | 336 | 0.001264 | PASS |
| 7 | MQ2 | 0.000244 | 436 | 0.000787 | PASS |

### Safety Notes

- Nulling self-test is blocked unless `externalPower=1`.
- The target writes DAC volatile registers only (`writeDAC(value, false)`), not MCP4725 EEPROM.
- The target does not transmit LoRa, build running `SENSOR_DATA`, run inference, publish MQTT, or save a production nulling profile.

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.5.4-ch0.4.0/` and remove the new `GldDacMux` / `GldNullingSelfTestMain` files if rolling back manually.

---

## v0.5.4 / CH v0.4.0 - 2026-06-17 12:52:21 Asia/Jakarta

**Summary:** Correct GLD external-power privilege semantics so inferred external 5V receives the same privilege as 24V, while PG24 remains a separate 24V-only signal.

### Changed Files

- firmware/README.md
- firmware/shared/include/FirmwareVersion.h
- firmware/gld/include/GldPower.h
- firmware/gld/src/GldPower.cpp
- firmware/gld/src/GldSensorSelfTestMain.cpp
- firmware/tests/test_shared_protocol.py
- firmware/versions/version.md

### Test Result

- `python firmware/tests/run_tests.py` -> `24/24 tests passed`
- `pio run -d firmware -e gld_sensor_selftest_esp32s3 -t upload --upload-port COM10` -> success
- `pio device monitor -p COM10 -b 115200 --raw` -> firmware `0.5.4`, `POWER_SELFTEST mode=5v`, `externalPower=1`, `pg24=0`, `POWER_SELFTEST_RESULT=PASS`, `LORA_SELFTEST_RESULT=PASS`, and `SENSOR_SELFTEST_RESULT=PASS`

### Board Result

- Expected on current external 5V setup: `mode=5v`, `externalPower=1`, `pg24=0`, and `POWER_SELFTEST_RESULT=PASS`.
- Meaning: external privilege applies to both `5v` and `24v`; only `battery` is power-limited.

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.5.3-ch0.4.0/`.

---

## v0.5.3 / CH v0.4.0 - 2026-06-17 12:45:23 Asia/Jakarta

**Summary:** Complete GLD board self-test coverage for power-mode detection and SX1262 LoRa init while keeping the test non-production and no-TX.

### Changed Files

- firmware/README.md
- firmware/shared/include/FirmwareVersion.h
- firmware/gld/include/GldPower.h
- firmware/gld/src/GldPower.cpp
- firmware/gld/src/GldSensorSelfTestMain.cpp
- firmware/tests/test_shared_protocol.py
- firmware/versions/version.md

### Test Result

- `python firmware/tests/run_tests.py` -> `24/24 tests passed`
- `pio run -d firmware -e gld_sensor_selftest_esp32s3 -t upload --upload-port COM10` -> success
- `pio device monitor -p COM10 -b 115200 --raw` -> firmware `0.5.3`, `POWER_SELFTEST_RESULT=PASS`, `ADS_BEGIN_RESULT=PASS`, `LORA_SELFTEST_RESULT=PASS`, `SENSOR_SELFTEST_PASS_SCAN=4`, and `SENSOR_SELFTEST_RESULT=PASS`

### Board Result

- Power mode reported `mode=5v`, `rawAdc=0`, `batteryMv=65535`, `batteryValid=0`, and `pg24=0`. This is expected for the current external 5V setup because 5V has no dedicated detect pin; when BatMon and PG24 are both inactive, firmware infers external 5V.
- SX1262/E22 LoRa init with TCXO `1.6V` returned `-707`, then XTAL/TCXO `0V` fallback returned `0`; standby also returned `0`.
- ADS1256 remained readable and all 8 sensor channels settled to valid, non-saturated readings after LoRa init.
- No production LoRa payload, inference, dataset, nulling, MQTT, or encrypted running frame was transmitted.

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.5.2-ch0.4.0/`.

---

## v0.5.2 / CH v0.4.0 - 2026-06-17 12:31:04 Asia/Jakarta

**Summary:** Finalize GLD ADS1256 sensor self-test behavior for the replacement board by waiting for adaptive gain settling before declaring self-test pass/fail.

### Changed Files

- firmware/README.md
- firmware/shared/include/FirmwareVersion.h
- firmware/gld/src/GldSensorSelfTestMain.cpp
- firmware/tests/test_shared_protocol.py
- firmware/versions/version.md

### Test Result

- `python firmware/tests/run_tests.py` -> `24/24 tests passed`
- `pio run -d firmware -e gld_sensor_selftest_esp32s3 -t upload --upload-port COM10` -> success
- `pio device monitor -p COM10 -b 115200 --raw` -> firmware `0.5.2`, `ADS_BEGIN_RESULT=PASS`, `SENSOR_SELFTEST_PASS_SCAN=4`, and `SENSOR_SELFTEST_RESULT=PASS`

### Board Result

- First tested board: ADS begin/register read failed and hardware probing found ADS VREFP around `0.8V`, so this is treated as a board/reference issue.
- Replacement board: ADS begin passed, register readback was `STATUS=0x36`, `MUX=0x0F`, `ADCON=0x06`, `DRATE=0xF0`, and later scans produced valid voltage and moving-average readings on all 8 channels after gain settling.

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.5.1-ch0.4.0/`.

---

## v0.5.1 / CH v0.4.0 - 2026-06-17 11:20:17 Asia/Jakarta

**Summary:** Replace the custom low-level ADS1256 probe with an adapter over the copied legacy `ADS1256-main` library so GLD sensor self-test follows the field-proven voltage-read path.

### Changed Files

- firmware/platformio.ini
- firmware/README.md
- firmware/shared/include/FirmwareVersion.h
- firmware/gld/include/Ads1256Probe.h
- firmware/gld/src/Ads1256Probe.cpp
- firmware/tests/test_shared_protocol.py
- firmware/versions/version.md
- firmware/lib/

### Test Result

- Pending until host tests, PlatformIO build, COM10 upload, and serial monitor are rerun.

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.5.0-ch0.4.0/`. Remove `firmware/lib/` if a full rollback to pre-v0.5.1 library state is required.

---

## v0.5.0 / CH v0.4.0 - 2026-06-17 11:12:34 Asia/Jakarta

**Summary:** Add GLD board pin, power, moving-average, ADS1256 probe, and sensor self-test target for first real sensor bring-up without LoRa or inference.

### Changed Files

- firmware/platformio.ini
- firmware/README.md
- firmware/shared/include/FirmwareVersion.h
- firmware/gld/include/BoardPins.h
- firmware/gld/include/GldSensorTypes.h
- firmware/gld/include/GldMovingAverage.h
- firmware/gld/src/GldMovingAverage.cpp
- firmware/gld/include/GldPower.h
- firmware/gld/src/GldPower.cpp
- firmware/gld/include/Ads1256Probe.h
- firmware/gld/src/Ads1256Probe.cpp
- firmware/gld/src/GldSensorSelfTestMain.cpp
- firmware/tests/test_shared_protocol.py

### Test Result

- `python firmware/tests/run_tests.py` -> `24/24 tests passed`
- `pio run -d firmware -e gld_selftest_esp32s3` -> success
- `pio run -d firmware -e gld_sensor_selftest_esp32s3` -> success
- `pio run -d firmware -e gld_sensor_selftest_esp32s3 -t upload --upload-port COM10` -> success
- `pio device monitor -p COM10 -b 115200 --raw` -> firmware boot/logging success, `ADS_BEGIN_RESULT=FAIL`, ADS register readback `STATUS=0x00`, `MUX=0x00`, `ADCON=0x00`, `DRATE=0x00`, and all 8 channels reported `status=NotReady`.

### Board Diagnosis

The GLD ESP32-S3 path, serial output, and sensor self-test firmware execute on
COM10. Sensor values are not considered valid yet because ADS1256 configuration
readback failed. Check ADS1256 power/reference, SPI wiring, `DRDY`, `CS`,
`SYNC/PDWN`, and board population/power before treating channel voltage output
as sensor data.

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.4.0-ch0.4.0/`, then remove new GLD sensor self-test scaffold files.

---

## v0.4.0 / CH v0.4.0 - 2026-06-16 14:41:54 Asia/Jakarta

**Summary:** Add board-independent runtime scaffolds for CH alarm handling/TX queues/pull requests and GLD retry/provisioning/radio abstractions so the remaining work before board testing is mostly driver integration.

### Changed Files

- firmware/README.md
- firmware/shared/include/FirmwareVersion.h
- firmware/shared/include/FirmwareConfig.h
- firmware/shared/src/FirmwareConfig.cpp
- firmware/shared/include/RadioTransport.h
- firmware/gld/include/GldRetryState.h
- firmware/gld/src/GldRetryState.cpp
- firmware/gld/include/GldProvisioning.h
- firmware/gld/src/GldProvisioning.cpp
- firmware/ch/include/AlarmQueue.h
- firmware/ch/src/AlarmQueue.cpp
- firmware/ch/include/ChTxQueue.h
- firmware/ch/src/ChTxQueue.cpp
- firmware/ch/include/ChPullRequest.h
- firmware/ch/src/ChPullRequest.cpp
- firmware/ch/include/ChRuntime.h
- firmware/ch/src/ChRuntime.cpp
- firmware/tests/test_shared_protocol.py

### Test Result

- `python firmware/tests/run_tests.py` -> `23/23 tests passed`
- `pio run -d firmware -e gld_selftest_esp32s3` -> success
- Board upload intentionally skipped; board COM is disconnected.

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.3.1-ch0.3.0/`, then remove new runtime/config/queue scaffold files.

---

## v0.3.1 / CH v0.3.0 - 2026-06-16 13:02:19 Asia/Jakarta

**Summary:** Add CH opaque NodeCache and ClusterDataResponse packing scaffold for board-independent STAR RX/cache and MESH forwarding logic.

### Changed Files

- firmware/README.md
- firmware/shared/include/FirmwareVersion.h
- firmware/ch/include/NodeCache.h
- firmware/ch/src/NodeCache.cpp
- firmware/ch/include/ClusterResponse.h
- firmware/ch/src/ClusterResponse.cpp
- firmware/tests/test_shared_protocol.py

### Test Result

- `python firmware/tests/run_tests.py` -> `17/17 tests passed`
- `pio run -d firmware -e gld_selftest_esp32s3` -> success
- Board upload intentionally skipped; board COM is disconnected.

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.3.1-ch0.2.0/`, then remove new CH cache/response scaffold files.

---

## v0.3.1 / CH v0.2.0 - 2026-06-16 11:53:43 Asia/Jakarta

**Summary:** Add CH uplink parser/compact ACK scaffold and expand host tests for GLD frame builder semantics, opaque CH payload handling, and ACK frame contract.

### Changed Files

- firmware/platformio.ini
- firmware/README.md
- firmware/shared/include/FirmwareVersion.h
- firmware/gld/include/GldFrameBuilder.h
- firmware/gld/src/GldFrameBuilder.cpp
- firmware/ch/include/ChUplink.h
- firmware/ch/src/ChUplink.cpp
- firmware/tests/test_shared_protocol.py

### Test Result

- `python firmware/tests/run_tests.py` -> `13/13 tests passed`
- `pio run -d firmware -e gld_selftest_esp32s3` -> success
- Board upload intentionally skipped; board COM was unplugged.

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.3.0/`, then remove new CH scaffold files.

---

## v0.3.0 - 2026-06-16 11:44:18 Asia/Jakarta

**Summary:** Add GLD frame builder and extend board self-test with vector, normal, alarm, retry, and clear frame checks.

### Changed Files

- firmware/shared/include/FirmwareVersion.h
- firmware/gld/include/GldFrameBuilder.h
- firmware/gld/src/GldFrameBuilder.cpp
- firmware/gld/src/main.cpp
- firmware/tests/test_shared_protocol.py

### Test Result

- `python firmware/tests/run_tests.py` -> `9/9 tests passed`
- `pio run -d firmware -e gld_selftest_esp32s3` -> success
- Pending: upload and serial read; COM10 was unavailable after board was unplugged.

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.2.2/`, then remove new `GldFrameBuilder` files.

---

## v0.2.2 - 2026-06-16 11:06:25 Asia/Jakarta

**Summary:** Make GLD self-test serial output more robust on ESP32-S3 by logging to both Arduino `Serial` and `Serial0`.

### Changed Files

- firmware/shared/include/FirmwareVersion.h
- firmware/gld/src/main.cpp
- firmware/tests/test_shared_protocol.py

### Test Result

- `python firmware/tests/run_tests.py` -> `9/9 tests passed`
- `pio run -d firmware -e gld_selftest_esp32s3` -> success
- `pio run -d firmware -e gld_selftest_esp32s3 -t upload --upload-port COM10` -> success
- `pio device monitor -p COM10 -b 115200` -> `SELFTEST_RESULT=PASS`

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.2.1/`.

---

## v0.2.1 - 2026-06-16 11:01:04 Asia/Jakarta

**Summary:** Rename board validation target from smoke-test to self-test to avoid ambiguity with gas/smoke terminology.

### Changed Files

- firmware/platformio.ini
- firmware/README.md
- firmware/shared/include/FirmwareVersion.h
- firmware/gld/include/GldSelfTestConfig.h
- firmware/gld/include/GldSmokeConfig.h
- firmware/gld/src/main.cpp
- firmware/tests/test_shared_protocol.py

### Test Result

- `python firmware/tests/run_tests.py` -> `9/9 tests passed`
- `pio run -d firmware -e gld_selftest_esp32s3` -> success
- Pending: board serial self-test harus mencetak `SELFTEST_RESULT=PASS`.

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.2.0/`.

---

## v0.2.0 - 2026-06-16 10:36:06 Asia/Jakarta

**Summary:** Tambah GLD ESP32-S3 smoke firmware dan wrapper AES-GCM berbasis mbedTLS untuk validasi board pertama.

### Changed Files

- firmware/platformio.ini
- firmware/README.md
- firmware/shared/include/FirmwareVersion.h
- firmware/shared/include/GldCrypto.h
- firmware/shared/src/GldCrypto.cpp
- firmware/gld/include/GldSmokeConfig.h
- firmware/gld/src/main.cpp
- firmware/tests/test_shared_protocol.py

### Test Result

- `python firmware/tests/run_tests.py` -> `9/9 tests passed`
- `pio run -d firmware -e gld_smoke_esp32s3` -> success
- Pending: board serial smoke-test harus mencetak `SMOKE_RESULT=PASS`.

### Rollback

Restore changed existing files from `firmware/versions/backups/v0.1.0/`, then remove new files listed above that do not exist in the backup.

---

## v0.1.0 - 2026-06-16 10:25:06 Asia/Jakarta

**Summary:** Initial shared protocol implementation for firmware phase 1. Added hardware-agnostic AppFrame, GLD payload, GLDRecord helpers, encrypted payload layout constants, AAD builder, and host-level contract tests.

### Changed Files

- firmware/README.md
- firmware/platformio.ini
- firmware/shared/include/FirmwareVersion.h
- firmware/shared/include/ProtocolConstants.h
- firmware/shared/include/AppFrame.h
- firmware/shared/src/AppFrame.cpp
- firmware/shared/include/GldPayload.h
- firmware/shared/src/GldPayload.cpp
- firmware/shared/include/GldRecord.h
- firmware/shared/src/GldRecord.cpp
- firmware/tests/test_shared_protocol.py
- firmware/tests/run_tests.py

### Test Result

```text
python firmware/tests/run_tests.py
9/9 tests passed
```

### Rollback

This is the initial firmware source version. No pre-change source backup is required. To rollback this version, remove the files listed above.
