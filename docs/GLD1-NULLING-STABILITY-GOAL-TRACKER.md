# GLD1 Model 1 — nulling stability hardening

Last tracker heartbeat: 2026-10-19 16:25:50 +07:00  
Last evidence update: 2026-10-19 16:25:50 +07:00

## Progress dashboard

| Scope | Progress | Status | Note |
|---|---:|---|---|
| **Overall goal** | **80%** | Waiting for external evidence | Software candidate is ready; physical calibration must not be assumed. |
| Phase 1. Audit and design | 100% | Done | Bounded decision-only stability gates selected. |
| Phase 2. GLD1-only repair and tests | 100% | Done | Native, UI, source isolation checks and firmware compile pass. |
| Phase 3. Build and Operator Hub package | 100% | Done | Exact Model 1 build and package integrity checks passed. |
| Phase 4. Physical validation | 0% | Waiting | User performs GLD1 upload/nulling and independent quality checks. |

## Progress calculation

`20% × 100 + 35% × (100+100+100)/3 + 25% × (100+100)/2 + 20% × 0 = 80%`. Work items within each phase have equal weights.

| Phase | Weight | Progress | Status | Closure evidence |
|---|---:|---:|---|---|
| 1. Audit and design | 20% | 100% | Done | Acceptance, saving and safety risks traced. |
| 2. GLD1-only repair and tests | 35% | 100% | Done | Native actual-service, UI and scope tests passed. |
| 3. Build and Operator Hub package | 25% | 100% | Done | Actual package manifest, marker, model provenance and flash hashes validated. |
| 4. Physical validation | 20% | 0% | Waiting | User-run repeated validation against independent reference. |

## Issue register

| ID | Status | Evidence | Next evidence gate |
|---|---|---|---|
| STAB-1 | Solved | Native actual-service tests reject unstable crossing, independent verify and final after three attempts. | Narrow software gate only; physical repeatability and accuracy remain STAB-2. |
| STAB-2 | Open | One fast run 409.524 s vs one baseline 476.964 s does not establish accuracy or repeatability. | Repeat real-device comparisons with independent reference. |
| STAB-3 | Open | Last COM7 readback had active profile 3 but model binding 1 and inference invalid. | User verifies status and model binding after their own hardware work; no automatic bind. |
| STAB-4 | Solved | Native actual-service max-DAC confirmation failure terminates with `confirm_failed`. | Monitor real-device execution separately. |
| STAB-5 | Solved in software | Model 1 failure attempts saved DAC restore and invalidates applied-profile/inference readiness; scope tests pass. | Actual restore behavior remains unverified on a device. |
| BUILD-1 | Solved | PIO Core 6.2.0 reinstalled SCons 4.41101 and removed 4.40801 on incremental build. | Build environment restored to previously observed SCons version. |

### Phase 1 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 1.1 | Audit unstable acceptance and saved-profile handling | 100% | Done | Trace code and captured evidence | Verify/final ignore stable; incomplete 8-channel result is not persisted; retry is operator-controlled. |
| 1.2 | Define bounded GLD1-only safety design | 100% | Done | Review scoped design and tradeoffs | Require stable recheck, independent verify and final, same-code retries bounded; exploratory scan remains unchanged. |

### Phase 2 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 2.1 | Implement scoped fail-closed check | 100% | Done | User-run hardware evidence in phase 4 | Actual firmware and fail-closed host checks pass; real device not yet checked. |
| 2.2 | Test stability, failure and profile safeguards | 100% | Done | User-run hardware evidence in phase 4 | Native actual-service tests, 11 source tests and exact build pass. |
| 2.3 | Protect other profiles and existing flows | 100% | Done | User-run hardware evidence in phase 4 | Other-board decision, alarm contract, UI reason and 159 non-Model-1 package-file hashes pass. |

### Phase 3 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 3.1 | Build GLD1 only and retain baseline | 100% | Done | Final package binary build and hashes | Exact `gld_model_1` package build succeeded; previous package is backed up. |
| 3.2 | Prepare validated Operator Hub candidate | 100% | Done | User selects GLD1 Model 1 in Operator Hub | Actual package, provenance, embedded model and uploader validators pass; baseline backup verified. |

### Phase 4 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 4.1 | User-run nulling and status | 0% | Waiting | User uploads and tests | No COM activity in this task. |
| 4.2 | Accuracy and repeatability | 0% | Waiting | Independent reference and repeat runs | A software pass is not calibration certification. |

## Protected baseline

GLD2/GLD3, alarm, LoRa, upload behavior, other model profiles and stored configuration remain protected. The Model 1 Operator Hub package was intentionally updated after a verified backup. No NVS reset, automatic bind, COM access, upload or nulling was performed by the agent in this task. Earlier artifacts and findings are in [previous tracker](GLD1-NULLING-OPTIMASI-GOAL-TRACKER.md).

## Current work / agent state

Tidak ada agent aktif saat ini.

## Evidence log

