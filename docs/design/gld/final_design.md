# Pertamina GLD Current Design - GLD Node

Status: current source mirror, 2026-06-29. Dokumen ini dibuat ulang dari
`docs/design/gld/design.md` dan firmware GLD saat ini. Imported baseline
`docs/design/gld/design.md` tidak diubah.

## 1. Scope

Dokumen ini adalah mirror GLD design terhadap firmware yang benar sedang
dikompilasi oleh workspace utama. Tujuannya bukan menyalin seluruh baseline
lama, tetapi menyaring baseline tersebut terhadap source firmware current.

Sumber yang dipakai untuk draft ini:

| Jenis | File |
|---|---|
| Imported baseline | `docs/design/gld/design.md` |
| PlatformIO current | `firmware/platformio.ini` |
| GLD main runtime | `firmware/gld/src/GldUnifiedMain.cpp` |
| GLD config | `firmware/config/GldConfig.h` |
| STAR LoRa config | `firmware/config/LoraStarConfig.h` |
| Server dataset config | `firmware/config/ServerConfig.h` |
| Board pins | `firmware/gld/include/BoardPins.h` |
| Mode manager | `firmware/gld/include/GldModeManager.h`, `firmware/gld/src/GldModeManager.cpp` |
| Command parser | `firmware/gld/include/GldCommandParser.h`, `firmware/gld/src/GldCommandParser.cpp` |
| Nulling | `firmware/gld/include/GldNullingProfile.h`, `firmware/gld/include/GldNullingService.h`, `firmware/gld/src/GldNullingService.cpp` |
| Uplink payload/crypto/frame | `firmware/shared/include/ProtocolConstants.h`, `firmware/shared/include/GldPayload.h`, `firmware/shared/src/GldPayload.cpp`, `firmware/gld/src/GldFrameBuilder.cpp` |
| Power | `firmware/gld/include/GldPower.h`, `firmware/gld/src/GldPower.cpp` |
| ML model wrapper | `firmware/gld/model/NeuralNetwork.*`, `model_data.*`, `scaler_params.*` |

## 2. Imported Baseline Adjustments

The imported baseline has many useful hardware and historical notes. The table
below records the important corrections made for the current firmware.

| Baseline topic | Current firmware truth |
|---|---|
| PlatformIO draft env | Active GLD runtime env is `gld`; the env uses the GLDW / ESP32-S3-WROOM-1U-N16R8 board profile. |
| Runtime mode names `RUNNING`, `TRAINING`, `SETUP` | Current mode enum is `INFERENCE`, `DATASET`, `NULLING`; command string `running` maps to `inference`. |
| Modbus RTU / RS485 runtime | Not compiled into the current GLD runtime envs. |
| EEPROM `boardId`, `modelFilePath`, `wiperArr` config | Current persistence uses ESP32 Preferences/NVS for mode and nulling profile. |
| CayenneLPP payload | Not used by current GLD uplink. Current payload is compact GLD plaintext encrypted by AES-GCM. |
| `LoRaPacketType`, `ackStatus`, health packet families | Not present in current GLD uplink contract. Current uplink is `AppFrame` + encrypted GLD payload. |
| One-shot battery sleep with TPL5110 DONE pulse | Current code initializes `PIN_TPL5110_DONE` LOW but does not implement a full one-shot DONE pulse/sleep loop. |
| MQTT `START_NULLING` service command | Current MQTT callback handles `SET_MODE`, `START_DATASET`, and `STOP_DATASET`; nulling is entered through `SET_MODE nulling`. |
| Normal LoRa telemetry 60 seconds | Current `GLD_TX_INTERVAL_MS` is `10000 ms`. |
| Generic SX127x wording | Current runtime uses SX1262 through RadioLib. |

## 3. Firmware Workspace

Current deploy/runtime environment in `firmware/platformio.ini`:

| Env | Board | Purpose |
|---|---|---|
| `gld` | `esp32-s3-devkitc-1` | Main GLD unified runtime for the GLDW / ESP32-S3-WROOM-1U-N16R8 board profile. |

