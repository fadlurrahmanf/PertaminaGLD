# GLD Project Ver2 Board Artifact

Imported: 2026-07-14
Source: `C:\Users\asus\Downloads\GLD_Project.zip`

The source ZIP contains EasyEDA export `GasLeakIntegratedVer2_dc4f1b9a29bc428f8b08da3ac8e47a03.zip`.
The extracted board files are kept here so the schematic and PCB can be searched,
diffed, and compared against firmware mapping.

## Files

| File | Purpose | SHA-256 |
|---|---|---|
| `source-GLD_Project.zip` | Original ZIP from Downloads | `A4A6701719C26434998FF3F834F060A5B1FF8916112C7870DD29AEABD1F1E042` |
| `1-Schematic_GasLeakIntegratedVer2.json` | EasyEDA schematic JSON, title `GasLeakIntegratedVer2`, editor `6.5.57` | `39E687022F247491CB0B3AD46EA69149AED813610B7B89BBF6FAFC89ECC8FE81` |
| `1-PCB_PCB_GasLeakIntegratedVer2.json` | EasyEDA PCB JSON | `FF7F4B0940BD5F23D8335E4FA2C35B776D5FEC72176E99EFE220A2CE7201CDD2` |
| `README.txt` | Original EasyEDA import note | `09A7EE7B449FB4C1C4217FADE8C4A5E9623643A8222FCD54FE33CB2CA09ED49F` |

## ADS To TCA/MCP Evidence

The schematic repeats eight analog sensor blocks. Each block contains one local
ADS net label (`AIN0`..`AIN7`) and one local MCP4725 branch connected through a
TCA9548A pair (`SDA0/SCL0`..`SDA7/SCL7`). Grouping those labels by the local
sensor block geometry gives this board mapping:

| ADS1256 input label | Local TCA/MCP mux branch in schematic |
|---:|---:|
| AIN0 | 7 |
| AIN1 | 6 |
| AIN2 | 5 |
| AIN3 | 0 |
| AIN4 | 1 |
| AIN5 | 2 |
| AIN6 | 3 |
| AIN7 | 4 |

This same mapping is also present in `docs/wiring/SCH_GasLeakIntegratedVer3_2026-06-25.json`.

## Compatibility Status

Firmware has been reconciled to this board artifact. The current mapping in
`firmware/gld/include/BoardPins.h` is:

```cpp
SENSOR_TO_MUX_CH = {7, 6, 5, 0, 1, 2, 3, 4};
SENSOR_TO_ADS_CH = {0, 1, 2, 3, 4, 5, 6, 7};
```

This firmware has been uploaded to the GLD board on COM9 and verified with
`RUN_BOOT_CHECK` plus `RUN_ADS_MCP_SWEEP` post-fix live voltage evidence.
