# CH-Gateway Design

**Status:** draft implementasi phase 1 + bench-proven direct path  
**Tanggal:** 2026-06-18  
**Scope:** komunikasi CH ke Gateway melalui Radio B / MESH  
**Sumber utama:** `docs/design/ch/design.updated.draft.md`, `docs/design/gld-ch/payload-contract.draft.md`, firmware CH/Gateway saat ini  
**Catatan:** desain ini tidak mengubah `docs/design/ch/design.md` original.

---

## 1. Ringkasan

CH-Gateway adalah boundary antara jaringan LoRa MESH dan server-side LAN/MQTT. CH mengirim data ke Gateway melalui Radio B, lalu Gateway mem-publish frame tersebut ke server lewat MQTT.

Status saat ini:

- Direct CH -> Gateway sudah live-tested.
- Normal server pull sudah terbukti end-to-end:

```text
GLD -> CH cache -> Gateway pull -> CH response -> Gateway MQTT -> Node-RED decode
```

Komponen aktif bench:

| Komponen | Port | Firmware/env |
|---|---|---|
| CH | `COM3` | `ch_star_mesh_runtime_esp32s3`, CH `v0.5.2` |
| Gateway | `COM38` | `gateway_mqtt_mesh_esp32s3`, Gateway `v0.1.2` |

---

## 2. Peran CH

CH bertugas:

- menerima GLD frame dari STAR Radio A,
- menyimpan latest opaque payload di `NodeCache`,
- menerima request dari Gateway melalui MESH Radio B,
- membangun `CLUSTER_DATA_RESPONSE` dari cache,
- meneruskan alarm push/recovery clear tanpa menunggu pull,
- menjaga payload GLD tetap opaque.

CH tidak bertugas:

- decrypt payload GLD,
- parse `gasClass`, `confidence`, atau `batteryMv`,
- menjalankan storage server,
- menjadi broker MQTT.

---

## 3. Peran Gateway

Gateway bertugas:

- menjadi MESH root untuk CH,
- menerima `CLUSTER_DATA_RESPONSE`, alarm push, dan recovery clear dari CH,
- publish frame MESH ke server via MQTT,
- menerima command MQTT dari server dan meneruskannya ke CH target via MESH,
- publish status koneksi gateway.

Gateway tidak bertugas:

- decrypt payload GLD,
- menyimpan event jangka panjang,
- menentukan alarm dari plaintext GLD.

---

## 4. Link MESH CH-Gateway

Parameter bench saat ini:

| Parameter | Nilai |
|---|---:|
| Frequency | `921.0 MHz` |
| Bandwidth | `125 kHz` |
| Spreading Factor | `SF9` |
| Coding Rate | `4/5` |
| Sync Word | `0x34` |
| Max payload | `80 byte` |

Aturan:

- Link memakai `AppFrame`.
- `srcId` dan `dstId` adalah ID CH/Gateway untuk hop MESH.
- `GLDRecord.nodeId` menyimpan identitas GLD asli.
- Gateway mem-publish frame MESH lengkap sebagai hex ke server.

---

## 5. ID Bench Saat Ini

| Entity | ID |
|---|---:|
| Gateway | `0x006F` |
| CH | `0x0064` |
| GLD test/manual | `0xF001` |

Catatan:

- `0xF001` berada di reserved range test/manual.
- Production GLD harus memakai range `0x0001..0xEFFF`.

---

## 6. Server Pull Flow

Flow normal:

```text
Server/Node-RED
  -> MQTT gld/gateway/cmd/pull
  -> Gateway
  -> MESH SERVER_PULL_REQUEST
  -> CH target
  -> MESH CLUSTER_DATA_RESPONSE
  -> Gateway
  -> MQTT gld/gateway/uplink
  -> Node-RED decode
```

Gateway command input:

```json
{"requestId":1,"hopList":["0x0064"]}
```

MQTT topic:

```text
gld/gateway/cmd/pull
```

Gateway builds:

```text
msgType = SERVER_PULL_REQUEST (0x30)
srcId = Gateway ID
dstId = CH ID
payload = requestId:uint16BE + chId:uint16BE
```

Catatan:

- Gateway command pull memakai `hopList[]`, bukan `nodeId`.
- Untuk direct CH-Gateway bench, `hopList=["0x0064"]`.
- Gateway membangun payload binary `requestId:uint16BE + hopList:uint16BE[]`.
- `node` tidak dipakai pada pull karena CH-level pull membaca seluruh latest cache normal `unsent`, bukan request langsung ke GLD tertentu.

CH response:

```text
msgType = CLUSTER_DATA_RESPONSE (0x31)
srcId = CH ID
dstId = Gateway ID
payload = response header + repeated GLDRecord
```

Response header:

| Field | Size |
|---|---:|
| `requestId` | 2 |
| `status` | 1 |
| `chBatteryMv` | 2 |
| `recordCount` | 1 |

Bench verified:

```text
GW_MESH_TX reason=server-pull state=0 len=14
CH_MESH_RX state=0 len=14
CH_PULL_PROCESS status=Ok onwardQueued=1 pullStatus=0 txStatus=0
CH_MESH_TX state=0 len=50
GW_MESH_RX state=0 len=50
GW_MQTT_PUBLISH topic=gld/gateway/uplink ok=1 frameLen=50
```

---

## 7. Alarm Push Flow

