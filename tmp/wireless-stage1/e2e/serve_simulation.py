"""PC-only GLD Operator wireless E2E fixture. Never opens COM or device IPs.

Real app HTML/CSS/JS, Handler wireless routes, collector and WebSocket client;
synthetic RFC6455 device on ephemeral loopback. This is not production Hub.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import math
import os
import select
import socket
import struct
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
APP = REPO / "apps" / "gld-operator"
OUTPUT = HERE / "output"
EVIDENCE = HERE / "evidence.json"
PASSWORD = "simulation-only-password"
FEATURES = ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"]
PROTOCOL = "gld-dataset-wifi/1"
BOOT = time.monotonic()

sys.path.insert(0, str(APP))
spec = importlib.util.spec_from_file_location("gld_simulation_bridge", APP / "bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
from wireless_dataset import ENDPOINT, WirelessDatasetCollector, _transport_factory


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


class Evidence:
    def __init__(self):
        self.lock = threading.RLock()
        self.collector = None
        self.value = dict(schema="gld-dataset-e2e/1", mode="pc-simulation",
                          endpoint={}, sessions=[], method_calls=[], blocked_requests=[],
                          diagnostics=[], diagnostic_counts={})

    def diagnostic(self, phase, exc):
        item = dict(phase=phase, exception_class=type(exc).__name__,
                    winerror=getattr(exc, "winerror", None), host_monotonic_s=time.monotonic())
        with self.lock:
            self.value["diagnostics"].append(item)
            self.value["diagnostics"] = self.value["diagnostics"][-100:]
            key = phase + ":" + type(exc).__name__
            self.value["diagnostic_counts"][key] = self.value["diagnostic_counts"].get(key, 0) + 1
        try:
            print("SIMULATION_DIAGNOSTIC " + json.dumps(item), file=sys.stderr, flush=True)
        except OSError:
            pass

    def session(self, session_id):
        return next((item for item in self.value["sessions"] if item["session_id"] == session_id), None)

    def begin(self, command):
        with self.lock:
            self.value["sessions"].append(dict(
                name=command["label"], device_id="1001", session_id=command["session_id"],
                label=command["label"], csv_path="", commands=[], emitted_samples=[],
                emitted_messages=[], emission_monotonic_s=[], summary=None,
                final_snapshot={}, checkpoints=[]))

    def call(self, path, action=None):
        with self.lock:
            self.value["method_calls"].append(dict(path=path, action=action,
                                                  host_monotonic_s=time.monotonic()))

    def command(self, command):
        with self.lock:
            item = self.session(command["session_id"])
            if item:
                item["commands"].append(dict(command))

    def message(self, message):
        with self.lock:
            item = self.session(message.get("session_id"))
            if item:
                item["emitted_messages"].append(dict(message))
                if message["type"] == "sample":
                    item["emitted_samples"].append(dict(message))
                    item["emission_monotonic_s"].append(time.monotonic())
                elif message["type"] == "summary":
                    item["summary"] = dict(message)

    def save(self, checkpoint=None):
        # Collector lock precedes evidence lock everywhere; never invert them.
        snapshot = self.collector.snapshot() if self.collector else {}
        with self.lock:
            item = self.session(snapshot.get("session_id"))
            if item:
                item["final_snapshot"] = snapshot
                item["csv_path"] = snapshot.get("path", "")
                if checkpoint:
                    item["checkpoints"].append(dict(name=checkpoint,
                        host_monotonic_s=time.monotonic(), snapshot=snapshot))
            result = json.loads(json.dumps(self.value))
            temporary = EVIDENCE.with_suffix(".tmp")
            try:
                temporary.write_text(json.dumps(result, indent=2), encoding="utf-8")
                temporary.replace(EVIDENCE)
            except OSError as exc:
                # Windows readers can temporarily prevent replacement. The
                # observability journal is not part of device transport: retain
                # it in memory and retry on the next event/checkpoint instead
                # of terminating an otherwise healthy WebSocket session.
                self.diagnostic("evidence_persistence", exc)
                result = json.loads(json.dumps(self.value))
            return result


evidence = Evidence()
peers = set()
peers_lock = threading.RLock()
stop_event = threading.Event()


class FakeDevice(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def exact(self, size):
        result = bytearray()
        while len(result) < size:
            part = self.connection.recv(size - len(result))
            if not part:
                raise ConnectionError()
            result.extend(part)
        return bytes(result)

    def receive(self):
        first, second = self.exact(2)
        if not first & 0x80 or first & 0x70 or not second & 0x80:
            raise ValueError("Invalid client frame")
        size = second & 127
        if size == 126:
            size = struct.unpack("!H", self.exact(2))[0]
        elif size == 127:
            size = struct.unpack("!Q", self.exact(8))[0]
        if size > 4096:
            raise ValueError("Client frame too large")
        mask = self.exact(4)
        raw = self.exact(size)
        return first & 15, bytes(value ^ mask[index % 4] for index, value in enumerate(raw))

    def send_frame(self, value, opcode=1):
        data = value.encode("utf-8") if isinstance(value, str) else value
        prefix = bytes([0x80 | opcode])
        if len(data) < 126:
            prefix += bytes([len(data)])
        else:
            prefix += bytes([126]) + struct.pack("!H", len(data))
        self.connection.sendall(prefix + data)

    def send_message(self, message):
        self.send_frame(json.dumps(message, separators=(",", ":")))
        evidence.message(message)

    def force_drop(self):
        self.dropped = True
        self.running = False
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.connection.close()

    def ack(self, command, result="ok", detail=""):
        self.send_message(dict(type="ack", cmd=command["cmd"],
            command_id=command["command_id"], session_id=command["session_id"],
            result=result, detail=detail))

    def handle_command(self, command):
        if (not isinstance(command, dict) or command.get("cmd") not in {"START_DATASET", "STOP_DATASET"} or
                not isinstance(command.get("command_id"), str) or
                not isinstance(command.get("session_id"), str) or
                not 1 <= len(command["command_id"]) <= 64 or
                not 1 <= len(command["session_id"]) <= 64):
            raise ValueError("Invalid Dataset command")
        if command["cmd"] == "START_DATASET":
            label = command.get("label")
            if (self.running or type(command.get("sample_interval_ms")) is not int or
                    command["sample_interval_ms"] != 500 or not isinstance(label, str) or
                    not 1 <= len(label) <= 31 or any(ord(char) < 32 or ord(char) > 126 for char in label) or
                    label[0] in "=+-@"):
                self.ack(command, "error", "invalid_start")
                return
            self.session_id, self.label = command["session_id"], label
            self.seq = 0
            self.base_ms = round((time.monotonic() - BOOT) * 1000)
            self.next_due = time.monotonic() + 0.5
            evidence.begin(command)
            evidence.command(command)
            self.ack(command)
            self.send_message(dict(type="status", session_id=self.session_id, state="running"))
            self.running = True
        else:
            evidence.command(command)
            if not self.running or command["session_id"] != self.session_id:
                self.ack(command, "error", "session_not_active")
                return
            self.running = False
            self.ack(command)
            self.send_message(dict(type="status", session_id=self.session_id, state="idle"))
            self.send_message(dict(type="summary", session_id=self.session_id,
                                   total_samples=self.seq, incomplete=False, reason="stopped"))
        evidence.save()

    def sample(self):
        timestamp = self.base_ms + (self.seq + 1) * 500
        message = dict(type="sample", device_id="1001", session_id=self.session_id,
            seq=self.seq, timestamp_ms=timestamp, scan_end_ms=timestamp + 10,
            mode="DATASET", label=self.label, nulling_profile_id=5,
            sensor_voltage=[round(0.1 * (channel + 1) + 0.02 * math.sin(self.seq * 0.17 + channel * 0.4), 7)
                            for channel in range(8)],
            sensor_gain=[1] * 8, sensor_status=[0] * 8, feature_order=FEATURES, overrun_count=0)
        self.send_message(message)
        self.seq += 1
        self.next_due += 0.5

    def do_GET(self):
        expected = "Basic " + base64.b64encode(f"gld:{PASSWORD}".encode()).decode()
        if self.path != "/dataset" or self.headers.get("Authorization") != expected:
            self.send_error(401)
            return
        key = self.headers.get("Sec-WebSocket-Key", "")
        if self.headers.get("Upgrade", "").lower() != "websocket" or not key:
            self.send_error(400)
            return
        accept = base64.b64encode(hashlib.sha1(
            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        self.connection.settimeout(1)
        self.running = self.dropped = False
        self.session_id = self.label = ""
        self.seq = 0
        with peers_lock:
            peers.add(self)
        try:
            self.send_message(dict(type="hello", protocol=PROTOCOL, device_id="1001",
                feature_order=FEATURES, interval_ms=500, ready=True,
                reason="SIMULATION: synthetic sensor data, no GLD hardware"))
            while not self.dropped and not stop_event.is_set():
                timeout = max(0, min(0.05, self.next_due - time.monotonic())) if self.running else 0.05
                readable, _, _ = select.select([self.connection], [], [], timeout)
                if readable:
                    opcode, raw = self.receive()
                    if opcode == 8:
                        self.send_frame(raw, opcode=8)
                        break
                    if opcode == 9:
                        self.send_frame(raw, opcode=10)
                        continue
                    if opcode != 1:
                        raise ValueError("Expected text command")
                    self.handle_command(json.loads(raw))
                if self.running and time.monotonic() >= self.next_due:
                    self.sample()
                    evidence.save()
        except (OSError, ValueError, ConnectionError) as exc:
            evidence.diagnostic("peer_loop", exc)
        finally:
            was_running = self.running or self.dropped
            self.running = False
            if was_running and self.session_id:
                with evidence.lock:
                    item = evidence.session(self.session_id)
                    if item:
                        item["disconnect"] = dict(host_monotonic_s=time.monotonic(),
                            total_samples=self.seq, incomplete=True, reason="forced_drop" if self.dropped else "client_disconnect")
            with peers_lock:
                peers.discard(self)
            evidence.save()


class SimulationHandler(bridge.Handler):
    def log_message(self, *_args):
        pass

    def body(self, value, kind="text/html; charset=utf-8", status=200):
        raw = value.encode("utf-8") if isinstance(value, str) else value
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def simulation_access(self):
        origin = self.headers.get("Origin", "")
        return (self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}" and
                (not origin or origin == f"http://127.0.0.1:{self.server.server_port}"))

    def do_GET(self):
        path = urlparse(self.path).path
        if not self.simulation_access():
            return bridge.json_response(self, {"error": "simulation origin rejected"}, HTTPStatus.FORBIDDEN)
        if path == "/":
            return self.body("""<!doctype html><html><head><meta charset=utf-8>
