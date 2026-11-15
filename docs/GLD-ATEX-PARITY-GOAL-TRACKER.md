# GLD ATEX feature parity — checklist

Last updated: 2026-11-14 11:17:43 Asia/Jakarta
Last tracker heartbeat: 2026-11-14 11:17:43 Asia/Jakarta
Last evidence update: synthetic ATEX models 1–3 build 3/3; firmware suite 51/52; simulated partial save plus ID provisioning confirms incomplete recovery. No device or upload.

User preference for this project: delegate independent work to available subagents in parallel when safe, with explicit ownership and protected baselines. This project note is not account-wide memory.

## Progress dashboard

| Scope | Progress | Status | Note |
|---|---:|---|---|
| **Overall goal** | **37%** | Active | Weighted phases below. |
| 1. Baseline and hardware audit | 70% | Waiting for external evidence | Map profile-specific behavior. |
| 2. ATEX implementation | 33% | Waiting for next assigned work | Recovery and physical gates remain. |
| 3. Build and regression | 40% | Waiting for external evidence | Synthetic builds and focused tests pass; hardware remains. |
| 4. Device evidence | 0% | Not started | Physical verification requires explicit upload authorization. |

## Progress calculation

`20% × 70 + 40% × (100/3) + 25% × 40 + 15% × 0 = 37.33%` (rounded 37%).

| Phase | Weight | Progress | Status | Closure evidence |
|---|---:|---:|---|---|
| 1. Baseline and hardware audit | 20% | 70% | Waiting for external evidence | Profile and feature differences documented. |
| 2. ATEX implementation | 40% | 33% | Active | Isolated source and UI paths reviewed. |
| 3. Build and regression | 25% | 40% | Active | Candidate builds and focused tests pass. |
| 4. Device evidence | 15% | 0% | Not started | Explicitly authorized device verification. |

## Issue register

| ID | Status | Evidence | Next gate |
|---|---|---|---|
| A1 | Open | GLD1 fast nulling explicitly excludes ATEX. | Assess ATEX mapping and appropriate nulling behavior. |
| A2 | Open | Shared operator and firmware files contain existing changes. | Preserve baseline and avoid disrupting other work. |
| A3 | Open | Existing GLD1 RX evidence did not observe an actual downlink. | Physical RX and ACK evidence. |
| A4 | Open | Warmup thresholds and integration are not validated. | Preserve existing behavior and identify validation prerequisites. |
| A5 | Open | Workflow owns the acquisition session and returns before native radio service, including on GLD1. Existing GLD1 source does not demonstrate simultaneous Dataset recording and LoRa RX. | Design and verify arbitration without breaking recording, alarms, or radio. |
| A6 | Open | Workflow inference directly uses GLD1-only readiness/alarm behavior; ATEX uses GLD2 alarm/power paths. | Separate hardware-specific policy and test fail-safe behavior. |
| A7 | Open | Model artifacts are board-specific; model 2 approval is based on operator-reported validation, model 3 gas accuracy remains unverified. | Validate model input order, profile binding and real ATEX gas behavior. |
| A8 | Open | An authenticated LoRa mode command can persist replay state and reboot during an active workflow lease, losing volatile replay. | Design safe busy/defer behavior and verify anti-replay, ACK and session recovery. |
| A9 | Open | ATEX TCA mapping differs from GLD1, and existing nulling profiles and model bindings do not identify board or mapping. | Confirm eight physical channels and board-specific profile/binding. |
| A10 | Open | Existing package validator, installer and private credential resolver recognize only GLD1 workflow packages. | Add isolated ATEX package validation/provisioning and test readback without installing synthetic builds. |
| A11 | Open | ATEX Dataset/QC candidates check external 24V mode and live PG; host tests pass. | Verify actual power transitions on board. |
| A13 | Solved | ATEX handler restores saved code on failure and invalidates runtime; host fault/negative controls pass. | Physical DAC/readback evidence tracked under A9. |
| A16 | Open | T16 drain/checked radio integrated and host tests pass; physical timing and operation remain unverified. | Verify integrated build and real board including CH when available. |
| A17 | Open | Legacy gld_atex, ATEX-labelled manifest and known ATEX binary marker are now held; tests pass. Labels/marker are unauthenticated and not complete provenance. | Trusted firmware provenance and hardware identity before release. |
| A21 | Open | Nonce handler and exclusive serial lease integrated; direct API port reservation race host-tested. Legacy firmware bootstrap remains unresolved. | Establish physical identity and a safe first-update procedure. |
| A20 | Open | ATEX-only CS cleanup and fake HAL tests pass; fault state allows recovery restart without proving physical radio idle. | Verify bus/radio physical cleanup and recovery. |
| A19 | Open | Radio start TX/RX packet-type getter may ignore SPI status; TX failure can leave RF switch TX, and aggregate timings remain unbounded. | Checked packet type, bounded cleanup/fault tests; verify hardware timing. |
| A18 | Open | Expert and Hub use exclusive nonce readback on a pinned stream; mocks pass. No authenticated physical identity or guarantee after lease ends. | Test target and migration; keep release closed. |
| A15 | Open | Firmware suite 51/52 after current alarm documentation and test fixture updates; remaining documentation mirror failure may mask further assertions. Prior 8 matched a partial T6 snapshot, not a full pristine baseline. | Audit each behavior and reconcile tests/docs without hiding regressions. |
| A14 | Open | Existing ATEX firmware may report GLD2; hardware profile cannot be inferred from GET_INFO alone. | Plan and validate explicit physical migration without weakening identity checks. |
| A22 | Open | An AES-128 GLD key appeared in session tool output; user informed and no rotation performed. | Coordinate key handling across paired devices before release. |
| A23 | Open | ATEX invalid-NVS load discards non-ID partial fields in RAM and disables auto TX, persisted after provisioning until QC enable; fake-NVS tests pass. Production-function simulated NVS cycle reproduces ID save validating defaults with empty AES and Auto TX OFF; latch is same-boot only, identity/manual TX/key reuse unverified. | Complete transactional recovery, safe identity and physical power-failure tests. |
| A24 | Solved | T39 fixture repair integrated; extracted production service, 15360 airtime comparisons, restart guard and airtime mutation negative controls, and config-failure interaction pass. | Physical RF and timing remain under A16/A19. |
| A25 | Open | ATEX workflow threshold aligned and confidence-0 valid frozen pending supported; frame/CH and 5-profile fake-NVS host tests pass. CRC is not authenticity. | Verify physical device, battery and CH; do not claim model output or cryptographic tamper validation. |
| A12 | Solved | Namespace alias harness corrected; GLD1/GLD2/ATEX plus negative-control mapping test passed. | Physical ATEX wiring still requires separate evidence (A9). |

