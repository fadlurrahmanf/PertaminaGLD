"""Independently verify PC-only Dataset simulation evidence; never open hardware.

CSV values are compared to the fake peer's emitted wire records, rather than
trusting UI counters. Device timestamp cadence and host arrival cadence remain
separate measurements. This does not prove firmware or RF behavior.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any

FEATURES = ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"]
SCALARS = ["device_id", "session_id", "seq", "timestamp_ms", "scan_end_ms", "mode",
           "label", "nulling_profile_id", "overrun_count"]
HEADERS = SCALARS + [f"voltage_{name}" for name in FEATURES] + [
    f"gain_{name}" for name in FEATURES] + [f"status_{name}" for name in FEATURES] + ["feature_order"]
PROTECTED_PORTS = {81, 1880, 1884, 5173, 5174, 5273, 5373}


class EvidenceError(ValueError):
    pass


def require(condition: Any, explanation: str) -> None:
    if not condition:
        raise EvidenceError(explanation)


def cadence(values: list[float]) -> dict[str, Any]:
    intervals = [right - left for left, right in zip(values, values[1:])]
    if not intervals:
        return {"interval_count": 0}
    return {"interval_count": len(intervals), "min": min(intervals),
            "median": statistics.median(intervals), "max": max(intervals)}


def verify_session(session: dict[str, Any], directory: Path, require_downloads: bool = False) -> dict[str, Any]:
    name, session_id, device_id = session["name"], session["session_id"], session["device_id"]
    require(name in {"clean", "drop"}, f"Unsupported scenario: {name}")
    emitted = session["emitted_samples"]
    require(len(emitted) >= 4, f"{name}: at least four emitted samples required")
    by_sequence = {}
    for sample in emitted:
        require(sample["session_id"] == session_id and sample["device_id"] == device_id,
                f"{name}: fake-peer sample identity differs")
        seq = sample["seq"]
        require(type(seq) is int and seq >= 0 and seq not in by_sequence,
                f"{name}: invalid/duplicate fake-peer sequence")
        require(sample["feature_order"] == FEATURES, f"{name}: fake feature order differs")
        require(sample["mode"] == "DATASET", f"{name}: unexpected fake mode")
        require(sample["label"] == session["label"], f"{name}: fake label differs")
        for key in ("sensor_voltage", "sensor_gain", "sensor_status"):
            require(len(sample[key]) == 8, f"{name}: fake {key} does not have eight channels")
        require(all(type(v) in (int, float) and math.isfinite(v)
                    for v in sample["sensor_voltage"]), f"{name}: invalid fake voltage")
        require(sample["scan_end_ms"] >= sample["timestamp_ms"], f"{name}: scan ends before start")
        by_sequence[seq] = sample
    ordered = sorted(emitted, key=lambda sample: sample["seq"])
    require([sample["seq"] for sample in ordered] == list(range(len(emitted))),
            f"{name}: fake emissions must begin at zero and be contiguous")
    device_cadence = cadence([sample["timestamp_ms"] for sample in ordered])
    require(device_cadence.get("min") == device_cadence.get("max") == 500,
            f"{name}: fake device timestamp interval is not exactly 500 ms")
    csv_path = Path(session["csv_path"])
    if not csv_path.is_absolute():
        csv_path = directory / csv_path
    csv_path = csv_path.resolve()
    require(csv_path.is_relative_to(directory.resolve()), f"{name}: CSV is outside simulation artifact directory")
    require(csv_path.is_file(), f"{name}: CSV not retained")
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == HEADERS, f"{name}: CSV columns/schema differ")
        rows = list(reader)
    require(len(rows) >= 4, f"{name}: at least four persisted samples required")
    seen = []
    for row in rows:
        seq = int(row["seq"])
        require(seq in by_sequence, f"{name}: CSV sequence {seq} was never emitted")
        sample = by_sequence[seq]
        for key in SCALARS:
            require(row[key] == str(sample[key]), f"{name}: row {seq} scalar {key} differs")
        require(row["feature_order"] == "|".join(FEATURES), f"{name}: CSV feature order differs")
        for index, sensor in enumerate(FEATURES):
            require(float(row[f"voltage_{sensor}"]) == sample["sensor_voltage"][index],
                    f"{name}: row {seq} {sensor} voltage differs")
            require(int(row[f"gain_{sensor}"]) == sample["sensor_gain"][index],
                    f"{name}: row {seq} {sensor} gain differs")
            require(int(row[f"status_{sensor}"]) == sample["sensor_status"][index],
                    f"{name}: row {seq} {sensor} status differs")
        seen.append(seq)
    require(seen == sorted(set(seen)), f"{name}: CSV contains duplicates or reordering")
    snapshot = session["final_snapshot"]
    require(snapshot["session_id"] == session_id, f"{name}: final snapshot session differs")
    require(snapshot["count"] == len(rows), f"{name}: final count differs from CSV")
    require(snapshot["duplicate_count"] == 0, f"{name}: unexpected duplicate count")
    expected_gaps = seen[-1] + 1 - len(seen)
    commands = session["commands"]
    require(commands and commands[0]["cmd"] == "START_DATASET", f"{name}: missing Start command")
    require(commands[0]["session_id"] == session_id and commands[0]["sample_interval_ms"] == 500,
            f"{name}: Start session or interval differs")
    require(commands[0]["command_id"], f"{name}: Start command correlation absent")
    messages = session["emitted_messages"]
    require(messages, f"{name}: no outgoing protocol evidence")
    for command in commands:
        matching = [message for message in messages if message.get("type") == "ack"
                    and message.get("command_id") == command["command_id"]
                    and message.get("cmd") == command["cmd"]
                    and message.get("session_id") == session_id]
        require(len(matching) == 1 and matching[0].get("result") == "ok",
                f"{name}: missing/duplicate/rejected correlated command ACK")
    start_ack = next(index for index, message in enumerate(messages)
                     if message.get("type") == "ack"
                     and message.get("command_id") == commands[0]["command_id"])
    running = next((index for index, message in enumerate(messages)
                    if message.get("type") == "status" and message.get("state") == "running"
                    and message.get("session_id") == session_id), -1)
    first_sample = next((index for index, message in enumerate(messages)
                         if message.get("type") == "sample"), -1)
    require(0 <= start_ack < running < first_sample,
            f"{name}: Start ACK/running status did not precede first sample")
    if name == "clean":
        require([cmd["cmd"] for cmd in commands] == ["START_DATASET", "STOP_DATASET"],
                "clean: unexpected command retry or missing Stop")
        require(commands[1]["session_id"] == session_id and commands[1]["command_id"]
                and commands[1]["command_id"] != commands[0]["command_id"],
                "clean: Stop command identity/correlation invalid")
        summary = session["summary"]
        require(summary and summary["session_id"] == session_id, "clean: missing matching summary")
        require(summary["total_samples"] == len(rows) == len(emitted), "clean: total/emitted/CSV differ")
        require(not summary.get("incomplete", False), "clean: device summary incomplete")
        require(snapshot["complete"] is True and snapshot["total_samples"] == len(rows),
                "clean: final completion not reconciled")
        stop_ack = next(index for index, message in enumerate(messages)
                        if message.get("type") == "ack"
                        and message.get("command_id") == commands[1]["command_id"])
        summaries = [(index, message) for index, message in enumerate(messages)
                     if message.get("type") == "summary"]
        require(len(summaries) == 1 and summaries[0][0] > stop_ack
                and summaries[0][1] == summary, "clean: Stop ACK/summary evidence differs")
        checkpoints = {point["name"]: point for point in session.get("checkpoints", [])}
        require("before_browser_close" in checkpoints and "after_browser_reopen" in checkpoints,
                "clean: missing browser-close/reopen recording observations")
        before, after = checkpoints["before_browser_close"], checkpoints["after_browser_reopen"]
        require(after["host_monotonic_s"] - before["host_monotonic_s"] >= 1.0,
                "clean: browser recording continuity observation is too short")
        require(after["snapshot"]["count"] > before["snapshot"]["count"],
                "clean: no recorded samples during browser-close/reopen window")
        for point in (before, after):
            require(point["snapshot"]["session_id"] == session_id
                    and point["snapshot"]["state"] == "recording"
                    and point["snapshot"]["connected"] is True,
                    "clean: session did not stay recording across browser-close/reopen")
        if "while_browser_closed" in checkpoints:
            middle = checkpoints["while_browser_closed"]
            require(before["host_monotonic_s"] < middle["host_monotonic_s"] < after["host_monotonic_s"]
                    and before["snapshot"]["count"] < middle["snapshot"]["count"] < after["snapshot"]["count"]
                    and middle["snapshot"]["session_id"] == session_id
                    and middle["snapshot"]["state"] == "recording"
                    and middle["snapshot"]["connected"] is True,
                    "clean: recording continuity during closed-browser window differs")
    else:
        require([cmd["cmd"] for cmd in commands] == ["START_DATASET"],
                "drop: unexpected Stop or automatic command retry")
        require(snapshot["complete"] is False and snapshot["state"] == "incomplete"
                and snapshot["connected"] is False, "drop: transport loss not marked incomplete")
        checkpoints = {point["name"]: point for point in session.get("checkpoints", [])}
        require("after_drop" in checkpoints and "after_drop_wait" in checkpoints,
                "drop: missing two post-disconnect observations")
        first, second = checkpoints["after_drop"], checkpoints["after_drop_wait"]
        require(second["host_monotonic_s"] - first["host_monotonic_s"] >= 1.0,
                "drop: post-disconnect observation shorter than two nominal intervals")
        for point in (first, second):
            require(point["snapshot"]["count"] == len(rows)
                    and point["snapshot"]["complete"] is False
                    and point["snapshot"]["connected"] is False
                    and point["snapshot"]["session_id"] == session_id,
                    "drop: recording changed or stayed connected after loss")
    require(snapshot["gap_count"] == expected_gaps, f"{name}: sequence gap counter differs")
    arrivals = session.get("arrival_monotonic_s", [])
    if arrivals:
        require(len(arrivals) == len(emitted), f"{name}: host arrival evidence length differs")
        require(all(right >= left for left, right in zip(arrivals, arrivals[1:])),
                f"{name}: host arrival clock moved backward")
    emissions = session.get("emission_monotonic_s", [])
    if emissions:
        require(len(emissions) == len(emitted), f"{name}: host emission evidence length differs")
        require(all(right >= left for left, right in zip(emissions, emissions[1:])),
                f"{name}: host emission clock moved backward")
    downloaded = directory / "downloads" / f"{name}.csv"
    download_result = {"verified": False}
    if downloaded.exists() or require_downloads:
        require(downloaded.is_file(), f"{name}: actual browser-downloaded CSV missing")
        with downloaded.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            require(reader.fieldnames == HEADERS, f"{name}: downloaded CSV columns differ")
            downloaded_rows = list(reader)
        require(downloaded_rows == rows, f"{name}: browser download differs from backend CSV")
        download_result = {"verified": True, "rows": len(downloaded_rows),
                           "path": str(downloaded.resolve()),
                           "sha256": hashlib.sha256(downloaded.read_bytes()).hexdigest()}
    return {"scenario": name, "status": "PASS", "session_id": session_id,
            "emitted": len(emitted), "persisted": len(rows), "gap_count": expected_gaps,
            "duplicate_count": 0, "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
            "csv_path": str(csv_path), "device_timestamp_interval_ms": device_cadence,
            "host_emission_interval_s": cadence(emissions),
            "host_arrival_interval_s": cadence(arrivals), "browser_download": download_result,
            "checkpoint_counts": {point["name"]: point["snapshot"]["count"]
                                  for point in session.get("checkpoints", [])}}


def verify(evidence: dict[str, Any], directory: Path, require_downloads: bool = False) -> dict[str, Any]:
    require(evidence.get("schema") == "gld-dataset-e2e/1", "Unsupported evidence schema")
    require(evidence.get("mode") == "pc-simulation", "Evidence is not explicitly PC simulation")
    endpoint = evidence["endpoint"]
    require(endpoint["host"] == "127.0.0.1", "Simulation must bind explicit IPv4 loopback")
    for key in ("http_port", "ws_port"):
        require(type(endpoint[key]) is int and 1024 <= endpoint[key] <= 65535
                and endpoint[key] not in PROTECTED_PORTS, f"Unsafe simulation port: {key}")
    require(endpoint["http_port"] != endpoint["ws_port"], "Simulation ports overlap")
    sessions = evidence["sessions"]
    require({session["name"] for session in sessions} == {"clean", "drop"} and len(sessions) == 2,
            "Expected exactly one clean session and one forced-drop session")
    require(len({session["session_id"] for session in sessions}) == 2, "Scenario session IDs reused")
    results = [verify_session(session, directory, require_downloads) for session in sessions]
    return {"status": "PASS", "scope": "PC simulation only; no RF/firmware/hardware proof",
            "sessions": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--require-downloads", action="store_true")
    args = parser.parse_args()
    try:
        result = verify(json.loads(args.evidence.read_text(encoding="utf-8")), args.evidence.parent,
                        args.require_downloads)
    except (EvidenceError, KeyError, TypeError, ValueError, OSError) as error:
        result = {"status": "FAIL", "reason": str(error)}
    output = json.dumps(result, indent=2, allow_nan=False)
    if args.report:
        args.report.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
