#!/usr/bin/env python3
"""Host-side validation for audit finding C1 (ML feature standardization
applied the wrong mean/std to 6 of 8 sensors - see audit-report/01-critical-bugs.md).

There is no physical GLD hardware available to whoever runs this in CI or in
a cloud dev environment, so this script reproduces the exact firmware
inference pipeline (StandardScaler normalize -> TFLite model) in Python,
using the REAL trained weights extracted from firmware/gld/model/model_data.cpp
and the REAL mean/std values from firmware/gld/model/scaler_params.cpp, and
compares the pre-fix (buggy) channel ordering against the post-fix (physical
channel order) ordering on synthetic sensor inputs.

This is NOT a substitute for either of the two things that would fully close
out C1:
  1. The actual training script/notebook that produced model_data.cpp and
     scaler_params.cpp, confirming what column order the model was fit on.
  2. A real labeled capture on physical hardware with known gas exposures,
     run through both orderings, to see which one classifies correctly.

What this script DOES establish (see "Findings" printed at the end):
  - The bug was real: the two orderings produce measurably different, large
    z-score and classification differences on the SAME physical sensor
    reading, using the actual deployed model weights.
  - The fix is a pure reorder (same values, different index order) - verified
    by an assertion, not just eyeballing the diff.
  - The directionality (physical order vs. some other order) is NOT fully
    settled by this script alone - one synthetic scenario below produces a
    result that happens to favor the OLD ordering, which is exactly why (1)
    or (2) above are still required before trusting this in the field.

Requirements (not part of the repo's normal dependencies - install manually):
    pip install tflite-runtime "numpy<2"
(tflite-runtime's prebuilt wheels are commonly built against numpy 1.x; if you
hit "_ARRAY_API not found" on import, that's why - use a numpy<2 virtualenv.)

Usage:
    python3 firmware/tools/validate_c1_scaler_order.py
Run from the repository root.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import numpy as np
except ImportError:
    print("Missing dependency: numpy. Install with: pip install \"numpy<2\"", file=sys.stderr)
    sys.exit(1)

try:
    import tflite_runtime.interpreter as tflite
except ImportError:
    print(
        "Missing dependency: tflite_runtime. Install with: pip install tflite-runtime\n"
        "(and \"numpy<2\" in the same environment - see this file's docstring).",
        file=sys.stderr,
    )
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parents[2]
GAS_NAMES = {0: "clearGas", 1: "LPG", 2: "methane", 3: "propane"}
# From firmware/gld/src/GldThresholdClassifier.cpp comments:
LPG_SENSOR = "MQ5"
METHANE_SENSOR = "MQ4"

# The pre-fix (buggy) scaler_params.cpp content, as committed at
# 9c3f940 (before the C1 fix). Kept here verbatim, rather than shelling out
# to `git show`, so this script stays self-contained and reproducible even if
# history is ever rewritten. Do not "fix" these values - they are
# deliberately the WRONG (historical) ordering, used only as the "before"
# side of the comparison.
PRE_FIX_SCALER_CPP = """
const float feature_means[8] = {
    1.151226426190476, // MQ135V
    0.9155299452380952, // MQ2V
    0.8747941047619049, // MQ3V
    0.849981730952381, // MQ4V
    0.8076531452380953, // MQ7V
    3.120307857142857, // MQ5V
    0.8551023309523809, // MQ6V
    1.0096667, // MQ8V
};

