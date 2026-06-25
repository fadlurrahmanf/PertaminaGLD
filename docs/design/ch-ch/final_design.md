# Pertamina GLD Final Design - CH To CH Multi-Hop

Status: current-state final design, 2026-06-25. This file describes CH-CH routing as implemented by the current CH firmware and observed bench behavior.

## Source Of Truth

- CH runtime: `firmware/ch/src/ChStarMeshRuntimeMain.cpp`.
- CH config: `firmware/config/ChConfig.h`.
- Protocol: `firmware/shared/include/ProtocolConstants.h`.
- Topology visualization: `server/nodered/functions/pertamina-gld-decode.js`.

## Design Goal

CH nodes form an auto-routed MESH backbone toward Gateway `0x006F`. A CH may use Gateway directly or another CH as parent. Parent and alternate are discovered from RF candidates, not statically flashed.

## Discovery

Discovery is based on CH_CONFIG:

1. Requesting CH sends broadcast `MSG_CH_CONFIG_REQUEST`.
2. Gateway and route-capable CH nodes reply with `MSG_CH_CONFIG_RESPONSE`.
3. Requester records candidate ID, parent, depth, RSSI/SNR, reverse RSSI/SNR when available, battery, and route-to-root ability.
4. Candidate selection rejects downstream/deeper nodes and weak Gateway links.
5. Selected parent/alternate are written to runtime immediately and persisted to NVS only after stable repeated scans.

Anti-collision response timing uses deterministic slots: 200 ms base, 280 ms slot gap, 16 slots, request interval 5000 ms.

## Parent Selection

Selection uses score and policy gates:

- Prefer direct Gateway only when RSSI and SNR pass direct thresholds and reverse link passes Gateway floor.
- Reject Gateway as parent/alternate when CH-side or reverse RSSI is below -100 dBm.
- Reject downstream candidates to avoid loops.
- During background verification, keep current parent until minimum dwell time is met unless failover is required.
- Require 15 dB RSSI margin before background parent switch.

## Multi-Hop Relay

For pull request downlink:

- Gateway sets `dstId` to first hop in `hopList`.
- Intermediate CH finds its local hop index and relays to the next hop.
- Final CH builds `MSG_CLUSTER_DATA_RESPONSE`.

For uplink response or alarm/data push:

- CH sends toward active parent.
- Parent CH relays upstream.
- Gateway receives final MESH frame and publishes it to MQTT.

Response path uses active parent routing, not a reverse hop list.

On every boot, a CH with a non-zero parent sends one immediate boot `CH_HELLO` after first entering `JOINED`, before waiting for the normal 5-minute hello interval. This is required even when the parent came from NVS/cache, so the server/topology layer sees the CH as live immediately after restart.

## Current Verified Topology Pattern

Latest saved observations include:

| Node | Observed role |
|---|---|
| Gateway `0x006F` | MESH root |
| CH `0x0064` | layer-1 parent via Gateway |
| CH `0x0065` | layer-1 or attached CH depending latest bench mapping |
| CH `0x0066` | layer-2 candidate/child in latest source mapping |

Bench notes changed over time as boards were moved between COM ports and IDs. Current source env mapping should be checked before upload. Runtime truth is the serial `CH_PARENT_SELECT`, `CH_HELLO_TX`, and Node-RED topology view.

## Failover

Failover is triggered by:

- parent health timeout after 180000 ms silent parent,
- repeated alarm ACK failures,
- weak bidirectional Gateway route detection.

Expected no-traffic failover is approximately 180 seconds plus up to the joining/config response window. The expected serial trace includes `CH_PARENT_HEALTH_FAIL`, `CH_STATE state=PARENT_FAILOVER`, `CH_CONFIG_REQUEST_TX`, `CH_CONFIG_RESPONSE_RECV`, and `CH_PARENT_SELECT reason=failover`.

## Known Gaps

- Discovery response collision risk remains in larger networks despite deterministic slotting.
- Background route verification is conservative by design, so UI may show retained routes before hard TTL expires.
- Parent/alternate decisions depend on live RF; static docs must not be treated as the only topology source.
- Gateway node command payload mismatch with CH affects remote GLD mode switching through multi-hop until fixed.

## Post-12 Work

- Run long soak with all active CH boards and record parent, alternate, RSSI, SNR, depth, and score over time.
- Test failover by powering off active parent and measuring switch time.
- Validate topology UI stale/retained states against serial truth.
- Add automated log parser for CH_PARENT_SELECT and CH_HELLO_TX evidence.
- Tune discovery slot/jitter if 10+ CH collisions are observed.
