# Pertamina GLD Current Design - Cluster Head

Status: current source mirror, 2026-06-29. Dokumen ini mengikuti CH STAR+MESH runtime yang sedang ada di repo. Imported baseline `design.md` tidak diubah.

## Source Files

| Area | Source |
|---|---|
| PlatformIO env | `firmware/platformio.ini` |
| Main runtime | `firmware/ch/src/ChStarMeshRuntimeMain.cpp` |
| Config | `firmware/config/ChConfig.h`, `LoraStarConfig.h`, `LoraMeshConfig.h` |
| Pins | `firmware/ch/include/ChBoardPinsCh3.h` (latest CH3/CH5 production profile) |
| STAR parser/ACK | `firmware/ch/include/ChUplink.h`, `firmware/ch/src/ChUplink.cpp` |
| Node cache | `NodeCache.h`, `NodeCache.cpp` |
| Alarm queue | `AlarmQueue.h`, `AlarmQueue.cpp` |
| TX queue | `ChTxQueue.h`, `ChTxQueue.cpp` |
| Pull parsing | `ChPullRequest.h`, `ChPullRequest.cpp` |
| Cluster response | `ClusterResponse.h`, `ClusterResponse.cpp` |
| Runtime logic | `ChRuntime.h`, `ChRuntime.cpp` |
| Shared protocol | `AppFrame`, `GldRecord`, `ProtocolConstants`, `FirmwareConfig` |

## Active Build Environments

| Env | CH ID | Overrides |
|---|---:|---|
| `ch` | NVS-provisioned; factory fallback `0x0064` | latest CH3/CH5 pins, RF switch, external WDT, reference radio reset |
| `chFieldtest` | same NVS identity as `ch` | 30 s HELLO, 5 s jitter, battery read-only |

The CH runtime env compiles shared `AppFrame`, `FirmwareConfig`, `GldRecord`; CH `AlarmQueue`, `ChPullRequest`, `ChRuntime`, `ChTxQueue`, `ChUplink`, `ClusterResponse`, `NodeCache`, `ChStarMeshRuntimeMain`. It excludes GLD source, `ChStarRxSelfTestMain`, docs, tests, and versions.

Firmware identifiers:

| Field | Value |
|---|---|
| firmware name | `PertaminaGLD-CH` |
| firmware version | `0.7.1` |
| protocol version | `0.1.0` |
| config schema version | `0.1.0` |

## Hardware Pins

| Function | Pin/value |
|---|---|
| SPI SCK/MOSI/MISO | GPIO12/GPIO11/GPIO13 |
| Radio A role | STAR with GLD |
| Radio A TXEN/RXEN/RST/BUSY/DIO1/CS | GPIO5/GPIO6/GPIO7/GPIO17/GPIO15/GPIO16 |
| Radio B role | MESH with CH/Gateway |
| Radio B CS/BUSY/RXEN/TXEN/RST/DIO1 | GPIO42/GPIO41/GPIO39/GPIO40/GPIO1/GPIO2 |
| Battery monitor ADC | GPIO4 |
| External WDT wake/keepalive | GPIO14/GPIO21 |

Radio init:

- Both radio reset pins are held LOW, delayed 50 ms, then HIGH, delayed 500 ms.
- Both radios try TCXO 1.6 V first and fallback to 0.0 V only on `RADIOLIB_ERR_SPI_CMD_FAILED`.
- Both radios set RadioLib RF switch pins after successful init.

## Radio Config

| Domain | Frequency | BW | SF | CR | Sync | TX power | Preamble | SPI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| STAR | 920.0 MHz | 125 kHz | 7 | 4/5 | `0x12` | 17 dBm | 8 | 2 MHz |
| MESH | 921.0 MHz | 125 kHz | 9 | 4/5 | `0x34` | 17 dBm | 8 | 2 MHz |

## Identity And Capacities

| Config | Value |
|---|---:|
| root Gateway ID | `0x006F` |
| default parent | `0x0000` |
| broadcast ID | `0xFFFF` |
| node cache capacity | 32 |
| alarm queue capacity | 8 |
| MESH TX queue capacity | 8 |
| pending downlink store capacity | 16 |
| parent candidate capacity | 8 |
| node stale threshold | 300000 ms |
| node cache expire threshold | 3600000 ms |
| cache report interval | 10000 ms |
| pending downlink TTL | 1800000 ms |
| housekeeping interval | 60000 ms |

