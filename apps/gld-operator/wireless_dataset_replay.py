"""Isolated protocol-2 collector: durable CSV prefixes and volatile-device replay.

No COM, Wi-Fi switching, deployment or backend-crash recovery. A browser is
never part of the persistence/ACK path. Protocol 1 remains untouched.
"""
from __future__ import annotations

import base64
import csv
import json
import math
import os
import re
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Callable

from wireless_dataset import CSV_HEADERS, FEATURE_ORDER, VALID_GAINS, _transport_factory

ENDPOINT = "ws://192.168.4.1:81/dataset"
PROTOCOL = "gld-dataset-wifi/2"
RETENTION_MS = 300000
CAPACITY = 640
HISTORY_LIMIT = 7200


class ProtocolError(ValueError):
    pass


def _uint(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
        raise ProtocolError("invalid_integer")
    return value


def _label(value: Any) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= 31 or
            any(not 32 <= ord(char) <= 126 for char in value) or value[0] in "=+-@"):
        raise ValueError("Dataset label must be 1..31 printable ASCII characters and CSV-safe")
    return value


def _reason(value: Any) -> str:
    # Do not reflect arbitrary device text into application logs/snapshots.
    allowed = {"retention_limit", "buffer_full", "stopped", "completed", "capture_failed",
               "sensor_invalid", "not_ready", "power_unavailable", "allocation_failed",
               "invalid_sample_or_power", "sequence_limit", "payload_encoding", "control_queue_full",
               "operator_stop", "started"}
    return value if isinstance(value, str) and value in allowed else "device_terminal"


