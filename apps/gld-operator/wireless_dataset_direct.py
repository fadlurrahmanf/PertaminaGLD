"""Additive direct recorder for authenticated protocol 1 and protocol 2.

Protocol 1 delegates unchanged. Protocol 2 freezes the user CSV on loss and
uses a separate private durable ledger to stop/drain only the owned session.
"""
from __future__ import annotations

import base64
import copy
import csv
import json
import os
import tempfile
import threading
import time
import uuid
from collections import deque
from pathlib import Path

from wireless_dataset import CSV_HEADERS, WirelessDatasetCollector, _transport_factory
from wireless_dataset_replay import ENDPOINT, PROTOCOL, WirelessDatasetReplayCollector


def _password(value):
    if not isinstance(value, str) or not 8 <= len(value) <= 63 or any(not 32 <= ord(c) <= 126 for c in value):
        raise ValueError("Hotspot password must contain 8..63 printable ASCII characters")


class _PrefetchedSocket:
    def __init__(self, socket, hello):
        self.socket, self.hello = socket, hello
    def recv(self):
        if self.hello is not None:
            value, self.hello = self.hello, None
            return value
        return self.socket.recv()
    def __getattr__(self, name):
        return getattr(self.socket, name)


class _ObservedSocket:
    def __init__(self, socket, observe):
        self.socket, self.observe, self.first = socket, observe, True
    def recv(self):
        raw = self.socket.recv()
        if self.first:
            self.first = False
            try:
                value = json.loads(raw)
                self.observe({key: value.get(key) for key in ("type", "protocol", "device_id", "boot_id",
                    "session_id", "label", "feature_order", "interval_ms", "retention_ms", "capacity",
                    "ready", "nulling_profile_id", "total_samples", "oldest_seq", "acked_next_seq",
                    "sampling", "incomplete")})
            except (ValueError, TypeError, AttributeError):
                pass
        return raw
    def __getattr__(self, name):
        return getattr(self.socket, name)


class _CleanupReplay(WirelessDatasetReplayCollector):
    """Keep a failed ledger close distinct from a reconciled terminal drain."""
    _ledger_closed_cleanly = False

    def _close_file(self):
        if self._file is None:
            # Base _finish retries close via _fatal after a close error.  That
            # no-op must not erase the failed close's outcome.
            return super()._close_file()
        self._ledger_closed_cleanly = False
        super()._close_file()
        self._ledger_closed_cleanly = True