## Phase 1 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 1.1 | Inventory firmware and UI feature guards | 80% | Waiting for external evidence | Final runtime audit | Profile, workflow and upload guard differences documented. |
| 1.2 | Check board mapping, model and nulling compatibility | 60% | Waiting for external evidence | ATEX physical channel and gas validation | Mapping and board-specific binding gaps documented. |

## Phase 2 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 2.1 | ATEX models, workflow and upload selection | 50% | Active | Production packages and readback | Three synthetic workflow candidates compiled; ATEX UI slots locked. |
| 2.2 | Running, RX continuity, nulling and QC | 40% | Active | Integrate radio scheduler and validate nulling | Running and Dataset RX scheduler integrated and host-tested; Dataset downlinks are rejected as busy, compact ACK parity and physical RX remain unverified. |
| 2.3 | Other checklist controls and diagnostics | 10% | Waiting for next assigned work | Remaining controls and diagnostics | ATEX identity and UI label added. |

## Phase 3 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 3.1 | Focused ATEX and protected GLD1 tests | 50% | Active | Complete integration and physical regressions | Focused dataset, source, label, package and native scheduler tests pass. |
| 3.2 | Build isolated candidates and validate packages | 30% | Active | Real credentials, release manifest and provenance | Three synthetic workflow candidate builds pass; no release package. |

## Phase 4 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 4.1 | Real ATEX hardware and CH integration | 0% | Not started | Device powered on, software tests complete, physical identification and readback | COM7 planned; no CH available. |

## GLD1 and GLD4/ATEX: shared features and board-specific behavior

| Area | Shared feature to verify | Difference to preserve / evidence gate |
|---|---|---|
| Models | Model 1–3 selection, inference and correct metadata. | Synthetic builds pass; ATEX sensor mapping, nulling binding and gas accuracy require real-board validation. |
| Running and LoRa | Eight-sensor telemetry, smooth 50 ms display, RX and diagnostics. | Board power policy and radio scheduling differ; physical timing and CH/ACK remain unverified. |
| Dataset Wireless | Same hotspot Connect flow/password, 500 ms capture, controls, recovery and CSV. | ATEX requires external 24 V mode and power-good; active sessions reject downlink mode commands as busy. |
| Nulling and QC | Eight-channel nulling, single-channel control, results and QC settings. | GLD1 fast deterministic and ATEX adaptive algorithms differ; validate ATEX mapping, settling and calibration. |
| Hardware | Equivalent operation through board-specific hardware. | ATEX mux/power mapping, GPIO7 fan, RS485 and GLD2-derived power/alarm paths must not be replaced by GLD1 pins. |
| Protection and release | Preserve GLD1 and verify model selection/upload flow. | ATEX candidate selection and release remain locked; no production image or physical bootstrap verified. |

## Final verification checklist

- [ ] ATEX firmware selection and model 1/2/3 injection.
- [ ] Running eight sensors, gain, gas/confidence, smooth 50 ms display and RX continuity.
- [ ] Background/minimized chart, settings, series, analysis and CSV.
- [ ] Dataset hotspot, 500 ms, five setup steps, lock, controls and CSV verification.
- [ ] Dataset optional fields, direct and bounded recovery, honest gaps.
- [ ] Dataset average by count/duration, raw CSV, concurrent LoRa.
- [ ] Eight-channel nulling, settings, retries, logs, profile and binding.
- [ ] LoRa TX/RX, radio settings, GLD/CH identity, AES and QC diagnostics.
- [ ] QC graphs, boot/IC and MQ checks, system status.
- [ ] Operating modes, alarm, sensor power, fan and warmup capability.
- [ ] Port, fleet slots, commands, serial log, expert and MQTT paths.
- [ ] ATEX pin/sensor/ADC/DAC/power/alarm/radio mapping and model compatibility.
- [ ] Protected GLD1 regression and existing package preservation.
- [ ] Actual ATEX device and physical evidence after software tests; CH downlink/ACK when a CH is available.

### No-device verification evidence and remaining gates

| Checklist area | Evidence available without device | Still open |
|---|---|---|
| Models and selection | Synthetic ATEX workflow models 1, 2 and 3 compile, preflight passes; GLD1 selection and fail-closed ATEX UI tested. | ATEX release/package admission remains locked; real sensor mapping and gas accuracy. |
| Running and display | 50 ms interpolation and source isolation tests pass; radio scheduling tested with simulated service. | Live sampling cadence, continuous RX, performance and physical timing. |
| Dataset Wireless | Host backend/UI and 500 ms workflow tests; same Connect flow configured. | Actual hotspot, sustained recording and simultaneous RF. |
| Nulling and QC | Native/host ATEX nulling, QC and failure-path tests; protected GLD1 source checks. | Eight physical channels, settling, calibration, power and actual RF. |
| Alarm and power | Simulated GLD1/GLD2/ATEX output, alarm frame and pending-record tests pass. | Real alarm output, battery transitions, CH reception and identity. |
| Configuration and identity | Invalid-record mitigation and simulated ID/hotspot checks; partial-save then ID test documents failure case. | Atomic recovery/provisioning, persistent completeness, trusted physical identity, key handling and replay. |
| Expert, status and other UI | ATEX Expert and Auto TX status tests pass; unknown remains unknown; GLD1 UI model selection passes. | Full device-connected fleet, port, MQTT and serial workflows. |
| Regression suite | GLD1 workflow source isolation 27/27; firmware suite 51/52; GLD1/ATEX nulling scope 4/4. | One suite failure: CH/GW design mirror and stale version assertions; further assertions may be masked. |
| Deployment | Synthetic builds only, credentials are dummy; release gate remains closed. | This turn explicitly prohibits upload; physical board and CH verification deferred. |

## Current work / agent state

| Sub-agent / worker | Active work item | Started at | Elapsed | Progress | Activity / state |
|---|---|---|---|---|---|
| None | No active worker | — | — | — | Host work summarized below; device and recovery gates remain open |

## Evidence log

