#!/usr/bin/env python3
"""Authenticated, request-only reverse proxy for the Pertamina GLD dashboard."""

from __future__ import annotations

import argparse
import base64
import binascii
import hmac
import http.client
import json
import re
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, quote, urlsplit
from urllib.request import Request, urlopen


VIEW_PATH = "/pertamina-gld/topology/view"
TOPOLOGY_PATH = "/pertamina-gld/topology"
REQUEST_PATH = "/pertamina-gld/topology/request"
CH_RE = re.compile(r"^(?:0x)?([0-9a-fA-F]{1,4})$")
MAX_BODY_BYTES = 8192


@dataclass(frozen=True)
class Settings:
    username: str
    password: str
    bind_host: str = "127.0.0.1"
    bind_port: int = 18790
    origin_host: str = "127.0.0.1"
    origin_port: int = 1880
    request_cooldown_sec: int = 20
    audit_log: str = ""

    @classmethod
    def from_file(cls, path: Path) -> "Settings":
        raw = json.loads(path.read_text(encoding="utf-8"))
        username = str(raw.get("username", "")).strip()
        password = str(raw.get("password", ""))
        if not username or len(password) < 16:
            raise ValueError("remote username is required and password must be at least 16 characters")
        return cls(
            username=username,
            password=password,
            bind_host=str(raw.get("bind_host", "127.0.0.1")),
            bind_port=int(raw.get("bind_port", 18790)),
            origin_host=str(raw.get("origin_host", "127.0.0.1")),
            origin_port=int(raw.get("origin_port", 1880)),
            request_cooldown_sec=max(1, int(raw.get("request_cooldown_sec", 20))),
            audit_log=str(raw.get("audit_log", "")),
        )


class RemoteAccessServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, settings: Settings):
        super().__init__(address, handler)
        self.settings = settings
        self._state_lock = threading.Lock()
        self._last_request_at = 0.0
        self._last_request_by_ch: dict[str, float] = {}

    def reserve_request(self, ch: str) -> int:
        now = time.monotonic()
        with self._state_lock:
            last = max(self._last_request_at, self._last_request_by_ch.get(ch, 0.0))
            remaining = self.settings.request_cooldown_sec - (now - last)
            if remaining > 0:
                return max(1, int(remaining + 0.999))
            self._last_request_at = now
            self._last_request_by_ch[ch] = now
            return 0

    def audit(self, event: str, **fields) -> None:
        if not self.settings.audit_log:
            return
        record = {
            "at": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **fields,
        }
        line = json.dumps(record, separators=(",", ":"), ensure_ascii=True) + "\n"
        path = Path(self.settings.audit_log)
        with self._state_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="") as handle:
                handle.write(line)