class _DirectV2(WirelessDatasetReplayCollector):
    def __init__(self, *args, cleanup_factory, **kwargs):
        super().__init__(*args, **kwargs)
        self._cleanup_factory = cleanup_factory
        self._exposure = threading.RLock()
        self._frozen = None
        self._cleanup = None
        self._cleanup_state = {}
        self._cleanup_pending = self._cleanup_paused = self._cleanup_confirmed = False
        self._cleanup_error = ""
        self._original_csv_error = ""
        self._sink_path = None
        self._sink_durable_offset = 0
        self._durable_offset = 0
        self._start_attempted = False
        self._seen_cleanup_hello = {}

    def _snapshot(self, history=True):
        with self._exposure:
            if self._frozen is None:
                value = super()._snapshot(history)
            else:
                value = copy.deepcopy(self._frozen)
                if not history:
                    value.pop("history", None)
                value.update(state="incomplete", complete=False, ready=False,
                    connected=self._cleanup_state.get("connected", False), recovery_active=False,
                    error="Direct recording stopped; original CSV is frozen.",
                    reason="direct_capture_interrupted", terminal_reason="direct_capture_interrupted",
                    sampling=False, stop_requested=self._cleanup_pending)
            value.update(mode="direct", cleanup_pending=self._cleanup_pending,
                cleanup_active=self._cleanup_pending and not self._cleanup_paused,
                cleanup_paused=self._cleanup_paused, cleanup_confirmed=self._cleanup_confirmed,
                cleanup_error=self._original_csv_error or self._cleanup_error,
                original_csv_error=self._original_csv_error,
                cleanup_saved_count=max(0, self._cleanup_state.get("count", self.count) - self.count),
                cleanup_next_seq=self._cleanup_state.get("next_seq", self.next_seq),
                cleanup_stop_acknowledged=self._cleanup_state.get("stop_acknowledged", False),
                cleanup_recovery_active=self._cleanup_state.get("recovery_active", False),
                remote_stop_uncertain=self._cleanup_pending,
                stop_pending=self._cleanup_pending and not self._cleanup_state.get("stop_acknowledged", False))
            return value

    def _emit(self, payload=None):
        if self._frozen is not None:
            return super()._emit({"type": "state", **self._snapshot(False)})
        if payload and payload.get("type") == "sample" and self._file:
            self._durable_offset = self._file.tell()  # Base emitted only after fsync.
        return super()._emit(payload)

    def _send_control(self, command, extra, command_id=None):
        if command == "START_DATASET":
            self._start_attempted = True
            self._durable_offset = self._file.tell()
        return super()._send_control(command, extra, command_id)

    def _loss(self, reason):
        if self._active and self._start_attempted and self._frozen is None:
            return self._begin_cleanup(reason)
        return super()._loss(reason)

    def _fatal(self, reason):
        # A correlated rejection proves this START never became our session.
        # It is not an ambiguous transport outcome and must not own a cleanup.
        if reason == "device_rejected_start_dataset":
            return super()._fatal(reason)
        if self._active and self._start_attempted and self._frozen is None:
            return self._begin_cleanup(reason)
        return super()._fatal(reason)

    def _observe_cleanup_hello(self, value):
        self._seen_cleanup_hello = value

    def _valid_cleanup_hello(self, value):
        # Identity-release decisions need the same full hello validation as the
        # recorder, not just an untrusted boot/session string from the socket.
        probe = WirelessDatasetReplayCollector(self.output_dir, clock=self._clock,
            autostart_worker=False)
        try:
            probe._hello(value, False)
            return True
        except (ValueError, TypeError):
            return False

    def _cleanup_transport(self, url, **options):
        self._seen_cleanup_hello = {}
        return _ObservedSocket(self._cleanup_factory(url, **options), self._observe_cleanup_hello)

    def _begin_cleanup(self, reason):
        # The only transferred prefix is the base's fsynced contiguous count.
        frozen = copy.deepcopy(super()._snapshot(True))
        frozen.update(complete=False, state="incomplete", error="direct_capture_interrupted")
        password, stop_intent, stop_acked = self._password, copy.deepcopy(self._stop_intent), self._stop_acked
        try:
            if self._file:
                self._file.seek(self._durable_offset)
                self._file.truncate()
                self._file.flush()
                self._fsync(self._file.fileno())
        except OSError:
            self._original_csv_error = "original_csv_disk_failure"
        try:
            self._close_file()
        except OSError:
            self._original_csv_error = "original_csv_disk_failure"
        with self._exposure:
            self._frozen = frozen
            self._cleanup_pending, self._cleanup_paused = True, False
        self._active = self._want_link = False
        self._cancel.set()
        self._worker_epoch += 1
        self._close_socket()
        self._password = None
        self.complete, self.state = False, "incomplete"
        child = _CleanupReplay(self.output_dir, self._on_cleanup,
            websocket_factory=self._cleanup_transport, clock=self._clock, fsync=self._fsync,
            command_timeout=self._timeout, silence_timeout=self._silence, autostart_worker=self._automatic)
        for key in ("device_id", "boot_id", "session_id", "label", "nulling_profile_id", "count", "next_seq",
                    "total_samples", "oldest_seq", "acked_next_seq", "buffered_samples"):
            setattr(child, key, getattr(self, key))
        child._history = deque(copy.deepcopy(list(self._history)), maxlen=self._history.maxlen)
        child._stop_intent = stop_intent or dict(command_id=uuid.uuid4().hex, delivered=False)
        child._stop_acked = stop_acked
        self._cleanup = child
        self._activate_cleanup(password)
        self._start_event.set()
        self._stop_event.set()
        self._emit()

    def _open_sink(self):
        child = self._cleanup
        stream = None
        try:
            if self._sink_path is None:
                stream = tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8", newline="",
                    prefix="gld-direct-private-cleanup-", suffix=".csv", delete=False)
                self._sink_path = Path(stream.name)
                csv.writer(stream).writerow(CSV_HEADERS)
            else:
                stream = self._sink_path.open("r+", encoding="utf-8", newline="")
                stream.seek(self._sink_durable_offset)
                stream.truncate()
                if self._sink_durable_offset == 0:
                    csv.writer(stream).writerow(CSV_HEADERS)
            stream.flush()
            self._fsync(stream.fileno())
            self._sink_durable_offset = stream.tell()
            child._file, child._writer = stream, csv.writer(stream)
            child._ledger_closed_cleanly = False
        except OSError:
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
            child._file = child._writer = None
            raise

    def _activate_cleanup(self, password):
        child = self._cleanup
        try:
            self._open_sink()
        except OSError:
            self._cleanup_paused = True
            self._cleanup_error = "cleanup_sink_disk_failure"
            self._emit()
            return
        child._password = password
        child._cancel.clear()
        child._active = child._want_link = True
        child._stream_confirmed = False
        child._control = child._summary = None
        child._loss("owned_direct_cleanup_pending")
        child._next_retry_at = self._clock()
        with self._exposure:
            self._cleanup_paused, self._cleanup_error = False, ""
        if self._automatic:
            child._worker_epoch += 1
            child._thread = threading.Thread(target=child._run, args=(child._worker_epoch,),
                daemon=True, name="gld-direct-owned-cleanup")
            child._thread.start()

    def _on_cleanup(self, event):
        child = self._cleanup
        if child is None:
            return
        with self._exposure:
            self._cleanup_state = {key: value for key, value in event.items() if key not in {"sample", "history", "type"}}
            if event.get("type") == "sample" and child._file:
                self._sink_durable_offset = child._file.tell()
            confirmed = (child._summary is not None and child._stop_acked and not child.sampling and
                         child._ledger_closed_cleanly and
                         child.next_seq == child._summary.get("total_samples") and not child._active)
            if confirmed:
                self._cleanup_pending = self._cleanup_paused = False
                self._cleanup_confirmed = True
                self._cleanup_error = ""
                if self._sink_path:
                    try:
                        self._sink_path.unlink(missing_ok=True)
                    except OSError:
                        pass
            elif not child._active and not child._want_link:
                hello = self._seen_cleanup_hello
                valid = self._valid_cleanup_hello(hello)
                same_device = valid and hello["device_id"].upper() == self.device_id
                new_boot = same_device and hello["boot_id"] != self.boot_id
                absent_idle = (same_device and hello["boot_id"] == self.boot_id and
                    hello["session_id"] != self.session_id and not hello["sampling"] and
                    hello["acked_next_seq"] == hello["oldest_seq"] == hello["total_samples"])
                if new_boot or absent_idle:
                    self._cleanup_pending = self._cleanup_paused = False
                    self._cleanup_error = ("owned_boot_ended_no_foreign_stop_sent" if new_boot
                        else "owned_session_absent_no_foreign_stop_sent")
                    if self._sink_path:
                        try:
                            self._sink_path.unlink(missing_ok=True)
                        except OSError:
                            pass
                else:
                    self._cleanup_paused = True
                    self._cleanup_error = child.error or "cleanup_paused_remote_state_uncertain"
        self._emit()

    def _step(self):
        if self._frozen is not None:
            if self._cleanup_pending and not self._cleanup_paused:
                self._cleanup._step()
            return
        return super()._step()

    def stop(self):
        if self._frozen is not None:
            return self.snapshot()
        return super().stop()

    def disconnect(self):
        if self._frozen is None and self._active and self._start_attempted:
            with self._lock:
                self._begin_cleanup("explicit_direct_disconnect")
            return self.snapshot()
        if self._frozen is not None and self._cleanup_pending:
            self._cleanup.disconnect()
            with self._exposure:
                self._cleanup_paused = True
                self._cleanup_error = "cleanup_paused_remote_state_uncertain"
            self._emit()
            return self.snapshot()
        return super().disconnect()

    def resume_cleanup(self, password):
        _password(password)
        if not self._cleanup_pending or not self._cleanup_paused:
            raise RuntimeError("Direct cleanup is not paused")
        self._activate_cleanup(password)
        return self.snapshot()

    def export_csv(self):
        if self._original_csv_error:
            raise RuntimeError("Original direct CSV could not be verified after a disk failure")
        return super().export_csv()


