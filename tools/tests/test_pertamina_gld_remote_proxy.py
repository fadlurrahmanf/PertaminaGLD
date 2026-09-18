from __future__ import annotations

import base64
import importlib.util
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener


MODULE_PATH = Path(__file__).resolve().parents[1] / "pertamina-gld-remote-proxy.py"
SPEC = importlib.util.spec_from_file_location("pgl_remote_proxy", MODULE_PATH)
proxy = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = proxy
SPEC.loader.exec_module(proxy)


class OriginHandler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return

    def do_GET(self):
        body = b"<html><head></head><body><h1>Pertamina GLD Topology</h1></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8" if self.path.endswith("/view") else "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = json.dumps({"ok": True, "path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class RemoteProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.origin = ThreadingHTTPServer(("127.0.0.1", 0), OriginHandler)
        cls.settings = proxy.Settings(
            username="operator",
            password="this-is-a-long-test-password",
            bind_port=0,
            origin_port=cls.origin.server_address[1],
            request_cooldown_sec=20,
        )
        cls.remote = proxy.RemoteAccessServer(("127.0.0.1", 0), proxy.RemoteAccessHandler, cls.settings)
        cls.origin_thread = threading.Thread(target=cls.origin.serve_forever, daemon=True)
        cls.remote_thread = threading.Thread(target=cls.remote.serve_forever, daemon=True)
        cls.origin_thread.start()
        cls.remote_thread.start()
        cls.base = f"http://127.0.0.1:{cls.remote.server_address[1]}"
        token = base64.b64encode(b"operator:this-is-a-long-test-password").decode()
        cls.auth = {"Authorization": f"Basic {token}"}
        cls.opener = build_opener()

    @classmethod
    def tearDownClass(cls):
        cls.remote.shutdown()
        cls.origin.shutdown()
        cls.remote.server_close()
        cls.origin.server_close()

    def fetch(self, path, *, method="GET", headers=None):
        request = Request(self.base + path, method=method, headers=headers or {})
        return self.opener.open(request, timeout=3)

    def test_authentication_is_required(self):
        with self.assertRaises(HTTPError) as caught:
            self.fetch(proxy.TOPOLOGY_PATH)
        self.assertEqual(caught.exception.code, 401)

    def test_dashboard_and_topology_are_allowed(self):
        response = self.fetch(proxy.VIEW_PATH, headers=self.auth)
        self.assertEqual(response.status, 200)
        self.assertIn(b"REMOTE SECURE", response.read())
        response = self.fetch(proxy.TOPOLOGY_PATH, headers=self.auth)
        self.assertEqual(response.status, 200)

    def test_sensitive_node_red_routes_are_blocked(self):
        for path in ["/flows", "/pertamina-gld/decode", "/pertamina-gld/topology/reset", "/pertamina-gld/topology/delete"]:
            with self.subTest(path=path), self.assertRaises(HTTPError) as caught:
                self.fetch(path, method="POST" if path != "/flows" else "GET", headers=self.auth)
            self.assertEqual(caught.exception.code, 404)

    def test_cross_site_post_is_blocked(self):
        headers = {**self.auth, "Sec-Fetch-Site": "cross-site"}
        with self.assertRaises(HTTPError) as caught:
            self.fetch(proxy.REQUEST_PATH + "?ch=0x0012", method="POST", headers=headers)
        self.assertEqual(caught.exception.code, 403)

    def test_request_is_forwarded_once_then_rate_limited(self):
        headers = {**self.auth, "Sec-Fetch-Site": "same-origin"}
        response = self.fetch(proxy.REQUEST_PATH + "?ch=0x0012", method="POST", headers=headers)
        self.assertEqual(response.status, 200)
        with self.assertRaises(HTTPError) as caught:
            self.fetch(proxy.REQUEST_PATH + "?ch=0x0012", method="POST", headers=headers)
        self.assertEqual(caught.exception.code, 429)
        self.assertTrue(caught.exception.headers.get("Retry-After"))


if __name__ == "__main__":
    unittest.main()
