"""Synthetic protocol-2 RAM peer over real RFC6455 loopback sockets.

Device acquisition uses an explicitly controlled virtual clock. Collector retry
timing uses real host time. Neither is evidence of firmware execution/RF timing.
"""
from __future__ import annotations

import base64
import copy
import csv
import hashlib
import importlib.util
import io
import json
import os
import select
import socket
import struct
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
APP = REPO / "apps/gld-operator"
sys.path.insert(0, str(APP))
HELPER = APP / "tests/test_wireless_dataset_replay.py"
spec = importlib.util.spec_from_file_location("stage2_ring_reference", HELPER)
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)
from wireless_dataset import _transport_factory
from wireless_dataset_replay import ENDPOINT

PASSWORD = "stage2-simulation-only"
PROTECTED_PORTS = {81, 1880, 1884, 5173, 5174, 5273, 5373}


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


class RingDevice(reference.FakeRingDevice):
    """Reference wire behavior plus firmware-faithful ACK-progress retention."""
    def __init__(self, clock):
        super().__init__(clock)
        self.ack_since = None

    def enforce_retention(self):
        if self.sampling and self.ack_since is not None and self.clock() - self.ack_since >= 300:
            self.terminal("retention_limit")

    def confirm(self, next_seq):
        advanced = next_seq > self.acked
        super().confirm(next_seq)
        if advanced:
            self.ack_since = self.clock() if self.records else None

    def capture(self):
        super().capture()
        if self.records and self.ack_since is None:
            self.ack_since = self.clock()
        if self.sampling and len(self.records) == 640:
            self.terminal("buffer_full")

    def command(self, command, peer):
        if command.get("cmd") == "START_DATASET":
            self.ack_since = self.outage_at = None
        super().command(command, peer)


class Peer:
    def __init__(self, engine, handler):
        self.engine, self.handler = engine, handler
        self.device = engine.device
        self.messages = deque([self.device.hello()])
        self.offered_next = self.device.acked
        self.summary_sent = self.offer_enabled = self.closed = False
        self.prepared_sent = 0

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.messages.clear()
        if self.device.sampling:
            if self.device.outage_at is None:
                self.device.outage_at = self.device.clock()
            if self.device.ack_since is None:
                self.device.ack_since = self.device.clock()
        try:
            self.handler.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.handler.connection.close()
        except OSError:
            pass


