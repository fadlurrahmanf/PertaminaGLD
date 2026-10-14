# GLD1 LoRa QC Matrix Goal Tracker

Last updated: 2026-10-14 22:04 WIB
Last tracker heartbeat: 2026-10-14 22:04 WIB

## Progress dashboard

| Scope | Progress | Status | Note |
|---|---:|---|---|
| **Overall goal** | **100%** | Complete (host/mock) | All requested source, build, and mock gates are closed; physical RF/CH remains external. |
| GLD1 firmware matrix | 100% | Complete (build) | GLD1 build passed and the execution branches explicitly exclude GLD2. |
| Operator LoRa QC | 100% | Complete (mock) | Manual/Auto Begin, read-back, compact activity, validation, and visual layout were exercised. |
| Mock evidence and regression | 100% | Complete (host/mock) | Four timed modes, gate bypass, radio faults, package and protected-flow checks passed. |

## Progress calculation

`45% x 100 + 30% x 100 + 25% x 100 = 100%`

| Phase | Weight | Progress | Status | Closure evidence |
|---|---:|---:|---|---|
| 1. GLD1 firmware matrix | 45% | 100% | Complete (build) | GLD1-only build passed and profile guards inspected. |
| 2. Operator LoRa QC | 30% | 100% | Complete (mock) | Browser proof of manual/auto Begin, read-back, validation, and log contract. |
| 3. Mock evidence and regression | 25% | 100% | Complete (host/mock) | All required mock timing/fault proofs, package checks, and protected checks passed. |

### Phase 1 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 1.1 | Isolate GLD1 scheduler and interval rules | 100% | Complete | GLD1 build and explicit `&& !PGL_GLD_BOARD_PROFILE_GLD2` guards. | 2026-10-14 22:04 WIB |
| 1.2 | Implement CH-normal, CH-dummy, and test-frame paths | 100% | Complete | Build and four-mode mock evidence. | 2026-10-14 22:04 WIB |
| 1.3 | Emit machine-readable TX activity only for GLD1 matrix path | 100% | Complete | Browser consumed `GLD_LORA_EVENT_JSON` with sequence/delta/fault fields. | 2026-10-14 22:04 WIB |

### Phase 2 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 2.1 | Replace Apply with one manual LoRa Begin flow | 100% | Complete | Browser mock manual Begin/read-back. | 2026-10-14 21:56 WIB |
| 2.2 | Add two-second Auto Begin debounce and cancellation | 100% | Complete | Browser proof after idle and after timer cancellation/restart. | 2026-10-14 22:04 WIB |
| 2.3 | Render compact active-readback and TX activity | 100% | Complete | Visual screenshot and concise timing/fault log proven. | 2026-10-14 22:04 WIB |

### Phase 3 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 3.1 | Simulate all four modes at minimum intervals | 100% | Complete | Four timestamp/delta logs plus browser screenshots. | 2026-10-14 21:56 WIB |
| 3.2 | Simulate gates, debounce, validation, and radio failures | 100% | Complete | Gate bypass, 1 s rejection, debounce, cancellation, and four radio faults recorded. | 2026-10-14 22:04 WIB |
| 3.3 | Build GLD1/package and re-run protected checks | 100% | Complete | Build, SHA match, 49 protected/static checks, and GLD2/3 diff guard passed. | 2026-10-14 22:04 WIB |

## Issue register

| ID | Status | Evidence | Closure / next-evidence gate |
|---|---|---|---|
| LMQ-01 | Accepted risk | Focus + Ke CH is structurally valid but intentionally not AES-authenticated. | Requires real authenticated CH/device test; no acceptance or RF receipt is claimed. |
| LMQ-02 | Solved | Mock now schedules TX events at active config cadence and emitted 4×~3 s and 6×~1 s sequences for all four modes. | Keep only browser evidence; physical RF remains external. |
| LMQ-03 | Solved | Browser screenshot shows the compact two-card parameter/activity layout. | Physical screen-size validation is optional external evidence. |
| LMQ-04 | Solved | GLD1 build passed twice and package firmware SHA matches manifest. | No COM/upload action was taken. |

## Current work / agent state

| Sub-agent / worker | Active work item | Started at | Elapsed | Progress | Activity / state |
|---|---|---:|---:|---:|---|
Tidak ada agent aktif saat ini.

## Evidence log

- 2026-10-14 21:49 WIB — Goal restarted for the explicit GLD1-only matrix. Protected: GLD2/GLD3, alarm, nulling, and upload flow. Source now removes QC Apply, uses one Begin sequence, and includes an Auto Begin debounce path. JS syntax checks passed; browser/build/device proof has not yet occurred.
- 2026-10-14 21:51 WIB — `pio run -e gld_model_1` passed (RAM 41.5%, flash 15.8%) and refreshed only the Operator Hub `gld_model_1/latest` package. No COM, upload, reset, or RF operation occurred.
- 2026-10-14 21:56 WIB — Heartbeat SLA breach: 00:05:00 elapsed while four browser timing runs were collected; the tracker was not refreshed between runs. No progress was inferred from the heartbeat. Evidence: Focus OFF + Ke CH and Focus OFF + Transmit saja each emitted four successful TX events at 3.000 s deltas; Focus ON + Ke CH (AES/ADS/sensor/model/inference unavailable) and Focus ON + Transmit saja each emitted six successful TX events at ~1.000 s. Focus + Ke CH log showed `CH ID 0064`, `frame 39 B`, and `RX off`. Screenshots were captured in the local browser. This is mock-only evidence.
- 2026-10-14 22:00 WIB — Browser mock fault proof: all four mode combinations emitted `TX ... GAGAL | SX1262/SPI/radio tidak siap` when a post-Begin radio fault was injected. Auto Begin fired once after 2 s of inactivity and a second edit cancelled/restarted its pending timer; 1 s with Focus OFF was rejected. Explicit `&& !PGL_GLD_BOARD_PROFILE_GLD2` guards were added to the new GLD1 execution branches before the final rebuild.
- 2026-10-14 22:04 WIB — Final host checks passed: the second GLD1-only build refreshed the Operator Hub package (RAM 41.5%, flash 15.8%), manifest firmware SHA matches package SHA, `git diff --check` is clean, no GLD2/GLD3 paths changed, JS syntax passed, and 49 protected/static tests passed. Full mock timing and fault evidence is in `docs/GLD1-LORA-MOCK-VERIFICATION.md`. No physical radio/CH claim is made.