- 2026-11-12 12:52 +07:00: Tracker start time corrected to host-local timestamp; previous date-only entry did not establish a heartbeat interval. Workflow lease returns before native radio service; simultaneous Dataset and RX is not proven and must not be claimed.
- 2026-11-12 12:53:27 +07:00: Heartbeat SLA breach: previous heartbeat was recorded only to the minute 12:52; actual gap lies between 28 and 87 seconds. Source/config audit and initial builds caused the delay. Three isolated ATEX candidate environments added with package hooks disabled; model 1 build in progress. GLD1 smooth chart test and fast-nulling scope tests pass; full parity remains open.

- 2026-11-12 12:54:31 +07:00: Heartbeat SLA breach: 64 seconds during source audit and protected Dataset tests. 55 Dataset backend tests and workflow UI test pass; model 1 build remains in progress. No package, live application or device changed.


- 2026-11-12 12:55:35 +07:00: Heartbeat SLA breach: 64 seconds while auditing workflow alarm policy and candidate build. ATEX must retain alarm state on invalid inference; GLD1 workflow explicitly clears it. Device-specific policy and radio arbitration need separate treatment.


- 2026-11-12 12:57:57 +07:00: Heartbeat SLA breach: 142 seconds during alarm and workflow design review. Candidate model 1 build remains running; no further evidence change.


- 2026-11-12 12:58:32 +07:00: ATEX model 1 base candidate compile passed (RAM 41.5%, flash 16.0%). Model 2/3 candidate builds started; workflow and release packaging not included.


- 2026-11-12 12:59:23 +07:00: Model 1 reported successful compile, but its build directory was no longer present when independently checking the binary after Model 2/3 started. Cause not established; model embedding and artifact retention remain unverified. Rebuild to isolated durable path before claiming an artifact.


- 2026-11-12 12:59:47 +07:00: Candidate Model 2/3 compile remains in progress. Model 1 binary retention issue is still being investigated; no package installed.


- 2026-11-12 13:00:51 +07:00: Heartbeat SLA breach: 64 seconds while checking binary identity and shared SPI ownership. Model 2 build completed; exact model blob is present once and its metadata SHA-256 matches. Model 3 build in progress. Workflow capture runs on the main thread; radio and capture require explicit arbitration.


- 2026-11-12 13:01:43 +07:00: ATEX base Model 2 and 3 builds passed; each binary contains exactly one matching model blob with correct source metadata SHA-256. Model 1 binary no longer available for identity check. No workflow support or deployment claimed.


- 2026-11-12 13:02:28 +07:00: Heartbeat SLA breach: around 55 seconds since previous evidence update while implementing isolated workflow candidates. ATEX-only workflow readiness state added; invalid inference retains ATEX alarm behavior. Candidate-specific credential preparation fails closed and GLD1 path is unchanged. Compile and tests pending; simultaneous radio remains unresolved.


- 2026-11-12 13:06:01 +07:00: Heartbeat SLA breach: 56 seconds while running isolation regression. Candidate workflow build uses explicit synthetic-only credentials and isolated build directory. Workflow source isolation tests show 2 failures: exact-three-environment assertion rejects ATEX and source hash changes; investigate baseline and preserve equivalent GLD1 behavior before passing gate.


- 2026-11-12 13:07:05 +07:00: Heartbeat SLA breach: 220 seconds while diagnosing regression and refining conditional isolation. Workflow-disabled GLD1 source hash now matches its original baseline; exact-three test was updated to exclude six new ATEX candidates while retaining the original baseline hash. All 26 source-isolation tests pass. Initial ATEX Model 1 workflow candidate compiled with synthetic credentials; final-source rebuild is running. RX arbitration and device proof remain open.



- 2026-11-12 13:08:51 +07:00: Heartbeat SLA breach: 56 seconds during workflow rebuild and RX source changes. Final-source workflow Model 1 built before RX change (synthetic credentials, RAM 57.4%, flash 17.4%); a fresh build is now required. ATEX workflow candidate now opts into RX-aware scanning during ordinary externally powered inference; workflow lease still excludes radio and remains open. The 26 GLD1 source-isolation tests pass after this change.


- 2026-11-12 13:11:21 +07:00: Heartbeat SLA breach: 151 seconds while running native RX gate and final-source build. Native IRQ-aware scan test passes. ATEX workflow Model 1 compile succeeds with synthetic credentials and RX-aware Running; Models 2/3 compiling. No real hotspot credential or package created. Dataset/radio concurrency and physical proof remain open.


- 2026-11-12 13:12:38 +07:00: Heartbeat SLA breach: 77 seconds during candidate build and binary checks. ATEX workflow Model 1 and 2 binaries each contain exactly one correct model and protocol 3 marker; both use synthetic credentials and are not deployable. Model 3 build continues.


- 2026-11-12 13:14:23 +07:00: Three workflow candidates compiled with synthetic test credentials; Model 1/2 binary identity and protocol marker checked, Model 3 check pending. Three read-only subagents assigned T1 radio arbitration, T2 package/UI, T3 hardware/nulling; owner retains all edits. T1 identified downlink mode command can restart while an active Dataset session owns volatile replay, so safe session handling is required before concurrent RX.


- 2026-11-12 13:14:44 +07:00: Heartbeat SLA breach: 124 seconds while coordinating user-requested parallel audits and reading required coordinator instructions. In-turn workers are read-only; root alone writes shared source. Audit found active workflow downlink may restart device and lose volatile replay; ATEX sensor TCA order differs from GLD1; package paths and native readback guards are GLD1-only. These remain open integration gates.


- 2026-11-12 13:20:34 +07:00: Three read-only parallel audits completed. All 3 synthetic workflow candidates built and each embeds its matching model once. Source changed afterward to identify ATEX explicitly; rebuild in progress. UI labels now distinguish ATEX/GLD2/GLD1 and focused label and existing wizard tests pass. Downlink-triggered reboot during session, model/board binding evidence and real credentials/promotion remain open.


- 2026-11-12 13:21:28 +07:00: Heartbeat SLA breach: observed gap greater than four minutes while integrating parallel audit and identifying device profile. UI board identity tests pass, source isolation tests pass; rebuild of Model 1 after profile change remains in progress. No upload or release installation.


- 2026-11-12 13:33:23 +07:00: Heartbeat SLA breach: 11 minutes 52 seconds since last recorded heartbeat while inspecting subagent results, preparing isolated worktree and rebuilding candidates. All three workflow candidate builds now pass after ATEX identity change; synthetic credentials only. UI board-label, wizard, 26 source-isolation, seven credential and RX gate tests pass. No deployment or device access. Worktree creation pending; Dataset/LoRa arbitration and release integration unresolved.


