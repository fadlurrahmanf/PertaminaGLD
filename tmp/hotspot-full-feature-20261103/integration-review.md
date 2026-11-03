# Integration review — additive final hotspot firmware

Date: 2026-11-03. Reviewer: Integration_Agent. Source review only; no compiler, device, COM port, Wi-Fi change, upload, service restart or hardware operation was performed.

## Scope and verdict

The approved boundary is normal controls over COM and Dataset over Wi-Fi. The app's existing COM/Wi-Fi exclusion remains protected: Stop, finish durable CSV delivery, Disconnect Wi-Fi, then use normal COM tools. Generic wireless configuration RPC and simultaneous LoRa recording are outside this change.

**Final source verdict: no remaining blocking finding in the frozen revision below.** The three concrete defects found in this review cycle have been corrected and inspected. This is approval to proceed to the user's compilation decision, not a claim of physical feature parity. The focused source contract confirms the normal non-workflow conditional branch and protected package/model inputs remain unchanged.

## Findings found during actual source-path review

1. **Resolved — alarm and moving-average discontinuity at ownership changes.** The initial revision reset the shared MAV, inference validity and AUTO alarm on entry/release of a session and again at the first acquisition epoch. Starting recording on valid non-clear input therefore immediately cleared GPIO48 solely because transport ownership changed, then required another 10 × 500 ms priming window. The GLD source owner removed these ownership/epoch resets. Reset remains appropriate for invalid acquisition/readiness or an actual unleased profile change (`GldDatasetWorkflowWifi.cpp:716`). The focused source test protects continuity; real steady-output measurement remains pending.

2. **Resolved — standalone Connect/Start starvation in stored native Dataset mode.** `maintainWifi()` originally called blocking `connectWifi()` on every idle loop when the configured station router was absent. Most incoming Starts captured `nativeBusy=true`; additionally a Hello masked by temporary busy caused the Hub to immediately disconnect a hardware-ready candidate. The corrected source uses cached hardware readiness in Hello, breaks an in-progress station wait when a Workflow client connects (`GldUnifiedMain.cpp:4869`), skips MQTT connect with a client/no station (`:4893`), and skips background STA/MQTT reconnect while a client is connected (`:7773`). Start retains the independent native-busy snapshot and fresh readiness validation. Once a new client is accepted during station wait, exit is bounded by the current 50 ms service slice, then the following main poll handles admission. A Start that raced the previous native operation may still receive an explicit busy rejection; it is not silently admitted later. No persistent starvation remains in the inspected path.

3. **Resolved — prediction-disabled wire projection conflicts with protocol 3.** Native inference executes regardless of the optional CSV prediction checkbox, but the initial serializer could emit `enabled=false`, `valid=false`, `status=valid` (or `warmup`). The serializer now selects Disabled before status serialization when projection is off (`GldDatasetWorkflowWifi.cpp:562`), while its valid guard leaves class/gas/confidence null. Native NN/AUTO execution remains independent of that CSV projection. Parent found this independently; reviewer confirmed both the defect and correction.

## Execution and ownership inspection

- Acquisition now runs synchronously from `poll()` on the Arduino main thread; the transport worker owns socket I/O, queueing and retained-prefix ACKs. It does not execute ADC, NN, calibration or serial callbacks.
- ADS1256 read waits are bounded and do not call `firmwareServiceTick()`. Native serial command execution therefore cannot reenter halfway through the workflow ADC/MAV/NN operation. Pause/Stop commands are processed by that same main thread and ACK only after the preceding capture has returned.
- The serial mutation fence is present both at command dispatch and before the special priority Restart/Cancel path. Read-only Info/Status/Telemetry/QC queries snapshot caches/NVS rather than starting a new ADC scan. Queued ordinary mutations are checked again at dispatch.
- Normal `runScan()` is not marked native-busy in the frozen snapshot. A Start arriving during the ordinary 500 ms scan queues until that main-thread scan completes, then receives fresh admission checks. It therefore avoids a busy rejection on every harmless scan. Native LoRa TX/RX, calibration and network operations do mark busy; a Start racing those can be explicitly rejected and require a user retry. Admission latency and real radio duty cycle remain physical usability gates.
- The session lease deliberately spans recording, Pause, replay, Stop finalization and final disconnection. While leased, native ADC recovery, normal scan, radio transactions, calibration and legacy MQTT scanning yield. Main-loop WDT/service, power reconciliation, cached environment service and 24 V fan policy still run.
- `refreshRuntime()` computes mutable native readiness on the main thread; worker Hello uses cached readiness plus atomic busy. Session profile metadata is frozen while leased and refreshed only when unleased. Calibration/binding mutators are rejected while leased.
- AP is retained by the normal offline-network helper and station reconnect uses AP+STA after workflow startup. A station association can still move the shared radio's AP channel, so actual reconnection/replay behavior needs a device test.
- Loss of 24 V invalidates workflow readiness; normal battery reconciliation/shutdown continues rather than artificially holding the device awake for Wi-Fi.
- Allocation/startup failure must leave normal native operation available. Workflow-only allocation uses nothrow; full RAM/socket startup behavior remains a build/device gate.

