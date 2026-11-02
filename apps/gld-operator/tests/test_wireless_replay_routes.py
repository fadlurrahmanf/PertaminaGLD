"""Protocol-2 API admission tests using real Handler and in-memory HTTP only.

No listener, socket, service, COM, hardware, or compiler is started. Both
collectors and every possible serial entry point are replaced by inert fakes.
"""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import threading
import unittest
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

APP = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("wireless_replay_routes_bridge", APP / "bridge.py")
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)
REPLAY_GETTER = getattr(bridge, "get_wireless_replay_collector", None)
ORIGIN = "http://127.0.0.1:61999"


class FakeCollector:
    def __init__(self, protocol):
        self.calls = []
        self.value = dict(state="disconnected", connected=False, recovery_active=False,
                          stop_requested=False, protocol=protocol, history=[], count=0)

    def snapshot(self):
        return copy.deepcopy(self.value)

    def connect(self, password):
        self.calls.append(("connect", password))
        self.value.update(state="ready", connected=True)
        return self.snapshot()

    def start(self, label, interval_ms):
        self.calls.append(("start", label, interval_ms))
        self.value.update(state="recording", connected=True)
        return self.snapshot()

    def stop(self):
        self.calls.append(("stop",))
        if self.value.get("recovery_active"):
            self.value.update(state="stop_pending", stop_requested=True)
        else:
            self.value.update(state="complete", complete=True)
        return self.snapshot()

    def disconnect(self):
        self.calls.append(("disconnect",))
        self.value.update(state="disconnected", connected=False, recovery_active=False)
        return self.snapshot()

    def export_csv(self):
        self.calls.append(("export",))
        return dict(filename="replay-test.csv", csv="seq,value\n0,1\n")


class MemoryHandler(bridge.Handler):
    def __init__(self, path, payload=None, token=True, origin=ORIGIN):
        self.path = path
        self.command = "GET" if payload is None else "POST"
        self.request_version = "HTTP/1.1"
        self.requestline = self.command + " " + path + " HTTP/1.1"
        self.client_address = ("127.0.0.1", 0)
        self.server = SimpleNamespace(server_address=("127.0.0.1", 61999))
        self.directory = str(APP)
        self.headers = Message()
        self.headers["Host"] = "127.0.0.1:61999"
        self.headers["Content-Type"] = "application/json"
        if token:
            self.headers["X-GLD-Bridge-Token"] = bridge.BRIDGE_CSRF_TOKEN
        if origin:
            self.headers["Origin"] = origin
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        self.headers["Content-Length"] = str(len(body))
        self.rfile, self.wfile = io.BytesIO(body), io.BytesIO()
        self.response_status = None

    def send_response(self, code, _message=None):
        self.response_status = int(code)

    def send_header(self, *_args):
        pass

    def end_headers(self):
        pass

    def log_message(self, *_args):
        pass

    def execute(self):
        self.do_GET() if self.command == "GET" else self.do_POST()
        return self.response_status, json.loads(self.wfile.getvalue())


