# GLD1 Model 1 — batas 30 kandidat Confirm

Last tracker heartbeat: 2026-10-20 12:06:10 +07:00  
Last evidence update: 2026-10-20 12:06:10 +07:00

## Progress dashboard

| Scope | Progress | Status | Note |
|---|---:|---|---|
| **Overall goal** | **95%** | Active — diagnosis required | Firmware/package and one physical Confirm 30 run are evidenced; its profile did not pass quality gates, so independent quality closure remains. |
| Phase 1. Design and baseline | 100% | Done | Backup and independent candidate-selection review complete. |
| Phase 2. Implementation and simulation | 100% | Done | Actual-service and focused regression tests passed; hardware remains separate. |
| Phase 3. Build and package | 100% | Done | Final build, manifest, provenance, embedded model and package isolation pass. |
| Phase 4. Physical validation | 67% | Active — diagnosis required | COM7 identity/read-back, non-reset upload and physical nulling run complete; full quality pass did not occur. |

## Progress calculation

`20% × phase 1 + 40% × phase 2 + 25% × phase 3 + 15% × phase 4`. Items in each phase have equal weight.

| Phase | Weight | Progress | Status | Closure evidence |
|---|---:|---:|---|---|
| 1. Design and baseline | 20% | 100% | Done | Candidate selection review and verified package backup. |
| 2. Implementation and simulation | 40% | 100% | Done | Actual-service bounded search and failure regressions pass. |
| 3. Build and package | 25% | 100% | Done | GLD1 package integrity and other packages preserved. |
| 4. Physical validation | 15% | 67% | Active — diagnosis required | Read-back/upload completed; full 8-channel nulling was attempted but failed closed at 1/8. |

## Issue register

| ID | Status | Evidence | Closure / next evidence gate |
|---|---|---|---|
| C30-1 | Solved in software | Actual-service tests count 30 scan points in long GLD1 bracket; non-target retains 75. | Hardware timing and accuracy remain unproven. |
| C30-2 | Deferred | Simulated good point in omitted gap fails closed; 30-point limit may miss a valid/better candidate. | Analyze operator's physical result and independent reference. |
| C30-3 | Solved | Seven previous package files backed up; 159 other package files match pre-build fingerprint. | Retain backup for recovery. |
| C30-4 | Deferred | Old NVS profiles are not automatically revalidated; physical accuracy is not proven. | Full operator nulling and independent verification. |
| C30-5 | Open — physical quality gate | First physical Confirm 30 run ended `PartialSuccess`, only MQ7 passed; seven channels were rejected for unstable crossing/final readings. | Diagnose live measurement stability before any retry; do not loosen gates or persist partial results. |

### Phase 1 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 1.1 | Review cap behavior and risks | 100% | Done | Edge cases added to test | Independent review confirms scoped scan and endpoint preservation. |
| 1.2 | Preserve package baseline | 100% | Done | Verify rollback after build | Seven files copied to `tmp/gld1-model1-pre-confirm30-20261019-1716`, hashes match. |

### Phase 2 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 2.1 | Implement isolated candidate cap | 100% | Done | Independent review | Cap scan to 29 nearby codes plus bracket endpoint if outside. |
| 2.2 | Verify bounded scan and failure checks | 100% | Done | Physical verification remains deferred | Native proves endpoint success, omitted valid point fails closed, ADC/DAC and final failures. |
| 2.3 | Protect other profiles and paths | 100% | Done | Confirm other package hashes after build | Legacy confirm 75 points; 11 nulling, alarm, UI and 8 package-validator checks pass. |

### Phase 3 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 3.1 | Build GLD1 Model 1 | 100% | Done | Physical validation remains deferred | Exact `gld_model_1` build passed; RAM 41.5%, flash 15.9%. |
| 3.2 | Validate package and rollback | 100% | Done | Physical validation remains deferred | Manifest, uploader, model provenance, marker, firmware hash and non-target hashes pass. |

### Phase 4 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 4.1 | Reconnect and identify COM7 | 100% | Done | Upload package without Reset NVS | Bridge connected COM7 and GET_STATUS identifies device 1001. |
| 4.2 | Upload and run Confirm 30 nulling | 100% | Done — quality gate failed | Physical log summary and preserved-profile read-back | Non-reset upload succeeded; full run ended PartialSuccess (1/8), no new profile saved. |
| 4.3 | Independent calibration quality | 0% | Waiting — diagnosis required | Stable live readings and repeatability | Do not retry until the observed instability is understood. |

## Protected baseline

GLD2/GLD3, other GLD1 model profiles, alarm, LoRa, upload flow, NVS, bindings and active hardware are protected.

## Non-negotiable scope lock — 2026-10-20

