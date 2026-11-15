# GLD telemetry continuity

Last tracker heartbeat: 2026-11-12 00:06:02 Asia/Jakarta
Last evidence update: 2026-11-12 00:06:02 Asia/Jakarta

## Progress dashboard

| Scope | Progress | Status | Note |
|---|---:|---|---|
| **Overall goal** | **94%** | Waiting for external evidence | Live integration and COM7 tests pass; received downlink and initial provisioning remain unverified. |
| LoRa receive and scan | 90% | Waiting for external evidence | Real sensor samples continue in RX windows; an actual downlink/ACK was not observed. |
| Background polling and replay | 100% | Complete | Real GLD1004 minimized/frozen browser and ordered replay pass via bridge. |
| Model selection | 90% | Waiting for external evidence | Model packages deployed; physical initial provisioning not performed. |
| Integration and verification | 90% | Waiting for external evidence | Live Model 1 deployed and tested; initial and received downlink proof pending. |

## Progress calculation

`35%×90 + 35%×100 + 15%×90 + 15%×90 = 93.5% ≈ 94%`

| Phase | Weight | Progress | Status | Closure evidence |
|---|---:|---:|---|---|
| LoRa receive and scan | 35% | 90% | Waiting for external evidence | Received downlink and ACK while scanning. |
| Background polling and replay | 35% | 100% | Complete | Real device minimized/frozen browser and replay. |
| Model selection | 15% | 90% | Waiting for external evidence | Physical initial provisioning on a suitable board. |
| Integration and verification | 15% | 90% | Waiting for external evidence | Downlink/ACK and initial provisioning evidence. |

## Issue register

| ID | Status | Evidence | Next gate |
|---|---|---|---|
| LORA-1 | Open | GLD1004 produced four samples during each of five real RX windows; TX passed. No downlink received. | Observe received downlink/ACK during scan. |
| POLL-1 | Solved | Real GLD1004 browser minimized/frozen polling and ordered replay passed via bridge. | Reopen if a real regression is observed. |
| LIVE-1 | Open | Model1 uploaded with no NVS reset; GLD1004 inference and binding preserved. | Validate initial provisioning on a suitable board without disturbing existing configuration. |

### Phase 1 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 1.1 | Implement and test receive scanning | 90% | Waiting for external evidence | Real received packet/ACK during scanning | Five RX windows contained four samples each; TX passed. |

### Phase 2 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 2.1 | Implement safe background polling and replay | 100% | Complete | — | Real board minimized/frozen test and replay passed. |

### Model selection work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| M.1 | Select Workflow packages using Board labels | 90% | Waiting for external evidence | Physical initial provisioning | Three packages deployed; Model1 normal upload verified. |

### Phase 3 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 3.1 | Verify protected flows and integration | 90% | Waiting for external evidence | Downlink/ACK and initial provisioning | Live GLD1004 integration and protected tests pass. |

## Current work / agent state

| Sub-agent / worker | Active work item | Started at | Elapsed | Progress | Activity / state |
|---|---|---|---|---|---|
Tidak ada agent aktif saat ini. Menunggu paket downlink/ACK aktual dan board yang sesuai untuk uji initial provisioning.

## Evidence log

- Existing active firmware work and running services are protected; no COM, flashing or restarts.

- Heartbeat SLA breach: approximately six minutes between recorded heartbeat and update; initial timestamp was taken from prior session log rather than current clock. No completion evidence was inferred.


- Isolated worktree created at C:/Users/MSI/.codex/worktrees/gld-telemetry-continuity/PertaminaGLD. No implementation, build, device or browser validation performed. Serial writes also originate outside the normal browser command queue; background polling requires shared ownership and response arbitration.


- Added scope: GLD Model 1–3 picker selects final Workflow packages, with Model 4 unavailable; preserve upload and NVS guards.


- Model selector isolated implementation: Expert 1–3 point to final Workflow environments; Simple Hub hides older three and labels final variants as Board 1–3. Existing upload routing/NVS tests and chart renderer tests passed. No live service changed.


- Tracker scope correction: Model selection weighted at 15%; existing phases reweighted to 35/35/15. Heartbeat was delayed approximately one minute while inspecting the firmware; no new result inferred from heartbeat.


- Workflow selector test now exercises all 3 exact package mappings and both upload guards; 28 board-package tests pass using bundled Python. Browser and real device not tested.


- Initial-firmware caveat: Simple Hub forces NVS reset on initial uploads and refuses Workflow environments with reset. Hiding legacy model choices can therefore affect initial setup; resolve before integrating selector change. No firmware or background polling changes implemented.



