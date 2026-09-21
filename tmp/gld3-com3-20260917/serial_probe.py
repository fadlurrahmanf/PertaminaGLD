"""Bounded, logged GLD bench commands; no reset on intentional DTR/RTS state."""
import argparse
import datetime
import json
import pathlib
import re
import time
import serial
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

p = argparse.ArgumentParser()
p.add_argument('--port', default='COM3')
p.add_argument('--log', required=True)
p.add_argument('--listen', type=float, default=3)
p.add_argument('--gap', type=float, default=2)
p.add_argument('--quiet', action='store_true')
p.add_argument('--alarm-test', action='store_true', help='Bounded two-second ON test with OFF/AUTO cleanup')
p.add_argument('commands', nargs='*')
a = p.parse_args()
path = pathlib.Path(a.log)
path.parent.mkdir(parents=True, exist_ok=True)

def sanitize(line):
    return re.sub(r'(?i)("(?:password|wifiPassword|mqttPassword|aesKey|keyHex|token|secret)"\s*:\s*")[^"]*', r'\1<redacted>', line)

with path.open('a', encoding='utf-8') as log:
    def record(line):
        safe = sanitize(line)
        log.write(datetime.datetime.now().isoformat(timespec='milliseconds') + ' ' + safe + '\n')
        log.flush()
        if not a.quiet:
            print(safe, flush=True)
    link = serial.Serial(port=None, baudrate=115200, timeout=0.1, write_timeout=2)
    link.dtr = False
    link.rts = False
    link.port = a.port
    try:
        link.open()
        buf = bytearray()
        def read_for(seconds):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                data = link.read(link.in_waiting or 1)
                if data:
                    buf.extend(data)
                    while b'\n' in buf:
                        line, _, rest = buf.partition(b'\n')
                        buf[:] = rest
                        record(line.decode('utf-8', errors='replace').rstrip('\r'))
        read_for(a.listen)
        for command in a.commands:
            record('>>> ' + command)
            link.write((command + '\n').encode())
            link.flush()
            read_for(a.gap)
        if a.alarm_test:
            def send_alarm(command, delay=1):
                record('>>> ' + command)
                link.write((command + '\n').encode())
                link.flush()
                read_for(delay)
            try:
                send_alarm('SET_ALARM_MODE_JSON {"mode":"manual"}')
                send_alarm('SET_MANUAL_ALARM_JSON {"enabled":true}', 2)
            finally:
                # Always clear the commanded output and restore AUTO before closing.
                send_alarm('SET_MANUAL_ALARM_JSON {"enabled":false}')
                send_alarm('SET_ALARM_MODE_JSON {"mode":"auto"}')
                send_alarm('GET_STATUS')
        if buf:
            record(buf.decode('utf-8', errors='replace'))
    finally:
        link.close()