- 2026-11-12 13:34:24 +07:00: T4 worker /root/package_ui started isolated worktree validator + synthetic tests, no release/hardware. Main checkout remains sole root ownership. Worktree does not include uncommitted user changes; integrate by reviewed diff only.


- 2026-11-12 13:45:38 +07:00: T4 validator and 10 synthetic tests integrated after review. Managed worktree archival rejected because it became the task primary checkout; original D: checkout remains unchanged by archival attempt and is used explicitly. T5 standalone radio scheduler/test assigned in the same isolated worktree; no runtime integration or hardware.


- 2026-11-12 13:47:24 +07:00: Heartbeat SLA breach: more than eleven minutes since last recorded heartbeat while integrating validator, reviewing worktree state and coordinating T5. Model 1 isolated candidate rebuilt and has correct embedded model and ATEX identity but synthetic credentials; it cannot be released. T5 scheduler worker remains active; no deployment or hardware access.


- 2026-11-12 13:51:37 +07:00: Heartbeat SLA breach: 257 seconds while reviewing T5 scheduler and running focused tests. T5 radio scheduling remains unintegrated; review found unknown TX outcome must not trigger retry after timeout/abort, worker revising. 10 package-validator, 26 source-isolation and board identity tests pass. Hardware, full runtime and deploy gates remain open.


- 2026-11-12 13:56:31 +07:00: T5 standalone scheduler and native tests integrated; it is not connected to runtime. Expert UI now lists Model 1/2/3 for ATEX but rejects all ATEX uploads pending verified packages; GLD1 routing remains unchanged and focused selection test passes. Full Dataset/LoRa concurrency, package route/credentials/readback and physical mapping remain open.


- 2026-11-12 13:57:57 +07:00: Checkpoint: all subagents finished. ATEX model selection is fail-closed pending verified packages. Three synthetic workflow builds, model blob checks, 55 Dataset backend tests, 26 source-isolation tests, 10 package-validator tests, UI tests and native scheduler/RX tests have passed in the stated scope. Radio scheduler is not wired to runtime; safe downlink handling, production packages, package routes/credentials, hardware mapping, model validation and physical testing are incomplete. No device upload.



- 2026-11-12 14:15:23 +07:00: Resumed after user request. T6 and T7 assigned in separate worktrees; T8 read-only audit found ATEX 24V-mode vs battery detection mismatch and mapping/nulling test gaps. Root owns integration/tracker; no COM or upload. Worker start timestamp is time of first tracker observation, not asserted launch time.


- 2026-11-12 14:20:48 +07:00: User says physical ATEX will be COM7, currently off; CH unavailable. No COM access authorized before software testing. Native nulling and alarm source checks pass. Existing boot I2C GLD1 passes but GLD2 harness fails compiling namespace alias; T9 independently repairs harness and extends ATEX. T6/T7/T9 active in isolated worktrees.


- 2026-11-12 14:23:26 +07:00: T9 boot I2C host test integrated after baseline hash review; GLD1/GLD2/ATEX pass with independent mapping oracle. Negative-control swapped TCA channels rejected in isolated worktree; physical mapping still open. Operator Hub existing 107 tests and workflow 26 source tests pass. T6/T7 remain active; ATEX COM7 is off, no CH.



- 2026-11-12 14:27:36 +07:00: Heartbeat SLA breach: 192s during independent test, code review and worker coordination.


- 2026-11-12 14:29:22 +07:00: Heartbeat SLA breach: 106s while reviewing worker output and coordinating hard upload gate.

- 2026-11-12 14:29:22 +07:00: T6 reports isolated ATEX prototype initial build and native tests pass; final ATEX/GLD1 builds pending. T7 is revising a hard deny for ATEX upload at UI and backend pending all release gates. T10 is preparing ATEX nulling host tests; potential failed single-null DAC/profile mismatch remains open. COM7 off; no CH.


- 2026-11-12 14:30:29 +07:00: Heartbeat SLA breach: 67s during radio and package code review. No completion inferred.

- 2026-11-12 14:30:29 +07:00: T6 reports 5 host contracts and IRQ scheduler tests pass; clean-source final ATEX and GLD1 builds in progress. T10 reproduced single-null primitive changing DAC on failure while NVS stays old; handler fix remains open. User-provided future COM7 stays off and CH unavailable; no upload/COM.


- 2026-11-12 14:38:41 +07:00: Heartbeat SLA breach: 493s during review/integration and protected regressions. T6 ATEX-only workflow radio prototype integrated with 6 source tests passing; T7 r2 package paths integrated, UI/backend upload hard denied. Hub 113/113 and Dataset 55/55 pass. T10 ATEX native nulling tests pass and reproduce failure; T11 fix + T12 bounded radio audit ongoing. Synthetic builds only, COM7 off and no CH.


- 2026-11-12 14:40:28 +07:00: Heartbeat SLA breach: 107s while running full firmware suite and coordinating regressions.

- 2026-11-12 14:40:28 +07:00: Full firmware test required Python314 cryptography; PlatformIO Python lacks dependency. Python314 run 44/52, pre-existing-vs-new comparison delegated T13. T12 found RadioLib nested SPI timeout 1000ms and ignored read errors; bounded 500ms cadence not yet proven. T11 handler fix in host testing, no COM/upload.


- 2026-11-12 14:47:46 +07:00: Heartbeat SLA breach: 439s while reviewing and integrating T11 and executing native regressions.

- 2026-11-12 14:47:46 +07:00: T11 ATEX-only handler rollback/readback invalidation merged. Native GLD1/GLD2/ATEX handler and nulling tests plus 27 isolation tests pass, legacy hash retained. Synthetic ATEX Model 1 rebuild in progress. T13 confirms 8 full-suite first failures predate T6/T7. T12 RadioLib nested blocking/error-handling audit remains open. Protocol3 radio_fault recovery diagnostic passes 56 tests; no COM/upload.


- 2026-11-12 14:49:03 +07:00: Heartbeat SLA breach: 77s during integrated handler build and reviews. Worker start times here are first observations; earlier assignments had completed.


- 2026-11-12 18:46:25 +07:00: Heartbeat SLA breach: 14242s during parallel review and agent coordination; no completion inferred.

- 2026-11-12 18:46:25 +07:00: Independent reviews found Pause/TX session interruption, legacy ATEX upload gate bypass, same-COM stream change risk, and inability to authenticate a relabeled package via manifest hashes. Radio and package gates remain closed for workflow but legacy needs fix. PG24 loss may trigger battery safety shutdown and lose volatile replay; no promise across actual power loss. COM7 off, no CH.


