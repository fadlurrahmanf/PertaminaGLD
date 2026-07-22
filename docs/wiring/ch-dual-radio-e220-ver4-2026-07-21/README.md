# CH DualRadio E220 Ver4 Board Artifact

Imported: 2026-07-21
Source: `C:\Users\MSI\Downloads\BackupProjects_mamanbudiman_personal_0_20260721\dualRadioCH_E220Ver4_beb7c925d2fd480bbbdd45ea1f0a42d0.zip`

The original EasyEDA ZIP is preserved unchanged. Extracted schematic and PCB
JSON files are included so board nets can be searched, diffed, and compared
against the CH firmware pin mapping.

## Files

| File | Purpose | SHA-256 |
|---|---|---|
| `source-CH_DualRadio_E220Ver4.zip` | Original ZIP from Downloads | `28B9871F38762B90BF90AB0FAF1327D4931462262EF6F521642D2330DC581AA8` |
| `1-Schematic_dualRadioCH_E220Ver4.json` | EasyEDA schematic JSON, title `dualRadioCH_E220Ver4`, editor `6.5.57` | `E10772EBD7C73ECAF519232FC9B164818D5F1BFDAB8463AC102AF92C74409CCD` |
| `1-PCB_PCB_dualRadioCH_E220Ver4.json` | EasyEDA routed PCB JSON | `57BC37F848241BFBC242CB364774AB37F13C33508195FFFBC85A7698A6DD1F60` |
| `README.txt` | Original EasyEDA import note | `09A7EE7B449FB4C1C4217FADE8C4A5E9623643A8222FCD54FE33CB2CA09ED49F` |

## Firmware Comparison Status

The two E22 radio mappings, shared SPI bus, RF-control pins, resets, and
`BATMON` match the `ch`/`chFieldtest` board profile. The imported artifact also
shows `TPL5010 WAKE -> GPIO21` and `TPL5010 DONE -> GPIO47`; those two signals
must be used when reconciling the CH watchdog firmware mapping.