class ReplayRoutes(unittest.TestCase):
    def setUp(self):
        self.direct = FakeCollector("gld-dataset-wifi/1")
        self.replay = FakeCollector("gld-dataset-wifi/2")
        self.patches = [patch.object(bridge, "BRIDGE_ALLOWED_ORIGINS", {ORIGIN}),
            patch.object(bridge, "serial_bridges", {}),
            patch.object(bridge, "wireless_dataset_collector", self.direct),
            patch.object(bridge, "wireless_replay_collector", self.replay, create=True),
            patch.object(bridge, "get_wireless_dataset_collector", return_value=self.direct),
            patch.object(bridge, "get_wireless_replay_collector", return_value=self.replay, create=True)]
        for current in self.patches:
            current.start()
            self.addCleanup(current.stop)

    def request(self, path, body=None, **options):
        return MemoryHandler(path, body, **options).execute()

    def test_replay_get_state_does_not_connect_or_touch_stage1(self):
        status, state = self.request("/api/wireless-replay/state")
        self.assertEqual(status, 200)
        self.assertEqual(state["protocol"], "gld-dataset-wifi/2")
        self.assertEqual(self.replay.calls, [])
        self.assertEqual(self.direct.calls, [])

    def test_replay_actions_dispatch_only_to_replay_collector(self):
        for action, payload in [("connect", {"password": "test-only-private"}),
                                ("start", {"label": "replay_test", "interval_ms": 500}),
                                ("stop", {}), ("export", {}), ("disconnect", {})]:
            with self.subTest(action=action):
                status, value = self.request("/api/wireless-replay/" + action, payload)
                self.assertEqual(status, 200)
                self.assertNotIn("test-only-private", json.dumps(value))
        self.assertEqual([call[0] for call in self.replay.calls], ["connect", "start", "stop", "export", "disconnect"])
        self.assertEqual(self.direct.calls, [])

    def test_stage1_prefix_retains_protocol1_collector(self):
        status, state = self.request("/api/wireless-dataset/connect", {"password": "test-only"})
        self.assertEqual(status, 200)
        self.assertEqual(state["protocol"], "gld-dataset-wifi/1")
        self.assertEqual(self.replay.calls, [])

    def test_authentication_and_origin_reject_before_replay_actions(self):
        for path, body in [("state", None), ("connect", {"password": "test-only"}), ("export", {})]:
            with self.subTest(path=path):
                self.assertEqual(self.request("/api/wireless-replay/" + path, body, token=False)[0], 403)
        self.assertEqual(self.request("/api/wireless-replay/connect", {}, origin="https://untrusted.invalid")[0], 403)
        self.assertEqual(self.replay.calls, [])

    def test_connected_com_on_any_slot_blocks_replay_connect(self):
        serial = SimpleNamespace(status=lambda: {"connected": True})
        with patch.object(bridge, "serial_bridges", {7: serial}):
            self.assertGreaterEqual(self.request("/api/wireless-replay/connect", {"password": "test-only"})[0], 400)
        self.assertEqual(self.replay.calls, [])

    def test_both_wireless_directions_are_mutually_exclusive(self):
        self.direct.value.update(state="ready", connected=True)
        self.assertGreaterEqual(self.request("/api/wireless-replay/connect", {"password": "test-only"})[0], 400)
        self.assertEqual(self.replay.calls, [])
        self.direct.value.update(state="disconnected", connected=False)
        self.replay.value.update(state="recovering", connected=False, recovery_active=True)
        self.assertGreaterEqual(self.request("/api/wireless-dataset/connect", {"password": "test-only"})[0], 400)
        self.assertEqual(self.direct.calls, [])

    def test_recovering_and_stop_intent_block_com_without_connected_socket(self):
        for state in ("starting", "recording", "recovering", "replaying", "stopping", "stop_pending"):
            with self.subTest(state=state), patch.object(bridge, "get_serial_bridge") as serial_factory:
                self.replay.value.update(state=state, connected=False, recovery_active=state == "recovering")
                status, _value = self.request("/api/serial/connect", {"port": "COM999", "baud": 115200})
                self.assertGreaterEqual(status, 400)
                serial_factory.assert_not_called()

    def test_recovering_stop_intent_and_explicit_cancel_are_available(self):
        self.replay.value.update(state="recovering", connected=False, recovery_active=True)
        status, value = self.request("/api/wireless-replay/stop", {})
        self.assertEqual(status, 200)
        self.assertEqual(value["state"], "stop_pending")
        self.assertTrue(value["stop_requested"])
        status, value = self.request("/api/wireless-replay/disconnect", {})
        self.assertEqual(status, 200)
        self.assertFalse(value["recovery_active"])

    def test_recovery_blocks_port_probe_and_firmware_before_com_entry_points(self):
        self.replay.value.update(state="recovering", connected=False, recovery_active=True)
        with patch.object(bridge, "probe_port") as probe, patch.object(bridge, "firmware_upload") as upload:
            self.assertGreaterEqual(self.request("/api/serial/port-status?port=COM999")[0], 400)
            self.assertGreaterEqual(self.request("/api/firmware/upload", {"port": "COM999"})[0], 400)
            probe.assert_not_called()
            upload.assert_not_called()

    def test_lazy_replay_collector_emits_separate_sse_namespace(self):
        self.assertTrue(callable(REPLAY_GETTER))
        with (patch.object(bridge, "wireless_replay_collector", None),
              patch.object(bridge, "WirelessReplayCollector", return_value=self.replay) as factory,
              patch.object(bridge.events, "emit") as emit):
            self.assertIs(REPLAY_GETTER(), self.replay)
            self.assertIs(REPLAY_GETTER(), self.replay)
            factory.assert_called_once()
            callback = factory.call_args.args[1]
            payload = {"type": "state", "state": "recovering", "protocol": "gld-dataset-wifi/2"}
            callback(payload)
            emit.assert_called_once_with("wireless_dataset_replay", payload)

    def test_finalized_disconnected_replay_does_not_block_com(self):
        self.replay.value.update(state="complete", connected=False, recovery_active=False, complete=True)
        serial = SimpleNamespace(connect=Mock(return_value={"connected": True}))
        with patch.object(bridge, "get_serial_bridge", return_value=serial), patch.object(bridge, "slot_holding_port", return_value=None):
            self.assertEqual(self.request("/api/serial/connect", {"port": "COM999", "baud": 115200})[0], 200)
        serial.connect.assert_called_once()

    def test_concurrent_cross_mode_connect_admission_is_atomic(self):
        entered, release, attempted = threading.Event(), threading.Event(), threading.Event()
        def blocking_connect(password):
            entered.set()
            if not release.wait(2):
                raise AssertionError("fake connect barrier timed out")
            return FakeCollector.connect(self.replay, password)
        self.replay.connect = blocking_connect
        results = {}
        first = threading.Thread(target=lambda: results.setdefault("replay", self.request(
            "/api/wireless-replay/connect", {"password": "test-only"})))
        def second_request():
            attempted.set()
            results["direct"] = self.request("/api/wireless-dataset/connect", {"password": "test-only"})
        second = threading.Thread(target=second_request)
        first.start()
        self.assertTrue(entered.wait(1))
        second.start()
        self.assertTrue(attempted.wait(1))
        release.set()
        first.join(timeout=3)
        second.join(timeout=3)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(results["replay"][0], 200)
        self.assertGreaterEqual(results["direct"][0], 400)
        self.assertEqual(self.direct.calls, [])


if __name__ == "__main__":
    unittest.main()
