# GLD TPL5010 Wake/Sleep COM10 Report

Date: 2026-07-14

Status: partial, not clear. The firmware sleep path and CLR pulse are proven on
COM10, but TPL5010 automatic wake-back is not proven. A passive COM10 capture
showed no automatic wake for 700 seconds after the node was already off/silent.

## Scope

- Board under test: GLD battery board on COM10 only.
- Explicit exclusion: COM9 was not used for this wake/sleep proof.
- Wiring artifact: `docs/wiring/gld-project-ver2-2026-07-01/source-GLD_Project.zip`,
  extracted schematic JSON
  `docs/wiring/gld-project-ver2-2026-07-01/1-Schematic_GasLeakIntegratedVer2.json`.
- Firmware evidence: current GLD firmware sources under `firmware/gld/`.

## Requirement Checklist

| Requirement | Evidence | Status |
| --- | --- | --- |
| Session renamed to `cek tpl wake up and sleep` | Thread title was updated in Codex app | Done |
| Verify CLR initial state HIGH in setup | `beginGldPowerPins()` sets `PIN_POWER_LATCH_CLR` output HIGH | Done |
| Verify sleep pulse is HIGH-LOW-HIGH on CLR | `pulseGldPowerLatchClear()` writes HIGH, LOW, HIGH with 5 ms delays | Done |
| Add manual serial sleep command | `SLEEP_NOW` parses on Serial/Serial0 and calls the same CLR pulse path | Done |
| Simulate TPL5010 plus SN74AUP1G74 function from wiring | Schematic audit maps U46/U51/U52, R92, R107, WAKE/PRE/CLR/ENA | Done |
| Identify resistor for near-3-minute TPL interval | R92 is 33k ohm; nominal is about 159 s, not exact 180 s | Done |
| Prove ESP actually powers off/sleeps on COM10 | After `GLD_BATTERY_CYCLE_DONE power_off` and after manual `SLEEP_NOW`, COM10 capture goes silent/port drops | Strong serial evidence |
| Prove ESP wakes again automatically after TPL interval | Passive capture did not see wake for 700 s | Failed / not proven |

## Datasheet Logic Anchors

Reference datasheets used for the functional simulation:

- TI TPL5010 datasheet:
  `https://www.ti.com/lit/ds/symlink/tpl5010.pdf`.
- TI SN74AUP1G74 datasheet:
  `https://www.ti.com/lit/ds/symlink/sn74aup1g74.pdf`.

The relevant behavior is:

- TPL5010 `WAKE` is an active-high periodic pulse. The datasheet lists
  `tWAKE` as 20 ms typical.
- TPL5010 `DONE` is the watchdog acknowledgement from the microcontroller.
- TPL5010 normal mode asserts periodic WAKE pulses in response to valid DONE
  pulses.
- TPL5010 `DELAY/M_RST` reads the external resistor to select `tIP`.
- SN74AUP1G74 `/PRE` and `/CLR` are active-low asynchronous inputs.
- SN74AUP1G74 `/PRE=LOW` and `/CLR=HIGH` sets `Q=HIGH`.
- SN74AUP1G74 `/CLR=LOW` resets `Q=LOW`; if `/PRE` and `/CLR` are both low,
  `/CLR` overrides `/PRE`.

## Wiring Evidence

From `1-Schematic_GasLeakIntegratedVer2.json`, Sheet_2:

- U46: `TPL5010DDCR`.
- U51: `SN74AUP1G74DCUR`.
- U52: `SN74LVC1G04DCKR` inverter.
- R92: `33k` ohm, manufacturer part `0603WAF3302T5E`, connected to
  `DELAY/M_RST` and GND.
- C98: `100nF` on the TPL5010 timing/AON area.
- R107: `10k` ohm pull-up from `CLR` to `3V3AON`.
- TPL5010 nets:
  - `WAKE` leaves U46 pin 5.
  - `DONE` enters U46 pin 4.
  - `RST` leaves U46 pin 6.
  - `DELAY/M_RST` uses R92 to GND.
  - VDD is on `3V3AON`.
- Latch nets:
  - U51 pin 5 `Q` is `ENA`.
  - U51 pin 6 `/CLR` is `CLR`.
  - U51 pin 7 `/PRE` is `PRE`.
  - U51 VCC is `3V3AON`.
  - U52 input is `WAKE`, U52 output is `PRE`.
