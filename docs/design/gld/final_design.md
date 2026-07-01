# Pertamina GLD Current Design - GLD Node

Status: current source mirror, 2026-06-29. Dokumen ini mengikuti firmware GLD unified yang sedang ada di repo. Imported baseline `design.md` tidak diubah.

## Source Files

| Area | Source |
|---|---|
| PlatformIO env | `firmware/platformio.ini` |
| Main runtime | `firmware/gld/src/GldUnifiedMain.cpp` |
| Board pins | `firmware/gld/include/BoardPins.h` |
| GLD config | `firmware/config/GldConfig.h` |
| Server config | `firmware/config/ServerConfig.h` |
| STAR radio config | `firmware/config/LoraStarConfig.h` |
| Mode manager | `firmware/gld/include/GldModeManager.h`, `firmware/gld/src/GldModeManager.cpp` |
| Command parser | `firmware/gld/include/GldCommandParser.h`, `firmware/gld/src/GldCommandParser.cpp` |
| ADS/DAC/power | `GldAds1256Reader`, `GldDacMux`, `GldPower` |
| Nulling | `GldNullingProfile.h`, `GldNullingService.h`, `GldNullingService.cpp` |
| Uplink crypto/frame | `GldFrameBuilder`, `GldPayload`, `GldCrypto`, `AppFrame`, `ProtocolConstants` |
| ML wrapper/model | `firmware/gld/model/NeuralNetwork.cpp`, `model_data.cpp`, `scaler_params.cpp` |

## Active Build Environments

`firmware/platformio.ini` contains one active GLD runtime env:

| Env | Board | Purpose |
|---|---|---|
| `gld` | `esp32-s3-devkitc-1` | GLD unified runtime for the GLDW / ESP32-S3-WROOM-1U-N16R8 board profile, with 16 MB flash, 8 MB OPI PSRAM, and `PGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8=1` |

The GLD env compiles only these runtime sources: shared `AppFrame`, `GldCrypto`, `GldPayload`, `GldRecord`; GLD `GldAds1256Reader`, `GldCommandParser`, `GldDacMux`, `GldFrameBuilder`, `GldModeManager`, `GldMovingAverage`, `GldNullingService`, `GldPower`, `GldThresholdClassifier`, `GldUnifiedMain`; model `NeuralNetwork`, `scaler_params`, `model_data`.

Excluded from this runtime env: legacy `gld/src/main.cpp`, all GLD self-test mains, old split inference/dataset/nulling mains, CH source, docs, tests, and versions.

Firmware identifiers:

| Field | Value |
|---|---|
| firmware name | `PertaminaGLD-GLD` |
| firmware version | `0.8.12` |
| protocol version | `0.1.0` |
| config schema version | `0.1.0` |

## Identity And Config

| Config | Current value |
|---|---|
| GLD node hex | `F001` |
| `GLD_NODE_ID` | `0xF001` |
| `GLD_DEVICE_ID_STR` | `F001` |
| MQTT client ID | `gld-unified-F001` |
| STAR target CH | `0x0064` |
| scan interval | `1000 ms` |
| TX interval | `10000 ms` |
| WiFi timeout | `15000 ms` |
| MQTT retry | `3000 ms` |
| MQTT status interval | `10000 ms` |
| LoRa RX window after TX | `2000 ms` |
| MQTT buffer | `1024 bytes` |

Dataset MQTT config comes from `ServerConfig.h` dataset namespace. Current committed values are `CHANGE_ME` for dataset WiFi SSID/password/host, port `1884`, empty MQTT user/pass, topic root `gas-leak-detector`.

## Hardware Pins

Default GLD board profile `4D-ESP32S3`:

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
| Firmware DONE symbol | `PIN_TPL5110_DONE=GPIO14`, set OUTPUT LOW during power init |
| Battery ADC | GPIO4 |
| 24V power-good input | GPIO45 |
| User button symbol | GPIO16 |
| TCA9548A address | `0x71` |
| MCP4725 address | `0x60` |
| DAC range | 0..4095 |

WROOM profile overrides:

| Function | Pin/value |
|---|---|
| LoRa CS/RST/BUSY/DIO1 | GPIO7/GPIO2/GPIO15/GPIO1 |
| LoRa RXEN/TXEN | GPIO5/GPIO6 |
| Alarm lamp | disabled, `-1` |
| Buzzer | disabled, `-1` |
| Board profile log | `WROOM-1U-N16R8` |

Sensor order and mux:

| Hardware channel | Sensor | TCA mux channel | Model input index |
|---:|---|---:|---:|
| 0 | MQ8 | 7 | 0 |
| 1 | MQ135 | 6 | 2 |
| 2 | MQ3 | 5 | 5 |
| 3 | MQ5 | 4 | 3 |
| 4 | MQ4 | 3 | 4 |
| 5 | MQ7 | 2 | 6 |
| 6 | MQ6 | 0 | 1 |
| 7 | MQ2 | 1 | 7 |

