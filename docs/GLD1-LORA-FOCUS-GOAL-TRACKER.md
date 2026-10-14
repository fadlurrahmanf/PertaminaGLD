# GLD1 LoRa Focus Goal Tracker

Last updated: 2026-10-14 14:18 WIB  
Last tracker heartbeat: 2026-10-14 14:18 WIB

## Progress dashboard

| Scope | Progress | Status | Note |
|---|---:|---|---|
| **Overall goal** | **100%** | Host verification complete | Device/RF verification remains external. |
| Firmware contract | 100% | Complete | GLD1-only volatile focus path and separated direct-TX frame. |
| Operator LoRa panel | 100% | Complete | QC LoRa sub-tab beside TPL with concise log and controls. |
| Verification | 100% | Complete | GLD1 package build, hashes, UI syntax, and source-contract checks pass. |

## Progress calculation

`45% x 100 + 35% x 100 + 20% x 100 = 100%`

| Phase | Weight | Progress | Status | Closure evidence |
|---|---:|---:|---|---|
| 1. Firmware contract | 45% | 100% | Complete | GLD1 build and focused source tests pass. |
| 2. Operator LoRa panel | 35% | 100% | Complete | UI contract and syntax checks pass. |
| 3. Verification | 20% | 100% | Complete | Protected-flow regression checks pass. |

### Phase 1 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 1.1 | Add GLD1-only runtime interval and target contract | 100% | Complete | Source tests | 2026-10-14 14:18 WIB |
| 1.2 | Add separated non-CH direct radio transmission | 100% | Complete | GLD1 build | 2026-10-14 14:18 WIB |

### Phase 2 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 2.1 | Add QC LoRa sub-tab and focused controls | 100% | Complete | UI contract | 2026-10-14 14:18 WIB |
| 2.2 | Add concise LoRa activity log and read-back | 100% | Complete | UI interaction/source check | 2026-10-14 14:18 WIB |

### Phase 3 work items

| ID | Work item | Progress | Status | Next gate | Last update |
|---|---|---:|---|---|---|
| 3.1 | Run GLD1 build and focused tests | 100% | Complete | Passing output | 2026-10-14 14:18 WIB |
| 3.2 | Run protected Operator UI checks | 100% | Complete | Passing output | 2026-10-14 14:18 WIB |

## Issue register

| ID | Status | Evidence | Closure / next-evidence gate |
|---|---|---|---|
| LF-01 | Closed (host) | Direct-TX helper omits RX window; normal CH path remains unchanged. | Device/RF timing remains to be bench-tested. |
| LF-02 | Closed (host) | Direct frame begins `PGLFTX1`, not the AppFrame magic; normal path remains gated. | CH rejection and RF receipt need bench evidence. |
| LF-03 | Closed (host) | Auto Apply is OFF by default; manual Begin emits an explicit ACK and UI requests read-back. | Physical radio begin needs device evidence. |

## Current work / agent state

| Sub-agent / worker | Active work item | Started at | Elapsed | Progress | Activity / state |
|---|---|---|---|---:|---|
| Codex /root | GLD1 LoRa Focus | 2026-10-14 14:05 WIB | 00:13:00 | 100% | Complete; no device access. |

## Evidence log

- 2026-10-14 14:05 WIB — Scope approved: GLD1 only; LoRa sub-tab beside TPL; default interval 10 s, adjustable down to 1 s; explicit CH versus transmit-only target; no upload or hardware operation authorized.
- 2026-10-14 14:18 WIB — `pio run -e gld_model_1` passed with RAM 41.5% and flash 15.8%; refreshed Operator Hub `gld_model_1/latest` package hashes verified; JS syntax and source/UI contract checks passed. No COM, upload, reset, or RF test occurred.
