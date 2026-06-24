# Firmware Phase 1 Plan Draft

**Status:** draft planning, belum mulai coding firmware  
**Tanggal:** 2026-06-15  
**Scope:** GLD-CH uplink MVP berdasarkan `docs/design/gld-ch/payload-contract.draft.md`  
**Model/effort yang disarankan:** GPT-5.5 high

Dokumen ini adalah rencana eksekusi firmware phase 1. Tujuannya membuat jalur uplink GLD -> CH bekerja secara minimal, terukur, dan tidak menutup jalan ke gateway, Node-RED, downlink, dan dashboard pada phase berikutnya.

---

## 1. Status Repo Saat Planning

Hasil inspeksi repo saat dokumen ini dibuat:

- Belum ada folder `firmware/`.
- File yang sudah ada adalah dokumen desain, kontrak payload, chat context, dan config template.
- Kontrak teknis uplink phase 1 sudah ada di:
  - `docs/design/gld-ch/payload-contract.draft.md`
- Template key/config non-secret sudah ada di:
  - `config/gld-crypto.env.example`
- Firmware GLD lama yang sudah jalan di board tersedia sebagai reference-only:
  - `D:\GasleakDetectorDesign\firmware`
- Traceability contract-vs-firmware-lama dicatat di:
  - `docs/firmware/01-gld-reference-traceability.draft.md`
- Arsitektur 3 stage GLD dicatat di:
  - `docs/firmware/02-gld-3-stage-plan.draft.md`

Implikasi:

- Phase 1 perlu membuat struktur firmware dari awal.
- Implementasi harus dimulai dari shared protocol, bukan langsung GLD atau CH sendiri-sendiri.
- Firmware baru bersifat contract-first; firmware lama hanya referensi pin/driver/runtime yang sudah terbukti.
- Tidak ada merge/copy otomatis dari firmware lama tanpa keputusan eksplisit di traceability matrix.
- Firmware coding belum boleh dimulai sebelum approval eksplisit dari user.

---

## 2. Goal Phase 1

Goal phase 1:

1. GLD bisa membentuk plaintext running payload 4 byte.
2. GLD bisa mengenkripsi payload menjadi 29 byte AES-128-GCM.
3. GLD bisa mengirim `SENSOR_DATA` normal/alarm ke CH melalui AppFrame.
4. CH bisa menerima AppFrame GLD.
5. CH menyimpan payload GLD sebagai opaque bytes di `NodeCache`.
6. CH bisa ACK alarm jika alarm diterima ke queue/processing.
7. CH bisa membentuk normal `CLUSTER_DATA_RESPONSE` berisi maksimal 2 `GLDRecord`.
8. CH bisa membentuk alarm push `SENSOR_DATA | FLAG_ALARM_ACK` berisi tepat 1 `GLDRecord`.
9. CH bisa membentuk recovery clear push berisi tepat 1 `GLDRecord` tanpa `FLAG_ALARM_ACK`.
10. Test/simulator bisa membuktikan byte layout, encryption test vector, cache, normal batch, dan alarm push sesuai kontrak.

Non-goal phase 1:

- Gateway firmware penuh.
- Node-RED production flow penuh.
- MySQL schema final.
- Dashboard.
- Downlink command execution.
- Field reliability penuh.
- Per-device key provisioning.
- Full ML integration di lapangan.

---

## 3. Recommended Repo Structure

Struktur awal yang disarankan:

```text
firmware/
  shared/
    include/
      gld_protocol.h
      app_frame.h
      crypto_contract.h
    src/
      app_frame.cpp
      gld_protocol.cpp
    test/
      test_vectors.cpp
      test_app_frame.cpp
      test_gld_record.cpp

  gld/
    platformio.ini
    include/
      GldConfig.h
      GldPayload.h
      GldCrypto.h
      GldRadio.h
      GldAlarm.h
    src/
      main.cpp
      GldPayload.cpp
      GldCrypto.cpp
      GldRadio.cpp
      GldAlarm.cpp
    test/
      test_payload_builder.cpp
      test_crypto_vector.cpp

  ch/
    platformio.ini
    include/
      ChConfig.h
      NodeCache.h
      AlarmQueue.h
      ClusterResponse.h
      ChRadioStar.h
      ChRadioMesh.h
    src/
      main.cpp
      NodeCache.cpp
      AlarmQueue.cpp
      ClusterResponse.cpp
      ChRadioStar.cpp
      ChRadioMesh.cpp
    test/
      test_node_cache.cpp
      test_cluster_response.cpp
      test_alarm_push.cpp
```

