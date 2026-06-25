# Pertamina GLD Final Design - GLD Node

Status: current-state final design, 2026-06-25. This file is the canonical GLD design for the firmware that exists in this repository now. The imported baseline `design.md` stays unchanged for audit/history.

## Source Of Truth

- Main runtime env: `gld_unified_esp32s3`.
- Optional bench env: `gld_unified_to_ch2_1_esp32s3`, overriding `GLD_CH_ID=0x0066`.
- Optional ESP32-S3-WROOM-1U-N16R8 env: `gld_unified_wroom_u1_n16r8_esp32s3`, using generic ESP32-S3 DevKitC board settings with 16MB flash and 8MB OPI PSRAM overrides.
- Current firmware version: GLD `0.8.2`, protocol `0.1.0`.
- Main source path: `firmware/gld/src/GldUnifiedMain.cpp`.
- Config source: `firmware/config/GldConfig.h`, `LoraStarConfig.h`, `ServerConfig.h`.
- Shared wire source: `firmware/shared/include/ProtocolConstants.h`, `AppFrame.h`, `GldPayload.h`, `GldRecord.h`.
- Model artifact source: `firmware/gld/model/NeuralNetwork.cpp`, `model_data.cpp`, `scaler_params.cpp`, `scaler_params.h`.

## Hardware And Pins

GLD runs on ESP32-S3 with one SX1262 STAR LoRa radio, ADS1256 sensor ADC, TCA9548A mux, MCP4725 DACs, alarm outputs, fan, power sense, and battery sense.

| Function | Pin/value |
|---|---|
| SPI SCK/MOSI/MISO | GPIO12/GPIO11/GPIO13 |
| ADS1256 CS/DRDY/SYNC | GPIO47/GPIO10/GPIO18 |
| LoRa CS/RST/BUSY/DIO1 | GPIO15/GPIO39/GPIO7/GPIO40 |
| LoRa RXEN/TXEN | GPIO5/GPIO6 |
| I2C SDA/SCL | GPIO8/GPIO9 |
| Status LED / alarm lamp / buzzer / fan | GPIO41/GPIO1/GPIO2/GPIO42 |
| TPL5110 DONE / battery ADC / 24V power-good / user button | GPIO14/GPIO4/GPIO45/GPIO16 |
| Sensor order | MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2 |
| TCA9548A / MCP4725 | `0x71` / `0x60` |
| DAC range | 0..4095 |
| sensor-to-mux map | `{7, 6, 5, 4, 3, 2, 0, 1}` |

The `gld_unified_wroom_u1_n16r8_esp32s3` env overrides the LoRa pins for the current ESP32-S3-WROOM-1U-N16R8 bench board:

| Function | WROOM env pin/value |
|---|---:|
| SPI SCK/MOSI/MISO | GPIO12/GPIO11/GPIO13 |
| LoRa CS/RST/BUSY/DIO1 | GPIO7/GPIO2/GPIO15/GPIO1 |
| LoRa RXEN/TXEN | GPIO5/GPIO6 |
| Alarm lamp / buzzer | disabled in firmware for this env because GPIO1/GPIO2 are used by LoRa |

## Runtime Modes

Mode is stored in NVS namespace `gld`, key `mode`. Invalid/missing mode falls back to `inference`. A mode switch writes NVS and restarts the ESP32.

| Mode | ID | Purpose |
|---|---:|---|
| `inference` | 0 | Normal production scan, ML inference, alarm output, LoRa STAR uplink, Class-A RX window. |
| `dataset` | 1 | MQTT-controlled labeled sample capture with nulling profile, sensor voltage/gain arrays, summary, and autostop. |
| `nulling` | 2 | Blocking calibration run, save nulling profile to NVS, publish retained nulling result/status over MQTT when WiFi is available. |

Mode commands:

- Serial: `SET_MODE inference`, `SET_MODE dataset`, `SET_MODE nulling`.
- Serial debug toggle: `DEBUG_OFF` disables normal GLD debug logs; `DEBUG_ON` re-enables them. The commands are read from both USB CDC `Serial` and UART0/CH340 `Serial0`, and the acknowledgement for these two commands always remains visible.
- MQTT direct GLD command topic: JSON `{"cmd":"SET_MODE","mode":"dataset"}`.
- LoRa downlink: `MSG_NODE_DOWNLINK` addressed to GLD, payload `cmdType=0x01`, `mode=0|1|2`.

## Boot Functional Report

Every boot prints a grouped hardware health report before entering the selected runtime mode. The report is intended for bench bring-up and field diagnosis:

- `[BOOT]`: firmware version, selected mode, and board profile.
- `[POWER]`: detected power source, external power flag, and battery reading.
- `[SPI]` / `[ADS]`: SPI pins, ADS1256 init result, DRDY level, and ADS status register when available.
- `[I2C]` / `[TCA]`: I2C pins and TCA9548A ACK at address `0x71`.
- `[MCP]`: per-sensor MCP4725 ACK at address `0x60` through the configured TCA mux channel.
- `[LORA]`: SX1262 readiness plus active NSS/DIO1/RST/BUSY pins.
- `[ML]`: neural-network wrapper readiness and output count.
- `[DAC]`: dataset/nulling-mode DAC mux runtime init result.

