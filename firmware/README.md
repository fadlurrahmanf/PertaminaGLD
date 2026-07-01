# Pertamina GLD Firmware

Status: current source map, 2026-06-29.

This README describes the firmware files that are active in this repository now.
Older board bring-up notes and upload captures are kept in
`firmware/versions/version.md`.

## Current Versions

| Component | Version |
|---|---:|
| GLD | `0.8.12` |
| CH | `0.7.1` |
| Gateway | `0.1.3` |
| Protocol | `0.1.0` |
| Config schema | `0.1.0` |

The source of truth for these values is
`firmware/shared/include/FirmwareVersion.h`.

## Active Deploy Workspace

Use the root firmware workspace for current deploy/runtime builds:

```powershell
pio project config -d firmware
```

Active envs in `firmware/platformio.ini`:

| Env | Role |
|---|---|
| `gld` | GLD unified runtime for the GLDW / ESP32-S3-WROOM-1U-N16R8 board profile |
| `ch1` | CH runtime default, `PGL_CH_ID=0x0064` |
| `ch2` | CH runtime, `PGL_CH_ID=0x0065`, battery thresholds disabled for bench |
| `ch3` | CH runtime, `PGL_CH_ID=0x0066` |
| `gw` | Gateway MESH radio + WiFi/MQTT bridge |

Main GLD upload example:

```powershell
pio run -d firmware -e gld -t upload --upload-port COM10
```

Main CH upload example:

```powershell
pio run -d firmware -e ch1 -t upload --upload-port COM3
```

Gateway upload example:

```powershell
pio run -d firmware -e gw -t upload --upload-port COM38
```

COM ports are examples from prior bench sessions. Re-check with
`pio device list` before upload.

## Bench And Legacy Workspaces

Bench-only self-test envs live in `firmware/bench/platformio.ini`.
They are not deploy/runtime envs.

```powershell
pio run -d firmware/bench -e gld_sensor_selftest_esp32s3
pio run -d firmware/bench -e gld_nulling_selftest_esp32s3
pio run -d firmware/bench -e gld_lora_tx_selftest_esp32s3
pio run -d firmware/bench -e ch_star_rx_selftest_esp32s3
```

Legacy per-mode GLD envs live in `firmware/support/platformio.ini`.
They are support/debug envs retained outside the deploy workspace:

```powershell
pio run -d firmware/support -e gld_inference_esp32s3
pio run -d firmware/support -e gld_dataset_esp32s3
pio run -d firmware/support -e gld_nulling_runtime_esp32s3
```

Do not treat `firmware/support/platformio.ini` as the current production
contract. The current GLD contract is the unified runtime env in
`firmware/platformio.ini`.

## Test Command

Host-level protocol/source guard tests:

```powershell
python firmware/tests/run_tests.py
```

Current expected result:

```text
27/27 tests passed
```

These tests assert current protocol constants, firmware versions, active envs,
GLD board pin macros, current GLD unified scaffolds, Node-RED pull hopList
contract, and selected source guardrails.

## Current Design Mirrors

Current design references are under `docs/design`:

| Area | Current document |
|---|---|
| GLD | `docs/design/gld/final_design.md` |
| CH | `docs/design/ch/final_design.md` |
| GLD-CH payload | `docs/design/gld-ch/payload-contract.draft.md` |
| CH-CH | `docs/design/ch-ch/final_design.md` |
| CH-Gateway | `docs/design/ch-gw/final_design.md` |
| Gateway | `docs/design/gw/final_design.md` |
| Gateway-server | `docs/design/gw-server/final_design.md` |
| Server/Node-RED | `docs/design/server/final_design.md` |

`docs/design/gld/design.md` and `docs/design/ch/design.md` are imported
historical baselines. Do not use them as current firmware contracts.

## Source Priority

If a historical note conflicts with current source, use this order:

1. `firmware/platformio.ini`
2. `firmware/shared/include/*.h`
3. `firmware/config/*.h`
4. `firmware/gld/include/*.h` and `firmware/gld/src/*.cpp`
5. `firmware/ch/include/*.h` and `firmware/ch/src/*.cpp`
6. `firmware/gateway/include/*.h` and `firmware/gateway/src/*.cpp`
7. `server/nodered/*`
8. `docs/design/*/final_design.md`