## Power Detection

`GldPower` reads 16 ADC samples from GPIO4. ADC conversion uses 12-bit count, 3.3 V ADC reference constant, divider ratio `3.0`, and returns invalid battery `0xFFFF` if calculated battery voltage is `<=0.05 V` or `>20.0 V`.

Power mode:

| Condition | Mode | `externalPower` |
|---|---|---:|
| GPIO45 HIGH | `24v` | 1 |
| battery ADC valid and GPIO45 LOW | `battery` | 0 |
| battery ADC invalid and GPIO45 LOW | `5v` | 1 |

## Runtime Modes

Mode is stored in NVS namespace `gld`, key `mode`. Invalid or missing value falls back to `inference`.

| Mode string | ID | Runtime behavior |
|---|---:|---|
| `inference` | 0 | ADS, moving average, ML, local alarm outputs, LoRa STAR uplink, LoRa RX window, WiFi/MQTT explicitly off |
| `running` | alias | Parsed as `inference` |
| `dataset` | 1 | ADS + DAC + nulling profile + WiFi/MQTT dataset capture |
| `nulling` | 2 | ADS + DAC + offline nulling calibration, WiFi/MQTT explicitly off |

Mode commands:

| Channel | Accepted command |
|---|---|
| USB CDC `Serial` and UART0 `Serial0` | `SET_MODE inference`, `SET_MODE running`, `SET_MODE dataset`, `SET_MODE nulling` |
| USB CDC `Serial` and UART0 `Serial0` | `DEBUG_ON`, `DEBUG_OFF` |
| Dataset MQTT `gas-leak-detector/F001/cmd` | JSON `{"cmd":"SET_MODE","mode":"..."}` |
| Dataset MQTT `gas-leak-detector/F001/dataset` | JSON `{"cmd":"SET_MODE","mode":"..."}` |
| LoRa downlink | `MSG_NODE_DOWNLINK`, payload byte 0 `0x01`, payload byte 1 mode `0|1|2` |

`DEBUG_OFF` disables normal `logPrintf/logPrintln` output, but the debug toggle acknowledgement uses raw serial and remains visible.

Network policy: firmware only calls `WiFi.begin()` and MQTT connect in `dataset`
mode. `inference`/`running` and `nulling` call the offline-mode guard, which
disconnects MQTT/socket state and sets `WiFi.mode(WIFI_OFF)`.

## Boot Flow And Report

Boot serial setup: `Serial.begin(115200)`, `Serial0.begin(115200)` on ESP32, delay 1000 ms.

Boot steps:

1. `setupPins()`.
2. `beginGldPowerPins()`.
3. Reset moving average.
4. Load mode from NVS.
5. Print firmware header, version, protocol, build date/time, mode, debug hint, and board profile.
6. Read power mode.
7. `ads.begin(gldSpi)`.
8. Probe ADS status/DRDY.
9. Probe I2C/TCA/MCP ACK.
10. If external power, run MCP write-control test with DAC code `1` then `10`.
11. Initialize mode-specific runtime.
12. Print `[BOOT_IC_REPORT]`.
13. If external power, print `[BOOT_SENSOR_SAMPLES]`.

Boot IC table columns:

| Column | Meaning |
|---|---|
| `IC/Fungsi` | Hardware/function name |
| `Check` | Check type |
| `Status` | `OK`, `NOT_OK`, `OK_TESTED`, or `SKIP` |
| `Detail` | Pin/address/result detail |

Boot rows:

| Row | Check | Detail |
|---|---|---|
| `POWER` | `sense` | `mode=<battery|5v|24v> external=<0|1> batteryMv=<value>` |
| `SPI_BUS` | `pins` | SCK/MOSI/MISO |
| `ADS1256` | `SPI begin` | CS/DRDY/SYNC, DRDY level, status register |
| `I2C_BUS` | `pins` | SDA/SCL |
| `TCA9548A` | `I2C ACK` | `addr=0x71` |
| `MCP4725-<sensor>` | `I2C ACK` or `I2C+DAC write` | mux, address, `ack only` or `write=1,10` |
| `SX1262` | `LoRa begin` | LoRa pins and RadioLib begin state |
| `ML_MODEL` | `init/classes` | `classes=<N> model outputs` |
| `MODE_READY` | current mode name | mode readiness summary |

Mode-specific rows:

| Mode | SX1262 | ML_MODEL | MODE_READY condition |
|---|---|---|---|
| inference | checked | checked | ADS ready, LoRa ready, ML ready |
| dataset | `SKIP` | `SKIP` | ADS ready, DAC ready, `nullingProfileId > 0` |
| nulling | `SKIP` | `SKIP` | true only after complete nulling save succeeds |