The TCA/MCP boot check is lightweight: firmware selects each mux channel, checks MCP4725 ACK, then disables all TCA channels. It does not run the full nulling calibration during normal inference boot.

## Inference Mode

Inference mode initializes ADS1256, moving average buffers, TFLite Micro wrapper, and STAR radio. It scans every `GLD_SCAN_INTERVAL_MS=1000` ms and transmits every `GLD_TX_INTERVAL_MS=10000` ms.

The ML pipeline reads eight sensor channels, waits until every moving average has at least 10 samples, remaps hardware channel order to model input order with `HW_TO_MODEL = {0,2,5,3,4,6,1,7}`, normalizes by `feature_means` and `feature_stds`, and calls `NeuralNetwork::predict()`. The current model is a placeholder/drop-in TFLite Micro artifact, not the final field-trained gas model.

Model output mapping:

| Model class | GLD gas class |
|---:|---|
| 0 | clearGas |
| 1 | LPG |
| 2 | methane |
| 3 | propane |
| 4 | butane |
| other | anomaly |

Alarm rule: `gasClass != clearGas` and `confidence >= GLD_LEL_THRESHOLD_PERCENT`. Current threshold is 30. Alarm drives alarm lamp, buzzer, and status LED.

## LoRa STAR Uplink

STAR radio settings are shared by GLD and CH radio A:

| Parameter | Value |
|---|---:|
| Frequency | 920.0 MHz |
| Bandwidth | 125 kHz |
| Spreading factor | SF7 |
| Coding rate | 4/5 |
| Sync word | `0x12` |
| TX power | 17 dBm |
| Preamble | 8 |
| SPI | 2 MHz |
| TCXO/fallback | 1.6 V / 0.0 V |

GLD builds an AppFrame with `MSG_SENSOR_DATA` and sends it to `GLD_CH_ID`. After every TX it opens a 2000 ms RX window for `MSG_NODE_DOWNLINK` commands.

Plain GLD payload is exactly 4 bytes:

| Byte(s) | Field |
|---|---|
| 0 | `gasClass` |
| 1 | `confidence` |
| 2..3 | `batteryMv`, big-endian, `0xFFFF` means invalid/unavailable |

The 4-byte payload is encrypted into a 29-byte AES-GCM payload: `keyId(1) + nonce(12) + ciphertext(4) + tag(12)`. Alarm and external-power state are not extra payload fields; they are represented by AppFrame/record flags.

## Dataset Mode

Dataset mode is MQTT-controlled and requires a valid nulling profile. It subscribes to:

- `gas-leak-detector/F001/cmd`
- `gas-leak-detector/F001/dataset`

`START_DATASET` parameters:

| Field | Meaning |
|---|---|
| `label` | sample label, for example clear air or gas type |
| `target_samples` | bounded capture count; 0 means no count limit |
| `sample_interval_ms` | sample interval |
| `max_duration_ms` | bounded capture duration; 0 means no duration limit |
| `use_fan_intake` | use fan before sample |
| `fan_on_ms` | fan run duration |
| `post_fan_settle_ms` | settle delay after fan |

Dataset records publish JSON to `gas-leak-detector/F001/dataset/data` with `device_id`, `node_id`, `mode`, `seq`, `timestamp_ms`, `label`, `nulling_profile_id`, `sensor_voltage[8]`, `sensor_gain[8]`, and `feature_order[8]`. Summary publishes to `dataset/summary`, status to `dataset/status`, command ACK to `cmd/ack`.

## Nulling Mode

Nulling mode initializes ADS1256 and DAC mux, runs `GldNullingService`, saves a profile to NVS if at least partial success is achieved, increments `profileId`, and publishes retained result/status when WiFi/MQTT is available. Dataset mode loads this profile and rejects `START_DATASET` when none exists.

## Server Config

Committed dataset config still uses placeholder values in `ServerConfig.h` unless the operator sets bench values before upload. Gateway/site config is separate from GLD dataset config. Do not commit production secrets permanently.

## Post-12 Work

Post-12 is outside the completed 12/12 milestone but is required for field-grade deployment:

- Collect real labeled gas dataset for clear air, LPG, methane, propane, butane, and anomaly cases.
- Train and package a real model, then replace `model_data.cpp`, `scaler_params.cpp`, and `scaler_params.h`.
- Validate feature order against the actual sensor order before removing or changing `HW_TO_MODEL`.
- Add production provisioning for WiFi/MQTT/AES keys instead of committed bench constants.
- Finish low-power/TPL5110 DONE behavior and Modbus RTU slave if still required by field scope.
