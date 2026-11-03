# Wi-Fi Connect diagnosis: firmware and Hello gates — 3 November 2026

Read-only source review. This child performed no GLD/COM access, TCP/WebSocket probe, credentials read/change, Wi-Fi/network configuration, service action, compile, package or source change. Only this report was written. The parent owns live probing and reconciliation.

## What association proves

Windows association to the advertised GLD SSID proves the ESP AP is reachable at the Wi-Fi link layer. It does **not** prove usable laptop IP/route, TCP port 81, accepted WebSocket authentication/path, compatible protocol Hello, raw acquisition readiness or inference readiness. Internet is unnecessary for this local endpoint.

`beginDatasetWorkflowIfNeeded()` (`GldUnifiedMain.cpp:7254`) starts the AP when external power is detected and the cached power mode is non-battery. It deliberately does not require ADS, DAC or a valid applied calibration before advertising. Startup also checks listener/task allocation, but AP association alone cannot certify subsequent listener/task health or that this is the selected intended device.

## Exact raw readiness gate

`datasetWifiReady()` (`GldUnifiedMain.cpp:7139`) requires all:

```text
!batteryPowerMode
readGldExternalPower()
!nullingRetryArmed
!fullScaleSweepActive
!powerTransitionShutdownPending
currentMode != NULLING
legacy datasetState == Idle
adsReady && dacReady
nullingProfileApplied && nullingProfileId > 0
```

The Hello at `GldDatasetWorkflowWifi.cpp:281` uses **`state.ready`**, cached from that gate in `begin()` and refreshed by `refreshRuntime()` at the head of the main loop. It is not masked by `nativeBusy` and is independent of `prediction_ready`.

Model approval, missing/mismatching binding, ML initialization and runtime DAC readback are additional **prediction** gates (`datasetWorkflowPredictionReady()`), not raw Connect gates. A stale model binding by itself therefore cannot explain failure to connect for raw eight-sensor Dataset acquisition. Do not reset/bind/null merely to test that hypothesis.

AP can remain visible after a power-mode transition because an already-running AP is not immediately removed when raw readiness falls. Cached battery mode is reconciled with three stable samples at one-second intervals; actual external-power GPIO is also checked directly in the raw gate. Profile loading/application can fail while AP still starts: missing/incompatible saved profile produces ID 0; failed DAC application also clears the applied ID. Native ADS recovery can change readiness later. During a long native operation the cached Hello may describe the previous main-loop snapshot; native busy by itself only rejects Start/Continue admission.

## Why the UI message is inconclusive

`dataset_workflow.py:251–259` catches all candidate-connect exceptions and replaces them with the same “GLD belum terhubung/siap…” message. Distinct source-supported possibilities are:

1. No route/TCP/listener or timeout; rejected Basic authorization (`gld` user), wrong `/dataset` path, or occupied single WebSocket client.
2. Wrong firmware/protocol, unexpected selected device identity, invalid Hello fields/model metadata/feature order/capabilities, or malformed prefix/session state.
3. **Profile ID 0**: the protocol collector rejects Hello as `invalid_profile` before simply treating `ready=false` as a readiness result (`wireless_dataset_replay.py:200–202`).
4. Valid Hello with `ready=false` from one of the raw gates above.
5. Valid raw-ready Hello but a sampling/paused/retained session requiring the original backend: the collector deliberately changes its effective `ready` to false, even when firmware `ready=true`.

The parent's “all Hub wireless sessions disconnected, zero samples” rules out those local services actively collecting, but does not alone establish firmware retention state or exclude another/stale firmware-side client. Capture actual Hello before attributing the failure to calibration or power.

## Minimal read-only evidence to distinguish cases

First record laptop associated SSID, IPv4 address/route to `192.168.4.1`, TCP `192.168.4.1:81` result, WebSocket HTTP status and the unmodified first Hello. Use the existing authenticated endpoint without sending START/STOP/ACK or calibration/configuration commands. Do not run a probe alongside a Hub connection competing for the single client.

Hello fields to retain: `protocol`, `device_id`, `boot_id`, `ready`, `reason`, `nulling_profile_id`, `prediction_ready`, model profile/scaler/runtime/approval/output/class map, capabilities/feature order/interval/retention/capacity, and `session_id`, `sampling`, `paused`, `incomplete`, `total_samples`, `oldest_seq`, `acked_next_seq`, `buffered_samples`, `transition_seq`. Close the diagnostic socket afterward.

