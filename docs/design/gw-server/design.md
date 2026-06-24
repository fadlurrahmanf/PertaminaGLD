# Gateway-Server Design

**Status:** draft + bench-proven MQTT bridge  
**Tanggal:** 2026-06-18  
**Scope:** komunikasi Gateway ke server melalui MQTT/LAN  
**Sumber utama:** `firmware/gateway/src/GatewayMqttMeshMain.cpp`, `server/nodered/README.md`, `docs/design/gld-ch/payload-contract.draft.md`  

---

## 1. Ringkasan

Gateway-Server adalah boundary IP/LAN. Gateway publish frame MESH ke MQTT, dan server/Node-RED mem-parse, decrypt, dedup, lalu meneruskan event ke storage/dashboard/alarm route.

Jalur utama:

```text
Gateway MQTT client -> MQTT broker/server -> Node-RED flow -> decoded/alarm/storage
```

Status bench:

- Node-RED berjalan di laptop server.
- Aedes broker aktif di port `1884`.
- Gateway publish `gld/gateway/uplink`.
- Node-RED berhasil publish `gld/server/decoded`.

---

## 2. Transport

Protocol:

```text
MQTT over TCP/IP
```

Bench:

| Field | Nilai |
|---|---|
| Server IP | `CHANGE_ME_MQTT_HOST` |
| Broker | Aedes dari Node-RED |
| Port | `1884` |
| Gateway topic uplink | `gld/gateway/uplink` |
| Command topic | `gld/gateway/cmd/pull`, `gld/gateway/cmd/node` |

Catatan:

- Port `1884` dipakai karena port `1883` di laptop bench sedang dipakai service Mosquitto lama.
- Production boleh memakai broker terpisah, tetapi topic contract sebaiknya tetap stabil.

---

## 3. Topic Contract

Gateway -> Server:

| Topic | Payload | Fungsi |
|---|---|---|
| `gld/gateway/uplink` | JSON gateway uplink | AppFrame MESH dari CH |
| `gld/gateway/status` | JSON status | health Gateway |

Server -> Gateway:

| Topic | Payload | Fungsi |
|---|---|---|
| `gld/gateway/cmd/pull` | JSON command | server pull ke CH target |
| `gld/gateway/cmd/node` | JSON command | downlink command ke GLD via CH |

Server internal/output:

| Topic | Payload | Fungsi |
|---|---|---|
| `gld/gateway/events` | JSON envelope | hasil parse AppFrame/record |
| `gld/server/decoded` | JSON decoded | event normal/decrypted |
| `gld/server/alarm` | JSON decoded | event alarm/decrypted |
| `gld/gateway/error` | JSON error | parse/decrypt/error route |

Status topic note:

- Gateway firmware bench saat ini publish health ke `gld/gateway/status`.
- Node-RED flow juga dapat menghasilkan normalized status.
- Untuk production, rekomendasi kontrak yang lebih bersih:
  - raw gateway health: `gld/gateway/status/raw` atau `gld/gateway/health`,
  - normalized server/operator status: `gld/server/gateway/status`.
  - Nama final perlu dikunci sebelum dashboard production.

---

## 4. Gateway Uplink Payload

Gateway publish JSON ke `gld/gateway/uplink`.

Required fields:

| Field | Type | Keterangan |
|---|---|---|
| `source` | string | `"gateway"` |
| `gatewayId` | number | ID Gateway |
| `frameHex` | string | AppFrame MESH lengkap |
| `frameLen` | number | panjang frame byte |
| `rssi` | number | RSSI dari MESH RX |
| `snr` | number | SNR dari MESH RX |
| `parseStatus` | number | hasil parse Gateway |

Optional if parse OK:

| Field | Keterangan |
|---|---|
| `typeFlags` | outer typeFlags |
| `msgType` | `typeFlags & 0x3F` |
| `srcId` | CH source |
| `dstId` | Gateway destination |
| `seq` | MESH seq |
| `payloadLen` | payload length |

Server wajib memakai `frameHex` untuk decode final.

---

## 5. Pull Command Payload

Topic:

```text
gld/gateway/cmd/pull
```

Payload:

```json
{
  "requestId": 1,
  "hopList": ["0x0064"]
}
```

Aturan:

- Pull mengikuti kontrak CH `SERVER_PULL_REQUEST` bagian 11.1.
- `hopList[]` adalah daftar CH dari Gateway menuju CH target.
- Untuk direct Gateway -> CH bench, `hopList=["0x0064"]`.
- Gateway membangun payload wire `requestId:uint16BE + hopList:uint16BE[]`.
- Tidak ada `node`, `dataType`, atau `targetCluster` pada pull.
- Response dari CH kembali sebagai `CLUSTER_DATA_RESPONSE`.

---

## 6. Node Command Payload

Topic:

```text
gld/gateway/cmd/node
```

Payload:

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

