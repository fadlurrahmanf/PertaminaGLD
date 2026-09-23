# GLD2 power allocation - calculation basis

The nine-page diagram is an engineering reference allocation, not a measured load, a complete maximum-load calculation, or a PSU/PCB approval. The schematic buck set point is 4.98848 V. Solving load current and typical switch drops together gives a main rail of 4.92973 V and module rails of 4.914-4.916 V. These are estimates, not precision measurements. Series-switch current is conserved and its loss is included once. No schematic or firmware was changed. The external 5 V source and paths are omitted from the diagram as requested.

## Scenario

External 24 V supplies the board. All eight heaters use datasheet room-temperature resistance references evaluated at their calculated module voltages. Battery contribution is zero; its 4.2 V label identifies the reference source, while 0 A means no contribution in this case. It is not a leakage specification. ESP uses the 91.7 mA, 240 MHz RF-off benchmark; LoRa uses 119 mA TX. SHT measures with its heater off, RS485 receives, CH340 is active, status LED and alarm are off. USB power is excluded from attribution: all AON power is charged to 24 V even if attached USB would share it.

The diagram uses calculated local currents. Page9 separately expresses each load's watts as equivalent24V source current. Conversion losses form one separate branch, preventing double counting. Subtotals at different voltages are never added as amperes.

## Inputs and assumptions

- LMR51450: approximate92% from TI Figure7-1,24V-to5V near1.5A,500kHz. Schematic RT is open, matching500kHz default. TPS62162: approximate93% from TI Figure12,5V-to3.3V near0.22A. These curve readings are estimates for reference circuits, not guaranteed actual-board efficiencies. Converter bias is already included in curve efficiency; do not add it twice.
- Heater model: see power_budget.py and power-sources.json for eight resistance values, tolerances and reference vendors. MQ7 is budgeted at continuous5V for this supplied fixed-supply module; this does not implement the manufacturer's low/high heating cycle. Fitted makers and hot resistance are unverified.
- Module: INA333 50 uA + MCP4725 210 uA + XBLW LM321 100 uA, plus a local 10k/10k divider (about 245.7-245.8 uA). Datasheet no-load benchmarks are estimates at the calculated supply point, not fitted-board maxima. DAC benchmark: code 000h. TPS22919 uses 8 uA at 3.6 V as a small-current estimate and its 5 V typical on-resistance of 89 milliohms for conduction loss. One selected ADS input receives a 35 uA allocation, divided over modules for budgeting; it is not eight simultaneous ADC currents.
- VMID: eight 20k||20k module sensing paths plus the motherboard 49.9-ohm resistor. As sensor resistance approaches zero, current = (main rail / 2) / (49.9 + 10000 / 8), about 1.8962 mA. Delivered VMID is about 2.3702 V after the shared resistor, versus 2.4649 V unloaded. This is a passive-load bound, not an invented gas resistance.
- ADS: AVDD 7 mA and DVDD 0.9 mA at PGA 1 / buffer off are 7.68 MHz references applied to the schematic 8 MHz as estimates. VREF impedance of 18.5 kilohms is scaled inversely with clock, including the 22-ohm series resistor. Two OPA320 use 1.5 mA each (5.5 V benchmark applied at the calculated rail); ADR03 uses 650 uA. VMID divider adds main-rail voltage / 20k, about 246.5 uA.
- PCF8574 uses the NXP100uA table maximum at6V as a budgeting allowance at3.3V; fitted vendor unknown. TCA uses30uA table maximum at5.5V as allowance at5V. These are deliberate cross-condition approximations, not exact3.3V/5V guarantees.
- Digital pullup envelope: seven10k and three100k resistors at3.3V, all low as an allocation allowance. AON: three10k branches at3.3V plus static watchdog/inverter/latch/supervisor upper reference currents. These simultaneous-low envelopes are not normal logic-state claims. AON LDO ground current uses25nA light-load typical reference.
- TPS2116 uses40mohm typical conduction resistance and1.32uA bias. Board bias includes100k+19.1k feedback and16k+4.99k priority divider.24V gate/zener branch uses(24-12)/100k.
- Input fuse/filter/FET/wiring ohmic losses, unmodelled switching and I/O/memory activity, leakage, startup, thermal variation and alarm-on demand remain outside this reference subtotal. No unsupported numeric allowance is silently inserted. The remaining PSU capacity is provisional, not usable current through any particular PCB path.

## Reproduction and source ledger

Run `python output/diagrams/gld2/allocation_budget.py`. `allocation-calculations.json` stores unrounded values, local-rail totals, losses and the eight24V-equivalent allocations. `power-calculations.json` retains underlying independent datasheet reference cases. Sources below are supporting files, not extra PDF pages.

