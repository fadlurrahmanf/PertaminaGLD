"""Independent CSV/prefix validation for the isolated Stage2 browser fixture."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

FEATURES = ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"]
SCALARS = ["device_id", "session_id", "seq", "timestamp_ms", "scan_end_ms", "mode", "label",
           "nulling_profile_id", "overrun_count"]
HEADERS = SCALARS + ["voltage_" + value for value in FEATURES] + ["gain_" + value for value in FEATURES] + [
    "status_" + value for value in FEATURES] + ["feature_order"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == HEADERS, "CSV header differs")
        return list(reader)


def verify(value, downloads=None):
    require(value.get("schema") == "gld-replay-e2e/2" and value.get("mode") == "pc-simulation", "simulation identity missing")
    require(value.get("acquisition_clock") == "virtual-controlled", "virtual clock not declared")
    endpoint = value["endpoint"]
    require(endpoint["host"] == "127.0.0.1", "fixture not loopback")
    require(endpoint["http_port"] != endpoint["ws_port"], "fixture ports overlap")
    require(all(1024 <= endpoint[key] <= 65535 and endpoint[key] not in {1880, 1884, 5173, 5174, 5273, 5373}
                for key in ("http_port", "ws_port")), "fixture touched a protected port")
    require(value["max_window_seen"] <= 8, "offered window exceeded eight")
    require(not value.get("errors"), "unexpected synthetic wire error recorded")
    sessions = [session for session in value["sessions"] if session["original_samples"]]
    require(len(sessions) == 2, "need one completed replay and one terminal capacity scenario")
    reports = []
    for session in sessions:
        sid = session["session_id"]
        data = rows(session["csv_path"])
        originals = session["original_samples"]
        state = session["final_snapshot"]
        require(state["session_id"] == sid and state["count"] == len(data) == len(originals), "CSV/count/original identity differs")
        require([int(row["seq"]) for row in data] == list(range(len(data))), "CSV sequence gap/duplicate")
        for row, original in zip(data, originals):
            require(original["session_id"] == sid and original["feature_order"] == FEATURES, "original schema/identity differs")
            for key in SCALARS:
                require(row[key] == str(original[key]), "CSV scalar changed: " + key)
            require(row["feature_order"] == "|".join(FEATURES), "CSV feature order differs")
            for index, feature in enumerate(FEATURES):
                require(float(row["voltage_" + feature]) == original["sensor_voltage"][index], "voltage changed")
                require(int(row["gain_" + feature]) == original["sensor_gain"][index], "gain changed")
                require(int(row["status_" + feature]) == original["sensor_status"][index], "status changed")
        require(state["gap_count"] == 0, "collector reported a gap")
        starts = [command for command in session["commands"] if command["cmd"] == "START_DATASET"]
        resumes = [command for command in session["commands"] if command["cmd"] == "RESUME_DATASET"]
        stops = [command for command in session["commands"] if command["cmd"] == "STOP_DATASET"]
        require(len(starts) == 1 and resumes, "fresh Start retried or no Resume proof")
        require(all(command["session_id"] == sid and command["boot_id"] == session["boot_id"]
                    and command["label"] == session["label"] for command in resumes), "Resume identity changed")
        durable = acknowledgements = 0
        for event in value["audit"]:
            if event["session_id"] != sid:
                continue
            if event["kind"] == "fsync":
                durable = max(durable, event["next_seq"])
            elif event["kind"] == "ack":
                require(event["next_seq"] <= durable, "ACK preceded actual flush/fsync")
                acknowledgements += 1
        require(acknowledgements >= len(data), "not every persisted sample has wire ACK evidence")
        summaries = [message for message in session["emitted_messages"] if message["type"] == "summary"]
        require(summaries and all(message["total_samples"] == len(data) for message in summaries), "summary total differs")
        require(all(message["session_id"] == sid and message["incomplete"] is (not state["complete"])
                    for message in summaries), "summary identity/completion flag differs")
        if state["complete"]:
            require(any(message.get("type") == "ack" and message.get("cmd") == "STOP_DATASET"
                        and message.get("command_id") == stops[0]["command_id"]
                        and message.get("session_id") == sid and message.get("result") == "ok"
                        for message in session["emitted_messages"]) if stops else False,
                    "clean completion lacks correlated Stop ACK")
        if state["complete"]:
            require(len(data) > 600 and state["replayed_count"] >= 600, "large replay not demonstrated")
            require(stops and len({command["command_id"] for command in stops}) == 1, "Stop intent identity changed/missing")
            require(any(point["retained_count"] > 600 and point["snapshot"]["recovery_active"]
                        for point in session["checkpoints"]), "no >600 offline retained checkpoint")
            scenario = "recover_over_600_same_csv"
        else:
            require(state["state"] == "incomplete" and state["terminal_reason"] == "buffer_full"
                    and len(data) >= 640, "negative capacity session not reconciled incomplete")
            require(any(point["retained_count"] == 640 for point in session["checkpoints"]),
                    "no full640 retained checkpoint before terminal drain")
            scenario = "capacity_pressure_no_overwrite"
        require(all(point["snapshot"].get("path") in {None, "", session["csv_path"]}
                    for point in session["checkpoints"]), "session CSV path changed across recovery")
        download = None
        if downloads is not None:
            require(sid in downloads, "missing actual browser download mapping")
            require(rows(downloads[sid]) == data, "browser download differs from backend")
            download = str(Path(downloads[sid]).resolve())
        reports.append(dict(scenario=scenario, status="PASS", session_id=sid,
            rows=len(data), replayed_count=state["replayed_count"], complete=state["complete"],
            gap_count=0, duplicate_count=state["duplicate_count"], resume_commands=len(resumes),
            all_fields_match_original=True, durable_ack_order=True, csv_path=session["csv_path"],
            csv_sha256=hashlib.sha256(Path(session["csv_path"]).read_bytes()).hexdigest(),
            browser_download=download))
    require({report["scenario"] for report in reports} == {"recover_over_600_same_csv", "capacity_pressure_no_overwrite"},
            "positive/negative scenario coverage differs")
    return dict(status="PASS", scope="synthetic protocol2 wire/UI/CSV only; not firmware or RF proof", sessions=reports)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--downloads-json", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        value = json.loads(args.evidence.read_text(encoding="utf-8"))
        downloads = json.loads(args.downloads_json.read_text(encoding="utf-8")) if args.downloads_json else None
        result = verify(value, downloads)
    except (ValueError, KeyError, OSError, TypeError) as error:
        result = dict(status="FAIL", reason=str(error))
    text = json.dumps(result, indent=2)
    if args.report:
        args.report.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
