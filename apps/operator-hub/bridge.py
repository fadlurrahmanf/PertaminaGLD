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
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HUB_DIR = Path(__file__).resolve().parent
if str(HUB_DIR) not in sys.path:
    # Embedded Python commonly runs in isolated mode and omits the script
    # directory from sys.path, so add this local module directory explicitly.
    sys.path.insert(0, str(HUB_DIR))

from preflight import print_report, run_preflight

APPS_DIR = HUB_DIR.parent
# Only this directory is served over HTTP. bridge.py, preflight.py,
# firmware-packages/, and the README stay outside the web root.
PUBLIC_DIR = HUB_DIR / "public"
# Kept outside apps/operator-hub entirely so it can never be served, even by
# mistake, alongside the static UI.
RUNTIME_DIR = APPS_DIR / "runtime" / "operator-hub"
BROKER_CREDENTIALS_PATH = RUNTIME_DIR / "credentials.local.json"

# The child bridges accept unauthenticated serial, MQTT, and firmware-flash
# commands from same-origin requests. Binding any of them - and therefore the
# Hub that forwards its own --host to them - to a LAN-reachable address would
# expose all of that to the network. Loopback only, always.
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

CHILD_APPS = {
    "gld": {
        "dir": APPS_DIR / "gld-operator",
        "port": 5174,
        "extra_args": [],
        "label": "GLD Operator",
        "appId": "gld-operator",
    },
    "ch": {
        "dir": APPS_DIR / "ch-operator",
        "port": 5273,
        "extra_args": [],
        "label": "CH Operator",
        "appId": "ch-operator",
    },
    "gw": {
        "dir": APPS_DIR / "gw-operator",
        "port": 5373,
        "extra_args": [],
        "label": "Gateway Operator",
        "appId": "gw-operator",
    },
}

CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
child_processes: dict[str, subprocess.Popen] = {}
mqtt_degraded = False


def validate_host(host: str) -> str:
    if host not in LOOPBACK_HOSTS:
        print(
            f"HUB_REFUSED_HOST {host}: Operator Hub only binds to loopback "
            "(127.0.0.1/localhost/::1). The child bridges accept unauthenticated "
            "serial, MQTT, and firmware-flash requests same-origin, so binding to "
            "a LAN address or 0.0.0.0 would expose that to the network. A LAN mode "
            "would need its own authentication and HTTPS, which does not exist yet."
        )
        sys.exit(2)
    return host


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


def local_ipv4() -> str | None:
    """Best-effort LAN IPv4 address, or None if no LAN is reachable.

    This used to raise, which took the whole Hub down whenever a laptop had
    Wi-Fi off - even though GLD/CH serial consoles don't need MQTT at all.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        value = sock.getsockname()[0]
        if value and not value.startswith("127."):
            return value
    except OSError:
        pass
    finally:
        sock.close()
    return None


def load_or_create_broker_config() -> dict[str, object] | None:
    """Return broker config, or None if no LAN IPv4 is available (degraded mode)."""
    host = local_ipv4()
    if host is None:
        return None

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
        "host": host,
        "port": int(config.get("port") or 1884),
        "username": username,
        "password": password,
        "topicRoot": str(config.get("topicRoot") or "gld/gateway"),
    }
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    BROKER_CREDENTIALS_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def launch_children(host: str, broker: dict[str, object] | None) -> None:
    for name, cfg in CHILD_APPS.items():
        app_dir: Path = cfg["dir"]
        if not (app_dir / "bridge.py").exists():
            print(f"HUB_SKIP {name}: {app_dir} has no bridge.py")
            continue
        python_exe = _python_for(app_dir)
        extra_args = list(cfg["extra_args"])
        child_env = os.environ.copy()
        if broker is None:
            # No LAN IPv4 available: GLD/CH serial consoles still work fine
            # without MQTT, so they still launch - just without broker args/env.
            if name == "gw":
                print(f"HUB_DEGRADED {name}: no LAN IPv4 detected, MQTT is unavailable")
        elif name == "gld":
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


def check_health(host: str, port: int, expected_app_id: str) -> dict[str, object]:
    """Probe a child bridge and verify it's actually ours, not some other
    service that happens to be listening on the port."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/health", timeout=1.5) as resp:
            if resp.status != 200:
                return {"up": False, "identityOk": False}
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {"up": False, "identityOk": False}
    if not isinstance(payload, dict):
        return {"up": True, "identityOk": False}
    app_id = payload.get("appId")
    return {
        "up": True,
        "identityOk": app_id == expected_app_id,
        "appId": app_id,
        "version": payload.get("version"),
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        pass

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] == "/api/status":
            self._handle_status()
            return
        if self.path.split("?", 1)[0] == "/api/preflight":
            self._handle_preflight()
            return
        super().do_GET()

    def _handle_preflight(self) -> None:
        # Recomputed on every request rather than cached from startup, so a
        # package that goes bad (or gets fixed) after launch is reflected here.
        host = self.server.server_address[0] or "127.0.0.1"
        port = self.server.server_address[1]
        report = run_preflight(host, port)
        body = json.dumps(report).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _handle_status(self) -> None:
        host = self.server.server_address[0] or "127.0.0.1"
        results: dict[str, dict[str, object]] = {}
        lock = threading.Lock()

        def probe(name: str, port: int, expected_app_id: str) -> None:
            result = check_health(host, port, expected_app_id)
            with lock:
                results[name] = result

        threads = [
            threading.Thread(target=probe, args=(name, cfg["port"], cfg["appId"]))
            for name, cfg in CHILD_APPS.items()
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2.5)

        body = json.dumps({"apps": results, "mqttDegraded": mqtt_degraded}).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def _wait_for_children_health(host: str, timeout: float = 5.0) -> None:
    """Give freshly-launched children a moment to answer /api/health before
    opening the browser, instead of a fixed blind sleep."""
    deadline = time.monotonic() + timeout
    pending = set(child_processes.keys())
    while pending and time.monotonic() < deadline:
        for name in list(pending):
            cfg = CHILD_APPS[name]
            if check_health(host, cfg["port"], cfg["appId"]).get("up"):
                pending.discard(name)
        if pending:
            time.sleep(0.25)


