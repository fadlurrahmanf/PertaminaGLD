#!/usr/bin/env python3
"""Operator Hub: single entry point that launches the GLD, CH, and Gateway
operator bridges as child processes and serves a tab-switcher UI that iframes
each one on its own port.

This process does not touch serial ports, MQTT, or firmware upload itself -
it only spawns the three existing bridge.py scripts (each already a complete,
independently launchable app) and reports their /api/health status to the UI
via /api/status, since the browser can't read that cross-origin (each child's
CORS allowlist is same-origin only).
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HUB_DIR = Path(__file__).resolve().parent
APPS_DIR = HUB_DIR.parent
BROKER_CREDENTIALS_PATH = HUB_DIR / "credentials.local.json"

CHILD_APPS = {
    "gld": {
        "dir": APPS_DIR / "gld-operator",
        "port": 5174,
        "extra_args": [],
        "label": "GLD Operator",
    },
    "ch": {
        "dir": APPS_DIR / "ch-operator",
        "port": 5273,
        "extra_args": [],
        "label": "CH Operator",
    },
    "gw": {
        "dir": APPS_DIR / "gw-operator",
        "port": 5373,
        "extra_args": [],
        "label": "Gateway Operator",
    },
}

CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
child_processes: dict[str, subprocess.Popen] = {}


def _python_for(app_dir: Path) -> str:
    candidates = [
        app_dir / "python-embed" / "python.exe",
        APPS_DIR / "gld-operator" / "python-embed" / "python.exe",
        APPS_DIR / "ch-operator" / "python-embed" / "python.exe",
    ]
    for embedded in candidates:
        if embedded.exists():
            return str(embedded)
    return "python"


def local_ipv4() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        value = sock.getsockname()[0]
        if value and not value.startswith("127."):
            return value
    finally:
        sock.close()
    raise RuntimeError("no active LAN IPv4 address is available for the MQTT broker")


def load_or_create_broker_config() -> dict[str, object]:
    config: dict[str, object] = {}
    if BROKER_CREDENTIALS_PATH.exists():
        try:
            loaded = json.loads(BROKER_CREDENTIALS_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                config = loaded
        except (OSError, json.JSONDecodeError):
            config = {}

    username = str(config.get("username") or "pgl_operator")
    password = str(config.get("password") or "")
    if len(password) < 16:
        password = secrets.token_urlsafe(24)
    result: dict[str, object] = {
        "host": local_ipv4(),
        "port": int(config.get("port") or 1884),
        "username": username,
        "password": password,
        "topicRoot": str(config.get("topicRoot") or "gld/gateway"),
    }
    BROKER_CREDENTIALS_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def launch_children(host: str, broker: dict[str, object]) -> None:
    for name, cfg in CHILD_APPS.items():
        app_dir: Path = cfg["dir"]
        if not (app_dir / "bridge.py").exists():
            print(f"HUB_SKIP {name}: {app_dir} has no bridge.py")
            continue
        python_exe = _python_for(app_dir)
        extra_args = list(cfg["extra_args"])
        child_env = os.environ.copy()
        if name == "gld":
            extra_args.extend([
                "--mqtt-broker-host", str(broker["host"]),
                "--mqtt-broker-port", str(broker["port"]),
            ])
            child_env.update({
                "GLD_BENCH_MQTT_USER": str(broker["username"]),
                "GLD_BENCH_MQTT_PASSWORD": str(broker["password"]),
            })
        elif name == "gw":
            child_env.update({
                "PGL_OPERATOR_MQTT_HOST": str(broker["host"]),
                "PGL_OPERATOR_MQTT_PORT": str(broker["port"]),
                "PGL_OPERATOR_MQTT_USER": str(broker["username"]),
                "PGL_OPERATOR_MQTT_PASSWORD": str(broker["password"]),
                "PGL_OPERATOR_MQTT_TOPIC_ROOT": str(broker["topicRoot"]),
            })
        cmd = [python_exe, "bridge.py", "--host", host, "--port", str(cfg["port"]), *extra_args]
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(app_dir),
                env=child_env,
                creationflags=CREATE_NEW_PROCESS_GROUP,
            )
            child_processes[name] = proc
            print(f"HUB_LAUNCHED {cfg['label']} pid={proc.pid} port={cfg['port']}")
        except Exception as exc:
            print(f"HUB_LAUNCH_FAILED {name}: {exc}")


def shutdown_children() -> None:
    for name, proc in child_processes.items():
        if proc.poll() is not None:
            continue
        try:
            if CREATE_NEW_PROCESS_GROUP and hasattr(signal, "CTRL_BREAK_EVENT"):
                proc.send_signal(signal.CTRL_BREAK_EVENT)
                proc.wait(timeout=5)
            else:
                proc.terminate()
                proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        print(f"HUB_STOPPED {name}")


def check_health(host: str, port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/health", timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HUB_DIR), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        pass

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] == "/api/status":
            self._handle_status()
            return
        super().do_GET()

    def _handle_status(self) -> None:
        host = self.server.server_address[0] or "127.0.0.1"
        results: dict[str, bool] = {}
        lock = threading.Lock()

        def probe(name: str, port: int) -> None:
            up = check_health(host, port)
            with lock:
                results[name] = up

        threads = [
            threading.Thread(target=probe, args=(name, cfg["port"]))
            for name, cfg in CHILD_APPS.items()
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2.5)

        body = json.dumps({"apps": results}).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=5173, type=int)
    parser.add_argument("--no-children", action="store_true", help="don't spawn gld/ch/gw bridges (assume already running)")
    args = parser.parse_args()

    if not args.no_children:
        broker = load_or_create_broker_config()
        print(f"HUB_MQTT_BROKER host={broker['host']} port={broker['port']} user={broker['username']} auth=1")
        launch_children(args.host, broker)
        time.sleep(1.0)

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Operator Hub: {url}")
    print("Press Ctrl+C to stop (this also stops the GLD/CH/Gateway bridges it launched).")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        if not args.no_children:
            shutdown_children()
    return 0


if __name__ == "__main__":
    sys.exit(main())
