# Pertamina GLD Current Design - Server And Node-RED

Status: current source mirror, 2026-06-29.

## Source Files

| Area | Source |
|---|---|
| Server flow generator | `server/nodered/apply-pertamina-gld-flow.js` |
| Generated flow snapshot | `server/nodered/pertamina-gld-server.flow.json` |
| Decode function | `server/nodered/functions/pertamina-gld-decode.js` |
| Dataset command helper | `server/nodered/send_dataset_cmd.py` |
| Dataset recorder helper | `server/nodered/gld_dataset_recorder.py` |
| Dataset flow generator | `server/nodered/apply-pertamina-gld-dataset-flow.ps1` |
| Dataset deploy compatibility wrapper | `server/nodered/deploy-dataset-flow.py` |
| Dataset flow snapshot | `server/nodered/pertamina-gld-dataset.flow.json` |

## Flow Generator

`apply-pertamina-gld-flow.js`:

- Reads `functions/pertamina-gld-decode.js`.
- Builds a Node-RED tab `Pertamina GLD Server`.
- Writes `server/nodered/pertamina-gld-server.flow.json`.
- With `--generate-only`, stops after writing the JSON.
- Without `--generate-only`, reads current Node-RED `/flows`, backs up local Node-RED files, merges/replaces `pgl_*` nodes, and POSTs full deployment to Node-RED.
- Creates/uses broker config node `pgl_mqtt_broker`.
- Adds credentials to the deployment body only when MQTT user or password is supplied.

Default CLI values:

| Arg/default | Value |
|---|---|
| `node-red-url` | `http://127.0.0.1:1880` |
| `node-red-user-dir` | `C:\Users\asus\.node-red` |
| `gateway-status-url` | `http://192.168.4.1/api/status` |
| `gateway-base-url` | `http://192.168.4.1` |
| `mqtt-host` | `127.0.0.1` |
| `mqtt-port` | `1884` |
| `mqtt-user` | `MQTT_USER` env or empty |
| `mqtt-password` | `MQTT_PASS` env or empty |

## Runtime Inputs

Generated server flow listens to:

| Input | Source |
|---|---|
| `POST /pertamina-gld/decode` | manual HTTP decode |
| `gld/gateway/uplink` | Gateway MQTT uplink |
| `gld/gateway/topology` | Gateway topology JSON |
| `gld/gateway/raw` | raw/debug MQTT input |
| `pertamina/gld/uplink` | compatibility MQTT input |
| optional Gateway poll inject | `gateway/status/poll` |
| test vector inject | `gld/test/vector` |

Decode normalizer accepts buffers, byte arrays, JSON strings, raw hex strings, gateway-status objects with `gateway_id` and `events`, topology objects, and objects containing `frameHex`, `appFrameHex`, `recordHex`, `payload_hex`, `payloadHex`, or `hex`.

## Protocol Decode

Constants in decode function:

| Constant | Value |
|---|---:|
| `MSG_SENSOR_DATA` | `0x10` |
| `MSG_SERVER_PULL_REQUEST` | `0x30` |
| `MSG_CLUSTER_DATA_RESPONSE` | `0x31` |
| `MSG_CH_HELLO` | `0x33` |
| `MSG_MESH_CONTROL_MIN` | `0x30` |
| `MSG_MESH_CONTROL_MAX` | `0x3F` |
| `MSG_TYPE_MASK` | `0x3F` |
| `FLAG_ALARM_ACK` | `0x40` |
| `FLAG_GLD_EXT_POWER` | `0x80` |
| `NC_FLAG_ALARM` | `0x01` |
| `NC_FLAG_EXT_POWER` | `0x10` |
| `GLD_ENCRYPTED_LEN` | 29 |
| `GLD_RECORD_LEN` | 34 |
| default Gateway ID | `0x006F` |
| default test AES key | `000102030405060708090A0B0C0D0E0F` |

Gas class names:

| ID | Name |
|---:|---|
| 0 | `clearGas` |
| 1 | `LPG` |
| 2 | `methane` |
| 3 | `propane` |
| 4 | `butane` |
| 5 | `reserve` |
| 6 | `anomaly` |

AppFrame validation:

- Minimum length 10.
- Magic byte `0xAA`.
- Total length equals `10 + payloadLen`.
- CRC16-CCITT-FALSE over header and payload.

## AES-GCM Decode

Encrypted payload layout:

| Offset | Field |
|---:|---|
| 0 | key ID |
| 1..12 | nonce |
| 13..16 | ciphertext |
| 17..28 | 12-byte tag |

Key behavior:

- Expected key ID defaults to env `GLD_KEY_ID` or 1.
- AES key comes from env `GLD_AES128_KEY_HEX` or default test key.
- Key hex must be 32 hex characters.
- Node-RED function requires Node crypto from `global.get("crypto")` or global `crypto`.

AAD is reconstructed as:

```text
nodeId:uint16BE + seq:uint8 + flags:uint8 + keyId:uint8
```

Plaintext must be 4 bytes: `gasClass`, `confidence`, `batteryMv:uint16BE`.

## Decode Outputs

Output topics:

