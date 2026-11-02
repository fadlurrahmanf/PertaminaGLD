"""Browser-independent, single-GLD hotspot Dataset collector (Stage 1).

Only the fixed device endpoint is supported. No COM access, broker, reconnect,
replay, or firmware deployment is performed here. The caller owns app lifetime.
"""
from __future__ import annotations

import base64
import csv
import importlib
import json
import math
import re
import sys
import threading
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Callable

ENDPOINT = "ws://192.168.4.1:81/dataset"
PROTOCOL = "gld-dataset-wifi/1"
FEATURE_ORDER = ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"]
HISTORY_LIMIT = 7200
VALID_GAINS = {1, 2, 4, 8, 16, 32, 64}
CSV_HEADERS = [
    "device_id", "session_id", "seq", "timestamp_ms", "scan_end_ms", "mode",
    "label", "nulling_profile_id", "overrun_count",
] + [f"voltage_{name}" for name in FEATURE_ORDER] + [
    f"gain_{name}" for name in FEATURE_ORDER
] + [f"status_{name}" for name in FEATURE_ORDER] + ["feature_order"]


def _uint(value: Any, name: str) -> int:
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(f"Invalid {name}")
    return value


def _transport_factory(url: str, **kwargs: Any) -> Any:
    vendor = str(Path(__file__).resolve().parent / "vendor" / "wireless")
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    try:
        websocket = importlib.import_module("websocket")
    except ImportError:
        raise RuntimeError("Wireless Dataset dependency is unavailable") from None
    connection = websocket.create_connection(url, **kwargs)
    if connection.getstatus() != 101:
        connection.close()
        raise RuntimeError("GLD WebSocket handshake was not accepted")
    return connection


