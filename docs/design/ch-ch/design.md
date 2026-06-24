# CH-CH Design

**Status:** draft desain backbone antar-CH  
**Tanggal:** 2026-06-18  
**Scope:** komunikasi CH child ke CH parent dalam MESH/TREE sebelum mencapai Gateway  
**Sumber utama:** `docs/design/ch/design.updated.draft.md`, `docs/design/gld-ch/payload-contract.draft.md`, firmware shared protocol  
**Catatan:** desain ini tidak mengubah `docs/design/ch/design.md` original.

---

## 1. Ringkasan

CH-CH adalah jalur backbone ketika sebuah Cluster Head tidak langsung berbicara ke Gateway, tetapi mengirim data ke CH parent. Jalur ini memakai Radio B / MESH dengan `AppFrame` yang sama seperti jalur CH-Gateway.

Tujuan CH-CH:

- memperluas coverage area lewat TREE/MESH,
- menjaga payload tetap opaque dari GLD sampai server,
- meneruskan alarm prioritas tinggi tanpa menunggu pull,
- meneruskan `CLUSTER_DATA_RESPONSE` dari CH child menuju Gateway,
- menyediakan arah balik untuk request/config/downlink dari server.

Status implementasi saat ini:

- Firmware CH sudah punya dasar MESH runtime, queue, pull parser, alarm queue, dan response packing.
- Bench yang sudah terbukti adalah CH langsung ke Gateway.
- Multi-hop CH-CH belum menjadi jalur live-tested penuh dan harus diperlakukan sebagai desain phase lanjut.

Source priority:

1. `docs/design/gld-ch/payload-contract.draft.md` menang untuk `GLDRecord`, AES-GCM, dan payload GLD.
2. `docs/design/ch/design.updated.draft.md` menang untuk perilaku CH terbaru.
3. Dokumen ini hanya mengatur backbone CH-CH dan tidak boleh mengubah kontrak GLD payload.

---

## 2. Topologi

```text
GLD nodes
  -> CH child
      -> CH parent
          -> Gateway root
              -> Server / Node-RED
```

Istilah:

| Istilah | Arti |
|---|---|
| `localChId` | ID CH yang sedang menjalankan firmware |
| `parentId` | CH parent atau Gateway tujuan uplink |
| `gatewayId` | root akhir jaringan MESH |
| `childChId` | CH anak yang menitipkan traffic ke CH parent |
| `hopList` | daftar hop forward-only untuk request/downlink dari Gateway/server |

Aturan dasar:

- CH child mengirim MESH uplink ke `parentId`.
- CH parent meneruskan frame menuju parent berikutnya atau Gateway.
- Gateway adalah root yang menghubungkan MESH ke MQTT/server.
- GLD tetap tidak tahu apakah CH-nya langsung ke Gateway atau lewat CH parent.

---

## 3. Radio Dan Link

CH-CH memakai Radio B / MESH.

Parameter phase bench yang sudah dipakai firmware:

| Parameter | Nilai saat ini |
|---|---:|
| Frequency | `921.0 MHz` |
| Bandwidth | `125 kHz` |
| Spreading Factor | `SF9` |
| Coding Rate | `4/5` |
| Sync Word | `0x34` |
| Payload max | `80 byte` |

Catatan:

- Final field frequency dapat disesuaikan sebelum deployment.
- STAR GLD-CH dan MESH CH-CH/CH-Gateway harus dipisah supaya tidak saling mengganggu.
- CH runtime perlu non-blocking untuk radio STAR dan MESH agar tidak melewatkan GLD periodic saat menunggu MESH.

---

## 4. Frame Dasar

Semua frame CH-CH memakai `AppFrame`.

Ringkasan `AppFrame`:

| Field | Size | Catatan |
|---|---:|---|
| `magic` | 1 | `0xAA` |
| `typeFlags` | 1 | `msgType` + flags |
| `srcId` | 2 | ID pengirim hop saat ini |
| `dstId` | 2 | ID tujuan hop berikutnya |
| `seq` | 1 | sequence frame/transaction sesuai message flow |
| `payloadLen` | 1 | panjang payload |
| `payload` | N | max `80 byte` untuk MESH |
| `crc16` | 2 | CRC16-CCITT-FALSE |

Aturan CH-CH:

- `srcId` dan `dstId` adalah identitas hop, bukan selalu identitas asal GLD.
- Identitas GLD asli tetap berada di `GLDRecord.nodeId`.
- Untuk `SERVER_PULL_REQUEST` dan `CLUSTER_DATA_RESPONSE`, `AppFrame.seq` dipertahankan sebagai sequence request/response transaction, bukan diganti di setiap hop.
- Untuk ACK/retry alarm, `seq` mengacu pada outer frame yang sedang di-ACK/retry.
- `GLDRecord.seq` adalah sequence data/event GLD dan dipakai untuk dedup server.