class WirelessDatasetDirectCollector:
    """One hello-authenticated socket; failed connects preserve prior evidence."""
    def __init__(self, output_dir, event_callback=None, *, websocket_factory=None,
                 command_timeout=8.0, silence_timeout=3.0, clock=time.monotonic,
                 fsync=os.fsync, autostart_worker=True):
        self.output_dir = Path(output_dir)
        self._callback = event_callback or (lambda _event: None)
        self._factory = websocket_factory or _transport_factory
        self._timeout, self._silence, self._clock, self._fsync = command_timeout, silence_timeout, clock, fsync
        self._automatic = autostart_worker
        self._delegate = None
        self._operation = threading.Lock()
        self._last_connection_error = ""

    def _event(self, event):
        event = dict(event, mode="direct")
        try:
            self._callback(event)
        except Exception:
            pass

    def snapshot(self):
        result = self._delegate.snapshot() if self._delegate else dict(connected=False, ready=False,
            complete=False, state="disconnected", count=0, gap_count=0, history=[], filename="", path="", session_id="")
        result.update(mode="direct", last_connection_error=self._last_connection_error)
        for key in ("cleanup_pending", "cleanup_active", "cleanup_paused", "cleanup_confirmed", "stop_pending"):
            result.setdefault(key, False)
        return result

    def connect(self, password):
        _password(password)
        with self._operation:
            current = self.snapshot()
            if current.get("cleanup_pending"):
                if not current.get("cleanup_paused"):
                    raise RuntimeError("Owned direct cleanup is still active")
                return self._delegate.resume_cleanup(password)
            if current.get("connected") or current.get("state") in {"starting", "recording", "recovering", "replaying", "stopping", "stop_pending"}:
                raise RuntimeError("Disconnect the current direct recorder first")
            socket = None
            staged = []
            committed = [False]
            def event(value):
                if committed[0]: self._event(value)
                else: staged.append(value)
            try:
                auth = base64.b64encode(f"gld:{password}".encode("ascii")).decode("ascii")
                socket = self._factory(ENDPOINT, timeout=self._timeout, enable_multithread=True,
                    header=[f"Authorization: Basic {auth}"], http_no_proxy=["*"], redirect_limit=0)
                raw = socket.recv()
                hello = WirelessDatasetReplayCollector._decode(raw)
                protocol = hello.get("protocol") if isinstance(hello, dict) and hello.get("type") == "hello" else None
                prefetched = _PrefetchedSocket(socket, raw)
                used = [False]
                def factory(url, **options):
                    if not used[0]:
                        used[0] = True
                        return prefetched
                    return self._factory(url, **options)
                if protocol == "gld-dataset-wifi/1":
                    candidate = WirelessDatasetCollector(self.output_dir, event,
                        websocket_factory=factory, command_timeout=self._timeout)
                elif protocol == PROTOCOL:
                    candidate = _DirectV2(self.output_dir, event, websocket_factory=factory,
                        cleanup_factory=self._factory, command_timeout=self._timeout, silence_timeout=self._silence,
                        clock=self._clock, fsync=self._fsync, autostart_worker=self._automatic)
                else:
                    raise RuntimeError("Unsupported direct Dataset protocol")
                candidate.connect(password)
            except Exception:
                if socket is not None:
                    try: socket.close()
                    except Exception: pass
                self._last_connection_error = "Cannot connect a compatible GLD; check hotspot and password"
                raise RuntimeError(self._last_connection_error) from None
            self._delegate = candidate
            committed[0] = True
            self._last_connection_error = ""
            self._event({"type": "state", **{k: v for k, v in self.snapshot().items() if k != "history"}})
            return self.snapshot()

    def start(self, label, interval_ms=500):
        if self.snapshot().get("cleanup_pending"):
            raise RuntimeError("Finish owned direct cleanup before a new Start")
        if self._delegate is None:
            raise RuntimeError("Connect GLD first")
        return self._delegate.start(label, interval_ms)

    def stop(self):
        if self._delegate is None:
            raise RuntimeError("No direct Dataset session")
        return self._delegate.stop()

    def disconnect(self):
        if self._delegate is None:
            return self.snapshot()
        return self._delegate.disconnect()

    def export_csv(self):
        if self._delegate is None:
            raise RuntimeError("No direct CSV is available")
        return self._delegate.export_csv()