class WirelessDatasetCollector:
    """One connection/session. Public operations never silently resend commands.

    ``event_callback(payload)`` receives ``type=state`` snapshots without history
    and ``type=sample, sample=record`` after a successful CSV write. Callbacks
    must not call blocking collector operations from the reader thread.
    ``websocket_factory`` is a fake-peer injection point for host-only tests.
    """

    def __init__(self, output_dir: str | Path,
                 event_callback: Callable[[dict[str, Any]], None] | None = None,
                 *, websocket_factory: Callable[..., Any] | None = None,
                 command_timeout: float = 8.0) -> None:
        self.output_dir = Path(output_dir).resolve()
        self._callback = event_callback or (lambda _payload: None)
        self._factory = websocket_factory or _transport_factory
        self._timeout = command_timeout
        self._lock = threading.RLock()
        self._operation = threading.Lock()
        self._ws: Any = None
        self._thread: threading.Thread | None = None
        self._generation = 0
        self._session_generation = -1
        self._hello_event = threading.Event()
        self._pending: dict[str, Any] | None = None
        self._file: Any = None
        self._writer: Any = None
        self._history: deque[dict[str, Any]] = deque(maxlen=HISTORY_LIMIT)
        self.connected = False
        self.ready = False
        self.state = "disconnected"
        self.error = ""
        self.device_id = ""
        self.session_id = ""
        self.filename = ""
        self.path = ""
        self.count = 0
        self.gap_count = 0
        self.duplicate_count = 0
        self.total_samples: int | None = None
        self.complete = False
        self._last_seq = -1
        self._label = ""
        self._summary: dict[str, Any] | None = None
        self._start_confirmed = False
        self._session_failed = False

    def _snapshot(self, history: bool = True) -> dict[str, Any]:
        result = dict(connected=self.connected, ready=self.ready, state=self.state,
                      error=self.error, device_id=self.device_id,
                      session_id=self.session_id, count=self.count,
                      gap_count=self.gap_count, duplicate_count=self.duplicate_count,
                      total_samples=self.total_samples, complete=self.complete,
                      filename=self.filename, path=self.path, protocol=PROTOCOL,
                      interval_ms=500, history_limit=HISTORY_LIMIT)
        if history:
            result["history"] = list(self._history)
        return result

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            # JSON round-trip isolates mutable sample arrays from API consumers.
            return json.loads(json.dumps(self._snapshot()))

    def export_csv(self) -> dict[str, str]:
        """Return only the collector-owned current session file, without paths."""
        with self._lock:
            if not self.session_id or not self.filename or not self.path:
                raise RuntimeError("No wireless Dataset CSV is available")
            expected = self.output_dir / f"wireless_{self.device_id}_{self.session_id}.csv"
            if Path(self.path) != expected or expected.parent != self.output_dir:
                raise RuntimeError("Wireless Dataset CSV identity is invalid")
            try:
                if self._file is not None:
                    self._file.flush()
                return {"filename": expected.name, "csv": expected.read_text(encoding="utf-8")}
            except OSError:
                raise RuntimeError("Wireless Dataset CSV cannot be read") from None

    def _emit(self, payload: dict[str, Any] | None = None) -> None:
        if payload is None:
            payload = {"type": "state", **self._snapshot(history=False)}
        try:
            self._callback(json.loads(json.dumps(payload)))
        except Exception:
            pass  # A disconnected browser must never interrupt recording.

    def _close_file(self) -> None:
        if self._file is not None:
            try:
                self._file.flush()
            finally:
                self._file.close()
                self._file = self._writer = None

    def _fail(self, message: str) -> None:
        self.error = message
        if self.complete:
            # A reconciled CSV remains complete after an idle connection ends.
            # The new error describes connectivity, not historical file integrity.
            self.ready = False
            self.state = "disconnected" if not self.connected else "error"
            self._hello_event.set()
            self._emit()
            return
        self._session_failed = True
        self.complete = False
        self.ready = False
        self.state = "incomplete" if self.session_id else "error"
        try:
            self._close_file()
        except OSError:
            self.error = "Dataset CSV write failed"
        if self._pending:
            self._pending["error"] = self.error
            self._pending["event"].set()
        self._hello_event.set()
        self._emit()

    def connect(self, password: str) -> dict[str, Any]:
        if not isinstance(password, str) or not 8 <= len(password) <= 63 or any(
                ord(char) < 32 or ord(char) > 126 for char in password):
            raise ValueError("Hotspot password must contain 8..63 printable ASCII characters")
        with self._operation:
            with self._lock:
                if self._ws is not None or self.connected:
                    raise RuntimeError("Disconnect the current wireless connection first")
                self._generation += 1
                generation = self._generation
                self._hello_event = threading.Event()
                self.state, self.error, self.ready = "connecting", "", False
                self._emit()
            authorization = base64.b64encode(f"gld:{password}".encode("ascii")).decode("ascii")
            ws = None
            try:
                ws = self._factory(ENDPOINT, timeout=self._timeout, enable_multithread=True,
                                   header=[f"Authorization: Basic {authorization}"],
                                   http_no_proxy=["*"], redirect_limit=0)
                ws.settimeout(0.5)
            except Exception:
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:
                        pass
                with self._lock:
                    self._fail("Cannot connect to GLD hotspot; check Wi-Fi and password")
                raise RuntimeError(self.error) from None
            finally:
                authorization = ""  # Never retain credentials in collector state.
            with self._lock:
                self._ws = ws
                self._thread = threading.Thread(target=self._read_loop,
                                                args=(ws, generation), daemon=True,
                                                name="gld-wireless-dataset")
                self._thread.start()
            if not self._hello_event.wait(self._timeout):
                self._close_transport()
                with self._lock:
                    self._fail("GLD hello timed out")
                raise RuntimeError(self.error)
            with self._lock:
                if not self.connected:
                    self._close_transport()
                    raise RuntimeError(self.error or "GLD handshake failed")
                return self.snapshot()

    def _close_transport(self) -> None:
        with self._lock:
            ws, self._ws = self._ws, None
            self.connected = self.ready = False
            self._generation += 1
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def disconnect(self) -> dict[str, Any]:
        with self._operation:
            with self._lock:
                active = self.state in {"starting", "recording", "stopping"}
                self._close_transport()
                if active:
                    self._fail("Wireless connection ended before session completion")
                else:
                    self._close_file()
                    self.state = "disconnected"
                    self._emit()
                return self.snapshot()

    def _read_loop(self, ws: Any, generation: int) -> None:
        while True:
            with self._lock:
                if generation != self._generation:
                    return
            try:
                raw = ws.recv()
                if not raw:
                    raise ConnectionError()
                if not isinstance(raw, str) or len(raw) > 16384:
                    raise ValueError("Invalid wireless message")
                message = json.loads(raw)
                with self._lock:
                    if generation != self._generation:
                        return
                    if not isinstance(message, dict):
                        raise ValueError("Invalid wireless message")
                    self._receive(message)
            except Exception as exc:
                if isinstance(exc, TimeoutError) or type(exc).__name__ == "WebSocketTimeoutException":
                    continue
                with self._lock:
                    if generation != self._generation:
                        return
                    self._close_transport()
                    # Never include transport exception text or untrusted payloads.
                    self._fail("Wireless stream ended or supplied invalid Dataset data")
                return

    def _receive(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == "hello":
            if self.connected:
                raise ValueError("Duplicate hello")
            device = message.get("device_id")
            if (message.get("protocol") != PROTOCOL or
                    not isinstance(device, str) or not re.fullmatch(r"[0-9A-Fa-f]{4}", device) or
                    message.get("feature_order") != FEATURE_ORDER or
                    type(message.get("interval_ms")) is not int or message["interval_ms"] != 500 or
                    type(message.get("ready")) is not bool):
                raise ValueError("Incompatible GLD hello")
            self.device_id = device.upper()
            self.connected, self.ready = True, message["ready"]
            self.state = "ready" if self.ready else "not_ready"
            self.error = "" if self.ready else "GLD is not ready; check saved nulling profile and sensors"
            self._hello_event.set()
            self._emit()
            return
        if not self.connected:
            raise ValueError("Hello required")
        if self.complete:
            return  # Finalized sessions cannot be altered by late stream frames.
        pending = self._pending
        if kind == "ack":
            if (not pending or message.get("command_id") != pending["command_id"] or
                    message.get("session_id") != self.session_id or message.get("cmd") != pending["cmd"]):
                return
            if message.get("result") != "ok":
                self._fail("GLD rejected the Dataset command")
                return
            pending["acked"] = True
            if pending["cmd"] == "STOP_DATASET":
                self._finish_if_ready()
            return
        if (message.get("session_id") != self.session_id or not self.session_id or
                self._session_generation != self._generation):
            return  # A prior session cannot create or alter a new recording.
        if kind == "status":
            if message.get("state") == "running" and pending and pending["cmd"] == "START_DATASET" and pending["acked"]:
                self.state = "recording"
                self._start_confirmed = True
                pending["event"].set()
                self._emit()
            elif message.get("state") == "error":
                self._fail("GLD reported a Dataset error")
            return
        if kind == "sample":
            if self.state in {"recording", "stopping"}:
                self._record(message)
            return
        if kind == "summary":
            self._summary = dict(message)
            self._finish_if_ready()

    def _record(self, message: dict[str, Any]) -> None:
        if str(message.get("device_id", "")).upper() != self.device_id or message.get("mode") != "DATASET":
            raise ValueError("Sample identity mismatch")
        if message.get("feature_order") != FEATURE_ORDER or message.get("label") != self._label:
            raise ValueError("Sample schema mismatch")
        seq = _uint(message.get("seq"), "sequence")
        for key in ("timestamp_ms", "scan_end_ms", "overrun_count"):
            _uint(message.get(key), key)
        profile = message.get("nulling_profile_id")
        if type(profile) is not int or not 1 <= profile <= 255:
            raise ValueError("Invalid nulling profile")
        voltage, gains, statuses = (message.get(key) for key in ("sensor_voltage", "sensor_gain", "sensor_status"))
        if (not isinstance(voltage, list) or len(voltage) != 8 or
                any(type(value) not in (int, float) or not math.isfinite(value) for value in voltage) or
                not isinstance(gains, list) or len(gains) != 8 or
                any(type(value) is not int or value not in VALID_GAINS for value in gains) or
                not isinstance(statuses, list) or len(statuses) != 8 or
                any(type(value) is not int or value != 0 for value in statuses)):
            raise ValueError("Invalid sensor sample")
        if seq <= self._last_seq:
            self.duplicate_count += 1
            return
        if self._writer is None:
            raise ValueError("No active output file")
        record = {key: message[key] for key in CSV_HEADERS[:9]}
        for key in ("sensor_voltage", "sensor_gain", "sensor_status", "feature_order"):
            record[key] = list(message[key])
        self._writer.writerow([record[key] for key in CSV_HEADERS[:9]] + voltage + gains + statuses + ["|".join(FEATURE_ORDER)])
        self._file.flush()
        self.gap_count += seq - self._last_seq - 1
        self._last_seq = seq
        self.count += 1
        self._history.append(record)
        self._emit(dict(type="sample", sample=record, count=self.count,
                        gap_count=self.gap_count, session_id=self.session_id, state=self.state))

    def _finish_if_ready(self) -> None:
        summary, pending = self._summary, self._pending
        if summary is None:
            return
        if not self._start_confirmed:
            return  # A rejected/timed-out Start cannot be completed by a late summary.
        if pending and pending["cmd"] == "START_DATASET":
            self._fail("Dataset ended before Start was confirmed")
            return
        # Stop remains uncertain until its matching ACK, even if summary arrived.
        if pending and pending["cmd"] == "STOP_DATASET" and not pending["acked"]:
            return
        total = _uint(summary.get("total_samples"), "summary count")
        if "incomplete" in summary and type(summary["incomplete"]) is not bool:
            raise ValueError("Invalid summary completion state")
        if total < self.count or total < self._last_seq + 1:
            raise ValueError("Summary contradicts persisted samples")
        self.total_samples = total
        self.gap_count = max(self.gap_count, total - self.count)
        self.complete = not self._session_failed and not self.gap_count and not summary.get("incomplete", False)
        self.state = "complete" if self.complete else "incomplete"
        self.error = "" if self.complete else "Session ended with missing samples or an incomplete device summary"
        self._close_file()
        if pending:
            pending["event"].set()
        self._emit()

    def _command(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            pending = dict(cmd=command, command_id=uuid.uuid4().hex, acked=False,
                           event=threading.Event(), error="")
            self._pending = pending
            wire = dict(cmd=command, command_id=pending["command_id"], session_id=self.session_id, **payload)
            try:
                self._ws.send(json.dumps(wire, allow_nan=False))
            except Exception:
                self._fail("Dataset command could not be sent; result is unknown")
        if not pending["event"].wait(self._timeout):
            with self._lock:
                self._fail("Dataset command timed out; result is unknown. Disconnect before another session")
                self._close_transport()
        with self._lock:
            if self._pending is pending:
                self._pending = None
            if pending["error"]:
                raise RuntimeError(pending["error"])
            return self.snapshot()

    def start(self, label: str, interval_ms: int = 500) -> dict[str, Any]:
        if (not isinstance(label, str) or not 1 <= len(label) <= 31 or
                any(ord(char) < 32 or ord(char) > 126 for char in label) or label[0] in "=+-@"):
            raise ValueError("Dataset label must be 1..31 printable ASCII characters and CSV-safe")
        if type(interval_ms) is not int or interval_ms != 500:
            raise ValueError("Stage 1 supports only a 500 ms interval")
        with self._operation:
            with self._lock:
                if not self.connected or not self.ready or self.state not in {"ready", "complete"}:
                    raise RuntimeError("Connect a ready GLD before starting a Dataset session")
                self.session_id = uuid.uuid4().hex
                self._session_generation = self._generation
                self._label = label
                self.count = self.gap_count = self.duplicate_count = 0
                self._last_seq = -1
                self.total_samples, self._summary = None, None
                self.complete, self.error = False, ""
                self._start_confirmed = self._session_failed = False
                self._history.clear()
                self.filename = f"wireless_{self.device_id}_{self.session_id}.csv"
                self.path = str(self.output_dir / self.filename)
                try:
                    self.output_dir.mkdir(parents=True, exist_ok=True)
                    self._file = Path(self.path).open("x", encoding="utf-8", newline="")
                    self._writer = csv.writer(self._file)
                    self._writer.writerow(CSV_HEADERS)
                    self._file.flush()
                except OSError:
                    self._fail("Cannot create Dataset CSV output")
                    raise RuntimeError(self.error) from None
                self.state = "starting"
                self._emit()
            return self._command("START_DATASET", dict(label=label, sample_interval_ms=interval_ms))

    def stop(self) -> dict[str, Any]:
        with self._operation:
            with self._lock:
                if not self.connected or self.state != "recording":
                    raise RuntimeError("No active wireless Dataset session")
                self.state = "stopping"
                self._emit()
            return self._command("STOP_DATASET", {})
