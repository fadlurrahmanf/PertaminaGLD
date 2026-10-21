"""Capture future GLD1 nulling events from the already-connected local bridge."""
import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = "http://127.0.0.1:5174"
DEST = Path(__file__).with_name("gld1-nulling-experiment-com7-20261019.jsonl")


def request(path, headers=None):
    req = urllib.request.Request(BASE + path, headers=headers or {})
    with urllib.request.urlopen(req, timeout=6) as response:
        return json.load(response)


def main():
    headers = {"X-GLD-Bridge-Token": request("/api/health")["csrfToken"]}
    sequence = int(request("/api/serial/recent?slot=1&after=0", headers)["sequence"])
    with DEST.open("x", encoding="utf-8") as output:
        print(f"CAPTURE_READY sequence={sequence} path={DEST}", flush=True)
        deadline = time.monotonic() + 1500
        while time.monotonic() < deadline:
            batch = request(f"/api/serial/recent?slot=1&after={sequence}", headers)
            observed = datetime.now().astimezone().isoformat(timespec="milliseconds")
            done = False
            for item in batch.get("lines", []):
                line = item.get("line", "")
                if not line.startswith(("NULLING_", "GLD_CMD_ACK_JSON", "GLD_ALARM_LATCH_OPERATOR_CLEAR")):
                    continue
                output.write(json.dumps({"sequence": item["sequence"], "observed_at": observed,
                                         "timestamp_basis": "pc-poll-time", "line": line}, ensure_ascii=False) + "\n")
                if line.startswith(("NULLING_RUNTIME_RESULT=PASS", "NULLING_RUNTIME_RESULT=PARTIAL_RETRY",
                                    "NULLING_RUNTIME_RESULT=FAIL_RETRY", "NULLING_SERVICE_BLOCKED")):
                    done = True
            output.flush()
            sequence = int(batch.get("sequence") or sequence)
            if done:
                print(f"CAPTURE_COMPLETE path={DEST}", flush=True)
                return
            time.sleep(0.25)
    raise SystemExit("CAPTURE_TIMEOUT; reconcile device status before issuing any commands")


if __name__ == "__main__":
    main()