class WirelessDatasetReplayCollector:
    def __init__(self, output_dir: str | Path,
                 event_callback: Callable[[dict[str, Any]], None] | None = None, *,
                 websocket_factory: Callable[..., Any] | None = None,
                 command_timeout: float = 8.0, silence_timeout: float = 3.0,
                 clock: Callable[[], float] = time.monotonic,
                 fsync: Callable[[int], None] = os.fsync,
                 autostart_worker: bool = True) -> None:
        self.output_dir = Path(output_dir).resolve()
        self._callback = event_callback or (lambda _event: None)
        self._factory = websocket_factory or _transport_factory
        self._clock, self._fsync = clock, fsync
        self._timeout, self._silence = command_timeout, silence_timeout
        self._automatic = autostart_worker
        self._lock = threading.RLock()
        self._operation = threading.Lock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._ws: Any = None
        self._generation = 0
        self._worker_epoch = 0
        self._password: str | None = None
        self._want_link = False
        self._file: Any = None
        self._writer: Any = None
        self._history: deque[dict[str, Any]] = deque(maxlen=HISTORY_LIMIT)
        self._control: dict[str, Any] | None = None
        self._start_event, self._stop_event = threading.Event(), threading.Event()
        self._start_confirmed = False
        self._stream_confirmed = False
        self._stop_intent: dict[str, Any] | None = None
        self._stop_acked = False
        self._summary: dict[str, Any] | None = None
        self._terminal_incomplete = False
        self._active = False
        self._outage_started: float | None = None
        self._next_retry_at = 0.0
        self._last_progress_at = self._clock()
        self.connected = self.ready = self.complete = False
        self.state, self.error, self.terminal_reason = "disconnected", "", ""
        self.device_id = self.boot_id = self.session_id = self.label = ""
        self.nulling_profile_id = 0
        self.filename = self.path = ""
        self.next_seq = self.count = self.gap_count = self.duplicate_count = self.replayed_count = 0
        self.total_samples = self.oldest_seq = self.acked_next_seq = self.buffered_samples = 0
        self.replay_target_seq = self.reconnect_attempt = self.retry_count = 0
        self.sampling = self.recovery_active = False

    def _snapshot(self, history: bool = True) -> dict[str, Any]:
        result = dict(connected=self.connected, ready=self.ready, state=self.state,
            error=self.error, reason=self.terminal_reason, terminal_reason=self.terminal_reason,
            device_id=self.device_id, boot_id=self.boot_id, session_id=self.session_id,
            label=self.label, nulling_profile_id=self.nulling_profile_id,
            count=self.count, next_seq=self.next_seq, gap_count=self.gap_count,
            duplicate_count=self.duplicate_count, replayed_count=self.replayed_count,
            total_samples=self.total_samples, oldest_seq=self.oldest_seq,
            acked_next_seq=self.acked_next_seq, buffered_samples=self.buffered_samples,
            sampling=self.sampling, complete=self.complete, filename=self.filename, path=self.path,
            protocol=PROTOCOL, interval_ms=500, retention_ms=RETENTION_MS, capacity=CAPACITY,
            recovery_active=self.recovery_active, reconnect_attempt=self.reconnect_attempt,
            retry_count=self.retry_count, replay_target_seq=self.replay_target_seq,
            backlog_remaining=max(0, self.replay_target_seq - self.next_seq),
            stop_requested=self._stop_intent is not None,
            stop_delivered=bool(self._stop_intent and self._stop_intent.get("delivered")),
            stop_acknowledged=self._stop_acked, history_limit=HISTORY_LIMIT,
            recovery_elapsed_ms=round((self._clock() - self._outage_started) * 1000)
                if self._outage_started is not None else 0)
        if history:
            result["history"] = list(self._history)
        return result

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._snapshot()))

    def _emit(self, payload: dict[str, Any] | None = None) -> None:
        try:
            self._callback(json.loads(json.dumps(payload or {"type": "state", **self._snapshot(False)})))
        except Exception:
            pass

    def _close_socket(self) -> None:
        ws, self._ws = self._ws, None
        self.connected = self.ready = False
        self._generation += 1
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def _close_file(self) -> None:
        stream, self._file = self._file, None
        self._writer = None
        if stream is not None:
            stream.close()

    def _fatal(self, reason: str) -> None:
        self.complete = False
        self.state = "incomplete" if self.session_id else "error"
        self.error = self.terminal_reason = reason
        self._active = self.recovery_active = self._want_link = False
        self._password = None
        self._cancel.set()
        self._close_socket()
        try:
            self._close_file()
        except OSError:
            self.error = self.terminal_reason = "disk_failure"
        self._control = None
        self._start_event.set()
        self._stop_event.set()
        self._emit()

    def _loss(self, reason: str) -> None:
        self._close_socket()
        self._control, self._summary = None, None
        self._stream_confirmed = False
        if not self._active:
            self._want_link = False
            self._password = None
            if not self.complete:
                self.state = "disconnected"
            self._emit()
            return
        self.recovery_active = True
        self.state = "stop_pending" if self._stop_intent else "recovering"
        self.error = reason
        if self._outage_started is None:
            self._outage_started = self._clock()
        self._next_retry_at = self._clock() + min(8, 2 ** min(self.reconnect_attempt, 3))
        self._emit()

    def _hello(self, message: Any, recovering: bool) -> None:
        if not isinstance(message, dict) or message.get("type") != "hello" or message.get("protocol") != PROTOCOL:
            raise ProtocolError("incompatible_hello")
        device, boot = message.get("device_id"), message.get("boot_id")
        if (not isinstance(device, str) or not re.fullmatch(r"[0-9A-Fa-f]{4}", device) or
                not isinstance(boot, str) or not re.fullmatch(r"[0-9a-f]{32}", boot) or
                message.get("feature_order") != FEATURE_ORDER or type(message.get("interval_ms")) is not int or
                message["interval_ms"] != 500 or type(message.get("retention_ms")) is not int or
                message["retention_ms"] != RETENTION_MS or type(message.get("capacity")) is not int or
                message["capacity"] != CAPACITY or type(message.get("ready")) is not bool):
            raise ProtocolError("incompatible_hello")
        profile = _uint(message.get("nulling_profile_id"))
        if not 1 <= profile <= 255:
            raise ProtocolError("invalid_profile")
        total, oldest, acked = (_uint(message.get(key)) for key in ("total_samples", "oldest_seq", "acked_next_seq"))
        if (not 0 <= acked <= oldest <= total or total - oldest > CAPACITY or
                type(message.get("sampling")) is not bool or type(message.get("incomplete")) is not bool or
                not isinstance(message.get("session_id"), str) or not isinstance(message.get("label"), str)):
            raise ProtocolError("invalid_prefix")
        if recovering:
            if device.upper() != self.device_id or boot != self.boot_id:
                raise ProtocolError("device_reboot_or_identity_changed")
            if (message["session_id"] != self.session_id or message["label"] != self.label or
                    profile != self.nulling_profile_id):
                raise ProtocolError("session_identity_changed")
            if not acked <= self.next_seq <= total or self.next_seq < oldest:
                raise ProtocolError("retained_prefix_unavailable")
        else:
            self.device_id, self.boot_id, self.nulling_profile_id = device.upper(), boot, profile
        self.total_samples, self.oldest_seq, self.acked_next_seq = total, oldest, acked
        self.buffered_samples = total - oldest
        self.sampling = message["sampling"]
        if message["incomplete"]:
            self._terminal_incomplete = True
            self.terminal_reason = _reason(message.get("reason"))
        self.connected = True
        self.ready = message["ready"]
        if not recovering:
            if self.sampling or oldest < total:
                self.ready = False
                self.state, self.error = "not_ready", "retained_session_requires_original_backend"
            else:
                self.state = "ready" if self.ready else "not_ready"
                self.error = "" if self.ready else "device_not_ready"

    def _open(self, recovering: bool) -> None:
        password = self._password
        if password is None:
            raise ProtocolError("reconnect_not_authorized")
        authorization = base64.b64encode(f"gld:{password}".encode("ascii")).decode("ascii")
        try:
            ws = self._factory(ENDPOINT, timeout=self._timeout, enable_multithread=True,
                header=[f"Authorization: Basic {authorization}"], http_no_proxy=["*"], redirect_limit=0)
        except Exception as exc:
            if getattr(exc, "status_code", None) in (401, 403):
                raise ProtocolError("authentication_rejected") from None
            raise
        try:
            raw = ws.recv()
            message = self._decode(raw)
            ws.settimeout(0.2)
            self._hello(message, recovering)
            self._ws = ws
            self._last_progress_at = self._clock()
            if recovering:
                self.replay_target_seq = self.total_samples
                self._send_control("RESUME_DATASET", dict(boot_id=self.boot_id, label=self.label, next_seq=self.next_seq))
            self._emit()
        except Exception:
            ws.close()
            raise

    def connect(self, password: str) -> dict[str, Any]:
        if not isinstance(password, str) or not 8 <= len(password) <= 63 or any(not 32 <= ord(char) <= 126 for char in password):
            raise ValueError("Hotspot password must contain 8..63 printable ASCII characters")
        with self._operation, self._lock:
            if self.connected or self._active or self._want_link:
                raise RuntimeError("Disconnect the current wireless recorder first")
            self._password = password
            self._cancel.clear()
            self._want_link = True
            self.state, self.error = "connecting", ""
            try:
                self._open(False)
            except ProtocolError as exc:
                self._fatal(str(exc))
                raise RuntimeError(self.error) from None
            except Exception:
                self._fatal("connection_failed_check_hotspot_and_password")
                raise RuntimeError(self.error) from None
            if self._automatic:
                self._worker_epoch += 1
                self._thread = threading.Thread(target=self._run, args=(self._worker_epoch,), daemon=True, name="gld-dataset-replay")
                self._thread.start()
            return self.snapshot()

    @staticmethod
    def _decode(raw: Any) -> dict[str, Any]:
        if not raw:
            raise EOFError()
        if not isinstance(raw, str) or len(raw) > 16384:
            raise ProtocolError("malformed_message")
        try:
            message = json.loads(raw)
        except (ValueError, TypeError):
            raise ProtocolError("malformed_message") from None
        if not isinstance(message, dict):
            raise ProtocolError("malformed_message")
        return message

    def _send(self, message: dict[str, Any]) -> None:
        if self._ws is None:
            raise ConnectionError()
        self._ws.send(json.dumps(message, allow_nan=False, separators=(",", ":")))

    def _send_control(self, command: str, extra: dict[str, Any], command_id: str | None = None) -> None:
        identifier = command_id or uuid.uuid4().hex
        wire = dict(cmd=command, command_id=identifier, session_id=self.session_id, **extra)
        self._control = dict(cmd=command, command_id=identifier, acked=False,
                             deadline=self._clock() + self._timeout)
        self._send(wire)
        if command == "STOP_DATASET" and self._stop_intent:
            self._stop_intent["delivered"] = True

    def _step(self) -> None:
        """One bounded supervisor turn; test peers may drive it with virtual time."""
        with self._lock:
            if not self._want_link or self._cancel.is_set():
                return
            if self._ws is None:
                if self._clock() < self._next_retry_at:
                    return
                self.reconnect_attempt += 1
                self.retry_count += 1
                try:
                    self._open(True)
                except ProtocolError as exc:
                    self._fatal(str(exc))
                except Exception:
                    self._loss("reconnect_failed")
                return
            if self._control and self._clock() >= self._control["deadline"]:
                self._loss("command_result_unknown_resume_required")
                return
            if self._active and self._stream_confirmed and self._clock() - self._last_progress_at >= self._silence:
                self._loss("sample_silence_resume_required")
                return
            ws, generation = self._ws, self._generation
        try:
            raw = ws.recv()
            message = self._decode(raw)
            with self._lock:
                if generation == self._generation and self._ws is ws:
                    self._receive(message)
        except Exception as exc:
            with self._lock:
                if generation != self._generation:
                    return
                if isinstance(exc, TimeoutError) or type(exc).__name__ == "WebSocketTimeoutException":
                    return
                if isinstance(exc, ProtocolError):
                    self._fatal(str(exc))
                elif isinstance(exc, OSError) and not isinstance(exc, (ConnectionError, TimeoutError)):
                    # Only filesystem operations are wrapped as disk_failure below.
                    self._loss("transport_lost")
                else:
                    self._loss("transport_lost")

    def _run(self, epoch: int) -> None:
        while epoch == self._worker_epoch and self._want_link and not self._cancel.is_set():
            self._step()
            self._cancel.wait(0.01)

    def _wait(self, event: threading.Event) -> None:
        if self._automatic:
            event.wait(self._timeout)
        else:
            deadline = self._clock() + self._timeout
            for _ in range(10000):
                if event.is_set() or self._clock() >= deadline:
                    break
                self._step()

    def start(self, label: str, interval_ms: int = 500) -> dict[str, Any]:
        _label(label)
        if type(interval_ms) is not int or interval_ms != 500:
            raise ValueError("Replay Dataset supports only a 500 ms interval")
        with self._operation:
            with self._lock:
                if not self.connected or not self.ready or self._active or self._password is None:
                    raise RuntimeError("Connect a ready replay GLD before Start")
                self.session_id, self.label = uuid.uuid4().hex, label
                self.next_seq = self.count = self.gap_count = self.duplicate_count = self.replayed_count = 0
                self.total_samples = self.oldest_seq = self.acked_next_seq = self.buffered_samples = 0
                self.replay_target_seq = self.reconnect_attempt = self.retry_count = 0
                self._history.clear()
                self._summary = self._stop_intent = None
                self._stop_acked = self._terminal_incomplete = self.complete = False
                self._start_confirmed = self._stream_confirmed = False
                self._start_event.clear()
                self._stop_event.clear()
                self._active, self.sampling = True, True
                self._outage_started = None
                self.error = self.terminal_reason = ""
                self.filename = f"wireless_replay_{self.device_id}_{self.session_id}.csv"
                self.path = str(self.output_dir / self.filename)
                try:
                    self.output_dir.mkdir(parents=True, exist_ok=True)
                    self._file = Path(self.path).open("x", encoding="utf-8", newline="")
                    self._writer = csv.writer(self._file)
                    self._writer.writerow(CSV_HEADERS)
                    self._file.flush()
                    self._fsync(self._file.fileno())
                except OSError:
                    self._fatal("disk_failure")
                    raise RuntimeError(self.error) from None
                self.state = "starting"
                self._emit()
                try:
                    self._send_control("START_DATASET", dict(label=label, sample_interval_ms=500))
                except Exception:
                    self._loss("start_result_unknown_resume_required")
            self._wait(self._start_event)
            with self._lock:
                if self._active and not self._start_confirmed and self._ws is not None:
                    self._loss("start_result_unknown_resume_required")
                if not self._active and not self.complete:
                    raise RuntimeError(self.error)
                return self.snapshot()

    def stop(self) -> dict[str, Any]:
        with self._operation:
            with self._lock:
                if not self._active:
                    raise RuntimeError("No active replay Dataset session")
                if self._stop_intent is None:
                    self._stop_intent = dict(command_id=uuid.uuid4().hex, delivered=False)
                    self._stop_event.clear()
                if self.connected and self._stream_confirmed and not self._control:
                    try:
                        self._send_control("STOP_DATASET", {}, self._stop_intent["command_id"])
                        self.state = "stopping"
                    except Exception:
                        self._loss("stop_result_unknown_resume_required")
                else:
                    self.state = "stop_pending"
                self._emit()
            self._wait(self._stop_event)
            return self.snapshot()

    def disconnect(self) -> dict[str, Any]:
        self._cancel.set()  # Wake a backoff/idle worker before waiting for its lock.
        with self._lock:
            self._want_link = False
            self._worker_epoch += 1
            self._cancel.set()
            self._password = None
            if self._active:
                self._fatal("cancelled_locally_remote_sampling_may_continue")
            else:
                self._close_socket()
                self.recovery_active = False
                if not self.complete and self.state != "incomplete":
                    self.state = "disconnected"
                self._emit()
            result = self.snapshot()
            worker = self._thread
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=1.0)
        return result

    def _metadata(self, message: dict[str, Any]) -> None:
        if message.get("session_id") != self.session_id:
            raise ProtocolError("session_identity_changed")
        for key, expected in (("device_id", self.device_id), ("boot_id", self.boot_id),
                              ("label", self.label), ("nulling_profile_id", self.nulling_profile_id)):
            if key in message and message[key] != expected:
                raise ProtocolError("session_identity_changed")

    def _status(self, message: dict[str, Any]) -> None:
        self._metadata(message)
        if type(message.get("sampling")) is not bool or type(message.get("incomplete")) is not bool:
            raise ProtocolError("malformed_status")
        if message.get("state") not in ({"running"} if message["sampling"] else {"stopped", "error"}):
            raise ProtocolError("malformed_status")
        total, oldest, acked, buffered = (_uint(message.get(key)) for key in
            ("total_samples", "oldest_seq", "acked_next_seq", "buffered_samples"))
        if (not acked <= oldest <= total or acked > self.next_seq or oldest > self.next_seq or
                total - oldest != buffered or buffered > CAPACITY or total < self.next_seq):
            raise ProtocolError("invalid_prefix")
        self.total_samples, self.oldest_seq, self.acked_next_seq, self.buffered_samples = total, oldest, acked, buffered
        self.sampling = message["sampling"]
        if message["incomplete"]:
            self._terminal_incomplete = True
            self.terminal_reason = _reason(message.get("reason"))
        control = self._control
        if control and control["acked"] and control["cmd"] in {"START_DATASET", "RESUME_DATASET"}:
            resumed = control["cmd"] == "RESUME_DATASET"
            self._control = None
            self._start_confirmed = self._stream_confirmed = True
            self._last_progress_at = self._clock()
            if resumed:
                self.replay_target_seq = total
            self.recovery_active = False
            self.error = ""
            self.state = "replaying" if self.next_seq < self.replay_target_seq or not self.sampling else "recording"
            self._start_event.set()
            if self._stop_intent and not self._stop_acked:
                self._send_control("STOP_DATASET", {}, self._stop_intent["command_id"])
                self.state = "stopping"
        self._emit()

    def _receive(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == "ack":
            control = self._control
            if (not control or message.get("command_id") != control["command_id"] or
                    message.get("cmd") != control["cmd"] or message.get("session_id") != self.session_id):
                return
            if message.get("result") != "ok":
                raise ProtocolError("device_rejected_" + control["cmd"].lower())
            control["acked"] = True
            if control["cmd"] == "STOP_DATASET":
                self._stop_acked = True
                self._control = None
                self._finish()
            return
        if kind not in {"status", "sample", "summary"}:
            raise ProtocolError("unexpected_message")
        self._metadata(message)
        if kind == "status":
            self._status(message)
        elif kind == "sample":
            if not self._stream_confirmed:
                raise ProtocolError("sample_before_control_confirmation")
            self._record(message)
        else:
            if not self._stream_confirmed:
                return  # A prior terminal report before Resume is not confirmation.
            total = _uint(message.get("total_samples"))
            _uint(message.get("overrun_count"))
            if type(message.get("incomplete")) is not bool or total != self.next_seq:
                raise ProtocolError("summary_count_mismatch")
            self._summary = dict(message)
            self.sampling = False
            self.total_samples = total
            self._finish()

    def _record(self, message: dict[str, Any]) -> None:
        self._metadata(message)
        if message.get("device_id") != self.device_id or message.get("label") != self.label or message.get("mode") != "DATASET" or message.get("feature_order") != FEATURE_ORDER:
            raise ProtocolError("invalid_sample_identity")
        if type(message.get("nulling_profile_id")) is not int or message.get("nulling_profile_id") != self.nulling_profile_id:
            raise ProtocolError("profile_changed")
        seq = _uint(message.get("seq"))
        for key in ("timestamp_ms", "scan_end_ms", "overrun_count"):
            _uint(message.get(key))
        voltage, gains, statuses = (message.get(key) for key in ("sensor_voltage", "sensor_gain", "sensor_status"))
        if (not isinstance(voltage, list) or len(voltage) != 8 or
                any(type(value) not in (int, float) or not math.isfinite(value) for value in voltage) or
                not isinstance(gains, list) or len(gains) != 8 or
                any(type(value) is not int or value not in VALID_GAINS for value in gains) or
                not isinstance(statuses, list) or len(statuses) != 8 or
                any(type(value) is not int or value != 0 for value in statuses)):
            raise ProtocolError("malformed_sample")
        if seq > self.next_seq:
            self.gap_count += seq - self.next_seq
            raise ProtocolError("noncontiguous_sample")
        record = {key: message[key] for key in CSV_HEADERS[:9]}
        for key in ("sensor_voltage", "sensor_gain", "sensor_status", "feature_order"):
            record[key] = list(message[key])
        if seq < self.next_seq:
            saved = next((row for row in reversed(self._history) if row["seq"] == seq), None)
            if saved is None or record != saved:
                raise ProtocolError("duplicate_sample_content_changed")
            self.duplicate_count += 1
            self._send(dict(cmd="ACK_SAMPLES", session_id=self.session_id, boot_id=self.boot_id, next_seq=self.next_seq))
            return
        if self._writer is None:
            raise ProtocolError("csv_not_open")
        try:
            self._writer.writerow([record[key] for key in CSV_HEADERS[:9]] + voltage + gains + statuses + ["|".join(FEATURE_ORDER)])
            self._file.flush()
            self._fsync(self._file.fileno())
        except OSError:
            self._fatal("disk_failure_before_ack")
            return
        self.next_seq += 1
        self.count += 1
        self.total_samples = max(self.total_samples, self.next_seq)
        if seq < self.replay_target_seq:
            self.replayed_count += 1
        if self.next_seq >= self.replay_target_seq and self.sampling and not self._stop_intent:
            self.state = "recording"
            self._outage_started = None
            self.reconnect_attempt = 0
        self._last_progress_at = self._clock()
        self._history.append(record)
        # Publish durable UI progress even if the subsequent ACK socket send fails.
        self._emit(dict(type="sample", sample=record, **self._snapshot(False)))
        # Durable file progress always precedes ACK. A failed ACK is recoverable.
        self._send(dict(cmd="ACK_SAMPLES", session_id=self.session_id, boot_id=self.boot_id, next_seq=self.next_seq))

    def _finish(self) -> None:
        if self._summary is None or (self._stop_intent and not self._stop_acked):
            return
        if not self._stop_intent and not self._terminal_incomplete and not self._summary["incomplete"]:
            raise ProtocolError("clean_summary_without_requested_stop")
        if self._summary["total_samples"] != self.next_seq:
            raise ProtocolError("summary_count_mismatch")
        self._terminal_incomplete = self._terminal_incomplete or self._summary["incomplete"]
        self.complete = not self._terminal_incomplete
        if self._terminal_incomplete:
            self.terminal_reason = self.terminal_reason or _reason(self._summary.get("reason"))
            self.error = self.terminal_reason
        else:
            self.error = self.terminal_reason = ""
        self.state = "complete" if self.complete else "incomplete"
        self._active = self.recovery_active = self._want_link = self.sampling = False
        self.buffered_samples = 0
        self.acked_next_seq = self.next_seq
        self._password = None
        self._cancel.set()
        try:
            self._close_file()
        except OSError:
            self._fatal("disk_failure_on_close")
            return
        self._close_socket()
        self._stop_event.set()
        self._emit()

    def export_csv(self) -> dict[str, str]:
        with self._lock:
            expected = self.output_dir / f"wireless_replay_{self.device_id}_{self.session_id}.csv"
            if not self.session_id or Path(self.path) != expected:
                raise RuntimeError("No current replay CSV is available")
            try:
                if self._file:
                    self._file.flush()
                return dict(filename=expected.name, csv=expected.read_text(encoding="utf-8"))
            except OSError:
                raise RuntimeError("Replay CSV cannot be read") from None
