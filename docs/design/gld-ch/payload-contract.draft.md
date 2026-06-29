# Pertamina GLD Current Payload Contract - GLD, CH, Gateway, Server

Status: current source mirror, 2026-06-29.

## Source Files

| Area | Source |
|---|---|
| Protocol constants | `firmware/shared/include/ProtocolConstants.h` |
| AppFrame codec | `firmware/shared/include/AppFrame.h`, `firmware/shared/src/AppFrame.cpp` |
| GLD payload | `firmware/shared/include/GldPayload.h`, `firmware/shared/src/GldPayload.cpp` |
| GLD crypto | `firmware/shared/include/GldCrypto.h`, `firmware/shared/src/GldCrypto.cpp` |
| GLD record | `firmware/shared/include/GldRecord.h`, `firmware/shared/src/GldRecord.cpp` |
| GLD uplink builder | `firmware/gld/src/GldFrameBuilder.cpp` |
| CH runtime | `firmware/ch/src/ChRuntime.cpp`, `ClusterResponse.cpp`, `ChUplink.cpp` |
| Gateway/server decode | `server/nodered/functions/pertamina-gld-decode.js` |

All multibyte integers on wire are big-endian.

## AppFrame

| Offset | Field | Size | Source constant |
|---:|---|---:|---|
| 0 | magic `0xAA` | 1 | `APPFRAME_MAGIC` |
| 1 | typeFlags | 1 | message type plus flags |
| 2..3 | srcId | 2 | big-endian |
| 4..5 | dstId | 2 | big-endian |
| 6 | seq | 1 | sender sequence |
| 7 | payloadLen | 1 | max depends on link |
| 8.. | payload | N | 0..64 STAR, 0..80 MESH |
| final 2 | CRC16-CCITT-FALSE | 2 | over header + payload |

Constants:

| Constant | Value |
|---|---:|
| `APPFRAME_HEADER_SIZE` | 8 |
| `APPFRAME_CRC_SIZE` | 2 |
| `APPFRAME_OVERHEAD` | 10 |
| `STAR_MAX_PAYLOAD` | 64 |
| `MESH_MAX_PAYLOAD` | 80 |
| `MSG_TYPE_MASK` | `0x3F` |
| `FLAG_ALARM_ACK` | `0x40` |
| `FLAG_GLD_EXT_POWER` | `0x80` |

## Message Types

| Type | Name |
|---:|---|
| `0x10` | `MSG_SENSOR_DATA` |
| `0x14` | `MSG_NODE_DOWNLINK` |
| `0x30` | `MSG_SERVER_PULL_REQUEST` |
| `0x31` | `MSG_CLUSTER_DATA_RESPONSE` |
| `0x32` | `MSG_SERVER_NODE_COMMAND` |
| `0x33` | `MSG_CH_HELLO` |
| `0x34` | `MSG_CH_CONFIG_REQUEST` |
| `0x35` | `MSG_CH_CONFIG_RESPONSE` |

Derived GLD typeFlags:

| Name | Value |
|---|---:|
| normal battery | `0x10` |
| normal external | `0x90` |
| alarm battery | `0x50` |
| alarm external | `0xD0` |
| compact alarm ACK | `0x50` |

`messageType(typeFlags)` is `typeFlags & 0x3F`.

## Gas And Alarm

Protocol gas classes:

| Value | Name |
|---:|---|
| 0 | clearGas |
| 1 | LPG |
| 2 | propane |
| 3 | butane |
| 4 | methane |
| 5 | reserved |
| 6 | anomaly |

GLD current model-class mapping:

| Model class | Protocol gas value |
|---:|---:|
| 0 | 0 |
| 1 | 1 |
| 2 | 4 |
| 3 | 2 |
| 4 | 3 |
| other | 6 |

Alarm rule:

```text
alarm = gasClass != 0 && confidence >= 30
```

Confidence is valid only when `<=100`. Gas class is valid only when `<=6`.

## GLD Plain Payload

Plain payload is exactly 4 bytes:

| Offset | Field | Size |
|---:|---|---:|
| 0 | gasClass | 1 |
| 1 | confidence | 1 |
| 2..3 | batteryMv | 2 |

`batteryMv=0xFFFF` means invalid or unavailable.

## AES-GCM Payload

Encrypted payload is exactly 29 bytes:

| Offset | Field | Size |
|---:|---|---:|
| 0 | keyId | 1 |
| 1..12 | nonce | 12 |
| 13..16 | ciphertext | 4 |
| 17..28 | tag | 12 |

Crypto:

| Parameter | Value |
|---|---:|
| AES key size | 16 bytes |
| mode | AES-128-GCM |
| nonce length | 12 bytes |
| ciphertext length | 4 bytes |
| tag length | 12 bytes |

AAD is exactly 5 bytes:

| Offset | Field |
|---:|---|
| 0..1 | nodeId |
| 2 | GLD seq |
| 3 | GLDRecord flags |
| 4 | keyId |

