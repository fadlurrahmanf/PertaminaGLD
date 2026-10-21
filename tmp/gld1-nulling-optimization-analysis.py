"""Counterfactual screen of one GLD1 recording; not a hardware simulation.

This intentionally reuses recorded observations; a shorter scan would change
the time/order of measurements, so equality here cannot validate calibration.
"""
import json
import re
from pathlib import Path


PATH = Path(__file__).with_name("gld1-nulling-com7-20261019.jsonl")
KV = re.compile(r"(\w+)=([^\s]+)")


def fields(line):
    return dict(KV.findall(line))


def main():
    channels = {}
    skipped_exponential = []
    for record in PATH.read_text(encoding="utf-8").splitlines():
        line = json.loads(record)["line"]
        f = fields(line)
        if line.startswith("NULLING_STABILITY stage=exp ") and int(f["code"]) in (1, 3, 7, 15, 31):
            skipped_exponential.append((int(f["ch"]), int(f["code"]), int(f["observeMs"])))
        if "ch" not in f:
            continue
        ch = int(f["ch"])
        if line.startswith("NULLING_CONFIRM_START "):
            channels[ch] = {"sensor": f["sensor"], "selected": int(f["selected"]),
                            "steps": [], "candidates": [], "verify": [], "final": None}
        elif ch not in channels:
            continue
        elif line.startswith("NULLING_STABILITY stage=confirm "):
            channels[ch]["steps"].append({"code": int(f["code"]),
                                          "observe_ms": int(f["observeMs"])})
        elif line.startswith("NULLING_CONFIRM_STEP "):
            if all(f.get(k) == "1" for k in
                   ("valid", "aboveMin", "zeroMargin", "outBaseline", "write")):
                channels[ch]["candidates"].append({"code": int(f["code"]),
                                                  "voltage": float(f["voltage"])})
        elif line.startswith("NULLING_CONFIRM_VERIFY "):
            channels[ch]["verify"].append({"code": int(f["code"]),
                                          "pass": all(f.get(k) == "1" for k in
                                                      ("valid", "aboveMin", "zeroMargin", "outBaseline"))})
        elif line.startswith("NULLING_CH_OK "):
            channels[ch]["final"] = int(f["dac"])

    assert len(channels) == 8
    assert sum(len(c["steps"]) for c in channels.values()) == 398
    assert len(skipped_exponential) == 40
    assert {ch for ch, _, _ in skipped_exponential} == set(range(8))
    for c in channels.values():
        ranked = sorted((v for v in c["candidates"] if v["voltage"] >= 0),
                        key=lambda v: v["voltage"])
        assert [x["code"] for x in ranked[:len(c["verify"])]] == [x["code"] for x in c["verify"]], c["sensor"]
        assert sum(v["pass"] for v in c["verify"]) == 1, c["sensor"]
    print("One-run counterfactual, NOT new samples, NOT accuracy proof")
    print(f"Early exponential points: {len(skipped_exponential)}; "
          f"recorded observeMs = {sum(ms for _, _, ms in skipped_exponential) / 1000:.3f}s; "
          "not a wall-clock prediction or safety proof")
    for width in (5, 10, 15, 20):
        dropped_ms = 0
        kept_accept = []
        missing = []
        for c in channels.values():
            accepted = next((v["code"] for v in c["verify"] if v["pass"]), None)
            included = accepted is not None and abs(accepted - c["selected"]) <= width
            (kept_accept if included else missing).append(c["sensor"])
            dropped_ms += sum(s["observe_ms"] for s in c["steps"]
                              if abs(s["code"] - c["selected"]) > width)
        print(f"+-{width}: recorded successful candidate retained {len(kept_accept)}/8; "
              f"excluded={','.join(missing) or 'none'}; "
              f"removed recorded observeMs={dropped_ms / 1000:.3f}s "
              f"(upper-bound arithmetic, not a predicted runtime)")
    for c in channels.values():
        accepted = next((v["code"] for v in c["verify"] if v["pass"]), None)
        print(f"{c['sensor']:5} binary={c['selected']:4} verified={accepted!s:4} "
              f"offset={accepted - c['selected']:+d} final={c['final']:4} "
              f"confirm_points={len(c['steps'])}")


if __name__ == "__main__":
    main()
