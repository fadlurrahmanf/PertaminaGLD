import json
import pathlib
import serial
import time

PORT = "COM3"
BAUD = 115200
OUTPUT = pathlib.Path("tmp/gld2-nulling-record-2026-08-28.jsonl")

def write_record(kind, **fields):
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "kind": kind, **fields}
    with OUTPUT.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
write_record("start", port=PORT, baud=BAUD, command="SET_MODE nulling")

with serial.Serial(PORT, BAUD, timeout=0.25) as board:
    time.sleep(0.3)
    board.reset_input_buffer()
    board.write(b"SET_MODE nulling\n")
    board.flush()
    write_record("command_sent", command="SET_MODE nulling")
    last_data = time.monotonic()
    while True:
        raw = board.readline()
        if raw:
            last_data = time.monotonic()
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            write_record("serial", line=line)
            if "NULLING_RUN status=" in line or "NULLING_RUN=BLOCKED" in line:
                write_record("terminal_marker", line=line)
        elif time.monotonic() - last_data > 1200:
            write_record("recorder_timeout", seconds=1200)
            break
