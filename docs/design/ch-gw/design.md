# Pertamina GLD Current Design - CH To Gateway Boundary

Status: current source mirror, 2026-06-29.

## Source Files

| Area | Source |
|---|---|
| CH runtime | `firmware/ch/src/ChStarMeshRuntimeMain.cpp` |
| Gateway runtime | `firmware/gateway/src/GatewayMqttMeshMain.cpp` |
| Protocol constants | `firmware/shared/include/ProtocolConstants.h` |
| AppFrame codec | `firmware/shared/include/AppFrame.h`, `firmware/shared/src/AppFrame.cpp` |
| MESH config | `firmware/config/LoraMeshConfig.h` |

## AppFrame

All CH-Gateway MESH traffic uses AppFrame:

| Offset | Field | Size |
|---:|---|---:|
| 0 | magic `0xAA` | 1 |
| 1 | `typeFlags` | 1 |
| 2..3 | `srcId` big-endian | 2 |
| 4..5 | `dstId` big-endian | 2 |
| 6 | `seq` | 1 |
| 7 | `payloadLen` | 1 |
| 8.. | payload | 0..80 |
| final 2 | CRC16-CCITT-FALSE | 2 |

Constants:

| Constant | Value |
|---|---:|
| `APPFRAME_HEADER_SIZE` | 8 |
| `APPFRAME_CRC_SIZE` | 2 |
| `APPFRAME_OVERHEAD` | 10 |
| `MESH_MAX_PAYLOAD` | 80 |
| `MSG_TYPE_MASK` | `0x3F` |
| `FLAG_ALARM_ACK` | `0x40` |
| `FLAG_GLD_EXT_POWER` | `0x80` |

## Message Types

| Type | Name | Current use |
|---:|---|---|
| `0x10` | `MSG_SENSOR_DATA` | GLD record push, alarm push, recovery clear, compact ACK reuse |
| `0x30` | `MSG_SERVER_PULL_REQUEST` | Gateway/server pull request toward CH path |
| `0x31` | `MSG_CLUSTER_DATA_RESPONSE` | CH pull response toward Gateway |
| `0x32` | `MSG_SERVER_NODE_COMMAND` | Gateway command to CH pending downlink store |
| `0x33` | `MSG_CH_HELLO` | CH topology/liveness |
| `0x34` | `MSG_CH_CONFIG_REQUEST` | CH parent discovery broadcast |
| `0x35` | `MSG_CH_CONFIG_RESPONSE` | Gateway/CH parent candidate response |

## CH To Gateway Push

CH can send these upstream frames to active parent/Gateway:

| Frame | Payload |
|---|---|
| `MSG_SENSOR_DATA` alarm push | one GLDRecord |
| `MSG_SENSOR_DATA` recovery clear | one GLDRecord |
| `MSG_CLUSTER_DATA_RESPONSE` | response header plus up to two current 34-byte GLDRecords |
| `MSG_CH_HELLO` | 11-byte topology payload |

Gateway receives one MESH frame at a time with RadioLib `receive()`, captures RSSI/SNR, publishes it to MQTT, then handles config response and alarm ACK if applicable.

## Gateway MQTT Publish For MESH Frames

Every valid radio RX frame is wrapped by Gateway and published to `gld/gateway/uplink` when MQTT is connected.

Gateway uplink JSON fields:

| Field | Source |
|---|---|
| `source` | literal `gateway` |
| `gatewayId` | `0x006F` numeric |
| `frameHex` | raw MESH AppFrame hex |
| `frameLen` | raw frame length |
| `rssi`, `snr` | RadioLib RX metrics |
| `parseStatus` | AppFrame decode status enum value |
| `typeFlags`, `msgType`, `srcId`, `dstId`, `seq`, `payloadLen` | included when parse OK |
| `topology` | embedded only for valid `MSG_CH_HELLO` with payload length at least 8 |

Gateway also publishes topology JSON to `gld/gateway/topology` for `MSG_CH_HELLO`, `MSG_CH_CONFIG_REQUEST`, and `MSG_CH_CONFIG_RESPONSE`, unless the frame source is Gateway itself.

## Gateway Config Response

When Gateway receives a valid broadcast `MSG_CH_CONFIG_REQUEST` not from itself:

| Gateway response field | Value |
|---|---|
| AppFrame type | `MSG_CH_CONFIG_RESPONSE` |
| `srcId` | Gateway ID `0x006F` |
| `dstId` | requester ID |
| `seq` | request seq |
| payload 0..1 | requester ID |
| payload 2..3 | parent `0x0000` |
| payload 4 | depth `0` |
| payload 5..6 | battery `0xFFFF` |
| payload 7 | route-to-root flag `0x01` |
| payload 8 | Gateway RX RSSI clamped to int8 |
| payload 9 | Gateway RX SNR clamped to int8 |

Gateway waits 20 ms, then transmits the response `CONFIG_RESPONSE_REPEAT_COUNT=2` times with `CONFIG_RESPONSE_REPEAT_GAP_MS=70` ms between attempts.

## Alarm ACK

When Gateway receives an AppFrame that:

- decodes OK,
- has message type `MSG_SENSOR_DATA`,
- has `FLAG_ALARM_ACK`,

Gateway sends a compact ACK:

| Field | Value |
|---|---|
| typeFlags | `TYPE_ALARM_ACK_COMPACT = 0x50` |
| srcId | Gateway ID |
| dstId | received frame srcId |
| seq | received frame seq |
| payload | empty |

## Pull Boundary

Server publishes pull command JSON to Gateway. Gateway encodes:

| Field | Value |
|---|---|
| AppFrame type | `MSG_SERVER_PULL_REQUEST` |
| srcId | Gateway ID |
| dstId | first hop in hopList |
| seq | Gateway mesh sequence |
| payload | `requestId:uint16BE + hopList:uint16BE[]` |

Gateway accepts hop list fields named `hopList`, `hop_list`, or `hops`. If no array is supplied, it accepts `cluster` as a single-hop target.

## Node Command Boundary

Gateway accepts JSON fields:

| JSON field | Meaning |
|---|---|
| `cluster` | target CH |
| `node` | target GLD |
| `id` | command ID, default 1 |
| `ttl` | TTL seconds, default 600 |
| `hex` | command bytes as hex |

Current Gateway wire payload is:

```text
nodeId(2) + commandId(2) + ttlSec(2) + commandLen(1) + commandBytes
```

Current CH parser expects the same payload shape. `ttlSec` becomes the pending downlink expiry; `0` falls back to the CH default pending TTL.