- Gateway command builder tersedia.
- Full execution downlink ke GLD adalah phase lanjut.

Command class rencana:

- request data,
- config parameter GLD,
- switch GLD mode: `running`, `dataset`, `nulling`.

---

## 7. Server Decode Flow

Node-RED/server menerima `frameHex`, lalu:

1. Decode `AppFrame`.
2. Branch by `msgType`.
3. Parse `CLUSTER_DATA_RESPONSE` atau single-record `SENSOR_DATA`.
4. Extract `GLDRecord`.
5. Reconstruct AAD:

```text
nodeId:uint16BE + gldSeq:uint8 + recordFlags:uint8 + keyId:uint8
```

6. AES-128-GCM decrypt payload 29 byte.
7. Parse plaintext 4 byte:

```text
gasClass:uint8 + confidence:uint8 + batteryMv:uint16BE
```

8. Validate enum/range.
9. Dedup.
10. Publish decoded/alarm/error route.

Threshold note:

- Alarm phase aktif mengikuti firmware/contract terbaru: `GLD_LEL_THRESHOLD_PERCENT = 30`.
- Jika ada catatan lama yang menyebut `80`, itu histori diskusi lama dan bukan nilai aktif desain phase ini.

---

## 8. Alarm Route

If outer `msgType = SENSOR_DATA` and `FLAG_ALARM_ACK = 1`:

- parse exactly one `GLDRecord`,
- decrypt,
- validate,
- publish to `gld/server/alarm` only if alarm event is valid and production-eligible,
- store/dedup as alarm event.

If decrypt fails:

- publish error,
- do not count as production alarm.

Current Node-RED bench note:

- Existing decoder routes by `record.flags` and emits a `dedupKey`.
- Production alarm routing still needs a stricter gate:
  - `decryptOk == true`,
  - gas class and confidence valid,
  - `alarm == true`,
  - `testDevice == false`,
  - reserved flags clean.
- Test/manual alarm should not enter production alarm statistics.

---

## 9. Normal Route

If outer `msgType = CLUSTER_DATA_RESPONSE`:

- parse response header,
- iterate `recordCount`,
- decrypt each record,
- publish each event to `gld/server/decoded`,
- mark `response.status` for UI/debug.

If `recordCount = 0`:

- show as empty data response,
- not a decrypt failure.

---

## 10. Dedup

Recommended dedup key:

```text
clusterId + nodeId + GLDRecord.seq + eventKind
```

Where:

- `clusterId` = CH ID from outer AppFrame source or response context,
- `nodeId` = GLDRecord node,
- `GLDRecord.seq` = original GLD seq,
- `eventKind` = normal/alarm/recovery.

Optional phase lanjut:

```text
payloadHash
```

Use case:

- protects against `seq` rollover and rare conflicting same-seq events.

Current Node-RED bench note:

- Decoder saat ini menghasilkan `dedupKey`.
- Dedup persistence/state lintas message belum menjadi storage produksi.
- Idempotent storage perlu ditambahkan saat MySQL/backend production dibuat.
- Recommended bench improvement: Node-RED context TTL map keyed by `dedupKey`.
- Recommended production improvement: database unique constraint on `dedup_key`.

---

## 11. Test/Manual Filtering

Server must classify GLD ID:

| Range | Meaning |
|---:|---|
| `0x0001..0xEFFF` | production |
| `0xF000..0xFEFF` | test/manual |
| `0xFF00..0xFFFF` | system/future |

Rules:

- Test/manual events may be shown in debug/bench UI.
- Test/manual events must not count as production alarm statistics.
- Current bench GLD `0xF001` is test/manual.

---

## 12. Security

Gateway-Server production requirements:

- MQTT credential from secret/config, not source.
- TLS or isolated LAN recommended.
- Server holds AES key for GLD decrypt.
- Gateway must not log AES key.
- Gateway must not decrypt GLD payload.
- Node-RED `.env` must not be committed.

Bench note:

- Current flow can use dummy AES key for selftest.
- Dummy key is allowed in docs/tests but not production.

---

## 13. Acceptance Criteria

Gateway-Server normal pull bench dianggap OK jika:

- Gateway status appears on `gld/gateway/status`.
- Server command on `gld/gateway/cmd/pull` reaches Gateway.
- Gateway publishes `gld/gateway/uplink`.
- Node-RED parses `frameHex`.
- Node-RED emits `gld/gateway/events`.
- Node-RED emits `gld/server/decoded` with `decryptOk=true` for normal record.
- Alarm path emits `gld/server/alarm` when live-tested later; it is not part of current passed bench acceptance.

Current bench satisfies normal route.

---

## 14. Open Items

- Production broker deployment.
- TLS/auth hardening.
- MySQL persistence schema.
- Dashboard API.
- Alarm notification integration.
- Offline retry/backfill.
- Command audit log.
- Downlink command execution confirmation.
