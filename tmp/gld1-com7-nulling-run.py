"""One user-authorized GLD1 COM7 nulling capture; preserves NVS outside normal profile save."""
from __future__ import annotations

import sys
import time

import serial


PORT = "COM7"
BAUD = 115200


def read_for(port: serial.Serial, seconds: float) -> list[str]:
    end = time.monotonic() + seconds
    lines: list[str] = []
    while time.monotonic() < end:
        raw = port.readline()
        if raw:
            line = raw.decode("utf-8", "replace").strip()
            if line:
                lines.append(line)
                print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)
    return lines


def send(port: serial.Serial, command: str) -> None:
    print(f">>> {command}", flush=True)
    port.write((command + "\n").encode("ascii"))
    port.flush()


def main() -> int:
    with serial.Serial(PORT, BAUD, timeout=0.25) as port:
        time.sleep(3.0)
        port.reset_input_buffer()
        send(port, "GET_STATUS")
        read_for(port, 4.0)
        # The operator already confirmed clean air for this user-authorized run.
        send(port, "VERIFY_CLEAN_AIR_FOR_NULLING")
        read_for(port, 3.0)
        send(port, "SET_MODE nulling")

        end = time.monotonic() + 900.0
        while time.monotonic() < end:
            raw = port.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)
            if line.startswith((
                "NULLING_RUNTIME_RESULT=PASS",
                "NULLING_RUNTIME_RESULT=PARTIAL_RETRY",
                "NULLING_RUNTIME_RESULT=FAIL_RETRY",
                "NULLING_SERVICE_BLOCKED",
            )):
                return 0
    print("Timed out waiting for nulling result", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
