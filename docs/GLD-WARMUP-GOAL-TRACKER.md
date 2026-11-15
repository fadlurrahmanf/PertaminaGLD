# GLD Warmup Goal Tracker

Last tracker heartbeat: 2026-11-11 15:51:25 WIB
Last evidence update: 2026-11-11 15:51:25 WIB

## Progress dashboard

| Scope | Progress | Status | Note |
|---|---:|---|---|
| **Overall goal** | **34.5%** | Paused by user | Continue GLD2 runtime integration and physical validation later. |
| Firmware readiness | 30% | Waiting for external evidence | Standalone evaluator passes native tests; runtime integration pending. |
| Operator indicator | 60% | Waiting for firmware integration | Optional-status UI and host tests; firmware integration pending. |
| Verification | 25% | Waiting for external evidence | One authorized cold-start being recorded; more evidence needed. |

## Progress calculation

`50%×30 + 20%×60 + 30%×25 = 34.5%`

| Phase | Weight | Progress | Status | Closure evidence |
|---|---:|---:|---|---|
| Firmware readiness | 50% | 30% | Waiting for external evidence | Source and focused tests |
| Operator indicator | 20% | 60% | Waiting for firmware integration | UI and compatibility tests |
| Verification | 30% | 25% | Waiting for external evidence | Build, regressions and physical validation |

## Issue register

| ID | Status | Evidence | Next evidence gate |
|---|---|---|---|
| W-1 | Open | Warmup parameters lack representative board measurements. | Cold-start samples and validation per variant. |
| W-2 | Open | Active GLD1 release uses a separate worktree; package hooks may overwrite artifacts. GLD1002 uses the newer Model 2 Workflow 0.8.36 image, a different baseline. | Verify each exact target and preserve existing packages. |
| W-4 | Open | GLD2 startup can restore a stored/pending alarm before power mode is established; battery handling shares this path. | Design and test scoped 24 V startup behavior without changing battery restore. |
| W-3 | Open | GLD1002 reported LPG/alarm through 17m23s in user-described clean air; gas concentration unmeasured. Final 8/8 averaged input voltages fall outside Model 2 declared min/max. | Investigate input mapping, nulling, training preprocessing and independently verified clean air; warmup gate alone cannot establish a fix. |

### Firmware readiness work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 1.1 | Audit power, alarm and release baselines | 40% | Waiting for external evidence | Complete transition and active-source mapping | GLD1 uses distinct release baseline; reference session confirmed Running/Dataset/Nulling baseline. |
| 1.2 | Add isolated readiness gate | 20% | Waiting for external evidence | Runtime integration after validated parameters | Parameterized standalone evaluator and native test pass; not connected to firmware. |

### Operator indicator work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 2.1 | Display live warmup status | 60% | Waiting for firmware integration | Firmware integration and browser validation | Optional UI tested in isolation. |

### Verification work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 3.1 | Build and regression | 30% | Waiting for firmware integration | All targeted checks | Native evaluator, chart and nulling checks pass. |
| 3.2 | Physical and threshold validation | 20% | Waiting for external evidence | Representative boards and full stability validation | First GLD1002 cold-start being recorded. |

Protected flows: existing AUTO/MANUAL alarm, battery, dataset, nulling, simulation, LoRa, model binding, sensor power and known-good firmware packages.

## Evidence log

- 2026-11-11 14:08 WIB: MinGW native evaluator tests passed for warmup time, stability, invalid readings, stale data, and timer rollover. No device interaction; no runtime integration.


- 2026-11-11 14:09:45 WIB: Heartbeat SLA breach: previous heartbeat was recorded only to minute at 14:08 WIB; observed interval exceeds one minute because source audit and regression checks ran before updating the tracker. Native test, nulling scope tests (4/4), and workflow chart regression passed. GLD2/3 power switching also occurs inside nulling; integration must account for this. Cold-start recording authorization requested; no COM access.


- 2026-11-11 14:10:55 WIB: Heartbeat SLA breach, 70 seconds since 14:09:45, caused by coordinating cold-start and compile checks. Native tests and ESP32-S3 cross-compilation of isolated evaluator pass. User asked whether to switch off; instructed to notify when off and await recording readiness. Runtime and UI remain untouched.


