# Pertamina GLD Final Design - Cluster Head

Status: current-state final design, 2026-06-25. This file describes the CH firmware as it exists now, including source-only changes that still need upload/bench verification.

## Source Of Truth

- Main runtime env: `ch_star_mesh_runtime_esp32s3`.
- Bench envs: `ch_layer1_1_esp32s3`, `ch_layer1_2_esp32s3`, `ch_layer2_1_esp32s3`.
- Current firmware version: CH `0.7.1`, protocol `0.1.0`.
- Main source path: `firmware/ch/src/ChStarMeshRuntimeMain.cpp`.
- Config source: `firmware/config/ChConfig.h`, `LoraStarConfig.h`, `LoraMeshConfig.h`.
- Runtime helpers: `NodeCache`, `AlarmQueue`, `ChTxQueue`, `ChRuntime`, `ClusterResponse`, `ChPullRequest`, `ChUplink`.

## Hardware And Radio Roles

CH has two SX1262 radios:

| Radio | Role | Pins |
|---|---|---|
| Radio A | STAR RX/TX with GLD | TXEN GPIO5, RXEN GPIO6, RST GPIO7, BUSY GPIO15, DIO1 GPIO16, CS GPIO17 |
| Radio B | MESH TX/RX with CH/Gateway | CS GPIO14, BUSY GPIO38, RXEN GPIO39, TXEN GPIO40, RST GPIO41, DIO1 GPIO42 |
| Shared SPI | SCK/MOSI/MISO | GPIO12/GPIO11/GPIO13 |
| Battery monitor | ADC | GPIO4 |

STAR uses 920.0 MHz, BW125, SF7, CR 4/5, sync `0x12`. MESH uses 921.0 MHz, BW125, SF9, CR 4/5, sync `0x34`. Both use 17 dBm TX power, preamble 8, SPI 2 MHz.

## Bench Env Mapping

| Env | CH ID | Notes |
|---|---:|---|
| `ch_layer1_1_esp32s3` | `0x0064` | layer-1 candidate |
| `ch_layer1_2_esp32s3` | `0x0065` | layer-1 candidate, battery thresholds overridden to 0 for bench |
| `ch_layer2_1_esp32s3` | `0x0066` | layer-2 candidate |
| `ch1_esp32s3`..`ch8_esp32s3` | `0x0001`..`0x0008` | generic bench/test IDs |

Active parent is not hardcoded. `DEFAULT_PARENT_ID=0x0000`; parent and alternate come from CH_CONFIG discovery and stable NVS cache.

## State Machine

Runtime states:

| State | Purpose |
|---|---|
| BOOT | initial state, immediately proceeds to WAIT_BATT |
| WAIT_BATT | waits for battery threshold stability before radio init |
| RADIO_INIT | initializes STAR and MESH radios |
| JOINING | sends CH_CONFIG_REQUEST and selects parent/alternate |
| JOINED | normal receive, cache, uplink, pull, hello, housekeeping |
| LOW_POWER | blocks or limits TX when battery is critical |
| PARENT_FAILOVER | scans/reselects parent after ACK/health failure |
| RECOVERY | restarts after unrecoverable repeated failures |

Watchdog is initialized at 60 seconds and reset in the main loop.

## Routing And Discovery

CH_CONFIG discovery is broadcast-based:

- CH requester sends `MSG_CH_CONFIG_REQUEST` to broadcast.
- Gateway responds as root candidate with depth 0 and reverse RSSI/SNR.
- Joined CH nodes with route-to-root respond as parent candidates.
- Candidates are scored by RSSI/SNR/depth and filtered to reject downstream/deeper parents and weak Gateway links.
- Gateway is prioritized only when direct bidirectional quality passes thresholds.

Key timing and thresholds:

