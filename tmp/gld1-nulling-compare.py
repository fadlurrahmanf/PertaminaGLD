"""Analyze the recorded baseline and current GLD1 experiment; no device access."""
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
KV = re.compile(r"(\w+)=([^\s]+)")


def load(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def analyze(records):
    channels = defaultdict(dict)
    stages = defaultdict(lambda: {"count": 0, "observeMs": 0, "stable": 0})
    issues = Counter()
    observations = []
    service_start = service_done = None
    for record in records:
        line = record["line"]
        fields = dict(KV.findall(line))
        stamp = record.get("observed_at")
        if line.startswith("NULLING_SERVICE_START"):
            service_start = stamp
        elif line.startswith("NULLING_SERVICE_DONE"):
            service_done = stamp
        if "ch" in fields:
            ch = int(fields["ch"])
            if line.startswith("NULLING_CH_START"):
                channels[ch].update(sensor=fields["sensor"], start=stamp)
            elif line.startswith("NULLING_CH_OK"):
                channels[ch].update(end=stamp, result="OK", **{k: float(fields[k]) for k in ("dac", "baseline", "after", "delta", "threshold")})
            elif line.startswith("NULLING_CH_FAIL"):
                channels[ch].update(end=stamp, result="FAIL", failure=line)
            elif line.startswith("NULLING_STABILITY"):
                stage = stages[(ch, fields["sensor"], fields["stage"])]
                stage["count"] += 1
                stage["observeMs"] += int(fields["observeMs"])
                stage["stable"] += int(fields["stable"])
                observations.append({"sequence": record["sequence"], "stamp": stamp, "ch": ch + 1,
                                     "sensor": fields["sensor"], "stage": fields["stage"],
                                     "code": int(fields["code"]), "stable": int(fields["stable"]),
                                     "spreadV": float(fields["spread"]), "observeMs": int(fields["observeMs"])})
            elif line.startswith("NULLING_CONFIRM_VERIFY"):
                issues["confirm_verify_fail"] += int(not all(fields.get(k) == "1" for k in ("valid", "aboveMin", "zeroMargin", "outBaseline")))
            elif line.startswith("NULLING_CONFIRM_RESUME_EXP"):
                issues["confirm_resume"] += 1
            if "valid" in fields and fields["valid"] == "0":
                issues["invalid_read"] += 1
            if "write" in fields and fields["write"] == "0":
                issues["write_failed"] += 1
    for channel in channels.values():
        if channel.get("start") and channel.get("end"):
            channel["seconds"] = (datetime.fromisoformat(channel["end"]) - datetime.fromisoformat(channel["start"])).total_seconds()
    elapsed = None
    if service_start and service_done:
        elapsed = (datetime.fromisoformat(service_done) - datetime.fromisoformat(service_start)).total_seconds()
    return {"channels": dict(channels), "stages": [{"ch": k[0] + 1, "sensor": k[1], "stage": k[2], **v} for k, v in sorted(stages.items())],
            "observations": observations, "issues": dict(issues), "serviceStart": service_start,
            "serviceDone": service_done, "serviceSeconds": elapsed,
            "markers": [r["line"] for r in records if r["line"].startswith(("NULLING_SERVICE_DONE", "NULLING_NVS_SAVE", "NULLING_RUNTIME_RESULT"))]}


def main():
    baseline = analyze(load(ROOT / "gld1-nulling-com7-20261019.jsonl"))
    previous = json.loads((ROOT / "gld1-nulling-xlsx" / "analysis.json").read_text(encoding="utf-8"))
    baseline["serviceSeconds"] = previous["totalServiceSeconds"]
    for c in previous["channels"]:
        baseline["channels"][c["ch"] - 1]["seconds"] = c["seconds"]
    experiment = analyze(load(ROOT / "gld1-nulling-experiment-com7-20261019.jsonl"))
    data = {"baseline": baseline, "experiment": experiment,
            "method": "Service/channel timestamps are PC observation times; baseline source includes prior Operator Hub capture. ObserveMs totals exclude overhead. No independent accuracy reference."}
    if experiment["serviceDone"]:
        dest = ROOT / "gld1-nulling-comparison-20261019.json"
        dest.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"REPORT {dest}")
    for label, run in (("BASELINE", baseline), ("EXPERIMENT", experiment)):
        print(label, "service_seconds=", run["serviceSeconds"], "issues=", run["issues"], "markers=", run["markers"])
        totals = defaultdict(lambda: {"count": 0, "observeMs": 0, "stable": 0})
        for phase in run["stages"]:
            for key in ("count", "observeMs", "stable"):
                totals[phase["stage"]][key] += phase[key]
        for name, phase in sorted(totals.items()):
            print(f"  stage={name} observations={phase['count']} observe_s={phase['observeMs']/1000:.3f} unstable={phase['count']-phase['stable']}")
        for ch, item in sorted(run["channels"].items()):
            print(f"  CH{int(ch)+1} {item.get('sensor')} result={item.get('result', 'running')} seconds={item.get('seconds')} dac={item.get('dac')} after={item.get('after')}")


if __name__ == "__main__":
    main()