- 2026-11-11 14:11:46 WIB: User switched GLD off and will notify when cold before power-on. No COM access, firmware upload, or device reset. Bridge on port 5174 unavailable; recording path must be checked before power-on. No agent active; next gate is user notification and agreed recording setup.


- 2026-11-11 14:53:07 WIB: Recorder process waiting for COM7. GET_STATUS polling starts when USB enumerates; user instructed to power on. No firmware upload or NVS action.


- 2026-11-11 14:55:17 WIB: Recorder still waiting for COM7; user asked to confirm power-on. No samples yet.


- 2026-11-11 14:56:37 WIB: User powered GLD1002; recorder connected COM7 and received first status at uptime 1.6 seconds. Early telemetry invalid awaiting scan; collection continues. No upload/reset/NVS action.


- 2026-11-11 14:58:28 WIB: First valid telemetry at 65.543 s uptime; first valid inference at 72.227 s; latest reports LPG and commanded alarm ON. Real gas presence unknown. Capture uses firmware moving averages; no raw ADC data claimed.


- 2026-11-11 14:59:28 WIB: At 161.5 s uptime, last-30-second moving-average ranges were 0.4–21.2 mV across channels; this is one cold start and cannot validate thermal readiness. LPG classification/alarm still active; gas exposure unknown. Recorder remains active.


- 2026-11-11 15:00:48 WIB: Warmup notice component added behind optional firmware status and tested for legacy, warmup, failure, ready, timer, and disconnect. Running chart regression passes. Recorder continues; previous heartbeat 2026-11-11 14:59:28; check elapsed for SLA.



- 2026-11-11 15:01:45 WIB: UI module syntax checks and warmup notice tests pass, including absent capability/legacy state, fault and ready timer. Running chart test passes. First cold-start has exceeded five minutes; further hardware evidence required before any threshold is approved.


- 2026-11-11 15:02:26 WIB: COM7 recorder active; 356 s sample showed 30 s moving-average spreads of 0.1–9.6 mV, 120 s spreads 0.2–41.1 mV. No readiness threshold inferred from this single unit.


- 2026-11-11 15:13:16 WIB: User reports clean air with no known LPG source; actual gas concentration unmeasured. Optional warmup status now suppresses stale gas/confidence in Running; compatibility and chart regression tests pass. Continue COM7 recording to ten minutes.


- 2026-11-11 15:13:56 WIB: Heartbeat SLA breach: last recorded heartbeat 15:03:05 WIB; actual gap exceeded 10 minutes while work continued. Capture ran 17m23s after boot instead of the announced approximately 10m; stopped and COM7 released. GLD1002 continued reporting LPG 99% and alarm ON in user-described clean air. This single test cannot establish gas concentration or thermal readiness parameters.


- 2026-11-11 15:14:36 WIB: Capture audit: 1,648 status records, one invalid status response; 1,510 valid inference results all LPG/alarm ON; no uptime reversals. Source documentation identifies GLD1002 as Model 2 Workflow 0.8.36, separate from the older production GLD1 v0.8.38 release worktree.


- 2026-11-11 15:15:06 WIB: Compared final captured feature-order-matched 8 input values to firmware Model 2 ADC normalization min/max; all eight are outside their per-channel ranges. This is an observation, not proof of root cause or a reason to alter scaler/nulling speculatively.


- 2026-11-11 15:16:10 WIB: All 11 GLD Operator Node UI regression scripts passed. Across 1,510 valid inference status records, at least two inputs were outside model min/max in every record; in 1,063 records all eight were outside. This does not establish cause or gas concentration. Availability of additional variants requested.


- 2026-11-11 15:16:42 WIB: Read-only inspection of supplied Model 2 ZIP: notebook uses CSV gasName labels; CSV contains 6,330 inference-mode rows, all deviceId 1001. Current capture is device 1002. Label provenance and cross-device applicability are not established by that observation; do not change model/scaler without validation.


- 2026-11-11 15:16:56 WIB: User confirms GLD1, GLD2, GLD3 units available for future cold-start validation; no authorization to switch/reset/upload them inferred. Current COM7 capture complete and released.


