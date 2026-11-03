# Workspace Connect audit — host side, revision 7

Date: 2026-11-03. Owner: Integration_Agent. Read-only source audit and an inert in-memory fixture reproduction. No COM, GLD socket, Wi-Fi/route change, credentials, service control, compiler, firmware, package or source edit was performed. The fixture used a fake platform/fake WebSocket peer and sent no Start; no CSV/ledger/output directory was created. Root separately owns live route/TCP/one authenticated Hello observations.

## Finding

The Workspace error does not identify the failed layer. `DatasetWorkflowService.connect()` wraps Windows join, authenticated WebSocket transport, protocol validation and device readiness in one catch-all (`apps/gld-operator/dataset_workflow.py:243`–`:262`). Every exception becomes:

> GLD belum terhubung/siap. Periksa hotspot, password, 24 V, dan profil nulling.

It deliberately drops the original exception (`from None`). Consequently a Windows screenshot showing association with GLD-DATASET-1002 proves Wi-Fi association only; it does not prove the route to 192.168.4.1, TCP port 81, authentication, protocol 3, selected identity or raw capture readiness.

Production-model approval and prediction readiness are separate from raw connection readiness. **An unapproved model by itself does not prevent raw Connect.** Do not attribute the current connection failure to Model 2 approval or binding/prediction without inspecting the received Hello.

## Exact connection sequence and failure classes

1. Service resolves its private credential, validates the selected scanned device and preserves the existing legacy/COM exclusion before it reaches this method. The current root report says all collectors and COM are disconnected, so the ordinary admission conflict is not indicated by the observed state; this reviewer did not query live devices.
2. `WindowsWorkflowPlatform.join()` checks the native WLAN association. If an enabled adapter is already associated with the exact SSID, it returns immediately (`workflow_platform.py:262`–`:264`); it does not verify IP assignment, routing, TCP or the GLD service. Otherwise its native join path has separate safe errors for adapter/location access, missing hotspot, profile policy/conflict, failed association and timeout.
3. The collector opens **ws://192.168.4.1:81/dataset**, with an 8 s default transport/Hello timeout, Basic authentication, proxy bypass and redirects disabled (`wireless_dataset_replay.py:234`–`:259`). HTTP 401/403 maps to `authentication_rejected`. Other transport exceptions map to `connection_failed_check_hotspot_and_password` without reflecting arbitrary exception text/headers.
4. `WorkflowCollector._hello()` first requires protocol 3 and its Pause/Continue/replay/prediction capability shape, valid safe model metadata and transition sequence (`wireless_dataset_workflow.py:48`–`:70`). It delegates the full base Hello validation to Replay, then checks selected device ID. An old stage1/protocol2 image can advertise a matching SSID yet fail `incompatible_hello` here.
5. Base Hello validation requires canonical eight-sensor feature order, interval 500, retention 300000, capacity 640, a real boolean ready, valid boot/device identity and valid sequence prefixes (`wireless_dataset_replay.py:189`–`:232`). It rejects **nulling_profile_id=0 as invalid_profile even when ready=false** before the model/device snapshot is committed.
6. A valid Hello with active acquisition, retained data or Pause owned by a previous backend is refused with `retained_session_requires_original_backend`; this is an important data-protection fence. Do not clear it or manufacture a new session to make Connect look successful.
7. A valid Hello may still say ready=false. Service currently disconnects that candidate and raises the generic error. The collector's safe `device_not_ready` detail remains internal, while the terminal reason can be blank. A valid raw-ready Hello with unavailable prediction still connects normally and merely disables prediction inclusion.

## What diagnostics already exist, and what is hidden