- 2026-10-19 16:11:19 +07:00 — Started scoped task. Previous single-run comparison and unstable final readings remain evidence, not a safety guarantee.
- 2026-10-19 16:11:58 +07:00 — Confirmed candidate verification and final acceptance ignore `stable`; one measurement window already exceeds the 15 ms cap. Normal Model 1 build automatically replaces the package directory, so backup and staged build are necessary.
- 2026-10-19 16:12:25 +07:00 — `saveCompleteNullingProfile` refuses incomplete results, and failed-channel retry is operator-requested. Runtime may merge successful channel results across retries; no claim of physical stability across time follows. Existing profile records are not automatically revalidated by a new firmware build.
- 2026-10-19 16:12:58 +07:00 — Independent GLD review recommends up to three same-DAC decision windows, no tolerance relaxation, and terminating unsuccessful max-DAC search. A successful software stability gate still cannot prove accuracy, repeatability, or NVS power-loss atomicity.
- 2026-10-19 16:13:35 +07:00 — Initial GLD1-only decision gates and max-DAC termination implemented. Single-channel failure handling is under review; no test or build result yet.
- 2026-10-19 16:14:48 +07:00 — Native test scaffold created for actual nulling source, but first compile failed because installed MinGW GCC 5 does not support C++17 nested namespace syntax. No passing native-test claim yet; adapting test compilation without modifying production logic.
- 2026-10-19 16:15:37 +07:00 — Native actual-service test now passes: stable 8/8; unstable recheck/verify/final rejected; unstable-to-stable retries; invalid/NaN, incomplete baseline, max-DAC termination, short write/corrupt readback. A legacy-board build preserves its previous decision rule. These are deterministic stubs, not analog hardware.
- 2026-10-19 16:15:37 +07:00 — Heartbeat SLA breach: observed gap 49 seconds since 16:14:48 while implementing and running native tests; no evidence or timestamp was backdated.
- 2026-10-19 16:16:20 +07:00 — 11 scoped nulling tests and alarm source contract pass. Isolated GLD1 compile started; package hash remains prior baseline. PIO replaced globally installed SCons version as noted in BUILD-1; restore after compile.
- 2026-10-19 16:17:00 +07:00 — Copied all seven current GLD1 Model 1 package files to `tmp/gld1-model1-pre-stability-20261019` and matched every SHA-256. No Operator Hub package changed during the isolated compile.
- 2026-10-19 16:17:49 +07:00 — Heartbeat SLA breach: observed gap 49 seconds since 16:17:00 while inspecting build and UI error display. No progress evidence or timestamp was backdated.
- 2026-10-19 16:18:31 +07:00 — Added readable GLD1-only stability failure reason descriptions to the existing nulling UI, without changing controls. JavaScript syntax and actual renderer tests pass; original error description still renders.
- 2026-10-19 16:19:18 +07:00 — Initial staged GLD1 build succeeded (RAM 41.5%, flash 15.9%). A small diagnostic/log change requires an incremental rebuild, underway with the original PIO 6.2 / SCons 4.41101 tool state restored.
- 2026-10-19 16:19:18 +07:00 — Heartbeat SLA breach: observed gap 47 seconds since 16:18:31 during build completion and tool restoration; timestamps are actual, not backdated.
- 2026-10-19 16:20:08 +07:00 — Re-ran native and UI tests successfully after the diagnostic adjustment. Captured SHA-256 fingerprint `617A6E80942B397E3E0C73DDEFEC0DF49DFF1022C3CA3D0C49044002E60D1F9B` across 159 non-Model-1 package files for later isolation verification.
- 2026-10-19 16:20:08 +07:00 — Heartbeat SLA breach: observed gap 50 seconds since 16:19:18 during package provenance inspection and fingerprinting; no backdating.
- 2026-10-19 16:20:50 +07:00 — Added candidate guide separating software safety checks, user-run validation, existing-profile/binding caveats and unproven accuracy. Early-code skip remains disabled due insufficient physical evidence.
- 2026-10-19 16:22:05 +07:00 — Final staged firmware build passed (RAM 41.5%, flash 15.9%). Exact `gld_model_1` build started; Operator Hub package is to be validated after its hook, including model sidecar and all flash hashes. The same firmware version label is not proof of installed binary identity.
- 2026-10-19 16:22:50 +07:00 — Native actual-service tests additionally prove that a bumped final DAC code receives an independent stable verification and that an unstable bumped verification is rejected. Previous SCons 4.41101 was verified restored.
- 2026-10-19 16:23:28 +07:00 — Existing child uploader package-validator regression passes 8/8. The real Model 1 package itself is still awaiting build and hash/model verification.
- 2026-10-19 16:24:01 +07:00 — The staged binary SHA-256 is `adf055fc7c7c89cfb80ee39cc784c8ab3592af66a1e858b367bb7f53981dfb17`, and it contains the `NULLING_STABILITY_GUARD=ON` identification marker. Exact package build remains in progress.
- 2026-10-19 16:25:17 +07:00 — Exact `gld_model_1` build succeeded in 162.57 s; package verification and provenance restoration remain. Heartbeat SLA breach: observed gap 76 s since 16:24:01, including an interrupted/truncated tool result; no timestamp was backdated.
- 2026-10-19 16:25:50 +07:00 — Exact Model 1 package firmware SHA-256 `f95119028d82be7f66cb3823d079a8227b0cb7edc8e2b7462bbc8299cd89ffdb` passed actual uploader and preflight validators, manifest/provenance, embedded model and guard-marker checks. The 159 other package files retain fingerprint `617A6E80942B397E3E0C73DDEFEC0DF49DFF1022C3CA3D0C49044002E60D1F9B`. Native actual-service and other-board tests, 11 nulling tests, 8 uploader validator tests, UI reason tests and alarm source contract all pass. This is software evidence only; user-controlled physical validation and independent calibration evidence remain waiting.