---

## 5. Message Types

Message types phase awal yang relevan:

| `msgType` | Nama | Arah | Fungsi |
|---:|---|---|---|
| `0x10` | `SENSOR_DATA` | child -> parent | Alarm push atau recovery clear satu `GLDRecord` |
| `0x30` | `SERVER_PULL_REQUEST` | parent/root -> child | Request data CH target |
| `0x31` | `CLUSTER_DATA_RESPONSE` | child -> parent/root | Response data normal dari latest cache |
| `0x32` | `SERVER_NODE_COMMAND` | parent/root -> child | Scaffold command server untuk GLD melalui CH; belum live execution end-to-end |
| `0x33` | `CH_HELLO` | child <-> parent | Discovery/keepalive phase lanjut |
| `0x34` | `CH_CONFIG_REQUEST` | parent/root -> child | Config CH phase lanjut |
| `0x35` | `CH_CONFIG_RESPONSE` | child -> parent/root | Response config phase lanjut |

Catatan:

- `CH_HELLO`, `CH_CONFIG_REQUEST`, dan `CH_CONFIG_RESPONSE` sudah ada sebagai constants, tetapi belum menjadi fokus bench end-to-end.
- Gateway/Node-RED phase bench hanya meneruskan message type yang belum didukung sebagai raw frame/debug; belum ada route bisnis untuk CH hello/config.
- Multi-hop forwarding harus menjaga payload GLD tetap opaque.

---

## 6. Normal Pull Multi-Hop

Normal data tidak langsung dikirim ke server setiap GLD update. Server/Gateway melakukan pull ke CH target.

Alur:

```text
Server
  -> Gateway
  -> CH parent
  -> CH target
  -> CH parent
  -> Gateway
  -> Server
```

Request:

```text
msgType = SERVER_PULL_REQUEST (0x30)
```

Payload konseptual:

```text
requestId:uint16BE + hopList:uint16BE[]
```

Current bench compatibility:

- Firmware Gateway saat ini menerima JSON `hopList[]` dan membangun payload wire `requestId + hopList[]`.
- Direct single-hop Gateway -> CH tetap berukuran 4 byte: `requestId + hopList[0]`.
- Firmware CH menafsirkannya sebagai `requestId + hopList[]`, memvalidasi `dstId == localChId`, dan phase awal hanya menerima `hopCount == 1`.
- Multi-hop CH-CH membutuhkan `hopList[]` lebih dari satu entry dan relay logic yang belum live-tested.

Response:

```text
msgType = CLUSTER_DATA_RESPONSE (0x31)
```

`CLUSTER_DATA_RESPONSE` payload:

| Offset | Field | Size | Catatan |
|---:|---|---:|---|
| 0..1 | `requestId` | 2 | dari request |
| 2 | `status` | 1 | status data |
| 3..4 | `chBatteryMv` | 2 | `0xFFFF` jika invalid |
| 5 | `recordCount` | 1 | jumlah `GLDRecord` |
| 6.. | `records` | variable | repeated `GLDRecord` |

Kapasitas:

```text
MESH_MAX_PAYLOAD = 80
responseHeader = 6
GLDRecord phase 1 = 34
max records = floor((80 - 6) / 34) = 2
```

Aturan forwarding:

- CH parent meneruskan response tanpa decrypt payload GLD.
- CH parent boleh membaca outer `AppFrame` untuk routing.
- CH parent tidak boleh mengubah `GLDRecord.nodeId`, `seq`, `flags`, `payloadLen`, atau `payload`.

---

## 7. Alarm Push Multi-Hop

Alarm tidak menunggu pull.

Alur:

```text
GLD alarm
  -> CH target alarmQueue
  -> CH parent
  -> Gateway
  -> Server alarm route
```

Format antar-CH:

```text
msgType = SENSOR_DATA (0x10)
FLAG_ALARM_ACK = 1
payload = exactly one GLDRecord
```

Aturan:

- Alarm push membawa tepat satu `GLDRecord`.
- Tidak memakai wrapper `CLUSTER_DATA_RESPONSE`.
- Retry alarm harus mempertahankan `GLDRecord.seq` dan encrypted payload yang sama.
- CH parent harus memperlakukan alarm sebagai traffic prioritas.
- ACK hop MESH dan ACK GLD adalah dua hal berbeda.

---

## 8. Recovery Clear

Jika GLD yang sebelumnya alarm kembali clear/non-alarm, CH target harus push recovery clear.

