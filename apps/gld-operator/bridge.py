#!/usr/bin/env python3
"""GLD Operator Lite local bridge.

Serves the static UI and exposes native Windows features that plain browser
JavaScript cannot access: COM port listing, serial read/write, WiFi/IP lookup,
MQTT publish for dataset commands, and direct verified firmware upload.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import hmac
import json
import os
import queue
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

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

# The bundled embeddable Python distribution (python-embed/) runs with a
# python312._pth file, which - unlike a normal CPython install - does not
# auto-add the launched script's own directory to sys.path. Without this,
# `import local_mqtt_broker` fails whenever bridge.py is started via the
# embedded interpreter, even though the file sits right next to bridge.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from local_mqtt_broker import LocalMqttBroker
except Exception as exc:  # pragma: no cover - surfaced in /api/health
    LocalMqttBroker = None  # type: ignore[assignment]
    MQTT_BROKER_IMPORT_ERROR = str(exc)
else:
    MQTT_BROKER_IMPORT_ERROR = ""


APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parents[1]
FIRMWARE_DIR = REPO_ROOT / "firmware"
DATASET_OUTPUT_DIR = APP_DIR / "output" / "datasets"
SESSION_LOG_DIR = APP_DIR / "output" / "logs"

# Populated at startup from the actual --host/--port the bridge binds to.
# The documented launch path (run-gld-operator.bat) serves the static UI and
# this API from the same origin, so same-origin requests never need a CORS
# header at all; this allowlist only covers the same machine reachable via
# 127.0.0.1/localhost, never an arbitrary remote origin. Do not widen this to
# "*" - the bridge exposes serial writes, MQTT publish, firmware flashing, and
# a WiFi-password lookup, and a wildcard lets any page open in the operator's
# browser call all of that cross-origin.
BRIDGE_ALLOWED_ORIGINS: set[str] = set()
BRIDGE_CSRF_TOKEN = secrets.token_urlsafe(32)
DEFAULT_JSON_BODY_LIMIT = 2 * 1024 * 1024
FIRMWARE_JSON_BODY_LIMIT = 16 * 1024 * 1024
SAFE_PACKAGE_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")

GLD_ID_MIN = 0x1001
GLD_ID_MAX = 0xFEFF
DEFAULT_GLD_ID = "1001"


def _register_allowed_origins(host: str, port: int) -> None:
    BRIDGE_ALLOWED_ORIGINS.update(
        {
            f"http://{host}:{port}",
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
        }
    )


VERSION = "0.4.0-lite-bridge"


class RequestError(RuntimeError):
    def __init__(self, message: str, status: HTTPStatus) -> None:
        super().__init__(message)
        self.status = status


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
    def __init__(self, events: EventHub, slot: int = 1) -> None:
        self.events = events
        self.slot = slot
        self._serial: Any = None
        self._lock = threading.Lock()
        self._reader_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.port = ""
        self.baud = 115200

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        self.events.emit(event, {**payload, "slot": self.slot})

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
        if is_flash_port_reserved(port):
            raise RuntimeError(f"{port} is reserved for firmware upload; wait until the upload finishes")
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
        self._emit("serial_status", {"connected": True, "port": port, "baud": baud})
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
        self._emit("serial_status", {"connected": False})
        return {"connected": False}

    def status(self) -> dict[str, Any]:
        with self._lock:
            ser = self._serial
            return {"connected": ser is not None and getattr(ser, "is_open", False), "port": self.port, "baud": self.baud}

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
        event_line = re.sub(
            r'("(?:aesKeyHex|gldAes128KeyHex|GLD_AES128_KEY_HEX)"\s*:\s*")[^"]*(")',
            r"\1<redacted>\2",
            line.rstrip("\r\n"),
            flags=re.IGNORECASE,
        )
        self._emit("serial_tx", {"line": event_line})
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
                self._emit("serial_error", {"message": str(exc)})
                break
            if not chunk:
                continue
            pending += chunk
            while b"\n" in pending:
                raw, pending = pending.split(b"\n", 1)
                line = raw.decode("utf-8", errors="replace").strip("\r")
                if line:
                    self._emit("serial_line", {"line": line})
        self._emit("serial_status", {"connected": False})


MAX_SLOTS = 8

events = EventHub()
serial_bridges: dict[int, "SerialBridge"] = {}
flash_port_lock = threading.Lock()
flash_ports: set[str] = set()


def _flash_port_key(port: str) -> str:
    return str(port).strip().upper()


def is_flash_port_reserved(port: str) -> bool:
    with flash_port_lock:
        return _flash_port_key(port) in flash_ports


def reserve_flash_port(port: str) -> bool:
    with flash_port_lock:
        key = _flash_port_key(port)
        if key in flash_ports:
            return False
        flash_ports.add(key)
        return True


def release_flash_port(port: str) -> None:
    with flash_port_lock:
        flash_ports.discard(_flash_port_key(port))
dataset_monitors: dict[int, "DatasetMqttMonitor"] = {}
local_mqtt_broker: Any = None
local_mqtt_broker_error = ""


def parse_slot(value: Any) -> int:
    try:
        slot = int(value)
    except (TypeError, ValueError):
        return 1
    return slot if 1 <= slot <= MAX_SLOTS else 1


def get_serial_bridge(slot: int) -> "SerialBridge":
    if slot not in serial_bridges:
        serial_bridges[slot] = SerialBridge(events, slot=slot)
    return serial_bridges[slot]


def get_dataset_monitor(slot: int) -> "DatasetMqttMonitor":
    if slot not in dataset_monitors:
        dataset_monitors[slot] = DatasetMqttMonitor(events, slot=slot)
    return dataset_monitors[slot]


def connected_slots_summary() -> dict[str, Any]:
    summary = {}
    for slot, bridge in serial_bridges.items():
        status = bridge.status()
        if status["connected"]:
            summary[str(slot)] = status
    return summary


class DatasetMqttMonitor:
    def __init__(self, events: EventHub, slot: int = 1) -> None:
        self.events = events
        self.slot = slot
        self._lock = threading.Lock()
        self._client: Any = None
        self.config: dict[str, Any] = {}

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        self.events.emit(event, {**payload, "slot": self.slot})

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
            self._emit(
                "dataset_monitor",
                {"status": "subscribed", "host": host, "port": port, "deviceId": device_id, "topics": topics, "reason": str(reason_code)},
            )

        def on_message(_client_obj: Any, _userdata: Any, msg: Any) -> None:
            text = msg.payload.decode("utf-8", errors="replace")
            try:
                parsed: Any = json.loads(text)
            except Exception:
                parsed = None
            self._emit(
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
        self._emit("dataset_monitor", {"status": "started", "host": host, "port": port, "deviceId": device_id})
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
            self._emit("dataset_monitor", {"status": "stopped"})
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


def json_response(handler: SimpleHTTPRequestHandler, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler: SimpleHTTPRequestHandler, limit: int = DEFAULT_JSON_BODY_LIMIT) -> dict[str, Any]:
    content_type = handler.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise RequestError("Content-Type must be application/json", HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
    try:
        length = int(handler.headers.get("Content-Length", "0") or "0")
    except ValueError as exc:
        raise RequestError("invalid Content-Length", HTTPStatus.BAD_REQUEST) from exc
    if length <= 0:
        raise RequestError("JSON request body is required", HTTPStatus.BAD_REQUEST)
    if length > limit:
        raise RequestError(f"request body exceeds {limit} bytes", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
    raw = handler.rfile.read(length)
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RequestError("invalid JSON request body", HTTPStatus.BAD_REQUEST) from exc
    if not isinstance(parsed, dict):
        raise RequestError("JSON request body must be an object", HTTPStatus.BAD_REQUEST)
    return parsed


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


def create_dataset_csv(payload: dict[str, Any]) -> dict[str, Any]:
    header_line = str(payload.get("header") or "")
    if not header_line.strip():
        raise RuntimeError("header is required")
    filename = safe_filename(str(payload.get("filename") or "dataset.csv"))
    DATASET_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = DATASET_OUTPUT_DIR / filename
    text = header_line if header_line.endswith("\n") else header_line + "\n"
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    result = {"ok": True, "path": str(path), "filename": filename, "bytes": path.stat().st_size}
    events.emit("dataset_created", result)
    return result


def append_dataset_csv(payload: dict[str, Any]) -> dict[str, Any]:
    filename = safe_filename(str(payload.get("filename") or ""))
    lines = payload.get("lines")
    if not isinstance(lines, list) or not lines:
        raise RuntimeError("lines is required")
    DATASET_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = DATASET_OUTPUT_DIR / filename
    if not path.exists():
        raise RuntimeError(f"{filename} does not exist - call /api/dataset/create first")
    text = "".join((line if str(line).endswith("\n") else f"{line}\n") for line in lines)
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    return {"ok": True, "path": str(path), "filename": filename, "bytes": path.stat().st_size, "appended": len(lines)}


def safe_log_filename(value: str, fallback: str = "session.log") -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    name = name.strip("._")
    if not name:
        name = fallback
    if not name.lower().endswith(".log"):
        name += ".log"
    return name[:120]


def save_session_log(payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("text") or "")
    if not text.strip():
        raise RuntimeError("log text is empty")
    filename = safe_log_filename(str(payload.get("filename") or "session.log"))
    SESSION_LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSION_LOG_DIR / filename
    path.write_text(text, encoding="utf-8", newline="")
    return {"ok": True, "path": str(path), "filename": filename, "bytes": path.stat().st_size}


def open_dataset_folder() -> dict[str, Any]:
    DATASET_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(DATASET_OUTPUT_DIR))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(DATASET_OUTPUT_DIR)])
    else:
        subprocess.Popen(["xdg-open", str(DATASET_OUTPUT_DIR)])
    return {"ok": True, "path": str(DATASET_OUTPUT_DIR)}


def mqtt_publish_dataset(payload: dict[str, Any], slot: int = 1) -> dict[str, Any]:
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
    dataset_monitor = get_dataset_monitor(slot)
    dataset_payload = payload.get("dataset") or {"cmd": command}
    if command == "START_DATASET":
        dataset_monitor.start(payload)
        topic = f"{topic_root}/{device_id}/dataset"
    elif command == "SET_MODE":
        mode = str(payload.get("mode") or dataset_payload.get("mode") or "").strip()
        if not mode:
            raise RuntimeError("mode is required")
        dataset_monitor.start(payload)
        topic = f"{topic_root}/{device_id}/cmd"
        dataset_payload = {"cmd": "SET_MODE", "mode": mode}
    else:
        topic = f"{topic_root}/{device_id}/dataset"
    message = json.dumps(dataset_payload)
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


def slot_holding_port(port: str) -> int | None:
    for slot, bridge in serial_bridges.items():
        status = bridge.status()
        if status["connected"] and status["port"] == port:
            return slot
    return None


def probe_port(port: str) -> dict[str, Any]:
    if not port:
        raise RuntimeError("port is required")
    holder = slot_holding_port(port)
    if holder is not None:
        return {
            "port": port,
            "free": True,
            "lockedByApp": True,
            "message": f"Connected by this app (slot {holder}); will disconnect automatically before upload.",
        }
    if serial is None:
        raise RuntimeError(f"pyserial unavailable: {SERIAL_IMPORT_ERROR}")
    try:
        probe = serial.Serial()
        probe.port = port
        probe.timeout = 0.2
        probe.open()
        probe.close()
        return {"port": port, "free": True, "lockedByApp": False, "message": "Port opened and closed cleanly."}
    except Exception as exc:
        return {"port": port, "free": False, "lockedByApp": False, "message": str(exc)}


def wait_for_reenumerated_port(port: str, timeout_seconds: float = 6.0) -> None:
    """Wait until a USB serial device has stayed enumerated after DTR reset."""
    if list_ports is None:
        raise RuntimeError(f"pyserial unavailable: {SERIAL_IMPORT_ERROR}")
    deadline = time.monotonic() + timeout_seconds
    stable_since: float | None = None
    target = port.upper()
    while time.monotonic() < deadline:
        present = any(str(item.device).upper() == target for item in list_ports.comports())
        if present:
            stable_since = stable_since or time.monotonic()
            if time.monotonic() - stable_since >= 0.8:
                return
        else:
            stable_since = None
        time.sleep(0.15)
    raise RuntimeError(f"COM port {port} did not re-enumerate after serial disconnect; unplug/replug the GLD USB, then retry")


def mqtt_reachability(payload: dict[str, Any]) -> dict[str, Any]:
    if mqtt is None:
        raise RuntimeError(f"paho-mqtt unavailable: {MQTT_IMPORT_ERROR}")
    host = str(payload.get("host") or "127.0.0.1")
    port = int(payload.get("port") or 1884)
    username = str(payload.get("username") or "")
    password = str(payload.get("password") or "")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if username or password:
        client.username_pw_set(username, password)
    connected = threading.Event()
    connect_error: dict[str, str] = {}
    started = time.monotonic()

    def on_connect(_client: Any, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any) -> None:
        if str(reason_code).lower() != "success" and reason_code != 0:
            connect_error["message"] = str(reason_code)
        connected.set()

    client.on_connect = on_connect
    try:
        client.connect(host, port, keepalive=5)
        client.loop_start()
        ok = connected.wait(timeout=4)
        latency_ms = round((time.monotonic() - started) * 1000, 1)
        client.loop_stop()
        client.disconnect()
        if not ok:
            return {"ok": False, "host": host, "port": port, "message": "connect timeout"}
        if connect_error:
            return {"ok": False, "host": host, "port": port, "message": connect_error["message"]}
        return {"ok": True, "host": host, "port": port, "latencyMs": latency_ms}
    except Exception as exc:
        return {"ok": False, "host": host, "port": port, "message": str(exc)}


def _manifest_flash_set_sha256(flash_files: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for item in flash_files:
        digest.update(
            f"{item['path']}\0{item['offset']}\0{item['size']}\0{item['sha256']}\n".encode("ascii")
        )
    return digest.hexdigest()


def validate_firmware_package(
    manifest: Any,
    package_files: Any,
    env: str,
    target_id: str,
) -> tuple[dict[str, Any], list[tuple[dict[str, Any], bytes]]]:
    if not isinstance(manifest, dict):
        raise RuntimeError("a schema-v2 manifest JSON object is required")
    required_top = {
        "schemaVersion", "packageType", "deviceId", "boardProfile", "environment",
        "firmwareVersion", "protocolVersion", "configSchemaVersion", "chip", "baud",
        "createdAtUtc", "source", "flashSetSha256", "flashFiles",
    }
    allowed_top = required_top
    missing = sorted(required_top - set(manifest))
    unknown = sorted(set(manifest) - allowed_top)
    if missing:
        raise RuntimeError(f"manifest missing required fields: {', '.join(missing)}")
    if unknown:
        raise RuntimeError(f"manifest has unsupported schema-v2 fields: {', '.join(unknown)}")
    if manifest.get("schemaVersion") != 2:
        raise RuntimeError("manifest schemaVersion must be 2")
    if manifest.get("packageType") != "pertamina-gld-prebuilt-firmware":
        raise RuntimeError("manifest packageType is invalid")

    manifest_env = str(manifest["environment"]).strip()
    if not SAFE_PACKAGE_FILE_RE.fullmatch(manifest_env) or manifest_env != env:
        raise RuntimeError(f"manifest environment {manifest_env!r} does not match selected env {env!r}")
    package_device_id = str(manifest["deviceId"]).strip().upper()
    if package_device_id != "ANY" and (not re.fullmatch(r"[0-9A-F]{4}", package_device_id) or package_device_id != target_id):
        raise RuntimeError(f"manifest deviceId {package_device_id!r} does not match target ID {target_id!r}")
    board_profile = str(manifest["boardProfile"]).strip()
    if not board_profile or len(board_profile) > 128 or any(ord(char) < 32 for char in board_profile):
        raise RuntimeError("manifest boardProfile is invalid")
    chip = str(manifest["chip"]).strip().lower()
    if chip != "esp32s3":
        raise RuntimeError(f"manifest chip {chip!r} is not esp32s3")
    for field in ("firmwareVersion", "protocolVersion", "configSchemaVersion"):
        if not SEMVER_RE.fullmatch(str(manifest[field])):
            raise RuntimeError(f"manifest {field} is not a semantic version")
    try:
        baud = int(manifest["baud"])
    except (TypeError, ValueError) as exc:
        raise RuntimeError("manifest baud must be an integer") from exc
    if baud < 9600 or baud > 2_000_000:
        raise RuntimeError("manifest baud is outside 9600..2000000")
    if not re.fullmatch(r"\d{8}T\d{6}Z", str(manifest["createdAtUtc"])):
        raise RuntimeError("manifest createdAtUtc must use YYYYMMDDTHHMMSSZ")

    source = manifest["source"]
    required_source = {
        "gitCommit", "gitTreeState", "platformioCoreVersion", "platformioIniSha256",
        "buildCommand", "buildStartedAtUtc", "buildCompletedAtUtc",
    }
    if not isinstance(source, dict) or set(source) != required_source:
        raise RuntimeError("manifest source identity is incomplete or has unsupported fields")
    if not re.fullmatch(r"[0-9a-f]{40}", str(source["gitCommit"])):
        raise RuntimeError("manifest source.gitCommit must be a full lowercase Git SHA")
    automated_package = source["gitTreeState"] in {"build-output", "operator-hub-auto"}
    if source["gitTreeState"] != "clean" and not automated_package:
        raise RuntimeError("manifest source tree must be clean or an Operator Hub auto-package")
    if not automated_package and not SEMVER_RE.fullmatch(str(source["platformioCoreVersion"])):
        raise RuntimeError("manifest PlatformIO Core version is invalid")
    if not SHA256_RE.fullmatch(str(source["platformioIniSha256"])):
        raise RuntimeError("manifest platformio.ini SHA-256 is invalid")
    expected_build = f"pio run -e {manifest_env}" if automated_package else f"pio run -e {manifest_env} -t clean && pio run -e {manifest_env}"
    if source["buildCommand"] != expected_build:
        raise RuntimeError("manifest buildCommand does not describe the required clean build")
    for field in ("buildStartedAtUtc", "buildCompletedAtUtc"):
        if not re.fullmatch(r"\d{8}T\d{6}Z", str(source[field])):
            raise RuntimeError(f"manifest source.{field} is invalid")
    if str(source["buildCompletedAtUtc"]) < str(source["buildStartedAtUtc"]):
        raise RuntimeError("manifest build completion precedes build start")

    flash_files = manifest["flashFiles"]
    if not isinstance(flash_files, list) or not 1 <= len(flash_files) <= 16:
        raise RuntimeError("manifest flashFiles must contain 1..16 entries")
    if not isinstance(package_files, dict):
        raise RuntimeError("packageFiles must be an object containing the declared binaries")
    declared_names: set[str] = set()
    offsets: set[int] = set()
    verified: list[tuple[dict[str, Any], bytes]] = []
    total_size = 0
    for raw_item in flash_files:
        if not isinstance(raw_item, dict) or set(raw_item) != {"path", "offset", "size", "sha256"}:
            raise RuntimeError("every flashFiles entry must contain only path, offset, size, and sha256")
        name = str(raw_item["path"])
        if not SAFE_PACKAGE_FILE_RE.fullmatch(name) or Path(name).name != name or name in {".", ".."}:
            raise RuntimeError(f"unsafe firmware package path {name!r}")
        if name in declared_names:
            raise RuntimeError(f"duplicate firmware package path {name!r}")
        declared_names.add(name)
        offset_text = str(raw_item["offset"])
        if not re.fullmatch(r"0x[0-9A-F]{8}", offset_text):
            raise RuntimeError(f"flash offset {offset_text!r} must use canonical 0x00000000 form")
        offset = int(offset_text, 16)
        if offset in offsets or offset % 0x1000 != 0:
            raise RuntimeError(f"flash offset {offset_text} is duplicate or not 4 KiB aligned")
        offsets.add(offset)
        size = raw_item["size"]
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0 or size > 8 * 1024 * 1024:
            raise RuntimeError(f"invalid declared size for {name!r}")
        expected_hash = str(raw_item["sha256"])
        if not SHA256_RE.fullmatch(expected_hash):
            raise RuntimeError(f"invalid SHA-256 for {name!r}")
        encoded = package_files.get(name)
        if not isinstance(encoded, str):
            raise RuntimeError(f"package binary {name!r} is missing")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise RuntimeError(f"package binary {name!r} is not valid base64") from exc
        if len(content) != size:
            raise RuntimeError(f"package binary {name!r} size does not match manifest")
        if not hmac.compare_digest(hashlib.sha256(content).hexdigest(), expected_hash):
            raise RuntimeError(f"package binary {name!r} SHA-256 does not match manifest")
        total_size += size
        verified.append((dict(raw_item), content))
    if set(package_files) != declared_names:
        extra = sorted(set(package_files) - declared_names)
        missing_files = sorted(declared_names - set(package_files))
        raise RuntimeError(f"packageFiles mismatch; missing={missing_files}, extra={extra}")
    if total_size > 12 * 1024 * 1024:
        raise RuntimeError("firmware package exceeds the 12 MiB decoded limit")
    expected_set_hash = _manifest_flash_set_sha256(flash_files)
    if not hmac.compare_digest(str(manifest["flashSetSha256"]), expected_set_hash):
        raise RuntimeError("manifest flashSetSha256 is invalid")
    return manifest, verified


def shared_esptool_command(args: list[str]) -> list[str]:
    runner = REPO_ROOT / "apps" / "lib" / "run_esptool.py"
    if not runner.is_file():
        raise RuntimeError("shared apps/lib esptool runtime is missing")
    return [sys.executable, str(runner), *args]


def erase_verified_nvs(manifest: dict[str, Any], verified_files: list[tuple[dict[str, Any], bytes]], port: str) -> None:
    """Erase only the verified NVS partition declared by this package."""
    for item, content in verified_files:
        if item.get("path") != "partitions.bin":
            continue
        for index in range(0, len(content) - 31, 32):
            magic = int.from_bytes(content[index:index + 2], "little")
            if magic == 0xFFFF:
                break
            if magic != 0x50AA:
                continue
            if content[index + 2] != 0x01 or content[index + 3] != 0x02:
                continue
            offset = int.from_bytes(content[index + 4:index + 8], "little")
            size = int.from_bytes(content[index + 8:index + 12], "little")
            if offset % 0x1000 or size == 0 or size % 0x1000:
                raise RuntimeError("verified NVS partition has an unsafe alignment")
            cmd = shared_esptool_command([
                "--chip", str(manifest["chip"]), "--port", port, "--baud", str(manifest["baud"]),
                "erase_region", f"0x{offset:X}", f"0x{size:X}",
            ])
            events.emit("upload_line", {"line": f"Resetting verified NVS region 0x{offset:X} (+0x{size:X})"})
            proc = subprocess.Popen(cmd, cwd=str(FIRMWARE_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace")
            assert proc.stdout is not None
            for line in proc.stdout:
                events.emit("upload_line", {"line": line.rstrip("\r\n")})
            code = proc.wait()
            if code != 0:
                raise RuntimeError(f"esptool NVS reset failed with exit code {code}")
            return
    raise RuntimeError("verified package does not declare an NVS partition")


def _firmware_upload_reserved(payload: dict[str, Any], slot: int = 1) -> dict[str, Any]:
    env = str(payload.get("env") or "").strip()
    port = str(payload.get("port") or "").strip()
    target_id = str(payload.get("targetDeviceId") or "").strip().upper()
    reset_nvs = bool(payload.get("resetNvs"))
    if not re.match(r"^[A-Za-z0-9_\\-]+$", env):
        raise RuntimeError("invalid firmware environment")
    if not re.fullmatch(r"COM\d+", port, re.IGNORECASE):
        raise RuntimeError("port must be a Windows COM port such as COM10")
    if not re.fullmatch(r"[0-9A-F]{4}", target_id) or not (GLD_ID_MIN <= int(target_id, 16) <= GLD_ID_MAX):
        raise RuntimeError("targetDeviceId must be a GLD ID in 1001-FEFF")
    manifest, verified_files = validate_firmware_package(
        payload.get("manifest"), payload.get("packageFiles"), env, target_id
    )
    holder = slot_holding_port(port)
    upload_bridge = get_serial_bridge(holder if holder is not None else slot)
    upload_bridge.disconnect()
    if not bool(payload.get("skipPreflight")):
        time.sleep(0.3)
        preflight = probe_port(port)
        if not preflight["free"]:
            raise RuntimeError(
                f"COM port {port} is still busy after disconnect ({preflight['message']}). "
                "Close other serial monitors, unplug/replug the GLD USB, then retry."
            )
        events.emit("upload_line", {"line": f"Waiting for {port} to stabilize after serial disconnect..."})
        wait_for_reenumerated_port(port)

    with tempfile.TemporaryDirectory(prefix="gld-verified-flash-") as temp_name:
        temp_dir = Path(temp_name)
        esptool_args = [
            "--chip", str(manifest["chip"]), "--port", port,
            "--baud", str(manifest["baud"]), "write_flash",
        ]
        for item, content in verified_files:
            target = temp_dir / item["path"]
            target.write_bytes(content)
            esptool_args.extend([item["offset"], str(target)])
        cmd = shared_esptool_command(esptool_args)
        events.emit("upload_start", {
            "cmd": f"verified shared esptool flash ({len(verified_files)} files)",
            "firmwareVersion": manifest["firmwareVersion"],
            "gitCommit": manifest["source"]["gitCommit"],
        })
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
    if code != 0:
        message = f"esptool flash failed with exit code {code}"
        events.emit("upload_error", {"message": message})
        raise RuntimeError(message)
    events.emit("upload_done", {"code": code})

    if reset_nvs:
        erase_verified_nvs(manifest, verified_files, port)

    return {
        "ok": True,
        "env": env,
        "port": port,
        "firmwareVersion": manifest["firmwareVersion"],
        "protocolVersion": manifest["protocolVersion"],
        "gitCommit": manifest["source"]["gitCommit"],
        "verifiedFiles": len(verified_files),
        "nvsReset": reset_nvs,
    }


def firmware_upload(payload: dict[str, Any], slot: int = 1) -> dict[str, Any]:
    port = str(payload.get("port") or "").strip()
    if not reserve_flash_port(port):
        raise RuntimeError(f"COM port {port} already has an active firmware upload")
    try:
        return _firmware_upload_reserved(payload, slot)
    finally:
        release_flash_port(port)


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
        if not urlparse(self.path).path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        if origin and origin in BRIDGE_ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-GLD-Bridge-Token")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin", "")
        return not origin or origin in BRIDGE_ALLOWED_ORIGINS

    def _token_allowed(self, path: str) -> bool:
        supplied = self.headers.get("X-GLD-Bridge-Token", "")
        if path == "/api/events" and not supplied:
            supplied = (parse_qs(urlparse(self.path).query).get("token") or [""])[0]
        return bool(supplied) and hmac.compare_digest(supplied, BRIDGE_CSRF_TOKEN)

    def _require_api_access(self, path: str, allow_public_health: bool = False) -> None:
        if not self._origin_allowed():
            raise RequestError("request origin is not allowed", HTTPStatus.FORBIDDEN)
        if not (allow_public_health and path == "/api/health") and not self._token_allowed(path):
            raise RequestError("bridge token is missing or invalid", HTTPStatus.FORBIDDEN)

    def _request_error(self, exc: Exception) -> None:
        status = exc.status if isinstance(exc, RequestError) else HTTPStatus.INTERNAL_SERVER_ERROR
        json_response(self, {"error": str(exc)}, status)

    def do_OPTIONS(self) -> None:  # noqa: N802
        if not self._origin_allowed():
            return json_response(self, {"error": "request origin is not allowed"}, HTTPStatus.FORBIDDEN)
        requested_headers = {
            item.strip().lower()
            for item in self.headers.get("Access-Control-Request-Headers", "").split(",")
            if item.strip()
        }
        if not requested_headers.issubset({"content-type", "x-gld-bridge-token"}):
            return json_response(self, {"error": "requested CORS headers are not allowed"}, HTTPStatus.FORBIDDEN)
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/"):
                self._require_api_access(path, allow_public_health=True)
            if path == "/api/health":
                broker_running = bool(local_mqtt_broker and local_mqtt_broker.running)
                return json_response(
                    self,
                    {
                    "ok": True,
                    "version": VERSION,
                    "csrfToken": BRIDGE_CSRF_TOKEN,
                    "features": {
                        "serial": serial is not None,
                        "mqtt": mqtt is not None,
                        "datasetMonitor": mqtt is not None,
                        "mqttBroker": broker_running,
                        "datasetOutput": True,
                        "networkInfo": os.name == "nt",
                        "firmwareUpload": True,
                    },
                    "mqttBroker": {
                        "running": broker_running,
                        "host": getattr(local_mqtt_broker, "host", ""),
                        "port": getattr(local_mqtt_broker, "port", 0),
                        "authRequired": bool(getattr(local_mqtt_broker, "username", None)),
                    },
                    "errors": {
                        "serial": SERIAL_IMPORT_ERROR,
                        "mqtt": MQTT_IMPORT_ERROR,
                        "mqttBroker": local_mqtt_broker_error or MQTT_BROKER_IMPORT_ERROR,
                    },
                    "maxSlots": MAX_SLOTS,
                    "slots": connected_slots_summary(),
                    },
                )
            if path == "/api/ports":
                return json_response(self, {"ports": get_serial_bridge(1).list_ports()})
            if path == "/api/firmware/package":
                package_env = (parse_qs(urlparse(self.path).query).get("env") or [""])[0]
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", package_env):
                    raise RuntimeError("invalid firmware environment")
                package_dir = REPO_ROOT / "apps" / "operator-hub" / "firmware-packages" / package_env / "latest"
                manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
                package_files = {str(item["path"]): base64.b64encode((package_dir / str(item["path"])).read_bytes()).decode("ascii") for item in manifest["flashFiles"]}
                return json_response(self, {"manifest": manifest, "packageFiles": package_files})
            if path == "/api/network":
                return json_response(self, network_info())
            if path == "/api/dataset/output-dir":
                return json_response(self, dataset_output_info())
            if path == "/api/serial/port-status":
                query = parse_qs(urlparse(self.path).query)
                port = (query.get("port") or [""])[0]
                return json_response(self, probe_port(port))
            if path == "/api/events":
                return self._serve_events()
            return super().do_GET()
        except Exception as exc:
            return self._request_error(exc)

    def do_POST(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            if not path.startswith("/api/"):
                raise RequestError("not found", HTTPStatus.NOT_FOUND)
            self._require_api_access(path)
            limit = FIRMWARE_JSON_BODY_LIMIT if path == "/api/firmware/upload" else DEFAULT_JSON_BODY_LIMIT
            payload = read_json(self, limit)
            slot = parse_slot(payload.get("slot"))
            if path == "/api/serial/connect":
                port = str(payload.get("port") or "")
                holder = slot_holding_port(port)
                if holder is not None and holder != slot:
                    raise RuntimeError(f"{port} is already connected on slot {holder}")
                result = get_serial_bridge(slot).connect(port, int(payload.get("baud") or 115200))
            elif path == "/api/serial/disconnect":
                result = get_serial_bridge(slot).disconnect()
            elif path == "/api/serial/write":
                result = get_serial_bridge(slot).write_line(str(payload.get("line") or ""), require_connected=False)
            elif path == "/api/mqtt/dataset":
                result = mqtt_publish_dataset(payload, slot)
            elif path == "/api/mqtt/dataset-monitor/stop":
                result = get_dataset_monitor(slot).stop()
            elif path == "/api/mqtt/test":
                result = mqtt_reachability(payload)
            elif path == "/api/dataset/save":
                result = save_dataset_csv(payload)
            elif path == "/api/dataset/create":
                result = create_dataset_csv(payload)
            elif path == "/api/dataset/append":
                result = append_dataset_csv(payload)
            elif path == "/api/session/log":
                result = save_session_log(payload)
            elif path == "/api/dataset/open-folder":
                result = open_dataset_folder()
            elif path == "/api/firmware/upload":
                result = firmware_upload(payload, slot)
            else:
                return json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)
            return json_response(self, result)
        except Exception as exc:
            return self._request_error(exc)

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
    global local_mqtt_broker, local_mqtt_broker_error
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=5174, type=int)
    parser.add_argument("--mqtt-broker-host", default="127.0.0.1")
    parser.add_argument("--mqtt-broker-port", default=0, type=int)
    parser.add_argument("--mqtt-broker-user", default=os.environ.get("GLD_BENCH_MQTT_USER", ""))
    parser.add_argument("--mqtt-broker-password", default=os.environ.get("GLD_BENCH_MQTT_PASSWORD", ""))
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    _register_allowed_origins(args.host, args.port)
    if args.mqtt_broker_port:
        if LocalMqttBroker is None:
            local_mqtt_broker_error = f"local MQTT broker unavailable: {MQTT_BROKER_IMPORT_ERROR}"
            print(local_mqtt_broker_error)
        else:
            try:
                local_mqtt_broker = LocalMqttBroker(
                    args.mqtt_broker_host,
                    args.mqtt_broker_port,
                    username=args.mqtt_broker_user or None,
                    password=args.mqtt_broker_password or None,
                )
                local_mqtt_broker.start()
            except Exception as exc:
                local_mqtt_broker = None
                local_mqtt_broker_error = str(exc)
                print(f"MQTT_BROKER_START_FAILED {local_mqtt_broker_error}")
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"GLD Operator Lite bridge: {url}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for monitor in dataset_monitors.values():
            monitor.stop(emit=False)
        for bridge in serial_bridges.values():
            bridge.disconnect()
        if local_mqtt_broker is not None:
            local_mqtt_broker.stop()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