| Parameter | Value |
|---|---:|
| `JOINING_TMO_MS` | 15000 |
| `CFG_REQUEST_INTERVAL_MS` | 5000 |
| `CFG_RESPONSE_BASE_DELAY_MS` | 200 |
| `CFG_RESPONSE_SLOT_GAP_MS` | 280 |
| `CFG_RESPONSE_SLOT_COUNT` | 16 |
| `ROUTE_VERIFY_INTERVAL_MS` | 600000 |
| `ROUTE_VERIFY_JITTER_MS` | 300000 |
| `ROUTE_VERIFY_WINDOW_MS` | 10000 |
| `PARENT_HEALTH_TIMEOUT_MS` | 180000 |
| `PARENT_MIN_DWELL_MS` | 300000 |
| `PARENT_SWITCH_MARGIN_DB` | 15 |
| `GATEWAY_DIRECT_PARENT_MIN_RSSI_DBM` | -95 |
| `GATEWAY_DIRECT_PARENT_MIN_SNR_DB` | 5 |
| `GATEWAY_PARENT_MIN_RSSI_DBM` | -100 |
| `GATEWAY_ALT_PARENT_MIN_RSSI_DBM` | -100 |
| `PARENT_NVS_STABLE_SCANS` | 4 |

## GLD STAR Processing

CH listens for GLD `MSG_SENSOR_DATA` frames on STAR. It decodes the AppFrame, stores the latest GLD record in `NodeCache`, builds compact alarm ACKs when required, and queues MESH uplink frames. `NodeCache` capacity is 32 GLDs, stale threshold is 300000 ms, and cache expire threshold is 3600000 ms.

Alarm behavior:

- Alarm frames are queued in `AlarmQueue` with capacity 8.
- Parent/Gateway compact ACK clears pending alarm only when ACK is received.
- ACK timeout is 1500 ms.
- Max alarm retry is 5.
- Parent fail threshold is 3 ACK failures; recovery threshold is 5 consecutive no-ACK events.

## Server Pull And Cluster Response

Server pull uses `MSG_SERVER_PULL_REQUEST` payload `requestId + hopList[]`. CH relays pull requests along the forward hop list until the final CH, then builds `MSG_CLUSTER_DATA_RESPONSE`.

Cluster response payload:

| Offset | Field |
|---|---|
| 0..1 | `requestId` |
| 2 | data status |
| 3..4 | CH battery mV |
| 5 | record count |
| 6.. | repeated GLD records |

Data statuses are `DataOk`, `DataEmpty`, `DataNotAvail`, `DataStale`, `DataBusy`, `DataInvalid`.

Source-only delta: CH pull response telemetry now logs requestId, data status, record count, response size, and build status. This is implemented in source and built once for `ch1_esp32s3`, but is pending upload/bench verification on the deployed CH boards.

## Downlink To GLD

`SERVER_NODE_COMMAND` stores a pending GLD downlink. Current CH parser expects payload `nodeId(2) + commandId(2) + commandLen(1) + commandBytes`. If the GLD is external-powered, CH can send `MSG_NODE_DOWNLINK` immediately; otherwise it waits for the GLD RX window after a sensor uplink.

Known integration caveat: current Gateway source builds node command payload as `nodeId + commandId + ttlSec + commandLen + commandBytes`, while CH parser currently expects no `ttlSec`. Treat Gateway-to-CH-to-GLD remote mode switching as needing a focused retest/fix before production reliance.

## CH_HELLO And Topology

CH sends one mandatory boot `MSG_CH_HELLO` immediately after first entering `JOINED` after boot when `parentId != 0`, including when parent state came from the previous NVS/cache state. After that, CH sends `MSG_CH_HELLO` every 300000 ms to its parent. Payload includes CH ID, parent, battery, uptime, mesh depth, and parent alternate when present. Gateway and Node-RED use this for installed topology, route rendering, and liveness display.

Boot hello logs `CH_BOOT_HELLO` before the send and `CH_HELLO_TX ... txOk=<0|1>` after the transmit attempt. The boot hello is considered complete only if TX succeeds; otherwise it remains pending and is retried with a 1000 ms throttle.

## Post-12 Work

- Upload and bench-verify the new pull response telemetry on all active CH boards.
- Resolve the `SERVER_NODE_COMMAND` TTL mismatch between Gateway and CH.
- Stress-test discovery with 10+ CH, including collision/backoff and background route verification.
- Validate field battery thresholds and low-power behavior with real CH power hardware.
- Add production diagnostics for route churn, ACK retry exhaustion, and stale cache reasons.