Catatan:

- `firmware/shared` berisi kontrak byte-level yang harus sama di GLD, CH, gateway, dan test host.
- `firmware/gld` dan `firmware/ch` boleh mengimpor header shared via PlatformIO `lib_extra_dirs` atau struktur library lokal.
- `firmware/gateway` belum dibuat pada phase 1 kecuali dibutuhkan untuk simulator ringan.

---

## 4. Pre-Coding Defaults

Bagian ini adalah default teknis yang dipilih untuk planning. Jika nanti source import atau hardware bench menunjukkan konflik, default ini boleh direvisi sebelum coding.

| Topic | Default Phase 1 | Alasan |
|---|---|---|
| Build system | PlatformIO | Cocok untuk ESP32-S3, test, dan struktur multi-firmware. |
| Framework | Arduino-ESP32 dulu | Lebih cepat untuk RadioLib dan bring-up; tetap bisa memakai mbedTLS/ESP32 API. |
| Radio library | RadioLib | Sudah selaras dengan desain GLD dan SX1262/E22 target. |
| AES-GCM library GLD | mbedTLS lewat Arduino-ESP32/ESP-IDF | AES-GCM tersedia matang, tidak perlu library crypto eksternal. |
| RNG nonce | `esp_random()` / hardware RNG ESP32 | Sesuai kontrak random nonce 12 byte. |
| Host/unit tests | PlatformIO native jika feasible, jika tidak pakai small C++ host harness | Byte layout harus bisa dites sebelum hardware. |
| `nodeId` source | config/provisioning constant phase 1 | Nanti bisa pindah NVS/provisioning tool. |
| `CH ID` destination | config/provisioning constant phase 1 | Phase 1 fokus uplink ke CH target tetap. |
| external power flag | GLD runtime power state | `FLAG_GLD_EXT_POWER` berasal dari status power GLD. |
| alarm ACK timeout | default awal 2000 ms | Selaras dengan RX window battery mode yang sudah ada di desain GLD. |
| alarm retry count | default awal 3 kali per event | Cukup untuk bench; field reliability diperdalam Phase 4. |
| GLD LEL threshold | default awal 30 percent confidence | Istilah operator `LEL threshold`; secara firmware phase awal diterapkan ke confidence model `0..100`. |
| normal TX | best-effort | Normal data dikoreksi oleh server pull berikutnya. |
| production secret | tidak masuk git/log/chat | Wajib untuk key produksi. |

Catatan:

- GLD tidak membungkus payloadnya sebagai `GLDRecord`; GLD hanya mengirim AppFrame payload encrypted 29 byte ke CH.
- CH yang membentuk `GLDRecord` saat data diteruskan ke MESH/server.
- `GLDRecord` phase 1 berukuran 34 byte: header 5 byte + payload 29 byte.
- `D:\GasleakDetectorDesign\firmware` tidak di-merge mentah; gunakan sebagai reference-only.
- Jika firmware lama konflik dengan kontrak, kontrak menang kecuali user menyetujui revisi kontrak.
- Arsitektur stage GLD mengikuti `docs/firmware/02-gld-3-stage-plan.draft.md`.

---

## 5. Reference-Only GLD Firmware Policy

Sebelum adaptasi modul GLD lama, gunakan matrix:

```text
docs/firmware/01-gld-reference-traceability.draft.md
```

Yang boleh diadaptasi dari firmware lama:

- PlatformIO/Arduino ESP32-S3 setup.
- Board pin mapping.
- RadioLib/SX1262 hardware init dan RF switch pattern.
- `PowerManager` dan TPL5110 flow.
- `InferenceStage` state flow.
- `ConfigStore` pattern.

Yang tidak boleh diikuti dari firmware lama untuk running LoRa phase 1:

- `LoRaPacketType NORMAL/ALARM/ACK/HEALTH`.
- `LoRaNormalPayload` 13 byte.
- `LoRaAlarmPayload` 33 byte.
- `sensorMv[8]` di alarm running LoRa.
- raw sensor, health, dan internal status dalam running payload.

Semua adaptasi dari firmware lama harus dicatat sebagai `dipakai`, `diadaptasi`, `ditolak`, atau `ditahan` di traceability matrix.

---

## 6. Implementation Order

Urutan paling aman:

1. **Shared Protocol**
   - constants,
   - endian helpers,
   - AppFrame encode/decode,
   - GLD plaintext payload encode,
   - GLDRecord encode/decode.

2. **Crypto Contract Test**
   - AES-GCM test vector,
   - AAD builder,
   - encrypted payload layout validation.

3. **GLD Payload Path**
   - payload builder,
   - alarm decision,
   - record flag mapping,
   - encryption wrapper,
   - AppFrame sender builder.

4. **CH Receive Path**
   - AppFrame parser,
   - `typeFlags` validation,
   - NodeCache update,
   - alarm ACK decision,
   - alarmQueue enqueue.

5. **CH MESH Payload Builders**
   - normal `CLUSTER_DATA_RESPONSE`,
   - alarm push one-record,
   - recovery clear one-record.

6. **Hardware Radio Integration**
   - GLD LoRa TX/RX window,
   - CH Radio A STAR receive/ACK,
   - CH Radio B MESH TX,
   - minimal serial logs.

7. **Bench Test**
   - GLD test/manual ID sends normal and alarm frames,
   - CH logs cache and response bytes,
   - host decoder verifies records and test vector.

Reasoning:

- Byte contracts must be stable before hardware timing.
- Crypto must be verified before LoRa integration, otherwise decrypt errors become hard to debug.
- CH should be validated with synthetic frames before real radio.

---

## 7. Shared Protocol Milestone

### 7.1 Files

Recommended files:

- `firmware/shared/include/gld_protocol.h`
- `firmware/shared/include/app_frame.h`
- `firmware/shared/include/crypto_contract.h`
- `firmware/shared/src/gld_protocol.cpp`
- `firmware/shared/src/app_frame.cpp`

### 7.2 Contents

Constants:

```c
GLD_GAS_CLEAR
GLD_GAS_LPG
GLD_GAS_PROPANE
GLD_GAS_BUTANE
GLD_GAS_METHANE
GLD_GAS_RESERVED
GLD_GAS_ANOMALY

GLD_LEL_THRESHOLD_PERCENT
GLD_RUNNING_PLAINTEXT_LEN
GLD_ENCRYPTED_PAYLOAD_LEN
GLD_AES_GCM_NONCE_LEN
GLD_AES_GCM_TAG_LEN
GLD_AES_KEY_LEN
GLD_BATTERY_MV_INVALID

GLD_RECORD_HEADER_LEN
GLD_PAYLOAD_MAX
NC_FLAG_ALARM
NC_FLAG_EXT_POWER

MSG_SENSOR_DATA
MSG_NODE_DOWNLINK
MSG_SERVER_PULL_REQUEST
MSG_CLUSTER_DATA_RESPONSE
MSG_SERVER_NODE_COMMAND

FLAG_ALARM_ACK
FLAG_GLD_EXT_POWER
MSG_TYPE_MASK
```

Struct/logic:

- `GldPlaintextPayload`
- `GldRecordView`
- AppFrame encode/decode helpers.
- Big-endian read/write helpers.
- CRC16-CCITT-FALSE helper if not already provided by radio/protocol lib.
- `buildAad(nodeId, seq, recordFlags, keyId)`.

### 7.3 Acceptance Criteria

- Encode plaintext LPG confidence 80 battery 3700 to `01 50 0E 74`.
- Build AAD for test vector to `F0 01 2A 11 01`.
- `GLDRecord` with 29-byte payload has size 34.
- `CLUSTER_DATA_RESPONSE` capacity calculation returns 2 records for 80-byte max payload.
- Parser rejects reserved flag bits nonzero.
- Parser rejects `payloadLen > 64`.
- Parser rejects invalid `msgType`.
- Parser rejects bit 7 active on non-`SENSOR_DATA` messages.
- Parser treats `0x50`, `0x90`, and `0xD0` as `typeFlags`, not new `msgType`.

---

## 8. GLD Milestone

### 8.1 Files

Recommended files:

- `firmware/gld/include/GldPayload.h`
- `firmware/gld/include/GldCrypto.h`
- `firmware/gld/include/GldAlarm.h`
- `firmware/gld/include/GldRadio.h`
- `firmware/gld/src/GldPayload.cpp`
- `firmware/gld/src/GldCrypto.cpp`
- `firmware/gld/src/GldAlarm.cpp`
- `firmware/gld/src/GldRadio.cpp`

### 8.2 Behavior

GLD phase 1 does:

1. Accept inference result or test/manual input:
   - `gasClass`,
   - `confidence`,
   - `batteryMv`,
   - power mode.
2. Validate running payload fields.
3. Decide alarm:
   ```c
   gasClass != GLD_GAS_CLEAR && confidence >= GLD_LEL_THRESHOLD_PERCENT
   ```
4. Build plaintext 4 byte.
5. Build AppFrame `typeFlags`:
   - normal battery `0x10`,
   - normal external `0x90`,
   - alarm battery `0x50`,
   - alarm external `0xD0`.
6. Build AAD from future `GLDRecord` fields:
   - `nodeId`,
   - GLD `seq`,
   - `recordFlags`,
   - `keyId`.
7. Encrypt AES-128-GCM to 29-byte payload.
8. Build AppFrame `SENSOR_DATA`.
9. If alarm, wait for ACK compact in RX window.
10. If alarm retry is needed, resend the same frame/payload for the same event.
11. Never wrap GLD payload as `GLDRecord` on the GLD side.

### 8.3 Phase 1 Test/Manual Mode

Because real ML may not be ready at firmware start:

- allow a compile-time or serial/test injection path,
- require GLD ID in `0xF000..0xFEFF`,
- mark logs clearly as test/manual,
- never count test/manual as production alarm on server.

### 8.4 Acceptance Criteria

- Given LPG confidence 30 battery 3700, GLD decides alarm.
- Given LPG confidence 29 battery 3700, GLD sends gas LPG with low confidence and no alarm.
- Given clearGas confidence 100, GLD sends non-alarm.
- Given active nulling profile and model metadata mismatch, GLD blocks production running TX.
- Given AI-not-ready/no-decision, GLD does not send alarm.
- AES-GCM output matches test vector using dummy key/nonce/AAD.
- Alarm retry reuses same encrypted payload/frame for the same event.
- Alarm retry does not change `gldSeq`, nonce, ciphertext, tag, payload, or frame snapshot.
- `payloadLen` is always 29 for running encrypted payload.
- External power sets `FLAG_GLD_EXT_POWER`.
- TPL5110 behavior is only used for battery mode.
- Production AES key is never printed to serial log.

---

## 9. CH Milestone

### 9.1 Files

Recommended files:

- `firmware/ch/include/NodeCache.h`
- `firmware/ch/include/AlarmQueue.h`
- `firmware/ch/include/ClusterResponse.h`
- `firmware/ch/include/ChRadioStar.h`
- `firmware/ch/include/ChRadioMesh.h`
- `firmware/ch/src/NodeCache.cpp`
- `firmware/ch/src/AlarmQueue.cpp`
- `firmware/ch/src/ClusterResponse.cpp`
- `firmware/ch/src/ChRadioStar.cpp`
- `firmware/ch/src/ChRadioMesh.cpp`

### 9.2 Behavior

CH phase 1 does:

1. Receive `SENSOR_DATA` on STAR.
2. Validate AppFrame:
   - magic,
   - CRC,
   - payloadLen,
   - valid `msgType`,
   - valid typeFlags usage.
3. Derive `record.flags`:
   - `NC_FLAG_ALARM` from `FLAG_ALARM_ACK`,
   - `NC_FLAG_EXT_POWER` from `FLAG_GLD_EXT_POWER`,
   - reserved bits 0.
4. Store payload opaque in `NodeCache`.
5. If alarm:
   - ACK GLD only if accepted into alarm queue/processing,
   - enqueue one-record alarm push for MESH.
   - if duplicate alarm is already queued/processing, ACK may be sent again without creating a duplicate event.
6. If normal:
   - update cache,
   - leave record unsent for next server pull.
7. If previous alarm becomes clear:
   - push recovery clear one-record without `FLAG_ALARM_ACK`.
8. Build normal `CLUSTER_DATA_RESPONSE` from unsent non-alarm records.
9. Mark `sentSeq = currentSeq` only after successful onward TX.
10. If onward TX fails, keep `sentSeq` unchanged.

### 9.3 Acceptance Criteria