The `gld` env sets 16 MB flash and OPI PSRAM options, defines
`BOARD_HAS_PSRAM`, enables `PGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8=1`, and keeps
`upload_speed = 57600` for the CH340 bench upload path.

Current GLD runtime source set:

| Group | Compiled source |
|---|---|
| Shared protocol | `AppFrame.cpp`, `GldCrypto.cpp`, `GldPayload.cpp`, `GldRecord.cpp` |
| GLD runtime | `GldAds1256Reader.cpp`, `GldCommandParser.cpp`, `GldDacMux.cpp`, `GldFrameBuilder.cpp`, `GldModeManager.cpp`, `GldMovingAverage.cpp`, `GldNullingService.cpp`, `GldPower.cpp`, `GldThresholdClassifier.cpp`, `GldUnifiedMain.cpp` |
| ML model | `NeuralNetwork.cpp`, `scaler_params.cpp`, `model_data.cpp` |

Excluded from this runtime env:

- old `gld/src/main.cpp`,
- self-test mains,
- old split `GldInferenceMain.cpp`, `GldDatasetMain.cpp`, and `GldNullingRuntimeMain.cpp`,
- CH source,
- docs, tests, and version logs.

Firmware identifiers:

| Field | Value |
|---|---|
| firmware name | `PertaminaGLD-GLD` |
| firmware version | `0.8.12` |
| protocol version | `0.1.0` |
| config schema version | `0.1.0` |

## 4. System Overview

Current GLD firmware is a unified ESP32-S3 runtime with three persistent modes:

```text
Sensors + ADS1256
    -> moving average / model input
    -> ML inference
    -> GLD compact payload
    -> AES-GCM encrypted payload
    -> AppFrame
    -> LoRa STAR uplink to CH
```

Dataset and nulling use the same board devices but different runtime behavior:

```text
dataset mode:
ADS1256 + DAC/nulling profile + WiFi/MQTT dataset capture

nulling mode:
ADS1256 + TCA9548A + MCP4725 DAC search + NVS profile save/retry + WiFi off
```

## 5. Hardware And Pins

### 5.1 Default 4D ESP32-S3 Profile

| Function | Pin/value |
|---|---|
| SPI SCK/MOSI/MISO | GPIO12/GPIO11/GPIO13 |
| ADS1256 CS/DRDY/SYNC | GPIO47/GPIO10/GPIO18 |
| LoRa CS/RST/BUSY/DIO1 | GPIO15/GPIO39/GPIO7/GPIO40 |
| LoRa RXEN/TXEN | GPIO5/GPIO6 |
| I2C SDA/SCL | GPIO8/GPIO9 |
| Status LED | GPIO41 |
| Alarm lamp | GPIO1 |
| Buzzer | GPIO2 |
| DC fan | GPIO42 |
| TPL5110 DONE symbol | GPIO14, initialized OUTPUT LOW |
| Battery ADC | GPIO4 |
| 24V power-good input | GPIO45 |
| User button symbol | GPIO16 |
| TCA9548A address | `0x71` |
| MCP4725 address | `0x60` |
| DAC range | `0..4095` |

### 5.2 WROOM Bench Profile

When `PGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8=1`, LoRa pin mapping changes:

| Function | Pin/value |
|---|---|
| LoRa CS/RST/BUSY/DIO1 | GPIO7/GPIO2/GPIO15/GPIO1 |
| LoRa RXEN/TXEN | GPIO5/GPIO6 |
| Alarm lamp | disabled, `-1` |
| Buzzer | disabled, `-1` |
| Board profile log | `WROOM-1U-N16R8` |

This is an important difference from the baseline document: on the WROOM bench
profile, GPIO1 and GPIO2 are consumed by LoRa, so alarm lamp and buzzer are
disabled by the board profile.

### 5.3 Sensor Order