GLD nonce provider in `GldUnifiedMain.cpp` copies the self-test nonce template, overwrites bytes 4..7 with `esp_random()`, overwrites bytes 8..11 with `txCounter`, then increments `txCounter`.

## GLDRecord

GLDRecord is the CH/server cache and response unit:

| Offset | Field | Size |
|---:|---|---:|
| 0..1 | nodeId | 2 |
| 2 | seq | 1 |
| 3 | flags | 1 |
| 4 | payloadLen | 1 |
| 5.. | encrypted payload | N |

Current phase:

| Field | Value |
|---|---:|
| encrypted payload length | 29 |
| record header size | 5 |
| full GLDRecord size | 34 |

Record flags:

| Flag | Value |
|---|---:|
| alarm | `0x01` |
| external power | `0x10` |

CH treats the encrypted payload as opaque bytes.

## GLD STAR Uplink

GLD sends AppFrame:

| Field | Value |
|---|---|
| typeFlags | `MSG_SENSOR_DATA` plus alarm/external flags |
| srcId | GLD node ID, current `0xF001` |
| dstId | CH ID, current `0x0064` |
| seq | GLD TX sequence |
| payload | 29-byte encrypted GLD payload |
| max payload | STAR 64 |

CH receives this and stores it as a GLDRecord in NodeCache. When CH sends to MESH, it wraps GLDRecord as payload.

## CH Single-Record Push

For alarm push and recovery clear, CH builds `MSG_SENSOR_DATA` on MESH:

| Field | Value |
|---|---|
| srcId | CH ID |
| dstId | active parent/Gateway |
| seq | CH MESH sequence |
| payload | one 34-byte GLDRecord |
| typeFlags | `MSG_SENSOR_DATA` plus alarm/external flags derived from NodeCache flags |

## Server Pull Request

Gateway/server builds `MSG_SERVER_PULL_REQUEST`:

| Offset | Field | Size |
|---:|---|---:|
| 0..1 | requestId | 2 |
| 2.. | hopList | 2 bytes per hop |

Gateway sets AppFrame `dstId` to first hop. Intermediate CH relays to next hop. Final CH handles the request.

## Cluster Data Response

Final CH builds `MSG_CLUSTER_DATA_RESPONSE`:

| Offset | Field | Size |
|---:|---|---:|
| 0..1 | requestId | 2 |
| 2 | data status | 1 |
| 3..4 | CH battery mV | 2 |
| 5 | record count | 1 |
| 6.. | GLDRecords | variable |

Data statuses:

| Value | Name |
|---:|---|
| `0x00` | DataOk |
| `0x01` | DataEmpty |
| `0x02` | DataNotAvail |
| `0x03` | DataStale |
| `0x04` | DataBusy |
| `0x05` | DataInvalid |

With MESH payload max 80 and current GLDRecord size 34, a response can carry at most two current GLDRecords:

```text
6 + (2 * 34) = 74 bytes
```

## CH_HELLO

CH_HELLO payload:

| Offset | Field | Size |
|---:|---|---:|
| 0..1 | CH ID | 2 |
| 2..3 | parent ID | 2 |
| 4..5 | battery mV | 2 |
| 6..7 | uptime seconds low 16 bits | 2 |
| 8 | mesh depth | 1 |
| 9..10 | alternate parent ID | 2 |

Gateway and Node-RED parse this as topology.

## CH_CONFIG

CH request payload:

| Offset | Field |
|---:|---|
| 0..1 | requester CH ID |

CH response payload:

| Offset | Field |
|---:|---|
| 0..1 | requester ID |
| 2..3 | responder parent ID |
| 4 | responder depth |
| 5..6 | responder battery mV |
| 7 | route-to-root flag |

Gateway response payload extends this to 10 bytes:

| Offset | Field |
|---:|---|
| 0..1 | requester ID |
| 2..3 | `0x0000` parent |
| 4 | depth 0 |
| 5..6 | `0xFFFF` battery |
| 7 | route-to-root flag `0x01` |
| 8 | Gateway RX RSSI int8 |
| 9 | Gateway RX SNR int8 |

## Node Downlink Command

GLD downlink over STAR uses:

| Field | Value |
|---|---|
| AppFrame type | `MSG_NODE_DOWNLINK (0x14)` |
| srcId | CH ID |
| dstId | target GLD |
| payload | command bytes |

GLD parser currently recognizes command payload byte 0 `0x01` as SET_MODE and byte 1 as mode `0|1|2`.

Current Gateway-to-CH command mismatch:

| Component | Wire layout |
|---|---|
| Gateway builder | `nodeId(2) + commandId(2) + ttlSec(2) + commandLen(1) + commandBytes` |
| CH parser | `nodeId(2) + commandId(2) + commandLen(1) + commandBytes` |

This mismatch is current source truth.
