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
from collections import deque
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
from telemetry_polling import BackgroundTelemetryPoller, SerialPollGate, TelemetryReplayBuffer, expected_response, response_kind

try:
    from wireless_dataset import WirelessDatasetCollector
except Exception as exc:  # Optional feature must never block existing consoles.
    WirelessDatasetCollector = None  # type: ignore[assignment]
    WIRELESS_DATASET_IMPORT_ERROR = type(exc).__name__
else:
    WIRELESS_DATASET_IMPORT_ERROR = ""

try:
    from wireless_dataset_direct import WirelessDatasetDirectCollector
except Exception:  # Keep legacy recording available in older/partial installations.
    WirelessDatasetDirectCollector = None  # type: ignore[assignment]

try:
    from wireless_dataset_replay import WirelessDatasetReplayCollector as WirelessReplayCollector
except Exception as exc:  # Replay is optional; Stage1 and other consoles stay available.
    WirelessReplayCollector = None  # type: ignore[assignment]
    WIRELESS_REPLAY_IMPORT_ERROR = type(exc).__name__
else:
    WIRELESS_REPLAY_IMPORT_ERROR = ""

try:
    from dataset_workflow import DatasetWorkflowService
    from workflow_platform import WindowsWorkflowPlatform
except Exception as exc:
    DatasetWorkflowService = WindowsWorkflowPlatform = None
    WORKFLOW_IMPORT_ERROR = type(exc).__name__
else:
    WORKFLOW_IMPORT_ERROR = ""

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
FIRMWARE_UPLOAD_TOTAL_TIMEOUT_SEC = 120.0
FIRMWARE_UPLOAD_IDLE_TIMEOUT_SEC = 30.0
DATASET_OUTPUT_DIR = APP_DIR / "output" / "datasets"
SESSION_LOG_DIR = APP_DIR / "output" / "logs"
# Node-RED's decoder is the source of truth for which AES key/keyId GLD
# uplinks must be encrypted with (see server/nodered/.env.example). Reading
# it here lets every SET_APP_CONFIG_JSON push provision a device with the
# same key automatically, instead of relying on someone re-typing it and the
# two sides silently drifting apart.
NODERED_ENV_PATH = REPO_ROOT / "server" / "nodered" / ".env"

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
GLD_DATASET_WIFI_ENVIRONMENTS = frozenset({
    "gld_model_1_dataset_wifi", "gld_model_2_dataset_wifi", "gld_model_3_dataset_wifi",
})
GLD_DATASET_REPLAY_ENVIRONMENTS = frozenset({
    "gld_model_1_dataset_replay_wifi", "gld_model_2_dataset_replay_wifi", "gld_model_3_dataset_replay_wifi",
})
ATEX_WORKFLOW_MODELS = {f"gld_atex_model_{model}_dataset_workflow_wifi": model for model in (1, 2, 3)}
# The known legacy ATEX image lacks an ATEX runtime marker. This narrow deny
# catches an accidental env/manifest relabel; hashes are not authentication.
ATEX_KNOWN_BLOCKED_FIRMWARE_SHA256 = frozenset({
    "10391c34a922c7b07026648dbd25749fd1adda8218ef25fedca327a674bb03a0",
})
GLD_DATASET_WORKFLOW_ENVIRONMENTS = (frozenset(f"gld_model_{model}_dataset_workflow_wifi" for model in (1, 2, 3))
                                     | frozenset(ATEX_WORKFLOW_MODELS))
AES_KEY_HEX_RE = re.compile(r"^[0-9A-Fa-f]{32}$")


def load_canonical_gld_aes_key() -> dict[str, Any] | None:
    """Read the AES key/keyId from server/nodered/.env, or None if it isn't
    configured there yet. This intentionally never falls back to the public
    self-test vector - an unconfigured Node-RED side means nothing gets
    auto-provisioned, rather than silently provisioning a known-public key."""
    if not NODERED_ENV_PATH.is_file():
        return None
    values: dict[str, str] = {}
    try:
        for raw_line in NODERED_ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    except OSError:
        return None
    key_hex = values.get("GLD_AES128_KEY_HEX", "")
    key_id_raw = values.get("GLD_KEY_ID", "")
    if not AES_KEY_HEX_RE.match(key_hex) or not key_id_raw.isdigit():
        return None
    key_id = int(key_id_raw)
    if not (1 <= key_id <= 255):
        return None
    return {"aesKeyHex": key_hex.upper(), "keyId": key_id}


def inject_canonical_aes_key(line: str) -> tuple[str, bool]:
    """Auto-fill aesKeyHex/keyId on an outgoing SET_APP_CONFIG_JSON command
    from server/nodered/.env, so every config push provisions the device with
    the same key Node-RED's decoder expects - the operator never has to type
    or paste it, and the two sides can't silently drift apart. A caller that
    already set a key explicitly is left untouched."""
    prefix = "SET_APP_CONFIG_JSON "
    if not line.startswith(prefix):
        return line, False
    canonical = load_canonical_gld_aes_key()
    if canonical is None:
        return line, False
    try:
        body = json.loads(line[len(prefix):])
    except (ValueError, TypeError):
        return line, False
    if not isinstance(body, dict):
        return line, False
    if any(body.get(k) for k in ("aesKeyHex", "gldAes128KeyHex", "GLD_AES128_KEY_HEX")):
        return line, False
    body["aesKeyHex"] = canonical["aesKeyHex"]
    body.setdefault("keyId", canonical["keyId"])
    return prefix + json.dumps(body), True


def _register_allowed_origins(host: str, port: int) -> None:
    BRIDGE_ALLOWED_ORIGINS.update(
        {
            f"http://{host}:{port}",
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
        }
    )