| Program channel | Sensor | ADS1256 input | TCA/MCP mux channel | Runtime feature index |
|---:|---|---:|---:|---:|
| 0 | MQ8 | 0 | 7 | 0 |
| 1 | MQ135 | 1 | 6 | 1 |
| 2 | MQ3 | 2 | 5 | 2 |
| 3 | MQ5 | 7 | 4 | 3 |
| 4 | MQ4 | 6 | 3 | 4 |
| 5 | MQ7 | 5 | 2 | 5 |
| 6 | MQ6 | 4 | 1 | 6 |
| 7 | MQ2 | 3 | 0 | 7 |

The board-side ADS order includes AINCOM between AIN2 and AIN7; AINCOM is not a
sensor channel. Firmware maps the eight MQ sensors to ADS inputs
`{0, 1, 2, 7, 6, 5, 4, 3}` and keeps runtime arrays, `feature_order`, moving
average, and model input in the program-channel order above.

## 6. Power Detection

`GldPower` samples GPIO4 sixteen times and calculates battery voltage using a
3.3 V ADC reference and divider ratio `3.0`.

| Condition | Runtime power mode | `externalPower` |
|---|---|---:|
| GPIO45 HIGH | `24v` | 1 |
| GPIO45 LOW and battery ADC valid | `battery` | 0 |
| GPIO45 LOW and battery ADC invalid | `5v` | 1 |

Battery value is treated invalid when calculated voltage is `<=0.05 V` or
`>20.0 V`. Invalid battery in the GLD payload becomes `0xFFFF`.

Current firmware initializes `PIN_TPL5110_DONE` LOW. It does not implement the
baseline one-shot wake, transmit, pulse DONE, and sleep sequence.

## 7. Runtime Modes

Current mode enum:

| Mode string | Enum value | Runtime behavior |
|---|---:|---|
| `inference` | 0 | ADS scan, moving average, ML inference, alarm outputs, LoRa STAR uplink, LoRa RX window, WiFi/MQTT explicitly off. |
| `running` | alias | Parsed as `inference`. |
| `dataset` | 1 | ADS + DAC/nulling profile + WiFi/MQTT dataset capture. |
| `nulling` | 2 | Offline ADS/DAC nulling calibration and NVS profile save/retry, WiFi/MQTT explicitly off. |

Mode is stored in ESP32 Preferences namespace `gld`, key `mode`. Invalid or
missing value falls back to `inference`.

Mode switch sources:

| Source | Command shape |
|---|---|
| USB `Serial` and UART0 `Serial0` | `SET_MODE inference`, `SET_MODE running`, `SET_MODE dataset`, `SET_MODE nulling` |
| MQTT in dataset mode | JSON `{"cmd":"SET_MODE","mode":"..."}` on command/dataset topics |
| LoRa downlink | `MSG_NODE_DOWNLINK`, authenticated payload `0x81 + mode + commandId + cmacTag4` |

Debug commands:

| Command | Effect |
|---|---|
| `DEBUG_ON` | Enables serial debug logging. |
| `DEBUG_OFF` | Disables serial debug logging. |

## 8. Boot Flow And Diagnostics

At boot, `GldUnifiedMain.cpp`:

1. Starts `Serial` and `Serial0`.
2. Initializes board pins and GLD power pins.
3. Reads persistent GLD mode from NVS.
4. Logs firmware name, version, protocol version, build date/time, mode, debug state, and board profile.
5. Reads GLD power mode.
6. Initializes ADS1256 and probes boot hardware.
7. Probes I2C/TCA/MCP devices and optionally tests DAC writes when external power is available.
8. Initializes mode-specific devices.
9. Prints `[BOOT_IC_REPORT]` table.

Boot report rows include:

| Row | Meaning |
|---|---|
| `POWER` | Power mode, external flag, battery mV. |
| `SPI_BUS` | Shared SPI pin report. |
| `ADS1256` | ADS init, DRDY, status register. |
| `I2C_BUS` | I2C pins. |
| `TCA9548A` | I2C ACK for mux. |
| `MCP4725-<sensor>` | I2C ACK and optional DAC write test for each sensor. |
| `SX1262` | LoRa begin state when checked. |
| `ML_MODEL` | ML model init/classes when checked. |
| `MODE_READY` | Mode readiness status and detail. |

