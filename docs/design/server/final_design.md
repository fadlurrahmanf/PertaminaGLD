# Pertamina GLD Final Design - Server And Node-RED

Status: current-state final design, 2026-06-25. This file describes the Node-RED/server flow as implemented by the current repository.

## Source Of Truth

- Flow generator/deployer: `server/nodered/apply-pertamina-gld-flow.js`.
- Decode function: `server/nodered/functions/pertamina-gld-decode.js`.
- Generated flow snapshot: `server/nodered/pertamina-gld-server.flow.json`.
- Dataset helpers: `server/nodered/send_dataset_cmd.py`, `gld_dataset_recorder.py`.

## Runtime Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /pertamina-gld/decode` | manual decode input |
| `GET /pertamina-gld/topology` | topology JSON |
| `GET /pertamina-gld/topology/view` | browser topology UI |
| `POST /pertamina-gld/topology/reset` | clear topology state |
| `POST /pertamina-gld/topology/request?ch=<id>` | publish pull request using installed route |
| `POST /pertamina-gld/topology/delete?ch=<id>` | remove CH topology state until future events recreate it |

The live topology page auto-refreshes every 1 second and shows CH status, last CH_HELLO age, expected next event, Request, and Hapus actions.

## Decode Pipeline

Node-RED accepts Gateway MQTT JSON, direct frame hex, buffers, topology objects, and gateway status objects. It:

- normalizes input,
- validates AppFrame magic/length/CRC,
- separates control frames from GLD data frames,
- parses `MSG_SENSOR_DATA`, `MSG_CLUSTER_DATA_RESPONSE`, `MSG_SERVER_PULL_REQUEST`, and CH topology messages,
- decrypts 29-byte GLD encrypted payloads with AES-128-GCM,
- emits GLD event objects with gas class, confidence, battery, flags, dedup key, and source metadata.

Gas class mapping is:

| ID | Name |
|---:|---|
| 0 | clearGas |
| 1 | LPG |
| 2 | propana |
| 3 | butana |
| 4 | metana |
| 5 | reserve |
| 6 | anomaly |

## Topology State

Flow state key: `pglTopology`.

Tracked maps:

- `parents`: installed CH parent reports.
- `discovery`: pending CH_CONFIG discovery candidates.
- `gatewayLinks`: RSSI/SNR for CH_CONFIG request heard by Gateway.
- `hellos`: latest CH_HELLO per CH.
- `routes`: computed route from Gateway to each installed CH.

TTL defaults:

| State | TTL |
|---|---:|
| installed parent / route | 900000 ms |
| discovery candidate | 420000 ms |
| Gateway-link RSSI | 420000 ms |
| CH_HELLO age | pruned with installed parent TTL |

Discovery candidates are not retained when the same CH already has a fresh installed topology route.

## Topology UI Actions

Request button:

- Requires installed route.
- Builds `hopList` from topology route.
- Publishes JSON to `gld/gateway/cmd/pull`.
- Returns HTTP 400 if route is missing/invalid.

Hapus button:

- Removes the selected CH from `parents`, `discovery`, `gatewayLinks`, `hellos`, and `routes`.
- The CH reappears only after later CH_HELLO/topology/discovery events.

## Dataset Server Flow

GLD dataset mode publishes to `gas-leak-detector/F001/dataset/data`, status, summary, and ack topics. The dataset pipeline stores bounded captures to MySQL and CSV. Final verified schema is:

- `device_id`
- `node_id`
- `mode`
- `seq`
- `timestamp_ms`
- `label`
- `nulling_profile_id`
- `sensor_voltage[8]`
- `sensor_gain[8]`
- `feature_order[8]`

Verified feature order is MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2.

## Debug Outputs

The flow keeps compact debug labels:

- INSTALLED
- DISCOVERY CANDIDATE
- STALE DISCOVERY
- STALE INSTALLED

For pull responses, compact debug includes response requestId, status, record count, responseFromCh, and GLD event summary when records are present.

## Status And Caveats

- Node-RED topology changes through 2026-06-24 were deployed and verified against the live page/API.
- Current generated flow contains the same topology features and should be redeployed only when the operator wants runtime change.
- No Node-RED deploy is required for creating this final design documentation.
- Gateway node command path has a known firmware payload mismatch and should not be presented as fully production-verified until fixed.

## Post-12 Work

- Add integration tests for topology Request/Hapus and pull response decode.
- Add persistent storage/history for topology if operator needs historical route audit.
- Add role-based operator UI if dashboard becomes a field tool.
- Add production MySQL migration/backup scripts for dataset and alarm history.
- Add model-training export pipeline from verified dataset rows.