VERSION = "0.4.0-lite-bridge"
APP_ID = "gld-operator"


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

    def registered(self, client: queue.Queue[dict[str, Any]]) -> bool:
        with self._lock:
            return client in self._clients

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
        self._reader_stop = threading.Event()
        # Each COM connection owns an immutable serial handle, stop event, and
        # generation.  A stale reader must never report a newly reconnected
        # port as disconnected.
        self._generation = 0
        # A complete eight-channel Nulling trace contains several thousand
        # samples. Retain enough history for the Operator Details export after
        # the board reboots back to Inference.
        self._recent_lines: deque[dict[str, Any]] = deque(maxlen=6000)
        self._line_sequence = 0
        self._poll_lock = threading.Lock()
        self._poll_condition = threading.Condition(self._poll_lock)
        # Only ATEX nonce verification uses this state. Ordinary GLD1 writes
        # retain their existing poll-gate behavior when no challenge is active.
        self._atex_identity_state_lock = threading.Lock()
        # Covers an entire open/install/reader-start or disconnect transaction.
        # Reentrant because connect deliberately disconnects its previous handle.
        self._atex_connection_lock = threading.RLock()
        self._atex_identity_active = False
        self._atex_identity_unknown_stream: str | None = None
        self._atex_command_writers = 0
        self._priority_pending = threading.Event()
        self._priority_state_lock = threading.Lock()
        self._priority_count = 0
        self._poll_gate = SerialPollGate()
        self._poll_enabled = False
        self._poll_version = 0
        self._passive_responses: list[str] = []
        self._passive_overflow = False
        self._late_poll_unknown = False
        self._cancelled_poll_owners: deque[str] = deque(maxlen=128)
        self._telemetry_stream = secrets.token_hex(16)
        self._telemetry_buffer = TelemetryReplayBuffer()
        self._poller = BackgroundTelemetryPoller(
            self._poll_gate, self._send_raw,
            self._background_poll_error,
        )
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
        # Register before waiting for another connect, so a queued replacement
        # cannot sneak in after an ATEX identity challenge has acquired its lease.
        _begin_port_operation(port)
        try:
            self._enter_regular_serial_operation(allow_unknown=True)
            try:
                with self._atex_connection_lock:
                    return self._connect_ordinary(port, baud)
            finally:
                self._exit_regular_serial_operation()
        finally:
            _end_port_operation(port)

    def _connect_ordinary(self, port: str, baud: int = 115200) -> dict[str, Any]:
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
            self._generation += 1
            generation = self._generation
            self._reader_stop = threading.Event()
            stop_event = self._reader_stop
            self._telemetry_stream = secrets.token_hex(16)
            self._telemetry_buffer = TelemetryReplayBuffer()
        self._reader_thread = threading.Thread(
            target=self._read_loop,
            args=(ser, stop_event, generation),
            name="gld-serial-reader",
            daemon=True,
        )
        self._reader_thread.start()
        self._emit("serial_status", {"connected": True, "port": port, "baud": baud})
        return {"connected": True, "port": port, "baud": baud}

    def disconnect(self, *, _atex_identity_guard: tuple[str, str, int, str] | None = None) -> dict[str, Any]:
        owner = _atex_identity_guard is not None
        if owner:
            with self._atex_identity_state_lock:
                if not self._atex_identity_active:
                    raise RuntimeError("ATEX identity lease is not active")
        else:
            self._enter_regular_serial_operation(allow_unknown=True)
        try:
            with self._atex_connection_lock:
                return self._disconnect_ordinary(_atex_identity_guard)
        finally:
            if not owner:
                self._exit_regular_serial_operation()

    def _disconnect_ordinary(self, _atex_identity_guard: tuple[str, str, int, str] | None) -> dict[str, Any]:
        if _atex_identity_guard is None:
            self._poller.stop_for_disconnect()
        reader: threading.Thread | None
        with self._poll_lock:
            if _atex_identity_guard is not None:
                expected_stream, expected_port, expected_epoch, expected_pending = _atex_identity_guard
                if (self._poll_gate.epoch() != expected_epoch or
                        self._poll_gate.pending_response() != expected_pending):
                    raise RuntimeError("ATEX upload held: serial ownership changed before disconnect")
            # Check stream and detach that exact handle in one critical section;
            # do not release the serial lock between verification and detach.
            with self._lock:
                if _atex_identity_guard is not None and (
                        self._serial is None or not getattr(self._serial, "is_open", False) or
                        self.port.upper() != expected_port.upper() or self._telemetry_stream != expected_stream):
                    raise RuntimeError("ATEX upload held: serial connection changed before disconnect")
                ser = self._serial
                self._serial = None
                self._generation += 1
                self._reader_stop.set()
                reader = self._reader_thread
                self._reader_thread = None
            if _atex_identity_guard is not None:
                # Sentinel still owns the poll gate, so no new polling write
                # can begin between verified detach and this stop request.
                self._poller.stop_for_disconnect()
            self._poll_gate.reset()
            self._poll_enabled = False
            self._poll_version += 1
            self._passive_responses.clear()
            self._passive_overflow = False
            self._late_poll_unknown = False
            self._poll_condition.notify_all()
        self._poller.join(1.0)
        close_error = None
        if ser is not None:
            try:
                ser.close()
            except Exception as exc:
                close_error = exc
        # Serial reads use a short timeout, so this normally returns within
        # 200 ms.  Waiting here prevents an old loop from racing a reconnect.
        if reader is not None and reader is not threading.current_thread():
            reader.join(timeout=1.0)
        self._emit("serial_status", {"connected": False})
        if _atex_identity_guard is not None and (close_error is not None or ser is None or getattr(ser, "is_open", True)):
            raise RuntimeError("ATEX upload held: verified serial handle did not close") from close_error
        return {"connected": False}

    def status(self) -> dict[str, Any]:
        with self._lock:
            ser = self._serial
            return {"connected": ser is not None and getattr(ser, "is_open", False), "port": self.port, "baud": self.baud,
                    "telemetryStream": self._telemetry_stream}

    def recent_lines(self, after: int = 0) -> dict[str, Any]:
        with self._lock:
            return {"sequence": self._line_sequence, "lines": [item for item in self._recent_lines if item["sequence"] > after]}

    def challenge_atex_identity(self, port: str, target_id: str, timeout: float = 8.0, *, keep_connected: bool = False) -> dict[str, Any] | None:
        """Verify nonce identity on one exclusive serial lease.

        A failed or ambiguous sent command quarantines that stream; no retry is
        attempted. This is a software identity response, not hardware attestation.
        """
        if not isinstance(port, str) or not re.fullmatch(r"COM\d+", port, re.IGNORECASE):
            raise RuntimeError("ATEX upload held: invalid serial port")
        if not isinstance(target_id, str) or not re.fullmatch(r"[0-9A-F]{4}", target_id) or not GLD_ID_MIN <= int(target_id, 16) <= GLD_ID_MAX:
            raise RuntimeError("ATEX upload held: invalid device identity")
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < timeout <= 30:
            raise RuntimeError("ATEX upload held: invalid identity timeout")
        nonce = secrets.token_hex(16)
        with self._atex_identity_state_lock:
            if self._atex_identity_active or self._atex_command_writers:
                raise RuntimeError("ATEX upload held: another serial command is active")
            self._atex_identity_active = True
        guard_name = "ATEX_IDENTITY_GUARD_" + nonce.upper()
        guard_expected = "ack:" + guard_name
        guard_token = None
        stream = None
        sent = False
        completed = False
        try:
            with self._poll_lock:
                with self._lock:
                    initial_handle = self._serial
                    initial_generation = self._generation
                    initial = {"connected": initial_handle is not None and getattr(initial_handle, "is_open", False),
                               "port": self.port, "telemetryStream": self._telemetry_stream}
                stream = initial.get("telemetryStream")
                if (not initial.get("connected") or str(initial.get("port") or "").upper() != port.upper() or
                        not isinstance(stream, str) or not stream):
                    raise RuntimeError("ATEX upload held: connect the selected port and identify the board")
                with self._atex_identity_state_lock:
                    if self._atex_identity_unknown_stream == stream:
                        raise RuntimeError("ATEX upload held: previous identity outcome unknown; reconnect")
                if (self._passive_responses or self._passive_overflow or self._late_poll_unknown or
                        self._priority_pending.is_set()):
                    raise RuntimeError("ATEX upload held: serial command response is unresolved")
                guard_token = self._poll_gate.reserve(guard_name)
                if guard_token is None:
                    raise RuntimeError("ATEX upload held: serial request gate is busy or quarantined")
                epoch = self._poll_gate.epoch()
                cursor = self.recent_lines().get("sequence")
                if type(cursor) is not int or cursor < 0:
                    raise RuntimeError("ATEX upload held: serial sequence unavailable")
                command = "GET_ATEX_IDENTITY_JSON " + json.dumps({"nonce": nonce}, separators=(",", ":"))
                # A write error may occur after bytes left the process.
                sent = True
                self._send_raw(command)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                current = self.status()
                if (not current.get("connected") or str(current.get("port") or "").upper() != port.upper() or
                        current.get("telemetryStream") != stream or self._poll_gate.epoch() != epoch or
                        self._poll_gate.pending_response() != guard_expected):
                    raise RuntimeError("ATEX upload held: serial connection or ownership changed")
                recent = self.recent_lines(after=cursor)
                lines = recent.get("lines")
                if not isinstance(lines, list):
                    raise RuntimeError("ATEX upload held: invalid serial history")
                matches = []
                for item in lines:
                    if not isinstance(item, dict) or type(item.get("sequence")) is not int or item["sequence"] != cursor + 1:
                        raise RuntimeError("ATEX upload held: serial history incomplete or out of order")
                    cursor = item["sequence"]
                    line = str(item.get("line") or "")
                    if not line.startswith("GLD_ATEX_IDENTITY_JSON "):
                        continue
                    try:
                        info = json.loads(line[len("GLD_ATEX_IDENTITY_JSON "):])
                    except (TypeError, ValueError) as exc:
                        raise RuntimeError("ATEX upload held: invalid identity response") from exc
                    if not isinstance(info, dict) or not isinstance(info.get("nonce"), str):
                        raise RuntimeError("ATEX upload held: invalid identity response")
                    if info["nonce"] == nonce:
                        matches.append(info)
                if len(matches) > 1:
                    raise RuntimeError("ATEX upload held: duplicate identity response")
                if matches:
                    info = matches[0]
                    model_profile = info.get("modelProfileId")
                    version = info.get("firmwareVersion")
                    if (set(info) != {"nonce", "boardProfile", "deviceId", "modelProfileId", "firmwareVersion"} or
                            not isinstance(version, str) or not version.strip() or
                            info.get("boardProfile") != "GLD ATEX MotherBoardGLDVer2" or
                            str(info.get("deviceId") or "").upper() != target_id or
                            not isinstance(model_profile, str) or
                            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/()+ -]{0,127}", model_profile) is None):
                        raise RuntimeError("ATEX upload held: board profile or device identity mismatch")
                    if keep_connected:
                        # Check the exact handle, generation and sentinel as one
                        # transaction before releasing the identity lease.
                        with self._poll_lock:
                            with self._lock:
                                if (self._serial is not initial_handle or
                                        initial_handle is None or not getattr(initial_handle, "is_open", False) or
                                        self._generation != initial_generation or self._telemetry_stream != stream or
                                        self.port.upper() != port.upper() or self._poll_gate.epoch() != epoch or
                                        self._poll_gate.pending_response() != guard_expected):
                                    raise RuntimeError("ATEX identity held: serial ownership changed before completion")
                                if not self._poll_gate.cancel_unsent(guard_token):
                                    raise RuntimeError("ATEX identity held: serial request gate changed")
                                guard_token = None
                                completed = True
                                return {"ok": True, "identity": info, "telemetryStream": stream}
                    # Preflash disconnect rechecks stream and guard atomically.
                    self.disconnect(_atex_identity_guard=(stream, port, epoch, guard_expected))
                    completed = True
                    guard_token = None  # disconnect reset the sentinel gate.
                    return None
                time.sleep(0.05)
            raise RuntimeError("ATEX upload held: nonce identity response timed out")
        finally:
            with self._poll_lock:
                if guard_token is not None:
                    if sent:
                        self._poll_gate.fail(guard_token)
                        self._passive_overflow = True
                    else:
                        self._poll_gate.cancel_unsent(guard_token)
                with self._atex_identity_state_lock:
                    if sent and not completed and stream:
                        self._atex_identity_unknown_stream = stream
                    self._atex_identity_active = False

    def telemetry_replay(self, cursor: int, stream: str) -> dict[str, Any]:
        with self._lock:
            current_stream = self._telemetry_stream
            buffer = self._telemetry_buffer
        changed = bool(stream and stream != current_stream)
        result = buffer.after(0 if changed else cursor)
        return {**result, "stream": current_stream, "streamChanged": changed}

    def _record_line(self, line: str, generation: int | None = None, serial_handle: Any = None) -> dict[str, Any] | None:
        received_ms = int(time.time() * 1000)
        kind = response_kind(line)
        # A stale reader must not satisfy a request or append telemetry to a
        # newly connected serial stream.
        with self._lock:
            if generation is not None and (self._generation != generation or self._serial is not serial_handle):
                return None
            self._poll_gate.observe(line)
            self._line_sequence += 1
            self._recent_lines.append({"sequence": self._line_sequence, "line": line})
            stream, buffer = self._telemetry_stream, self._telemetry_buffer
        with self._poll_lock:
            if kind == "telemetry":
                self._late_poll_unknown = False
            if kind in self._passive_responses:
                self._passive_responses.remove(kind)
                self._poll_condition.notify_all()
        if kind == "telemetry":
            return {"telemetrySequence": buffer.append(line, received_ms),
                    "receivedMs": received_ms, "telemetryStream": stream}
        return {}

    def start_background_poll(self, owner: str, interval_ms: int, stream: str) -> dict[str, Any]:
        self._enter_regular_serial_operation()
        try:
            return self._start_background_poll_ordinary(owner, interval_ms, stream)
        finally:
            self._exit_regular_serial_operation()

    def _start_background_poll_ordinary(self, owner: str, interval_ms: int, stream: str) -> dict[str, Any]:
        with self._poll_lock:
            deadline = time.monotonic() + 5.0
            while True:
                if owner in self._cancelled_poll_owners:
                    raise RuntimeError("polling request was already stopped")
                status = self.status()
                if not status["connected"]:
                    raise RuntimeError("serial port is not connected")
                if not stream or stream != status["telemetryStream"]:
                    raise RuntimeError("serial connection changed before polling started")
                if self._passive_overflow:
                    raise RuntimeError("serial command state is unknown; reconnect before polling")
                if not self._passive_responses:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError("serial command is still awaiting a response")
                self._poll_condition.wait(remaining)
            if not self._poll_enabled:
                self._poll_gate.reset()
            started = self._poller.start(owner, interval_ms)
            self._poll_enabled = True
            if started:
                self._poll_version += 1
            return {"ok": True, "started": started}

    def stop_background_poll(self, owner: str) -> dict[str, Any]:
        self._enter_regular_serial_operation()
        try:
            return self._stop_background_poll_ordinary(owner)
        finally:
            self._exit_regular_serial_operation()

    def _stop_background_poll_ordinary(self, owner: str) -> dict[str, Any]:
        with self._poll_lock:
            if not isinstance(owner, str) or not 16 <= len(owner) <= 128:
                raise ValueError("invalid polling owner")
            version = self._poll_version
            self._poller.stop(owner)
            self._cancelled_poll_owners.append(owner)
            self._poll_condition.notify_all()
        if not self._poller.join(6.0) or not self._poll_gate.is_idle():
            # Do not release an unrelated operator command merely because a
            # polling owner stopped; its response may still be in flight.
            if self._poll_gate.pending_response() == "telemetry":
                self._disable_background_poll("poll response unresolved; polling stopped", expected_version=version)
            raise RuntimeError("poll response unresolved; reconnect serial before retrying")
        with self._poll_lock:
            if self._poll_version == version:
                self._poll_enabled = False
        return {"ok": True}

    def _disable_background_poll(self, message: str, expected_epoch: int | None = None,
                                 expected_version: int | None = None) -> None:
        with self._poll_lock:
            if expected_epoch is not None and (not self._poll_enabled or self._poll_gate.epoch() != expected_epoch):
                return
            if expected_version is not None and self._poll_version != expected_version:
                return
            pending = self._poll_gate.pending_response()
            self._poller.stop_for_disconnect()
            self._poll_enabled = False
            self._poll_version += 1
            self._passive_overflow = True  # Explicit reconnect required for another background poll.
            self._late_poll_unknown = pending == "telemetry"
            self._poll_gate.reset()
        self._emit("telemetry_poll_error", {"message": message})

    def _background_poll_error(self, message: str) -> None:
        self._disable_background_poll(message)

    def _watch_external_poll_gate(self, token: int, command: str, epoch: int) -> None:
        timeout = 15.0 if command == "RUN_CURRENT_STATE_CHECK" else 5.0
        if not self._poll_gate.wait_response(token, timeout):
            self._disable_background_poll("serial response unresolved; polling stopped", expected_epoch=epoch)

    def _enter_regular_serial_operation(self, *, allow_unknown: bool = False) -> None:
        with self._atex_identity_state_lock:
            if self._atex_identity_active:
                raise RuntimeError("ATEX identity challenge owns serial")
            with self._lock:
                current_stream = self._telemetry_stream
            if not allow_unknown and self._atex_identity_unknown_stream == current_stream:
                raise RuntimeError("ATEX identity result unknown; reconnect before serial commands")
            self._atex_command_writers += 1

    def _exit_regular_serial_operation(self) -> None:
        with self._atex_identity_state_lock:
            self._atex_command_writers -= 1

    def write_line(self, line: str, require_connected: bool = True) -> dict[str, Any]:
        self._enter_regular_serial_operation()
        try:
            return self._write_line_ordinary(line, require_connected)
        finally:
            self._exit_regular_serial_operation()

    def _write_line_ordinary(self, line: str, require_connected: bool = True) -> dict[str, Any]:
        command = line.strip().split(maxsplit=1)[0].upper() if line.strip() else ""
        priority = command in {"RESTART", "CANCEL_FULLSCALE_SWEEP"}
        preempted_telemetry = False
        if priority:
            with self._priority_state_lock:
                self._priority_count += 1
                self._priority_pending.set()
        try:
            if priority and self._poll_enabled:
                self._poller.stop_for_disconnect()
                preempted_telemetry = self._poll_gate.pending_response() == "telemetry"
                # Wake an operator request waiting on the poll gate before
                # taking the lock it holds. The firmware treats this command
                # as an explicit high-priority recovery action.
                self._poll_gate.reset()
            with self._poll_lock:
                if not priority and self._priority_pending.is_set():
                    raise RuntimeError("priority serial command is in progress")
                if self._poll_enabled and priority:
                    self._poller.stop_for_disconnect()
                    self._late_poll_unknown = preempted_telemetry or self._poll_gate.pending_response() == "telemetry"
                    self._passive_overflow = True
                    self._poll_gate.reset()
                    self._poll_enabled = False
                    self._poll_version += 1
                token = None
                passive_added = False
                if self._late_poll_unknown and command == "GET_TELEMETRY":
                    raise RuntimeError("previous telemetry response is unresolved")
                if self._poll_enabled:
                    token = self._poll_gate.reserve(line, 5.0)
                    if token is None:
                        raise RuntimeError("serial request unresolved; polling paused")
                    token_epoch = self._poll_gate.epoch()
                else:
                    if len(self._passive_responses) < 64:
                        self._passive_responses.append(expected_response(line))
                        passive_added = True
                    else:
                        self._passive_overflow = True
                try:
                    result = self._send_raw(line, require_connected)
                except Exception:
                    if token is not None:
                        self._poll_gate.fail(token)
                    elif passive_added:
                        self._passive_responses.pop()
                    raise
                if not result.get("ok"):
                    if token is not None:
                        self._poll_gate.fail(token)
                    elif passive_added:
                        self._passive_responses.pop()
                elif token is not None:
                    threading.Thread(target=self._watch_external_poll_gate, args=(token, command, token_epoch),
                                     name="gld-poll-command-watch", daemon=True).start()
                return result
        finally:
            if priority:
                with self._priority_state_lock:
                    self._priority_count -= 1
                    if not self._priority_count:
                        self._priority_pending.clear()

    def _send_raw(self, line: str, require_connected: bool = True) -> dict[str, Any]:
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

    def _read_loop(self, ser: Any, stop_event: threading.Event, generation: int) -> None:
        pending = b""
        while not stop_event.is_set():
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
                    metadata = self._record_line(line, generation, ser)
                    if metadata is not None:
                        self._emit("serial_line", {"line": line, **metadata})
        with self._lock:
            still_active = self._generation == generation and self._serial is ser
            if still_active:
                self._serial = None
                self._reader_thread = None
        if still_active:
            self._emit("serial_status", {"connected": False})