External-power boot sensor samples:

- Header: `[BOOT_SENSOR_SAMPLES]`.
- If a saved nulling profile exists, firmware writes all saved DAC codes first.
- If no saved profile exists and DAC is ready, firmware writes all DACs to code `0`.
- It prints 5 rows.
- Each row reads all 8 ADS channels as fast as the ADS reader allows and formats `MQx : x.xxxxxV | ...`.
- If a channel read fails, that channel prints `ERR(<status>)`.
- Battery mode skips this block.

## ADS, DAC, And Nulling Profile

Nulling profile:

| Field | Type | Meaning |
|---|---|---|
| `validMagic` | `uint8_t` | valid when `0xA5` |
| `profileId` | `uint8_t` | increments on each complete saved profile |
| `dacCode[8]` | `uint16_t` | selected DAC code per sensor |
| `baselineV[8]` | `float` | baseline voltage from nulling |
| `afterV[8]` | `float` | final voltage after applying selected code |
| `channelOk[8]` | `uint8_t` | 1 if channel succeeded |

Profile persistence uses Preferences namespace `gld-null`, key `profile`.

Nulling service constants:

| Constant | Value |
|---|---:|
| average count | 8 |
| confirm count | 10 |
| baseline prescan max DAC code | 10 |
| exponential initial step | 1 |
| exponential max step | 2048 |
| confirm window | 10 DAC codes |
| settle delay | 5 ms |
| threshold | `0.0001 V` |
| minimum final voltage | `0.0 V` |

Nulling channel flow:

1. Write DAC code 0.
2. Baseline prescan from code 0 through 10, averaging 8 readings per code.
3. Exponential range search starts at code 1 and doubles step up to 2048 until absolute delta from baseline is at least `0.0001 V`.
4. Binary search narrows low/high threshold boundary.
5. Confirm scans 10 DAC codes around selected code, averaging 10 readings per candidate.
6. Candidate is accepted only if DAC write OK, ADS reading valid, voltage `>=0.0`, and delta `>=0.0001 V`.
7. Final DAC write is applied.
8. Final after-read averages 8 readings and must be valid and `>=0.000000000`.

Nulling serial logs include:

| Log prefix | Meaning |
|---|---|
| `NULLING_SERVICE_START` | channels, avgCount, confirmCount, settleMs |
| `NULLING_CH_START` | channel start |
| `NULLING_BASELINE_*` | baseline prescan progress |
| `NULLING_EXP_*` | exponential search progress |
| `NULLING_BIN_*` | binary search progress |
| `NULLING_CONFIRM_*` | confirm window progress |
| `NULLING_CH_OK` | per-channel success |
| `NULLING_CH_FAIL` | per-channel fail with stage and reason |
| `NULLING_SERVICE_DONE` | service status and success count |

Error reasons:

| Code | Reason |
|---:|---|
| 1 | `dac_zero_write_failed` |
| 2 | `baseline_no_valid_samples` |
| 3 | `exponential_range_not_found` |
| 4 | `confirm_failed` |
| 5 | `dac_final_write_failed` |
| 6 | `after_read_invalid` |
| 7 | `after_voltage_negative` |

Nulling mode behavior:

- If ADS or DAC is not ready, print boot report and schedule retry after `5000 ms`.
- If all 8 channels succeed and profile save succeeds, print `NULLING_RUNTIME_RESULT=PASS`, print boot report, run external-power sensor samples, write mode `INFERENCE`, delay `800 ms`, flush serial, restart ESP32.
- If any channel fails, or NVS save fails, print `PARTIAL_RETRY` or `FAIL_RETRY`, schedule retry after `5000 ms`, and keep checking serial commands between attempts.
- Nulling mode does not call WiFi connect, MQTT connect, MQTT subscribe, or MQTT publish.

## Inference Mode

Inference initializes:

- ADS1256 reader.
- Moving average.
- `NeuralNetwork`.
- SX1262 STAR radio.

Inference scan:

1. Every `1000 ms`, read 8 sensor channels.
2. Feed moving average.
3. ML runs only after all 8 channels have at least 10 moving-average samples.
4. Hardware channel values are remapped through `HW_TO_MODEL`.
5. Model input uses `(voltage - feature_means[index]) / feature_stds[index]`.
6. `NeuralNetwork::predict()` returns predicted model class and confidence float.
7. Confidence is stored as `uint8_t(confidenceFloat * 100.0f)`.

Model class to protocol gas class:

| Model class | Protocol gas class value | Protocol name |
|---:|---:|---|
| 0 | 0 | clearGas |
| 1 | 1 | LPG |
| 2 | 2 | methane |
| 3 | 3 | propane |
| 4 | 4 | butane |
| other | 6 | anomaly |

