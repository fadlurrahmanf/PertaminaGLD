# GLD1 Model 1 — perbaikan penolakan nulling

Last tracker heartbeat: 2026-10-19 17:01:07 +07:00  
Last evidence update: 2026-10-19 17:01:07 +07:00

## Progress dashboard

| Scope | Progress | Status | Note |
|---|---:|---|---|
| **Overall goal** | **85%** | Waiting for external evidence | Software candidate packaged; operator-controlled hardware and calibration remain. |
| Phase 1. Diagnose and protect baseline | 100% | Done | Baseline copied and hashed; GLD review complete. |
| Phase 2. Scoped repair and simulation | 100% | Done | Reviewed actual-service simulations and protected-flow checks pass. |
| Phase 3. GLD1 package and regression checks | 100% | Done | Exact Model 1 build and package integrity/isolation validated. |
| Phase 4. Physical validation | 0% | Waiting | Operator tests hardware, not the agent. |

## Progress calculation

`20% × (100+100)/2 + 40% × (100+100+100)/3 + 25% × (100+100)/2 + 15% × 0 = 85%`. Work items within each phase have equal weights.

| Phase | Weight | Progress | Status | Closure evidence |
|---|---:|---:|---|---|
| 1. Diagnose and protect baseline | 20% | 100% | Done | Baseline verified; bounded/fail-closed design reviewed. |
| 2. Scoped repair and simulation | 40% | 100% | Done | Review, actual-service and protected-flow checks passed. |
| 3. GLD1 package and regression checks | 25% | 100% | Done | Exact build, restored provenance, model, manifest and package isolation pass. |
| 4. Physical validation | 15% | 0% | Waiting | Operator-run device results and independent reference. |

## Issue register

| ID | Status | Evidence | Closure / next evidence gate |
|---|---|---|---|
| REJ-1 | Solved in software | Bounded recovery tests succeed after an unstable first bracket and first candidate. | Exact current-run cause and physical availability remain REJ-2. |
| REJ-2 | Open | Prior run showed unstable crossing/verification/final readings. | Validate new actual-device raw attempt logs; don't loosen tolerance blindly. |
| REJ-3 | Solved in software | Tests reach a stable seventh candidate and reject unstable final. | Hardware and calibration quality remain unproven. |
| REJ-4 | Solved in software | Bounded bracket recovery and hard DAC/ADC failure cases pass. | Physical behavior remains unproven. |
| REJ-5 | Deferred | Screenshot displays TCA no ACK although GLD1 telemetry is not a live probe. | Separate indicator fix outside nulling scope; do not infer TCA hardware failure. |
| REJ-6 | Solved | Actual-service host test proves an invalid decision window stops before a later valid window. | Physical ADC behavior remains unverified. |
| REJ-7 | Solved | Actual-service host test proves six unstable candidates can be followed by a successful seventh; all 75 scan candidates remain bounded. | Physical residual quality and run time remain unverified. |
| REJ-8 | Deferred | Existing profile algorithm version remains unchanged, so old NVS profiles are not automatically revalidated by the new guard. | Operator must rerun full nulling and independently verify; no silent NVS migration or invalidation. |
| REJ-9 | Deferred | Existing fast timing guards check whether macro is defined; nonstandard macro=0 or misuse on another board may change timing. | Official build declares =1 only for Model 1; do not silently alter other configurations. |

### Phase 1 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 1.1 | Trace rejection logic and prior device evidence | 100% | Done | Actual current-run logs and device evidence remain in phase 4 | Early-abort paths confirmed; prior channel had zero stable confirm points. |
| 1.2 | Preserve baseline and non-Model-1 artifacts | 100% | Done | Verify hashes after package build | All seven current files backed up and hashed; 159 other package-file fingerprint recorded. |

### Phase 2 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 2.1 | Implement GLD1 bounded rejection recovery | 100% | Done | Physical evidence remains in phase 4 | Reviewer confirms fixes, hard errors stop and GLD1 search is bounded. |
| 2.2 | Test recovery, exhaustion and safety invariants | 100% | Done | Physical evidence remains in phase 4 | Invalid-then-valid is rejected; stable seventh candidate is reached and accepted. |
| 2.3 | Test isolation and protected workflows | 100% | Done | Physical evidence remains in phase 4 | Legacy decision behavior, 11 nulling tests, UI reason, alarm contract and 159 other package-file hashes pass. |

### Phase 3 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 3.1 | Build GLD1 Model 1 candidate | 100% | Done | Physical evidence remains in phase 4 | Exact `gld_model_1` build passed (RAM 41.5%, flash 15.9%). |
| 3.2 | Validate Operator Hub package and rollback | 100% | Done | User-run upload and status remain in phase 4 | Actual package, embedded model, preflight, child uploader, provenance, manifest and backup verified. |

### Phase 4 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 4.1 | Operator runs GLD1 nulling | 0% | Waiting | Operator uploads and collects raw log | No hardware action by agent. |
| 4.2 | Verify calibration quality | 0% | Waiting | Repeatability and independent reference | Software PASS is not operational safety proof. |

## Protected baseline

GLD2/GLD3, other GLD1 models, alarm, LoRa, upload workflow, NVS and binding are protected. No physical device, COM, reset, upload or binding by the agent. Preserve the existing operator package and its pre-guard backup before replacing any artifact. No tolerance relaxation merely to obtain PASS.

## Current work / agent state

Tidak ada agent aktif saat ini.

## Evidence log