Alarm dari CH ke Gateway:

```text
msgType = SENSOR_DATA (0x10)
FLAG_ALARM_ACK = 1
payload = exactly one GLDRecord
```

Aturan:

- Alarm push tidak memakai `CLUSTER_DATA_RESPONSE`.
- Gateway mem-publish alarm push ke `gld/gateway/uplink`.
- Node-RED mendecode dan mengarahkan alarm ke `gld/server/alarm`.
- Gateway boleh mengirim compact ACK ke CH jika frame alarm MESH meminta ACK.

Status:

- Code path alarm ada di CH/Gateway.
- Live test alarm push dengan GLD alarm asli belum dilakukan.
- Bagian ini adalah expected path yang harus diuji; jangan dianggap sudah lulus bench sampai `gld/server/alarm` muncul dari frame alarm GLD asli.

---

## 8. Recovery Clear Flow

Recovery clear:

```text
msgType = SENSOR_DATA (0x10)
FLAG_ALARM_ACK = 0
payload = exactly one GLDRecord
GLDRecord.flags alarm bit = 0
```

Aturan:

- Recovery clear bukan pull response.
- Gateway mem-publish seperti uplink biasa.
- Server memakai recovery clear untuk menutup alarm aktif.
- Recovery clear live path belum divalidasi end-to-end; phase 1 tetap dapat direkonsiliasi oleh normal pull berikutnya.

---

## 9. Gateway MQTT Publish Shape

Gateway publish `gld/gateway/uplink` dengan JSON:

| Field | Arti |
|---|---|
| `source` | `"gateway"` |
| `gatewayId` | Gateway ID decimal |
| `frameHex` | AppFrame MESH lengkap dalam hex |
| `frameLen` | panjang frame |
| `rssi` | RSSI MESH |
| `snr` | SNR MESH |
| `parseStatus` | status parse AppFrame di Gateway |
| `typeFlags` | jika parse OK |
| `msgType` | jika parse OK |
| `srcId` | jika parse OK |
| `dstId` | jika parse OK |
| `seq` | jika parse OK |
| `payloadLen` | jika parse OK |

Server harus memperlakukan `frameHex` sebagai source utama untuk decode kontrak.

---

## 10. Error Handling

CH:

- Jika `SERVER_PULL_REQUEST` salah hop, CH menolak.
- Jika tidak ada payload valid, CH mengirim response status `DataNotAvail`.
- Jika semua payload valid sudah stale, CH mengirim response status `DataStale`.
- Jika ada payload valid non-stale tetapi tidak ada record normal unsent, CH mengirim response status `DataEmpty`.
- `sentSeq` hanya ditandai setelah TX MESH lokal success; ini bukan bukti Gateway publish, server receive, atau decrypt server berhasil.
- CH pull parser saat ini memvalidasi `hopList[0]`; production harus memvalidasi juga `decoded.dstId == localChId`.

Gateway:

- Jika MQTT down, Gateway tetap mencoba reconnect.
- Jika MESH TX gagal, Gateway log `GW_MESH_TX ... state != 0`.
- Jika frame MESH parse gagal, Gateway tetap dapat publish `frameHex` dengan `parseStatus` non-zero untuk debug.

Server:

- Jika `recordCount=0`, current Node-RED tidak menghasilkan decoded event; response kosong dapat ditampilkan nanti bila flow ditambah branch eksplisit.
- Jika decrypt gagal, publish ke error/debug route.

---

## 11. Functional Monitor

CH serial yang diharapkan:

```text
CH_CACHE_SUMMARY reason=...
CH_CACHE_ENTRY index=... node=0xF001 ...
CH_MESH_RX state=0 len=14
CH_PULL_PROCESS status=Ok ...
CH_MESH_TX state=0 len=50
```

Gateway serial yang diharapkan:

```text
GW_MQTT_CONNECT host=... port=1884 ok=1
GW_MQTT_CMD topic=gld/gateway/cmd/pull
GW_MESH_TX reason=server-pull state=0 len=14
GW_MESH_RX state=0 len=50
GW_MQTT_PUBLISH topic=gld/gateway/uplink ok=1
```

---

## 12. Acceptance Criteria

CH-Gateway direct path normal pull bench dianggap OK jika:

- Gateway MQTT connected.
- Gateway menerima pull command.
- Gateway mengirim `SERVER_PULL_REQUEST` ke CH target.
- CH menerima request dan membangun response dari cache.
- `CLUSTER_DATA_RESPONSE.status == DataOk`.
- `recordCount > 0`.
- `payloadLen <= 80`.
- Gateway menerima MESH response.
- Gateway publish `gld/gateway/uplink`.
- Node-RED menghasilkan `gld/server/decoded` dengan `decryptOk=true`.

Acceptance bench terbaru sudah memenuhi normal pull.

Alarm push dan recovery clear belum masuk acceptance lulus; keduanya masih open test.

---

## 13. Open Items

- Live test alarm push.
- Multi-hop `hopList[]` CH-CH belum live-tested.
- Gateway persistent config untuk WiFi/MQTT/IDs, tidak hardcoded produksi.
- Gateway non-blocking MESH receive seperti CH jika traffic makin ramai.
- Gateway offline buffer jika MQTT/server down.
- Per-hop ACK/retry untuk alarm MESH.
- Production security untuk MQTT credentials.