- AON regulator path:
  - U42 is `TPS7A0233DBVR`.
  - U42 output is `3V3AON`.
  - D3 `BAT54C` ORs `VBAT` and `5VBUCK` into the AON regulator input.

Interpretation: in the intended design, TPL5010 and the latch live on
`3V3AON`, so they should remain powered after the main `ENA` rail is cleared.
TPL WAKE should drive U52, U52 should pull `/PRE` low, and U51 should set
`ENA` high again.

## PCB Probe Evidence

From `1-PCB_PCB_GasLeakIntegratedVer2.json`, the timer/latch cluster is placed
close together. Coordinates below are EasyEDA PCB pad-center coordinates from
the JSON, useful for cross-checking the physical area and pad selection.

| Component | Ref | Function | Key pad/net | PCB pad center |
| --- | --- | --- | --- | --- |
| TPL5010DDCR | U46 | Timer/watchdog | pin 1 `3V3AON` | `3739.185,3387.760` |
| TPL5010DDCR | U46 | Timer/watchdog | pin 3 `R92_2` / `DELAY/M_RST` side | `3739.185,3395.240` |
| TPL5010DDCR | U46 | Timer/watchdog | pin 4 `DONE` | `3749.815,3395.240` |
| TPL5010DDCR | U46 | Timer/watchdog | pin 5 `WAKE` | `3749.815,3391.500` |
| TPL5010DDCR | U46 | Timer/watchdog | pin 6 `RST` | `3749.815,3387.760` |
| R0603 33k | R92 | TPL interval resistor | pad 1 `GND` | `3733.034,3402.000` |
| R0603 33k | R92 | TPL interval resistor | pad 2 `R92_2` | `3738.966,3402.000` |
| SN74AUP1G74DCUR | U51 | Power latch flip-flop | pin 8 `3V3AON` | `3767.547,3383.399` |
| SN74AUP1G74DCUR | U51 | Power latch flip-flop | pin 7 `PRE` | `3769.516,3383.399` |
| SN74AUP1G74DCUR | U51 | Power latch flip-flop | pin 6 `CLR` | `3771.484,3383.399` |
| SN74AUP1G74DCUR | U51 | Power latch flip-flop | pin 5 `ENA` | `3773.453,3383.399` |
| SN74LVC1G04DCKR | U52 | WAKE inverter | pin 2 `WAKE` | `3762.324,3391.000` |
| SN74LVC1G04DCKR | U52 | WAKE inverter | pin 4 `PRE` | `3755.676,3388.441` |
| SN74LVC1G04DCKR | U52 | WAKE inverter | pin 5 `3V3AON` | `3755.676,3393.559` |
| R0603 10k | R107 | `/CLR` pull-up | pad 2 `3V3AON` | `3757.034,3373.500` |
| R0603 10k | R107 | `/CLR` pull-up | pad 1 `CLR` | `3762.966,3373.500` |
| TPS7A0233DBVR | U42 | Always-on 3.3 V regulator | pin 5 `3V3AON` | `3798.260,3480.669` |
| TPS7A0233DBVR | U42 | Always-on 3.3 V regulator | pin 2 `GND` | `3802.000,3489.331` |
| BAT54C | D3 | VBAT/5VBUCK OR diode to AON regulator | pin 1 `VBAT` | `3794.138,3498.260` |
| BAT54C | D3 | VBAT/5VBUCK OR diode to AON regulator | pin 2 `5VBUCK` | `3794.138,3505.740` |
| BAT54C | D3 | VBAT/5VBUCK OR diode to AON regulator | pin 3 `U42_1` | `3803.863,3502.000` |

PCB routing evidence also shows local tracks/vias on these nets:

- `WAKE`: U46 pin 5 routes toward U52 input.
- `PRE`: U52 output routes to U51 pin 7.
- `CLR`: U51 pin 6 routes through R107 pull-up and to ESP GPIO38.
- `ENA`: U51 pin 5 routes into the main power-enable path.
- `3V3AON`: U42 output feeds U46, U51, U52, R107, and related decoupling.

This means the physical probe should start in two nearby clusters:

- Timer/latch cluster: U46, U51, U52, R92, R107 around
  `x=3733..3773`, `y=3373..3402`.
- AON supply cluster: U42, D3 around `x=3794..3804`, `y=3480..3506`.

## Functional Simulation

This is the expected GLD battery-mode state machine when the TPL5010 and
SN74AUP1G74 path is healthy.

