# Firmware Phase 1 Implementation Checklist Draft

**Status:** pre-coding checklist  
**Scope:** shared protocol, GLD running uplink, CH opaque cache/forwarding  
**Rule:** firmware coding starts only after explicit user approval.

---

## 1. Source Order

Read in this order before coding:

1. `docs/design/gld-ch/payload-contract.draft.md`
2. `docs/firmware/01-gld-reference-traceability.draft.md`
3. `docs/firmware/02-gld-3-stage-plan.draft.md`
4. `docs/firmware/03-phase-1-plan.draft.md`
5. `docs/firmware/05-firmware-versioning-backup-policy.draft.md`
6. `docs/design/gld/design.updated.draft.md`
7. `docs/design/ch/design.updated.draft.md`

If any old firmware behavior conflicts with the contract, the contract wins.

---

## 2. Do Not Start With Old Payloads

Do not implement or copy these as running LoRa payload:

- `LoRaNormalPayload`
- `LoRaAlarmPayload`
- `LoRaHealthPayload`
- `packetType` old wire format
- `sensorMv[8]`
- raw ADC / raw sensor voltage in running LoRa
- health/status internal fields in running LoRa
- nulling snapshot in running LoRa
- dataset record in running LoRa

---

## 3. Milestone 1 - Shared Protocol

Create shared protocol first.

Target files:

```text
firmware/shared/include/ProtocolConstants.h
firmware/shared/include/AppFrame.h
firmware/shared/include/GldPayload.h
firmware/shared/include/GldRecord.h
firmware/shared/src/AppFrame.cpp
firmware/shared/src/GldPayload.cpp
firmware/shared/src/GldRecord.cpp
```

Must include:

- AppFrame header layout and CRC.
- `typeFlags` helpers.
- GLD gas class constants.
- `GLD_LEL_THRESHOLD_PERCENT = 30`.
- GLD plaintext 4 byte encode/decode.
- Encrypted payload layout 29 byte constants.
- `GLDRecord` encode/decode.
- `CLUSTER_DATA_RESPONSE` capacity helper.

Acceptance:

- `SENSOR_DATA` normal battery = `0x10`.
- `SENSOR_DATA` normal external = `0x90`.
- `SENSOR_DATA` alarm battery = `0x50`.
- `SENSOR_DATA` alarm external = `0xD0`.
- GLD plaintext LPG confidence 80 battery 3700 = `01 50 0E 74`.
- `GLDRecord` with encrypted payload 29 byte = 34 byte.
- MESH payload 80 byte fits max 2 GLD records.

---

## 4. Milestone 2 - Crypto / AAD

Target files:

```text
firmware/shared/include/GldCrypto.h
firmware/shared/src/GldCrypto.cpp
```

Must include:

- AES-128-GCM encrypt/decrypt wrapper.
- 12-byte nonce.
- 12-byte tag.
- 4-byte ciphertext.
- 29-byte encrypted payload builder/parser.
- AAD builder:

```text
nodeId:uint16BE + gldSeq:uint8 + recordFlags:uint8 + keyId:uint8
```

Acceptance:

- Test vector passes:

```text
key        = 000102030405060708090A0B0C0D0E0F
keyId      = 01
nodeId     = F001
seq        = 2A
flags      = 11
nonce      = 101112131415161718191A1B
plaintext  = 01500E74
AAD        = F0012A1101
ciphertext = C57E0DDB
tag        = F88ABEC591E9F5BFAD982A6C
payload    = 01101112131415161718191A1BC57E0DDBF88ABEC591E9F5BFAD982A6C
```

---

## 5. Milestone 3 - GLD Running Uplink

Target files depend on final firmware structure, but the behavior must be:

1. Read 8 sensor voltages using final feature order:

```text
MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2
```

2. Use `movingAverageVoltage` / `voltage_after_gain_compensation`.
3. Validate active nulling profile.
4. Validate model sidecar metadata.
5. Block production running TX if:

```text
activeNullingProfileId != modelMetadata.boundNullingProfileId
```

6. Map model class to `gasClass` using metadata.
7. Convert confidence to `uint8 0..100`.
8. Decide alarm:

```c
gasClass != GLD_GAS_CLEAR &&
confidence >= GLD_LEL_THRESHOLD_PERCENT
```

9. Build plaintext 4 byte.
10. Encrypt to payload 29 byte.
11. Send AppFrame `SENSOR_DATA`.

Acceptance:

- `clearGas` always normal.
- LPG confidence 29 normal when threshold 30.
- LPG confidence 30 alarm when threshold 30.
- Low-confidence gas remains gas class with low confidence.
- Model/nulling profile mismatch blocks production running TX.
- GLD never wraps its own payload as `GLDRecord`.

---

## 6. Milestone 4 - CH STAR RX / Cache

Target files:

```text
firmware/ch/include/NodeCache.h
firmware/ch/src/NodeCache.cpp
firmware/ch/src/StarReceiver.cpp
```

Must include:

- AppFrame parser/validator.
- `payloadLen <= 64` validation.
- Running payload phase 1 expects 29 byte encrypted payload.
- Opaque cache by `nodeId`.
- Dedup by GLD `seq`.
- `record.flags` from `typeFlags`:

```text
NC_FLAG_ALARM     = 0x01
NC_FLAG_EXT_POWER = 0x10
```

Acceptance:

- CH does not decrypt payload.
- CH does not parse `gasClass`, `confidence`, `batteryMv`, health, raw sensor, dataset, or nulling.
- Normal frame updates cache and does not ACK.
- Alarm frame ACKs compact if queue is available.
- If alarm queue full, CH does not ACK GLD.

---

## 7. Milestone 5 - CH MESH Forwarding

Target files:

```text
firmware/ch/src/MeshForwarder.cpp
firmware/ch/src/ClusterDataResponse.cpp
```

Must include:

- Normal pull response `CLUSTER_DATA_RESPONSE`.
- Alarm push `SENSOR_DATA | FLAG_ALARM_ACK`.
- Recovery clear push `SENSOR_DATA` without `FLAG_ALARM_ACK`.

Acceptance:

- Normal `CLUSTER_DATA_RESPONSE` contains response header plus max 2 records for payload 29 byte.
- Alarm push contains exactly one `GLDRecord`.
- Recovery clear contains exactly one `GLDRecord`.
- Outer `CLUSTER_DATA_RESPONSE` does not use `FLAG_GLD_EXT_POWER`.
- Per-GLD power status stays in `GLDRecord.flags`.

---

## 8. Milestone 6 - Tests

Host-level tests:

- AppFrame encode/decode.
- CRC valid/invalid.
- `typeFlags` decode.
- GLD plaintext payload builder.
- AES-GCM test vector.
- AAD builder.
- `GLDRecord` encode/decode.
- `CLUSTER_DATA_RESPONSE` capacity.
- CH cache update.
- Alarm ACK behavior.

Device bench tests:

- synthetic normal GLD frame.
- synthetic alarm GLD frame.
- alarm retry with same frame snapshot.
- normal server pull returns max 2 records.
- model/nulling profile mismatch blocks production running TX.

---

## 9. Coding Gate

Do not begin firmware coding until user explicitly approves starting firmware implementation.

Recommended first coding command after approval:

```text
Start with Milestone 1 - Shared Protocol.
```

Before modifying firmware source/config for an official build, follow `05-firmware-versioning-backup-policy.draft.md`.