MAX_SLOTS = 8

events = EventHub()
wireless_dataset_collector: Any = None
wireless_dataset_lock = threading.Lock()
wireless_replay_collector: Any = None
wireless_replay_lock = threading.Lock()
# Admission spans identity checks and connection creation across HTTP threads.
dataset_transport_admission = threading.RLock()
dataset_workflow_service = None
dataset_workflow_lock = threading.Lock()


def get_dataset_workflow_service():
    global dataset_workflow_service
    if DatasetWorkflowService is None:
        raise RuntimeError("Dataset wizard belum tersedia. Jalankan ulang backend setelah pembaruan aplikasi.")
    with dataset_workflow_lock:
        if dataset_workflow_service is None:
            dataset_workflow_service = DatasetWorkflowService(
                DATASET_OUTPUT_DIR, WindowsWorkflowPlatform(),
                lambda payload: events.emit("dataset_workflow", payload))
        return dataset_workflow_service


def workflow_in_use():
    if dataset_workflow_service is None:
        return False
    state = dataset_workflow_service.snapshot()
    return bool(state.get("connected") or state.get("cleanup_pending") or
                state.get("state") in {"connecting", "starting", "recording", "pausing", "paused", "resuming", "continuing",
                    "recovering", "replaying", "stopping", "stop_pending", "cleanup_wait", "cleanup_pending"})


