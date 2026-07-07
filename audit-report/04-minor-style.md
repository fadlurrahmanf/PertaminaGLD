# 04 — Minor issues & style

Continues from `03-security-performance.md`. Low-impact correctness nits,
robustness gaps, and misleading comments. None block shipping; several are worth
a cleanup pass. Nothing here should trigger a rewrite of working code.

---

## M1 — Misleading "no remap" comment survives even after C1 is fixed

**Status: FIXED (comment updated only)** — C1 was resolved by reordering
`scaler_params.cpp` to physical order, so the "no remap" statement is now true
and was kept, with an added line noting the scaler must stay in this order.
The suggested boot-time size/order self-check was not added (would require a
new runtime assertion, judged unnecessary scope beyond the audited defect).

`firmware/gld/src/GldUnifiedMain.cpp:1493`
```cpp
// Channel n is fed directly as feature n (no remap - hardware channel order
// matches model feature order).
```

This comment asserts the very invariant that C1 shows is violated. Once C1 is
resolved by reordering `scaler_params.cpp`, the statement becomes true — but if
C1 is instead resolved by adding a remap map (the alternative in C1's fix), this
comment must be deleted. Either way, do not leave a comment claiming an alignment
the code does not enforce. Cheapest durable fix: add a `static_assert`-style
runtime check at boot that the model input size equals `SENSOR_COUNT` and log the
`feature_order` the firmware is using, so a future scaler/model swap surfaces a
mismatch instead of silently mis-scaling.

---

## M2 — `decodeGldPlainPayload` is called on GCM output but its range check is redundant / the CLUSTER response record loop is unbounded

**Status: FIXED (part a)** — `pertamina-gld-decode.js`'s
`MSG_CLUSTER_DATA_RESPONSE` loop now bounds-checks the record header and body
before reading, throwing a clear `truncated` error instead of a confusing
`NaN`-length crash. Part (b) required no change (firmware already safe).

Two small robustness gaps in the decode paths:

**(a)** `server/nodered/functions/pertamina-gld-decode.js:411`
```js
for (let i = 0; i < outer.response.recordCount; i++) {
    const payloadLenAtRecord = payload[offset + 4];
    const len = 5 + payloadLenAtRecord;
    records.push(parseGldRecord(payload.subarray(offset, offset + len)));
    offset += len;
}
```
`recordCount` comes from the frame body (`payload[5]`). If it is larger than the
records actually present, `payload[offset + 4]` reads past the buffer, yielding
`undefined` → `len = NaN` → `parseGldRecord` throws. The outer `try/catch`
(`:715`) turns it into a decode-error message, so no crash, but a single
corrupt-but-CRC-valid frame produces a confusing error. Add
`if (offset + 5 > payload.length) break;` before the read, and stop when
`offset + len > payload.length`.

**(b)** Firmware side is already safe here — `decodeGldRecord`
(`firmware/shared/src/GldRecord.cpp:52`) validates `recordLen`/`payloadLen`
strictly. No change needed on-device; this is a JS-only hardening note.

---

## M3 — `ClusterResponse` size-skip logic is dead code

**Status: left as-is** — harmless dead code, not a bug; simplifying it is a
"rewrite working code" style change outside this fix pass. Revisit if
variable-length records are ever planned, per the note below.

`firmware/ch/src/ClusterResponse.cpp:151`
```cpp
if (used + recordSize > maxPayload) {
    if (skippedCount < ...) { skippedIndexes[skippedCount++] = index; continue; }
    break;
}
```
Every GLD record is a fixed 34 bytes (`GLD_RECORD_PHASE1_SIZE`), so once one
record does not fit, no other record will either — the "skip this one and try a
smaller later record" branch can never succeed and just spins until
`skippedIndexes` (16 slots) fills, then breaks. Harmless but wasted work and
confusing intent. Simplify to a plain `break` on first non-fit, and drop the
`skippedIndexes` machinery, unless variable-length records are a planned future
(if so, leave a comment saying the skip logic is forward-looking).

---

## M4 — `read_packet` in the recorder crashes on a cleanly-closed socket mid-header

**Status: FIXED** — guarded the empty-`recv` case and now raises a clear
`ConnectionError("connection closed mid-header")`, matching the existing
pattern used elsewhere in the same function.

`server/nodered/gld_dataset_recorder.py:199`
```python
b = sock.recv(1)[0]
```
If the peer closes the connection between packets, `sock.recv(1)` returns `b""`
and `[0]` raises `IndexError`, which is caught by the broad
`except Exception` (`:259`) and treated as a generic error → 3-second reconnect.
Functionally recoverable, but the log line is misleading ("error: index out of
range"). Guard it:
```python
chunk = sock.recv(1)
if not chunk:
    raise ConnectionError("connection closed mid-header")
b = chunk[0]
```
matching the pattern already used correctly at `:194-196`.

---

## M5 — `package_firmware_release.required_file` has an unreachable fallthrough

**Status: FIXED** — replaced the dead `if not path.exists(): raise ...` tail
with an unconditional `raise FileNotFoundError(...)` after the loop.

`firmware/tools/package_firmware_release.py:67`
```python
for path in candidates:
    if path.exists():
        return path
if not path.exists():
    raise FileNotFoundError(...)
```
The function returns inside the loop on the first existing candidate and raises
otherwise, so it is correct in practice — but the trailing `if not path.exists()`
reads as if a non-raising fallthrough (returning `None`) were possible, and if
`candidates` were ever empty, `path` would be unbound (`NameError`). Replace the
tail with an unconditional `raise FileNotFoundError(...)` after the loop for
clarity and to remove the latent unbound-name path.

---

## M6 — Duplicated big-endian and idHex helpers across layers; version drift risk

**Status: left as-is** — style/maintainability note, not a bug; all existing
copies are byte-identical and correct today. Left for a future consolidation
pass rather than bundled into this fix commit.

`writeU16Be`/`readU16Be` are re-implemented independently in at least five files
(`AppFrame.cpp:7`, `GldRecord.cpp:7`, `GldPayload.cpp:7`, `ClusterResponse.cpp:11`,
`ChStarMeshRuntimeMain.cpp:729`, plus the gateway `:298`), and `idHex`/`cleanHex`
are re-declared in every Node-RED function string
(`apply-pertamina-gld-flow.js` and `pertamina-gld-decode.js`). They agree today,
but each copy is an independent place to drift. This is a style/maintainability
note, not a bug: the firmware copies are all byte-identical and correct. If a
shared `pgl::protocol` byte-order header is introduced, fold them in; the
Node-RED duplication is largely unavoidable given each function node is a
self-contained sandbox, so leave those but keep a single canonical copy in a
comment/source-of-truth file.

---

## Closing note

The two empty capture files `dataset/F001_clear_air_test_20260630_051653.csv` and
`...051701.csv` are 0 bytes. They are harmless but should either be removed or
regenerated, and — relevant to C1 — they cannot be used as an inference
regression baseline. Capture a fresh labeled dataset after the C1 fix and keep
one non-empty sample in-repo as a smoke test for the standardization path.