- 2026-11-12 18:47:31 +07:00: Heartbeat SLA breach: 66s since prior recorded heartbeat. Runtime now reports subagents pending_init; do not infer they are actively working or completed. No COM/upload. Reconcile worker artifacts before reassignment. T14/T15 found Pause/TX interruption, legacy gld_atex release-gate gap, and same-COM stream/readback issues (A16-A18).


- 2026-11-12 18:49:52 +07:00: Heartbeat SLA breach: 141s while closing identified legacy upload paths and running host tests.

- 2026-11-12 18:49:52 +07:00: Legacy gld_atex and explicit ATEX labels/known binary marker are blocked in child/Hub before port use; 8 ATEX child tests and 113 Hub tests pass. Detection is not cryptographic provenance. T12/T14/T15 runtime status pending_init following workspace context change; worker state not assumed.


- 2026-11-12 18:53:36 +07:00: Heartbeat SLA breach: 225s while reviewing upload guard bypass and coordinating workers.

- 2026-11-12 18:53:36 +07:00: Known legacy ATEX image SHA and known ATEX marker rejected in any decoded flash file, including renamed image; 9 child tests and 113 Hub tests pass. This is not a comprehensive or authenticated provenance policy. T12 checked API, T16 pause/stop drain, T17 same-stream readback are active; no COM/upload.


- 2026-11-12 18:55:06 +07:00: Heartbeat SLA breach: 90s during worker reconciliation and driver review.

- 2026-11-12 18:55:06 +07:00: T12 checked IRQ/length and bounded per-wait RadioLib driver integrated; fake-HAL native tests 3/3 pass, GLD1 preprocess unchanged. Runtime consumers remain unchecked until T16 patch. T16 Pause/Stop and TX deadline, T17 same-stream UI in isolated tests. Known legacy ATEX hash and ATEX marker denied for any flash file name (9 child tests). Hash/marker do not prove trusted provenance. No COM/upload.


- 2026-11-12 18:56:12 +07:00: Heartbeat SLA breach: 66s while reviewing T12/T17 and host tests.

- 2026-11-12 18:56:12 +07:00: T17 same-stream ATEX GET_INFO/GET_STATUS readback merged; reconnect mock and GLD1 JS regressions pass. Stale in-flight GET_INFO remains A18; T18 nonce design isolated. T16 preparing pause/stop fix and checked radio consumer, no hardware.


- 2026-11-12 18:57:40 +07:00: Heartbeat SLA breach: 88s while integrating stream pin and coordinating identity challenge.

- 2026-11-12 18:57:40 +07:00: T17 ATEX same-stream identity/model UI proof added and mock-tested; stale in-flight GET_INFO remains open. T18 nonce challenge backend in isolated worktree. T16 is integrating checked radio APIs and Pause/Stop safe drain; T19 review independently confirms old unchecked getters still exist until T16 patch. Upload hard-gated in source; running service not restarted. COM7 off, no CH.


- 2026-11-12 18:58:35 +07:00: T19 found failed SPI status may accompany valid packet-type byte, plus failed start TX may leave RF switch TX; forwarded to T16/T20. T18 designs nonce/exclusive serial gate. No device or CH attached; release blocked.


- 2026-11-12 18:59:39 +07:00: Heartbeat SLA breach: 65s while coordinating three worker implementations.

- 2026-11-12 18:59:39 +07:00: T16 implements pause/stop drain + checked radio consumer and airtime bound; T20 addresses SPI error with valid packet-type payload; T18 implements preflash nonce/exclusive serial gate. Postflash model response correlation, full physical and CH proof remain open. No COM/upload; gate source remains closed.


- 2026-11-12 19:00:51 +07:00: Heartbeat SLA breach: 73s while running replay/adversarial tests and coordinating agents.

- 2026-11-12 19:00:51 +07:00: Dataset 19 adversarial and 22 replay tests pass on current main. T20 reports fake HAL catches SPI error with valid packet-type bytes; negative control/patch pending. T16 pause/stop drain and T18 nonce identity remain isolated and unverified. Release hard denied in source, services not restarted, no COM.


- 2026-11-12 19:02:30 +07:00: Heartbeat SLA breach: 100s while coordinating parallel fault and serial tests.

- 2026-11-12 19:02:30 +07:00: T20 ATEX-only checked packet type merged; real driver/fake HAL tests pass, no total cadence proof. T16 pure scheduler pause/stop tests pass in worktree, production interaction and vendor airtime comparisons pending. T18 serial challenge tests pending; postflash freshness still open. No COM/upload.


- 2026-11-12 19:04:25 +07:00: Heartbeat SLA breach: 116s while reviewing new SPI chip-select failure.

- 2026-11-12 19:04:25 +07:00: T22 independently found standby BUSY pre-transfer timeout can leave LoRa CS LOW; driver fix and fake HAL proof required. T16/T18 in progress; no COM/upload, legacy and workflow release guards remain closed in source only.


- 2026-11-12 19:05:26 +07:00: Heartbeat SLA breach: 61s while reviewing standby/CS and nonce contracts.

- 2026-11-12 19:05:26 +07:00: T18 reports 12 synthetic nonce/serial gate tests pass in worktree, integration review pending. T23 fixes ATEX CS release on standby failure; T16 quarantines uncertain SPI and preserves battery shutdown precedence. No claim volatile replay survives power loss. No COM/upload.


- 2026-11-12 19:06:24 +07:00: T16 reports production-radio-body fake tests for pause/stop, checked SPI faults, CRC/power and cleanup pass; airtime comparison 15360 combinations with negative control passed; final quarantine test pending. T23 driver CS fix and T18 nonce backend tests pending patch review. No physical/COM/upload.


- 2026-11-12 19:08:27 +07:00: Heartbeat SLA breach: 124s during RadioLib patch integration and independent serial review.

- 2026-11-12 19:08:27 +07:00: T23 CS release fix merged and fake-HAL tests pass. T24 found T18 connect/open+detach races; patch withheld and T18 r2 correcting. T16 found queued Pause/Stop ordering race; fixing. Existing ATEX firmware lacks nonce command, so bootstrap remains open; no COM/upload.


- 2026-11-12 19:09:08 +07:00: T24 refined serial race: HTTP connect admission normally serializes competing connect, but reader can clear handle between check/detach. T18 r2 atomic guard+detach and mock barrier tests pending. T16 production pause/stop control and T23 CS release host tests continue. No COM/upload.