- [LMR51450](https://www.ti.com/lit/ds/symlink/lmr51450.pdf) - TI electrical characteristics: 0.8 V feedback
- [TPS61088](https://www.ti.com/lit/ds/symlink/tps61088.pdf) - TI electrical characteristics: PWM/PFM feedback
- [TPS61175](https://www.ti.com/lit/ds/symlink/tps61175.pdf) - TI electrical characteristics: 1.229 V feedback
- [TPS62162](https://www.ti.com/lit/ds/symlink/tps62162.pdf) - TI fixed 3.3 V option; converter rating
- [TPS2116](https://www.ti.com/lit/ds/symlink/tps2116.pdf) - TI power multiplexer; rating is not load current
- [TPS7A02](https://www.ti.com/lit/ds/symlink/tps7a02.pdf) - TI fixed 3.3 V option; ground current depends on load
- [ADS1256](https://www.ti.com/lit/ds/symlink/ads1256.pdf) - TI electrical characteristics, 7.68 MHz clock
- [OPA320](https://www.ti.com/lit/ds/symlink/opa320.pdf) - TI supply-current table, no output load
- [ADR03](https://www.analog.com/media/en/technical-documentation/data-sheets/ADR01_02_03_06.pdf) - Analog Devices Rev. S, Table 4
- [ESP32-S3-WROOM-1](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf) - Espressif v1.8, Tables 6-4 and 6-6
- [E22-900MM22S](https://www.cdebyte.com/products/E22-900MM22S/1) - Ebyte electrical-parameter table
- [SHT40](https://sensirion.com/resource/datasheet/sht4x) - Sensirion SHT4x current and heater tables
- [TCA9548A](https://www.ti.com/lit/ds/symlink/tca9548a.pdf) - TI electrical characteristics, 100/400 kHz
- [PCF8574](https://www.nxp.com/docs/en/data-sheet/PCF8574_PCF8574A.pdf) - NXP reference only; fitted vendor not established
- [THVD1410](https://www.ti.com/lit/ds/symlink/thvd1410.pdf) - TI quiescent current; excludes bus load
- [TPL5010](https://www.ti.com/lit/ds/symlink/tpl5010.pdf) - TI supply current and timing conversion
- [SN74AUP1G74](https://www.ti.com/lit/ds/symlink/sn74aup1g74.pdf) - TI static ICC at valid logic levels
- [SN74LVC1G06](https://www.ti.com/lit/ds/symlink/sn74lvc1g06.pdf) - TI static ICC; excludes pull-up load
- [TPS3839](https://www.ti.com/lit/ds/symlink/tps3839.pdf) - TI supply current, output unloaded
- [MQ8](https://www.winsen-sensor.com/product/mq-8.html) - Winsen MQ-8 heater resistance at room temperature
- [MQ135](https://www.winsen-sensor.com/manual/mq135.html) - Winsen MQ135 heater resistance at room temperature
- [MQ3](https://www.olimex.com/Products/Components/Sensors/Gas/SNS-MQ3/resources/SNS-MQ3.pdf) - Hanwei original datasheet, hosted by Olimex
- [MQ5](https://www.winsen-sensor.com/product/mq-5.html) - Winsen MQ-5 heater resistance at room temperature
- [MQ4](https://www.winsen-sensor.com/product/mq-4.html) - Winsen MQ-4 heater resistance at room temperature
- [MQ7](https://www.sparkfun.com/datasheets/Sensors/Biometric/MQ-7.pdf) - Hanwei original datasheet, hosted by SparkFun
- [MQ6](https://www.winsen-sensor.com/product/mq-6.html) - Winsen MQ-6 heater resistance at room temperature
- [MQ2](https://www.winsen-sensor.com/product/mq-2.html) - Winsen MQ-2 heater resistance at room temperature
- [INA333](https://www.ti.com/lit/ds/symlink/ina333.pdf) - TI quiescent current, output unloaded
- [MCP4725](https://ww1.microchip.com/downloads/aemDocuments/documents/MSLD/ProductDocuments/DataSheets/MCP4725-Data-Sheet-20002039E.pdf) - Microchip supply current, DS20002039E p3
- [TPS22919](https://www.ti.com/lit/ds/symlink/tps22919.pdf) - TI switch supply current and on-resistance
- [LM321DTR (XBLW)](https://xonstorage.z8.web.core.windows.net/pdf/xblw_lm321dtrxblw_xonlink.pdf) - XBLW original datasheet v1.0 p2; distributor mirror
- [CH340C](https://www.hestore.eu/en/prod_getfile.php?id=21171) - WCH original datasheet v3D, section 6.3; distributor mirror