- Preliminary isolated RX scan change added. Initial build lacked credentials and failed before compilation; restarted with synthetic build-only credentials. Radio timing and concurrency remain unverified.



- Heartbeat SLA breach: approximately two minutes since previous recorded heartbeat while assessing integration risks; no additional completion evidence inferred.


- Initial Workflow upload source permits only validated native-serial packages with explicit reset confirmation; ordinary Workflow resets remain blocked. Seven Hub mock tests and selector tests pass; physical initial provisioning not tested.
- Heartbeat SLA breach: approximately 1 minute 40 seconds elapsed while implementing and testing initial upload; no additional completion evidence inferred.


- Child bridge mock tests verify initial Workflow still requires AES provisioning and rejects missing confirmation or capabilities; no serial port opened.


- Isolated serial request gate has 3 host tests for response matching, non-overlap, timeout quarantine and reset. It is not integrated into the bridge or browser; minimized polling remains unimplemented.
- Heartbeat SLA breach: approximately 1 minute 24 seconds while implementing the isolated gate; no test or build result was inferred.




- Isolated Model 1 Workflow firmware compiled successfully (RAM 57.4%, flash 17.2%) with synthetic build-only credentials. No upload; no measured real RX behavior. Build artifact is not for deployment.
- Heartbeat SLA breach: 73 seconds elapsed while waiting for test/build results; no progress inferred from the heartbeat itself.



- Four isolated gate/poller tests now cover non-overlap, owner isolation, stop and timeout quarantine. No bridge API, browser integration, or minimized-window verification yet.


- Fifth poll-gate test verifies missing poll response stops acquisition and quarantines the serial gate. Preliminary firmware scope narrowed to GLD1 automatic inference only; rebuild needed after scope change.
- Heartbeat SLA breach: 64 seconds between updates while reviewing the RX diff and gate tests; no completion was inferred.


- Isolated replay buffer tests check timestamp preservation, cursor and explicit overflow reporting; integration and browser behavior remain unverified. RX build restarted after restricting changes to GLD1.
- Heartbeat SLA breach: 64 seconds elapsed while implementing and testing replay; no completion evidence inferred.


- The second full rebuild was stopped to avoid consuming additional resources; the successful first build used the same GLD1 branch. Later changes removed opt-in from GLD2 and corrected a comment. Firmware still requires board timing and ACK validation.



- Prototype bridge poll API and serial gate passed a fake-wire overlap/ownership test. It is not connected to the browser or replay path; do not deploy. Additional priority, reconnect and failure tests are required.
- Heartbeat SLA breach: 98 seconds during bridge prototype and fake-wire test; no completion inferred.


- Prototype bridge telemetry replay endpoint now records per-connection stream and receive timestamps. No UI integration or real-session tests yet. Heartbeat SLA breach: 64 seconds elapsed during implementation.


- Bridge prototype records replay timestamps and exposes a replay API; fake-wire and initial AES-gate tests pass. Priority commands, reconnect, client replay ordering and actual minimized behavior remain unverified.


- Browser poll start/stop now points at prototype bridge endpoint in isolated worktree. Replay, slot switching, priority commands, disconnect and real minimized-window behavior are not yet verified; do not deploy.
- Heartbeat SLA breach: 64 seconds elapsed during browser poll prototype implementation.




- Fake-wire test verifies priority cancellation is not blocked by a missing poll reply; Running replay merge test preserves Dataset history. Real browser minimized test, reconnection, race review and regression suite pending.
- Heartbeat SLA breach: 86 seconds elapsed during replay and priority testing; no completion inferred.


- UI replay/live sequencing unit test passed for missing-event recovery without duplicate processing. Full bridge-to-browser integration, real minimized state and safe slot ownership still require verification.


- Prototype guards mock mode against real replay and preserves priority cancellation; session lifecycle and end-to-end testing remain open. Heartbeat SLA breach: 69 seconds during lifecycle audit.


- Heartbeat SLA breach: approximately 114 seconds elapsed during polling lifecycle review; no completion inferred.


- Fake-wire tests cover stop-before-delayed-start and stale connection ID; UI tests cover immediate stop and slot transfer. End-to-end browser and device validation remain open. Heartbeat SLA breach: approximately 102 seconds during race fixes and tests.


- Prototype loopback HTTP test shows polling and replay continue while no browser callbacks occur; it does not prove a real minimized browser or device. Dataset-mode isolation remains under review. Heartbeat SLA breach: 118 seconds while running integration and safety review.