- 2026-11-12 19:10:10 +07:00: Heartbeat SLA breach: 63s while review and build preparation.

- 2026-11-12 19:10:10 +07:00: T23 chip-select fix and native HAL tests integrated. T16 production-loop fake test + 15360 airtime comparisons pass in isolated worktree; combined synthetic build pending. T18 challenge patch withheld after independent serial race, now in r2. No COM/upload.



- 2026-11-12 19:12:17 +07:00: Heartbeat SLA breach: 82s while delegating nonce firmware parser and coordinating runtime build.

- 2026-11-12 19:12:17 +07:00: T16 host production-body tests and airtime comparisons pass, synthetic build ongoing. T18 r2 exclusive serial race tests ongoing; T21a ATEX-only nonce parser assigned. Upload gate remains source-closed and no COM.


- 2026-11-12 19:46:02 +07:00: User chose ATEX hotspot password same as GLD1, same Connect workflow. Do not print credentials or rotate silently; validate exact compatibility before release. T16/T18/T21a in worktrees, no COM/upload.


- 2026-11-12 19:48:22 +07:00: Heartbeat SLA breach: 141s during extended worker processing/coordination. Do not infer progress from elapsed time.

- 2026-11-12 19:48:22 +07:00: User selected shared GLD1 hotspot password and unchanged Connect UI. T18 r2 nonce patch independently unmerged; 16 synthetic serial race tests pass in worker report, physical bootstrap/postflash remain open. T16 integration and T21 parser pending reconciliation; upload remains hard-denied, COM7 off/no CH.


- 2026-11-12 19:56:53 Asia/Jakarta: T16 real service fake-radio interaction, 15,360 vendor airtime comparisons, RadioLib fake HAL 3/3, Running interpolation and GLD1 source isolation 27/27 pass. T21a parser/handler and T18 r2 candidate integrated; synthetic identity tests 16/16, package admission 9/9, polling regression 18/18 pass. T25 password helper passes 15 synthetic tests but is unwired. Legacy bootstrap, direct API race, postflash nonce and hardware remain open; release source gate stays closed.

- 2026-11-12 20:10:50 Asia/Jakarta: Audit found GLD1 LoRa QC Focus/txTarget, auto/manual TX capability and persistence excluded by GLD2 guards for ATEX; implementation and independent tests assigned. Existing postflash serial write/recent can leave poll gate pending; nonce lease endpoint and clients under repair.

- 2026-11-12 20:19:20 Asia/Jakarta: T31 QC candidate withheld: blocking transmit and unchecked driver getters can stall; precondition failures can quarantine healthy radio. Worker correcting before merge.

- 2026-11-12 20:31:48 Asia/Jakarta: 8 firmware suite first failures reproduced in T6 partial snapshot, not complete pristine baseline. Some assertions/docs stale, but ADC behavior and terminal echo require investigation; no claims about assertions hidden by first failures. GLD1 GPIO48 Hub contract mismatch corrected in source; 119 Hub tests pass.

- 2026-11-12 20:35:17 Asia/Jakarta: Isolated prototypes retained for follow-up: T35 full-config snapshot/owner `C:/Users/MSI/.codex/worktrees/atex-board-host-tests/T35-full-config-prototype.patch` SHA256 46cb61bcc8279f852c8ec041e2e7709c97f347f5dc6c770d8263623cfd45a774; T32 fast nulling `C:/Users/MSI/.codex/worktrees/atex-board-host-tests/T32-baseline/T32-null-fast-candidate.patch` SHA256 b9d6a96dc1eb2913ed17d091fc9c6744d4b818906156a7f8fb723c80a2c0401d. Neither wired, released or validated on hardware.
- Heartbeat gaps observed: 19:48:22–19:53:04, 20:34:33–20:36:23, 20:36:23–20:37:47, 20:38:47–20:40:06, and 20:40:06–20:41:21 Asia/Jakarta; all exceeded one minute.

- Heartbeat gap 20:44:28–20:46:07 Asia/Jakarta exceeded one minute.
- QC candidate retained unmerged: apply T31 baseline `C:/Users/MSI/.codex/worktrees/atex-board-host-tests/T31-baseline/T31-qc-candidate.patch` then v2 delta `C:/Windows/Temp/gld-atex-qc-async-baseline/t31-qc-async-candidate-v2.patch` (SHA256 69fe19d22887598810afc0814b0f538d2b85ae866ee790a779e79011d77fed35). Build synthetic Model 1 passed; NVS partial-write, ACK-event correlation, final integration and physical checks remain open.

- 2026-11-12 21:00:58 Asia/Jakarta: User did not understand AES exposure; explained plainly that communication key appeared in session log and changing it requires coordinating devices. No automatic rotation, CH unavailable. User decision on key handling remains open.

- 2026-11-12 21:07:39 Asia/Jakarta: Final source snapshot built 3/3 ATEX model workflows with T26 private preflight and dummy credentials in isolated fixture `C:/Windows/Temp/gld-final-atex-model-fixture/build.log`; model markers matched selected environment. Candidate QC async excluded; no hardware/release.

- 2026-11-12 21:12:50 Asia/Jakarta: QC async combined source integrated after independent review; host tests passed on main. Model1 synthetic candidate build passed in isolated snapshot; models 2/3 combined build, physical radio/timing and QC persistence fault handling still open. Release gate remains hard-denied.

- 2026-11-12 21:19:29 Asia/Jakarta: QC source synthetic builds passed Model1 (`C:/Windows/Temp/gld-qc-async-build/combined-confirm.log`) and Model2/3 (`C:/Windows/Temp/gld-final-atex-qc-model-fixture/build.log`); model2/3 markers matched. No release, live device or real credential involved.

- 2026-11-12 21:34:05 Asia/Jakarta: Final T37 source compiled successfully for all three models in isolated dummy-credential fixture (`C:/Windows/Temp/gld-final-atex-t37r3-fixture/build.log`), public model markers matched; not release or physical proof.

- 2026-11-12 21:35:59 Asia/Jakarta: Diagnostic prototype `C:/Users/MSI/.codex/worktrees/atex-board-host-tests/T38-invalid-marker-diagnostic.patch` SHA256 3e3a1b5474c8dd5cb4fdb08deba9ca149bfd524798a7fc2d88028a4b5f5eeb39 reproduces current partial load after invalid/missing marker with fake Preferences, not a desired-behavior test. Missing marker cannot establish first boot versus corruption; recovery must avoid automatic counter/key reset and requires verified target and trusted configuration or coordinated fresh key.

