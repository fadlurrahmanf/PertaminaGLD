"""Read one post-nulling GLD status from COM7 without changing configuration."""
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
    port.reset_input_buffer()
    port.write(b"GET_STATUS\n")
    port.flush()
    end = time.monotonic() + 5.0
    while time.monotonic() < end:
        raw = port.readline()
        if raw:
            text = raw.decode("utf-8", "replace").rstrip()
            print(text.encode("ascii", "backslashreplace").decode("ascii"), flush=True)
finally:
    port.close()