CH ID, parent ID, and alternate parent are runtime values. CH ID is provisioned by
the operator app and stored in Preferences namespace `ch-cfg`, key `chId`.
Changing it clears `parentId` and `parentAlt`, verifies the NVS readback, and
reboots so discovery restarts under the new identity.

## Battery And State Machine

Battery read:

- 12-bit ADC.
- ADC attenuation `ADC_11db`.
- 16 samples of `analogReadMilliVolts(GPIO4)`.
- Formula: `(average_adc_mV * 3) + 200`.

Battery thresholds:

| Threshold | Default |
|---|---:|
| start | 3500 mV |
| run minimum | 3150 mV |
| critical | 3100 mV |

`chFieldtest` keeps the ADC reading for diagnostics but bypasses battery gating.

State machine:

| State | Behavior |
|---|---|
| `BOOT` | immediate transition to `WAIT_BATT` |
| `WAIT_BATT` | read battery every 1000 ms until 8 consecutive readings pass start threshold |
| `RADIO_INIT` | reset/init radios, clear cache/queues, arm STAR and MESH RX |
| `JOINING` | send periodic CH_CONFIG_REQUEST, collect candidates, select parent after timeout |
| `JOINED` | normal STAR RX, MESH RX, TX drain, ACK timeout, hello, route verify, housekeeping |
| `LOW_POWER` | still handles RX; drains TX only if critical threshold allows |
| `PARENT_FAILOVER` | discovery loop after parent failure |
| `RECOVERY` | delay 500 ms and `ESP.restart()` |

Watchdog is initialized with 60 second timeout and reset every loop.

## Discovery And Parent Selection

Discovery request:

| Field | Value |
|---|---|
| AppFrame type | `MSG_CH_CONFIG_REQUEST (0x34)` |
| source | local CH ID |
| destination | `0xFFFF` |
| payload | requester CH ID, 2 bytes big-endian |
| sequence | local static config-request sequence |
| jitter before TX | `20 + ((CH_ID & 0x000F) * 30) + (millis() % 40)` ms |

Discovery response from CH:

| Offset | Field |
|---:|---|
| 0..1 | requester ID |
| 2..3 | responding CH current parent |
| 4 | advertised mesh depth |
| 5..6 | CH battery mV |
| 7 | route/capability flags: route-to-root `0x01`, HELLO ACK v1 `0x02`, alarm ACK node ID v1 `0x04`, routed node command v1 `0x08` |

Gateway responses are described in Gateway docs. CH accepts Gateway reverse-link RSSI/SNR only when Gateway response payload has at least 10 bytes.

Timing:

| Parameter | Value |
|---|---:|
| joining timeout | 15000 ms |
| config request interval | 5000 ms |
| config response base delay | 200 ms |
| config response slot gap | 280 ms |
| config response slot count | 16 |
| route verify interval | 600000 ms |
| route verify jitter max | 300000 ms |
| route verify window | 10000 ms |
| parent health timeout | 180000 ms |
| parent minimum dwell | 300000 ms |
| parent switch margin | 15 dB |
| parent NVS stable scans | 4 |

Selection rules implemented in source:

- Candidate is ignored if ID is 0, local CH ID, broadcast ID, advertised parent is local CH, or depth is `0xFF`.
- Candidate score is RSSI. Tie-breakers are lower depth, higher SNR, lower ID.
- Direct Gateway is preferred only when Gateway RSSI is at least `-95 dBm`, SNR at least `5 dB`, reverse link exists, and reverse RSSI is at least `-100 dBm`.
- Gateway is not allowed as runtime parent if CH-side RSSI or reverse RSSI is below `-100 dBm`, or reverse link is missing.
- Alternate parent is not used when selected parent is Gateway.
- Candidates must be upstream for current depth to avoid loops.
- Background verification keeps current parent until dwell time unless failover is active.

## STAR GLD Processing

CH STAR RX accepts GLD `MSG_SENSOR_DATA` AppFrames. Parser output contains node ID, CH ID, GLD seq, typeFlags, alarm flag, external power flag, encrypted payload pointer, and encrypted payload length.

Valid GLD payload length for current phase is 29 bytes. CH does not decrypt it.

