# Pertamina GLD Current Design - Gateway To Server Boundary

Status: current source mirror, 2026-06-29.

## Source Files

| Area | Source |
|---|---|
| Gateway firmware | `firmware/gateway/src/GatewayMqttMeshMain.cpp` |
| Gateway config | `firmware/config/GwConfig.h`, `firmware/config/ServerConfig.h` |
| Node-RED generator | `server/nodered/apply-pertamina-gld-flow.js` |
| Generated server flow | `server/nodered/pertamina-gld-server.flow.json` |
| Decode function | `server/nodered/functions/pertamina-gld-decode.js` |

## Broker Configs In Source

Firmware Gateway site config:

| Field | Value |
|---|---|
| MQTT host | `10.158.198.180` |
| MQTT port | `1884` |
| MQTT user/pass | `deviot` / `deviot` |
| topic root | `gld/gateway` |

Node-RED generator defaults:

| Field | Value |
|---|---|
| node-red URL | `http://127.0.0.1:1880` |
| node-red user dir | `C:\Users\asus\.node-red` |
| MQTT host | `127.0.0.1` unless CLI arg overrides |
| MQTT port | `1884` unless CLI arg overrides |
| MQTT user/pass | environment `MQTT_USER` / `MQTT_PASS` or empty |

Current generated `pertamina-gld-server.flow.json` contains broker node `pgl_mqtt_broker`; its checked-in broker host can differ from firmware source because the generator writes the snapshot using the CLI args used at generation time.

## Gateway To Server Topics

| Topic | Producer | Consumer | Payload |
|---|---|---|---|
| `gld/gateway/uplink` | Gateway | Node-RED | JSON wrapper around raw MESH frame |
| `gld/gateway/topology` | Gateway | Node-RED | topology JSON from CH control frames |
| `gld/gateway/status` | Gateway | Node-RED/operator | Gateway status JSON |
| `gld/gateway/cmd/pull` | Node-RED/server | Gateway | pull command JSON |
| `gld/gateway/cmd/node` | Node-RED/server | Gateway | node command JSON |
| `gld/server/cmd/node` | operator/server | Node-RED | high-level node command JSON before signing |

Node-RED also subscribes debug/compat inputs:

| Topic | Purpose |
|---|---|
| `gld/gateway/raw` | raw/debug AppFrame input |
| `pertamina/gld/uplink` | compatibility input |
| `gld/gateway/debug/http-pull` | debug path to build pull command |
| `gld/gateway/debug/http-node` | debug path to build node command |

## Gateway Uplink JSON

Gateway publishes:

| Field | Meaning |
|---|---|
| `source` | literal `gateway` |
| `gatewayId` | numeric Gateway ID |
| `frameHex` | full raw AppFrame as uppercase hex |
| `frameLen` | frame length |
| `rssi`, `snr` | radio metrics |
| `parseStatus` | AppFrame decode status enum |
| `typeFlags`, `msgType`, `srcId`, `dstId`, `seq`, `payloadLen` | only when AppFrame parse succeeds |
| `topology` | only for CH_HELLO payload length >=8 |

Node-RED decode accepts JSON fields `frameHex`, `appFrameHex`, `recordHex`, `payload_hex`, `payloadHex`, or `hex`; strings are parsed as JSON first, then as hex if JSON parse fails.

## Decode Outputs

Node-RED decode has four output groups in the generated flow:

| Output | Topic/path |
|---|---|
| gateway status | `gld/gateway/status` |
| gateway event envelopes/topology | `gld/gateway/events` or `gld/server/topology` |
| decoded GLD events | `gld/server/decoded` or `gld/server/alarm` |
| errors | `gld/gateway/error` |

GLD event fields include:

| Field | Meaning |
|---|---|
| `ok` | true for decoded event |
| `kind` | `gld-event` |
| `source` | `contract`, `gateway-status`, or direct source |
| `receivedAt` | ISO timestamp |
| `sourceTopic` | MQTT/input topic |
| `outer` | decoded AppFrame metadata |
| `nodeId`, `nodeIdHex` | GLD ID |
| `seq` | GLD record sequence |
| `flags` | GLDRecord flags |
| `alarm` | flag bit `0x01` |
| `externalPower` | flag bit `0x10` |
| `testDevice` | node ID in `0xF000..0xFEFF` |
| `payloadLen`, `payloadHex` | encrypted payload metadata |
| `dedupKey` | `<cluster>:<node>:<seq>:<alarm|normal>` |
| decrypt fields | `decryptOk`, key/nonce/AAD/plaintext/gas/confidence/battery validity fields |

## Pull Command Shape

Node-RED topology request endpoint and inject path publish:

```json
{"requestId":1,"hopList":["0x0064","0x0066"]}
```

Gateway accepts `requestId` or `id`, and `hopList`/`hop_list`/`hops`. It builds wire payload `requestId:uint16BE + hopList:uint16BE[]`.

## Node Command Shape

Node-RED/Gateway command topic accepts:

```json
{"cluster":"0x0064","node":"0xF001","id":1,"ttl":600,"mode":"dataset"}
```

Gateway encodes and CH parses the same wire payload:

```text
nodeId:uint16BE + commandId:uint16BE + ttlSec:uint16BE + commandLen:uint8 + commandBytes
```

`ttlSec` controls the CH pending-downlink expiry; `0` falls back to the CH default pending TTL.
The Node-RED `build authenticated node command` function subscribes to
`gld/server/cmd/node`, converts `mode` into
`commandBytes = 0x81 + mode + commandId + cmacTag4` using
`GLD_AES128_KEY_HEX`, then publishes the signed command to
`gld/gateway/cmd/node`.

## Topology Boundary

Gateway publishes topology reports from:

- `MSG_CH_HELLO`
- `MSG_CH_CONFIG_REQUEST`
- `MSG_CH_CONFIG_RESPONSE`

Node-RED stores topology in flow context key `pglTopology`.

Tracked maps:

| Map | Meaning |
|---|---|
| `parents` | installed CH parent reports |
| `discovery` | pending CH_CONFIG candidates |
| `gatewayLinks` | Gateway-heard RSSI/SNR for CH_CONFIG request |
| `hellos` | latest CH_HELLO per CH |
| `routes` | computed Gateway-to-CH hop lists |

TTL defaults:

| State | Default |
|---|---:|
| installed parent/route | 900000 ms |
| discovery candidate | 420000 ms |
| Gateway-link RSSI | 420000 ms |

## HTTP Endpoints

Generated Node-RED endpoints:

| Endpoint | Behavior |
|---|---|
| `POST /pertamina-gld/decode` | manual decode |
| `GET /pertamina-gld/topology` | topology JSON |
| `GET /pertamina-gld/topology/view` | HTML topology UI |
| `POST /pertamina-gld/topology/reset` | reset topology state |
| `POST /pertamina-gld/topology/request?ch=<id>` | publish pull request if installed route exists |
| `POST /pertamina-gld/topology/delete?ch=<id>` | remove selected CH from topology maps |