- Collector snapshots already include `error`, `terminal_reason`, device/boot identity, profile, model metadata, prediction availability, counts, session identity, sampling/Pause and recovery state.
- Service `_on_engine()` preserves the engine snapshot internally (`dataset_workflow.py:523`), but the public snapshot uses the service's generic `self.error` rather than the engine error (`:137`–`:166`). Its `reason` exposes only `engine.terminal_reason`. This is enough for fatal protocol/auth errors but loses readiness-only detail.
- `_reason()` intentionally allowlists device terminal strings; the firmware's broad initial reason `requires_24v_and_saved_valid_nulling_profile` is not an allowed terminal code and is not preserved for a non-incomplete Hello. Do not expose arbitrary device text as a shortcut.
- The UI displays the HTTP failure message and/or snapshot.error (`js/dataset-workflow.js:137`, `:231`). It does not explain snapshot.reason. Thus the precise safe code can exist in the service state without being visible in the Workspace message.
- If the failure occurs in Windows join before a new candidate is made, internal engine metadata can belong to an older attempt. Selected SSID/device alone is not authenticated current-device evidence. A fresh authenticated Hello must establish it.

## Inert actual-code reproduction

Executed the real service/collector with existing fake platform and WebSocket fixtures, no worker thread and no Start:

| Fixture condition | Connect | Public error | Public reason | Engine error |
| --- | --- | --- | --- | --- |
| profile 0, ready=false | Refused | Generic message above | invalid_profile | invalid_profile |
| profile 1, ready=false | Refused | Generic message above | empty | device_not_ready |
| valid profile, raw ready=true, production_approved=false, prediction_ready=false | Accepted | empty | empty | empty |

The accepted third case had prediction_available=false. This confirms the model/prediction approval distinction in actual host code, not just a source inference.

## Raw-ready firmware gate relevant to root's Hello

Current source `datasetWifiReady()` (`firmware/gld/src/GldUnifiedMain.cpp:7139`) requires external power and non-battery mode, no armed nulling retry, no fullscale sweep/pending shutdown, native mode not Nulling, native Dataset state Idle, ADS and DAC ready, an applied saved nulling profile and profile ID > 0. It does **not** require production approval, model binding or prediction readiness. The initial firmware Hello exposes only a broad reason for this gate; without extra readback its false components cannot be distinguished confidently.

## Smallest repair recommendation

Do not change admission, protocol validation, firmware raw-ready gates, retained-session recovery or CSV/ACK semantics as part of error diagnosis.

Add a narrow service-side connection diagnostic with a phase and allowlisted safe code, mapping the already controlled protocol/collector codes to clear Indonesian messages. Preserve the collector's error before disconnecting a ready=false candidate. Map known Windows join errors separately without passing through arbitrary network exception strings. Expose the safe diagnostic in the public snapshot and HTTP error; have the Workspace render it. A valid not-ready Hello should continue to prevent file choice/Start, while the message identifies device readiness rather than telling the operator to guess the password.

Suggested distinctions: Windows association, endpoint/timeout, authentication rejected, wrong protocol/package, selected identity mismatch, saved profile unavailable, device not ready, and an existing retained session requiring its original backend. Keep raw Hello/auth headers/passwords out of user messages, logs and diagnostics. Root's live observation should determine which one applies before any further source/firmware action.

No repair was applied in this audit. Current GLD firmware version/model and the live cause remain unproven by this worker; root's fresh sanitized Hello is the next decisive evidence.

## Revision 8 — authorized host diagnostics implemented

The parent subsequently authorized a bounded implementation in `dataset_workflow.py` and `wireless_dataset_workflow.py`, plus tests. The preceding sections record the read-only diagnosis before that authorization. No firmware, package, compiler, live endpoint, COM, Wi-Fi configuration, credential, service or Hub operation was performed by this worker.

- Workflow-only `_open()` now classifies **initial** TimeoutError/WebSocket timeout and known OS refused/unreachable/reset failures into fixed safe protocol codes. The `recovering=True` path re-raises the original exception unchanged, preserving existing retry/backoff/fatal behavior. Legacy direct/replay collectors are unchanged.
- Service Connect maps only fixed allowlisted codes to Indonesian messages. It exposes `connection_diagnostic={phase, code, message}` in the existing state snapshot and uses that same safe message in the existing HTTP exception/error display. The existing Workspace already renders the error, so no UI or endpoint change was required.
- Phases distinguish Windows association, data transport, authentication, protocol, selected identity, device readiness and retained-session ownership. Ready=false/retained reason is captured before disconnect. A failed new engine allocation cannot accidentally reuse a previous attempt's error.
- Unknown platform/transport exception text, raw replies, authentication headers and password values are not reflected. Known error codes drive the message; arbitrary error strings fall back to a fixed safe message.
- Existing admission, candidate disconnection, file choice/Start gates, profile validation, retained ownership, cleanup, durable CSV/ACK, Pause, replay and session semantics remain unchanged. A valid raw-ready but prediction-unapproved GLD still connects; unavailable prediction remains optional.

