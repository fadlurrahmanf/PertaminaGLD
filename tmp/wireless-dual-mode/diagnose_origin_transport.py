"""Bounded loopback-only probe of early-origin rejection transport behavior."""
import importlib.util
import json
import socket
import threading
from http.client import HTTPResponse
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("origin_transport_probe_bridge", ROOT / "apps/gld-operator/bridge.py")
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)
observed = []

class Handler(bridge.Handler):
    def log_message(self, *_args):
        pass
    def _request_error(self, exc):
        observed.append({"status": int(exc.status), "remaining_request_bytes":
            int(self.headers.get("Content-Length", 0)), "read_json_reached": False})
        super()._request_error(exc)

def attempt(kind, port):
    headers = {"Content-Type": "application/json", "Origin": "https://untrusted.invalid",
               "X-GLD-Bridge-Token": bridge.BRIDGE_CSRF_TOKEN}
    if kind == "one_send_post_json":
        wire = (f"POST /api/wireless-dataset/connect HTTP/1.1\r\nHost:127.0.0.1:{port}\r\n"
                f"Origin: https://untrusted.invalid\r\nX-GLD-Bridge-Token: {bridge.BRIDGE_CSRF_TOKEN}\r\n"
                "Content-Type: application/json\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}").encode()
        with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
            client.sendall(wire)
            response = HTTPResponse(client)
            response.begin()
            value = json.loads(response.read())
            return response.status, value["error"]
    body = b"{}" if kind == "urllib_post_json" else b""
    request = Request(f"http://127.0.0.1:{port}/api/wireless-dataset/connect", data=body,
                      headers=headers, method="POST")
    try:
        with urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())["error"]

server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
report = {"scope": "loopback-only", "cases": {}}
try:
    with patch.object(bridge, "get_wireless_dataset_collector") as collector, patch.object(bridge, "read_json", side_effect=AssertionError("must reject before body parser")):
        for kind in ("urllib_post_json", "urllib_post_empty", "one_send_post_json"):
            outcomes = {}
            for _ in range(30):
                try:
                    status, detail = attempt(kind, server.server_port)
                    key = str(status) + ":" + detail
                except Exception as exc:
                    key = type(exc).__name__ + ":" + str(getattr(exc, "winerror", None))
                outcomes[key] = outcomes.get(key, 0) + 1
            report["cases"][kind] = outcomes
        report["collector_calls"] = collector.call_count
        report["server_rejected_403_count"] = len(observed)
        report["request_lengths"] = sorted({item["remaining_request_bytes"] for item in observed})
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
target = Path(__file__).with_name("origin-transport-diagnosis.json")
target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
