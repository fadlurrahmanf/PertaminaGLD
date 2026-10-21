"""Read COM7 without asserting modem-control reset lines."""
from __future__ import annotations

import time
import serial

port = serial.Serial()
port.port = "COM7"
port.baudrate = 115200
port.timeout = 0.25
port.dtr = False
port.rts = False
port.open()
try:
    end = time.monotonic() + 12.0
    while time.monotonic() < end:
        raw = port.readline()
        if raw:
            text = raw.decode("utf-8", "replace").rstrip()
            print(text.encode("ascii", "backslashreplace").decode("ascii"), flush=True)
finally:
    port.close()
