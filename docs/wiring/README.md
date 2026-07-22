# Wiring Artifacts

This folder stores source wiring and schematic artifacts used to align firmware
pin configuration with the actual bench hardware.

## Current Schematic

| File | Source | Format | Notes |
|---|---|---|---|
| `SCH_GasLeakIntegratedVer3_2026-06-25.json` | `C:\Users\asus\Downloads\SCH_GasLeakIntegratedVer3_2026-06-25.json` | EasyEDA schematic JSON, editor `6.5.54` | Title `GasLeakIntegratedVer3`; contains `Sheet_1` and `Sheet_2`. |
| `gld-project-ver2-2026-07-01/` | `C:\Users\asus\Downloads\GLD_Project.zip` | EasyEDA schematic + PCB JSON, original ZIP preserved | Title `GasLeakIntegratedVer2`; contains schematic, PCB, and import note. |
| `ch-dual-radio-e220-ver4-2026-07-21/` | `C:\Users\MSI\Downloads\BackupProjects_mamanbudiman_personal_0_20260721\dualRadioCH_E220Ver4_beb7c925d2fd480bbbdd45ea1f0a42d0.zip` | EasyEDA schematic + PCB JSON, original ZIP preserved | Title `dualRadioCH_E220Ver4`; source reference for the dual E22 CH board. |

## ADS To TCA/MCP Board Mapping

Both the existing Ver3 schematic and the newly imported Ver2 board ZIP show the
same local analog-block mapping:

| ADS1256 input label | TCA/MCP mux branch shown by schematic |
|---:|---:|
| AIN0 | 7 |
| AIN1 | 6 |
| AIN2 | 5 |
| AIN3 | 0 |
| AIN4 | 1 |
| AIN5 | 2 |
| AIN6 | 3 |
| AIN7 | 4 |

This is now the firmware mapping in `firmware/gld/include/BoardPins.h`:
`SENSOR_TO_MUX_CH = {7, 6, 5, 0, 1, 2, 3, 4}` with identity ADS mapping.

## Current GLD Bench Wiring

The ESP32-S3-WROOM-1U-N16R8 GLD bench board is represented in firmware by:

```text
gldw
```

LoRa STAR wiring currently applied to that env:

| Signal | ESP32-S3 GPIO |
|---|---:|
| SCK | GPIO12 |
| MOSI | GPIO11 |
| MISO | GPIO13 |
| CS | GPIO7 |
| RST | GPIO2 |
| BUSY | GPIO15 |
| DIO1 | GPIO1 |
| RXEN | GPIO5 |
| TXEN | GPIO6 |

Because this wiring uses GPIO1 and GPIO2 for LoRa, the WROOM env disables the
old alarm lamp and buzzer firmware outputs that previously used those pins.

## Firmware Reference

- `firmware/platformio.ini`
- `firmware/gld/include/BoardPins.h`
- `docs/design/gld/final_design.md`