| Step | Event | `3V3AON` | `WAKE` | `PRE` | `CLR` | `ENA/Q` | ESP/main rail | Expected result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Sleep/off waiting state | HIGH | LOW | HIGH | HIGH via R107 | LOW | OFF | ESP silent, TPL/latch alive |
| 2 | TPL interval expires | HIGH | HIGH pulse, about 20 ms | LOW pulse via U52 | HIGH | HIGH | ON | U51 sets ENA and ESP boots |
| 3 | WAKE pulse ends | HIGH | LOW | HIGH | HIGH | HIGH latched | ON | ESP continues running |
| 4 | Firmware setup | HIGH | LOW | HIGH | GPIO38 HIGH | HIGH | ON | CLR is explicitly idle HIGH |
| 5 | Firmware keepalive | HIGH | LOW | HIGH | HIGH | HIGH | ON | GPIO14 DONE pulses HIGH then LOW |
| 6 | Firmware sleep request | HIGH | LOW | HIGH | HIGH-LOW-HIGH | LOW on LOW part | OFF | CLR active-low resets ENA |
| 7 | Next TPL interval | HIGH | HIGH pulse | LOW pulse | HIGH | HIGH | ON | ESP should boot again |

Comparison with COM10 evidence:

- Steps 2 to 6 were observed when the board was forced awake by USB/RTS reset.
- Step 6 was observed by the firmware log and the following serial silence.
- Step 7 was not observed during the 700 s passive capture.
- Therefore the failing or unproven section is after sleep, inside the
  always-on timer/latch path: `3V3AON`, U46 `WAKE`, U52 `PRE`, U51 `CLR`, or
  U51 `ENA`.

Timing note: firmware pulses TPL `DONE` during setup, before the final sleep
pulse. Therefore, with R92 = 33k, the next WAKE should occur about 159 s after
that DONE pulse, not exactly 159 s after `GLD_BATTERY_CYCLE_DONE`. Because the
work cycle is only a few seconds, a 700 s passive capture is still much longer
than the expected wake-back window.

## Firmware Evidence

`firmware/gld/include/BoardPins.h`:

- `PGL_GLD_PIN_TPL5110_DONE` is GPIO14.
- `PGL_GLD_PIN_POWER_LATCH_CLR` is GPIO38.

`firmware/gld/src/GldPower.cpp`:

- `beginGldPowerPins()` at line 62:
  - sets DONE as output LOW.
  - preloads CLR HIGH before making the pin OUTPUT, so the active-low latch
    clear line does not glitch low during boot.
- `pulseGldTpl5010Keepalive()` at line 76:
  - DONE HIGH, delay 5 ms, DONE LOW.
- `pulseGldPowerLatchClear()` at line 82:
  - CLR HIGH, delay 5 ms, CLR LOW, delay 5 ms, CLR HIGH.

`firmware/gld/src/GldUnifiedMain.cpp`:

- setup calls `beginGldPowerPins()` at line 2243 and then
  `pulseWdtKeepaliveNow()` at line 2244.
- battery mode is detected with `batteryPowerMode = !power.externalPower` at
  line 2272.
- loop battery branch logs `GLD_BATTERY_CYCLE_DONE power_off`, then calls
  `pulseGldPowerLatchClear()` at lines 2453-2454.
- serial command `SLEEP_NOW` emits `GLD_CMD_ACK_JSON`, logs
  `GLD_SERIAL_SLEEP_NOW ... clr=HIGH_LOW_HIGH`, flushes serial, then calls
  `pulseGldPowerLatchClear()`.
- setup waits for USB serial to settle with a plain delay before dispatching
  serial commands, so a queued `SLEEP_NOW` cannot clear the latch before the
  firmware banner is visible.

## TPL5010 Interval

TI TPL5010 datasheet table values around the target:

- 2 min: 29.35k ohm.
- 3 min: 34.73k ohm.
- 4 min: 39.11k ohm.

The schematic uses R92 = 33k ohm. Using the datasheet polynomial for the
100-1000 s range gives about 159 s, or about 2 min 39 s. Therefore the board is
not configured for exact 3 minutes by nominal resistance. A true 3 minute target
would use about 34.73k ohm, or a nearby practical standard value after tolerance
review.

## COM10 Evidence

Initial board state:

- COM10 enumerated as `USB-SERIAL CH340 (COM10)`.
- The CH340 COM port can remain visible even when the ESP side is not running,
  so COM10 visibility is not proof that the ESP is awake.
