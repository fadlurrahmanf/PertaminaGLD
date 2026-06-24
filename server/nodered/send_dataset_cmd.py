#!/usr/bin/env python3
"""Send START_DATASET / STOP_DATASET to GLD via raw MQTT.
Usage:
    python send_dataset_cmd.py start [label]
    python send_dataset_cmd.py stop
"""
import socket
import struct
import sys
import time
import json
import os

HOST  = os.environ.get("MQTT_HOST", "127.0.0.1")
PORT  = int(os.environ.get("MQTT_PORT", "1884"))
USER  = os.environ.get("MQTT_USER", "").encode("utf-8")
PASS  = os.environ.get("MQTT_PASS", "").encode("utf-8")
CID   = b"py-dataset-cmd"
# Design Section 10.2: dataset commands on .../dataset topic (not .../dataset/cmd)
TOPIC = "gas-leak-detector/F001/dataset"

def encode_remaining(n):
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        if n:
            byte |= 0x80
        out.append(byte)
        if not n:
            break
    return bytes(out)

def mqtt_connect(sock):
    cid   = struct.pack(">H", len(CID)) + CID
    flags = 0x02
    auth = b""
    if USER:
        flags |= 0x80
        auth += struct.pack(">H", len(USER)) + USER
    if PASS:
        flags |= 0x40
        auth += struct.pack(">H", len(PASS)) + PASS
    var   = b"\x00\x04MQTT\x04" + bytes([flags]) + b"\x00\x3c" + cid + auth
    pkt   = b"\x10" + encode_remaining(len(var)) + var
    sock.sendall(pkt)
    time.sleep(0.2)
    ack = sock.recv(4)
    if len(ack) < 4 or ack[3] != 0:
        raise RuntimeError(f"CONNACK error code: {ack[3] if len(ack) >= 4 else '?'}")

def mqtt_publish(sock, topic_str, payload_bytes):
    topic = topic_str.encode("ascii")
    var   = struct.pack(">H", len(topic)) + topic + payload_bytes
    pkt   = b"\x30" + encode_remaining(len(var)) + var
    sock.sendall(pkt)
    time.sleep(0.1)


action = sys.argv[1].lower() if len(sys.argv) > 1 else "start"
label  = sys.argv[2] if len(sys.argv) > 2 else "clear_air_test"

if action == "start":
    cmd_obj = {
        "cmd": "START_DATASET",
        "label": label,
        "target_samples": 0,          # 0 = unlimited
        "sample_interval_ms": 1000,
        "max_duration_ms": 0,          # 0 = unlimited
        "use_fan_intake": False,       # set True if fan wired and needed
        "fan_on_ms": 1000,
        "post_fan_settle_ms": 0,
    }
elif action == "stop":
    cmd_obj = {"cmd": "STOP_DATASET"}
else:
    print(f"Unknown action: {action}. Use 'start' or 'stop'.")
    sys.exit(1)

# json.dumps produces clean ASCII-safe JSON with no BOM
payload_bytes = json.dumps(cmd_obj, separators=(",", ":")).encode("ascii")
print(f"Sending to {TOPIC}: {payload_bytes.decode()}")

s = socket.socket()
s.settimeout(10)
s.connect((HOST, PORT))
mqtt_connect(s)
mqtt_publish(s, TOPIC, payload_bytes)
s.close()
print("Done.")
