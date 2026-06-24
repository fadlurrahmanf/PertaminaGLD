# Pertamina GLD Firmware

Firmware implementation starts from the shared protocol layer.

## Current Status

- Phase: `1 - GLD-CH Uplink MVP`
- Current versions:
  - GLD `v0.6.4`
  - CH `v0.5.3`
  - Gateway `v0.1.3`
- Current implemented scope: shared protocol primitives, host-level contract tests, GLD frame builder, GLD retry/provisioning scaffold, GLD board pins/power-mode detection/moving average/ADS1256/LoRa init self-test scaffold, GLD nulling self-test scaffold, GLD STAR LoRa TX self-test, GLD STAR alarm self-test, shared config/radio abstraction, CH uplink parser/ACK scaffold, CH opaque NodeCache, alarm queue, TX queue, pull request parser, runtime orchestrator, CH cluster response packing, CH Radio A STAR RX self-test, CH non-blocking STAR+MESH runtime, Gateway MESH+MQTT runtime, SERVER_PULL_REQUEST `requestId + hopList[]` alignment, GLD -> CH -> Gateway -> Node-RED normal pull validation, and GLD alarm push delivery validation.

## Folders

- `shared/`: protocol code shared by GLD and CH firmware.
- `gld/`: GLD firmware entry points, GLD-only config, frame builder, and alarm retry state before radio integration.
- `ch/`: CH protocol-side parser, ACK helpers, opaque cache, alarm queue, TX queue, runtime orchestration, and response packing before radio integration.
- `gateway/`: Gateway MESH radio and WiFi/MQTT bridge for Node-RED bench integration.
- `lib/`: local library copies from the field-tested legacy firmware; sensor ADS1256 code uses `ADS1256-main` from here, not a custom ADC library.
- `tests/`: host-level tests for byte-level protocol contracts.
- `versions/`: version history and rollback backup policy.

## Board Self-Test

The first board target is `gld_selftest_esp32s3`.

It verifies:

- firmware/protocol version logging,
- canonical GLD plaintext payload `01 50 0E 74`,
- canonical AAD `F0 01 2A 11 01`,
- AES-GCM encrypted payload 29 byte,
- `SENSOR_DATA` AppFrame generation,
- GLD frame builder modes: vector, normal, alarm, retry, and clear.

It does not read gas sensors, transmit LoRa, run inference, or enter dataset/nulling modes.

Build command:

```powershell
pio run -d firmware -e gld_selftest_esp32s3
```

## GLD Sensor Self-Test

The sensor bring-up target is `gld_sensor_selftest_esp32s3`.

It verifies:

- board pin constants for SPI, ADS1256, battery, and 24V power-good,
- ADS1256 init and register reads through the local legacy `ADS1256-main` library,
- 8 single-ended ADS1256 channel reads in final sensor order,
- adaptive ADS1256 gain settling before declaring self-test pass/fail,
- per-channel moving average,
- three GLD power modes: `battery` from BatMon, `24v` from PG24, and inferred external `5v` when neither BatMon nor PG24 is active,
- battery mV/raw ADC read from GPIO4,
- PG24 read from GPIO45,
- SX1262/E22 LoRa init through local `RadioLib`, without transmitting a production packet.

It does not transmit LoRa, run inference, run nulling, publish MQTT, or alter the running encrypted payload contract.

Build command:

```powershell
pio run -d firmware -e gld_sensor_selftest_esp32s3
```

Upload command for the current GLD board on COM10:

```powershell
pio run -d firmware -e gld_sensor_selftest_esp32s3 -t upload --upload-port COM10
```

Latest board result for threshold `0.0005V`:

- upload to COM10 succeeded,
- firmware boot and serial logging succeeded,
- on the first tested board, `ADS_BEGIN_RESULT=FAIL` with ADS register readback
  `STATUS=0x00`, `MUX=0x00`, `ADCON=0x00`, `DRATE=0x00`; hardware probing then
  found ADS VREFP around `0.8V` while the op-amp output before R74 was around
  `2.2V`, so that board is treated as a hardware/reference issue,
- after the board was replaced, `ADS_BEGIN_RESULT=PASS`,
- ADS register readback on the replacement board was `STATUS=0x36`,
  `MUX=0x0F`, `ADCON=0x06`, `DRATE=0xF0`,
- power mode detection reported `POWER_SELFTEST mode=5v`, `batteryValid=0`,
  `externalPower=1`, `pg24=0`, and `POWER_SELFTEST_RESULT=PASS`; this is
  expected for external 5V because this board cannot run from USB alone, 5V has
  no dedicated detect pin, and 5V is inferred when BatMon and PG24 are both
  inactive,
- LoRa init first failed with TCXO `1.6V` (`LORA_BEGIN_TCXO16_STATE=-707`) and
  then passed with XTAL/TCXO `0V` fallback (`LORA_BEGIN_XTAL_STATE=0`,
  `LORA_STANDBY_STATE=0`, `LORA_SELFTEST_RESULT=PASS`),