- 2026-10-19 16:52:22 +07:00 — User screenshot shows all eight failed after stability guard; prior agent analysis found early abort on unstable crossing and first verify candidate. Current run's raw log is not available, so exact per-channel cause remains unproven.
- 2026-10-19 16:52:39 +07:00 — Read-only GLD and packaging reviews dispatched with disjoint scope; no device access authorized for this task.
- 2026-10-19 16:53:12 +07:00 — Copied and verified all seven current Model 1 package files in `tmp/gld1-model1-before-rejection-fix-20261019-1653`; 159 other package files fingerprint `617A6E80942B397E3E0C73DDEFEC0DF49DFF1022C3CA3D0C49044002E60D1F9B`. Packaging audit confirms NVS readback failure does not guarantee previous contents intact. Prior hardware confirm-stage stable observations by channels 1–8 were 9/21, 9/27, 9/61, 9/21, 6/60, 2/49, 0/30, 30/74 respectively; these are older data, not current-run proof.
- 2026-10-19 16:53:45 +07:00 — GLD review identified premature channel abort at unstable crossing and first unstable candidate; recommended bounded monotonic alternate search, hard ADC/DAC failure termination, and unchanged stable independent final checks. Review is complete; this design does not establish real-device availability or calibration accuracy.
- 2026-10-19 16:54:24 +07:00 — Initial Model 1 bounded recovery implemented (maximum four rejected brackets, six candidate verifies per bracket); ADC-invalid and DAC-write failures stop instead of becoming valid measurements. First native run failed its old immediate verify-failure assertion; tests are being expanded, so no passing claim yet.
- 2026-10-19 16:54:56 +07:00 — Expanded actual-service native simulation passes stable 8/8, recheck recovery, verify-candidate recovery, bounded repeated instability, invalid ADC, failed DAC, unstable final, final-bump verification and NVS readback. Legacy decision behavior, 11 nulling tests, UI descriptions and alarm source contract pass. Analog quality and new physical run remain unverified.
- 2026-10-19 16:55:32 +07:00 — Native simulation additionally proves end-to-end ADC invalid and DAC write errors terminate without bracket retry, and verifies six unstable candidates are the bounded limit. Added distinct Indonesian UI explanations for these two hard errors; native and UI tests pass.
- 2026-10-19 16:55:41 +07:00 — Dispatched independent read-only GLD code review; operator activity log records that its separate UI scope entry was added after the change (sequencing error).
- 2026-10-19 16:56:12 +07:00 — Started isolated GLD1 candidate compilation with package post-hook disabled. Existing Operator Hub package has not been replaced; build and independent review remain in progress.
- 2026-10-19 16:56:43 +07:00 — Initial isolated build passed (RAM 41.5%, flash 15.9%). Added `NULLING_RECOVERY=ON` marker to distinguish the revised binary from previous guarded firmware; native and UI tests passed again and isolated rebuild is running. Operator Hub package remains untouched.
- 2026-10-19 16:57:21 +07:00 — Final isolated candidate build passed SHA-256 `0173ae85a38a552c905551d26163547332812cac20652d26f1bed23ef982e0fe`. Ten deterministic full 8-channel recovery simulations passed (same fake model, not ten independent hardware trials); an all-invalid ADC run failed closed. Independent review is pending.
- 2026-10-19 16:58:25 +07:00 — Independent review found transient invalid ADC can be masked by a later stable retry and that the six-candidate cap can skip a valid seventh candidate. Publication is held; progress reduced honestly pending repair and new tests. Heartbeat SLA breach: actual gap 64 seconds since 16:57:21 during detailed review and wait; no timestamp was backdated.
- 2026-10-19 16:59:00 +07:00 — Fixed invalid decision-window masking and removed premature cap of six (bounded by the 75-point confirm window). Native tests prove invalid-then-valid is rejected and a stable seventh candidate is reached. The revised isolated build is in progress. Existing NVS profiles retain algorithm version 16 and do not automatically gain the new checks; no silent invalidation will be performed.
- 2026-10-19 16:59:48 +07:00 — Revised isolated firmware build passed (RAM 41.5%, flash 15.9%). Nulling source tests 11/11 and child uploader validator tests 8/8 pass. Updated candidate guide describes bounded search and the old-profile caveat. Heartbeat SLA breach: observed gap 48 seconds since 16:59:00 during review and regression checks; timestamps not backdated.
- 2026-10-19 17:00:25 +07:00 — Independent reviewer confirms invalid-window and seventh-candidate repairs, bounded search, and no identified ADC/DAC hard-failure pass path. Existing version-16 profiles are not automatically revalidated; nonstandard macro=0 timing scope remains deferred. Exact `gld_model_1` release build started; the hook will replace only its package, and provenance/manifest must be verified before use.
- 2026-10-19 17:00:30 +07:00 — Independent GLD review completed with no further blocker under explicit old-profile compatibility and required new nulling; reviewer released.
- 2026-10-19 17:01:07 +07:00 — Exact `gld_model_1` build and Operator Hub package validation passed. Firmware SHA-256 `a0e7d32a022189d8ca7bb4924912fbea5eab66110e122e4890f7600be91fd389` matches release binary, manifest and provenance; embedded model and unique recovery marker verified. All 159 non-Model-1 package files retain fingerprint `617A6E80942B397E3E0C73DDEFEC0DF49DFF1022C3CA3D0C49044002E60D1F9B`. Post-build native, UI and source/uploader regressions pass. No hardware or COM used; real calibration and repeatability remain waiting for user-controlled evidence.
