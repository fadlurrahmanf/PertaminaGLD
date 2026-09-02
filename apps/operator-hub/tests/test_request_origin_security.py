from __future__ import annotations

import http.client
import importlib.util
import json
import sys
import threading
import unittest
from contextlib import contextmanager
from email.message import Message
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path


HUB_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HUB_DIR))
SPEC = importlib.util.spec_from_file_location("operator_hub_security_bridge", HUB_DIR / "bridge.py")
assert SPEC and SPEC.loader
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


@contextmanager
def running_hub():
    server = ThreadingHTTPServer(("127.0.0.1", 0), bridge.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def hub_request(
    port: int,
    path: str,
    *,
    host: str,
    origin: str | None = None,
    method: str = "GET",
    token: str | None = None,
) -> tuple[int, dict[str, object]]:
    headers = {"Host": host}
    if origin is not None:
        headers["Origin"] = origin
    body = None
    if token is not None:
        headers["X-Operator-Hub-Token"] = token

    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        return response.status, payload
    finally:
        connection.close()


class RequestAuthoritySecurityTests(unittest.TestCase):
    def test_bootstrap_accepts_only_exact_loopback_authorities_on_bound_port(self) -> None:
        with running_hub() as port:
            for authority in (f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"):
                with self.subTest(authority=authority):
                    status, payload = hub_request(port, "/api/simple/bootstrap", host=authority)
                    self.assertEqual(status, HTTPStatus.OK)
                    self.assertEqual(payload["apiToken"], bridge.HUB_API_TOKEN)

    def test_bootstrap_rejects_hostile_missing_or_wrong_port_host_without_leaking_token(self) -> None:
        with running_hub() as port:
            invalid_authorities = (
                f"attacker.example:{port}",
                f"localhost:{port + 1}",
                "localhost",
                f"127.0.0.2:{port}",
                f"[0:0:0:0:0:0:0:1]:{port}",
            )
            for authority in invalid_authorities:
                with self.subTest(authority=authority):
                    status, payload = hub_request(port, "/api/simple/bootstrap", host=authority)
                    self.assertEqual(status, HTTPStatus.MISDIRECTED_REQUEST)
                    self.assertNotIn("apiToken", payload)

    def test_bootstrap_allows_matching_origin_and_rejects_cross_origin_aliases(self) -> None:
        with running_hub() as port:
            authority = f"localhost:{port}"
            status, payload = hub_request(
                port,
                "/api/simple/bootstrap",
                host=authority,
                origin=f"http://{authority}",
            )
            self.assertEqual(status, HTTPStatus.OK)
            self.assertIn("apiToken", payload)

            for origin in (
                f"http://127.0.0.1:{port}",
                f"http://attacker.example:{port}",
                f"http://localhost:{port + 1}",
                f"http://{authority}/",
                "null",
            ):
                with self.subTest(origin=origin):
                    status, payload = hub_request(
                        port,
                        "/api/simple/bootstrap",
                        host=authority,
                        origin=origin,
                    )
                    self.assertEqual(status, HTTPStatus.FORBIDDEN)
                    self.assertNotIn("apiToken", payload)

    def test_token_bearing_post_checks_authority_before_token_or_body_dispatch(self) -> None:
        with running_hub() as port:
            status, payload = hub_request(
                port,
                "/api/simple/disconnect",
                host=f"attacker.example:{port}",
                method="POST",
                token=bridge.HUB_API_TOKEN,
            )
            self.assertEqual(status, HTTPStatus.MISDIRECTED_REQUEST)
            self.assertIn("Host", str(payload.get("error")))

            status, payload = hub_request(
                port,
                "/api/simple/disconnect",
                host=f"127.0.0.1:{port}",
                origin=f"http://attacker.example:{port}",
                method="POST",
                token=bridge.HUB_API_TOKEN,
            )
            self.assertEqual(status, HTTPStatus.FORBIDDEN)
            self.assertIn("Origin", str(payload.get("error")))

    def test_duplicate_host_header_is_rejected(self) -> None:
        headers = Message()
        headers.add_header("Host", "localhost:5173")
        headers.add_header("Host", "attacker.example:5173")
        failure = bridge.validate_hub_request_headers(headers, 5173)
        self.assertIsNotNone(failure)
        assert failure is not None
        self.assertEqual(failure[0], HTTPStatus.MISDIRECTED_REQUEST)


if __name__ == "__main__":
    unittest.main()