class Engine:
    def __init__(self):
        self.lock = threading.RLock()
        self.clock = reference.Clock()
        self.device = RingDevice(self.clock)
        self.peers = set()
        self.available = True
        self.auto_capture = True
        self.pause_outbound = False
        self.drop_after_ack = None
        self.resume_acquisition_after_ack = False
        self.sample_delay = 0.005
        self.collector = None
        self.sessions = {}
        self.audit = []
        self.trace = []
        self.controls = []
        self.errors = []
        self.closed = threading.Event()
        self.server = Server(("127.0.0.1", 0), self.handler_class())
        if self.server.server_port in PROTECTED_PORTS:
            self.server.server_close()
            raise RuntimeError("refusing protected port")
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.02}, daemon=True)
        self.thread.start()
        self.sampler = threading.Thread(target=self._sampler, daemon=True)
        self.sampler.start()

    def _session(self, sid):
        if sid and sid not in self.sessions:
            self.sessions[sid] = dict(session_id=sid, original_samples=[], commands=[], checkpoints=[],
                                      emitted_messages=[], durable_events=[], csv_path="")
        return self.sessions.get(sid)

    def command(self, command, peer):
        with self.lock:
            sid = command.get("session_id", "")
            current = self._session(sid)
            if current:
                current["commands"].append(copy.deepcopy(command))
            kind = command.get("cmd")
            if kind == "ACK_SAMPLES":
                self.audit.append(dict(kind="ack", session_id=sid, next_seq=command["next_seq"],
                                       host_monotonic_s=time.monotonic()))
            self.device.command(command, peer)
            if kind == "START_DATASET" and current:
                current.update(label=self.device.label, device_id=self.device.device_id,
                               boot_id=self.device.boot, nulling_profile_id=self.device.profile)
            if kind == "ACK_SAMPLES" and self.drop_after_ack is not None and command["next_seq"] >= self.drop_after_ack:
                self.drop_after_ack = None
                self.available = self.auto_capture = False
                peer.close()
            elif kind == "ACK_SAMPLES" and self.resume_acquisition_after_ack:
                self.resume_acquisition_after_ack = False
                self.auto_capture = True

    def capture(self, count=1, advance=True):
        with self.lock:
            for _ in range(count):
                if advance:
                    self.clock.advance(0.5)
                self.device.enforce_retention()
                before = self.device.total
                self.device.capture()
                if self.device.total > before:
                    record = copy.deepcopy(self.device.originals[-1])
                    self._session(record["session_id"])["original_samples"].append(record)

    def _sampler(self):
        while not self.closed.wait(0.5):
            with self.lock:
                if self.auto_capture and self.device.sampling:
                    self.capture()

    def fsync(self, descriptor):
        os.fsync(descriptor)
        collector = self.collector
        if collector is None or not collector.path:
            return
        # Called after actual flush/fsync while collector lock is held. We never
        # take collector locks while holding engine.lock in the opposite order.
        with Path(collector.path).open(encoding="utf-8", newline="") as handle:
            count = len(list(csv.DictReader(handle)))
        event = dict(kind="fsync", session_id=collector.session_id, next_seq=count,
                     host_monotonic_s=time.monotonic())
        with self.lock:
            self.audit.append(event)
            session = self._session(collector.session_id)
            session["durable_events"].append(event)
            session["csv_path"] = collector.path

    def factory(self, requested_url, **options):
        if requested_url != ENDPOINT:
            raise RuntimeError("fixture refuses unexpected device endpoint")
        with self.lock:
            if not self.available:
                raise ConnectionError("synthetic radio unavailable")
        return _transport_factory(f"ws://127.0.0.1:{self.server.server_port}/dataset", **options)

    def control(self, action, payload=None):
        payload = payload or {}
        with self.lock:
            self.controls.append(dict(action=action, payload=payload,
                                      acquisition_clock_s=self.clock(), host_monotonic_s=time.monotonic()))
            if action == "acquire":
                count = int(payload.get("count", 1))
                if not 0 <= count <= 650:
                    raise ValueError("invalid acquisition count")
                self.capture(count)
            elif action == "prepare-drop":
                count = int(payload.get("count", 10))
                if not self.device.sampling or not self.peers or not 2 <= count <= 30:
                    raise ValueError("running session required")
                self.auto_capture = False
                self.pause_outbound = True
                self.capture(count)
                self.drop_after_ack = self.device.acked + 1
                for peer in self.peers:
                    peer.prepared_sent = 0
                self.pause_outbound = False
            elif action == "drop":
                self.available = self.auto_capture = False
                for peer in list(self.peers):
                    peer.close()
            elif action == "gap":
                if self.available:
                    raise ValueError("drop before virtual outage acquisition")
                self.capture(int(payload.get("count", 599)))
            elif action == "resume":
                self.available = True
                self.resume_acquisition_after_ack = self.device.sampling
            elif action == "overflow":
                if not self.device.sampling:
                    raise ValueError("running session required")
                self.auto_capture = False
                self.available = False
                for peer in list(self.peers):
                    peer.close()
                # Deliberate capacity-pressure fault, not a timing/cadence claim.
                self.capture(641, advance=False)
            elif action == "speed":
                self.sample_delay = max(0, min(0.1, float(payload.get("sample_delay_ms", 5)) / 1000))
            else:
                raise ValueError("unsupported control")
        return self.snapshot()

    def snapshot(self):
        state = self.collector.snapshot() if self.collector else {}
        with self.lock:
            current = self._session(state.get("session_id", ""))
            if current:
                current["final_snapshot"] = state
                current["csv_path"] = state.get("path", current["csv_path"])
            return copy.deepcopy(dict(schema="gld-replay-e2e/2", mode="pc-simulation",
                acquisition_clock="virtual-controlled", collector_clock="real-host-monotonic",
                virtual_acquisition_s=self.clock(), available=self.available,
                auto_capture=self.auto_capture, device=self.device.hello(), retained_count=len(self.device.records),
                max_window_seen=self.device.max_window_seen, collector=state,
                sessions=list(self.sessions.values()), audit=self.audit, controls=self.controls,
                errors=self.errors))

    def checkpoint(self, name):
        state = self.collector.snapshot()
        with self.lock:
            session = self._session(state.get("session_id", ""))
            if session:
                session["checkpoints"].append(dict(name=name, host_monotonic_s=time.monotonic(),
                    virtual_acquisition_s=self.clock(), retained_count=len(self.device.records), snapshot=state))
        return self.snapshot()

    def close(self):
        self.closed.set()
        if self.collector:
            self.collector.disconnect()
        with self.lock:
            for peer in list(self.peers):
                peer.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.sampler.join(timeout=2)

    def handler_class(self):
        engine = self
        class WireHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            def log_message(self, *_args):
                pass
            def exact(self, count):
                data = bytearray()
                while len(data) < count:
                    part = self.connection.recv(count - len(data))
                    if not part:
                        raise ConnectionError()
                    data.extend(part)
                return bytes(data)
            def receive(self):
                first, second = self.exact(2)
                if not first & 128 or first & 112 or not second & 128:
                    raise ValueError("invalid frame")
                size = second & 127
                if size == 126:
                    size = struct.unpack("!H", self.exact(2))[0]
                elif size == 127:
                    size = struct.unpack("!Q", self.exact(8))[0]
                if size > 4096:
                    raise ValueError("oversized frame")
                mask, data = self.exact(4), self.exact(size)
                return first & 15, bytes(value ^ mask[index % 4] for index, value in enumerate(data))
            def send(self, payload, opcode=1):
                raw = json.dumps(payload, separators=(",", ":")).encode() if opcode == 1 else payload
                header = bytes([128 | opcode])
                header += bytes([len(raw)]) if len(raw) < 126 else bytes([126]) + struct.pack("!H", len(raw))
                self.connection.sendall(header + raw)
            def do_GET(self):
                authorization = "Basic " + base64.b64encode(f"gld:{PASSWORD}".encode()).decode()
                with engine.lock:
                    available = engine.available and not engine.peers
                if self.path != "/dataset" or self.headers.get("Authorization") != authorization:
                    self.send_error(401)
                    return
                if not available:
                    self.send_error(503)
                    return
                key = self.headers.get("Sec-WebSocket-Key", "")
                if not key or self.headers.get("Upgrade", "").lower() != "websocket":
                    self.send_error(400)
                    return
                accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
                self.send_response(101)
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.send_header("Sec-WebSocket-Accept", accept)
                self.end_headers()
                self.close_connection = True  # No second HTTP request after WS handler returns.
                self.connection.settimeout(0.5)
                with engine.lock:
                    peer = Peer(engine, self)
                    engine.peers.add(peer)
                    engine.device.peer = peer
                try:
                    last_sample_at = 0.0
                    while not peer.closed and not engine.closed.is_set():
                        readable, _, _ = select.select([self.connection], [], [], 0.002)
                        if readable:
                            opcode, raw = self.receive()
                            if opcode == 8:
                                self.send(raw, 8)
                                break
                            if opcode == 9:
                                self.send(raw, 10)
                                continue
                            if opcode != 1:
                                raise ValueError("text frame required")
                            engine.command(json.loads(raw), peer)
                        message = None
                        with engine.lock:
                            if peer.messages and not engine.pause_outbound and not peer.closed:
                                first = peer.messages[0]
                                is_sample = first.get("type") == "sample"
                                blocked = is_sample and engine.drop_after_ack is not None and peer.prepared_sent >= 1
                                if not blocked and (not is_sample or time.monotonic() - last_sample_at >= engine.sample_delay):
                                    message = peer.messages.popleft()
                                    if is_sample:
                                        peer.prepared_sent += 1
                        if message is not None:
                            self.send(message)
                            if message.get("type") == "sample":
                                last_sample_at = time.monotonic()
                            with engine.lock:
                                session = engine._session(message.get("session_id", ""))
                                if session:
                                    session["emitted_messages"].append(copy.deepcopy(message))
                except (OSError, ValueError, ConnectionError) as error:
                    with engine.lock:
                        if not peer.closed:
                            engine.errors.append(dict(phase="wire_peer", error_class=type(error).__name__))
                finally:
                    with engine.lock:
                        peer.close()
                        engine.peers.discard(peer)
        return WireHandler