- COM10 chip probe showed ESP32-S3, MAC `e8:f6:0a:a0:f3:e8`, 16MB flash.

Firmware boot and sleep proof from COM10:

```text
13:41:15.657 BOOT rst:0x1 (POWERON),boot:0x9 (SPI_FAST_FLASH_BOOT)
13:41:16.881 RX Pertamina GLD unified firmware
13:41:16.885 RX Firmware version: 0.8.12
13:41:16.936 RX GLD_POWER mode=battery externalPower=0 batteryMv=3350
13:41:21.777 RX GLD_SENSOR_SCAN seq=0 allValid=1 primed=0 gasClass=6(anomaly) confidence=0 alarm=0
13:41:21.781 RX GLD_SECURITY_NOT_PROVISIONED aesKey=0 txBlocked=1
13:41:21.783 RX GLD_LORA_TX_RESULT=FAIL
13:41:21.785 RX GLD_BATTERY_CYCLE_DONE power_off
```

Passive no-wake proof from COM10 with the port held open:

```text
2026-07-14 13:25:56.063 START port=COM10 passive duration_s=700.0
2026-07-14 13:25:56.079 OPEN ok no_tx
2026-07-14 13:28:56.572 t=180.510 NO_RX silence_s=180.5 boot_count=0 cycle_count=0
2026-07-14 13:31:27.099 t=331.037 NO_RX silence_s=331.0 boot_count=0 cycle_count=0
2026-07-14 13:34:57.517 t=541.454 NO_RX silence_s=541.5 boot_count=0 cycle_count=0
2026-07-14 13:37:27.784 t=691.722 NO_RX silence_s=691.7 boot_count=0 cycle_count=0
2026-07-14 13:37:36.238 t=700.175 DONE boot_count=0 cycle_count=0
```

Manual/USB reset comparison:

- `esptool chip_id` can still force the ESP32-S3 into ROM bootloader on COM10.
- After that manual USB reset path, the GLD firmware can boot again and can
  reach `GLD_BATTERY_CYCLE_DONE power_off` again.
- This does not count as TPL5010 wake proof because it depends on USB/RTS
  interaction, not the TPL WAKE path.

Manual serial sleep command proof after firmware update:

```text
2026-07-14 14:24:16.856 RX Pertamina GLD unified firmware
2026-07-14 14:24:16.927 TX SLEEP_NOW reason=firmware_banner
2026-07-14 14:24:16.974 RX GLD_POWER mode=battery externalPower=0 batteryMv=3189
2026-07-14 14:24:17.010 RX GLD_INFO_JSON ... "sleepNow":"SLEEP_NOW" ...
2026-07-14 14:24:20.219 RX GLD_CMD_ACK_JSON {"cmd":"SLEEP_NOW","status":"ok","message":"clearing power latch via CLR",...}
2026-07-14 14:24:20.228 RX GLD_SERIAL_SLEEP_NOW power_off mode=battery externalPower=0 batteryMv=3188 clr=HIGH_LOW_HIGH
2026-07-14 14:24:20.437 READ_ERROR ... "Access to the port 'COM10' is denied."
2026-07-14 14:24:20.471 DONE sent=1 ack=1 sleep_log=1 cycle_log=0 read_errors=1
```

Interpretation: the uploaded firmware accepted `SLEEP_NOW` on COM10, executed
the same active-low CLR sleep path, and the serial link dropped immediately
after the sleep log. This is strong runtime evidence that the manual CLR sleep
path is working. It is still not proof of TPL auto-wake.

Follow-up wake-back attempt after manual `SLEEP_NOW`:

```text
2026-07-14 14:26:33.864 START COM10-only foreground SLEEP_NOW wakeback capture
2026-07-14 14:26:34.281 ESPTOOL A fatal error occurred: Could not open COM10, the port is busy or doesn't exist.
2026-07-14 14:26:38.331 RX --- Terminal on COM10 | 115200 8-N-1
2026-07-14 14:27:06.690 MARK sent=0 ack=0 sleep_log=0 since_sleep_s=none since_rx_s=28.4 post_sleep_boots=0
2026-07-14 14:27:13.908 NO_FIRMWARE_BANNER_BEFORE_40S no_tx
2026-07-14 14:27:13.912 DONE rc=1 sent=0 ack=0 sleep_log=0 cycle_log=0 post_sleep_boots=0
```

Interpretation: after the manual sleep, a later COM10-only attempt did not see
a firmware banner or post-sleep boot. COM9 was not used.