If the parent already has an authorized fresh native status read/cache, correlate:

- `mode`, `power.mode`, `power.externalPower`, source ambiguity/STP and battery-session state;
- `bootHealth.adsReady`, `dacReady`, `nullingProfileApplied`;
- `model.activeNullingProfileId` and `dataset.nullingProfileId`;
- `nulling.retryArmed`, `dataset.state/step`, recovery ADS counters/reason and `bootRecoveryArmed`;
- model/binding/ML/DAC readiness separately, to distinguish optional prediction failure.

`fullScaleSweepActive`, raw cached `batteryPowerMode` and `powerTransitionShutdownPending` do not each have a direct dedicated status field in the inspected serialization. Infer only when supported by the operation/power logs; do not claim one is the cause solely from generic Hello reason. The default not-ready reason groups several gates rather than identifying a specific failed one.

**Audit conclusion:** no specific root cause is established from SSID association plus the generic Hub error. The TCP/authenticated-Hello result is the next decisive evidence. No speculative source or device changes are recommended by this review.

## Addendum: actual TCP failure and fresh USB read-only status

Parent evidence now narrows the layer:

- `local-result.json`, diagnostic v2 at 17:18:40 WIB: associated target SSID and direct `/24` route confirmed; the **first TCP connect to 192.168.4.1:81 timed out after five seconds**. No HTTP authorization, WebSocket Hello or device command was sent. This failure precedes any `ready`/binding/CSV decision.
- Cached device boot log showed listener startup success, applied profile 2 and successful Model 2 binding. That certifies the earlier startup, not current listener health.
- `usb-readonly-status.json`, captured by parent at 17:28:22: GLD1002, Model 2, INFERENCE, external power, approval true, bound/active profile 2, fingerprint match, model profile ready and inference valid, all sensor/ML/DAC prerequisites ready, blocker `none`, uptime 2,922,530 ms. Native main loop is alive. Parent closed COM afterward. Since command admission reads `ownsSession()` under the module mutex, successful fresh GET_STATUS also argues against that mutex being permanently held at the response time.

The earlier diagnostic v1's later Python import failure suggests its preceding TCP step may have succeeded, but no partial-stage success record was saved. Treat initial TCP success as an inference, not a proven recorded result. The fresh evidence does not justify changing model binding, calibration, power policy or NVS.

## Actual dependency/runtime inspection

Model 2's release receipt points to `firmware/.pio/workflow-libdeps-model2/gld_model_2_dataset_workflow_wifi/WebSockets` version 2.6.1. Its `WebSocketsServer.cpp` matches the regular Model 2 dependency copy byte-for-byte, SHA-256 `33999868afc019706d65f42bccd7e94a1933a3fbdac0ae5d51398a1ee7044f73`.

1. **Listener lifetime:** `CheckedServer::beginChecked()` only reads `WiFiServer::operator bool()`, which returns its latched `_listening` flag. `available()` in the workflow module only reads `initialized`; neither checks ongoing file-descriptor validity, transport-task progress nor acceptance. Arduino WiFiServer binds INADDR_ANY, calls `listen(..., 4)` by its default constructor, and uses nonblocking accept. This SDK enables `TCP_LISTEN_BACKLOG=1`. A stopped/stalled accept loop can therefore fill its pending queue and later connections can time out while the AP remains visible. This mechanism is source-supported, not proof the queue is actually full now.
2. **Single WebSocket slot:** while transport is healthy, a second client is still TCP-accepted then immediately closed when no slot is free. Occupying the one WebSocket slot alone does not explain a SYN/connect timeout. It can explain upgrade rejection/closure after TCP succeeds.
3. **Guard audit:** socket `loop()`, sends and disconnects are called outside the workflow mutex. Synchronous library callbacks acquire it only after the caller has released it; process/status helpers under the mutex queue data without calling socket operations. Capture/prediction occurs outside the mutex on the main thread. No definite recursive-mutex/deadlock path was found in those inspected routes. PortMAX_DELAY waits still lack runtime timeout telemetry, so source inspection cannot exclude corruption or an unforeseen task failure.
4. **Task lifetime:** the transmitter is created with a 12,288-byte stack and priority 1; no later normal-mode/bind path deletes it. Only startup-failure cleanup deletes it. There is no progress counter, stack watermark, alive/rebind supervision or socket health field exposed by this module. A native main-loop response therefore cannot certify transport-task progress.
5. **AP changes:** Arduino `WiFi.mode()` returns immediately when the mode is unchanged; AP/AP_STA changes use `esp_wifi_set_mode`, while WIFI_OFF stops Wi-Fi. The application preserves AP during its offline/station helpers. No actual event log proves a later AP/interface reset or stale lwIP listener here. Do not present that alternative as an established cause. Native INFERENCE normally has no repeated station reconnect loop.