- early scans saturated while the adaptive gain stepped down,
- from the later scans all 8 channels reported `status=Ok`, valid voltage,
  moving average voltage, and `allValid=1`,
- `SENSOR_SELFTEST_PASS_SCAN=4` and `SENSOR_SELFTEST_RESULT=PASS`,
- no LoRa TX, inference, dataset, nulling, or running payload was executed.

This means the replacement GLD board can read the ADS1256 sensor front-end,
detect the current 5V external power mode by inference, grant the same external
power privilege to 5V as 24V, initialize SX1262 LoRa without transmitting, and
keep the sensor scan valid after LoRa init. The
self-test waits for the adaptive gain to settle before printing
`SENSOR_SELFTEST_RESULT`, so the expected final board result is `PASS` after a
valid settled scan, not during the first saturated scan.

## GLD Nulling Self-Test

The nulling bring-up target is `gld_nulling_selftest_esp32s3`.

It verifies:

- TCA9548A I2C mux init at `0x71`,
- MCP4725 DAC access at `0x60`,
- non-linear sensor-to-mux mapping `{7, 6, 5, 4, 3, 2, 0, 1}`,
- external-power gating before nulling,
- before/nulling/after serial report per sensor channel,
- DAC writes through `writeDAC(value, false)` so the self-test does not write MCP4725 EEPROM,
- no LoRa TX, no running `SENSOR_DATA`, and no production profile save.

Build command:

```powershell
pio run -d firmware -e gld_nulling_selftest_esp32s3
```

Upload command for the current GLD board on COM10:

```powershell
pio run -d firmware -e gld_nulling_selftest_esp32s3 -t upload --upload-port COM10
```

Latest board result:

- upload to COM10 succeeded,
- firmware `0.5.5` booted and logged `POWER_SELFTEST mode=5v`,
  `externalPower=1`, `pg24=0`, and `POWER_SELFTEST_RESULT=PASS`,
- `ADS_BEGIN_RESULT=PASS`,
- `DAC_MUX_BEGIN_RESULT=PASS`,
- all 8 `NULLING_BEFORE` rows were valid and non-saturated,
- all 8 per-channel `NULLING_RESULT` rows succeeded,
- all 8 `NULLING_AFTER` rows were valid and non-saturated,
- final result was `NULLING_SELFTEST_RESULT=PASS`.

Captured before/after summary:

| Channel | Sensor | Before V | DAC Code | After V | Result |
|---|---:|---:|---:|---:|---|
| 0 | MQ8 | 0.000806 | 419 | 0.005827 | PASS |
| 1 | MQ135 | 0.000280 | 957 | 0.001203 | PASS |
| 2 | MQ3 | 0.000119 | 861 | 0.000360 | PASS |
| 3 | MQ5 | -0.001223 | 968 | -0.000175 | PASS |
| 4 | MQ4 | 0.000206 | 585 | 0.001855 | PASS |
| 5 | MQ7 | -0.000382 | 275 | 0.001161 | PASS |
| 6 | MQ6 | 0.000712 | 336 | 0.001264 | PASS |
| 7 | MQ2 | 0.000244 | 436 | 0.000787 | PASS |

This confirms the nulling hardware path is alive on the current GLD board:
external-power detection, ADS1256 reads, TCA9548A mux selection, MCP4725 DAC
writes, and per-channel before/after measurement all work. This target is still
a lab self-test; production nulling profile persistence and monotonic
`nullingProfileId` are implemented in a later stage.

Latest board result for threshold `0.0001V`:

- upload to COM10 succeeded,
- firmware `0.5.6` booted with `NULLING_CONFIG thresholdV=0.000100`,
- `POWER_SELFTEST_RESULT=PASS`, `ADS_BEGIN_RESULT=PASS`, and
  `DAC_MUX_BEGIN_RESULT=PASS`,
- all 8 channels produced valid before readings, successful DAC response, valid
  after readings, and final `NULLING_SELFTEST_RESULT=PASS`.

Captured before/after summary:

| Channel | Sensor | Before V | DAC Code | After V | Closer To Zero |
|---|---:|---:|---:|---:|---|
| 0 | MQ8 | 0.000803 | 418 | 0.000804 | NO |
| 1 | MQ135 | 0.000279 | 956 | 0.000635 | NO |
| 2 | MQ3 | 0.000121 | 860 | 0.000217 | NO |
| 3 | MQ5 | -0.001225 | 967 | -0.000958 | YES |
| 4 | MQ4 | 0.000206 | 584 | 0.000487 | NO |
| 5 | MQ7 | -0.000381 | 271 | -0.000065 | YES |
| 6 | MQ6 | 0.000711 | 337 | 0.001342 | NO |
| 7 | MQ2 | 0.000245 | 448 | 0.000588 | NO |