## 9. Inference Mode

Inference mode initializes:

- `NeuralNetwork`,
- SX1262 STAR radio,
- ADS scanning path.

Loop behavior:

| Interval | Action |
|---:|---|
| `1000 ms` | Read ADS channels, update moving averages, run ML when all channels are primed. |
| `10000 ms` | Build encrypted GLD uplink frame, transmit over LoRa STAR, then open RX window. |

ML input:

```text
modelInput[modelIndex] = (voltage - feature_means[modelIndex]) / feature_stds[modelIndex]
```

Model class mapping:

| Predicted class | Protocol gas class | Label |
|---:|---:|---|
| 0 | 0 | clearGas |
| 1 | 1 | LPG |
| 2 | 2 | methane |
| 3 | 3 | propane |
| 4 | 4 | butane |
| other | 5 | anomaly |

Confidence is stored as `uint8_t(confidenceFloat * 100.0f)`.

Alarm rule:

```text
alarm = gasClass != clearGas && confidence >= 30
```

When alarm state changes, firmware updates alarm lamp, buzzer, and status LED
through optional pins. These outputs are active-low: ON writes LOW, OFF writes
HIGH. On the WROOM profile, alarm lamp and buzzer are disabled by pin value
`-1`, so only valid optional pins are driven.

Alarm lamp, buzzer, and status LED are active-low.

## 10. LoRa STAR Runtime

Current STAR config:

| Parameter | Value |
|---|---:|
| Frequency | 920.0 MHz |
| Bandwidth | 125 kHz |
| Spreading factor | 7 |
| Coding rate | 4/5 |
| Sync word | `0x12` |
| TX power | 17 dBm |
| Preamble | 8 |
| SPI speed | 2 MHz |
| TCXO first try | 1.6 V |
| XTAL fallback | 0.0 V |

LoRa init tries TCXO 1.6 V first and falls back to 0.0 V when RadioLib returns
`RADIOLIB_ERR_SPI_CMD_FAILED`.

Transmit flow:

1. Read power state.
2. Choose `batteryMv` or `0xFFFF`.
3. Build `GldFrameBuilderConfig`.
4. Build encrypted GLD uplink frame.
5. Force ADS CS HIGH before LoRa transmit.
6. Transmit frame.
7. Clear RXEN/TXEN.
8. Increment sequence if TX succeeds.
9. Open RX window for downlink.

RX window:

| Item | Value |
|---|---:|
| Duration | `2000 ms` |
| Accepted AppFrame type | `MSG_NODE_DOWNLINK` |
| Accepted destination | local GLD node ID |
| Accepted command payload | byte 0 `0x81`, byte 1 mode `0|1|2`, byte 2..3 `commandId`, byte 4..7 AES-CMAC tag |
| Auth input | CH srcId + GLD dstId + AppFrame seq + first 4 payload bytes |
| Replay guard | `commandId` must be newer than the last accepted downlink command |
| Action | switch mode via NVS write and `ESP.restart()` |

This differs from stale baseline text that said LoRa downlink command execution
was not active.

## 11. GLD Payload And AppFrame

Current plaintext GLD payload is 4 bytes:

| Offset | Field | Size |
|---:|---|---:|
| 0 | `gasClass` | 1 |
| 1 | `confidence` | 1 |
| 2..3 | `batteryMv` big-endian | 2 |

Payload validation:

| Field | Rule |
|---|---|
| `gasClass` | `<= GLD_GAS_ANOMALY` |
| `confidence` | `<= 100` |
| `batteryMv` | uint16; `0xFFFF` means unavailable/invalid |

Encrypted payload size:

| Part | Size |
|---|---:|
| key ID | 1 |
| AES-GCM nonce | 12 |
| ciphertext | 4 |
| AES-GCM tag | 12 |
| total | 29 |

AAD:

| Offset | Field |
|---:|---|
| 0..1 | node ID |
| 2 | GLD seq |
| 3 | record flags |
| 4 | key ID |

AppFrame:

| Field | Current GLD value |
|---|---|
| message type | `MSG_SENSOR_DATA` |
| source | `GLD_NODE_ID` |
| destination | `GLD_CH_ID` |
| seq | `txSeq` |
| payload | 29-byte encrypted GLD payload |

`typeFlags`:

| Bit(s) | Meaning |
|---|---|
| 0..5 | message type |
| 6 | alarm flag (`FLAG_ALARM_ACK`) |
| 7 | GLD external power flag (`FLAG_GLD_EXT_POWER`) |

The current firmware does not use the baseline `LoRaPacketType`, `ackStatus`,
site ID, GPS, CayenneLPP, or larger health/status packet families in the active
GLD uplink.

## 12. Nulling Mode

Current nulling mode is a persistent GLD mode. It is offline/local: the nulling
mode setup calls the offline-mode guard and the loop does not connect WiFi,
MQTT, subscribe, or publish.

`inference`/`running` and `nulling` call the offline-mode guard.

Nulling profile:

| Field | Type | Meaning |
|---|---|---|
| `validMagic` | `uint8_t` | `0xA5` when valid |
| `profileId` | `uint8_t` | increments on each new saved profile |
| `dacCode[8]` | `uint16_t` | best DAC code per sensor channel |
| `baselineV[8]` | `float` | baseline voltage during nulling |
| `afterV[8]` | `float` | voltage after applying selected DAC code |
| `channelOk[8]` | `uint8_t` | 1 when channel succeeded |

Persistence:

| Item | Value |
|---|---|
| Storage API | ESP32 Preferences |
| Namespace | `gld-null` |
| Key | `profile` |

Nulling service result:

| Status | Meaning |
|---|---|
| `Ok` | All channels completed. |
| `AdsNotReady` | ADS object not initialized. |
| `DacNotReady` | DAC mux object not initialized. |
| `AllChannelsFailed` | No channel succeeded. |
| `PartialSuccess` | Some channels succeeded, but unified runtime must retry and not save as complete profile. |

Algorithm shape:

1. For each sensor channel, write DAC code 0.
2. Baseline prescan tries codes `0..10`.
3. Exponential search doubles the DAC code until the reading crosses up to
   (near) absolute zero volts — not until it merely differs from baseline.
   A channel with a deep negative baseline needs a large compensation swing
   before it reaches zero; targeting "delta from baseline exceeds threshold"
   locks onto baseline-adjacent noise long before the real crossing.
4. Binary search narrows to the precise code of that zero crossing.
5. Confirm window scans candidate codes around the crossing (10 codes for a
   baseline >= 0 channel, 20 for baseline < 0 — 10 before + 10 after the
   binary search result) and re-verifies every non-negative candidate with a
   second independent read, smallest-voltage-first, discarding any that flip
   negative on reconfirmation (the reading can swing several hundred
   microvolts to a few millivolts per DAC LSB right at the crossing, so a
   single sample set closest to zero is not reliable enough on its own). If
   no candidate reconfirms non-negative, falls back to the first candidate
   clearing the configured minimum final voltage.
6. Final code is written and the channel is read again (a third independent
   read). If that still comes back negative, the code is nudged up one DAC
   LSB at a time (re-checking each time, up to `final check max bumps`)
   instead of failing the channel outright — the priority is a positive
   final result, not the exact code the confirm stage picked.
7. Channel passes only when the final read is valid and at or above the
   configured minimum final voltage.

Key constants:

| Constant | Value |
|---|---:|
| average count | 8 |
| confirm count | 10 |
| baseline prescan max DAC code | 10 |
| exponential initial step | 1 |
| exponential max step | 2048 |
| confirm window (baseline >= 0) | 10 (5 before + 5 after selected) |
| confirm window (baseline < 0) | 20 (10 before + 10 after selected) |
| final check max bumps | 20 |
| settle delay | 5 ms |
| stage transition pause | 2000 ms |
| delta threshold (default, configurable) | `0.0001 V` |
| minimum final voltage (default, configurable) | `0.0 V` |