def workflow_action(action, payload):
    service = get_dataset_workflow_service()
    with dataset_transport_admission:
        if action in {"connect", "start", "continue", "resume"}:
            if wireless_collector_in_use(wireless_dataset_collector) or wireless_collector_in_use(wireless_replay_collector):
                raise RuntimeError("Disconnect Dataset lama sebelum menggunakan wizard.")
            if any(item.status().get("connected") for item in serial_bridges_snapshot().values()):
                raise RuntimeError("Disconnect COM sebelum menghubungkan Dataset Wireless.")
        operations = {
            "scan": service.scan,
            "select": lambda: service.select(payload.get("device_id", "")),
            "connect": lambda: service.connect(payload.get("device_id", ""), payload.get("password")),
            "choose-file": service.choose_file,
            "choose-default-file": service.choose_default_file,
            "configure": lambda: service.configure(payload),
            "lock": lambda: service.lock(payload.get("locked")),
            "start": service.start, "pause": service.pause, "resume": service.resume,
            "stop": service.stop, "continue": service.continue_recording,
            "reset": service.reset, "disconnect": service.disconnect, "export": service.export_csv,
        }
        if action not in operations:
            raise ValueError("Aksi Dataset tidak dikenal.")
        return operations[action]()


def get_wireless_dataset_collector() -> Any:
    global wireless_dataset_collector
    collector_type = WirelessDatasetDirectCollector or WirelessDatasetCollector
    if collector_type is None:
        raise RuntimeError("Wireless Dataset is unavailable in this installation")
    with wireless_dataset_lock:
        if wireless_dataset_collector is None:
            wireless_dataset_collector = collector_type(
                DATASET_OUTPUT_DIR,
                lambda payload: events.emit("wireless_dataset", payload),
            )
        return wireless_dataset_collector


def get_wireless_replay_collector() -> Any:
    global wireless_replay_collector
    if WirelessReplayCollector is None:
        raise RuntimeError("Wireless replay is unavailable in this installation")
    with wireless_replay_lock:
        if wireless_replay_collector is None:
            wireless_replay_collector = WirelessReplayCollector(
                DATASET_OUTPUT_DIR,
                lambda payload: events.emit("wireless_dataset_replay", payload),
            )
        return wireless_replay_collector


def wireless_collector_in_use(collector: Any) -> bool:
    if collector is None:
        return False
    state = collector.snapshot()
    return bool(state.get("connected") or state.get("recovery_active") or state.get("cleanup_pending") or
                state.get("stop_requested") and state.get("state") not in {"complete", "incomplete", "disconnected", "ready", "not_ready"} or
                state.get("state") in {"connecting", "starting", "recording", "recovering",
                                       "reconnecting", "resuming", "replaying", "stopping", "stop_pending"})


def connect_wireless_dataset(password: str, *, replay: bool = False) -> Any:
    with dataset_transport_admission:
        if workflow_in_use():
            raise RuntimeError("Selesaikan dan Disconnect Dataset wizard terlebih dahulu.")
        other = wireless_dataset_collector if replay else wireless_replay_collector
        if wireless_collector_in_use(other):
            raise RuntimeError("Disconnect the other Wireless Dataset mode first")
        if any(item.status().get("connected") for item in serial_bridges_snapshot().values()):
            raise RuntimeError("Disconnect COM before connecting Wireless Dataset")
        collector = get_wireless_replay_collector() if replay else get_wireless_dataset_collector()
        return collector.connect(password)


