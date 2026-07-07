# Pertamina GLD — End-to-End Codebase Audit

**Scope:** first-party source only. Firmware (`firmware/gld`, `firmware/ch`,
`firmware/gateway`, `firmware/shared`, `firmware/config`), the Node-RED server
layer (`server/nodered`), the operator app (`apps/gld-operator`), and the
Python tooling. Vendored libraries (`firmware/lib/RadioLib`, `firmware/lib/tfmicro`,
`firmware/lib/PubSubClient`, `firmware/lib/ADS1256-main`, `firmware/lib/MCP4725`,
etc.) were treated as third-party and not line-audited. Design docs and PDF/mermaid
tooling were read only where they defined a contract the code must honor.

## Master verdict

The system is, on the whole, carefully engineered. The binary protocol layer
(`firmware/shared`) is clean, defensively coded, and covered by a host-side test
harness (`firmware/tests/test_shared_protocol.py`). The CH mesh runtime, node
cache, alarm queue, and TX queue are consistent and internally coherent. AES-GCM
framing and the AES-CMAC authenticated-downlink path match byte-for-byte between
the GLD firmware, the CH relay, and the Node-RED decoder/command builder — that
cross-layer agreement is the strongest part of the codebase.

**One confirmed critical defect dominated the verdict:** the ML feature
standardization in the GLD inference path fed the wrong per-sensor mean/std to
6 of 8 channels, because `scaler_params.cpp` was stored in a different sensor
order than the firmware reads and than the design's §8.6 "Feature Order
Alignment" mandates. Every inference on real hardware was affected.

**Status: all findings below have since been fixed in this branch** (see the
"Fixed" marker on each finding). `scaler_params.cpp` is reordered to physical
channel order; re-validate classification against a fresh labeled capture
before field deployment, since the two in-repo dataset CSVs are empty and
cannot serve as a regression check (see `04-minor-style.md`, closing note).

**Follow-up hardening (this session, post-merge):** added automated regression
guards for C1 and H1 to `firmware/tests/test_shared_protocol.py` (both
verified to actually fail against the pre-fix code, not just tautologically
pass), and a best-effort host-side validation of C1 against the real,
extracted, trained TFLite model — see `01-critical-bugs.md` for the honest
result (the bug's real-world impact is confirmed; the fix's directionality
relative to the actual training pipeline is still not fully closed out from
source alone, and still needs either the training script or a real hardware
capture). The two empty `dataset/F001_clear_air_test_*.csv` files were left in
place — deleting them was outside what was explicitly authorized.

## Severity counts

| Severity | Count | IDs | Status |
|---|---:|---|---|
| Critical | 1 | C1 | Fixed |
| High | 2 | H1, H2 | Fixed |
| Medium (security / performance) | 5 | S1, S2, S3, S4, P1 | Fixed (S3 informational, no code change) |
| Minor / style | 6 | M1–M6 | M1, M2, M4, M5 fixed; M3, M6 left as-is (style/dead-code, not bugs) |

Findings are numbered once here and carried forward; later files continue the
sequence rather than repeating earlier detail. Each finding gives **what breaks**,
**trigger**, **root cause**, and **exact fix**, with `file:line` anchors. Fixes
were applied directly on top of these reports in the same branch; the original
analysis is left intact below each fix marker for traceability.

- `01-critical-bugs.md` — C1
- `02-high-priority.md` — H1, H2
- `03-security-performance.md` — S1, S2, S3, S4, P1
- `04-minor-style.md` — M1–M6

## What is solid (verified, do not touch)

- **`firmware/shared/src/AppFrame.cpp`** — CRC-16/CCITT-FALSE, length/magic/bounds
  checks on both encode and decode are correct and symmetric. Matches the JS
  decoder's `crc16CcittFalse` and the Python test vectors.
- **`firmware/shared/src/GldCrypto.cpp`** — AES-128-GCM with 12-byte tag and the
  AES-CMAC (RFC 4493) subkey/padding logic are implemented correctly; the CMAC
  `k1/k2` derivation and last-block handling match the Node-RED `aesCmac`
  reimplementation in `apply-pertamina-gld-flow.js`.
- **`firmware/gld/src/GldCommandParser.cpp`** — authenticated downlink verifies
  magic → CRC → msg type → dstId → CMAC tag → monotonic `commandId` replay window
  (`commandIdIsNewer`, half-range wraparound). Replay/forgery protection is sound.
- **`firmware/ch/*`** — NodeCache dedup/conflict handling, AlarmQueue
  absent-only enqueue, and the TX-queue peek/pop/mark lifecycle are consistent;
  cluster-response record packing respects `MESH_MAX_PAYLOAD`.
- **`firmware/shared/src/GldPayload.cpp` / `GldRecord.cpp`** — gas-class and
  confidence range validation, big-endian helpers, and record sizing are correct.

These were checked against the protocol constants in
`firmware/shared/include/ProtocolConstants.h` and the Python model in
`firmware/tests/test_shared_protocol.py`; no defects found.