- 2026-11-11 15:17:36 WIB: Heartbeat gap 41 seconds. Working on source provenance and regression; no device activity. Model 2 notebook computes ADC min/max from training split, CSV available in supplied ZIP contains device 1001, and independence of labels and cross-device model behavior remain unverified.


- 2026-11-11 15:21:40 WIB: User identifies GLD1002 as GLD2; latest workflow package manifest uses WROOM-1U/Model 2, not gld_v2 profile. Clarification requested before selecting hardware-specific code. Previous heartbeat 2026-11-11 15:17:36; record actual gap if SLA exceeded.


- 2026-11-11 15:22:54 WIB: Workflow Python regressions 40/40, nulling 4/4, and alarm source contract pass. GLD2 setup restores persisted/pending alarm before power identification: warmup integration needs a scoped boot solution protecting battery. User confirms target is GLD2; avoid imposing technical naming questions. Previous heartbeat 2026-11-11 15:21:40; check SLA gap.


- 2026-11-11 15:24:06 WIB: Heartbeat gap 72s (source/UI checks; breach if >60s). Legacy ML log is now prevented from replacing warmup-blocked result; lightweight status without fresh warmup goes back to unknown/warming rather than preserving READY. Focused UI and chart tests pass. Runtime gate remains disconnected.


- 2026-11-11 15:25:11 WIB: Manufacturer reference https://www.winsen-sensor.com/d/files/semiconductor/mq-2.pdf specifies over 48h preheat for standard test conditions. Actual sensor manufacturer not confirmed and this is not treated as a boot delay. Heartbeat gap 65s; record breach if >60s.


- 2026-11-11 15:27:02 WIB: User directed focus on GLD2 first and confirmed all variants are available for subsequent validation. 11 UI regression scripts, 40 Workflow tests, 4 nulling tests, alarm contract, native warmup and ESP32-S3 compile checks pass. No runtime gate, firmware build, package promotion or hardware flash occurred. Waiting for evidence to set defensible readiness parameters and resolve persistent LPG result; previous heartbeat gap 111s (breach if >60s).


- 2026-11-11 15:31:27 WIB: User requested continued root-cause work and GLD2 implementation; no device upload/reset authorization inferred. Current focus: model inputs, exact firmware baseline and readiness integration design.


- 2026-11-11 15:32:36 WIB: Replayed final GLD1002 input through Model 2 ADC normalization and int8 quantization: normalized [-0.63,-0.18,22.26,-0.02,-0.13,-0.13,-0.14,-0.13] maps to [-128,-128,127,-128,-128,-128,-128,-128]. Dataset CSV gasName is inference telemetry, not an independently verified gas reference; no root cause or gas absence asserted.


- 2026-11-11 15:34:35 WIB: Added isolated 24V warmup session controller; native scenario tests and ESP32-S3 compile pass. Tests cover rail unknown/loss, first-ready buffer reset signal, fresh inference, post-ready gas changes and battery bypass. Not wired into runtime; thresholds remain unvalidated. Heartbeat gap 120s; if >60s, SLA breach during source audit/implementation.


- 2026-11-11 15:44:34 WIB: Native actual TFLM replay of four captured vectors is compiling from archived Model 2 sources; no device access or model change. Heartbeat gap 600s; if >60s, SLA breach while designing and starting replay.


- 2026-11-11 15:48:03 WIB: Actual TFLM Model 2 host replay at 75.341, 180.279, 599.778, 1000.364 s reproduces class 1 with confidence 0.996094 at all four points. Model, scaler and sensitivity headers match checked-in Model 2 hashes; NN differs only by line endings. This validates reproducibility, not gas ground truth nor the exact live binary's full build identity.


- 2026-11-11 15:51:25 WIB: User requests to continue later. No process/device held. TFLM replay reproduces LPG for 4 recorded vectors. Standalone session controller and optional UI are not integrated into firmware. Remaining: investigate input/model/nulling mismatch, determine verified warmup parameters, integrate guarded 24V runtime including startup alarm and PCF power interruptions, build without replacing packages, run protected regression and authorized physical cold-start/gas checks. Prior heartbeat gap 202s; if >60s, heartbeat SLA breach while calculating capture trends.

