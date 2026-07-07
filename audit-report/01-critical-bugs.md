# 01 — Critical bugs

Continues from `00-summary.md`. One confirmed critical defect.

---

## C1 — ML feature standardization applies the wrong mean/std to 6 of 8 sensors

**Severity:** Critical — corrupts every on-device inference and therefore every
alarm/gas-class decision made in the field.

**Verdict:** CONFIRMED (cross-checked code ↔ design contract; the actual
misclassification magnitude depends on real sensor values, but the ordering
mismatch itself is unambiguous).

### What breaks

In INFERENCE mode the GLD standardizes each moving-averaged sensor voltage with
a per-feature mean/std before feeding the TFLite model:

`firmware/gld/src/GldUnifiedMain.cpp:1493`
```cpp
// Channel n is fed directly as feature n (no remap - hardware channel order
// matches model feature order).
for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
    modelInput[ch] = (mavVoltage[ch] - feature_means[ch]) / feature_stds[ch];
}
```

`mavVoltage[ch]` is indexed in **hardware channel order**, defined in
`firmware/gld/include/BoardPins.h:149`:
```
SENSOR_NAMES = { MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2 }   // ch0..ch7
```

But `feature_means[]` / `feature_stds[]` are stored in a **different** order,
per their own labels in `firmware/gld/model/scaler_params.cpp:4`:
```
feature_means = { MQ135, MQ2, MQ3, MQ4, MQ7, MQ5, MQ6, MQ8 }  // idx0..idx7
```

So the standardization pairs are:

| ch | hardware sensor (`mavVoltage[ch]`) | `feature_means[ch]` label | aligned? |
|---:|---|---|:--:|
| 0 | MQ8   | MQ135 | ✗ |
| 1 | MQ135 | MQ2   | ✗ |
| 2 | MQ3   | MQ3   | ✓ |
| 3 | MQ5   | MQ4   | ✗ |
| 4 | MQ4   | MQ7   | ✗ |
| 5 | MQ7   | MQ5   | ✗ |
| 6 | MQ6   | MQ6   | ✓ |
| 7 | MQ2   | MQ8   | ✗ |

Six of eight channels are standardized with another sensor's statistics. The
resulting z-scores are wrong, so the model receives out-of-distribution inputs
and its class probabilities are meaningless. `runScan()` then derives the alarm
from that output (`GldUnifiedMain.cpp:1525`), so both classification and alarm
raising are unreliable.

### Trigger

Any boot into INFERENCE mode on real hardware, once the moving-average windows
are primed (`runScan()` → `runInference()`), i.e. normal operation. The bench
self-test path (`firmware/gld/src/main.cpp`) does not exercise the model, so this
is invisible to the existing tests.

### Root cause

The design explicitly forbids a runtime remap and requires all three orderings
to be identical — `docs/design/gld/design.md:1466` (§8.6 Feature Order Alignment):

> Urutan channel fisik, urutan baca firmware, dan urutan feature model harus sama.
> … remap feature tidak dipakai.

The firmware honors that (no remap, `channel n → feature n`). The violation is in
the exported scaler table: `scaler_params.cpp` was generated in the training
pipeline's column order (which is not the physical order) and committed without
being re-ordered to the mandated physical order. The comment at
`GldUnifiedMain.cpp:1493` asserts the orders match; they do not.

### Exact fix

Re-order the two arrays in `firmware/gld/model/scaler_params.cpp` so index `i`
holds the statistics for physical channel `i` = `SENSOR_NAMES[i]`
(`MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, MQ2`). Using the values already present
in the file (keyed by their labels):

```cpp
const float feature_means[8] = {
    1.0096667,          // ch0 MQ8
    1.151226426190476,  // ch1 MQ135
    0.8747941047619049, // ch2 MQ3
    3.120307857142857,  // ch3 MQ5
    0.849981730952381,  // ch4 MQ4
    0.8076531452380953, // ch5 MQ7
    0.8551023309523809, // ch6 MQ6
    0.9155299452380952, // ch7 MQ2
};
const float feature_stds[8] = {
    0.9062927429386844, // ch0 MQ8
    0.6836354136532563, // ch1 MQ135
    0.5358539933242062, // ch2 MQ3
    0.4780387180480543, // ch3 MQ5
    0.7398564334928974, // ch4 MQ4
    0.4721864452266815, // ch5 MQ7
    0.669980479449558,  // ch6 MQ6
    0.8188832805994214, // ch7 MQ2
};
```

**Before shipping this fix, verify one thing that this audit cannot from source
alone:** that the *TFLite model itself* was trained with input features in the
physical order. Reordering the scaler is correct **only if** the model's input
layer expects physical order. Confirm against the training notebook/script:

- If the model input is in physical order → apply the reorder above; the model
  and scaler are then both aligned and no code change to `runInference` is needed.
- If the model input is in the scaler's current (training) order → the correct
  fix is instead to add a physical→feature index map in `runInference` and use it
  for both `feature_means`/`feature_stds` **and** the input tensor, and delete the
  "no remap" comment. Do not do both.

Either way, re-validate classification on a labeled capture after the change; the
two `dataset/F001_clear_air_test_*.csv` files are empty and cannot serve as a
regression check.