- 2026-11-13 13:50:54 Asia/Jakarta: User explicitly confirms shared functionality with intentional GLD1/GLD4 board differences. Prior production radio interaction PASS is superseded by current harness compile failure A24; tests for GLD1 source and focused QC pass.

- 2026-11-13 13:51:55 Asia/Jakarta: GLD4/ATEX keeps board-specific sensor/power mapping, GPIO7 fan, RS485 and alarm/power; shared feature parity includes models, 50ms display, Dataset, nulling, QC and LoRa. Nulling algorithms differ and require physical validation. Hub 119 and Dataset 56 tests pass; A24 supersedes previous radio harness result.

- 2026-11-13 13:53:27 Asia/Jakarta: Heartbeat SLA breach: 93s since previous heartbeat while evaluating parallel audit reports.

- 2026-11-13 13:54:21 Asia/Jakarta: A24 fixed in test harness only; production radio interaction and both mutation negative controls pass after T37. Assertions printed by mutated executables are expected and detected.

- 2026-11-13 13:55:45 Asia/Jakarta: Heartbeat SLA breach: 84s elapsed during bounded test review.

- 2026-11-13 13:57:28 Asia/Jakarta: Heartbeat SLA breach: 104s gap while reviewing MQTT bypass; no result was inferred during the gap.

- 2026-11-13 13:58:29 Asia/Jakarta: Heartbeat SLA breach: 62s gap while reconciling network paths.

- 2026-11-13 13:59:56 Asia/Jakarta: Heartbeat SLA breach: 88s gap while reviewing Dataset provisioning constraints.

- 2026-11-13 14:01:17 Asia/Jakarta: Heartbeat SLA breach: 81s gap during worker polls.

- 2026-11-13 14:02:47 Asia/Jakarta: Heartbeat SLA breach: 91s gap during MQTT call-site audit.

- 2026-11-13 14:04:40 Asia/Jakarta: ATEX-only native network guard integrated; host tests and GLD1 isolation pass. Existing socket/STA is not torn down, MQTT status/ACK during fault is not queued, native sample queue can fill, Wireless retained survives only within device uptime. A23 remains open.

- 2026-11-13 14:07:19 Asia/Jakarta: Heartbeat SLA breach: 100s during provisioning ID compatibility review.

- 2026-11-13 14:09:02 Asia/Jakarta: Heartbeat SLA breach: 103s gap during Dataset identity and provisioning review.

- 2026-11-13 14:09:02 Asia/Jakarta: Candidate Dataset identity guard not merged: it blocks initial START without a precise reason; ctrlword alone does not prove consistent NVS after subsequent SET_DEVICE_ID. Shared Wireless must not require native router/MQTT.

- 2026-11-13 14:10:02 Asia/Jakarta: Dataset identity guard withheld: hello/collector currently returns generic not-ready reason, marker alone cannot prove coherent NVS, and first-boot/rebind behavior needs explicit compatibility design. Candidate only: C:/Windows/Temp/gld-atex-network-audit/atex-dataset-identity-guard.patch SHA256 e075ee5f6f19d1f491e069b7f4115e2f484c5a797771fbb4ec068b9c55ec16e0.

- 2026-11-13 14:13:30 Asia/Jakarta: Heartbeat SLA breach: 190s gap while awaiting compile fixture preparation.

- 2026-11-13 14:15:28 Asia/Jakarta: Heartbeat SLA breach: 119s gap; worker runtime disappeared and no active process remained; build incomplete.

- 2026-11-13 14:15:28 Asia/Jakarta: Agent build output at C:/Windows/Temp/gld4-network-guard-fixture-20261113/build.log ends in Model 1 compilation; no success or completed process. Retrying safely in new fixture.

- 2026-11-13 14:19:43 Asia/Jakarta: Heartbeat SLA breach: 71s gap during build progress checks.

- 2026-11-13 14:20:53 Asia/Jakarta: Final three-model isolated synthetic build (`C:/Windows/Temp/gld4-network-retry-vhfgxg5r/build.log`) SUCCESS 3/3; 16/16 source hashes matched main and each model binary contained only its expected public profile marker. Synthetic images are not release. Native network guard and radio fixture repair integrated; NVS recovery, hardware, CH and exposed-key handling remain open.

- 2026-11-14 08:41:57 Asia/Jakarta: Heartbeat SLA breach: 71s elapsed while reviewing parallel reports.

- 2026-11-14 08:43:03 Asia/Jakarta: Heartbeat SLA breach: 66s during suite review.

- 2026-11-14 08:43:03 Asia/Jakarta: One old test NameError fixed by reading actual ProtocolConstants.h; complete test now passes and full firmware suite is 45/52. Seven first failures remain; not declared harmless or solved.

- 2026-11-14 08:45:55 Asia/Jakarta: ATEX workflow rejects ID changes without reboot when hotspot is active; same ID and built-in reboot:true flow remain available. Handler/lease mocks and GLD1 source 27/27 pass. No actual hotspot or reboot.

- 2026-11-14 08:47:00 Asia/Jakarta: Heartbeat SLA breach: 65s during test/version and NVS candidate audit.

- 2026-11-14 08:48:05 Asia/Jakarta: Heartbeat SLA breach: 66s during version contract review.

- 2026-11-14 08:49:18 Asia/Jakarta: Heartbeat SLA breach: 74s during isolated test development.

- 2026-11-14 08:50:52 Asia/Jakarta: Heartbeat SLA breach: 94s while awaiting isolated candidate tests.

- 2026-11-14 08:52:06 Asia/Jakarta: Heartbeat SLA breach: 74s during test integration and candidate review.

- 2026-11-14 08:52:06 Asia/Jakarta: Replaced stale pinned-version assertions with semver checks and runtime/packager profile-selection test with negative mutations. Firmware suite now 46/52; tests are host-only.

- 2026-11-14 10:04:48 Asia/Jakarta: Heartbeat SLA breach: 4363s clock gap observed while awaiting worker reports; actual intervening execution not inferred.

- 2026-11-14 10:07:34 Asia/Jakarta: Heartbeat SLA breach: 167s during ADS test review and integration.

- 2026-11-14 10:07:34 Asia/Jakarta: Real ADS1256 driver host simulation across GLD1/GLD2/ATEX passed, with DRDY/gain mutations detected; physical ADC still unverified. A23 candidate not merged because it silently persists first-boot auto-TX OFF into Dataset workflow.