`delta threshold` and `minimum final voltage` are runtime-tunable via
`SET_NULLING_CONFIG_JSON {"thresholdV":<V>,"minFinalV":<V>}`, persisted to NVS
namespace `gld-nullcfg`, and loaded back into defaults on boot.
`GLD_STATUS_JSON.nulling` reports the currently active `thresholdV`/`minFinalV`,
and `GLD_INFO_JSON.capabilities.nullingConfig` advertises the command. With
`minFinalV` left at its `0.0 V` default, verified 8/8 success on a reference
board where several channels have a deep negative ADC baseline (down to
-15 mV), all landing at a small positive residual (roughly 0.1-3 mV) after
the crossing-search + reconfirm + final-bump changes above.
Between each algorithm phase (baseline -> exponential -> binary search ->
confirm) the firmware pauses `stage transition pause` (2000 ms, ticking the
WDT/serial in the background) and logs `NULLING_STAGE_TRANSITION`, so an app
polling the serial log can visibly show each phase instead of the whole
channel flashing by.

Nulling runtime behavior:

- If hardware is not ready, schedule retry.
- On complete saved profile, write mode `INFERENCE`, wait `800 ms`, and restart.
- On partial/fail/NVS save failure, schedule retry after `5000 ms`.
- Serial mode commands are still checked between retry attempts.

## 13. Dataset Mode

Dataset mode initializes ADS and DAC, loads or creates a nulling profile, then
connects WiFi/MQTT and waits for dataset commands.

MQTT topics:

| Topic | Direction |
|---|---|
| `gas-leak-detector/F001/cmd` | command in / command ack source |
| `gas-leak-detector/F001/dataset` | dataset command in |
| `gas-leak-detector/F001/dataset/data` | data out |
| `gas-leak-detector/F001/dataset/status` | status out |
| `gas-leak-detector/F001/dataset/summary` | summary out |
| `gas-leak-detector/F001/cmd/ack` | command ack out |

`GldConfig.h` also defines `nulling/result` and `nulling/status` topic macros,
but the current unified runtime does not publish to those topics.

Accepted MQTT commands:

| Command | Topic handling | Effect |
|---|---|---|
| `SET_MODE` | command or dataset topic | Save mode and restart. |
| `START_DATASET` | dataset command handling | Start dataset session if profile exists. |
| `STOP_DATASET` | dataset command handling | Stop session and publish summary/status. |

`START_DATASET` fields:

| Field | Default |
|---|---|
| `label` | `unknown` |
| `target_samples` | 0 |
| `sample_interval_ms` | 1000 |
| `max_duration_ms` | 0 |
| `use_fan_intake` | true |
| `fan_on_ms` | 1000 |
| `post_fan_settle_ms` | 0 |

If `nullingProfileId == 0`, `START_DATASET` is rejected with
`reject_no_profile`.

Dataset state machine:

| State/step | Behavior |
|---|---|
| Idle | No capture. |
| Running / None | Wait for sample interval. |
| FanOn | Fan HIGH for `fan_on_ms` when `use_fan_intake=true`. |
| FanSettle | Fan LOW, then wait `post_fan_settle_ms`. |
| Scan | Read ADS channels and publish one record. |

Dataset JSON fields:

| Field | Meaning |
|---|---|
| `device_id` | `F001` |
| `node_id` | numeric `0xF001` |
| `mode` | `DATASET` |
| `seq` | dataset sequence |
| `timestamp_ms` | `millis()` |
| `label` | current dataset label |
| `nulling_profile_id` | loaded/saved profile ID |
| `sensor_voltage` | array of 8 sensor voltages |
| `sensor_gain` | array of 8 reading gain/status values |
| `feature_order` | hardware-order sensor names |

Autostop rules:

- Stop when `target_samples > 0` and `datasetSeq >= targetSamples`.
- Stop when `max_duration_ms > 0` and elapsed session duration reaches it.

## 14. WiFi And MQTT

Current WiFi/MQTT values are derived from `ServerConfig.h` dataset namespace:

