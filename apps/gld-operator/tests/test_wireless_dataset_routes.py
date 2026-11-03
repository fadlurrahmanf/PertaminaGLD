"""Authenticated API boundary, fake collector only; no GLD/COM or app restart."""
import importlib.util
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SPEC = importlib.util.spec_from_file_location("wireless_routes_bridge", Path(__file__).resolve().parents[1] / "bridge.py")
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class FakeCollector:
    def __init__(self):
        self.calls = []

    def snapshot(self):
        return {"state": "ready", "connected": True, "history": []}

    def connect(self, password):
        self.calls.append(("connect", password))
        return self.snapshot()

    def start(self, label, interval_ms):
        self.calls.append(("start", label, interval_ms))
        return self.snapshot()

    def stop(self):
        self.calls.append(("stop",))
        return self.snapshot()

    def disconnect(self):
        self.calls.append(("disconnect",))
        return self.snapshot()

    def export_csv(self):
        self.calls.append(("export",))
        return {"filename": "wireless.csv", "csv": "seq,value\n0,1\n"}


class Routes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class QuietHandler(bridge.Handler):
            def log_message(self, *_args):
                pass
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        cls.url = "http://127.0.0.1:%d" % cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        self.collector = FakeCollector()
        self.getter = patch.object(bridge, "get_wireless_dataset_collector", return_value=self.collector)
        self.getter.start()
        self.serial = patch.object(bridge, "serial_bridges", {})
        self.serial.start()

    def tearDown(self):
        self.getter.stop()
        self.serial.stop()

    def request(self, path, body=None, *, token=True, origin=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-GLD-Bridge-Token"] = bridge.BRIDGE_CSRF_TOKEN
        if origin:
            headers["Origin"] = origin
        data = body if body is None or isinstance(body, bytes) else json.dumps(body).encode()
        req = Request(self.url + path, data=data, headers=headers)
        with urlopen(req, timeout=3) as response:
            return json.load(response)

    def test_state_does_not_connect_to_device(self):
        result = self.request("/api/wireless-dataset/state")
        self.assertEqual(result["state"], "ready")
        self.assertEqual(self.collector.calls, [])

    def test_all_actions_are_scoped_to_collector(self):
        for action, payload in [("connect", {"password": "test-only-pass"}), ("start", {"label": "test", "interval_ms": 500}), ("stop", {}), ("export", {}), ("disconnect", {})]:
            self.request("/api/wireless-dataset/" + action, payload)
        self.assertEqual([row[0] for row in self.collector.calls], ["connect", "start", "stop", "export", "disconnect"])

    def test_missing_token_blocks_read_and_write(self):
        # Authorization is rejected before reading a body. Empty POSTs avoid
        # Windows resetting urllib's separate header/body writes after that close.
        for path, body in [("state", None), ("connect", b""), ("export", b"")]:
            with self.assertRaises(HTTPError) as caught:
                self.request("/api/wireless-dataset/" + path, body, token=False)
            self.assertEqual(caught.exception.code, 403)
        self.assertEqual(self.collector.calls, [])

    def test_foreign_origin_blocks_connect(self):
        with self.assertRaises(HTTPError) as caught:
            self.request("/api/wireless-dataset/connect", b"", origin="https://untrusted.invalid")
        self.assertEqual(caught.exception.code, 403)
        self.assertEqual(self.collector.calls, [])

    def test_com_connection_must_be_released_first(self):
        class ConnectedSerial:
            def status(self):
                return {"connected": True}
        with patch.object(bridge, "serial_bridges", {1: ConnectedSerial()}):
            with self.assertRaises(HTTPError):
                self.request("/api/wireless-dataset/connect", {"password": "test-only-pass"})
        self.assertEqual(self.collector.calls, [])

    def test_wireless_connection_blocks_com_before_device_access(self):
        with patch.object(bridge, "wireless_dataset_collector", self.collector), patch.object(bridge, "get_serial_bridge") as serial_factory:
            with self.assertRaises(HTTPError):
                self.request("/api/serial/connect", {"port": "COM-TEST", "baud": 115200})
            serial_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