- Unit tests cover transfer between Running bridge polling and legacy Dataset/Nulling polling, stop/start race, slot transfer, and six fake bridge cases. Real browser/device and broader regressions pending. Heartbeat SLA breach: 67 seconds elapsed during mode tests.


- Poll timeout now disables background acquisition while permitting unrelated operator commands; fake-wire regression confirms unresolved telemetry cannot be reissued until its response or reconnect. Heartbeat SLA breach: 106 seconds during timeout implementation and tests.


- Fake-wire test confirms stopping the poll owner cannot release an unrelated operator command awaiting its response; timeout/replay/UI mode tests pass in isolation.


- Added stale-reader generation check and retired-stream filtering; tests pending. Heartbeat SLA breach: 114 seconds during disconnect/reconnect race review.


- Host tests pass for priority waiters, disconnect generation, stale readers, stop races, HTTP polling/replay, and Running replay. Hub Python suite 107/107 and Dataset suites 40/19/4 pass. Hardware/minimized-browser proof not obtained. Heartbeat SLA breach: 98 seconds during race tests.


- Delayed Running telemetry is batched into replay without live Dataset/alarm side effects; timestamp ordering and duplicate tests pass. Real minimized browser and hardware remain unverified. Heartbeat SLA breach: 125 seconds during replay safety work.


- Prototype start now waits up to five seconds for existing operator responses and stop can cancel that wait. One test expectation changed with the stricter reconnect error; rerun pending. Heartbeat SLA breach: 248 seconds during start/disconnect race work.


- Fake-wire regression now verifies emergency cancel preempts another session waiting behind a lost poll response, plus start/stop/connection races. Heartbeat SLA breach: 85 seconds during priority-preemption fix.




- Isolated Chrome/loopback test confirmed visibility hidden after minimizing and history increased from 2 to 11 timestamp-ordered samples with fake serial, no callbacks required. New temporary browser profile and ephemeral bridge only; no COM. Heartbeat SLA breach: 103 seconds during browser fixture implementation and test.


- Extracted RX scan decision and ran a native test for 500 ms cadence, RX interrupt priority, mode/power gates and millis rollover. Actual SPI latency/downlink still requires hardware. Isolated Model 1 rebuild running. Heartbeat SLA breach: 88 seconds during RX test implementation.


- Evidence correction: earlier statement that the host RX test passed was premature; the initial compile failed because the compiler PATH and namespace syntax were incompatible. After setting PATH and using C++11 namespace syntax, compilation and execution returned exit 0. The running firmware build began before that syntax-only edit; final-input build evidence remains pending. Heartbeat SLA breach: 84 seconds during correction.


- Second isolated Chrome test confirmed at least three samples occurred inside the actual minimized interval and Stop Poll halted bridge acquisition. Fake device and unique browser profile only. Heartbeat SLA breach: 93 seconds during browser verification.


- Chrome test previously passed minimized plus frozen collection, but a later rerun encountered transient missing execution context; retry logic added and rerun pending. Heartbeat SLA breach: 120 seconds during lifecycle testing.


- Chrome rerun passed minimized/frozen recovery and page-close polling release. Fake-wire tests also verify a different owner cannot start or stop an existing poll. Heartbeat SLA breach: 69 seconds during these checks.


- RX scan now aborts an incomplete local batch after an interrupt and restores the previous sample timestamp; native test validates interruption and complete batches. Final-input firmware build started with synthetic credentials. Heartbeat SLA breach: 138 seconds during safety redesign and testing.


- EventHub overflow now closes the stale SSE stream so the browser reconnects and requests replay; overflow and fake-wire tests pass. Final Model 1 build is still running after RX interruption changes. Heartbeat SLA breach: 221 seconds while auditing RX and SSE recovery.



- Running animation now stops redrawing when the chart is not visible and avoids redundant canvas resizing/legend rebuilding; tests pending. Heartbeat SLA breach: 89 seconds during priority and performance review.


- After graph redraw optimization, isolated Chrome again passed minimized, frozen, resume and page-close polling checks with fake serial. RX rebuild is still running. Heartbeat SLA breach: 87 seconds during regression verification.


- Added gate epoch checks so an old watchdog cannot disable a newly connected stream; 14 bridge and 7 gate tests pass. Disconnect now serializes with in-flight writes. Heartbeat SLA breach: 72 seconds during concurrency fixes.


