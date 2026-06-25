# Pertamina GLD Final Design - CH To Gateway Boundary

Status: current-state final design, 2026-06-25. This file defines the CH-Gateway MESH boundary used by the current firmware.

## Source Of Truth

- CH source: `firmware/ch/src/ChStarMeshRuntimeMain.cpp`.
- Gateway source: `firmware/gateway/src/GatewayMqttMeshMain.cpp`.
- Protocol source: `firmware/shared/include/ProtocolConstants.h`, `AppFrame.h`.
- MESH radio config: `firmware/config/LoraMeshConfig.h`.

## AppFrame

All CH-Gateway traffic uses AppFrame:

| Field | Size |
|---|---:|
| magic `0xAA` | 1 |
| typeFlags | 1 |
| srcId | 2 |
| dstId | 2 |
| seq | 1 |
| payloadLen | 1 |
| payload | 0..80 |
| crc16 | 2 |

`MSG_TYPE_MASK=0x3F`; `FLAG_ALARM_ACK=0x40`; `FLAG_GLD_EXT_POWER=0x80`. MESH max payload is 80 bytes.

## Message Types

| Type | Direction | Purpose |
|---:|---|---|
| `0x10 MSG_SENSOR_DATA` | CH -> Gateway/root, or CH relay | GLD event push, alarm push, compact ACK reuse |
| `0x30 MSG_SERVER_PULL_REQUEST` | Gateway -> CH path | Server pull request with requestId and hopList |
| `0x31 MSG_CLUSTER_DATA_RESPONSE` | CH -> Gateway path | Pull response carrying cache records |
| `0x32 MSG_SERVER_NODE_COMMAND` | Gateway -> CH | Store pending GLD downlink |
| `0x33 MSG_CH_HELLO` | CH -> parent/Gateway | Installed topology and liveness |
| `0x34 MSG_CH_CONFIG_REQUEST` | CH -> broadcast | Parent discovery |
| `0x35 MSG_CH_CONFIG_RESPONSE` | Gateway/CH -> requester | Parent candidate response |

## Uplink Push

CH converts GLD STAR records into MESH frames. Alarm frames stay queued until a compact ACK is received from the parent/Gateway. Normal records are cached and can also be returned later by pull.

Gateway publishes every received MESH frame to MQTT `gld/gateway/uplink` as JSON containing `frameHex`, `frameLen`, RSSI, SNR, parse status, and decoded AppFrame metadata when parse succeeds.

## Pull Request Flow

Server/Gateway sends `MSG_SERVER_PULL_REQUEST`:

| Payload field | Size |
|---|---:|
| requestId | 2 |
| hopList[0..n] | 2 each |

The AppFrame `dstId` is the next hop. A relay CH rebuilds the AppFrame with itself as `srcId`, next hop as `dstId`, same `seq`, and the same payload. The final CH builds `MSG_CLUSTER_DATA_RESPONSE`.

Response route follows active parent routing, not a reverse hop list inside the payload. `requestId` is used to match request/response; AppFrame `seq` remains sender sequence.

## Topology And Discovery Boundary

CH_CONFIG request/response is the discovery boundary:

- Requester broadcasts `MSG_CH_CONFIG_REQUEST`.
- Gateway responds with root depth 0, battery unknown `0xFFFF`, route-to-root flag, and reverse RSSI/SNR.
- Joined CH nodes respond only when they have a route to root.
- CH selects parent and alternate locally; Gateway does not assign parent.

Gateway also publishes topology events to MQTT `gld/gateway/topology`, including CH_HELLO, CH_CONFIG_REQUEST, and CH_CONFIG_RESPONSE derived topology reports.

## Failure Modes

- If CH hears no valid candidate during JOINING, it keeps no parent and retries discovery.
- If parent health timeout reaches 180000 ms, CH enters failover and re-discovers.
- Weak Gateway candidates are rejected when CH-side or reverse RSSI is below configured floor.
- Pending CH_CONFIG discovery can collide in RF; current anti-collision uses deterministic slots, and Gateway repeats root response twice.
- Gateway-to-CH node command has a known TTL payload mismatch with current CH parser; remote GLD mode commands must be retested after this is fixed.

## Post-12 Work

- Run multi-CH discovery soak tests and record parent/alternate stability.
- Add stronger diagnostics for every rejected parent candidate.
- Fix and verify `SERVER_NODE_COMMAND` payload alignment end-to-end.
- Validate pull and alarm ACK behavior through multi-hop routes under packet loss.