serial_bridges: dict[int, "SerialBridge"] = {}
serial_bridges_lock = threading.Lock()
flash_port_lock = threading.Lock()
flash_ports: dict[str, object] = {}
flash_port_operations: dict[str, int] = {}


def _flash_port_key(port: str) -> str:
    return str(port).strip().upper()


def is_flash_port_reserved(port: str) -> bool:
    with flash_port_lock:
        return _flash_port_key(port) in flash_ports


def _begin_port_operation(port: str, reservation: object | None = None) -> None:
    key = _flash_port_key(port)
    with flash_port_lock:
        owner = flash_ports.get(key)
        if owner is not None and owner is not reservation:
            raise RuntimeError(f"{port} is reserved for firmware upload; wait until the upload finishes")
        if reservation is not None and owner is not reservation:
            raise RuntimeError("firmware upload reservation is not valid")
        flash_port_operations[key] = flash_port_operations.get(key, 0) + 1


def _end_port_operation(port: str) -> None:
    key = _flash_port_key(port)
    with flash_port_lock:
        remaining = flash_port_operations[key] - 1
        if remaining:
            flash_port_operations[key] = remaining
        else:
            del flash_port_operations[key]


def reserve_flash_port(port: str) -> object | None:
    with flash_port_lock:
        key = _flash_port_key(port)
        if key in flash_ports or flash_port_operations.get(key, 0):
            return None
        token = object()
        flash_ports[key] = token
        return token


def _require_flash_reservation(port: str, token: object | None) -> None:
    with flash_port_lock:
        if token is None or flash_ports.get(_flash_port_key(port)) is not token:
            raise RuntimeError("firmware upload reservation is not valid")


def release_flash_port(port: str, token: object) -> None:
    with flash_port_lock:
        key = _flash_port_key(port)
        if flash_ports.get(key) is not token or flash_port_operations.get(key, 0):
            raise RuntimeError("firmware upload reservation cannot be released")
        del flash_ports[key]
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
    # Publish exactly one bridge per slot, including simultaneous first requests.
    with serial_bridges_lock:
        if slot not in serial_bridges:
            serial_bridges[slot] = SerialBridge(events, slot=slot)
        return serial_bridges[slot]


def serial_bridges_snapshot() -> dict[int, "SerialBridge"]:
    # Never call bridge methods while holding the registry lock.
    with serial_bridges_lock:
        return dict(serial_bridges)


def get_dataset_monitor(slot: int) -> "DatasetMqttMonitor":
    if slot not in dataset_monitors:
        dataset_monitors[slot] = DatasetMqttMonitor(events, slot=slot)
    return dataset_monitors[slot]


def connected_slots_summary() -> dict[str, Any]:
    summary = {}
    for slot, bridge in serial_bridges_snapshot().items():
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

        subscribed = threading.Event()
        subscribe_error: dict[str, str] = {}
        pending_subscriptions = {"count": len(topics)}

        def on_connect(client_obj: Any, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any) -> None:
            if not (str(reason_code).lower() == "success" or reason_code == 0):
                subscribe_error["message"] = f"connect failed: {reason_code}"
                subscribed.set()
                return
            for topic in topics:
                client_obj.subscribe(topic, qos=0)
            self._emit(
                "dataset_monitor",
                {"status": "subscribed", "host": host, "port": port, "deviceId": device_id, "topics": topics, "reason": str(reason_code)},
            )

        def on_subscribe(_client_obj: Any, _userdata: Any, _mid: int, reason_codes: Any, _properties: Any) -> None:
            if any(getattr(code, "value", code) == 0x80 for code in reason_codes):
                subscribe_error["message"] = "broker rejected dataset topic subscription"
                subscribed.set()
                return
            pending_subscriptions["count"] -= 1
            if pending_subscriptions["count"] <= 0:
                subscribed.set()

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
        client.on_subscribe = on_subscribe
        client.on_message = on_message
        client.connect(host, port, keepalive=20)
        client.loop_start()

        if not subscribed.wait(timeout=5):
            client.loop_stop()
            client.disconnect()
            raise RuntimeError(f"MQTT dataset monitor subscription timeout to {host}:{port}")
        if subscribe_error:
            client.loop_stop()
            client.disconnect()
            raise RuntimeError(subscribe_error["message"])

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
    for slot, bridge in serial_bridges_snapshot().items():
        status = bridge.status()
        if status["connected"] and status["port"] == port:
            return slot
    return None


def probe_port(port: str, *, _reservation: object | None = None) -> dict[str, Any]:
    _begin_port_operation(port, _reservation)
    try:
        return _probe_port_ordinary(port)
    finally:
        _end_port_operation(port)


def _probe_port_ordinary(port: str) -> dict[str, Any]:
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
    allowed_top = required_top | {"capabilities"}
    missing = sorted(required_top - set(manifest))
    unknown = sorted(set(manifest) - allowed_top)
    if missing:
        raise RuntimeError(f"manifest missing required fields: {', '.join(missing)}")
    if unknown:
        raise RuntimeError(f"manifest has unsupported schema-v2 fields: {', '.join(unknown)}")
    if "capabilities" in manifest:
        capabilities = manifest["capabilities"]
        if (env not in GLD_DATASET_WORKFLOW_ENVIRONMENTS or
                not isinstance(capabilities, dict) or
                set(capabilities) != {"nativeSerial", "datasetWifi"} or
                capabilities.get("nativeSerial") is not True or
                capabilities.get("datasetWifi") is not True):
            raise RuntimeError("manifest capabilities must identify a final native-serial Dataset Wi-Fi package")
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
        "buildCommand",
    }
    allowed_source = required_source | {
        "firmwareTreeSnapshotSha256", "firmwareSourceTreeSha256",
        "gitTreeStateScope",
        "packagedAtUtc", "buildStartedAtUtc", "buildCompletedAtUtc",
    }
    if not isinstance(source, dict) or not required_source.issubset(source) or not set(source).issubset(allowed_source):
        raise RuntimeError("manifest source identity is incomplete or has unsupported fields")
    if not re.fullmatch(r"[0-9a-f]{40}", str(source["gitCommit"])):
        raise RuntimeError("manifest source.gitCommit must be a full lowercase Git SHA")
    tree_state = str(source["gitTreeState"])
    automated_package = tree_state in {"build-output", "operator-hub-auto"}
    post_build_package = source["platformioCoreVersion"] == "PlatformIO post-build hook"
    if tree_state not in {"clean", "dirty", "build-output", "operator-hub-auto"}:
        raise RuntimeError("manifest source.gitTreeState is invalid")
    tree_state_scope = source.get("gitTreeStateScope")
    if tree_state_scope is not None and tree_state_scope != "firmware/":
        raise RuntimeError("manifest source.gitTreeStateScope is invalid")
    snapshot_hash = source.get("firmwareTreeSnapshotSha256")
    legacy_source_hash = source.get("firmwareSourceTreeSha256")
    if snapshot_hash is not None and not SHA256_RE.fullmatch(str(snapshot_hash)):
        raise RuntimeError("manifest firmware tree-snapshot SHA-256 is invalid")
    if legacy_source_hash is not None and not SHA256_RE.fullmatch(str(legacy_source_hash)):
        raise RuntimeError("manifest legacy firmware source-tree SHA-256 is invalid")
    if snapshot_hash is not None and legacy_source_hash is not None:
        raise RuntimeError("manifest must use exactly one firmware tree identity field")
    if tree_state == "dirty" and snapshot_hash is None and legacy_source_hash is None:
        raise RuntimeError("dirty source packages require a firmware tree identity SHA-256")
    if not automated_package and not post_build_package and not SEMVER_RE.fullmatch(str(source["platformioCoreVersion"])):
        raise RuntimeError("manifest PlatformIO Core version is invalid")
    if not SHA256_RE.fullmatch(str(source["platformioIniSha256"])):
        raise RuntimeError("manifest platformio.ini SHA-256 is invalid")
    expected_build = f"pio run -e {manifest_env}" if automated_package or post_build_package else f"pio run -e {manifest_env} -t clean && pio run -e {manifest_env}"
    if source["buildCommand"] != expected_build:
        raise RuntimeError("manifest buildCommand does not describe the required clean build")
    has_packaged_at = "packagedAtUtc" in source
    has_legacy_build_times = (
        "buildStartedAtUtc" in source or "buildCompletedAtUtc" in source
    )
    if has_packaged_at == has_legacy_build_times:
        raise RuntimeError("manifest source must use packagedAtUtc or the legacy build timestamp pair")
    if has_packaged_at:
        if not re.fullmatch(r"\d{8}T\d{6}Z", str(source["packagedAtUtc"])):
            raise RuntimeError("manifest source.packagedAtUtc is invalid")
    else:
        if "buildStartedAtUtc" not in source or "buildCompletedAtUtc" not in source:
            raise RuntimeError("manifest legacy build timestamps are incomplete")
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


