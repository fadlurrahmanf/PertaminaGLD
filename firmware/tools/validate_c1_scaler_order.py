#!/usr/bin/env python3
"""Validate active GLD model-slot ADC normalization contracts.

The legacy C1 StandardScaler artifact was retired when GLD moved to the
dual-input min-max models under ``firmware/gld/models``.  This host-side check
guards the deployment invariant that each selectable model slot uses physical
board channel order and has a valid finite min/max range per ADC channel.

Usage: ``python firmware/tools/validate_c1_scaler_order.py``
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODEL_SLOTS = ("model_1", "model_2")


def extract_float_array(source: str, name: str) -> list[float]:
    match = re.search(name + r"\[CNN_GAS_N_ADC\]\s*=\s*\{(.*?)\}", source, re.S)
    assert match, f"missing {name}"
    values = [float(value) for value in re.findall(r"(-?(?:\d+\.\d*|\d*\.\d+|\d+)(?:[eE][-+]?\d+)?)f", match.group(1))]
    assert len(values) == 8, f"{name} must contain exactly 8 values"
    return values


def physical_order() -> list[str]:
    board_pins = (REPO_ROOT / "firmware/gld/include/BoardPins.h").read_text(encoding="utf-8")
    match = re.search(r"SENSOR_NAMES\[SENSOR_COUNT\]\s*=\s*\{([^}]*)\}", board_pins)
    assert match, "could not find SENSOR_NAMES in BoardPins.h"
    return re.findall(r'"(\w+)"', match.group(1))


def validate_slot(slot: str, expected_order: list[str]) -> None:
    path = REPO_ROOT / "firmware/gld/models" / slot / "cnn_gas_datasheet_normalize_params.h"
    source = path.read_text(encoding="utf-8")
    name_match = re.search(r"CNN_GAS_ADC_NAMES\[CNN_GAS_N_ADC\]\s*=\s*\{([^}]*)\}", source)
    assert name_match, f"{slot}: missing CNN_GAS_ADC_NAMES"
    actual_order = re.findall(r'"(\w+)"', name_match.group(1))
    assert actual_order == expected_order, (
        f"{slot}: ADC order {actual_order} differs from BoardPins order {expected_order}"
    )
    minimums = extract_float_array(source, "CNN_GAS_ADC_MIN")
    maximums = extract_float_array(source, "CNN_GAS_ADC_MAX")
    for index, (minimum, maximum) in enumerate(zip(minimums, maximums)):
        assert math.isfinite(minimum) and math.isfinite(maximum), f"{slot}: non-finite range at {expected_order[index]}"
        assert minimum < maximum, f"{slot}: invalid range at {expected_order[index]} ({minimum} >= {maximum})"
    print(f"[OK] {slot}: physical order and all 8 min-max ranges are valid")


def main() -> int:
    order = physical_order()
    assert order == ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"]
    for slot in MODEL_SLOTS:
        validate_slot(slot, order)
    return 0


if __name__ == "__main__":
    sys.exit(main())