NodeCache entry:

| Field | Meaning |
|---|---|
| `used` | slot active |
| `nodeId` | GLD ID |
| `currentSeq` | latest GLD seq |
| `sentSeq` | latest seq marked sent upstream |
| `flags` | record flags: alarm bit `0x01`, external-power bit `0x10` |
| `lastSeenMs` | receive timestamp |
| `lastSentMs` | upstream sent timestamp |
| `payloadLen` | encrypted payload length |
| `payload` | opaque encrypted payload |

Duplicate seq with same flags/payload updates `lastSeenMs`. Duplicate seq with different payload is conflict. Inserted/updated alarm can request compact STAR ACK and MESH alarm push.

Alarm behavior:

- Alarm queue stores alarm records until parent/Gateway compact ACK is received.
- CH sends compact STAR ACK back to GLD when alarm is accepted or already queued.
- Alarm MESH push remains in alarm queue until upstream ACK.
- `ALARM_ACK_TMO_MS=1500`.
- Current `checkAlarmAckTimeout()` logs timeout, removes alarm queue item, increments parent failure and no-ACK burst counters, and does not retry the same alarm frame.
- Parent fail threshold is 3.
- Recovery threshold for no-ACK burst is 5.
- Failover cooldown is 60000 ms.

Recovery clear:

- If previous cache entry was alarm and new GLD record is non-alarm, CH queues one `RecoveryClear` MESH record.

## MESH TX Queue

TX queue item kinds:

| Value | Kind |
|---:|---|
| 0 | `AlarmPush` |
| 1 | `RecoveryClear` |
| 2 | `ClusterDataResponse` |
| 3 | `RelayFrame` |

Queue capacity is 8. `CH_TX_FRAME_MAX = APPFRAME_OVERHEAD + MESH_MAX_PAYLOAD`.

Queue drain behavior:

- Skips if MESH radio is not ready.
- Skips if an alarm ACK is pending.
- Stops if battery critical blocks TX.
- On success, marks selected cache entries sent or leaves RelayFrame cache untouched.
- Alarm push activates upstream ACK tracking and stops drain.
- After any TX attempt, MESH RX is re-armed.

## Pull And Cluster Response

Server pull request:

| Field | Meaning |
|---|---|
| AppFrame type | `MSG_SERVER_PULL_REQUEST (0x30)` |
| payload bytes 0..1 | requestId |
| payload bytes 2.. | hopList, each hop `uint16BE` |

Intermediate CH relay:

- Finds local CH in hopList.
- If local index is not final index, rebuilds same payload with `srcId=local CH`, `dstId=next hop`, same AppFrame seq.
- Enqueues RelayFrame.

Final CH response:

| Offset | Field |
|---:|---|
| 0..1 | requestId |
| 2 | data status |
| 3..4 | CH battery mV |
| 5 | record count |
| 6.. | GLD records |

Data statuses:

| Value | Name |
|---:|---|
| `0x00` | DataOk |
| `0x01` | DataEmpty |
| `0x02` | DataNotAvail |
| `0x03` | DataStale |
| `0x04` | DataBusy |
| `0x05` | DataInvalid |

Cluster response selection:

- Selects oldest normal unsent, non-stale, valid cache entries.
- Excludes alarm entries.
- Fits records within MESH payload max 80 bytes.
- Current selected index capacity is 2, and a 34-byte phase-1 GLD record means at most 2 records fit with 6-byte response header.
- Mark selected entries sent only after MESH TX success.

## CH_HELLO And Topology

CH_HELLO:

| Offset | Field |
|---:|---|
| 0..1 | CH ID |
| 2..3 | parent ID |
| 4..5 | battery mV |
| 6..7 | uptime seconds low 16 bits |
| 8 | mesh depth |
| 9..10 | alternate parent ID |

Behavior:

- After first JOINED state with non-zero parent, CH sends boot hello immediately.
- Boot hello is retried with 1000 ms throttle until transmit succeeds.
- Periodic hello interval is 300000 ms after boot hello succeeds.
- `CH_HELLO_TX` logs parent, alternate, battery, uptime, depth, and `txOk`.

## Downlink To GLD

CH accepts two backward-compatible `MSG_SERVER_NODE_COMMAND` payload forms.
The direct legacy form remains:

