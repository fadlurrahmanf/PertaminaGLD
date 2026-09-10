#!/usr/bin/env python3
"""Portable loopback MQTT broker for the local Node-RED bench stack.

It deliberately reuses the repository's MQTT 3.1.1 bench implementation and
creates local credentials on first launch. This is not a TLS/production broker.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import secrets
import signal
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BROKER_SOURCE = REPO_ROOT / "apps" / "gld-operator" / "local_mqtt_broker.py"
DEFAULT_RUNTIME_DIR = REPO_ROOT / "apps" / "runtime" / "local-mqtt"


def load_broker_class():
    spec = importlib.util.spec_from_file_location("pgl_local_mqtt_impl", BROKER_SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load MQTT broker implementation: {BROKER_SOURCE}")
    module = importlib.util.module_from_spec(spec)
    # dataclass resolves its module through sys.modules while the implementation
    # is being executed, so register the dynamic module before exec_module().
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.LocalMqttBroker


def atomic_json_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_credentials(path: Path, host: str, port: int, default_user: str) -> dict:
    previous: dict = {}
    if path.exists():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                previous = parsed
        except (OSError, json.JSONDecodeError):
            previous = {}
    username = str(previous.get("username") or default_user).strip() or default_user
    password = str(previous.get("password") or "")
    if len(password) < 16:
        password = secrets.token_urlsafe(24)
    credentials = {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "topicRoot": str(previous.get("topicRoot") or "gld/gateway"),
    }
    atomic_json_write(path, credentials)
    return credentials


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=1884, type=int)
    parser.add_argument("--username", default="pgl_local")
    parser.add_argument("--credentials-file", type=Path,
                        default=DEFAULT_RUNTIME_DIR / "credentials.local.json")
    parser.add_argument("--status-file", type=Path,
                        default=DEFAULT_RUNTIME_DIR / "status.local.json")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        raise ValueError("MQTT port must be in 1..65535")

    credentials = load_credentials(args.credentials_file, args.host, args.port, args.username)
    status = {
        "running": False,
        "pid": None,
        "host": args.host,
        "port": args.port,
        "credentialsFile": str(args.credentials_file),
        "startedAt": None,
        "lastEvent": "starting",
        "events": [],
        "clients": [],
    }
    clients: set[str] = set()

    def write_status(event: str) -> None:
        status["lastEvent"] = event
        status["clients"] = sorted(clients)
        atomic_json_write(args.status_file, status)

    def log(message: str) -> None:
        print(message, flush=True)
        events = status["events"]
        events.append(message)
        del events[:-40]
        if message.startswith("MQTT_BROKER_CONNECT client="):
            client = message.split("client=", 1)[1].split(" ", 1)[0]
            if client:
                clients.add(client)
        elif message.startswith("MQTT_BROKER_DISCONNECT client="):
            client = message.split("client=", 1)[1].split(" ", 1)[0]
            clients.discard(client)
        write_status(message)

    broker_class = load_broker_class()
    broker = broker_class(args.host, args.port, log=log,
                           username=credentials["username"], password=credentials["password"])

    def stop(*_unused: object) -> None:
        broker.stop()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        broker.start()
        status["running"] = True
        status["pid"] = __import__("os").getpid()
        status["startedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        write_status("ready")
        print(f"LOCAL_MQTT_READY host={args.host} port={args.port} credentials={args.credentials_file}", flush=True)
        while broker.running:
            time.sleep(0.25)
    finally:
        broker.stop()
        status["running"] = False
        status["pid"] = None
        write_status("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