### Concrete long-header timeout defect

The following units mismatch is verified in the **actual release dependency and installed ESP32 framework**:

```text
platformio.ini: WEBSOCKETS_TCP_TIMEOUT=1000                 # library milliseconds
WebSocketsServer.cpp:464:
    client->tcp->setTimeout(WEBSOCKETS_TCP_TIMEOUT)
ESP32 WiFiClient.cpp:325:
    setTimeout(uint32_t seconds)
    Client::setTimeout(seconds * 1000)
    _timeout = seconds * 1000
```

The accepted client's Stream timeout becomes **1,000,000 ms (1,000 seconds, approximately 16.7 minutes)**, not one second. `WebSocketsServer.cpp:705` calls `readStringUntil('\n')` when any header bytes are available. ESP32 `Stream::readStringUntil()` uses `timedRead()`; the latter waits until its Stream timeout and does not terminate early on socket disconnect. Thus a partial HTTP line without its newline, followed by silence/disconnect, can occupy the transmitter for that long. During that stall it cannot accept, heartbeat, deliver Hello or drain queues, and subsequent pending connections can fill the backlog. This is a definite implementation defect and a plausible mechanism for the observations. **The captured evidence does not prove a partial header was the triggering event on this GLD.**

The normal WebSocket frame reader instead checks disconnects and the millisecond macro in its own loop; do not claim that every partial frame necessarily suffers the same 1,000-second header wait. Changing the global macro to `1` is also incorrect: that would turn unrelated library read/write loop deadlines into **1 ms**.

## Targeted repair recommendation — not implemented under this audit

Prefer a workflow-only `CheckedServer` adapter instead of editing the shared vendor cache or changing the global timeout constant:

1. In this checked-in subclass, provide its own `loop()` used through the concrete `CheckedServer socket` object. Preserve actual vendor ordering: check `_runnning`, yield, call protected `handleNewClients()`, then call `WebSocketsServerCore::loop()`.
2. **Between accepting and parsing headers**, normalize accepted clients' ESP32 `tcp->setTimeout()` to seconds, e.g. ceiling of `WEBSOCKETS_TCP_TIMEOUT / 1000` (currently 1 second). This corrects both Stream/socket timeout units while leaving the vendor macro at 1000 ms. `_clients`, `_runnning` and `handleNewClients()` are protected and accessible from this subclass. Make the normalization idempotent or limit it to header clients.
3. Do not merely shadow `newClient()`: actual `newClient`, `handleNewClient`, `handleNewClients` and `loop` methods are **nonvirtual**. A same-name `newClient` in the subclass will not intercept the base library's calls. A connection-event or HTTP-header-validation callback is too late to protect the first partial header. Calling normalization before the ordinary base loop also leaves an accept/parse race; the order must be explicit in the wrapper.
4. Add a source/host regression proving millisecond-to-second conversion, one-second Stream behavior from actual framework semantics, acceptance-normalization-before-header-read ordering, and preservation of 1000-ms library deadlines. Preserve normal firmware/non-workflow source and model/calibration/package baselines.
5. After approved three-model builds and controlled deployment, test fragmented/truncated HTTP headers, client disconnect mid-header and a following healthy authenticated connection; then repeat normal Dataset graph8/CSV/500 ms/replay and native Running acceptance. Do not call this a verified device root-cause fix before those observations.

This adapter is reproducible from repository source for all three final workflow environments and needs no global dependency patch. If a vendor patch is chosen instead, it must be pinned/version/hash checked, idempotent, environment-specific and applied through the dedicated build preparation mechanism; manually modifying `.pio` caches is not a durable release method. No repair, build or deployment was performed by this audit.