Format:

```text
msgType = SENSOR_DATA (0x10)
FLAG_ALARM_ACK = 0
payload = exactly one GLDRecord
GLDRecord.flags bit0 alarm = 0
```

Aturan:

- Recovery clear tidak memakai `FLAG_ALARM_ACK`.
- CH parent meneruskan recovery clear seperti single-record sensor push.
- Server memakai event ini untuk menutup status alarm aktif.

---

## 9. Routing Dan Hop List

Direction request/downlink:

```text
Gateway/root -> parent -> child -> CH target
```

Direction response/uplink:

```text
CH target -> parent -> Gateway/root
```

Field routing kontrak phase awal:

| Field | Fungsi |
|---|---|
| `requestId` | korelasi response dengan request |
| `hopList[]` | daftar CH yang harus dilewati |

Aturan:

- `hopList[]` bersifat forward-only untuk request/downlink.
- Tidak ada field routing tambahan terpisah di payload phase awal.
- CH target adalah entry terakhir yang relevan di `hopList[]`; origin Gateway dibaca dari outer `AppFrame.srcId` atau route context.
- Response mengikuti parent aktif atau reverse route cache jika nanti ditambahkan.
- Phase awal boleh fixed tree/static parent.
- Dynamic route discovery menjadi phase lanjut.

---

## 10. Queue Priority

Prioritas TX MESH antar-CH:

1. Alarm push.
2. Alarm/recovery clear retry.
3. Response pull yang sudah dibangun.
4. Pending server node command/downlink.
5. CH status/hello/config.

Aturan:

- Queue penuh untuk alarm harus terdeteksi.
- Alarm tidak boleh hilang diam-diam.
- Normal response boleh dikoreksi oleh pull berikutnya.
- `sentSeq` NodeCache baru ditandai setelah TX success, bukan saat build/enqueue.

---

## 11. Reliability

Phase awal:

- CRC16 di `AppFrame`.
- Retry/ACK terutama untuk alarm path.
- Normal pull best-effort; jika gagal, server bisa pull ulang.

Phase lanjut:

- Per-hop ACK untuk MESH alarm/critical frames.
- Failover parent jika TX gagal berulang.
- Parent health score berdasarkan RSSI/SNR/success rate.
- Duplicate suppression untuk retry alarm.
- Route stale timeout.

---

## 12. Security Boundary

CH-CH tidak decrypt payload GLD.

Yang boleh dibaca CH parent:

- outer `AppFrame`,
- `GLDRecord.nodeId`,
- `GLDRecord.seq`,
- `GLDRecord.flags`,
- `payloadLen`.

Yang tidak boleh dibaca/diubah CH parent:

- plaintext `gasClass`,
- plaintext `confidence`,
- plaintext `batteryMv`,
- encrypted payload,
- AAD-relevant `GLDRecord` fields.

Server adalah endpoint decrypt phase 1.

---

## 13. Acceptance Criteria

### Current Direct Bench Baseline

Bench saat ini baru membuktikan direct CH-Gateway normal pull:

- CH menerima GLD STAR dan update `NodeCache`.
- Gateway mengirim `SERVER_PULL_REQUEST` langsung ke CH.
- CH mengirim `CLUSTER_DATA_RESPONSE` langsung ke Gateway.
- Server/Node-RED dapat decode response normal.

### Future CH-CH Acceptance

Kriteria di bawah ini adalah target acceptance untuk phase multi-hop CH-CH, bukan status bench saat ini.

CH-CH dianggap siap phase awal jika:

- CH child dapat menerima GLD STAR dan update `NodeCache`.
- CH child dapat menerima `SERVER_PULL_REQUEST` dari CH parent.
- CH child mengirim `CLUSTER_DATA_RESPONSE` ke CH parent.
- CH parent meneruskan response ke Gateway tanpa mengubah `GLDRecord`.
- Server dapat decrypt record dari CH target multi-hop.
- Alarm push satu `GLDRecord` dapat melewati CH parent sampai Gateway/server.
- Duplicate retry alarm tidak menjadi event baru di server.

Belum lulus/currently not proven:

- relay multi-hop `SERVER_PULL_REQUEST`,
- relay multi-hop `CLUSTER_DATA_RESPONSE`,
- alarm push multi-hop,
- `SERVER_NODE_COMMAND` sampai GLD.

---

## 14. Open Items

- Format final `CH_HELLO`.
- Format final parent discovery/failover.
- Reverse route cache atau static tree only.
- Per-hop ACK MESH untuk alarm.
- Persistent route/config storage di CH.
- Field LoRa frequency plan final.
- Live test multi-hop CH-CH belum dilakukan.
