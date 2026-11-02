"""Extract unmodified snapshots from completed REAL GLD evidence for PDF views."""
import copy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / "firmware/.pio/gld-real-test-20261102/stage2/output/20261102T093208Z-1334ef/real-evidence.json"
DESTINATION = HERE / "archive-scenes.json"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def extract():
    raw = SOURCE.read_bytes()
    evidence = json.loads(raw)
    if evidence.get("mode") != "real-device":
        raise ValueError("Refuse non-real-device evidence")
    session = evidence["sessions"][0]
    ready = evidence["provenance"]["connect_response"]
    if ready.get("state") != "ready" or ready.get("connected") is not True:
        raise ValueError("Actual ready snapshot missing")
    recording = [(index, point) for index, point in enumerate(session["snapshots"])
                 if point.get("name") == "initial_capture" and point["snapshot"].get("state") == "recording"
                 and point["snapshot"].get("count", 0) >= 6]
    if not recording:
        raise ValueError("Actual initial recording snapshot missing")
    recording_index, recording_point = min(recording, key=lambda item: abs(item[1]["snapshot"]["count"] - 13))
    replaying = [(index, point) for index, point in enumerate(session["snapshots"])
                 if point.get("name") == "auto_resume" and point["snapshot"].get("state") == "replaying"]
    if not replaying:
        raise ValueError("Actual replaying snapshot missing; never synthesize it")
    replaying.sort(key=lambda item: item[1]["snapshot"].get("count", 0))
    replay_index, replay_point = replaying[len(replaying) // 2]
    selections = {
        "ready": ("provenance.connect_response", ready, None),
        "recording": (f"sessions[0].snapshots[{recording_index}].snapshot", recording_point["snapshot"], recording_point),
        "replaying": (f"sessions[0].snapshots[{replay_index}].snapshot", replay_point["snapshot"], replay_point),
    }
    result = dict(kind="recorded_actual_archive", live_connection=False, source_path=str(SOURCE),
                  source_sha256=hashlib.sha256(raw).hexdigest(), scenes={})
    for name, (selector, snapshot, point) in selections.items():
        if snapshot.get("device_id") != "1002" or snapshot.get("nulling_profile_id") != 1:
            raise ValueError("Unexpected real device/profile")
        result["scenes"][name] = dict(source_selector=selector,
            snapshot_sha256=hashlib.sha256(canonical(snapshot)).hexdigest(), snapshot=copy.deepcopy(snapshot),
            recorded_utc=point.get("utc") if point else None,
            recorded_host_monotonic_s=point.get("host_monotonic_s") if point else None)
    DESTINATION.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    result = extract()
    print(json.dumps(dict(source_sha256=result["source_sha256"], scenes={name: {
        "source_selector": value["source_selector"], "snapshot_sha256": value["snapshot_sha256"],
        "state": value["snapshot"]["state"], "count": value["snapshot"]["count"]}
        for name, value in result["scenes"].items()}), indent=2))