- CH never decrypts or parses GLD payload.
- CH stores 29-byte payload unchanged.
- Alarm frame with queue available triggers ACK compact `typeFlags = 0x50`, payloadLen 0.
- Alarm frame with queue full does not ACK GLD.
- Duplicate alarm already queued/processing may be ACKed again but must not create a duplicate alarm record.
- Alarm push payload contains exactly one `GLDRecord`.
- Normal pull response contains response header plus max 2 records when each payloadLen is 29.
- `CLUSTER_DATA_RESPONSE` does not use outer `FLAG_GLD_EXT_POWER`.
- Recovery clear push has alarm flag 0 and no `FLAG_ALARM_ACK`.
- CH does not put device fault/AI-not-ready/no-decision into alarmQueue unless GLD explicitly sends valid alarm flag.
- CH rejects payloadLen over 64.
- CH rejects reserved `record.flags` bits if they appear in received/reconstructed records.
- If alarm/response TX fails, `sentSeq` does not advance.

---

## 10. Minimal Test Strategy

### 10.1 Host-Level Tests

Before hardware:

- test endian helpers,
- test AppFrame encode/decode,
- test CRC,
- test GLD plaintext payload builder,
- test AAD builder,
- test AES-GCM vector,
- test GLDRecord pack/unpack,
- test CH NodeCache update,
- test normal response capacity,
- test alarm push one-record,
- test recovery clear one-record.

### 10.2 Device Bench Tests

With boards:

1. GLD test ID `0xF001` sends normal frame.
2. CH receives and logs cache update.
3. Server pull simulator asks CH response.
4. CH returns `CLUSTER_DATA_RESPONSE`.
5. GLD sends alarm frame.
6. CH sends ACK compact.
7. CH builds alarm push one-record.
8. GLD sends clear frame.
9. CH builds recovery clear one-record.

### 10.3 Log Requirements

Minimum logs:

- GLD:
  - nodeId,
  - seq,
  - gasClass,
  - confidence,
  - batteryMv,
  - alarm yes/no,
  - payloadLen,
  - typeFlags.
- CH:
  - srcId,
  - seq,
  - typeFlags,
  - payloadLen,
  - cache slot,
  - alarmQueue status,
  - response recordCount.

Logs must not print production AES keys.

---

## 11. Key Risks

| Risk | Impact | Mitigation |
|---|---|---|
| GLD and CH duplicate constants differently | Decode mismatch | Start with shared protocol layer |
| AES-GCM nonce reuse | Security break | Random 12-byte hardware RNG and same-frame retry |
| CH accidentally parses encrypted payload | Layer violation | Keep CH opaque and test payload byte equality |
| `typeFlags` confused with `msgType` | Wrong routing | Shared parser and explicit tests |
| Alarm ACK interpreted as server delivery | False reliability | Document ACK as next-hop/queue acceptance only |
| Normal batch capacity overestimated | MESH payload overflow | Hard-code capacity test for 2 records |
| Test/manual alarms counted as production | Bad operations data | Reserved GLD ID and server filter |
| Real ML not ready | Cannot validate uplink | Use isolated test/manual GLD IDs |
| GLD sends `GLDRecord` instead of encrypted payload | Layer mismatch | GLD only sends 29-byte encrypted AppFrame payload; CH creates records |
| ACK sent before alarm is queued | Alarm loss | ACK only after queue accepted or duplicate already processing |
| Firmware lama di-merge mentah | Kontrak payload baru bisa kalah oleh payload lama | Reference-only dengan traceability matrix |
| Payload lama `NORMAL/ALARM/HEALTH` ikut terbawa | CH/server tidak sesuai kontrak | Rewrite LoRa wire protocol phase 1 |

---

## 12. Decision Gates

### Gate A: Planning Approval

User approves this phase-1 plan.

Output after approval:

- create firmware folder structure,
- create shared protocol stubs/tests,
- still no hardware-specific implementation until structure is accepted.
- use `01-gld-reference-traceability.draft.md` as required reference gate for any GLD legacy adaptation.

### Gate B: Shared Protocol Approval

Shared constants, AppFrame, GLDRecord, AAD, and test vector pass host tests.

Output after approval:

- start GLD payload/encryption implementation.

### Gate C: GLD Path Approval

GLD can produce valid encrypted `SENSOR_DATA` frames from test/manual data.

Output after approval:

- start CH receive/cache/response path.

### Gate D: CH Path Approval

CH can process synthetic GLD frames and build normal/alarm/clear onward payloads.

Output after approval:

- start radio integration/bench test.

---

## 13. Recommended Next Action

Next action after user approval:

```text
Create firmware/shared skeleton and host-level tests for protocol constants, AppFrame, GLDRecord, AAD, and AES-GCM test vector.
```

Do not begin firmware coding until user explicitly says to start firmware implementation.