### Host verification

All passed:

| Test suite | Count |
| --- | ---: |
| New Connect diagnostics | 10 |
| Existing Dataset workflow | 38 |
| Existing Workflow adversarial | 17 |
| Existing replay | 22 |
| Existing replay wire | 2 |
| Existing legacy direct collector | 24 |
| Existing Workflow routes/admission | 4 |

The 117 Python tests include actual service refusal for initial timeout (factory and Hello read), refusal, unreachable/reset, authentication, unknown exception, WLAN join, invalid profile 0, valid-profile not-ready, wrong selected identity, active/paused retained ownership, malformed/wrong protocol/model metadata, secret sanitization, successful retry clearing diagnostics and unapproved prediction accepting raw Connect. Recovery tests confirm transport exception objects/types remain unchanged. The existing Workflow UI test also passed. Scoped diff check passed. These are inert host/fixture results, not live GLD proof.

### Frozen host SHA-256

| File | SHA-256 |
| --- | --- |
| `apps/gld-operator/dataset_workflow.py` | `db756a3f5fd684639af4716a3d3d5f440a1f05ddd2d345085d6a10dccf0d8406` |
| `apps/gld-operator/wireless_dataset_workflow.py` | `9e1f69ecbb17d692be03485dd6d9e255286cceb149b1310edc0b2ddc0868e5fd` |
| `apps/gld-operator/tests/test_workflow_connect_diagnostics.py` | `acf0f038da90047732a4d382172d02cf52dc6a7a6c094b3f5f21838116b67679` |

## Independent firmware timeout-delta review

The GLD source owner separately supplied a stable `GldDatasetWorkflowWifi.cpp` SHA-256 `fcd4195db2e8f39d15c5b3dd898bc346478c53ea7e55441ffeeda8eec5ef0bfc`. This reviewer read that source and the actual installed vendor/framework files; no firmware edit or compilation was performed.

The new concrete `CheckedServer::loop()` uses the same running/YIELD/accept order as installed WebSocketsServer, normalizes each accepted `WSC_HEADER` client's Stream timeout after vendor acceptance, then invokes `WebSocketsServerCore::loop()` for the first header read. Protected `_clients`, `_runnning` and `handleNewClients()` are accessible in the actual installed headers; calls on the concrete `CheckedServer socket` select the subclass method without requiring a virtual override.

Installed WebSockets `newClient()` passes `WEBSOCKETS_TCP_TIMEOUT` (1000 ms) into ESP32 `WiFiClient::setTimeout(uint32_t seconds)`, which multiplies by 1000 for both Stream and client timeouts. The adapter correctly converts with ceiling to seconds while leaving the vendor millisecond macro unchanged. The getTimeout comparison uses milliseconds, consistent with the installed Stream API. No header is parsed during the synchronous ESP32 acceptance path before normalization; Core parses it afterward. No vendor/global timeout macro, authentication, data queue, capture gate or ownership code is changed by this delta.

**No blocking source finding.** Independently reran the seven timeout fixture/dependency-contract tests: PASS. The fixture executes a modeled scheduling sequence derived from production ordering/conversion and checks actual installed APIs; it is not C++ binary or ESP32 execution. Compilation and actual fragmented/aborted header followed by a fresh authenticated Hello remain required. Real eight-sensor/CSV acquisition and interruption/replay must retain their own acceptance evidence.

Root owns the next approval question for three parallel builds, Model 2 upload with NVS preserved, and bounded real connection verification. No such approval or runtime action is inferred from this review. Host diagnostics also require a later user-visible/accessibly launched Hub runtime to load the changed Python source; this worker did not launch or restart it.
