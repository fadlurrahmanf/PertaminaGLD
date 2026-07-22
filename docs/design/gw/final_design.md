# Pertamina GLD Current Design - Gateway Firmware

Status: current source mirror, 2026-06-29.

## Source Files

| Area | Source |
|---|---|
| PlatformIO env | `firmware/platformio.ini` |
| Main runtime | `firmware/gateway/src/GatewayMqttMeshMain.cpp` |
| Gateway config | `firmware/config/GwConfig.h` |
| Server config | `firmware/config/ServerConfig.h` |
| MESH config | `firmware/config/LoraMeshConfig.h` |
| Pins | `firmware/gateway/include/GatewayBoardPins.h` |
| Protocol | `firmware/shared/include/ProtocolConstants.h`, `AppFrame.h` |

## Active Build Environment

| Env | Board | Source set |
|---|---|---|
| `gw` | `4d_systems_esp32s3_gen4_r8n16` | shared `AppFrame.cpp`, `gateway/src/GatewayMqttMeshMain.cpp` |

The env excludes GLD source, CH source, docs, tests, and versions.

Firmware identifiers:

| Field | Value |
|---|---|
| firmware name | `PertaminaGLD-Gateway` |
| firmware version | `0.1.3` |
| protocol version | `0.1.0` |
| config schema version | `0.1.0` |

## Hardware Pins

| Function | Pin/value |
|---|---|
| SPI SCK/MOSI/MISO | GPIO12/GPIO11/GPIO13 |
| unused Radio A TXEN/RXEN/RST/CS | GPIO5/GPIO6/GPIO7/GPIO17 |
| Radio B CS/BUSY/RXEN/TXEN/RST/DIO1 | GPIO14/GPIO38/GPIO39/GPIO40/GPIO41/GPIO42 |
| Status LED | GPIO19 |

`setupPinsSafe()` sets status LED LOW, unused Radio A CS HIGH, unused Radio A RST LOW, unused Radio A RXEN/TXEN LOW, Radio B CS HIGH, Radio B RST LOW, Radio B RXEN/TXEN LOW.

## Identity And Network Config

| Config | Value |
|---|---|
| Gateway ID | `0x006F` |
| WiFi SSID | deployment-provisioned (`CHANGE_ME_WIFI_SSID`) |
| WiFi password | deployment secret (`CHANGE_ME_WIFI_PASSWORD`) |
| MQTT host | deployment-provisioned (`CHANGE_ME_MQTT_HOST`) |
| MQTT port | `1884` |
| MQTT user/pass | deployment secrets (`CHANGE_ME_MQTT_USER` / `CHANGE_ME_MQTT_PASSWORD`) |
| topic root | `gld/gateway` |
| WiFi retry | `5000 ms` |
| MQTT retry | `3000 ms` |
| status interval | `10000 ms` |
| MQTT buffer | `1024 bytes` |

MQTT client ID is generated as `pgl-gateway-%04X-%08lX` using Gateway ID and ESP efuse MAC low formatting.

## MESH Radio

| Parameter | Value |
|---|---:|
| Frequency | 921.0 MHz |
| Bandwidth | 125 kHz |
| Spreading factor | SF9 |
| Coding rate | 4/5 |
| Sync word | `0x34` |
| TX power | 17 dBm |
| Preamble | 8 |
| SPI clock | 2 MHz |
| TCXO first attempt | 1.6 V |
| XTAL fallback | 0.0 V |

`beginMeshRadio()` starts SPI, toggles Radio B reset LOW 50 ms then HIGH 500 ms, creates SX1262 on Radio B pins, starts RadioLib, falls back to 0.0 V only for SPI command failure, then sets RF switch pins.

## MQTT Topics

| Topic | Direction | Runtime use |
|---|---|---|
| `gld/gateway/uplink` | Gateway to server | JSON wrapper for every received MESH frame |
| `gld/gateway/status` | Gateway to server | periodic Gateway status JSON |
| `gld/gateway/topology` | Gateway to server | CH_HELLO, CH_CONFIG_REQUEST, CH_CONFIG_RESPONSE topology JSON |
| `gld/gateway/cmd/#` | server to Gateway | wildcard subscription |
| `gld/gateway/cmd/pull` | server to Gateway | build `MSG_SERVER_PULL_REQUEST` |
| `gld/gateway/cmd/node` | server to Gateway | build `MSG_SERVER_NODE_COMMAND` |

Gateway subscribes all three command subscriptions after MQTT connect: wildcard, pull exact, and node exact. In callback, any topic equal to pull topic or containing `/pull` is handled as pull; any topic equal to node topic or containing `/node` is handled as node command.

## Status Publish

Status JSON to `gld/gateway/status`:

| Field | Value |
|---|---|
| `kind` | `gateway-status` |
| `gatewayId` | numeric Gateway ID |
| `state` | currently `alive` for periodic status |
| `wifi` | WiFi connected boolean |
| `mqtt` | MQTT connected boolean |
| `meshReady` | MESH radio ready boolean |
| `ip` | local IP string when WiFi connected |

## Pull Command Builder

Accepted pull JSON:

| Field | Behavior |
|---|---|
| `hopList`, `hop_list`, or `hops` | array of numeric or string IDs |
| `cluster` | fallback single-hop target if no hop list array exists |
| `requestId` | request ID |
| `id` | fallback request ID |