## Deliberate recovery gate and limitations

Unacknowledged retained samples do not expire into silent deletion at five minutes: acquisition stops with an incomplete reason and keeps RAM replay available. If the client disappears before durable ACK/drain/summary, the lease remains held until that same session reconnects and finishes recovery. This is a deliberate data-protection gate, not a mutex deadlock. Consequently Stop+Disconnect is a normal-controls recovery path only after delivery succeeds. There is no protocol command to abandon retained data; power cycling loses RAM by the already approved requirement. The manual must not promise that Disconnect alone always restores mutating COM controls.

Pause stops acquisition, and replay/finalization also suspend native acquisition under the lease. Alarm state during those intervals is the most recent valid state, not evidence of continued live sensing. The current source does not promise concurrent LoRa TX while wireless recording. Native mode behavior resumes after lease release.

Native `SET_DEVICE_ID_JSON` defaults to reboot. If an external caller explicitly sets `reboot=false`, native runtime ID changes while the workflow's copied device ID/SSID remains the boot identity until restart. Document restart for hotspot identity changes; do not silently rewrite the established native command semantics.

Stored native Dataset mode initializes station/MQTT before starting the AP at the end of setup. `GLD_WIFI_TIMEOUT_MS` is 15,000 ms (`firmware/config/GldConfig.h:48`). With no station, that adds approximately 15 s to the pre-existing hardware diagnostic/profile/sensor boot work; the new MQTT gate skips MQTT entirely without a station. If the station is reachable but the broker is unavailable, PubSubClient additionally has a 15 s default MQTT response timeout, plus underlying DNS/TCP connection time. This is not an overall measured boot bound. The manual should allow boot completion before declaring the hotspot absent; real boot timing and watchdog behavior remain device gates.

## Frozen source and verification

SHA-256, confirmed unchanged before and after the focused checks:

| File | SHA-256 |
| --- | --- |
| `firmware/gld/src/GldUnifiedMain.cpp` | `2b93d489b873d173faa008474c7d307aa83af21ed80c9dca3e129a93ebd7c0a6` |
| `firmware/gld/src/GldDatasetWorkflowWifi.cpp` | `71493a20a62233a8ce7e3e3168ac1573c84039a03a8b3d2f4051606899a808c5` |
| `firmware/gld/include/GldDatasetWorkflowWifi.h` | `b8222a17ffb3bf3b0d39d4b2b5271366bd2b2f1ea88a53891a4c5ff4d8213888` |
| `firmware/tests/test_dataset_workflow_source.py` | `e61c096c688b89f625e15e95ef7f484d300d8e5e641b179e39868c0f70467a52` |

Independently rerun with the bundled Python, all passed:

- `test_dataset_workflow_source.py`: 22 source-contract tests, including preserved normal branch/protected inputs, main-thread ownership, serializer projection and admission protections.
- `test_dataset_replay_source.py`: 18 source-contract tests.
- `test_dataset_workflow.py`: 38 inert backend/protocol/durable CSV tests.
- `test_workflow_routes.py`: 4 inert route/admission tests.
- `firmware/gld/tests/test_alarm_control_contract.py` executed directly: PASS. An initial unittest-discovery invocation discovered zero tests because this file uses a standalone `main()`; that invocation is not counted as passing coverage.

The Python backend tests exercise simulated transport/storage rather than this C++ binary. Regex/source contracts supplement execution-path inspection and do not execute ADC, NN, FreeRTOS or socket scheduling.

## Acceptance gates

| Gate | Required evidence |
| --- | --- |
| Non-workflow regression | Preprocessed/stripped native branch unchanged plus focused alarm/nulling tests. |
| Source concurrency | Single main-thread ADC/NN owner; worker queue/socket only; Pause/Stop ACK after capture. |
| Idle normal COM | Info/Status/Telemetry, config, nulling/QC, bind, LoRa mode/TX, alarm manual/AUTO, sleep/restart retain normal behavior when unleased. |
| Standalone Wi-Fi | Stored Inference and stored Dataset boot modes, configured station unavailable, AP client can Start without reconnect starvation. |
| CSV checkbox off | Native NN/AUTO continues, wire prediction projects disabled/null, raw eight-sensor CSV remains accepted. |
| CSV checkbox on | Valid same-frame prediction/class/confidence, approval/binding gates, unsupported Model 2 inference remains unavailable. |
| Alarm continuity | Valid non-clear alarm remains steady across Start, Pause/Continue, Stop/delivery and Disconnect; actual invalid frame follows native invalid policy. |
| Durable replay | 500 ms cadence, disconnect/reconnect before 5 minutes, exact contiguous sequence/CSV count, no duplicate rows, explicit overflow/timeout failure. |
| Stop/COM handoff | Summary after durable ACK prefix, Stop confirms target CSV, Disconnect releases lease, subsequent native mutation accepted. |
| Power | External 24 V path and loss/restoration policy; no unintended CLR/service hold/default mode rewrite. |

Compilation, real-device timing, Wi-Fi AP visibility, GPIO48 level, LoRa behavior, NVS retention and end-to-end CSV delivery are **not verified** by this source review. User confirmation is required before compiling; no upload is implied by compile approval.
