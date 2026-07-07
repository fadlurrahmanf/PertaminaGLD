#!/usr/bin/env python3
"""GLD Operator Lite local bridge.

Serves the static UI and exposes native Windows features that plain browser
JavaScript cannot access: COM port listing, serial read/write, WiFi/IP lookup,
MQTT publish for dataset commands, and PlatformIO firmware upload orchestration.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import serial
    from serial.tools import list_ports
except Exception as exc:  # pragma: no cover - surfaced in /api/health
    serial = None
    list_ports = None
    SERIAL_IMPORT_ERROR = str(exc)
else:
    SERIAL_IMPORT_ERROR = ""

try:
    import paho.mqtt.client as mqtt
except Exception as exc:  # pragma: no cover - MQTT is optional
    mqtt = None
    MQTT_IMPORT_ERROR = str(exc)
else:
    MQTT_IMPORT_ERROR = ""


APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parents[1]
FIRMWARE_DIR = REPO_ROOT / "firmware"
DATASET_OUTPUT_DIR = APP_DIR / "output" / "datasets"

# Populated at startup from the actual --host/--port the bridge binds to.
# The documented launch path (run-gld-operator.bat) serves the static UI and
# this API from the same origin, so same-origin requests never need a CORS
# header at all; this allowlist only covers the same machine reachable via
# 127.0.0.1/localhost, never an arbitrary remote origin. Do not widen this to
# "*" - the bridge exposes serial writes, MQTT publish, firmware flashing, and
# a WiFi-password lookup, and a wildcard lets any page open in the operator's
# browser call all of that cross-origin.
BRIDGE_ALLOWED_ORIGINS: set[str] = set()


def _register_allowed_origins(host: str, port: int) -> None:
    BRIDGE_ALLOWED_ORIGINS.update(
        {
            f"http://{host}:{port}",
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
        }
    )


VERSION = "0.2.3-lite-bridge"


class EventHub:
    def __init__(self) -> None:
        self._clients: set[queue.Queue[dict[str, Any]]] = set()
        self._lock = threading.Lock()

    def add(self) -> queue.Queue[dict[str, Any]]:
        client: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=500)
        with self._lock:
            self._clients.add(client)
        return client

    def remove(self, client: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._clients.discard(client)

    def emit(self, event: str, payload: dict[str, Any]) -> None:
        item = {"event": event, "payload": payload, "ts": time.time()}
        stale: list[queue.Queue[dict[str, Any]]] = []
        with self._lock:
            clients = list(self._clients)
        for client in clients:
            try:
                client.put_nowait(item)
            except queue.Full:
                stale.append(client)
        if stale:
            with self._lock:
                for client in stale:
                    self._clients.discard(client)


class SerialBridge:
    def __init__(self, events: EventHub) -> None:
        self.events = events
        self._serial: Any = None
        self._lock = threading.Lock()
        self._reader_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.port = ""
        self.baud = 115200

    def list_ports(self) -> list[dict[str, Any]]:
        if list_ports is None:
            raise RuntimeError(f"pyserial unavailable: {SERIAL_IMPORT_ERROR}")
        ports = []
        for port in list_ports.comports():
            ports.append(
                {
                    "path": port.device,
                    "description": port.description,
                    "manufacturer": port.manufacturer,
                    "serialNumber": port.serial_number,
                    "vendorId": port.vid,
                    "productId": port.pid,
                }
            )
        return ports

    def connect(self, port: str, baud: int = 115200) -> dict[str, Any]:
        if serial is None:
            raise RuntimeError(f"pyserial unavailable: {SERIAL_IMPORT_ERROR}")
        self.disconnect()
        ser = serial.Serial()
        ser.port = port
        ser.baudrate = baud
        ser.timeout = 0.2
        ser.write_timeout = 2
        ser.dtr = False
        ser.rts = False
        ser.open()
        try:
            ser.setDTR(False)
            ser.setRTS(False)
        except Exception:
            pass
        with self._lock:
            self._serial = ser
            self.port = port
            self.baud = baud
            self._stop.clear()
        self._reader_thread = threading.Thread(target=self._read_loop, name="gld-serial-reader", daemon=True)
        self._reader_thread.start()
        self.events.emit("serial_status", {"connected": True, "port": port, "baud": baud})
        return {"connected": True, "port": port, "baud": baud}

    def disconnect(self) -> dict[str, Any]:
        self._stop.set()
        with self._lock:
            ser = self._serial
            self._serial = None
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
        self.events.emit("serial_status", {"connected": False})
        return {"connected": False}

    def write_line(self, line: str, require_connected: bool = True) -> dict[str, Any]:
        if not line.endswith("\n"):
            line += "\n"
        with self._lock:
            ser = self._serial
        if ser is None or not ser.is_open:
            if not require_connected:
                return {"ok": False, "connected": False, "skipped": True, "message": "serial port is not connected"}
            raise RuntimeError("serial port is not connected")
        ser.write(line.encode("utf-8", errors="replace"))
        ser.flush()
        self.events.emit("serial_tx", {"line": line.rstrip("\r\n")})
        return {"ok": True}

    def _read_loop(self) -> None:
        pending = b""
        while not self._stop.is_set():
            with self._lock:
                ser = self._serial
            if ser is None or not ser.is_open:
                break
            try:
                chunk = ser.read(512)
            except Exception as exc:
                self.events.emit("serial_error", {"message": str(exc)})
                break
            if not chunk:
                continue
            pending += chunk
            while b"\n" in pending:
                raw, pending = pending.split(b"\n", 1)
                line = raw.decode("utf-8", errors="replace").strip("\r")
                if line:
                    self.events.emit("serial_line", {"line": line})
        self.events.emit("serial_status", {"connected": False})


events = EventHub()
serial_bridge = SerialBridge(events)


class DatasetMqttMonitor:
    def __init__(self, events: EventHub) -> None:
        self.events = events
        self._lock = threading.Lock()
        self._client: Any = None
        self.config: dict[str, Any] = {}

    def start(self, config: dict[str, Any]) -> dict[str, Any]:
        if mqtt is None:
            raise RuntimeError(f"paho-mqtt unavailable: {MQTT_IMPORT_ERROR}")
        device_id = str(config.get("deviceId") or "").strip()
        topic_root = str(config.get("topicRoot") or "gas-leak-detector").strip("/")
        host = str(config.get("host") or "127.0.0.1")
        port = int(config.get("port") or 1884)
        username = str(config.get("username") or "")
        password = str(config.get("password") or "")
        if not device_id:
            raise RuntimeError("deviceId is required")

        topics = [
            f"{topic_root}/{device_id}/cmd/ack",
            f"{topic_root}/{device_id}/dataset/status",
            f"{topic_root}/{device_id}/dataset/data",
            f"{topic_root}/{device_id}/dataset/summary",
        ]
        self.stop(emit=False)

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if username or password:
            client.username_pw_set(username, password)

        def on_connect(client_obj: Any, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any) -> None:
            for topic in topics:
                client_obj.subscribe(topic, qos=0)
            self.events.emit(
                "dataset_monitor",
                {"status": "subscribed", "host": host, "port": port, "deviceId": device_id, "topics": topics, "reason": str(reason_code)},
            )

        def on_message(_client_obj: Any, _userdata: Any, msg: Any) -> None:
            text = msg.payload.decode("utf-8", errors="replace")
            try:
                parsed: Any = json.loads(text)
            except Exception:
                parsed = None
            self.events.emit(
                "dataset_mqtt",
                {"topic": msg.topic, "kind": self._kind(msg.topic), "payload": text, "json": parsed},
            )

        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(host, port, keepalive=20)
        client.loop_start()

        with self._lock:
            self._client = client
            self.config = {"deviceId": device_id, "topicRoot": topic_root, "host": host, "port": port, "topics": topics}
        self.events.emit("dataset_monitor", {"status": "started", "host": host, "port": port, "deviceId": device_id})
        return {"started": True, "topics": topics}

    def stop(self, emit: bool = True) -> dict[str, Any]:
        with self._lock:
            client = self._client
            self._client = None
        if client is not None:
            try:
                client.loop_stop()
            except Exception:
                pass
            try:
                client.disconnect()
            except Exception:
                pass
        if emit:
            self.events.emit("dataset_monitor", {"status": "stopped"})
        return {"stopped": True}

    @staticmethod
    def _kind(topic: str) -> str:
        if topic.endswith("/dataset/data"):
            return "data"
        if topic.endswith("/dataset/status"):
            return "status"
        if topic.endswith("/dataset/summary"):
            return "summary"
        if topic.endswith("/cmd/ack"):
            return "ack"
        return "message"


dataset_monitor = DatasetMqttMonitor(events)


def json_response(handler: SimpleHTTPRequestHandler, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler: SimpleHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


def run_text_command(args: list[str], timeout: int = 10) -> str:
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )
    return f"{completed.stdout}\n{completed.stderr}"


def active_wifi_ssid() -> str:
    text = run_text_command(["netsh", "wlan", "show", "interfaces"])
    for line in text.splitlines():
        match = re.match(r"^\s*SSID\s*:\s*(.+?)\s*$", line)
        if match and not line.strip().startswith("BSSID"):
            return match.group(1).strip()
    return ""


def wifi_password(ssid: str) -> str:
    if not ssid:
        return ""
    text = run_text_command(["netsh", "wlan", "show", "profile", f"name={ssid}", "key=clear"])
    for line in text.splitlines():
        match = re.search(r"Key Content\s*:\s*(.+)$", line)
        if match:
            return match.group(1).strip()
    return ""


def local_ipv4() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        value = sock.getsockname()[0]
        sock.close()
        if value and not value.startswith("127."):
            return value
    except Exception:
        pass
    try:
        for value in socket.gethostbyname_ex(socket.gethostname())[2]:
            if value and not value.startswith("127."):
                return value
    except Exception:
        pass
    return "127.0.0.1"


def network_info() -> dict[str, str]:
    ssid = active_wifi_ssid()
    return {"ssid": ssid, "password": wifi_password(ssid), "ipv4": local_ipv4()}


def safe_filename(value: str, fallback: str = "dataset.csv") -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    name = name.strip("._")
    if not name:
        name = fallback
    if not name.lower().endswith(".csv"):
        name += ".csv"
    return name[:120]


def dataset_output_info() -> dict[str, Any]:
    DATASET_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return {"path": str(DATASET_OUTPUT_DIR), "exists": DATASET_OUTPUT_DIR.exists()}


def save_dataset_csv(payload: dict[str, Any]) -> dict[str, Any]:
    csv_text = str(payload.get("csv") or "")
    if not csv_text.strip():
        raise RuntimeError("csv payload is empty")
    filename = safe_filename(str(payload.get("filename") or "dataset.csv"))
    DATASET_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = DATASET_OUTPUT_DIR / filename
    path.write_text(csv_text, encoding="utf-8", newline="")
    result = {"ok": True, "path": str(path), "filename": filename, "bytes": path.stat().st_size}
    events.emit("dataset_saved", result)
    return result


def open_dataset_folder() -> dict[str, Any]:
    DATASET_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(DATASET_OUTPUT_DIR))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(DATASET_OUTPUT_DIR)])
    else:
        subprocess.Popen(["xdg-open", str(DATASET_OUTPUT_DIR)])
    return {"ok": True, "path": str(DATASET_OUTPUT_DIR)}


def mqtt_publish_dataset(payload: dict[str, Any]) -> dict[str, Any]:
    if mqtt is None:
        raise RuntimeError(f"paho-mqtt unavailable: {MQTT_IMPORT_ERROR}")
    device_id = str(payload.get("deviceId") or "").strip()
    topic_root = str(payload.get("topicRoot") or "gas-leak-detector").strip("/")
    host = str(payload.get("host") or "127.0.0.1")
    port = int(payload.get("port") or 1884)
    username = str(payload.get("username") or "")
    password = str(payload.get("password") or "")
    command = str(payload.get("command") or "START_DATASET")
    if not device_id:
        raise RuntimeError("deviceId is required")
    if command == "START_DATASET":
        dataset_monitor.start(payload)
    topic = f"{topic_root}/{device_id}/dataset"
    message = json.dumps(payload.get("dataset") or {"cmd": command})
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if username or password:
        client.username_pw_set(username, password)
    connected = threading.Event()
    connect_error: dict[str, str] = {}

    def on_connect(_client: Any, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any) -> None:
        if str(reason_code).lower() == "success" or reason_code == 0:
            connected.set()
        else:
            connect_error["message"] = str(reason_code)
            connected.set()

    client.on_connect = on_connect
    client.connect(host, port, keepalive=10)
    client.loop_start()
    if not connected.wait(timeout=5):
        client.loop_stop()
        client.disconnect()
        raise RuntimeError(f"MQTT connect timeout to {host}:{port}")
    if connect_error:
        client.loop_stop()
        client.disconnect()
        raise RuntimeError(f"MQTT connect failed: {connect_error['message']}")
    result = client.publish(topic, message, qos=0, retain=False)
    result.wait_for_publish(timeout=5)
    if not result.is_published():
        client.loop_stop()
        client.disconnect()
        raise RuntimeError(f"MQTT publish timeout to {topic}")
    client.disconnect()
    client.loop_stop()
    events.emit("mqtt_publish", {"topic": topic, "payload": message})
    return {"ok": True, "topic": topic}


def validate_firmware_manifest(manifest: Any, env: str, target_id: str) -> None:
    if manifest in (None, ""):
        return
    if not isinstance(manifest, dict):
        raise RuntimeError("manifest must be a JSON object")
    manifest_env = str(manifest.get("env") or manifest.get("environment") or "").strip()
    if manifest_env and manifest_env != env:
        raise RuntimeError(f"manifest env {manifest_env} does not match selected env {env}")
    package_device_id = str(manifest.get("deviceId") or "").strip().upper()
    if package_device_id and package_device_id != "F000" and package_device_id != target_id:
        raise RuntimeError(f"manifest deviceId {package_device_id} does not match target ID {target_id}")
    chip = str(manifest.get("chipFamily") or manifest.get("chip") or "").strip()
    if chip and not re.search(r"esp32s3", chip, re.IGNORECASE):
        raise RuntimeError(f"manifest chip {chip} is not ESP32-S3")
    flash_files = manifest.get("flashFiles")
    if flash_files is not None and not isinstance(flash_files, list):
        raise RuntimeError("manifest flashFiles must be a list")


def firmware_upload(payload: dict[str, Any]) -> dict[str, Any]:
    env = str(payload.get("env") or "gld").strip()
    port = str(payload.get("port") or "").strip()
    target_id = str(payload.get("targetDeviceId") or "").strip().upper()
    if not re.match(r"^[A-Za-z0-9_\\-]+$", env):
        raise RuntimeError("invalid PlatformIO env")
    if not port:
        raise RuntimeError("port is required")
    validate_firmware_manifest(payload.get("manifest"), env, target_id)
    serial_bridge.disconnect()

    def worker() -> None:
        cmd = ["pio", "run", "-e", env, "-t", "upload", "--upload-port", port]
        events.emit("upload_start", {"cmd": " ".join(cmd), "cwd": str(FIRMWARE_DIR)})
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(FIRMWARE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                events.emit("upload_line", {"line": line.rstrip("\r\n")})
            code = proc.wait()
            events.emit("upload_done", {"code": code})
            if code == 0 and re.match(r"^[0-9A-F]{4}$", target_id) and target_id != "0000":
                time.sleep(2.5)
                serial_bridge.connect(port, 115200)
                time.sleep(1.0)
                serial_bridge.write_line(f'SET_DEVICE_ID_JSON {{"deviceId":"{target_id}","reboot":true}}')
        except Exception as exc:
            events.emit("upload_error", {"message": str(exc)})

    threading.Thread(target=worker, name="gld-firmware-upload", daemon=True).start()
    return {"started": True, "env": env, "port": port}


class Handler(SimpleHTTPRequestHandler):
    server_version = "GLDOperatorLiteBridge/0.2"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(APP_DIR), **kwargs)

    def handle(self) -> None:
        try:
            super().handle()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    def end_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin and origin in BRIDGE_ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        super().end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/health":
            return json_response(
                self,
                {
                    "ok": True,
                    "version": VERSION,
                    "features": {
                        "serial": serial is not None,
                        "mqtt": mqtt is not None,
                        "datasetMonitor": mqtt is not None,
                        "datasetOutput": True,
                        "networkInfo": os.name == "nt",
                        "firmwareUpload": True,
                    },
                    "errors": {"serial": SERIAL_IMPORT_ERROR, "mqtt": MQTT_IMPORT_ERROR},
                },
            )
        if path == "/api/ports":
            try:
                return json_response(self, {"ports": serial_bridge.list_ports()})
            except Exception as exc:
                return json_response(self, {"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
        if path == "/api/network":
            try:
                return json_response(self, network_info())
            except Exception as exc:
                return json_response(self, {"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
        if path == "/api/dataset/output-dir":
            try:
                return json_response(self, dataset_output_info())
            except Exception as exc:
                return json_response(self, {"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
        if path == "/api/events":
            return self._serve_events()
        return super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            payload = read_json(self)
            if path == "/api/serial/connect":
                result = serial_bridge.connect(str(payload.get("port") or ""), int(payload.get("baud") or 115200))
            elif path == "/api/serial/disconnect":
                result = serial_bridge.disconnect()
            elif path == "/api/serial/write":
                result = serial_bridge.write_line(str(payload.get("line") or ""), require_connected=False)
            elif path == "/api/mqtt/dataset":
                result = mqtt_publish_dataset(payload)
            elif path == "/api/mqtt/dataset-monitor/stop":
                result = dataset_monitor.stop()
            elif path == "/api/dataset/save":
                result = save_dataset_csv(payload)
            elif path == "/api/dataset/open-folder":
                result = open_dataset_folder()
            elif path == "/api/firmware/upload":
                result = firmware_upload(payload)
            else:
                return json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)
            return json_response(self, result)
        except Exception as exc:
            return json_response(self, {"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _serve_events(self) -> None:
        client = events.add()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    item = client.get(timeout=15)
                    event = item["event"]
                    data = json.dumps(item["payload"])
                    self.wfile.write(f"event: {event}\n".encode("utf-8"))
                    self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except queue.Empty:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
        except Exception:
            pass
        finally:
            events.remove(client)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=5173, type=int)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    _register_allowed_origins(args.host, args.port)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"GLD Operator Lite bridge: {url}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        dataset_monitor.stop(emit=False)
        serial_bridge.disconnect()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
