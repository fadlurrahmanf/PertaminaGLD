# Server Design

**Status:** draft server-side design + Node-RED bench reference  
**Tanggal:** 2026-06-18  
**Scope:** Node-RED/server layer untuk MQTT ingest, decrypt, dedup, alarm routing, storage, dan operator integration  
**Sumber utama:** `server/nodered/README.md`, `server/nodered/functions/pertamina-gld-decode.js`, `docs/design/gld-ch/payload-contract.draft.md`  

---

## 1. Ringkasan

Server adalah endpoint aplikasi yang menerima data dari Gateway, melakukan decrypt payload GLD, memvalidasi event, membuat `dedupKey`, routing event, dan pada phase production menyimpan data untuk dashboard/operator.

Untuk bench saat ini, server direpresentasikan oleh Node-RED flow dengan Aedes MQTT broker.

Status saat ini:

- Node-RED flow sudah deployed.
- Aedes broker aktif di port `1884`.
- Normal pull sudah menghasilkan `gld/server/decoded`.
- Alarm live test belum dilakukan.
- MySQL/dashboard production belum menjadi scope yang selesai.

Status matrix:

| Area | Status |
|---|---|
| MQTT ingest | Bench implemented |
| AppFrame/GLDRecord parse | Bench implemented |
| AES-GCM decrypt | Bench implemented |
| `dedupKey` generation | Bench implemented |
| Stateful dedup | Planned |
| Production alarm gate | Planned hardening |
| MySQL storage | Planned |
| Dashboard API/UI | Planned |

---

## 2. Tanggung Jawab Server

Server bertanggung jawab untuk:

- menerima uplink Gateway via MQTT,
- parse `AppFrame`,
- parse `GLDRecord`,
- reconstruct AAD,
- decrypt AES-128-GCM payload GLD,
- validate plaintext,
- emit `dedupKey` and later dedup normal/alarm/recovery in persistent storage,
- filter test/manual device,
- publish decoded/alarm/error topic,
- menyimpan data ke database phase lanjut,
- menyediakan command request/config/mode-switch ke Gateway/CH/GLD phase lanjut.

Server tidak bertanggung jawab untuk:

- menentukan alarm di CH,
- mengubah payload encrypted,
- mengirim request langsung ke GLD melewati CH,
- training model di firmware running.

---

## 3. Runtime Bench

Bench server:

```text
Node-RED + Aedes MQTT broker
```

Port:

```text
1884
```

Reason:

- Port `1883` di laptop bench sedang dipakai service Mosquitto lama.
- Aedes di Node-RED dipakai agar begitu Node-RED running, broker MQTT ikut tersedia.

Production dapat memakai:

- Node-RED + external broker,
- atau backend service terpisah,
- atau hybrid Node-RED orchestration + API/database service.

Kontrak topic sebaiknya tetap stabil.

---

## 4. Input Topics

Server menerima:

| Topic | Source | Fungsi |
|---|---|---|
| `gld/gateway/uplink` | Gateway | frame MESH utama |
| `gld/gateway/raw` | Gateway/debug | raw gateway input alternatif |
| `pertamina/gld/uplink` | compatibility | alias/legacy input |

Server juga menerima internal debug/test vector:

| Input | Fungsi |
|---|---|
| GLD AES-GCM test vector | test decrypt function |
| HTTP debug optional | hanya jika Gateway expose HTTP endpoint |

---

## 5. Output Topics

| Topic | Fungsi |
|---|---|
| `gld/gateway/status` | status Gateway |
| `gld/gateway/events` | event envelope hasil parse |
| `gld/server/decoded` | event normal/recovery decrypted |
| `gld/server/alarm` | event alarm decrypted |
| `gld/gateway/error` | parse/decrypt/validation error |

Aturan:

- `gld/server/alarm` harus hanya untuk alarm valid dan production-eligible.
- Test/manual alarm dapat diarahkan ke alarm debug, tetapi tidak boleh dihitung sebagai alarm produksi.
- Error decrypt tidak boleh menjadi alarm produksi.

Current bench note:

- Decoder saat ini perlu hardening agar alarm topic tidak hanya berdasarkan `record.flags`.
- Production alarm route harus fail-closed jika decrypt/validation/test filter gagal.

---

## 6. Command Outputs

Server mengirim command ke Gateway:

| Topic | Fungsi |
|---|---|
| `gld/gateway/cmd/pull` | request latest cache dari CH target |
| `gld/gateway/cmd/node` | downlink command ke GLD via CH |

Pull payload:

```json
{
  "requestId": 1,
  "hopList": ["0x0064"]
}
```