Latest passive COM10 auto-wake check:

```text
2026-07-14 14:30:58.896 START port=COM10 baud=115200 passive_dtr_rts_low duration_s=240 no_tx no_COM9
2026-07-14 14:30:59.067 OPEN ok dtr=False rts=False
2026-07-14 14:31:29.135 MARK t=30.2 since_rx_s=30.2 boot_count=0 cycle_count=0
2026-07-14 14:32:29.054 MARK t=90.2 since_rx_s=90.2 boot_count=0 cycle_count=0
2026-07-14 14:33:29.036 MARK t=150.2 since_rx_s=150.2 boot_count=0 cycle_count=0
2026-07-14 14:33:58.963 MARK t=180.1 since_rx_s=180.1 boot_count=0 cycle_count=0
2026-07-14 14:34:58.956 MARK t=240.1 since_rx_s=240.1 boot_count=0 cycle_count=0
2026-07-14 14:34:58.970 DONE boot_count=0 cycle_count=0
```

Interpretation: Windows still enumerated `USB-SERIAL CH340 (COM10)` and the
port opened, but the ESP firmware did not boot or print anything through the
nominal 159-180 s wake window. This reinforces that COM10 presence alone is
not proof that the ESP/main rail is alive.

## Current Conclusion

The firmware-side sleep sequence is correct and has run on COM10:

1. CLR idle HIGH during setup.
2. Battery mode detected.
3. GLD work cycle runs.
4. Firmware logs `GLD_BATTERY_CYCLE_DONE power_off`.
5. Firmware pulses CLR HIGH-LOW-HIGH.
6. Manual `SLEEP_NOW` also pulses CLR HIGH-LOW-HIGH through the same helper.
7. Serial goes silent / the COM10 handle drops afterward.

The hardware wake-back sequence is not proven:

1. Expected WAKE interval from R92=33k is around 159 s nominal.
2. Expected 3-minute interval would be around 180 s if REXT were about 34.73k.
3. COM10 passive capture saw no boot at 180 s, 331 s, 541 s, or 691 s.
4. A later 240 s passive check also saw no boot at 150 s, 180 s, or 240 s.
5. Therefore, current COM10 evidence contradicts the claim that the ESP wakes
   automatically after about 3 minutes.

## Most Likely Failure Area

Because firmware can boot and can clear the latch, the highest-value physical
checks are on the always-on timer/latch path:

1. `3V3AON` after `GLD_BATTERY_CYCLE_DONE`.
   - Expected: remains near 3.3 V.
   - If missing: TPL5010/U51/U52 cannot wake the board.
2. TPL5010 `WAKE` after 159-180 s.
   - Expected: active pulse from U46.
   - If missing while `3V3AON` is present: check TPL5010 orientation, soldering,
     R92 value, R92 connection to GND, or `DELAY/M_RST` state.
3. U52 output `PRE`.
   - Expected: inverter converts WAKE into active-low `/PRE` pulse.
   - If WAKE exists but PRE does not: check U52 power/orientation/soldering.
4. U51 `/CLR`.
   - Expected: high after ESP power is cut, via R107 pull-up to `3V3AON`.
   - If low: U51 clear overrides preset and ENA will never relatch.
5. U51 `ENA`.
   - Expected: goes high after `/PRE` pulse.
   - If PRE pulses and CLR is high but ENA stays low: check U51 orientation,
     soldering, or latch wiring.

## Next Bench Procedure

Use a scope or logic analyzer if available; a multimeter is enough for
`3V3AON` and `ENA`, but not ideal for the WAKE/PRE pulses.

1. Start COM10 monitor at 115200.
2. Force a boot with USB reset if needed.
3. Wait for `GLD_BATTERY_CYCLE_DONE power_off`.
4. Immediately measure:
   - `3V3AON`: should remain 3.3 V.
   - `ENA`: should be low after sleep.
   - `/CLR`: should return high after the firmware pulse.
5. Keep scope on:
   - TPL5010 `WAKE`.
   - U52 `PRE`.
   - U51 `ENA`.
6. Wait at least 240 s.
7. Expected healthy behavior:
   - WAKE pulse occurs around 159 s nominal with R92=33k.
   - PRE pulses low.
   - ENA goes high.
   - ESP boot log appears on COM10.

If this physical sequence does not happen, the failure is hardware-side in the
AON timer/latch path, not the GLD firmware sleep code.