Only the GLD1 nulling algorithm/process may be inspected or changed. The following are expressly out of scope: GLD2/GLD3; alarm; LoRa; AES/provisioning; runtime sensor/model/inference/dataset behavior; upload and Operator Hub behavior except replacing a changed GLD1 firmware package artifact; UI; serial protocol; NVS outside existing GLD1 nulling profile/config data; board pins, hardware drivers, and other device profiles. Any prospective change that crosses this boundary must stop for user direction before it is made.

## Current work / agent state

| Sub-agent / worker | Active work item | Started at | Elapsed | Progress | Activity / state |
|---|---|---|---|---|---|
| Codex | 4.2 physical execution complete | 2026-10-20 12:06:10 +07:00 | 00:19:52 | 100% | Upload succeeded without NVS reset. Full nulling ended `PartialSuccess` (1/8); failed-channel retry is available but deliberately not invoked pending diagnosis. Existing profile ID 3 and binding remain unchanged. |

## Evidence log

- 2026-10-19 17:16:28 +07:00 — User requested 30 candidates per confirm bracket; independent GLD review requested. Current device testing is user-controlled; no hardware access.
- 2026-10-19 17:16:55 +07:00 — Verified all seven current package files against backup `tmp/gld1-model1-pre-confirm30-20261019-1716`; no firmware replacement yet.
- 2026-10-19 17:17:51 +07:00 — Actual-service native tests pass for a maximum of 30 GLD1 scan points, retained far endpoint, low/high DAC boundaries, hard errors and final checks. Legacy-path actual confirm scans 75 points. Initial test exposed a test-double injection assumption and a mistaken expected omitted count; both corrected. Heartbeat SLA breach: observed 56 seconds since previous update while implementing and running iterative native tests; no timestamps backdated.
- 2026-10-19 17:18:21 +07:00 — Native tests also prove the far endpoint can succeed after independent verification and a valid point in the omitted gap fails closed. Nulling source suite 11/11, alarm contract, UI errors and uploader validators 8/8 pass. Pre-build 159 non-Model-1 package fingerprint `4A33E2F34377924632480FC01F434E65975736B68A7FEB2A5E26DB151EC303C2`.
- 2026-10-19 17:19:02 +07:00 — Initial Model 1 build succeeded; independent GLD review confirms monotonic, unique in-range points and preserved endpoint/legacy path. Review requested unambiguous scan-limit marker and 30/31-point boundary cases before final release. Package post-build hook refreshed Model 1 only; provenance must be restored and verified after final rebuild.
- 2026-10-19 17:19:43 +07:00 — Clarified marker as `NULLING_CONFIRM_SCAN_MAX_POINTS=30`, corrected outdated comment, and added actual-service tests for exactly 30 and 31 points plus low-rail duplicate-avoidance. Native target and legacy tests pass; final GLD1 rebuild is running.
- 2026-10-19 17:20:12 +07:00 — Final `gld_model_1` build and actual-package validation passed; firmware SHA-256 `326992d5b6318a69d70f18df026bfa13b394e3167c124f44c9b3b7497f58aa83`, binary equals build, manifest/preflight/uploader/marker/embedded model/provenance valid. Native tests and 11 nulling tests re-passed; 159 non-Model-1 package files retain fingerprint `4A33E2F34377924632480FC01F434E65975736B68A7FEB2A5E26DB151EC303C2`. No COM, hardware upload, NVS or binding action; accuracy, safety and repeatability not established by simulation.
- 2026-10-20 11:42:49 +07:00 — User requested continuation. Read-only Windows and bridge checks show `USB-SERIAL CH340 (COM7)` is present and bridge is active but every GLD bridge slot is disconnected. Heartbeat SLA breach: 18:22:37 elapsed since prior tracker heartbeat while the goal was waiting for external/user action; no timestamp was backdated. Next action is user-authorized reconnect/read-back only.
- 2026-10-20 11:43:58 +07:00 — COM7 reconnect initially failed before serial access because `127.0.0.1:5174` actively refused connections; the GLD bridge process was no longer listening. Restarted only the existing local GLD bridge, verified `gld-operator` health and serial capability. No COM opened yet, no firmware upload/reset/nulling/binding.
- 2026-10-20 11:46:18 +07:00 — Opened COM7 through the restarted bridge and read `GET_STATUS`: device ID 1001 responds in inference mode. Existing Model 1 identity and binding are present, but `profileReady=false` and `inferenceValid=false`; no reset, model binding, alarm or nulling command was sent. Proceeding under user authorization to the verified package upload without Reset NVS.
- 2026-10-20 11:48:30 +07:00 — Read the local `gld_model_1` upload package through the same bridge: manifest protocol is `0.2.0` and it contains only `bootloader.bin`, `partitions.bin`, `boot_app0.bin`, and `firmware.bin`. No package data was altered. The next controlled state change is the authorized upload with `resetNvs=false`.
- 2026-10-20 11:50:15 +07:00 — Upload endpoint completed successfully for COM7: environment `gld_model_1`, firmware version `0.8.36`, protocol `0.2.0`, four verified flash files, and `nvsReset=false`. The uploader owned and closed serial access as designed; reboot reconnect/read-back is required before any nulling command.
- 2026-10-20 11:52:10 +07:00 — Reconnected after the update and read post-reboot `GET_STATUS`: ID remains `1001`; boot reports ADS, DAC, radio and ML ready; all eight current DAC read-backs verify. Existing model binding was preserved. Profile readiness/inference remain false because the active profile does not match the preserved model binding. No bind, alarm or LoRa configuration command was sent. Full nulling is the authorized next action.
- 2026-10-20 11:54:00 +07:00 — `VERIFY_CLEAN_AIR_FOR_NULLING` returned `ok` (no alarm latch was active; acknowledgement recorded). `SET_MODE nulling` then returned `ok` with reboot expected. Device logged the inference-to-nulling mode switch. Full eight-channel nulling is in progress; no model bind, alarm or LoRa command was sent.
- 2026-10-20 11:54:35 +07:00 — Boot log confirms GLD1 started in nulling mode with 8/8 MCP DAC ready. Service began with `avgCount=6`, `confirmCount=8`, `settleMs=5`, `stabilityWindows=3`, `stabilityGapMs=5`, adaptive per-channel stability and existing limits. This records the actual optimized run parameters, not a simulated result.
- 2026-10-20 11:58:20 +07:00 — Live serial log remains in confirm scanning. The latest observed channel-2 candidate was valid but unstable across its verification windows and was rejected; scanning advanced to the next code under `max=30`. That is the intended fail-closed stability behavior. No channel result, NVS save, profile binding, alarm or LoRa change has occurred yet.
- 2026-10-20 11:59:29 +07:00 — Live service reached channel 4 (MQ5). Its exponential bracket advanced from codes 831 to 895 after an unstable recheck; all shown ADC/DAC writes were acknowledged, so this is measurement stability handling rather than an MCP/DAC write fault. Nulling remains active and bounded.
- 2026-10-20 12:00:46 +07:00 — Channel-4 exponential recheck at code 895 subsequently passed, then confirmation scan reached 25 of 30 candidates. The current candidates continue to fail their stability criterion; no NVS profile was saved from a non-stable candidate. Heartbeat cadence exceeded by 17 seconds while a bounded monitor wait returned no output; no timestamp was backdated.
- 2026-10-20 12:01:20 +07:00 — Channel 4/MQ5 exhausted its bounded recovery after confirmation and exponential rechecks; firmware reported `NULLING_CH_FAIL ... crossing_unstable_or_invalid` and advanced to channel 5/MQ4. Channel 5 has at least one stable confirmation observation but remains in progress. No NVS profile save occurred because a full 8-channel pass is required.
- 2026-10-20 12:02:25 +07:00 — Channel 5/MQ4 failed its final `after_read` stability validation (`final_unstable_or_invalid`) after candidate selection; service advanced to channel 6/MQ7. This confirms that the current live issue is measurement stability, not the earlier DAC/MCP acknowledgement failure. The run remains in progress solely to preserve a complete per-channel diagnostic record.
- 2026-10-20 12:03:55 +07:00 — Channel 6/MQ7 reached a stable confirm candidate and a stable final read, producing `NULLING_CH_OK` at DAC 1014. Service advanced to channel 7/MQ6. MQ5 and MQ4 remain failures, so firmware must not persist a partial profile; it continues only to capture all eight channels' outcomes.
- 2026-10-20 12:04:48 +07:00 — Channel 7/MQ6 failed final stability (`final_unstable_or_invalid`) after an accepted exponential bracket. The service is now on channel 8/MQ2 and has resumed its exponential search after unstable rechecks. Because at least MQ5, MQ4 and MQ6 failed, a complete profile cannot be saved by design; existing NVS profile/binding remains protected.
- 2026-10-20 12:06:10 +07:00 — Physical Confirm 30 run completed: `PartialSuccess`, 1/8 channel successful, and firmware armed operator retry only. MQ7 passed at DAC 1014; MQ8, MQ135, MQ3, MQ5 and MQ2 failed unstable crossing rechecks, while MQ4 and MQ6 failed final stability reads. Boot/read-back after the result shows all 8 MCP/DAC write/read-back checks pass and profile ID 3 was reapplied; no new profile was saved, no model binding changed, and alarm/LoRa settings remained unchanged. Device uptime at final status was 504.675 seconds; this bounds reboot-to-final-result timing but does not alone isolate pure calibration duration. No retry was sent because persisting a complete, stable profile must remain the quality gate.
- 2026-10-20 12:07:00 +07:00 — User imposed a non-negotiable scope lock: future work may address GLD1 nulling algorithm/process only. Any change touching other firmware profiles, runtime subsystems, UI/protocol/upload, or non-nulling NVS must stop for explicit user direction.