| Topic | Payload |
|---|---|
| `gld/gateway/status` | gateway status object |
| `gld/gateway/events` | event envelope/debug object |
| `gld/server/decoded` | non-alarm decoded GLD event |
| `gld/server/alarm` | alarm decoded GLD event |
| `gld/server/topology` | topology event |
| `gld/gateway/error` | error object |

Error object:

| Field | Meaning |
|---|---|
| `ok` | false |
| `kind` | `pertamina-gld-error` |
| `reason` | error reason |
| `detail` | error detail |
| `sourceTopic` | input topic |
| `receivedAt` | ISO timestamp |

## Topology State

Flow context key: `pglTopology`.

Topology state fields:

| Field | Meaning |
|---|---|
| `gatewayIdHex` | root Gateway ID |
| `parents` | installed parent reports by CH hex ID |
| `discovery` | CH_CONFIG discovery candidates |
| `gatewayLinks` | Gateway-heard CH_CONFIG request quality |
| `hellos` | latest CH_HELLO per CH |
| `routes` | computed route arrays |
| `updatedAt` | latest installed update |
| `discoveryUpdatedAt` | latest discovery-only update |
| `resetAt` | set by reset endpoint |

TTL env defaults:

| Env | Default |
|---|---:|
| `PGL_TOPOLOGY_PARENT_TTL_MS` | 900000 |
| `PGL_TOPOLOGY_DISCOVERY_TTL_MS` | 420000 |
| `PGL_TOPOLOGY_GATEWAY_LINK_TTL_MS` | 420000 |

Route builder walks parent links from target CH back to Gateway, with guard limit 16.

## Topology HTTP UI

Endpoints:

| Endpoint | Behavior |
|---|---|
| `GET /pertamina-gld/topology` | returns JSON with nodes, edges, routes, discovery |
| `GET /pertamina-gld/topology/view` | returns HTML/CSS/JS topology UI |
| `POST /pertamina-gld/topology/reset` | clears parents, discovery, gatewayLinks, hellos, routes |
| `POST /pertamina-gld/topology/request?ch=<id>` | publishes `{requestId, hopList}` to `gld/gateway/cmd/pull` if route exists |
| `POST /pertamina-gld/topology/delete?ch=<id>` | deletes CH from all topology maps and any route that includes it |

The HTML UI auto-refreshes every 1000 ms, stores manual node layout in `localStorage` key `pertamina-gld-topology-layout-v1`, and provides Refresh, Reset Layout, Reset Routing, Request, and Hapus controls.

## Dataset Helpers

`send_dataset_cmd.py`:

| Field | Value |
|---|---|
| MQTT host | env `MQTT_HOST` or `127.0.0.1` |
| MQTT port | env `MQTT_PORT` or `1884` |
| MQTT user/pass | env `MQTT_USER` / `MQTT_PASS` or empty |
| client ID | `py-dataset-cmd` |
| topic | `gas-leak-detector/F001/dataset` |

Start command JSON:

```json
{"cmd":"START_DATASET","label":"clear_air_test","target_samples":0,"sample_interval_ms":1000,"max_duration_ms":0,"use_fan_intake":false,"fan_on_ms":1000,"post_fan_settle_ms":0}
```

Stop command JSON:

```json
{"cmd":"STOP_DATASET"}
```

`gld_dataset_recorder.py`:

| Field | Default |
|---|---|
| MQTT topic | `gas-leak-detector/+/dataset/data` |
| MQTT host/port | `127.0.0.1:1884` |
| MySQL host/port | `localhost:3306` |
| MySQL user/pass/db | `root` / empty / `pertamina_gld` |
| CSV path | `gld-dataset.csv` |

Recorder table columns:

```text
device_id,node_id,mode,seq,timestamp_ms,label,nulling_profile_id,
sv0..sv7,gain0..gain7
```

`apply-pertamina-gld-dataset-flow.ps1` generates `pertamina-gld-dataset.flow.json`. `deploy-dataset-flow.py` is a compatibility wrapper that forwards to the PowerShell generator so the dataset flow has one source of truth.

The generated dataset flow includes operator inject controls:

| Node | MQTT topic | Payload |
|---|---|---|
| `START_DATASET clear_air_test` | `gas-leak-detector/F001/dataset` | `START_DATASET` JSON with `label`, `target_samples`, `sample_interval_ms`, `max_duration_ms`, `use_fan_intake`, `fan_on_ms`, and `post_fan_settle_ms` |
| `STOP_DATASET` | `gas-leak-detector/F001/dataset` | `{"cmd":"STOP_DATASET"}` |

The generated dataset flow listens to:

| Topic | Use |
|---|---|
| `gas-leak-detector/+/dataset/data` | insert current GLD unified dataset records to MySQL and append CSV |
| `gas-leak-detector/+/dataset/status` | debug dataset lifecycle status |
| `gas-leak-detector/+/dataset/summary` | debug dataset session summary |
| `gas-leak-detector/+/cmd/ack` | debug GLD command ACK, including `START_DATASET` and `STOP_DATASET` results |
| `gas-leak-detector/+/nulling/result` | debug retained nulling profile result |

The dataset flow expects the current GLD unified JSON field names `sensor_voltage`, `sensor_gain`, `feature_order`, `device_id`, `node_id`, `timestamp_ms`, `label`, and `nulling_profile_id`.
