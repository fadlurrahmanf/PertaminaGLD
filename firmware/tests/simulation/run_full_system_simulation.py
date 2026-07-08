#!/usr/bin/env python3
"""End-to-end system simulation orchestrator for Pertamina GLD.

Ties together every leg built in firmware/tests/simulation/, all running the
REAL, unmodified production code where it is possible to execute off-target:

  1. (optional) firmware/tools/validate_c1_scaler_order.py's model - runs
     the REAL trained TFLite model on synthetic sensor voltages to produce a
     genuine gas classification, instead of a hardcoded one.
  2. host_protocol_sim (C++, compiled here) - the REAL AES-GCM encryption,
     AES-CMAC signing/verification, AppFrame encode/decode, and CH-side
     NodeCache/AlarmQueue/TxQueue/ClusterResponse logic (mbedtls-backed),
     simulating GLD1 (alarm) + GLD2 (normal) -> CH-B (depth 2) -> CH-A
     (depth 1) -> Gateway, including the H1 hop-by-hop alarm-ACK fix.
  3. run_decode_js.js - the REAL, unmodified
     server/nodered/functions/pertamina-gld-decode.js, executed via Node's
     vm module with a minimal Node-RED function-node shim, decrypting and
     decoding the wire frames scenario 2 produced.
  4. run_server_cmac.js - the REAL AES-CMAC implementation extracted from
     server/nodered/apply-pertamina-gld-flow.js's build_node_command_auth,
     cross-checked against the C++ mbedtls-backed computeAesCmac128 for the
     authenticated downlink command.

See README.md in this directory for exactly what this does and does not
prove about the real system.

Usage: python3 firmware/tests/simulation/run_full_system_simulation.py
Run from anywhere; paths are resolved relative to this file.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parent
REPO_ROOT = SIM_DIR.parents[2]
BUILD_DIR = SIM_DIR / "build"
BINARY = BUILD_DIR / "host_protocol_sim"

SOURCES = [
    "firmware/shared/src/AppFrame.cpp",
    "firmware/shared/src/FirmwareConfig.cpp",
    "firmware/shared/src/GldCrypto.cpp",
    "firmware/shared/src/GldPayload.cpp",
    "firmware/shared/src/GldRecord.cpp",
    "firmware/gld/src/GldFrameBuilder.cpp",
    "firmware/ch/src/AlarmQueue.cpp",
    "firmware/ch/src/ChPullRequest.cpp",
    "firmware/ch/src/ChRuntime.cpp",
    "firmware/ch/src/ChTxQueue.cpp",
    "firmware/ch/src/ChUplink.cpp",
    "firmware/ch/src/ClusterResponse.cpp",
    "firmware/ch/src/NodeCache.cpp",
]

INCLUDES = [
    "firmware/shared/include",
    "firmware/ch/include",
    "firmware/gld/include",
    "firmware/config",
]

GLD1_DEFAULT = (1, 90, 3650)  # GLD_GAS_LPG, 90%, 3650mV


class SimError(RuntimeError):
    pass


def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kwargs)


def build_harness() -> None:
    if not shutil.which("g++"):
        raise SimError("g++ not found - cannot build the host protocol simulation harness")
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        "g++", "-std=c++17", "-O1", "-DESP_PLATFORM=1",
        *[f"-I{REPO_ROOT / inc}" for inc in INCLUDES],
        str(SIM_DIR / "host_protocol_sim.cpp"),
        *[str(REPO_ROOT / src) for src in SOURCES],
        "-lmbedtls", "-lmbedcrypto", "-lmbedx509",
        "-o", str(BINARY),
    ]
    result = run(cmd)
    if result.returncode != 0:
        raise SimError(f"failed to compile host_protocol_sim:\n{result.stdout}\n{result.stderr}")
    print(f"[build] compiled {BINARY} against the real firmware source + mbedtls")


def get_ml_classification():
    """Best-effort: run the real TFLite model for a genuine classification.
    Returns (gasClass, confidence, batteryMv) or None if unavailable."""
    try:
        return _get_ml_classification_impl()
    except Exception as exc:  # noqa: BLE001 - deliberately broad: this leg is optional
        print(f"[ml] tflite_runtime unavailable or incompatible in this Python ({exc.__class__.__name__}: {exc})")
        print("[ml] using a fixed GLD1 input instead. To exercise this leg, use a virtualenv with:")
        print('[ml]   pip install tflite-runtime "numpy<2"')
        print("[ml] (tflite-runtime's prebuilt wheels are commonly built against numpy 1.x; the system")
        print("[ml] Python's numpy>=2 install will raise \"_ARRAY_API not found\" - a numpy<2 venv avoids it.)")
        return None


def _get_ml_classification_impl():
    import numpy as np
    import tflite_runtime.interpreter as tflite

    physical_order_text = (REPO_ROOT / "firmware/gld/include/BoardPins.h").read_text(encoding="utf-8")
    match = re.search(r"SENSOR_NAMES\[SENSOR_COUNT\]\s*=\s*\{([^}]*)\}", physical_order_text)
    physical_order = re.findall(r'"(\w+)"', match.group(1))

    scaler_text = (REPO_ROOT / "firmware/gld/model/scaler_params.cpp").read_text(encoding="utf-8")

    def parse_scaler(array_name):
        block = re.search(array_name + r"\[8\]\s*=\s*\{(.*?)\}", scaler_text, re.S).group(1)
        pairs = re.findall(r"([\d.]+),\s*//\s*ch\d+\s+(\w+?)V", block)
        return [float(v) for v, _ in pairs], [lbl for _, lbl in pairs]

    means, mean_labels = parse_scaler("feature_means")
    stds, _ = parse_scaler("feature_stds")
    assert mean_labels == physical_order
    mean_by_sensor = dict(zip(mean_labels, means))
    std_by_sensor = dict(zip(mean_labels, stds))

    model_text = (REPO_ROOT / "firmware/gld/model/model_data.cpp").read_text(encoding="utf-8")
    hex_bytes = re.findall(r"0x[0-9a-fA-F]{2}", model_text)
    model_bytes = bytes(int(b, 16) for b in hex_bytes)
    model_path = BUILD_DIR / "_sim_model.tflite"
    model_path.write_bytes(model_bytes)

    interp = tflite.Interpreter(model_path=str(model_path))
    interp.allocate_tensors()
    in_idx = interp.get_input_details()[0]["index"]
    out_idx = interp.get_output_details()[0]["index"]

    # A genuine LPG-leak-like sensor signature: MQ5 (LPG-sensitive, per
    # GldThresholdClassifier.cpp) elevated well above its trained baseline,
    # everything else at baseline.
    raw = np.array([mean_by_sensor[s] for s in physical_order], dtype=np.float32)
    lpg_idx = physical_order.index("MQ5")
    raw[lpg_idx] = mean_by_sensor["MQ5"] + 4 * std_by_sensor["MQ5"]
    z = np.array(
        [(raw[i] - mean_by_sensor[physical_order[i]]) / std_by_sensor[physical_order[i]] for i in range(8)],
        dtype=np.float32,
    )
    interp.set_tensor(in_idx, np.array([z], dtype=np.float32))
    interp.invoke()
    out = interp.get_tensor(out_idx)[0]
    gas_class = int(np.argmax(out))
    confidence = int(round(float(out[gas_class]) * 100))
    print(f"[ml] real TFLite model classified the synthetic MQ5-elevated input as "
          f"class={gas_class} confidence={confidence}% (raw scores={np.round(out, 3).tolist()})")
    return gas_class, confidence, 3650


def run_harness(gld1_input):
    gas_class, confidence, battery_mv = gld1_input
    result = run([str(BINARY), str(gas_class), str(confidence), str(battery_mv)])
    print(result.stdout)
    if result.returncode != 0:
        raise SimError(f"host_protocol_sim reported failures (exit {result.returncode}); see output above")
    frames = dict(re.findall(r"^(\w+_hex)=([0-9A-Fa-f]+)$", result.stdout, re.MULTILINE))
    lines = result.stdout.splitlines()
    pass_count = sum(1 for line in lines if line.startswith("PASS "))
    fail_count = sum(1 for line in lines if line.startswith("FAIL "))
    return frames, pass_count, fail_count


def decode_frame_via_real_js(frame_hex: str):
    result = run(["node", str(SIM_DIR / "run_decode_js.js"), frame_hex])
    if result.returncode != 0:
        raise SimError(f"run_decode_js.js failed:\n{result.stdout}\n{result.stderr}")
    return json.loads(result.stdout)


def cross_check_cmac(frames: dict) -> bool:
    key_hex = frames.get("cmac_key_hex")
    mac_input_hex = frames.get("cmac_mac_input_hex")
    cpp_tag_hex = frames.get("cmac_full_tag_hex")
    if not (key_hex and mac_input_hex and cpp_tag_hex):
        print("[cmac] missing expected hex fields from harness output - skipping cross-check")
        return False
    result = run(["node", str(SIM_DIR / "run_server_cmac.js"), key_hex, mac_input_hex])
    if result.returncode != 0:
        raise SimError(f"run_server_cmac.js failed:\n{result.stdout}\n{result.stderr}")
    js_tag_hex = json.loads(result.stdout)["tagHex"]
    match = js_tag_hex == cpp_tag_hex
    print(f"[cmac] real C++ (mbedtls) tag = {cpp_tag_hex}")
    print(f"[cmac] real JS  (crypto)  tag = {js_tag_hex}")
    print(f"[cmac] {'MATCH' if match else 'MISMATCH'}: server-side JS signing and firmware-side C++ "
          f"verification are cryptographically compatible")
    return match


def main() -> int:
    print("=" * 78)
    print("PERTAMINA GLD - FULL SYSTEM SIMULATION (host-side, no physical hardware)")
    print("=" * 78)
    build_harness()

    ml_result = get_ml_classification()
    gld1_input = ml_result or GLD1_DEFAULT
    print(f"\n[harness] driving GLD1's scenario with gasClass={gld1_input[0]} "
          f"confidence={gld1_input[1]}% batteryMv={gld1_input[2]}"
          f"{' (from real TFLite model)' if ml_result else ' (fixed default - no ML runtime available)'}\n")

    frames, cpp_pass, cpp_fail = run_harness(gld1_input)

    overall_ok = cpp_fail == 0
    checks = [("host_protocol_sim (C++, real crypto/framing/CH logic)", cpp_fail == 0, f"{cpp_pass} passed, {cpp_fail} failed")]

    if "gateway_uplink_frame_hex" in frames:
        decoded = decode_frame_via_real_js(frames["gateway_uplink_frame_hex"])
        ok = decoded.get("ok") and decoded["event"]["gasClass"] == gld1_input[0] and \
            decoded["event"]["confidence"] == gld1_input[1] and decoded["event"]["batteryMv"] == gld1_input[2] and \
            decoded["event"]["decryptOk"]
        checks.append(("real pertamina-gld-decode.js decrypts GLD1's alarm and recovers the original values", ok,
                        json.dumps(decoded.get("event", decoded.get("error")))))
        overall_ok = overall_ok and ok

    if "gateway_cluster_response_frame_hex" in frames:
        decoded = decode_frame_via_real_js(frames["gateway_cluster_response_frame_hex"])
        ok = decoded.get("ok") and decoded["event"]["gasClass"] == 0 and decoded["event"]["nodeIdHex"] == "0xF002" and \
            decoded["event"]["decryptOk"]
        checks.append(("real pertamina-gld-decode.js decrypts GLD2's relayed cluster response", ok,
                        json.dumps(decoded.get("event", decoded.get("error")))))
        overall_ok = overall_ok and ok

    cmac_match = cross_check_cmac(frames)
    checks.append(("real C++ (mbedtls) AES-CMAC matches real JS AES-CMAC for the authenticated downlink", cmac_match, ""))
    overall_ok = overall_ok and cmac_match

    print("\n" + "=" * 78)
    print("FULL SYSTEM SIMULATION SUMMARY")
    print("=" * 78)
    for name, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        if detail:
            print(f"       {detail}")
    print()
    print("Overall:", "ALL LEGS PASSED" if overall_ok else "AT LEAST ONE LEG FAILED")
    print("See firmware/tests/simulation/README.md for exactly what this does")
    print("and does not prove about the real, physical system.")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