def require_atex_release(env: str) -> None:
    """Hard-coded release gate; opening it requires a reviewed source change."""
    if env == "gld_atex" or env in ATEX_WORKFLOW_MODELS:
        raise RuntimeError("ATEX upload held: integration and device release gates are not complete")


def reject_atex_manifest_before_release(payload: dict[str, Any]) -> None:
    """Reject an explicitly ATEX-labelled manifest even if its env is renamed.

    Labels and markers are not authenticated; this is a guard against mistakes,
    not proof of firmware provenance or physical board identity.
    """
    manifest = payload.get("manifest")
    profile = str(manifest.get("boardProfile") or "") if isinstance(manifest, dict) else ""
    if "ATEX" in profile.upper():
        raise RuntimeError("ATEX upload held: integration and device release gates are not complete")


def validate_atex_workflow(manifest: Any, package_files: Any, env: str, target_id: str) -> dict[str, Any]:
    """Fail closed if the independent ATEX verifier or its source contract is unavailable."""
    import importlib.util
    model = ATEX_WORKFLOW_MODELS.get(env)
    if model is None:
        raise RuntimeError("unrecognized ATEX workflow environment")
    verifier_path = REPO_ROOT / "firmware" / "tools" / "validate_atex_package.py"
    try:
        spec = importlib.util.spec_from_file_location("gld_atex_package_validator", verifier_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("ATEX validator unavailable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.validate_atex_package(
            manifest, package_files, model, target_id,
            base_validator=validate_firmware_package, nvs_resolver=verified_nvs_region)
    except (OSError, ImportError) as exc:
        raise RuntimeError("ATEX package verifier or model source unavailable") from exc


def shared_esptool_command(args: list[str]) -> list[str]:
    runner = REPO_ROOT / "apps" / "lib" / "run_esptool.py"
    if not runner.is_file():
        raise RuntimeError("shared apps/lib esptool runtime is missing")
    return [sys.executable, str(runner), *args]


def requires_gld1_nvs_reset_before_boot(manifest: dict[str, Any]) -> bool:
    """Only the approved unversioned-profile GLD1 rollback needs this guard."""
    source = manifest.get("source")
    return (
        manifest.get("environment") in {"gld", "gld_model_1", "gld_model_2", "gld_model_3"}
        and manifest.get("firmwareVersion") == "0.8.38"
        and isinstance(source, dict)
        and source.get("gitCommit") == "69a493c32d2500134a21e029820cd4addea1794a"
    )


def verified_nvs_region(verified_files: list[tuple[dict[str, Any], bytes]]) -> tuple[int, int]:
    """Resolve NVS from already hash-verified partition bytes, never UI input."""
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
            return offset, size
    raise RuntimeError("verified package does not declare an NVS partition")


def erase_verified_nvs(manifest: dict[str, Any], verified_files: list[tuple[dict[str, Any], bytes]], port: str,
                       *, hold_in_bootloader: bool = False) -> None:
    """Erase only verified NVS; guarded rollback stays in ROM until flashing."""
    offset, size = verified_nvs_region(verified_files)
    args = ["--chip", str(manifest["chip"]), "--port", port, "--baud", str(manifest["baud"])]
    if hold_in_bootloader:
        args.extend(["--after", "no_reset"])
    args.extend(["erase_region", f"0x{offset:X}", f"0x{size:X}"])
    cmd = shared_esptool_command(args)
    events.emit("upload_line", {"line": f"Resetting verified NVS region 0x{offset:X} (+0x{size:X})"})
    if hold_in_bootloader:
        # Bounded pre-erase. If it fails, the downgrade has NOT been written.
        try:
            completed = subprocess.run(cmd, cwd=str(FIRMWARE_DIR), stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                       errors="replace", timeout=45, check=False)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("NVS pre-erase timed out; rollback was not flashed") from exc
        for line in (completed.stdout or "").splitlines():
            events.emit("upload_line", {"line": line})
        if completed.returncode != 0:
            raise RuntimeError(f"esptool NVS reset failed with exit code {completed.returncode}; rollback was not flashed")
        return
    proc = subprocess.Popen(cmd, cwd=str(FIRMWARE_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")
    assert proc.stdout is not None
    for line in proc.stdout:
        events.emit("upload_line", {"line": line.rstrip("\r\n")})
    code = proc.wait()
    if code != 0:
        raise RuntimeError(f"esptool NVS reset failed with exit code {code}")


def verify_atex_upload_identity(upload_bridge: Any, port: str, target_id: str, timeout: float = 8.0) -> None:
    """Require a nonce-matched identity on the same exclusive serial stream."""
    upload_bridge.challenge_atex_identity(port, target_id, timeout)


def _firmware_upload_reserved(payload: dict[str, Any], slot: int = 1, *, _reservation: object | None = None) -> dict[str, Any]:
    env = str(payload.get("env") or "").strip()
    require_atex_release(env)
    reject_atex_manifest_before_release(payload)
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
    if any(b"GLD ATEX MotherBoardGLDVer2" in data or
           hashlib.sha256(data).hexdigest() in ATEX_KNOWN_BLOCKED_FIRMWARE_SHA256
           for _item, data in verified_files):
        raise RuntimeError("ATEX upload held: integration and device release gates are not complete")
    if env in ATEX_WORKFLOW_MODELS:
        validate_atex_workflow(manifest, payload.get("packageFiles"), env, target_id)
    native_initial = (payload.get("initialFirmware") is True and
                      env in GLD_DATASET_WORKFLOW_ENVIRONMENTS and
                      manifest.get("capabilities") == {"nativeSerial": True, "datasetWifi": True} and
                      payload.get("resetNvsConfirmation") == "RESET NVS")
    if env in GLD_DATASET_WIFI_ENVIRONMENTS | GLD_DATASET_REPLAY_ENVIRONMENTS | GLD_DATASET_WORKFLOW_ENVIRONMENTS and reset_nvs and not native_initial:
        raise RuntimeError(
            "Hotspot Dataset requires an existing saved nulling profile; Reset NVS must be OFF"
        )
    # Reset NVS removes the device-specific LoRa AES configuration. Refuse the
    # destructive operation before touching the serial port unless this PC has
    # a valid local provisioning source to restore it after the upload. The
    # source is deliberately outside Git and the error must not disclose it.
    if reset_nvs and load_canonical_gld_aes_key() is None:
        raise RuntimeError(
            "Reset NVS diblokir: provisioning AES lokal tidak tersedia atau tidak valid; "
            "sinkronkan server/nodered/.env yang sah pada PC ini lalu ulangi"
        )
    preerase_nvs = requires_gld1_nvs_reset_before_boot(manifest)
    if preerase_nvs:
        if payload.get("resetNvs") is not True or payload.get("resetNvsConfirmation") != "RESET NVS":
            raise RuntimeError("GLD1 v0.8.38 rollback requires explicit Reset NVS confirmation; configuration, nulling and model binding will be erased")
        # The exact approved baseline uses default_16MB.csv. Reject an altered
        # partition layout before any serial access or destructive operation.
        if verified_nvs_region(verified_files) != (0x9000, 0x5000):
            raise RuntimeError("GLD1 rollback NVS partition does not match the approved baseline")
    _require_flash_reservation(port, _reservation)
    holder = slot_holding_port(port)
    if env in ATEX_WORKFLOW_MODELS and holder != slot:
        raise RuntimeError("ATEX upload held: selected port must be connected in the selected slot")
    upload_bridge = get_serial_bridge(holder if holder is not None else slot)
    if env in ATEX_WORKFLOW_MODELS:
        # Challenge owns the stream through the verified disconnect.
        verify_atex_upload_identity(upload_bridge, port, target_id)
    else:
        upload_bridge.disconnect()
    if not bool(payload.get("skipPreflight")):
        time.sleep(0.3)
        preflight = probe_port(port, _reservation=_reservation)
        if not preflight["free"]:
            raise RuntimeError(
                f"COM port {port} is still busy after disconnect ({preflight['message']}). "
                "Close other serial monitors, unplug/replug the GLD USB, then retry."
            )
        events.emit("upload_line", {"line": f"Waiting for {port} to stabilize after serial disconnect..."})
        wait_for_reenumerated_port(port)

    if preerase_nvs:
        events.emit("upload_line", {"line": "GLD1 rollback: erase confirmed NVS before flashing; keep board in bootloader until upload succeeds"})
        try:
            erase_verified_nvs(manifest, verified_files, port, hold_in_bootloader=True)
        except Exception as exc:
            events.emit("upload_error", {"message": str(exc)})
            raise

    with tempfile.TemporaryDirectory(prefix="gld-verified-flash-") as temp_name:
        temp_dir = Path(temp_name)
        esptool_args = [
            "--chip", str(manifest["chip"]), "--port", port,
            "--baud", str(manifest["baud"]),
        ]
        if preerase_nvs:
            # Pre-erase left the chip in ROM: do not boot the app in between.
            esptool_args.extend(["--before", "no_reset"])
        esptool_args.append("write_flash")
        for item, content in verified_files:
            target = temp_dir / item["path"]
            target.write_bytes(content)
            esptool_args.extend([item["offset"], str(target)])
        cmd = shared_esptool_command(esptool_args)
        events.emit("upload_start", {
            "cmd": f"verified shared esptool flash ({len(verified_files)} files)",
            "firmwareVersion": manifest["firmwareVersion"],
            "gitCommit": manifest["source"]["gitCommit"],
            # Esptool restarts its displayed percentage for every binary. Send
            # verified sizes so the Hub can render one aggregate package percent.
            "files": [{"path": item["path"], "bytes": len(content)} for item, content in verified_files],
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
        primary_file_index = max(range(len(verified_files)), key=lambda index: len(verified_files[index][1]))
        total_flash_bytes = sum(len(content) for _, content in verified_files)
        # Esptool restarts its percentage for every binary. Track each verified
        # file separately, then report a byte-weighted percentage for the
        # complete package instead of treating app.bin as the whole upload.
        file_progress = [0 for _ in verified_files]
        output_lines: queue.Queue[str | None] = queue.Queue()

        def forward_upload_output() -> None:
            assert proc.stdout is not None
            try:
                for output_line in proc.stdout:
                    output_lines.put(output_line)
            finally:
                output_lines.put(None)

        reader = threading.Thread(target=forward_upload_output, name="gld-upload-output", daemon=True)
        reader.start()
        started_at = time.monotonic()
        last_output_at = started_at
        while True:
            now = time.monotonic()
            if now - started_at >= FIRMWARE_UPLOAD_TOTAL_TIMEOUT_SEC or now - last_output_at >= FIRMWARE_UPLOAD_IDLE_TIMEOUT_SEC:
                proc.terminate()
                try:
                    proc.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                message = "esptool stopped responding before flash verification"
                events.emit("upload_error", {"message": message})
                raise RuntimeError(message)
            try:
                line = output_lines.get(timeout=0.25)
            except queue.Empty:
                continue
            if line is None:
                break
            last_output_at = time.monotonic()
            clean_line = line.rstrip("\r\n")
            match = re.search(r"Writing at 0x([0-9a-fA-F]+).*?\(\s*(\d+)\s*%\s*\)", clean_line)
            if match:
                address = int(match.group(1), 16)
                local_percent = min(100, int(match.group(2)))
                for index, (item, content) in enumerate(verified_files):
                    offset = int(str(item["offset"]), 0)
                    if offset <= address < offset + len(content):
                        file_progress[index] = max(file_progress[index], local_percent)
                        package_percent = round(sum(
                            len(file_content) * file_progress[file_index] / 100
                            for file_index, (_, file_content) in enumerate(verified_files)
                        ) * 100 / total_flash_bytes) if total_flash_bytes else 0
                        events.emit("upload_progress", {
                            "fileIndex": index,
                            "fileCount": len(verified_files),
                            "filePath": item["path"],
                            "filePercent": local_percent,
                            "packagePercent": package_percent,
                            "primary": index == primary_file_index,
                        })
                        break
            events.emit("upload_line", {"line": clean_line})
        code = proc.wait()
    if code != 0:
        message = f"esptool flash failed with exit code {code}"
        events.emit("upload_error", {"message": message})
        raise RuntimeError(message)
    events.emit("upload_done", {"code": code})

    if reset_nvs and not preerase_nvs:
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
    require_atex_release(str(payload.get("env") or "").strip())
    reject_atex_manifest_before_release(payload)
    port = str(payload.get("port") or "").strip()
    reservation = reserve_flash_port(port)
    if reservation is None:
        raise RuntimeError(f"COM port {port} is busy or has an active firmware upload")
    try:
        return _firmware_upload_reserved(payload, slot, _reservation=reservation)
    finally:
        release_flash_port(port, reservation)


class ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    """One bridge owns a Windows address; never share an active listener."""
    allow_reuse_address = False

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Handler(SimpleHTTPRequestHandler):
    server_version = "GLDOperatorLiteBridge/0.2"
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".css": "text/css",
    }

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
                    "appId": APP_ID,
                    "version": VERSION,
                    "processId": os.getpid(),
                    "csrfToken": BRIDGE_CSRF_TOKEN,
                    "features": {
                        "serial": serial is not None,
                        "mqtt": mqtt is not None,
                        "datasetMonitor": mqtt is not None,
                        "mqttBroker": broker_running,
                        "datasetOutput": True,
                        "wirelessDataset": WirelessDatasetDirectCollector is not None or WirelessDatasetCollector is not None,
                        "wirelessDirectCompatible": WirelessDatasetDirectCollector is not None,
                        "wirelessReplay": WirelessReplayCollector is not None,
                        "datasetWorkflow": DatasetWorkflowService is not None,
                        "networkInfo": os.name == "nt",
                        "firmwareUpload": True,
                        "firmwarePackageCapabilities": True,
                        "firmwareGld1DowngradeGuard": True,
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
                        "wirelessDataset": WIRELESS_DATASET_IMPORT_ERROR,
                        "wirelessReplay": WIRELESS_REPLAY_IMPORT_ERROR,
                    },
                    "maxSlots": MAX_SLOTS,
                    "slots": connected_slots_summary(),
                    },
                )
            if path == "/api/ports":
                return json_response(self, {"ports": get_serial_bridge(1).list_ports()})
            if path == "/api/wireless-dataset/state":
                return json_response(self, get_wireless_dataset_collector().snapshot())
            if path == "/api/dataset-workflow/state":
                return json_response(self, get_dataset_workflow_service().snapshot())
            if path == "/api/dataset-workflow/chart-history":
                return json_response(self, get_dataset_workflow_service().chart_history())
            if path == "/api/wireless-replay/state":
                return json_response(self, get_wireless_replay_collector().snapshot())
            if path == "/api/serial/status":
                slot = parse_slot((parse_qs(urlparse(self.path).query).get("slot") or [1])[0])
                return json_response(self, get_serial_bridge(slot).status())
            if path == "/api/serial/recent":
                query = parse_qs(urlparse(self.path).query)
                slot = parse_slot((query.get("slot") or [1])[0])
                try:
                    after = max(0, int((query.get("after") or [0])[0]))
                except (TypeError, ValueError):
                    after = 0
                return json_response(self, get_serial_bridge(slot).recent_lines(after))
            if path == "/api/serial/telemetry-replay":
                query = parse_qs(urlparse(self.path).query)
                slot = parse_slot((query.get("slot") or [1])[0])
                try:
                    after = max(0, int((query.get("after") or [0])[0]))
                except (TypeError, ValueError):
                    raise ValueError("invalid telemetry cursor")
                stream = (query.get("stream") or [""])[0]
                return json_response(self, get_serial_bridge(slot).telemetry_replay(after, stream))
            if path == "/api/firmware/package":
                package_env = (parse_qs(urlparse(self.path).query).get("env") or [""])[0]
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", package_env):
                    raise RuntimeError("invalid firmware environment")
                package_dir = REPO_ROOT / "apps" / "operator-hub" / "firmware-packages" / package_env / "latest"
                manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
                if package_env in ATEX_WORKFLOW_MODELS:
                    entries = manifest.get("flashFiles") if isinstance(manifest, dict) else None
                    if not isinstance(entries, list) or len(entries) != 4 or any(
                        not isinstance(item, dict) or item.get("path") not in
                        {"bootloader.bin", "partitions.bin", "boot_app0.bin", "firmware.bin"} for item in entries
                    ):
                        raise RuntimeError("invalid ATEX package file list")
                package_files = {str(item["path"]): base64.b64encode((package_dir / str(item["path"])).read_bytes()).decode("ascii") for item in manifest["flashFiles"]}
                response = {"manifest": manifest, "packageFiles": package_files}
                if package_env in ATEX_WORKFLOW_MODELS:
                    package_id = str(manifest.get("deviceId") or "").upper()
                    target = "1001" if package_id == "ANY" else package_id
                    response["atexEvidence"] = validate_atex_workflow(manifest, package_files, package_env, target)
                return json_response(self, response)
            if path == "/api/network":
                return json_response(self, network_info())
            if path == "/api/gld-key-status":
                canonical = load_canonical_gld_aes_key()
                return json_response(
                    self,
                    {
                        "configured": canonical is not None,
                        "keyId": canonical["keyId"] if canonical else None,
                        "source": "server/nodered/.env" if canonical else None,
                        # This bridge can read the local provisioning source but cannot
                        # authenticate to, or inspect, a remote/running Node-RED flow.
                        # Do not present source readiness as deployment proof.
                        "nodeRedDeployment": "unverified",
                    },
                )
            if path == "/api/dataset/output-dir":
                return json_response(self, dataset_output_info())
            if path == "/api/serial/port-status":
                query = parse_qs(urlparse(self.path).query)
                port = (query.get("port") or [""])[0]
                with dataset_transport_admission:
                    if workflow_in_use() or wireless_collector_in_use(wireless_replay_collector) or wireless_collector_in_use(wireless_dataset_collector):
                        raise RuntimeError("Disconnect Wireless Dataset before probing COM")
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
            if path.startswith("/api/dataset-workflow/"):
                result = workflow_action(path.removeprefix("/api/dataset-workflow/"), payload)
            elif path == "/api/wireless-dataset/connect":
                result = connect_wireless_dataset(payload.get("password", ""))
            elif path == "/api/wireless-dataset/start":
                result = get_wireless_dataset_collector().start(
                    payload.get("label", ""), payload.get("interval_ms", 500)
                )
            elif path == "/api/wireless-dataset/stop":
                result = get_wireless_dataset_collector().stop()
            elif path == "/api/wireless-dataset/disconnect":
                result = get_wireless_dataset_collector().disconnect()
            elif path == "/api/wireless-dataset/export":
                result = get_wireless_dataset_collector().export_csv()
            elif path == "/api/wireless-replay/connect":
                result = connect_wireless_dataset(payload.get("password", ""), replay=True)
            elif path == "/api/wireless-replay/start":
                result = get_wireless_replay_collector().start(payload.get("label", ""), payload.get("interval_ms", 500))
            elif path == "/api/wireless-replay/stop":
                result = get_wireless_replay_collector().stop()
            elif path == "/api/wireless-replay/disconnect":
                result = get_wireless_replay_collector().disconnect()
            elif path == "/api/wireless-replay/export":
                result = get_wireless_replay_collector().export_csv()
            elif path == "/api/serial/connect":
                with dataset_transport_admission:
                    if workflow_in_use() or wireless_collector_in_use(wireless_dataset_collector) or wireless_collector_in_use(wireless_replay_collector):
                        raise RuntimeError("Disconnect Wireless Dataset before connecting COM")
                    port = str(payload.get("port") or "")
                    holder = slot_holding_port(port)
                    if holder is not None and holder != slot:
                        raise RuntimeError(f"{port} is already connected on slot {holder}")
                    result = get_serial_bridge(slot).connect(port, int(payload.get("baud") or 115200))
            elif path == "/api/serial/atex-identity":
                result = get_serial_bridge(slot).challenge_atex_identity(
                    str(payload.get("port") or ""), str(payload.get("targetDeviceId") or ""),
                    keep_connected=True)
            elif path == "/api/serial/disconnect":
                result = get_serial_bridge(slot).disconnect()
            elif path == "/api/serial/poll/start":
                result = get_serial_bridge(slot).start_background_poll(
                    str(payload.get("owner") or ""), payload.get("intervalMs"), str(payload.get("stream") or ""))
            elif path == "/api/serial/poll/stop":
                result = get_serial_bridge(slot).stop_background_poll(str(payload.get("owner") or ""))
            elif path == "/api/serial/write":
                line, aes_key_synced = inject_canonical_aes_key(str(payload.get("line") or ""))
                result = get_serial_bridge(slot).write_line(line, require_connected=False)
                if aes_key_synced and isinstance(result, dict):
                    result["aesKeySynced"] = True
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
                with dataset_transport_admission:
                    if workflow_in_use() or wireless_collector_in_use(wireless_replay_collector) or wireless_collector_in_use(wireless_dataset_collector):
                        raise RuntimeError("Disconnect Wireless Dataset before firmware upload")
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
            # Overflowed clients are removed by EventHub. Close their SSE
            # connection so EventSource reconnects and can request replay.
            while events.registered(client):
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
    # Establish sole HTTP ownership before starting the optional MQTT broker.
    try:
        httpd = ExclusiveThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        print(f"GLD_BIND_FAILED {args.host}:{args.port}: {exc}")
        return 2
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
    url = f"http://{args.host}:{args.port}/"
    print(f"GLD Operator Lite bridge: {url}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if wireless_replay_collector is not None:
            wireless_replay_collector.disconnect()
        if wireless_dataset_collector is not None:
            wireless_dataset_collector.disconnect()
        for monitor in dataset_monitors.values():
            monitor.stop(emit=False)
        for bridge in serial_bridges_snapshot().values():
            bridge.disconnect()
        if local_mqtt_broker is not None:
            local_mqtt_broker.stop()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
