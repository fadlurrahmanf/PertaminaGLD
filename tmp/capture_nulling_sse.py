"""Capture one complete Nulling trace from the local GLD bridge SSE stream."""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge", default="http://127.0.0.1:5174")
    parser.add_argument("--out", required=True)
    parser.add_argument("--timeout", type=float, default=420.0)
    args = parser.parse_args()

    bridge = args.bridge.rstrip("/")
    with urllib.request.urlopen(f"{bridge}/api/health", timeout=5) as response:
        health = json.loads(response.read().decode("utf-8"))
    token = str(health["csrfToken"])
    url = f"{bridge}/api/events?token={urllib.parse.quote(token)}"
    started = time.monotonic()
    current_event = ""
    lines: list[str] = []
    with urllib.request.urlopen(url, timeout=args.timeout + 15) as stream:
        while time.monotonic() - started < args.timeout:
            raw = stream.readline()
            if not raw:
                break
            text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if text.startswith("event: "):
                current_event = text[7:]
                continue
            if not text.startswith("data: "):
                continue
            if current_event != "serial_line":
                continue
            payload = json.loads(text[6:])
            line = str(payload.get("line", ""))
            if not line:
                continue
            lines.append(line)
            if line == "NULLING_RUNTIME_RESULT=PASS":
                break
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({"lines": lines}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"CAPTURED_LINES={len(lines)} output={destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