This confirms the lower threshold causes earlier DAC response detection, but it
does not turn the current self-test algorithm into true zero-seeking nulling.
Production nulling must choose the DAC code that minimizes `abs(voltage)`, not
the first DAC code that crosses `abs(voltage - baseline) >= threshold`.

## GLD-to-CH STAR LoRa Link Self-Test

The GLD transmitter target is `gld_lora_tx_selftest_esp32s3`.

It verifies:

- SX1262/E22 init on the GLD board with STAR radio settings,
- contract `SENSOR_DATA` AppFrame generation through `buildGldUplinkFrame()`,
- encrypted GLD payload length of 29 byte,
- total GLD uplink frame length of 39 byte,
- test-only `nodeId=0xF001`, `chId=0x0064`, clear-gas normal external frame,
- LoRa transmit through RadioLib without legacy `NORMAL/ALARM/HEALTH` payloads.

Upload command for the current GLD board on COM10:

```powershell
pio run -d firmware -e gld_lora_tx_selftest_esp32s3 -t upload --upload-port COM10
```

Alarm push test target:

```powershell
pio run -d firmware -e gld_lora_alarm_selftest_esp32s3 -t upload --upload-port COM10
```

The alarm target uses the same GLD STAR TX path but compiles with
`GLD_SELFTEST_ALARM_FRAME=1`, so it sends:

- `gasClass=1 LPG`,
- `confidence=30`,
- `threshold=30`,
- `typeFlags=0xD0`,
- `alarm=1`,
- `externalPower=1`.

The CH receiver target is `ch_star_rx_selftest_esp32s3`.

It verifies:

- Radio A / U1 STAR pin mapping from `docs/design/ch/design.md`,
- proven CH init pattern from `C:\Users\asus\Downloads\Implementasi Sistem\Implementasi Sistem\ClusterHead_DualLoRa`,
- RadioLib `SX1262` init on CH Radio A / U1 with `SPISettings(2000000, MSBFIRST, SPI_MODE0)`,
- STAR RX at 920.0 MHz, BW 125 kHz, SF7, CR 4/5, sync word `0x12`,
- raw received frame logging,
- `parseGldUplinkFrame()` validation of AppFrame, CRC, `typeFlags`, and 29-byte encrypted payload.

Upload command for the current CH board on COM9:

```powershell
pio run -d firmware -e ch_star_rx_selftest_esp32s3 -t upload --upload-port COM9
```

Latest board result:

- CH upload to COM9 succeeded.
- GLD upload to COM10 succeeded.
- GLD Radio init: TCXO `1.6V` returned `-707`, XTAL/TCXO `0V` fallback returned `0`, and `GLD_STAR_TX_READY=1`.
- GLD normal TX produced repeated 39-byte frames with `typeFlags=0x90`, `alarm=0`, `recordFlags=0x10`, payload length `29`, and `GLD_LORA_TX_RESULT=PASS`.
- Initial CH Radio A init failed before the proven init pattern was applied.
- After adapting the proven CH init pattern, CH Radio A / U1 reported `CH_STAR_PROBE radio=A/U1 beginState=0`, `CH_STAR_ACTIVE_RADIO=A/U1`, and `CH_STAR_RX_READY=1`.
- CH received GLD frame length `39` with `rssi=-97.00`, `snr=11.25`.
- CH parser result: `CH_STAR_PARSE status=Ok nodeId=0xF001 ... typeFlags=0x90 alarm=0 externalPower=1 payloadLen=29`.
- Final result: `CH_LORA_RX_RESULT=PASS`.

This confirms the current GLD board can transmit a contract-compatible encrypted
running frame to the current CH board through Radio A / U1 STAR, and the CH can
receive and parse it.

Latest alarm push board result:

- Host tests: `python firmware/tests/run_tests.py` -> `26/26 tests passed`.
- GLD alarm target upload to COM10 succeeded.
- Node-RED MQTT alarm proof:
  - topic `gld/server/alarm`,
  - `outer.msgType=16`,
  - `outer.typeFlags=208`,
  - `outer.srcIdHex=0x0064`,
  - `outer.dstIdHex=0x006F`,
  - `nodeIdHex=0xF001`,
  - `flags=17`,
  - `alarm=true`,
  - `decryptOk=true`,
  - `gasClass=1 LPG`,
  - `confidence=30`,
  - `batteryMv=65535`.
- After the alarm proof, COM10 was returned to the normal
  `gld_lora_tx_selftest_esp32s3` target.

This validates alarm push delivery from GLD through CH and Gateway to Node-RED.
It does not yet validate production MESH ACK/retry behavior: Gateway sends a
compact ACK, but CH runtime does not yet consume Gateway compact ACK frames and
currently marks alarm sent after local MESH TX success.
