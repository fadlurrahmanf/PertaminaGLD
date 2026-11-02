"""Host-only fake-peer tests. No COM, GLD, network connection, or services."""
import csv
import base64
import hashlib
import importlib.util
import json
import queue
import struct
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "wireless_dataset.py"
SPEC = importlib.util.spec_from_file_location("wireless_dataset", MODULE_PATH)
wireless = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wireless)


class Peer:
    def __init__(self, *, ready=True, start_mode="normal", hello_patch=None):
        self.inbound = queue.Queue()
        self.sent = []
        self.start_mode = start_mode
        self.session_id = ""
        self.label = ""
        self.total = 0
        self.closed = False
        hello = dict(type="hello", protocol=wireless.PROTOCOL, device_id="1001",
                     feature_order=wireless.FEATURE_ORDER, interval_ms=500,
                     ready=ready, reason="private untrusted reason")
        hello.update(hello_patch or {})
        self.push(hello)

    def settimeout(self, _timeout):
        pass

    def push(self, message):
        self.inbound.put(json.dumps(message))

    def recv(self):
        try:
            return self.inbound.get(timeout=0.02)
        except queue.Empty:
            raise TimeoutError() from None

    def send(self, text):
        message = json.loads(text)
        self.sent.append(message)
        ack = dict(type="ack", cmd=message["cmd"], command_id=message["command_id"],
                   session_id=message["session_id"], result="ok")
        if message["cmd"] == "START_DATASET":
            self.session_id, self.label = message["session_id"], message["label"]
            self.total = 0
            if self.start_mode == "timeout":
                return
            if self.start_mode == "wrong_ack":
                ack["command_id"] = "wrong-command"
            if self.start_mode == "reject":
                ack.update(result="error", detail="do-not-expose-password")
            if self.start_mode == "pre_ack_sample":
                self.push(self.sample(0))
                self.total = 1
            self.push(ack)
            self.push(dict(type="status", session_id=self.session_id, state="running"))
        else:
            self.push(ack)
            self.push(dict(type="status", session_id=self.session_id, state="idle"))
            self.push(dict(type="summary", session_id=self.session_id,
                           total_samples=self.total, reason="stopped"))

    def sample(self, seq, **patch):
        message = dict(type="sample", device_id="1001", session_id=self.session_id,
                       seq=seq, timestamp_ms=1000 + seq * 500,
                       scan_end_ms=1400 + seq * 500, mode="DATASET", label=self.label,
                       nulling_profile_id=5, sensor_voltage=[0.1] * 8,
                       sensor_gain=[1] * 8, sensor_status=[0] * 8,
                       feature_order=wireless.FEATURE_ORDER, overrun_count=0)
        message.update(patch)
        return message

    def emit_sample(self, seq, **patch):
        self.total = max(self.total, seq + 1)
        self.push(self.sample(seq, **patch))

    def close(self):
        self.closed = True
        self.inbound.put("")


