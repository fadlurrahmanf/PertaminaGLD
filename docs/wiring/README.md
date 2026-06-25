# Wiring Artifacts

This folder stores source wiring and schematic artifacts used to align firmware
pin configuration with the actual bench hardware.

## Current Schematic

| File | Source | Format | Notes |
|---|---|---|---|
| `SCH_GasLeakIntegratedVer3_2026-06-25.json` | `C:\Users\asus\Downloads\SCH_GasLeakIntegratedVer3_2026-06-25.json` | EasyEDA schematic JSON, editor `6.5.54` | Title `GasLeakIntegratedVer3`; contains `Sheet_1` and `Sheet_2`. |

## Current GLD Bench Wiring

The ESP32-S3-WROOM-1U-N16R8 GLD bench board is represented in firmware by:

```text
gld_unified_wroom_u1_n16r8_esp32s3
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