Alarm rule:

```text
alarm = gasClass != clearGas && confidence >= 30
```

Local outputs are updated only when alarm state changes. Alarm lamp, buzzer, and status LED are active-low: alarm ON writes LOW when those pins are enabled, and alarm OFF writes HIGH.

## LoRa STAR Uplink

STAR radio settings:

| Parameter | Value |
|---|---:|
| Frequency | 920.0 MHz |
| Bandwidth | 125 kHz |
| Spreading factor | SF7 |
| Coding rate | 4/5 |
| Sync word | `0x12` |
| TX power | 17 dBm |
| Preamble | 8 |
| SPI clock | 2 MHz |
| TCXO first attempt | 1.6 V |
| XTAL fallback | 0.0 V |

`beginLoraRadio()` tries TCXO 1.6 V first. If RadioLib returns `RADIOLIB_ERR_SPI_CMD_FAILED`, it retries with 0.0 V.

Uplink every `10000 ms` when radio is ready:

1. Read power.
2. Battery field is real battery mV only if valid; otherwise `0xFFFF`.
3. Build GLD frame with node `0xF001`, destination CH `0x0064`, AES key ID 1.
4. Nonce starts from self-test nonce bytes, overwrites bytes 4..7 with `esp_random()`, bytes 8..11 with `txCounter`, then increments counter.
5. Transmit with RadioLib.
6. Increment TX sequence.
7. Open LoRa RX window for `2000 ms`.

Plain GLD payload:

| Offset | Field | Size |
|---:|---|---:|
| 0 | `gasClass` | 1 |
| 1 | `confidence` | 1 |
| 2..3 | `batteryMv` big-endian | 2 |

Encrypted GLD payload:

| Offset | Field | Size |
|---:|---|---:|
| 0 | `keyId` | 1 |
| 1..12 | AES-GCM nonce | 12 |
| 13..16 | ciphertext | 4 |
| 17..28 | tag | 12 |

AAD is `nodeId:uint16BE + seq:uint8 + recordFlags:uint8 + keyId:uint8`.

## Dataset Mode

Dataset mode initializes ADS and DAC. It loads the saved nulling profile without
running nulling automatically:

- If a profile exists, load it and write saved DAC codes.
- If no profile exists, keep `nullingProfileId=0`, log `auto_nulling=skip`, and
  let `START_DATASET` reject with `reject_no_profile`.
- Operators must explicitly run `SET_MODE nulling` first when a fresh nulling
  profile is required.

Dataset mode then connects WiFi/MQTT, subscribes `TOPIC_CMD`, subscribes `TOPIC_DATASET`, and enters state machine.

Topics for GLD `F001`:

| Topic | Direction |
|---|---|
| `gas-leak-detector/F001/cmd` | command in |
| `gas-leak-detector/F001/dataset` | dataset command in |
| `gas-leak-detector/F001/dataset/data` | data out |
| `gas-leak-detector/F001/dataset/status` | status out |
| `gas-leak-detector/F001/dataset/summary` | summary out |
| `gas-leak-detector/F001/cmd/ack` | ack out |

`GldConfig.h` also defines `nulling/result` and `nulling/status` topic macros, but current `GldUnifiedMain.cpp` does not publish to them.

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

If `nullingProfileId == 0`, `START_DATASET` is rejected with `reject_no_profile`.

Dataset state machine:

| State/step | Behavior |
|---|---|
| Idle | no capture |
| Running/None | wait for sample interval |
| FanOn | fan HIGH for `fan_on_ms` when `use_fan_intake=true` |
| FanSettle | fan LOW and wait `post_fan_settle_ms` |
| Scan | read ADS and publish one record |

Dataset data JSON fields:

| Field | Meaning |
|---|---|
| `device_id` | `F001` |
| `node_id` | `0xF001` numeric |
| `mode` | `DATASET` |
| `seq` | dataset sequence |
| `timestamp_ms` | `millis()` |
| `label` | current label |
| `nulling_profile_id` | loaded/saved profile ID |
| `sensor_voltage` | array of 8 voltages |
| `sensor_gain` | array of 8 gain/status values from readings |
| `feature_order` | sensor names in hardware order |

Autostop:

- If `target_samples > 0` and `datasetSeq >= targetSamples`, stop and publish summary/status.
- If `max_duration_ms > 0` and elapsed session duration reaches it, stop and publish summary/status.

`STOP_DATASET` turns fan and status LED off, publishes ack, summary, and `idle/stopped`.
While GLD remains in `dataset` mode it keeps WiFi/MQTT alive so the app can send
another dataset command. Switching back to `inference` reboots and disables
WiFi/MQTT through the offline-mode guard.