def _install_signal_handlers() -> None:
    def _handle(signum, frame):
        raise KeyboardInterrupt

    for sig_name in ("SIGTERM", "SIGBREAK"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                signal.signal(sig, _handle)
            except (ValueError, OSError):
                pass


def main() -> int:
    global mqtt_degraded
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="loopback address to bind: 127.0.0.1, localhost, or ::1 (no LAN/0.0.0.0)")
    parser.add_argument("--port", default=5173, type=int)
    parser.add_argument("--no-children", action="store_true", help="don't spawn gld/ch/gw bridges (assume already running)")
    parser.add_argument("--open-browser", action="store_true", help="open the Operator Hub in the default browser after binding the server socket")
    args = parser.parse_args()

    # 1. Validate configuration.
    host = validate_host(args.host)
    preflight = run_preflight(host, args.port)
    print_report(preflight)
    if any(check["id"] == "hub-port" and check["state"] == "error" for check in preflight["checks"]):
        return 2

    # 2. Bind the Hub itself before touching anything else, so a failure here
    #    never leaves an orphaned child process behind.
    try:
        httpd = ThreadingHTTPServer((host, args.port), Handler)
    except OSError as exc:
        print(f"HUB_BIND_FAILED {host}:{args.port}: {exc}")
        return 2

    _install_signal_handlers()
    try:
        if not args.no_children:
            # 3. Launch children. Broker setup is isolated in its own
            #    try/except: a broker failure must not block GLD/CH serial,
            #    which don't need MQTT at all.
            try:
                broker = load_or_create_broker_config()
            except Exception as exc:
                print(f"HUB_MQTT_BROKER_ERROR {exc}")
                broker = None
            mqtt_degraded = broker is None
            if broker is not None:
                print(f"HUB_MQTT_BROKER host={broker['host']} port={broker['port']} user={broker['username']} auth=1")
            else:
                print("HUB_MQTT_DEGRADED no LAN IPv4 detected; Gateway/MQTT is unavailable, GLD/CH serial still work")
            launch_children(host, broker)
            # 4. Wait for health before opening the browser.
            _wait_for_children_health(host)

        url = f"http://{host}:{args.port}/"
        print(f"Operator Hub: {url}")
        if args.open_browser and not webbrowser.open(url):
            print(f"HUB_BROWSER_OPEN_FAILED Open this URL manually: {url}")
        print("Press Ctrl+C to stop (this also stops the GLD/CH/Gateway bridges it launched).")
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