| Legacy offset | Field |
|---:|---|
| 0..1 | target GLD node ID |
| 2..3 | command ID |
| 4..5 | TTL seconds |
| 6 | command length |
| 7.. | command bytes, max accepted length 8 |

When the Gateway JSON has an explicit `hopList`/`hop_list`/`hops` array, it
uses the routed v1 envelope:

| Routed v1 offset | Field |
|---:|---|
| 0 | route magic `0xC1` |
| 1 | route version `0x01` |
| 2 | hop count |
| 3..5 | reserved, must be zero |
| 6 | legacy rejection guard `0xFF` |
| 7.. | `hopList[]`, each CH ID as `uint16BE` |
| after hop list | complete legacy command body shown above |

The first hop is the CH directly reachable from the Gateway and the last hop
is the CH that owns the target GLD. Every CH requires its local ID in the
unique, non-zero hop list and requires AppFrame `srcId` to equal the previous
hop (the Gateway ID for hop zero). An intermediate CH keeps the AppFrame seq
and payload unchanged, rewrites `srcId`/`dstId` for the next hop, and enqueues
the frame as `RelayFrame`. Only the final CH stores the pending downlink.

The v1 guard is intentionally greater than the legacy maximum command length.
An older CH therefore rejects a routed payload instead of storing it as a
bogus legacy command. Direct commands that use only `cluster` keep the legacy
wire format and continue to work with old and new CH firmware. A routed
command requires every CH in the explicit hop list to advertise
`CH_CONFIG_CAP_NODE_COMMAND_ROUTE_V1 (0x08)`. With an 8-byte command and the
80-byte MESH limit, v1 supports at most 29 CH hops.

If NodeCache says target GLD is external-powered and STAR is ready, CH sends `MSG_NODE_DOWNLINK` immediately. If target GLD is not external-powered, CH waits for the next STAR uplink from that GLD and sends downlink inside the GLD RX window.

Pending downlink store has one active slot per `nodeId` lookup. A new command for the same node reuses the existing slot and overwrites its fields.

CH and Gateway share the same encoder/decoder for both payload forms.
`ttlSec` becomes the pending downlink expiry; `0` uses the CH default pending
TTL. Gateway and CH both enforce an 8-byte command maximum; Gateway rejects a
longer value instead of truncating the command.
For GLD mode commands, `commandBytes` is the authenticated GLD payload
`0x81 + mode + commandId + cmacTag4`; CH stores it opaquely and forwards it as
`MSG_NODE_DOWNLINK` with AppFrame seq `commandId & 0xFF`.

`MSG_SERVER_NODE_COMMAND` remains fire-and-forget on MESH: this route version
does not add a relay ACK or an end-to-end GLD command-result ACK.

## Serial Logs

Important CH log prefixes:

| Prefix | Meaning |
|---|---|
| `CH_WDT_INIT` | watchdog initialized |
| `CH_IDS` | local/root/default IDs |
| `CH_NVS_LOAD`, `CH_NVS_SAVE` | parent persistence |
| `CH_STATE` | state transition |
| `CH_BATT_MV`, `CH_BATT_LOW`, `CH_LOW_POWER` | battery state |
| `CH_STAR_BEGIN_*`, `CH_MESH_BEGIN_*` | radio init |
| `CH_CONFIG_REQUEST_TX` | discovery request |
| `CH_CONFIG_RESPONSE_RECV`, `CH_CONFIG_RESPONSE_TX` | discovery response |
| `CH_PARENT_CANDIDATE`, `CH_PARENT_CANDIDATE_REJECT`, `CH_PARENT_SELECT` | routing decision |
| `CH_STAR_RX`, `CH_STAR_PROCESS` | GLD receive path |
| `CH_CACHE_SUMMARY`, `CH_CACHE_ENTRY` | cache report |
| `CH_PULL_PROCESS`, `CH_PULL_RELAY` | pull request path |
| `CH_MESH_TX_KIND`, `CH_MESH_TX_MARK` | MESH transmit path |
| `CH_ALARM_ACK_RECV`, `CH_ALARM_ACK_TIMEOUT` | alarm upstream ACK |
| `CH_DOWNLINK_STORED`, `CH_NODE_DOWNLINK_TX` | downlink path |
| `CH_HELLO_TX`, `CH_BOOT_HELLO` | topology hello |