- Fake-wire stress test sent 20 concurrent operator requests while polling; observed no overlapping requests. Heartbeat SLA breach: 61 seconds during stress test implementation.


- Final-input GLD1 Model 1 Workflow build passed (RAM 57.4%, flash 17.2%) with synthetic credentials; it is not deployable. Host RX interrupt test passed. Models 2/3 build and hardware proof remain open.


- Race audit found an old watchdog/stop could overlap a newer poll owner; epoch and control-version checks added, tests pending. Heartbeat SLA breach: 108 seconds during concurrency audit.



- Three GLD1 Workflow candidate builds started sequentially in isolated worktree using existing private credentials without printing them; active packages remain unchanged. Fake-wire test confirms stopping one slot does not stop another. Heartbeat SLA breach: 67 seconds during the slot test.


- RX scan now requires both reconciled external-24V mode and the live power-good pin. Because source changed during the ongoing build, all three models must be rebuilt after it ends before packaging. Heartbeat SLA breach: 113 seconds during power-safety review.


- Added GLD1 info capability for later device readback; builds restarted from the same finalized source. Heartbeat SLA breach: 248 seconds during build and provenance review.



- A native ArduinoJson test with maximum GLD1 network fields showed 1536-byte GET_INFO capacity overflow. Scoped GLD1 capacity to 3072 and added overflow diagnostic; the same native test passes. Previous candidate builds were stopped before final source change and must not be packaged. Heartbeat SLA breach: 163 seconds during this capacity investigation.


- Added operator-visible polling failure and direct-browser throttling notice. Three-model final build is active, no device access. Heartbeat SLA breach: 122 seconds during safety and UI review.



- Tracker correction: top-level heartbeat remained at 22:27:55 because exact-string replacements stopped matching, despite later evidence-log updates. Actual recorded heartbeat gap was 01:08:16; corrected current worker and heartbeat now. This correction is not implementation progress.


- Final isolated Chrome test passed minimized, frozen, ordered replay, explicit Stop Poll and page-close cleanup after latest bridge changes.





- JSON-suffixed serial commands now match firmware ACK names; successful commands that emit a following status hold the gate until the status or bounded compatibility timeout. 18 fake bridge and 9 gate tests pass. Heartbeat SLA breach: approximately five minutes since previous top-level heartbeat during protocol audit; no completion inferred.


- Heartbeat update delayed approximately 80 seconds during build monitoring; no completion inferred.

- 2026-11-11 23:54:51: all three Workflow firmware builds passed; candidate-adf0ef0e5725 staged and validated without installation. Latest isolated minimized/frozen browser, gate (9), bridge (18), chart/replay and native RX tests pass. Running software and physical boards remain unchanged; real-device verification remains outstanding.

- 2026-11-11 23:56:41: Live read-only serial status reports COM7 connected in GLD slot 1; an established browser connection exists. No firmware upload, reset, port open or restart attempted. Asked user which board/port is available without disturbing the active session.

- User authorized COM7 and closing their Operator Hub/terminal as needed, while protecting other sessions. Existing main source has concurrent Dataset/warmup changes; normalized three-way merge preview preserves warmup and Dataset. Chart overlap differs only by the improved animation optimization.

- Merged isolated main Dataset/warmup modifications with continuity implementation; 48 Dataset tests, workflow/warmup UI tests, 18 bridge tests and isolated minimized browser passed. GLD1004 Model1 profile 3 and model binding valid before upload; COM7 explicitly released by user. CH/Gateway listeners have no established connections; MQTT broker port has no established connections at check.

- Heartbeat SLA breach: 56 seconds elapsed during controlled deployment and restart; timestamp reflects actual update. Hub and GLD restarted successfully; CH/Gateway PIDs unchanged; package backups retained.

- Model 1 live upload returned success with four verified files and no NVS reset. GET_INFO read back GLD1004 v0.8.36 with scanDuringLoRaRx=true; GET_STATUS confirmed inference valid, nulling profile 3 and matching valid binding, 24V. Running real-board minimized browser test.

- 2026-11-12 00:06:02: Real GLD1004 Model1 upload succeeded with 4 verified files, no NVS reset; GET_INFO and GET_STATUS confirmed identity and valid profile 3/binding. Real minimized/frozen browser: 2 → 11 → 20 samples; ordered. A 24-second sample span had max 529ms gap; five RX windows each had four unique samples and successful TX. No actual downlink observed. Hub/GLD restarted; CH/Gateway original PIDs retained. Protected Dataset 48 tests, UI, bridge and charts passed. Old packages preserved.
