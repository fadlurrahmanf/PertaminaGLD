# Pertamina GLD Final Design - Gateway Firmware

Status: current-state final design, 2026-06-25. This file describes the Gateway firmware and the current bench upload target.

## Source Of Truth

- Runtime env: `gateway_mqtt_mesh_esp32s3`.
- Current firmware version: Gateway `0.1.3`, protocol `0.1.0`.
- Main source path: `firmware/gateway/src/GatewayMqttMeshMain.cpp`.
- Config source: `firmware/config/GwConfig.h`, `ServerConfig.h`, `LoraMeshConfig.h`.

## Hardware

Gateway uses the MESH SX1262 radio on Radio B pins:

| Function | Pin |
|---|---:|
| SPI SCK/MOSI/MISO | GPIO12/GPIO11/GPIO13 |
| Radio B CS/BUSY/RXEN/TXEN/RST/DIO1 | GPIO14/GPIO38/GPIO39/GPIO40/GPIO41/GPIO42 |
| Status LED | GPIO19 |

Radio A pins are marked unused in Gateway firmware.

## Identity And Radio

Gateway ID is `0x006F`. It is the MESH root and final MQTT bridge. MESH radio uses 921.0 MHz, BW125, SF9, CR 4/5, sync `0x34`, 17 dBm TX power, preamble 8, and SPI 2 MHz.

## Site Network Config

Gateway uses the `server::site` config namespace. For the current upload request, source config is set to:

| Field | Value |
|---|---|
| WiFi SSID | `Fshares` |
| WiFi password | `kayabiasa` |
| MQTT host | `10.158.198.180` |
| MQTT port | `1884` |
| MQTT user/pass | `deviot` / `deviot` |
| topic root | `gld/gateway` |

Do not commit production secrets permanently. Move production credentials to provisioning/NVS/local ignored config before field release.

## MQTT Topics

| Topic | Direction | Purpose |
|---|---|---|
| `gld/gateway/uplink` | Gateway -> server | JSON wrapper for every received MESH frame |
| `gld/gateway/status` | Gateway -> server | alive/status JSON |
| `gld/gateway/topology` | Gateway -> server | topology reports from CH_HELLO and CH_CONFIG frames |
| `gld/gateway/cmd/#` | server -> Gateway | command subscription umbrella |
| `gld/gateway/cmd/pull` | server -> Gateway | build `MSG_SERVER_PULL_REQUEST` |
| `gld/gateway/cmd/node` | server -> Gateway | build `MSG_SERVER_NODE_COMMAND` |

Gateway connects MQTT with retry interval 3000 ms and publishes status every 10000 ms.

## Pull Command Builder

Pull command JSON accepts `requestId` or `id` and `hopList`. Gateway builds payload `requestId(2) + hopList[]`, sets `dstId` to the first hop, and transmits `MSG_SERVER_PULL_REQUEST` on MESH.

## Node Command Builder

Node command JSON expects `cluster`, `node`, optional `id`, optional `ttl`, and `hex`. Gateway builds `MSG_SERVER_NODE_COMMAND` toward the CH cluster. Current source payload includes `nodeId + commandId + ttlSec + commandLen + commandBytes`.

Known integration caveat: current CH source expects `nodeId + commandId + commandLen + commandBytes`. This mismatch must be fixed or tested before relying on Gateway-origin remote GLD mode switching.

## MESH Receive And Publish

For every received MESH frame, Gateway:

- Captures RSSI/SNR.
- Decodes AppFrame when possible.
- Publishes JSON to `gld/gateway/uplink`.
- Publishes topology events for CH_HELLO, CH_CONFIG_REQUEST, and CH_CONFIG_RESPONSE.
- Sends compact ACK for alarm sensor frames when needed.
- Sends Gateway CH_CONFIG_RESPONSE when it receives broadcast CH_CONFIG_REQUEST.

Gateway CH_CONFIG_RESPONSE payload contains requester ID, parent `0x0000`, depth 0, battery `0xFFFF`, route-to-root flag, and reverse RSSI/SNR. Gateway repeats the response twice with 70 ms gap.

## Upload Status

Gateway was built and uploaded successfully on 2026-06-25 to COM9 with server IP `10.158.198.180`. Verification log: `firmware/logs/codex-upload-gw-com9-20260625-145100.log`. Build size was RAM 17.5 percent and flash 12.1 percent. The upload ended with `SUCCESS` and hard reset via RTS.

## Post-12 Work

- Fix/align node command payload with CH.
- Move WiFi/MQTT credentials out of committed source for production.
- Add retained/heartbeat status fields that include firmware version, broker, root ID, and radio health.
- Soak-test Gateway as root under multi-hop CH traffic and repeated CH_CONFIG discovery.