<title>Operator Hub Simulator — Synthetic GLD</title>
<style>html,body{margin:0;height:100%;font:15px system-ui;background:#102235;color:#fff}
header{padding:12px 18px;background:#9d3d00}h1{margin:0;font-size:19px}p{margin:5px 0 0}
iframe{border:0;width:100%;height:calc(100vh - 83px);background:#fff}</style></head>
<body><header><h1>Operator Hub Simulator — SIMULATION</h1>
<p>Data delapan sensor sintetis · tidak ada COM/GLD fisik · real GLD Operator UI dan backend</p></header>
<iframe title="GLD Operator — simulation only" src="/gld/"></iframe></body></html>""")
        if path == "/sim/state":
            return bridge.json_response(self, evidence.save())
        if path == "/api/health":
            return bridge.json_response(self, dict(ok=True, appId=bridge.APP_ID,
                version=bridge.VERSION + "-SIMULATION", csrfToken=bridge.BRIDGE_CSRF_TOKEN,
                simulation=True, features=dict(serial=False, mqtt=False, datasetMonitor=False,
                    mqttBroker=False, datasetOutput=True, wirelessDataset=True,
                    networkInfo=False, firmwareUpload=False, firmwareGld1DowngradeGuard=False),
                slots={}, maxSlots=0, mqttBroker=dict(running=False), errors={}))
        if path.startswith("/api/"):
            try:
                self._require_api_access(path)
            except Exception as exc:
                return self._request_error(exc)
            if path == "/api/ports":
                return bridge.json_response(self, {"ports": []})
            if path == "/api/network":
                return bridge.json_response(self, dict(ssid="SIMULATION-LOOPBACK", ipv4="127.0.0.1", simulation=True))
            if path == "/api/serial/status":
                return bridge.json_response(self, dict(connected=False, port="", baud=115200))
            if path == "/api/serial/recent":
                return bridge.json_response(self, dict(sequence=0, lines=[]))
            if path == "/api/gld-key-status":
                return bridge.json_response(self, dict(configured=False, keyId=None, source=None, nodeRedDeployment="simulation"))
            if path in {"/api/events", "/api/wireless-dataset/state", "/api/dataset/output-dir"}:
                return super().do_GET()
            return self.blocked(path)
        if path.startswith("/gld/"):
            suffix = unquote(path[len("/gld/"):]) or "index.html"
            target = (APP / suffix).resolve()
            if (not target.is_relative_to(APP) or not target.is_file() or
                    target.suffix not in {".html", ".css", ".js"} or
                    (suffix not in {"index.html", "style.css"} and not suffix.startswith(("js/", "css/")))):
                return self.body("not found", "text/plain", 404)
            source = target.read_text(encoding="utf-8")
            if suffix == "index.html":
                source = source.replace("<body>", "<body><div id='simulationBanner' style='background:#a84000;color:#fff;padding:8px 16px;font:600 13px system-ui'>SIMULATION — sensor sintetis, tanpa COM/perangkat fisik. Hotspot password uji: simulation-only-password.</div>")
                source = source.replace('href="http://127.0.0.1:5173/"', 'href="/"')
                source = source.replace("<title>GLD Operator</title>", "<title>GLD Operator — SIMULATION</title>")
            elif suffix == "js/bridge-client.js":
                source = source.replace('"http://127.0.0.1:5174"', f'"http://127.0.0.1:{self.server.server_port}"')
                source = source.replace('location.port === "5174"', f'location.port === "{self.server.server_port}"')
            return self.body(source, {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}.get(target.suffix, "text/html; charset=utf-8"))
        return self.body("not found", "text/plain", 404)

    def blocked(self, path):
        with evidence.lock:
            evidence.value["blocked_requests"].append(dict(method=self.command, path=path))
        evidence.save()
        return bridge.json_response(self, {"error": "SIMULATION: hardware, firmware, serial and MQTT routes are disabled"}, HTTPStatus.FORBIDDEN)

    def do_POST(self):
        path = urlparse(self.path).path
        if not self.simulation_access():
            return bridge.json_response(self, {"error": "simulation origin rejected"}, HTTPStatus.FORBIDDEN)
        evidence.call(path)
        if path.startswith("/sim/"):
            try:
                payload = bridge.read_json(self)
                if path == "/sim/checkpoint":
                    return bridge.json_response(self, evidence.save(checkpoint=str(payload.get("name", "checkpoint"))[:80]))
                if path == "/sim/drop":
                    with peers_lock:
                        current = list(peers)
                    for peer in current:
                        peer.force_drop()
                    return bridge.json_response(self, dict(ok=True, dropped=len(current), evidence=evidence.save()))
                if path == "/sim/shutdown":
                    bridge.json_response(self, {"ok": True})
                    threading.Thread(target=shutdown, daemon=True).start()
                    return
            except Exception:
                return bridge.json_response(self, {"error": "invalid simulation request"}, HTTPStatus.BAD_REQUEST)
        if path in {"/api/wireless-dataset/connect", "/api/wireless-dataset/start",
                    "/api/wireless-dataset/stop", "/api/wireless-dataset/disconnect",
                    "/api/wireless-dataset/export"}:
            return super().do_POST()
        return self.blocked(path)


def callback(payload):
    bridge.events.emit("wireless_dataset", payload)
    evidence.save()


def websocket_factory(requested_url, **options):
    if requested_url != ENDPOINT:
        raise RuntimeError("Simulation refused a non-fixed device endpoint")
    return _transport_factory(f"ws://127.0.0.1:{ws_server.server_port}/dataset", **options)


def shutdown():
    stop_event.set()
    with peers_lock:
        current = list(peers)
    for peer in current:
        peer.force_drop()
    bridge.wireless_dataset_collector.disconnect()
    evidence.save()
    ws_server.shutdown()
    http_server.shutdown()


if __name__ == "__main__":
    OUTPUT.mkdir(parents=True, exist_ok=True)
    bridge.DATASET_OUTPUT_DIR = OUTPUT
    bridge.SESSION_LOG_DIR = OUTPUT / "logs"
    bridge.serial_bridges.clear()
    ws_server = Server(("127.0.0.1", 0), FakeDevice)
    http_server = Server(("127.0.0.1", 0), SimulationHandler)
    origin = f"http://127.0.0.1:{http_server.server_port}"
    bridge.BRIDGE_ALLOWED_ORIGINS = {origin}
    collector = WirelessDatasetCollector(OUTPUT, callback,
        websocket_factory=websocket_factory, command_timeout=3)
    evidence.collector = collector
    bridge.wireless_dataset_collector = collector
    with evidence.lock:
        evidence.value["endpoint"] = dict(host="127.0.0.1", http_port=http_server.server_port,
                                          ws_port=ws_server.server_port)
    evidence.save()
    ready = dict(ui_url=origin + "/", app_url=origin + "/gld/", bridge_port=http_server.server_port,
                 ws_port=ws_server.server_port, password=PASSWORD, output_dir=str(OUTPUT),
                 evidence_path=str(EVIDENCE), pid=os.getpid(), mode="pc-simulation")
    (HERE / "ready.json").write_text(json.dumps(ready, indent=2), encoding="utf-8")
    threading.Thread(target=ws_server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    print(json.dumps({"simulation_ready": True, "ui_url": ready["ui_url"], "pid": ready["pid"]}), flush=True)
    try:
        http_server.serve_forever(poll_interval=0.05)
    finally:
        stop_event.set()
        http_server.server_close()
        ws_server.server_close()