- 2026-11-14 10:11:58 Asia/Jakarta: Heartbeat SLA breach: 264s observed clock gap during worker reports; no intervening execution inferred.

- 2026-11-14 10:24:04 Asia/Jakarta: Heartbeat SLA breach: 727s observed clock gap during worker report exchange; actual intervening execution not inferred.

- 2026-11-14 10:26:36 Asia/Jakarta: Heartbeat SLA breach: 152s observed while reviewing UI candidate.

- 2026-11-14 10:26:36 Asia/Jakarta: ATEX Expert inference status view integrated; contradictory/unreported readiness remains non-green. GLD1/GLD2/GLD3 VM tests, model binding and ATEX firmware UI tests pass. No physical claim.

- 2026-11-14 10:28:22 Asia/Jakarta: Heartbeat SLA breach: 106s gap during worker test development; no inferred device activity.

- 2026-11-14 10:31:00 Asia/Jakarta: Heartbeat SLA breach: 158s observed while awaiting isolated UX implementation.

- 2026-11-14 10:33:34 Asia/Jakarta: Heartbeat SLA breach: 154s observed while integrating ADS/route tests.

- 2026-11-14 10:33:34 Asia/Jakarta: Firmware suite is 48/52 after ADS/route scaffold updates backed by real production-code host tests and detected negative mutations; four first failures remain. No firmware version or runtime modified.

- 2026-11-14 10:35:03 Asia/Jakarta: Heartbeat SLA breach: 89s observed during isolated collector and test work.

- 2026-11-14 10:36:30 Asia/Jakarta: Heartbeat SLA breach: 87s observed during packager test integration.

- 2026-11-14 10:36:30 Asia/Jakarta: Suite 49/52; production packager exercised using synthetic build and overwrite/missing-output controls. Independent alarm fixture compilation now requires updated LED stub; not claimed passed.

- 2026-11-14 10:38:31 Asia/Jakarta: Heartbeat SLA breach: 122s observed during isolated docs and test work.

- 2026-11-14 10:42:02 Asia/Jakarta: Heartbeat SLA breach: 212s during alarm contract review.

- 2026-11-14 10:45:47 Asia/Jakarta: Heartbeat SLA breach: 225s observed during UX/alarm review.

- 2026-11-14 10:45:47 Asia/Jakarta: Host reproduction: valid non-clear confidence 0 gives physical-command alarm ON but TX alarm flag OFF; confidence 1/29/30 matches. Real model output and device/CH behavior are unverified.

- 2026-11-14 10:47:31 Asia/Jakarta: Heartbeat SLA breach: 104s during parallel alarm and UX review.

- 2026-11-14 10:51:51 Asia/Jakarta: Heartbeat SLA breach: 261s observed while reviewing alarm pipeline.

- 2026-11-14 10:54:55 Asia/Jakarta: Heartbeat SLA breach: 184s during battery-alarm and documentation review.

- 2026-11-14 10:59:28 Asia/Jakarta: Heartbeat SLA breach: 273s during alarm integration and host tests.

- 2026-11-14 10:59:28 Asia/Jakarta: ATEX confidence-0 non-clear alarm now yields alarm frame and validated frozen pending in host tests; GLD1/GLD2 remain threshold 1. Fake crypto/NVS, no hardware/CH/server proof.

- 2026-11-14 11:01:00 Asia/Jakarta: Heartbeat SLA breach: 93s observed during duplicate-state reconciliation.

- 2026-11-14 11:02:16 Asia/Jakarta: Heartbeat SLA breach: 77s observed while reconciling previously integrated UX and issuing build tasks.

- 2026-11-14 11:06:03 Asia/Jakarta: Heartbeat SLA breach: 227s observed during NVS mitigation integration and tests.

- 2026-11-14 11:06:03 Asia/Jakarta: A23 limited ATEX invalid-record mitigation integrated: default non-ID RAM, marker invalid, Auto TX OFF; provisioning remains possible but OFF persists until QC enables. Host tests pass, manual TX/key reuse/NVS atomicity and identity remain unresolved.

- 2026-11-14 11:09:14 Asia/Jakarta: Heartbeat gap observed since 11:06:03 while reconciling resumed context; no intervening activity inferred. A23 is integrated, but production whole-record save during ID provisioning may validate defaults; investigating before closure.

- 2026-11-14 11:09:55 Asia/Jakarta: Alarm output simulated for GLD1/GLD2/ATEX, frame combinations and pending NVS tests pass. Firmware suite 50/52; remaining stale scaffold and cross-component documentation tests under audit. Production provisioning interaction remains open. No physical proof.

- 2026-11-14 11:10:52 Asia/Jakarta: Production loader/save/ID handler with simulated Preferences reproduces that after a partial write and reboot, ID save validates defaults (empty AES, Auto TX OFF). A23 provisioning remains open; first boot and corrupted record cannot be distinguished by marker alone. Release remains denied.

- 2026-11-14 11:12:55 Asia/Jakarta: Synthetic final-source ATEX workflow build 3/3 with preflight passed; 122 recorded source hashes match main after build. Firmware suite 50/52 after parser test repair. Real-save simulated NVS test passes by reproducing unresolved failure, not by proving recovery. No COM, upload or release.

- 2026-11-14 11:13:46 Asia/Jakarta: Recovery review found a persistent completeness state and explicit finalization would need a defined provisioning policy and failure injection, including legacy and first boot. No unsafe one-line fix claimed; transaction design remains non-production.

- 2026-11-14 11:14:23 Asia/Jakarta: Cross-component docs test compares three diverged CH/GW design/final pairs and stale firmware versions; correction requires separate source/document audit, not mass replacement. Recovery review complete; persistent completeness and safe commissioning policy remain unresolved.

- 2026-11-14 11:15:46 Asia/Jakarta: Unified-runtime scaffold audit prepared isolated candidate; five mutation controls reported detected. Integration pending review and test; overall suite remains 50/52.

- 2026-11-14 11:17:43 Asia/Jakarta: Current unified runtime source-contract test updated after audit, with five negative mutations detected in fixture; nulling scope corrected to test both branches, 4/4 plus GLD1 fast 3/3 pass. Actual general suite is 51/52. Remaining mirror test includes unrelated CH/GW design/final differences and stale version expectations; no documents changed to conceal it.

- 2026-11-14 11:18:00 Asia/Jakarta: Heartbeat gap of 117 seconds observed between 11:15:46 and 11:17:43 during patch review and final tests.