Aturan pull:

- `gld/gateway/cmd/pull` mengikuti kontrak CH `SERVER_PULL_REQUEST` bagian 11.1.
- Payload logis adalah `requestId + hopList[]`.
- Pull adalah request level-CH ke latest cache CH target, bukan request per GLD.
- Tidak ada `node`, `dataType`, atau `targetCluster` pada pull.
- Untuk direct Gateway -> CH bench, `hopList=["0x0064"]`.

Node command payload:

```json
{
  "cluster": "0x0064",
  "node": "0xF001",
  "id": 1,
  "ttl": 600,
  "hex": "..."
}
```

Status:

- Pull normal sudah live-tested.
- Node command/downlink execution adalah phase lanjut.

---

## 7. Decode Pipeline

Pipeline:

```text
MQTT in
  -> normalize input
  -> parse AppFrame
  -> branch msgType
  -> parse GLDRecord(s)
  -> decrypt payload
  -> validate
  -> dedup/classify
  -> publish decoded/alarm/error
  -> store phase lanjut
```

Supported input shapes:

- Gateway JSON with `frameHex`.
- Direct `AppFrame` hex.
- Direct `GLDRecord` hex.
- Direct encrypted payload with metadata for debug.

---

## 8. AppFrame Branching

Server branches by `msgType`:

| `msgType` | Name | Server action |
|---:|---|---|
| `0x31` | `CLUSTER_DATA_RESPONSE` | parse response header and repeated `GLDRecord` |
| `0x10` + `FLAG_ALARM_ACK` | alarm `SENSOR_DATA` | parse one alarm `GLDRecord` |
| `0x10` without `FLAG_ALARM_ACK` | recovery clear | parse one recovery `GLDRecord` |

Unsupported `msgType`:

- publish error,
- do not drop silently.

---

## 9. GLDRecord Parse

`GLDRecord`:

| Field | Size |
|---|---:|
| `nodeId` | 2 |
| `seq` | 1 |
| `flags` | 1 |
| `payloadLen` | 1 |
| `payload` | N |

Phase 1:

```text
payloadLen = 29
recordSize = 34
```

Validation:

- `payloadLen` must match actual record bytes.
- For decrypt phase 1, `payloadLen` must be `29`.
- `flags` reserved bits should be checked/logged.

Alarm threshold:

- Nilai aktif phase ini adalah `GLD_LEL_THRESHOLD_PERCENT = 30`.
- Alarm ditentukan di GLD sebelum encrypt: `gasClass != clearGas && confidence >= 30`.
- Server memvalidasi dan menampilkan hasil, tetapi tidak mengganti keputusan alarm CH/GLD.
- Jika ada catatan lama yang menyebut threshold `80`, itu histori diskusi sebelum kontrak/firmware aktif memakai `30`.

---

## 10. AES-GCM Decrypt

Encrypted payload layout:

| Field | Size |
|---|---:|
| `keyId` | 1 |
| `nonce` | 12 |
| `ciphertext` | 4 |
| `tag` | 12 |

AAD:

```text
nodeId:uint16BE + gldSeq:uint8 + recordFlags:uint8 + keyId:uint8
```

Cipher:

```text
AES-128-GCM, tag 12 byte
```

Plaintext:

```text
gasClass:uint8 + confidence:uint8 + batteryMv:uint16BE
```

Key source:

- bench may use dummy test key,
- production must use secret store / environment,
- `.env` with secret must not be committed.

---

## 11. Validation

Server validates:

| Field | Rule |
|---|---|
| `gasClass` | `0..6` valid, `5` reserved |
| `confidence` | `0..100` |
| `batteryMv` | `0..65534` valid, `0xFFFF` invalid/unavailable |
| `payloadLen` | `29` for encrypted phase 1 |
| `keyId` | must be known |
| GCM tag | must verify |

If validation fails:

- event goes to error route,
- do not count as production event,
- include enough metadata for debug without exposing secret.

---

## 12. Event Classification

Server event fields should include:

| Field | Meaning |
|---|---|
| `nodeId` / `nodeIdHex` | GLD identity |
| `clusterId` | CH source/context |
| `gatewayId` | Gateway source |
| `seq` | GLDRecord seq |
| `alarm` | from `GLDRecord.flags` |
| `externalPower` | from `GLDRecord.flags` |
| `testDevice` | based on node ID range |
| `gasClass` / `gasName` | decrypted plaintext |
| `confidence` | decrypted plaintext |
| `batteryMv` | decrypted plaintext |
| `decryptOk` | decrypt result |
| `dedupKey` | event identity |