def eventually(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("fake-peer condition timed out")


class LoopbackPeer:
    """Minimal RFC6455 peer; binds an ephemeral loopback port for one test."""
    def __enter__(self):
        owner = self
        self.authenticated = False
        self.commands = []
        self.errors = []

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                pass

            def exact(self, size):
                result = bytearray()
                while len(result) < size:
                    part = self.connection.recv(size - len(result))
                    if not part:
                        raise ConnectionError("fixture peer closed")
                    result.extend(part)
                return bytes(result)

            def frame(self, payload, opcode=1):
                data = payload.encode("utf-8") if isinstance(payload, str) else payload
                prefix = bytes([0x80 | opcode])
                if len(data) < 126:
                    prefix += bytes([len(data)])
                else:
                    prefix += bytes([126]) + struct.pack("!H", len(data))
                self.connection.sendall(prefix + data)

            def message(self, value):
                self.frame(json.dumps(value))

            def receive(self):
                first, second = self.exact(2)
                opcode = first & 15
                size = second & 127
                if size == 126:
                    size = struct.unpack("!H", self.exact(2))[0]
                elif size == 127:
                    size = struct.unpack("!Q", self.exact(8))[0]
                if not second & 128 or size > 16384:
                    raise ValueError("invalid client fixture frame")
                mask = self.exact(4)
                payload = self.exact(size)
                return opcode, bytes(value ^ mask[index % 4] for index, value in enumerate(payload))

            def do_GET(self):
                expected = "Basic " + base64.b64encode(b"gld:hotspot-password").decode("ascii")
                if self.path != "/dataset" or self.headers.get("Authorization") != expected:
                    self.send_error(401)
                    return
                owner.authenticated = True
                key = self.headers["Sec-WebSocket-Key"]
                accept = base64.b64encode(hashlib.sha1(
                    (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
                ).digest()).decode("ascii")
                self.send_response(101, "Switching Protocols")
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.send_header("Sec-WebSocket-Accept", accept)
                self.end_headers()
                self.connection.settimeout(2)
                self.message(dict(type="hello", protocol=wireless.PROTOCOL, device_id="1001",
                                  interval_ms=500, ready=True, feature_order=wireless.FEATURE_ORDER))
                try:
                    while True:
                        opcode, payload = self.receive()
                        if opcode == 8:
                            self.frame(payload, opcode=8)
                            return
                        if opcode == 9:
                            self.frame(payload, opcode=10)
                            continue
                        command = json.loads(payload.decode("utf-8"))
                        owner.commands.append(command["cmd"])
                        self.message(dict(type="ack", cmd=command["cmd"],
                                          command_id=command["command_id"],
                                          session_id=command["session_id"], result="ok"))
                        if command["cmd"] == "START_DATASET":
                            self.message(dict(type="status", session_id=command["session_id"], state="running"))
                            template = Peer()
                            template.session_id, template.label = command["session_id"], command["label"]
                            for seq in (0, 1):
                                self.message(template.sample(seq))
                        else:
                            self.message(dict(type="summary", session_id=command["session_id"],
                                              total_samples=2, incomplete=False, reason="stopped"))
                except (ConnectionError, OSError):
                    pass
                except Exception as exc:
                    owner.errors.append(type(exc).__name__)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"ws://127.0.0.1:{self.server.server_port}/dataset"
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.collectors = []

    def tearDown(self):
        for collector in self.collectors:
            collector.disconnect()
        self.directory.cleanup()

    def collector(self, peer=None, callback=None):
        peer = peer or Peer()
        self.connection_options = None
        def factory(url, **options):
            self.connection_options = (url, options)
            return peer
        collector = wireless.WirelessDatasetCollector(
            self.directory.name, callback, websocket_factory=factory,
            command_timeout=0.15)
        self.collectors.append(collector)
        return collector, peer

    def connect_start(self, **kwargs):
        collector, peer = self.collector(**kwargs)
        collector.connect("hotspot-password")
        collector.start("clear_air")
        return collector, peer

    def test_csv_is_written_without_any_browser_and_summary_matches(self):
        events = []
        collector, peer = self.connect_start(callback=events.append)
        peer.emit_sample(0)
        peer.emit_sample(1)
        eventually(lambda: collector.snapshot()["count"] == 2)
        result = collector.stop()
        self.assertTrue(result["complete"])
        self.assertEqual(result["state"], "complete")
        self.assertEqual(result["total_samples"], 2)
        with open(result["path"], newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["seq"], "1")
        self.assertEqual(rows[0]["session_id"], result["session_id"])
        self.assertEqual(rows[0]["gain_MQ8"], "1")
        self.assertEqual(rows[0]["status_MQ2"], "0")
        self.assertEqual(rows[0]["feature_order"], "|".join(wireless.FEATURE_ORDER))
        self.assertEqual([event["type"] for event in events].count("sample"), 2)
        self.assertFalse(any("history" in event for event in events))
        exported = collector.export_csv()
        self.assertEqual(exported["filename"], result["filename"])
        self.assertIn("clear_air", exported["csv"])
        self.assertNotIn("path", exported)

    def test_fixed_endpoint_proxy_redirect_guards_and_redaction(self):
        collector, _peer = self.collector()
        collector.connect("hotspot-password")
        url, options = self.connection_options
        self.assertEqual(url, "ws://192.168.4.1:81/dataset")
        self.assertEqual(options["http_no_proxy"], ["*"])
        self.assertEqual(options["redirect_limit"], 0)
        self.assertNotIn("password", json.dumps(collector.snapshot()))
        self.assertNotIn("Authorization", json.dumps(collector.snapshot()))

    def test_not_ready_does_not_create_csv(self):
        collector, _peer = self.collector(Peer(ready=False))
        collector.connect("hotspot-password")
        with self.assertRaises(RuntimeError):
            collector.start("clear_air")
        self.assertEqual(list(Path(self.directory.name).glob("*.csv")), [])
        with self.assertRaises(RuntimeError):
            collector.export_csv()

    def test_bad_hello_fails_closed(self):
        collector, _peer = self.collector(Peer(hello_patch={"feature_order": ["wrong"] * 8}))
        with self.assertRaises(RuntimeError):
            collector.connect("hotspot-password")
        self.assertFalse(collector.snapshot()["connected"])

    def test_wrong_or_rejected_ack_cannot_activate_recording(self):
        for mode in ("wrong_ack", "reject"):
            collector, peer = self.collector(Peer(start_mode=mode))
            collector.connect("hotspot-password")
            with self.assertRaises(RuntimeError):
                collector.start("clear_air")
            peer.emit_sample(0)
            peer.push(dict(type="summary", session_id=peer.session_id, total_samples=0))
            time.sleep(0.03)
            self.assertEqual(collector.snapshot()["count"], 0)
            self.assertFalse(collector.snapshot()["complete"])
            self.assertNotIn("do-not-expose", collector.snapshot()["error"])

    def test_timeout_does_not_retry_or_accept_late_ack(self):
        collector, peer = self.collector(Peer(start_mode="timeout"))
        collector.connect("hotspot-password")
        with self.assertRaises(RuntimeError):
            collector.start("clear_air")
        self.assertEqual(len(peer.sent), 1)
        command = peer.sent[0]
        peer.push(dict(type="ack", cmd=command["cmd"], command_id=command["command_id"],
                       session_id=command["session_id"], result="ok"))
        peer.emit_sample(0)
        time.sleep(0.03)
        self.assertFalse(collector.snapshot()["connected"])
        self.assertEqual(collector.snapshot()["state"], "incomplete")
        self.assertEqual(collector.snapshot()["count"], 0)

    def test_sample_before_start_ack_is_not_persisted(self):
        collector, peer = self.connect_start(peer=Peer(start_mode="pre_ack_sample"))
        peer.emit_sample(1)
        eventually(lambda: collector.snapshot()["count"] == 1)
        result = collector.stop()
        self.assertEqual(result["gap_count"], 1)
        self.assertFalse(result["complete"])

    def test_missing_and_duplicate_sequences_are_visible(self):
        collector, peer = self.connect_start()
        for seq in (0, 2, 2):
            peer.emit_sample(seq)
        eventually(lambda: collector.snapshot()["duplicate_count"] == 1)
        result = collector.stop()
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["gap_count"], 1)
        self.assertEqual(result["state"], "incomplete")

    def test_disconnect_finishes_file_incomplete_and_reconnect_ignores_old_session(self):
        collector, peer = self.connect_start()
        peer.emit_sample(0)
        eventually(lambda: collector.snapshot()["count"] == 1)
        old_session = collector.snapshot()["session_id"]
        peer.close()
        eventually(lambda: not collector.snapshot()["connected"])
        self.assertEqual(collector.snapshot()["state"], "incomplete")
        new_peer = Peer()
        collector._factory = lambda *_args, **_kwargs: new_peer
        collector.connect("hotspot-password")
        new_peer.push(dict(type="summary", session_id=old_session, total_samples=1))
        time.sleep(0.03)
        self.assertFalse(collector.snapshot()["complete"])
        collector.start("new_session")
        new_peer.emit_sample(0, session_id=old_session)
        new_peer.emit_sample(0)
        eventually(lambda: collector.snapshot()["count"] == 1)
        self.assertEqual(collector.snapshot()["history"][0]["label"], "new_session")

    def test_invalid_sensor_schema_stops_before_write(self):
        for patch in ({"sensor_voltage": [float("nan")] * 8},
                      {"sensor_status": [1] * 8}, {"sensor_gain": [3] * 8},
                      {"device_id": "9999"}, {"nulling_profile_id": 0}):
            collector, peer = self.connect_start()
            peer.emit_sample(0, **patch)
            eventually(lambda: collector.snapshot()["state"] == "incomplete")
            self.assertEqual(collector.snapshot()["count"], 0)

    def test_callback_failure_never_stops_recording(self):
        def callback(_payload):
            raise RuntimeError("browser gone")
        collector, peer = self.connect_start(callback=callback)
        peer.emit_sample(0)
        eventually(lambda: collector.snapshot()["count"] == 1)
        self.assertTrue(collector.stop()["complete"])

    def test_completed_session_stays_complete_when_idle_peer_disconnects(self):
        collector, peer = self.connect_start()
        peer.emit_sample(0)
        eventually(lambda: collector.snapshot()["count"] == 1)
        completed = collector.stop()
        self.assertTrue(completed["complete"])
        peer.close()
        eventually(lambda: not collector.snapshot()["connected"])
        result = collector.snapshot()
        self.assertTrue(result["complete"])
        self.assertEqual(result["state"], "disconnected")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["gap_count"], 0)
        self.assertEqual(result["total_samples"], 1)
        self.assertEqual(collector.export_csv()["filename"], completed["filename"])

    def test_real_vendored_websocket_handshake_basic_auth_and_wire_messages(self):
        with LoopbackPeer() as fixture:
            def factory(requested_url, **options):
                self.assertEqual(requested_url, wireless.ENDPOINT)
                return wireless._transport_factory(fixture.url, **options)
            collector = wireless.WirelessDatasetCollector(
                self.directory.name, websocket_factory=factory, command_timeout=1.5)
            self.collectors.append(collector)
            try:
                collector.connect("hotspot-password")
                collector.start("wire_test")
                eventually(lambda: collector.snapshot()["count"] == 2)
                result = collector.stop()
                self.assertTrue(result["complete"])
                self.assertEqual(result["gap_count"], 0)
                self.assertTrue(fixture.authenticated)
                self.assertEqual(fixture.commands, ["START_DATASET", "STOP_DATASET"])
                self.assertEqual(len(collector.export_csv()["csv"].splitlines()), 3)
            finally:
                collector.disconnect()
            self.assertEqual(fixture.errors, [])

    def test_stop_without_matching_ack_is_incomplete_even_with_summary(self):
        collector, peer = self.connect_start()
        peer.emit_sample(0)
        eventually(lambda: collector.snapshot()["count"] == 1)
        def stop_without_ack(text):
            message = json.loads(text)
            peer.sent.append(message)
            peer.push(dict(type="summary", session_id=peer.session_id, total_samples=1))
        peer.send = stop_without_ack
        with self.assertRaises(RuntimeError):
            collector.stop()
        self.assertFalse(collector.snapshot()["complete"])
        self.assertEqual(collector.snapshot()["state"], "incomplete")
        self.assertEqual(len(peer.sent), 2)

    def test_disk_write_failure_is_incomplete_and_never_counted(self):
        collector, peer = self.connect_start()
        class BrokenWriter:
            def writerow(self, _row):
                raise OSError("private path or sensitive filesystem error")
        with collector._lock:
            collector._writer = BrokenWriter()
        peer.emit_sample(0)
        eventually(lambda: collector.snapshot()["state"] == "incomplete")
        self.assertEqual(collector.snapshot()["count"], 0)
        self.assertNotIn("private", collector.snapshot()["error"])

    def test_active_export_is_flushed_and_transport_error_is_redacted(self):
        collector, peer = self.connect_start()
        peer.emit_sample(0)
        eventually(lambda: collector.snapshot()["count"] == 1)
        self.assertEqual(len(collector.export_csv()["csv"].splitlines()), 2)
        other, _peer = self.collector()
        def failed_factory(*_args, **_kwargs):
            raise RuntimeError("Authorization Basic secret hotspot-password")
        other._factory = failed_factory
        with self.assertRaisesRegex(RuntimeError, "Cannot connect"):
            other.connect("hotspot-password")
        self.assertNotIn("Authorization", json.dumps(other.snapshot()))
        self.assertNotIn("hotspot-password", json.dumps(other.snapshot()))

    def test_history_is_bounded_while_disk_count_continues(self):
        collector, peer = self.connect_start()
        with collector._lock:
            for seq in range(wireless.HISTORY_LIMIT + 3):
                collector._receive(peer.sample(seq))
        snapshot = collector.snapshot()
        self.assertEqual(snapshot["count"], wireless.HISTORY_LIMIT + 3)
        self.assertEqual(len(snapshot["history"]), wireless.HISTORY_LIMIT)
        self.assertEqual(snapshot["history"][0]["seq"], 3)
        snapshot["history"][0]["sensor_voltage"][0] = 999
        self.assertNotEqual(collector.snapshot()["history"][0]["sensor_voltage"][0], 999)

    def test_bad_interval_label_and_password_rejected(self):
        collector, _peer = self.collector()
        for password in ("short", "pass\nword", "a" * 64):
            with self.assertRaises(ValueError):
                collector.connect(password)
        collector.connect("hotspot-password")
        for label in ("", "=formula", "a" * 32):
            with self.assertRaises(ValueError):
                collector.start(label)
        with self.assertRaises(ValueError):
            collector.start("clear_air", 1000)


if __name__ == "__main__":
    unittest.main()
