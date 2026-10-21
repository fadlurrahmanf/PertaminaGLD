"""Capture only GLD nulling lines from the existing local Operator Hub bridge."""
import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = "http://127.0.0.1:5174"
DEST = Path(__file__).with_name("gld1-nulling-com7-20261019.jsonl")


def request(path, headers=None):
    req = urllib.request.Request(BASE + path, headers=headers or {})
    with urllib.request.urlopen(req, timeout=6) as response:
        return json.load(response)


def main():
    token = request("/api/health")["csrfToken"]
    headers = {"X-GLD-Bridge-Token": token}
    sequence = 0
    first = True
    with DEST.open("x", encoding="utf-8") as output:
        while True:
            batch = request(f"/api/serial/recent?slot=1&after={sequence}", headers)
            observed = datetime.now().astimezone().isoformat(timespec="milliseconds")
            done = False
            for item in batch.get("lines", []):
                line = item.get("line", "")
                if not line.startswith("NULLING_"):
                    continue
                output.write(json.dumps({
                    "sequence": item["sequence"],
                    "observed_at": None if first else observed,
                    "timestamp_basis": "historical-not-recorded" if first else "pc-poll-time",
                    "line": line,
                }, ensure_ascii=False) + "\n")
                if line.startswith(("NULLING_RUNTIME_RESULT=PASS", "NULLING_RUNTIME_RESULT=PARTIAL_RETRY", "NULLING_RUNTIME_RESULT=FAIL_RETRY", "NULLING_SERVICE_BLOCKED")):
                    done = True
            output.flush()
            sequence = int(batch.get("sequence") or sequence)
            first = False
            if done:
                break
            time.sleep(0.25)
    print(f"CAPTURE_COMPLETE path={DEST}", flush=True)


if __name__ == "__main__":
    main()