If no request ID is supplied, Gateway uses a local `requestId` counter starting at 1 and increments it.

Wire payload:

```text
requestId:uint16BE + hopList:uint16BE[]
```

Frame:

| Field | Value |
|---|---|
| type | `MSG_SERVER_PULL_REQUEST` |
| srcId | Gateway ID |
| dstId | first hop |
| seq | Gateway `meshSeq++` |

## Node Command Builder

Accepted node command JSON:

| Field | Behavior |
|---|---|
| `cluster` | direct legacy target CH; with a route it must equal the final hop if supplied |
| `hopList`, `hop_list`, or `hops` | optional explicit Gateway-to-target-CH route; selects routed v1 |
| `node` | required target GLD |
| `id` | command ID, default 1 |
| `ttl` | TTL seconds, default 600 |
| `hex` | command bytes; non-hex chars ignored by parser |

Command length is limited to 8 bytes, matching the CH pending-downlink store
and the authenticated GLD mode command. Gateway rejects longer input; it does
not silently truncate it.

Without an explicit hop list, the backward-compatible direct wire payload is:

```text
nodeId:uint16BE + commandId:uint16BE + ttlSec:uint16BE + commandLen:uint8 + commandBytes
```

With an explicit hop list, Gateway prepends routed v1 metadata and the complete
legacy body:

```text
magic(0xC1) + version(1) + hopCount + reserved(3) + legacyGuard(0xFF)
+ hopList:uint16BE[]
+ nodeId + commandId + ttlSec + commandLen + commandBytes
```

Frame type is `MSG_SERVER_NODE_COMMAND`, source Gateway, destination
`hopList[0]` for routed v1 or `cluster` for direct legacy, and seq is
`meshSeq++`. The final hop is the target CH; if `cluster` is also supplied it
must match that final hop. Hop IDs must be unique, non-zero, and non-broadcast.
At the maximum 8-byte command length, the 80-byte MESH payload permits 29 hops.

CH parses the same payload shape and stores `ttlSec` as the pending downlink expiry. A `ttlSec` of `0` uses the CH default pending TTL.
Direct legacy delivery works with old and new CH firmware. Routed v1 must be
used only when every listed CH advertises capability flag `0x08`; an old CH
rejects the guard as an invalid legacy command length.

## MESH Receive

Loop order:

1. `ensureWifi()`.
2. `ensureMqtt()`.
3. `mqtt.loop()`.
4. `publishStatusPeriodic()`.
5. If MESH ready, `receiveMeshOnce()`.

For each successful RX:

1. Read raw frame.
2. Capture packet length, RSSI, SNR.
3. Publish raw wrapper to MQTT.
4. If frame is CH_CONFIG_REQUEST, send Gateway config response.
5. If frame is alarm `MSG_SENSOR_DATA`, send compact ACK.

## Uplink JSON

Gateway publishes `gld/gateway/uplink` with:

| Field | Included when |
|---|---|
| `source="gateway"` | always |
| `gatewayId` | always |
| `frameHex` | always |
| `frameLen` | always |
| `rssi`, `snr` | always |
| `parseStatus` | always |
| `typeFlags`, `msgType`, `srcId`, `dstId`, `seq`, `payloadLen` | AppFrame parse OK |
| `topology` object | parse OK and msg type is CH_HELLO with payload length >= 8 |

Topology object inside uplink contains cluster ID, parent ID, optional parentAlt ID, battery, uptime, mesh depth, parentIsRoot, viaHop, Gateway ID, RSSI, SNR.

## Topology Publish

Gateway publishes separate topology JSON to `gld/gateway/topology` for:

- `MSG_CH_HELLO`
- `MSG_CH_CONFIG_REQUEST`
- `MSG_CH_CONFIG_RESPONSE`

Common fields: `kind`, `source`, `gatewayId`, `rootId`, `msgType`, `typeFlags`, `srcId`, `dstId`, `seq`, `payloadLen`, `rssi`, `snr`, hex ID variants.

Report-specific fields:

| Report | Fields |
|---|---|
| `ch-hello` | `chId`, `parentId`, `parentAltId`, `edgeFrom`, `edgeTo`, `batteryMv`, `uptimeSec16`, `parentIsRoot` |
| `ch-config-response` | `chId`, `requesterId`, `parentId`, `edgeFrom`, `edgeTo`, `depth`, `batteryMv`, `routeFlags`, `routeToRoot`, `helloAckV1`, `alarmAckNodeIdV1`, `nodeCommandRouteV1`, `parentIsRoot` |
| `ch-config-request` | `chId`, `requesterId` |

## Gateway Responses

Gateway CH_CONFIG_RESPONSE payload:

| Offset | Field |
|---:|---|
| 0..1 | requester ID |
| 2..3 | parent `0x0000` |
| 4 | depth 0 |
| 5..6 | battery `0xFFFF` |
| 7 | capability bitfield `0x0F`: route-to-root `0x01`, HELLO ACK v1 `0x02`, alarm ACK node ID v1 `0x04`, node-command route v1 `0x08` |
| 8 | Gateway RX RSSI as int8 |
| 9 | Gateway RX SNR as int8 |

Gateway alarm compact ACK:

| Field | Value |
|---|---|
| typeFlags | `0x50` |
| srcId | Gateway ID |
| dstId | source CH of received alarm frame |
| seq | same seq as received alarm frame |
| payload | empty |
