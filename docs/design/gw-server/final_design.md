# Pertamina GLD Final Design - Gateway To Server Boundary

Status: current-state final design, 2026-06-25. This file defines the MQTT contract between Gateway firmware and the Node-RED/server layer.

## Source Of Truth

- Gateway firmware: `firmware/gateway/src/GatewayMqttMeshMain.cpp`.
- Gateway config: `firmware/config/GwConfig.h`, `ServerConfig.h`.
- Node-RED flow generator: `server/nodered/apply-pertamina-gld-flow.js`.
- Decode function: `server/nodered/functions/pertamina-gld-decode.js`.

## Broker And Topics

Current Gateway/site source config points to `10.158.198.180:1884` with topic root `gld/gateway`.

| Topic | Producer | Consumer | Payload |
|---|---|---|---|
| `gld/gateway/uplink` | Gateway | Node-RED | JSON wrapper with frameHex, RSSI/SNR, parse metadata |
| `gld/gateway/topology` | Gateway | Node-RED | JSON topology object/event |
| `gld/gateway/status` | Gateway | Node-RED/operator | Gateway alive/status JSON |
| `gld/gateway/cmd/pull` | Node-RED/server | Gateway | pull command JSON |
| `gld/gateway/cmd/node` | Node-RED/server | Gateway | node command JSON |

## Uplink JSON Shape

Gateway uplink JSON includes:

- `source="gateway"`
- `gatewayId`
- `frameHex`
- `frameLen`
- `rssi`
- `snr`
- `parseStatus`
- decoded `typeFlags`, `msgType`, `srcId`, `dstId`, `seq`, `payloadLen`, `payloadHex` when parse succeeds
- embedded topology object for CH_HELLO when applicable

Node-RED decodes AppFrame, validates CRC, decrypts 29-byte GLD encrypted payloads using AES-GCM, and emits GLD events. Non-data MESH control frames are treated as control/topology frames, not decode failures.

## Pull Command Shape

Server publishes:

```json
{"requestId":1,"hopList":["0x0064","0x0066"]}
```

Gateway builds `MSG_SERVER_PULL_REQUEST` with `requestId + hopList[]`, sends to the first hop, and CH relays through the path. Node-RED uses the same installed topology route when the topology UI Request button is pressed.

## Node Command Shape

Server publishes:

```json
{"cluster":"0x0064","node":"0xF001","id":1,"ttl":600,"hex":"0101"}
```

Current Gateway includes TTL in the wire payload. Current CH parser does not consume TTL in that position. This is a known compatibility caveat and must be corrected before operator-facing node commands are treated as fully final.

## Topology Boundary

Gateway publishes CH topology reports from:

- `MSG_CH_HELLO`
- `MSG_CH_CONFIG_REQUEST`
- `MSG_CH_CONFIG_RESPONSE`

Node-RED stores installed parents, discovery candidates, Gateway-link RSSI, CH_HELLO ages, and computed routes. Installed topology TTL is 900000 ms. Discovery and Gateway-link TTL are 420000 ms.

## Server Expectations

Node-RED expects:

- MQTT broker reachable on configured host/port.
- AES key in env `GLD_AES128_KEY_HEX` or default test key for bench decode.
- Gateway ID default `0x006F`, overridable by `PGL_GATEWAY_ID` or `GATEWAY_ID`.
- Pull response only fully decoded when final `MSG_CLUSTER_DATA_RESPONSE` arrives at Gateway.

## Post-12 Work

- Formalize this boundary into a versioned contract file after node command TTL mismatch is fixed.
- Add broker/auth provisioning model for production.
- Add integration tests that publish representative Gateway JSON and verify Node-RED emitted GLD event/topology/pull output.
- Add operator-safe error messages for unknown AES key, bad CRC, stale topology, and missing route.