Current bench decoded example:

```json
{
  "nodeIdHex": "0xF001",
  "alarm": false,
  "externalPower": true,
  "testDevice": true,
  "decryptOk": true,
  "gasName": "clearGas",
  "confidence": 100,
  "batteryMv": 65535
}
```

---

## 13. Dedup Policy

Recommended:

```text
dedupKey = clusterId + nodeId + GLDRecord.seq + eventKind
```

Where:

| Component | Source |
|---|---|
| `clusterId` | outer AppFrame CH source |
| `nodeId` | GLDRecord |
| `seq` | GLDRecord |
| `eventKind` | normal/alarm/recovery |

Rules:

- Alarm retry with same key should not create new alarm event.
- Normal repeated response should not create duplicate storage rows if already stored.
- Payload hash can be added later to handle seq rollover/conflict.

Current Node-RED bench note:

- The decoder emits `dedupKey`.
- It does not yet maintain production dedup state across messages.
- Production dedup belongs in MySQL/backend storage or a durable state layer.
- Recommended bench improvement: Node-RED context map with TTL.
- Recommended production improvement: unique index on `dedup_key`.

---

## 14. Storage Direction

Phase lanjut storage should separate:

1. Raw gateway frames.
2. Decoded GLD events.
3. Alarm lifecycle.
4. Device registry.
5. Gateway/CH health.
6. Command audit.

Recommended minimum tables:

| Table | Purpose |
|---|---|
| `gateway_frames` | raw `frameHex`, RSSI/SNR, parse status |
| `gld_events` | decoded normal/recovery data |
| `gld_alarms` | alarm lifecycle/open/clear |
| `devices` | GLD/CH/Gateway registry |
| `commands` | downlink/pull audit |

MySQL is planned but not yet implemented as production storage.

---

## 15. Alarm Handling

Alarm route:

```text
gld/server/alarm
```

Alarm accepted if:

- decrypt OK,
- validation OK,
- `alarm = true`,
- production/test filter applied.

Current bench gap:

- Existing Node-RED flow must be hardened so `gld/server/alarm` is emitted only after the above checks.
- Until then, alarm live test results must be reviewed carefully and test/manual GLD IDs must not be counted as production alarms.

Alarm lifecycle:

- open on valid alarm event,
- update on repeated alarm retry without duplicate open,
- close on valid recovery clear.

Operator route phase lanjut:

- dashboard active alarm,
- notification,
- acknowledgment,
- manual test filter.

---

## 16. Test/Manual Filter

ID ranges:

| Range | Meaning |
|---:|---|
| `0x0001..0xEFFF` | production |
| `0xF000..0xFEFF` | test/manual |
| `0xFF00..0xFFFF` | system/future |

Rules:

- Current GLD `0xF001` is test/manual.
- Test/manual can be decoded and displayed.
- Test/manual must not count as production alarm.

---

## 17. Security

Server owns GLD AES decrypt keys.

Requirements:

- Production key from environment/secret store.
- Do not commit `.env`.
- Do not log AES key.
- Do not expose decrypted secrets beyond needed event fields.
- MQTT production should use auth and ideally TLS.
- Node-RED admin should be protected.

Bench warning:

- Dummy key fallback is for test only.
- Production must override key config.

---

## 18. Operator / UI Requirements

Server/dashboard should expose:

- Gateway online/offline.
- CH online/cache status.
- GLD latest status.
- Decoded gas class/confidence/battery.
- Active alarms.
- Alarm history.
- Test/manual marker.
- Pull request button per CH/GLD context.
- Command audit for future downlink.

Avoid showing encrypted payload as primary operator data.

---

## 19. Acceptance Criteria

Server normal pull bench considered OK if:

- Node-RED starts.
- Broker port available.
- Gateway connects MQTT.
- Pull inject publishes command.
- Gateway publishes uplink.
- Node-RED decodes `CLUSTER_DATA_RESPONSE`.
- `gld/server/decoded` contains `decryptOk=true`.
- Test/manual ID is identified.

Alarm route is not considered bench-passed until a real GLD alarm frame produces `gld/server/alarm`.

Production server acceptance later:

- MySQL storage active.
- Alarm lifecycle works.
- Dashboard shows latest and alarms.
- Secrets are not hardcoded.
- Backup/restore documented.

---

## 20. Open Items

- MySQL schema.
- Dashboard API.
- Production broker/auth/TLS.
- Alarm notification channel.
- Command/downlink execution confirmation.
- Data retention and backup policy.
- HA/auto-start deployment.
- Operator manual.