class RemoteAccessHandler(BaseHTTPRequestHandler):
    server: RemoteAccessServer
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/":
            if not self._authenticate():
                return
            self.send_response(302)
            self.send_header("Location", VIEW_PATH)
            self.send_header("Content-Length", "0")
            self._security_headers()
            self.end_headers()
            return
        if parsed.path not in {VIEW_PATH, TOPOLOGY_PATH}:
            self._deny(404, "route-not-exposed")
            return
        if not self._authenticate():
            return
        self._forward("GET")

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path != REQUEST_PATH:
            self._deny(404, "route-not-exposed")
            return
        if not self._authenticate():
            return
        if not self._same_origin_post():
            self._deny(403, "cross-site-request-blocked")
            return
        ch = self._validated_ch(parsed.query)
        if ch is None:
            self._deny(400, "invalid-ch-id")
            return
        retry_after = self.server.reserve_request(ch)
        if retry_after:
            self.send_response(429)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Retry-After", str(retry_after))
            payload = json.dumps({"ok": False, "reason": "remote-request-rate-limited", "retryAfterSec": retry_after}).encode()
            self.send_header("Content-Length", str(len(payload)))
            self._security_headers()
            self.end_headers()
            self.wfile.write(payload)
            self.server.audit("request-rate-limited", ip=self._client_ip(), ch=ch, retryAfterSec=retry_after)
            return
        self.server.audit("request-forwarded", ip=self._client_ip(), ch=ch)
        self._forward("POST")

    def _authenticate(self) -> bool:
        header = self.headers.get("Authorization", "")
        supplied_user = ""
        supplied_password = ""
        if header.startswith("Basic "):
            try:
                decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
                supplied_user, supplied_password = decoded.split(":", 1)
            except (ValueError, UnicodeDecodeError, binascii.Error):
                pass
        settings = self.server.settings
        valid = hmac.compare_digest(supplied_user, settings.username) and hmac.compare_digest(
            supplied_password, settings.password
        )
        if valid:
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Pertamina GLD Remote", charset="UTF-8"')
        payload = b"Authentication required\n"
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(payload)
        self.server.audit("auth-denied", ip=self._client_ip())
        return False

    def _same_origin_post(self) -> bool:
        fetch_site = self.headers.get("Sec-Fetch-Site", "").lower()
        if fetch_site and fetch_site not in {"same-origin", "none"}:
            return False
        origin = self.headers.get("Origin", "")
        if not origin:
            return True
        public_host = self.headers.get("Host", "")
        public_proto = self.headers.get("X-Forwarded-Proto", "https")
        return hmac.compare_digest(origin.rstrip("/"), f"{public_proto}://{public_host}")

    @staticmethod
    def _validated_ch(query: str) -> str | None:
        values = parse_qs(query, keep_blank_values=True).get("ch", [])
        if len(values) != 1:
            return None
        match = CH_RE.fullmatch(values[0].strip())
        if not match:
            return None
        value = int(match.group(1), 16)
        if value < 0x0010 or value > 0x0FFF:
            return None
        return f"0x{value:04X}"

    def _forward(self, method: str) -> None:
        length_raw = self.headers.get("Content-Length", "0")
        try:
            length = int(length_raw)
        except ValueError:
            self._deny(400, "invalid-content-length")
            return
        if length < 0 or length > MAX_BODY_BYTES:
            self._deny(413, "request-body-too-large")
            return
        body = self.rfile.read(length) if length else None
        headers = {"Accept": self.headers.get("Accept", "*/*")}
        content_type = self.headers.get("Content-Type")
        if content_type:
            headers["Content-Type"] = content_type
        connection = http.client.HTTPConnection(
            self.server.settings.origin_host,
            self.server.settings.origin_port,
            timeout=8,
        )
        try:
            connection.request(method, self.path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read()
            response_type = response.getheader("Content-Type", "application/octet-stream")
            if self.path.startswith(VIEW_PATH) and "text/html" in response_type:
                payload = self._make_remote_safe(payload)
            self.send_response(response.status)
            self.send_header("Content-Type", response_type)
            self.send_header("Content-Length", str(len(payload)))
            retry_after = response.getheader("Retry-After")
            if retry_after:
                self.send_header("Retry-After", retry_after)
            self._security_headers()
            self.end_headers()
            self.wfile.write(payload)
        except (OSError, http.client.HTTPException) as exc:
            self.server.audit("origin-error", ip=self._client_ip(), detail=type(exc).__name__)
            self._deny(502, "origin-unavailable")
        finally:
            connection.close()

    @staticmethod
    def _make_remote_safe(payload: bytes) -> bytes:
        marker = b"</head>"
        if marker not in payload:
            return payload
        injection = b"""<style>#resetRouting{display:none!important}.pgl-remote-banner{padding:8px 12px;margin:8px 0;background:#17324d;color:#d9efff;border:1px solid #3d7cab;border-radius:6px;font:600 13px system-ui}</style><script>(function(){function secure(){var h=document.querySelector('h1');if(h&&!document.querySelector('.pgl-remote-banner')){var b=document.createElement('div');b.className='pgl-remote-banner';b.textContent='REMOTE SECURE - Monitoring dan Request GLD saja';h.parentNode.insertBefore(b,h.nextSibling)}document.querySelectorAll('button').forEach(function(x){if(x.textContent.trim()==='Hapus'||x.id==='resetRouting')x.style.display='none'})}new MutationObserver(secure).observe(document.documentElement,{childList:true,subtree:true});document.addEventListener('DOMContentLoaded',secure);secure()})();</script></head>"""
        return payload.replace(marker, injection, 1)

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
        )

    def _deny(self, status: int, reason: str) -> None:
        payload = json.dumps({"ok": False, "reason": reason}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(payload)
        self.server.audit("route-denied", ip=self._client_ip(), method=self.command, path=urlsplit(self.path).path, reason=reason)

    def _client_ip(self) -> str:
        return (
            self.headers.get("CF-Connecting-IP")
            or self.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
            or self.client_address[0]
        )


def initialize_config(path: Path) -> dict[str, str]:
    if path.exists():
        raise FileExistsError(f"refusing to replace existing credentials: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    password = secrets.token_urlsafe(24)
    config = {
        "username": "operator",
        "password": password,
        "bind_host": "127.0.0.1",
        "bind_port": 18790,
        "origin_host": "127.0.0.1",
        "origin_port": 1880,
        "request_cooldown_sec": 20,
        "audit_log": str(path.parent / "audit.jsonl"),
    }
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return {"username": config["username"], "password": password}


def self_test(settings: Settings, base: str = "") -> dict[str, object]:
    base = base.rstrip("/") or f"http://{settings.bind_host}:{settings.bind_port}"
    token = base64.b64encode(f"{settings.username}:{settings.password}".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}
    with urlopen(Request(base + VIEW_PATH, headers=headers), timeout=5) as response:
        view_status = response.status
        remote_banner = b"REMOTE SECURE" in response.read()
    try:
        urlopen(Request(base + "/flows", headers=headers), timeout=5)
        flows_status = 200
    except HTTPError as exc:
        flows_status = exc.code
    try:
        urlopen(Request(base + TOPOLOGY_PATH), timeout=5)
        unauthenticated_status = 200
    except HTTPError as exc:
        unauthenticated_status = exc.code
    return {
        "viewStatus": view_status,
        "remoteBanner": remote_banner,
        "flowsStatus": flows_status,
        "unauthenticatedStatus": unauthenticated_status,
    }


def remote_request_test(settings: Settings, base: str, ch: str) -> dict[str, object]:
    base = base.rstrip("/")
    normalized_ch = RemoteAccessHandler._validated_ch("ch=" + quote(ch))
    if not normalized_ch:
        raise ValueError("invalid CH ID")
    token = base64.b64encode(f"{settings.username}:{settings.password}".encode()).decode()
    headers = {
        "Authorization": f"Basic {token}",
        "Origin": base,
        "Sec-Fetch-Site": "same-origin",
        "Content-Type": "application/json",
    }
    request = Request(
        base + REQUEST_PATH + "?ch=" + quote(normalized_ch),
        data=b"",
        method="POST",
        headers=headers,
    )
    with urlopen(request, timeout=10) as response:
        submitted = json.loads(response.read())
    request_id = submitted.get("requestId")
    deadline = time.monotonic() + 25
    latest = None
    while time.monotonic() < deadline:
        with urlopen(Request(base + TOPOLOGY_PATH, headers={"Authorization": f"Basic {token}"}), timeout=10) as response:
            topology = json.loads(response.read())
        latest = (topology.get("gldDiscovery") or {}).get(normalized_ch)
        if latest and latest.get("requestId") == request_id and latest.get("status") in {"received", "timeout"}:
            break
        time.sleep(1)
    return {
        "submitted": bool(submitted.get("ok")),
        "ch": normalized_ch,
        "requestId": request_id,
        "status": latest.get("status") if latest else None,
        "responseStatus": latest.get("responseStatus") if latest else None,
        "recordCount": latest.get("recordCount") if latest else None,
        "deviceCount": latest.get("deviceCount") if latest else None,
        "gldNodeCount": topology.get("gldNodeCount") if "topology" in locals() else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path)
    parser.add_argument("--init-config", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--self-test-base", default="")
    parser.add_argument("--request-ch", default="")
    args = parser.parse_args()
    if args.init_config:
        print(json.dumps(initialize_config(args.init_config)))
        return 0
    if not args.config:
        parser.error("--config is required unless --init-config is used")
    settings = Settings.from_file(args.config)
    if args.self_test:
        print(json.dumps(self_test(settings, args.self_test_base)))
        return 0
    if args.request_ch:
        if not args.self_test_base:
            parser.error("--request-ch requires --self-test-base")
        print(json.dumps(remote_request_test(settings, args.self_test_base, args.request_ch)))
        return 0
    server = RemoteAccessServer((settings.bind_host, settings.bind_port), RemoteAccessHandler, settings)
    print(json.dumps({"ready": True, "bind": f"http://{settings.bind_host}:{settings.bind_port}"}), flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
