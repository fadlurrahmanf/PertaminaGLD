import datetime as dt
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
folder = Path(__file__).resolve().parent
receipt = json.loads((folder / "model1-build-attempt2.json").read_text(encoding="utf-8-sig"))
for key in ("startUtc", "endUtc"):
    receipt[key] = dt.datetime.fromisoformat(receipt[key]).astimezone(dt.timezone.utc).isoformat()
for item in receipt["artifacts"]:
    artifact, build = Path(item["path"]), Path(item["buildPath"])
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == item["sha256"]
    assert hashlib.sha256(build.read_bytes()).hexdigest() == item["sha256"]
    assert artifact.stat().st_size == item["sizeBytes"]
assert receipt["sourceUnchanged"] and all(item["matches"] for item in receipt["frozenSourceChecks"])
receipt["artifactHashesVerified"] = True
for name in ("model1-build-attempt2.json", "model1-build-receipt.json"):
    (folder / name).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: receipt[key] for key in ("status", "startUtc", "endUtc", "startWib", "endWib", "firmwareSha256", "artifactHashesVerified")}))