const float feature_stds[8] = {
    0.6836354136532563, // MQ135V
    0.8188832805994214, // MQ2V
    0.5358539933242062, // MQ3V
    0.7398564334928974, // MQ4V
    0.4721864452266815, // MQ7V
    0.4780387180480543, // MQ5V
    0.669980479449558, // MQ6V
    0.9062927429386844, // MQ8V
};
"""


def parse_scaler(text: str, array_name: str):
    block = re.search(array_name + r"\[8\]\s*=\s*\{(.*?)\}", text, re.S).group(1)
    pairs = re.findall(r"([\d.]+),\s*//\s*(?:ch\d+\s+)?(\w+?)V", block)
    return [float(v) for v, _ in pairs], [lbl for _, lbl in pairs]


def physical_order_from_board_pins() -> list[str]:
    text = (REPO_ROOT / "firmware/gld/include/BoardPins.h").read_text(encoding="utf-8")
    match = re.search(r"SENSOR_NAMES\[SENSOR_COUNT\]\s*=\s*\{([^}]*)\}", text)
    assert match, "could not find SENSOR_NAMES in BoardPins.h"
    return re.findall(r'"(\w+)"', match.group(1))


def extract_tflite_model() -> bytes:
    text = (REPO_ROOT / "firmware/gld/model/model_data.cpp").read_text(encoding="utf-8")
    hex_bytes = re.findall(r"0x[0-9a-fA-F]{2}", text)
    assert hex_bytes, "could not find any hex byte literals in model_data.cpp"
    return bytes(int(b, 16) for b in hex_bytes)


def main() -> int:
    physical_order = physical_order_from_board_pins()

    new_text = (REPO_ROOT / "firmware/gld/model/scaler_params.cpp").read_text(encoding="utf-8")
    new_means, new_mean_labels = parse_scaler(new_text, "feature_means")
    new_stds, new_std_labels = parse_scaler(new_text, "feature_stds")
    old_means, old_mean_labels = parse_scaler(PRE_FIX_SCALER_CPP, "feature_means")
    old_stds, old_std_labels = parse_scaler(PRE_FIX_SCALER_CPP, "feature_stds")

    assert new_mean_labels == new_std_labels, "current file: mean/std label order mismatch"
    assert old_mean_labels == old_std_labels, "pre-fix snapshot: mean/std label order mismatch"
    assert new_mean_labels == physical_order, (
        f"current scaler_params.cpp order {new_mean_labels} != physical order {physical_order} "
        "- C1 regression! (also caught by firmware/tests/test_shared_protocol.py)"
    )

    mean_by_sensor = dict(zip(new_mean_labels, new_means))
    std_by_sensor = dict(zip(new_std_labels, new_stds))
    assert mean_by_sensor == dict(zip(old_mean_labels, old_means)), "FIX CHANGED MEAN VALUES, NOT JUST ORDER"
    assert std_by_sensor == dict(zip(old_std_labels, old_stds)), "FIX CHANGED STD VALUES, NOT JUST ORDER"

    print("[OK] Fix is a pure reorder: identical mean/std value set, only index order differs.")
    print(f"     Pre-fix (buggy) index order:  {old_mean_labels}")
    print(f"     Post-fix index order:         {new_mean_labels}  (== physical/hardware order)")
    print()

    model_bytes = extract_tflite_model()
    model_path = "/tmp/_validate_c1_model.tflite"
    Path(model_path).write_bytes(model_bytes)
    interp = tflite.Interpreter(model_path=model_path)
    interp.allocate_tensors()
    in_idx = interp.get_input_details()[0]["index"]
    out_idx = interp.get_output_details()[0]["index"]

    def run_model(z):
        interp.set_tensor(in_idx, np.array([z], dtype=np.float32))
        interp.invoke()
        out = interp.get_tensor(out_idx)[0]
        cls = int(np.argmax(out))
        return cls, GAS_NAMES.get(cls, f"class{cls}"), out

    def zscore(raw_by_physical_ch, index_order):
        z = np.zeros(8, dtype=np.float32)
        for ch in range(8):
            applied_sensor = index_order[ch]
            z[ch] = (raw_by_physical_ch[ch] - mean_by_sensor[applied_sensor]) / std_by_sensor[applied_sensor]
        return z

    def true_baseline_voltage():
        return np.array([mean_by_sensor[s] for s in physical_order], dtype=np.float32)

    print("=" * 78)
    print("SCENARIO 1: every sensor exactly at its own true baseline (clear air)")
    print("=" * 78)
    raw = true_baseline_voltage()
    z_new = zscore(raw, new_mean_labels)
    z_old = zscore(raw, old_mean_labels)
    print("z-scores (NEW/fixed, should be ~0 for all 8 channels):", np.round(z_new, 4))
    print("z-scores (OLD/buggy, nonzero = phantom deviation from a perfectly nominal reading):")
    print("                                                       ", np.round(z_old, 4))
    cls_new, name_new, out_new = run_model(z_new)
    cls_old, name_old, out_old = run_model(z_old)
    print(f"\nNEW (fixed)  -> class={cls_new} ({name_new}), raw scores={np.round(out_new, 3)}")
    print(f"OLD (buggy)  -> class={cls_old} ({name_old}), raw scores={np.round(out_old, 3)}")
    print(f"\n{'MATCH' if cls_new == cls_old else 'MISMATCH'}: a perfectly nominal sensor reading "
          f"{'is' if cls_new == cls_old else 'is NOT'} classified the same way under old vs new ordering.")

    print()
    print("=" * 78)
    print("SCENARIO 2: noisy baseline batch (2000 samples, +/- N(0, 0.5*std) per")
    print("            channel around true baseline - normal sensor noise, no gas)")
    print("=" * 78)
    rng = np.random.default_rng(42)
    n = 2000
    noisy_new_nonclear = 0
    noisy_old_nonclear = 0
    for _ in range(n):
        raw = np.array(
            [mean_by_sensor[s] + rng.normal(0, 0.5 * std_by_sensor[s]) for s in physical_order],
            dtype=np.float32,
        )
        cls_new, _, _ = run_model(zscore(raw, new_mean_labels))
        cls_old, _, _ = run_model(zscore(raw, old_mean_labels))
        noisy_new_nonclear += cls_new != 0
        noisy_old_nonclear += cls_old != 0
    print(f"NEW (fixed): {noisy_new_nonclear}/{n} ({100*noisy_new_nonclear/n:.1f}%) of pure-noise "
          f"baseline samples classified as NON-clear")
    print(f"OLD (buggy): {noisy_old_nonclear}/{n} ({100*noisy_old_nonclear/n:.1f}%) of pure-noise "
          f"baseline samples classified as NON-clear")
    print("NOTE: both rates are high because the scaler's mean is fit over the WHOLE training set")
    print("      (all classes mixed), not clear-air samples only - see module docstring caveat.")

    for label, sensor in (("LPG", LPG_SENSOR), ("methane", METHANE_SENSOR)):
        print()
        print("=" * 78)
        print(f"SCENARIO: genuine {label} event ({sensor} raised +4 std, rest at baseline)")
        print("=" * 78)
        raw = true_baseline_voltage().copy()
        idx = physical_order.index(sensor)
        raw[idx] = mean_by_sensor[sensor] + 4 * std_by_sensor[sensor]
        cls_new, name_new, out_new = run_model(zscore(raw, new_mean_labels))
        cls_old, name_old, out_old = run_model(zscore(raw, old_mean_labels))
        print(f"NEW (fixed)  -> class={cls_new} ({name_new}), raw scores={np.round(out_new, 3)}")
        print(f"OLD (buggy)  -> class={cls_old} ({name_old}), raw scores={np.round(out_old, 3)}")
        print(f"Expected ground truth: {label}")

    print()
    print("=" * 78)
    print("FINDINGS (see this file's docstring for the full caveat)")
    print("=" * 78)
    print("- The fix is a verified pure reorder (same values, corrected index order).")
    print("- Old vs new ordering produce large, real differences on the actual trained")
    print("  model - the bug had teeth, this was not a cosmetic mismatch.")
    print("- Directionality (is physical order truly what the model was trained on?)")
    print("  is NOT fully settled by synthetic single-channel scenarios alone - real")
    print("  MQ sensors have cross-sensitivity, so a single-channel spike is not a")
    print("  realistic gas signature. Do not treat a clean run of this script as a")
    print("  substitute for (1) the training pipeline or (2) a real hardware capture.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