| Field | Current committed value |
|---|---|
| WiFi SSID | `CHANGE_ME_WIFI_SSID` |
| WiFi password | `CHANGE_ME_WIFI_PASSWORD` |
| MQTT host | `CHANGE_ME_MQTT_HOST` |
| MQTT port | `1884` |
| MQTT user/pass | empty |
| Topic root | `gas-leak-detector` |
| MQTT client ID | `gld-unified-F001` |
| MQTT buffer | 1024 bytes |
| WiFi timeout | 15000 ms |
| MQTT retry | 3000 ms |
| status interval | 10000 ms |

Current unified runtime connects MQTT in dataset mode. Inference mode does not
maintain MQTT in the active main loop. Nulling mode is offline.

## 15. Persistent Data

Current persistent data:

| Data | Storage |
|---|---|
| GLD mode | Preferences namespace `gld`, key `mode` |
| Nulling profile | Preferences namespace `gld-null`, key `profile` |

Not current in active runtime:

- EEPROM `boardId`,
- EEPROM `modelFilePath`,
- EEPROM `wiperArr`,
- serial setup/config wait flow,
- LittleFS model path loading.

The ML model is compiled as C/C++ model data in `firmware/gld/model/model_data.cpp`.

## 16. Logs

Important current serial log tokens:

| Token | Meaning |
|---|---|
| `GLD_MODE=` | Loaded current mode. |
| `GLD_POWER` | Power mode and battery result. |
| `ADS_BEGIN_RESULT` | ADS init result. |
| `[BOOT_IC_REPORT]` | Boot table header. |
| `GLD_ML_INIT` | ML model init result. |
| `GLD_INFERENCE_READY` | Inference-mode readiness. |
| `DATASET_READY` | Dataset-mode readiness. |
| `NULLING_RUN` / `NULLING_RUN_DONE` | Nulling execution status. |
| `NULLING_RUNTIME_RESULT=PASS` | Complete nulling profile saved. |
| `NULLING_RUNTIME_RESULT=PARTIAL_RETRY` | Partial nulling result, retry scheduled. |
| `NULLING_RUNTIME_RESULT=FAIL_RETRY` | Failed nulling result, retry scheduled. |
| `GLD_SENSOR_SCAN` | Inference scan result. |
| `GLD_ML_RESULT` | Model prediction result. |
| `GLD_TX_HEADER` | Built uplink frame metadata. |
| `GLD_LORA_TX_RESULT=PASS/FAIL` | LoRa TX result. |
| `GLD_LORA_DOWNLINK_RX` | RX window received a downlink frame. |
| `GLD_LORA_DOWNLINK_CMD` | Valid downlink mode command parsed. |
| `DATASET_START` | Dataset session starts. |
| `DATASET_RECORD` | Dataset record publish attempt. |
| `DATASET_AUTOSTOP` | Dataset session auto-stopped. |
| `DATASET_STOP` | Dataset stop command handled. |

## 17. Current Safety And Caveats

| Area | Current behavior/caveat |
|---|---|
| Imported design | Keep `docs/design/gld/design.md` immutable; use this draft as adjusted copy. |
| RS485/Modbus | Baseline describes it, but active GLD envs do not compile it. |
| TPL5110 | DONE pin exists and is initialized LOW, but no complete sleep-cycle/pulse-DONE loop exists in unified runtime. |
| MQTT nulling result topics | Topic macros exist, but current unified runtime does not publish them. |
| Nulling partial success | Partial profile is retry-only; it must not be saved as complete production profile. |
| Dataset start | Requires `nullingProfileId > 0`; otherwise command is rejected. |
| LoRa downlink | Only authenticated mode command payload `0x81 + mode + commandId + cmacTag4` is accepted. |
| Old split GLD envs | Split inference/dataset/nulling mains are retained as source/support history but excluded from current runtime env. |

## 18. Verification Commands

Lightweight verification for this document:

```powershell
python firmware\tests\run_tests.py
pio project config -d firmware
```

No firmware build, upload, COM port action, Node-RED deploy, or database action
is required to validate this documentation draft.
