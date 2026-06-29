# Pertamina GLD Current Design - CH To CH Multi-Hop

Status: current source mirror, 2026-06-29.

## Source Files

| Area | Source |
|---|---|
| CH runtime | `firmware/ch/src/ChStarMeshRuntimeMain.cpp` |
| CH config | `firmware/config/ChConfig.h` |
| MESH config | `firmware/config/LoraMeshConfig.h` |
| Pull parser | `firmware/ch/src/ChPullRequest.cpp` |
| Cluster response | `firmware/ch/src/ClusterResponse.cpp` |
| Server topology decode | `server/nodered/functions/pertamina-gld-decode.js` |

## MESH Domain

CH-CH traffic uses Radio B and MESH AppFrame:

| Parameter | Value |
|---|---:|
| Frequency | 921.0 MHz |
| Bandwidth | 125 kHz |
| Spreading factor | SF9 |
| Coding rate | 4/5 |
| Sync word | `0x34` |
| TX power | 17 dBm |
| Preamble | 8 |
| SPI | 2 MHz |
| Max payload | 80 bytes |

## Routing Model

No static CH-CH route is compiled into firmware. Every CH starts with `DEFAULT_PARENT_ID=0x0000`, loads a cached parent from NVS if present, then uses CH_CONFIG discovery to find a parent toward root Gateway `0x006F`.

Parent candidate state:

| Field | Meaning |
|---|---|
| `id` | candidate CH/Gateway ID |
| `advertisedParent` | parent advertised by candidate |
| `batteryMv` | candidate battery |
| `rssiDbm`, `snrDb` | RSSI/SNR measured by local CH while receiving candidate response |
| `reverseRssiDbm`, `reverseSnrDb` | Gateway reverse link fields when candidate is Gateway |
| `depth` | advertised depth to root |
| `seenAtMs` | candidate timestamp |
| `hasReverseLink` | true only when Gateway response has reverse fields |

Selection:

- Primary score is RSSI.
- Tie breakers are lower depth, higher SNR, lower ID.
- Downstream/deeper candidates are rejected.
- Gateway requires bidirectional quality to become parent.
- Alternate parent is selected only when primary parent is not Gateway.
- Parent/alternate are saved to NVS only after the same pair appears for 4 stable scans.

## Discovery Messages

`MSG_CH_CONFIG_REQUEST`:

| Field | Value |
|---|---|
| `srcId` | requester CH |
| `dstId` | `0xFFFF` |
| `seq` | requester config sequence |
| payload | requester CH ID, 2 bytes |

`MSG_CH_CONFIG_RESPONSE` from a CH:

| Offset | Field |
|---:|---|
| 0..1 | requester ID |
| 2..3 | responder current parent |
| 4 | responder depth |
| 5..6 | responder battery mV |
| 7 | route-to-root flag, `0x01` |

Response anti-collision:

- Response slot is `CH_ID % 16`.
- Delay is `200 ms + slot * 280 ms`.
- Request interval is 5000 ms.

## Pull Downstream Relay

Gateway/server pull payload is `requestId:uint16BE + hopList:uint16BE[]`.

Intermediate CH behavior:

1. Decode AppFrame.
2. Verify `MSG_SERVER_PULL_REQUEST`.
3. Find local CH index in hopList.
4. If local CH is not final hop, set `dstId` to next hop.
5. Re-encode same payload with `srcId=local CH`, same AppFrame seq, same typeFlags.
6. Enqueue as `RelayFrame`.

Final CH behavior:

- If local CH is final hop, `handleServerPullRequestFrame()` builds `MSG_CLUSTER_DATA_RESPONSE`.
- Response goes to active parent `runtimeConfig.meshDstId`, not through a reverse hop list.

## Uplink Relay

A CH relays these local-destination MESH frames upstream to its active parent when `decoded.dstId == CH_ID` and `parentId != CH_ID`:

| Message | Relay condition |
|---|---|
| `MSG_CLUSTER_DATA_RESPONSE` | pull response from child path |
| `MSG_SENSOR_DATA` | alarm/recovery/data push from child path |
| `MSG_CH_HELLO` | topology hello from child path |

Relay re-encodes frame with `srcId=local CH`, `dstId=parentId`, same seq, same payload.

## Parent Health And Failover

Parent health fields:

| Field | Behavior |
|---|---|
| `lastParentSeenMs` | updated when current parent is heard as candidate |
| `lastParentRssiDbm`, `lastParentSnrDb` | latest parent quality |
| `PARENT_HEALTH_TIMEOUT_MS` | 180000 ms |
| `PARENT_MIN_DWELL_MS` | 300000 ms |
| `PARENT_SWITCH_MARGIN_DB` | 15 dB |

Failover triggers:

- Parent health timeout in JOINED.
- Alarm ACK failures reach threshold 3 and failover cooldown has elapsed.
- No-ACK burst reaches threshold 5, which enters RECOVERY.

Failover state sends CH_CONFIG_REQUEST every 5000 ms and evaluates candidates after 15000 ms. If no parent is selected, it repeats failover discovery.

## Topology Visibility

CH sends `MSG_CH_HELLO` to active parent:

- Immediately after first successful JOINED state with non-zero parent.
- Every 300000 ms after boot hello succeeds.
- Payload carries CH ID, parent, battery, uptime, depth, alternate parent.

Gateway publishes CH_CONFIG/HELLO topology events to MQTT. Node-RED stores installed parents, discovery candidates, gateway link quality, hellos, and computed routes.

## Current Source Caveat

Remote GLD mode switching through multi-hop uses `MSG_SERVER_NODE_COMMAND`. Current Gateway and CH payload layouts differ by a `ttlSec` field, so this path is not source-aligned until one side is changed.
