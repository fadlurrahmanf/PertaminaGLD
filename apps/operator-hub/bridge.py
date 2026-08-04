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
import urllib.error
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
HUB_API_TOKEN = secrets.token_urlsafe(32)
simple_activity: list[dict[str, object]] = []
simple_activity_lock = threading.Lock()


def json_response(handler: SimpleHTTPRequestHandler, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler: SimpleHTTPRequestHandler, limit: int = 16 * 1024) -> dict[str, object]:
    raw_length = handler.headers.get("Content-Length", "0")
    try:
        length = int(raw_length)
    except ValueError as exc:
        raise ValueError("invalid Content-Length") from exc
    if length < 2 or length > limit:
        raise ValueError("invalid request size")
    parsed = json.loads(handler.rfile.read(length).decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("JSON object required")
    return parsed


def add_activity(device: str, action: str, detail: str) -> None:
    item = {"time": time.strftime("%H:%M:%S"), "device": device, "action": action, "detail": detail}
    with simple_activity_lock:
        simple_activity.insert(0, item)
        del simple_activity[12:]


def latest_package(device: str) -> dict[str, object]:
    environment = {"gld": "gld", "ch": "ch", "gw": "gw"}[device]
    manifest_path = HUB_DIR / "firmware-packages" / environment / "latest" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {"environment": environment, "firmwareVersion": manifest.get("firmwareVersion"), "protocolVersion": manifest.get("protocolVersion")}


def child_request(host: str, device: str, method: str, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    """Server-side allow-listed proxy. Child CSRF tokens never reach the UI."""
    cfg = CHILD_APPS[device]
    base = f"http://{host}:{cfg['port']}"
    try:
        with urllib.request.urlopen(f"{base}/api/health", timeout=2) as health:
            token = json.loads(health.read().decode("utf-8")).get("csrfToken")
        if not isinstance(token, str) or len(token) < 16:
            raise RuntimeError("child bridge did not provide an API token")
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(f"{base}{path}", data=body, method=method)
        req.add_header("X-GLD-Bridge-Token" if device == "gld" else "X-CH-Bridge-Token" if device == "ch" else "X-GW-Bridge-Token", token)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=12) as response:
            parsed = json.loads(response.read().decode("utf-8"))
            return parsed if isinstance(parsed, dict) else {"result": parsed}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(detail or f"child request failed ({exc.code})") from exc


def recent_matching(host: str, device: str, prefix: str, after: int, timeout: float = 5.0) -> dict[str, object] | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        recent = child_request(host, device, "GET", f"/api/serial/recent?slot=1&after={after}")
        for item in recent.get("lines", []):
            line = str(item.get("line", ""))
            if line.startswith(prefix):
                raw = line[len(prefix):].strip()
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    continue
        time.sleep(0.15)
    return None


def simple_device_state(host: str, device: str, query: bool = False) -> dict[str, object]:
    status = child_request(host, device, "GET", "/api/serial/status?slot=1")
    state: dict[str, object] = {"device": device, "connected": bool(status.get("connected")), "port": status.get("port"), "info": None}
    if not state["connected"]:
        return state
    recent = child_request(host, device, "GET", "/api/serial/recent?slot=1&after=0")
    after = int(recent.get("sequence") or 0)
    if query:
        command = "GET_GATEWAY_ADDRESS" if device == "gw" else "GET_INFO"
        child_request(host, device, "POST", "/api/serial/write", {"slot": 1, "line": command})
    prefix = "GW_GATEWAY_ADDRESS_JSON" if device == "gw" else "GLD_INFO_JSON" if device == "gld" else "CH_INFO_JSON"
    info = recent_matching(host, device, prefix, after if query else 0, 2.5 if query else 0.1)
    if device == "gw" and query and info:
        current = child_request(host, device, "GET", "/api/serial/recent?slot=1&after=0")
        child_request(host, device, "POST", "/api/serial/write", {"slot": 1, "line": "GET_STATUS"})
        runtime = recent_matching(host, device, "GW_STATUS_JSON", int(current.get("sequence") or 0), 2.5)
        if runtime:
            info.update(runtime)
    elif device == "gld" and query and info:
        current = child_request(host, device, "GET", "/api/serial/recent?slot=1&after=0")
        child_request(host, device, "POST", "/api/serial/write", {"slot": 1, "line": "GET_STATUS"})
        runtime = recent_matching(host, device, "GLD_STATUS_JSON", int(current.get("sequence") or 0), 2.5)
        if runtime and "radioReady" not in info:
            lora = runtime.get("lora")
            if isinstance(lora, dict) and isinstance(lora.get("beginState"), (int, float)):
                info["radioReady"] = lora["beginState"] == 0
    state["info"] = info
    return state


def wait_for_readback(host: str, device: str, port: str, timeout: float = 20.0) -> dict[str, object]:
    """After a deliberate reboot/flash, wait for the serial device then read its identity again."""
    deadline = time.monotonic() + timeout
    last_error = "device did not reappear"
    while time.monotonic() < deadline:
        time.sleep(1.0)
        try:
            state = simple_device_state(host, device, query=True)
            if state.get("connected") and state.get("info"):
                return state
        except Exception as exc:
            last_error = str(exc)
        try:
            child_request(host, device, "POST", "/api/serial/disconnect", {"slot": 1})
            child_request(host, device, "POST", "/api/serial/connect", {"slot": 1, "port": port, "baud": 115200})
        except Exception as exc:
            last_error = str(exc)
    raise RuntimeError(f"device did not return for verified read-back: {last_error}")


def send_and_confirm(host: str, device: str, line: str, ack_marker: str) -> dict[str, object]:
    before = child_request(host, device, "GET", "/api/serial/recent?slot=1&after=0")
    sequence = int(before.get("sequence") or 0)
    sent = child_request(host, device, "POST", "/api/serial/write", {"slot": 1, "line": line})
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        recent = child_request(host, device, "GET", f"/api/serial/recent?slot=1&after={sequence}")
        for item in recent.get("lines", []):
            text = str(item.get("line", ""))
            if ack_marker not in text:
                continue
            if "status=error" in text or "status=rejected" in text or '"status":"error"' in text or '"status":"rejected"' in text:
                raise RuntimeError(f"device rejected configuration: {text}")
            return {"sent": sent, "ack": text}
        time.sleep(0.15)
    raise RuntimeError("command sent but no firmware ACK was received; do not assume configuration was saved")


def gld_boot_report(status: dict[str, object]) -> dict[str, object]:
    """Convert the firmware's GLD_STATUS_JSON boot fields into an operator report."""
    boot = status.get("bootHealth") if isinstance(status.get("bootHealth"), dict) else {}
    telemetry = status.get("telemetry") if isinstance(status.get("telemetry"), dict) else {}
    lora = status.get("lora") if isinstance(status.get("lora"), dict) else {}

    def check(label: str, ok: bool | None, detail: str) -> dict[str, object]:
        return {"label": label, "ok": ok, "detail": detail}

    ads_ready = boot.get("adsReady")
    ads_ok = ads_ready if isinstance(ads_ready, bool) else None
    ads_reason = str(boot.get("adsReason") or "")
    ads_detail = "ADS1256 siap" if ads_ok else (
        f"ADS1256 tidak siap{'; ' + ads_reason if ads_reason else ''}" if ads_ok is False else "Belum ada bukti boot ADS1256"
    )

    mcp_values = boot.get("mcpOk")
    mcp_count = sum(value is True for value in mcp_values) if isinstance(mcp_values, list) else boot.get("mcpOkCount")
    mcp_known = isinstance(mcp_count, (int, float))
    mcp_ok = int(mcp_count) >= 8 if mcp_known else None
    mcp_detail = "MCP4725 terdeteksi pada semua 8 kanal" if mcp_ok else (
        f"MCP4725 terdeteksi {int(mcp_count) if mcp_known else '?'}/8; periksa kanal TCA, alamat MCP, dan catu daya" if mcp_ok is False else "Belum ada bukti boot MCP4725"
    )

    control_values = boot.get("mcpControlOk")
    control_count = sum(value is True for value in control_values) if isinstance(control_values, list) else boot.get("mcpControlOkCount")
    control_tested = boot.get("mcpControlTested") is True
    dac_ready = boot.get("dacReady")
    dac_known = control_tested or isinstance(dac_ready, bool)
    dac_ok = (int(control_count) >= 8 if control_tested and isinstance(control_count, (int, float)) else dac_ready) if dac_known else None
    dac_detail = "Uji tulis DAC lulus pada semua kanal" if dac_ok else (
        f"Uji tulis DAC lulus {int(control_count) if isinstance(control_count, (int, float)) else 0}/8" if control_tested else "DAC tidak siap; periksa MCP4725/TCA dan catu daya"
    ) if dac_ok is False else "Belum ada bukti uji DAC"

    begin_state = lora.get("beginState")
    radio_ready = boot.get("radioReady")
    lora_known = isinstance(radio_ready, bool) or isinstance(begin_state, (int, float))
    lora_ok = (radio_ready is True or begin_state == 0) if lora_known else None
    lora_detail = "Radio LoRa siap" if lora_ok else (
        f"Radio LoRa tidak siap; begin state {begin_state}" if lora_ok is False else "Belum ada bukti boot LoRa"
    )

    ml_ready = boot.get("mlReady")
    ml_ok = ml_ready if isinstance(ml_ready, bool) else None
    ml_detail = "Model ML siap" if ml_ok else ("Model ML tidak siap; periksa artefak model dan PSRAM" if ml_ok is False else "Belum ada bukti boot model ML")

    sensor_status = telemetry.get("sensorStatus")
    sensor_valid = telemetry.get("valid")
    sensor_ok = sensor_valid is True and isinstance(sensor_status, list) and len(sensor_status) >= 8 and all(int(value) == 0 for value in sensor_status)
    sensor_known = sensor_valid is True or ads_ok is False or mcp_ok is False
    sensor_detail = "Semua 8 pembacaan sensor valid" if sensor_ok else (
        "Pembacaan sensor belum valid; selesaikan masalah ADS/MCP atau tunggu telemetri" if sensor_known else "Belum ada telemetri sensor setelah boot check"
    )

    checks = [
        check("ADS1256", ads_ok, ads_detail),
        check("MCP4725", mcp_ok, mcp_detail),
        check("DAC Control", dac_ok, dac_detail),
        check("LoRa", lora_ok, lora_detail),
        check("ML Model", ml_ok, ml_detail),
        check("Sensor Read", sensor_ok if sensor_known else None, sensor_detail),
    ]
    passed = sum(item["ok"] is True for item in checks)
    failed = sum(item["ok"] is False for item in checks)
    return {"total": len(checks), "passed": passed, "failed": failed, "unknown": len(checks) - passed - failed, "checks": checks}


def readiness_report(checks: list[dict[str, object]]) -> dict[str, object]:
    passed = sum(item["ok"] is True for item in checks)
    failed = sum(item["ok"] is False for item in checks)
    return {"total": len(checks), "passed": passed, "failed": failed, "unknown": len(checks) - passed - failed, "checks": checks}


def ch_readiness_report(info: object) -> dict[str, object]:
    data = info if isinstance(info, dict) else {}
    radio = data.get("radio") if isinstance(data.get("radio"), dict) else {}
    ch_id = str(data.get("chId") or "")
    root_id = str(data.get("rootGatewayId") or "")
    star_ready = radio.get("starReady") in (1, True)
    mesh_ready = radio.get("meshReady") in (1, True)
    checks = [
        {"label": "CH identity", "ok": bool(ch_id), "detail": ch_id or "CH ID tidak terbaca"},
        {"label": "Root Gateway", "ok": bool(root_id), "detail": root_id or "Root Gateway ID tidak terbaca"},
        {"label": "Radio STAR", "ok": star_ready, "detail": "STAR siap" if star_ready else "Radio STAR tidak siap"},
        {"label": "Radio Mesh", "ok": mesh_ready, "detail": "Mesh siap" if mesh_ready else "Radio Mesh tidak siap"},
    ]
    return readiness_report(checks)


def gateway_readiness_report(info: object) -> dict[str, object]:
    data = info if isinstance(info, dict) else {}
    gateway_id = str(data.get("gatewayId") or "")
    checks = [
        {"label": "Gateway identity", "ok": bool(gateway_id), "detail": gateway_id or "Gateway ID tidak terbaca"},
        {"label": "Radio Mesh", "ok": data.get("meshReady") in (1, True), "detail": "Mesh siap" if data.get("meshReady") in (1, True) else "Mesh tidak siap"},
        {"label": "Wi-Fi", "ok": data.get("wifi") in (1, True), "detail": "Wi-Fi tersambung" if data.get("wifi") in (1, True) else "Wi-Fi belum tersambung"},
        {"label": "MQTT", "ok": data.get("mqtt") in (1, True), "detail": "MQTT tersambung" if data.get("mqtt") in (1, True) else "MQTT belum tersambung"},
    ]
    return readiness_report(checks)


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
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".css": "text/css",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        pass

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/status":
            self._handle_status()
            return
        if path == "/api/preflight":
            self._handle_preflight()
            return
        if path == "/api/simple/bootstrap":
            return json_response(self, {"apiToken": HUB_API_TOKEN, "activity": simple_activity})
        if path == "/api/simple/overview":
            return self._handle_simple_overview()
        if path == "/api/simple/ports":
            return self._handle_simple_ports()
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.headers.get("X-Operator-Hub-Token") != HUB_API_TOKEN:
                return json_response(self, {"error": "invalid API token"}, HTTPStatus.FORBIDDEN)
            payload = read_json(self)
            path = self.path.split("?", 1)[0]
            if path == "/api/simple/connect":
                return self._simple_connect(payload)
            if path == "/api/simple/disconnect":
                return self._simple_disconnect(payload)
            if path == "/api/simple/refresh":
                return self._simple_refresh(payload)
            if path == "/api/simple/test-device":
                return self._simple_test_device(payload)
            if path == "/api/simple/restart":
                return self._simple_command(payload, "RESTART", "restart")
            if path == "/api/simple/config/id":
                return self._simple_config_id(payload)
            if path == "/api/simple/config/star-frequency":
                return self._simple_config_frequency(payload)
            if path == "/api/simple/config/target-ch":
                return self._simple_config_target_ch(payload)
            if path == "/api/simple/config/root-gateway":
                return self._simple_config_root_gateway(payload)
            if path == "/api/simple/config/wifi":
                return self._simple_config_wifi(payload)
            if path == "/api/simple/config/mqtt":
                return self._simple_config_mqtt(payload)
            if path == "/api/simple/firmware/upload":
                return self._simple_firmware_upload(payload)
            return json_response(self, {"error": "not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            device = str(locals().get("payload", {}).get("device") or "hub")
            port = str(locals().get("payload", {}).get("port") or "")
            add_activity(device, "Failed request", f"{port + '; ' if port else ''}{path if 'path' in locals() else 'unknown'}: {exc}")
            return json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _simple_device(self, payload: dict[str, object]) -> str:
        device = str(payload.get("device") or "")
        if device not in CHILD_APPS:
            raise ValueError("device must be gld, ch, or gw")
        return device

    def _simple_connect(self, payload: dict[str, object]) -> None:
        device = self._simple_device(payload)
        port = str(payload.get("port") or "").upper()
        if not port.startswith("COM") or not port[3:].isdigit():
            raise ValueError("valid COM port required")
        host = self.server.server_address[0] or "127.0.0.1"
        child_request(host, device, "POST", "/api/serial/connect", {"slot": 1, "port": port, "baud": 115200})
        state = simple_device_state(host, device, query=True)
        add_activity(device, "Connect", f"{port}; connected and identified")
        json_response(self, state)

    def _simple_disconnect(self, payload: dict[str, object]) -> None:
        device = self._simple_device(payload)
        host = self.server.server_address[0] or "127.0.0.1"
        result = child_request(host, device, "POST", "/api/serial/disconnect", {"slot": 1})
        add_activity(device, "Disconnect", f"{result.get('port') or 'COM'}; serial disconnected")
        json_response(self, result)

    def _simple_refresh(self, payload: dict[str, object]) -> None:
        device = self._simple_device(payload)
        host = self.server.server_address[0] or "127.0.0.1"
        json_response(self, simple_device_state(host, device, query=True))

    def _simple_test_device(self, payload: dict[str, object]) -> None:
        device = self._simple_device(payload)
        host = self.server.server_address[0] or "127.0.0.1"
        state = simple_device_state(host, device, query=True)
        if not state.get("connected") or not state.get("info"):
            raise RuntimeError("connect and identify the device first")
        if device != "gld":
            report = ch_readiness_report(state["info"]) if device == "ch" else gateway_readiness_report(state["info"])
            result = "all checks OK" if report["failed"] == 0 and report["unknown"] == 0 else f"{report['failed']} error, {report['unknown']} pending"
            add_activity(device, "Test Device", f"{state.get('port') or 'COM'}; {report['passed']}/{report['total']} OK; {result}")
            return json_response(self, {"report": report, "status": state["info"]})
        before = child_request(host, device, "GET", "/api/serial/recent?slot=1&after=0")
        sequence = int(before.get("sequence") or 0)
        child_request(host, device, "POST", "/api/serial/write", {"slot": 1, "line": "RUN_BOOT_CHECK"})
        status = recent_matching(host, device, "GLD_STATUS_JSON", sequence, timeout=18.0)
        if not status:
            raise RuntimeError("Boot Report did not return; keep the device connected and try again")
        report = gld_boot_report(status)
        result = "all checks OK" if report["failed"] == 0 and report["unknown"] == 0 else f"{report['failed']} error, {report['unknown']} pending"
        add_activity(device, "Test Device", f"{state.get('port') or 'COM'}; {report['passed']}/{report['total']} OK; {result}")
        json_response(self, {"report": report, "status": status})

    def _simple_command(self, payload: dict[str, object], command: str, action: str) -> None:
        device = self._simple_device(payload)
        host = self.server.server_address[0] or "127.0.0.1"
        state = simple_device_state(host, device)
        if not state["connected"]:
            raise RuntimeError("connect and identify the device first")
        result = child_request(host, device, "POST", "/api/serial/write", {"slot": 1, "line": command})
        add_activity(device, action, f"{state.get('port') or 'COM'}; command sent")
        json_response(self, result)

    def _simple_config_id(self, payload: dict[str, object]) -> None:
        device = self._simple_device(payload)
        value = str(payload.get("value") or "").upper()
        if not __import__("re").fullmatch(r"[0-9A-F]{4}", value):
            raise ValueError("ID must be 4 hexadecimal digits")
        number = int(value, 16)
        if device == "gld" and not 0x1001 <= number <= 0xFEFF:
            raise ValueError("GLD ID must be 1001-FEFF")
        if device == "ch" and not 0x0010 <= number <= 0x0FFF:
            raise ValueError("CH ID must be 0010-0FFF")
        if device == "gw" and not 0x0001 <= number <= 0x000F:
            raise ValueError("Gateway ID must be 0001-000F")
        host = self.server.server_address[0] or "127.0.0.1"
        state = simple_device_state(host, device)
        if not state["connected"] or not state.get("info"):
            raise RuntimeError("connect and identify the device first")
        command = (f"SET_DEVICE_ID_JSON {{\"deviceId\":\"{value}\",\"reboot\":true}}" if device == "gld" else
                   f"SET_CH_ADDRESS_JSON {{\"chId\":\"{value}\",\"reboot\":true}}" if device == "ch" else
                   f"SET_GATEWAY_ADDRESS_JSON {{\"gatewayId\":\"0x{value}\"}}")
        ack_marker = "SET_DEVICE_ID" if device == "gld" else "SET_CH_ADDRESS_JSON" if device == "ch" else "SET_GATEWAY_ADDRESS_JSON"
        result = send_and_confirm(host, device, command, ack_marker)
        readback = wait_for_readback(host, device, str(state["port"]))
        persisted = (readback.get("info") or {}).get("deviceId" if device == "gld" else "chId" if device == "ch" else "gatewayId")
        if str(persisted).upper().removeprefix("0X") != value:
            raise RuntimeError(f"firmware ACK was received but read-back differs: {persisted}")
        add_activity(device, "Set ID", f"{state.get('port')}; {value} saved and read back")
        json_response(self, {"ok": True, "confirmation": result, "readback": readback})

    def _simple_config_frequency(self, payload: dict[str, object]) -> None:
        device = self._simple_device(payload)
        if device not in {"gld", "ch"}:
            raise ValueError("Gateway Mesh radio is fixed and cannot be edited here")
        try:
            frequency = float(payload.get("freqMHz"))
        except (TypeError, ValueError) as exc:
            raise ValueError("frequency required") from exc
        if not 920.0 <= frequency <= 923.0:
            raise ValueError("STAR frequency must be 920.0-923.0 MHz")
        host = self.server.server_address[0] or "127.0.0.1"
        state = simple_device_state(host, device, query=True)
        info = state.get("info")
        if not state["connected"] or not isinstance(info, dict):
            raise RuntimeError("connect and identify the device first")
        radio = info.get("starLora")
        if not isinstance(radio, dict):
            raise RuntimeError("current STAR radio configuration was not returned by the device")
        required = ("bwKHz", "sf", "cr", "syncWord", "txPowerDbm") if device == "ch" else ("bwKHz", "sf", "cr", "syncWord", "txPowerDbm", "preamble", "tcxoVoltage", "xtalVoltage")
        if any(key not in radio for key in required):
            raise RuntimeError("incomplete current radio configuration; switch to Expert to inspect firmware compatibility")
        updated = {key: radio[key] for key in required}
        updated["freqMHz"] = frequency
        updated["reboot"] = True
        command = f"SET_STAR_LORA_JSON {json.dumps(updated, separators=(',', ':'))}" if device == "ch" else f"SET_LORA_CONFIG_JSON {json.dumps(updated, separators=(',', ':'))}"
        result = send_and_confirm(host, device, command, "SET_STAR_LORA_JSON" if device == "ch" else "SET_LORA_CONFIG")
        readback = wait_for_readback(host, device, str(state["port"]))
        stored_radio = (readback.get("info") or {}).get("starLora")
        if not isinstance(stored_radio, dict) or abs(float(stored_radio.get("freqMHz")) - frequency) > 0.001:
            raise RuntimeError("firmware ACK was received but STAR frequency read-back differs")
        add_activity(device, "Set STAR frequency", f"{state.get('port')}; {frequency:.3f} MHz saved and read back")
        json_response(self, {"ok": True, "confirmation": result, "readback": readback})

    def _simple_config_target_ch(self, payload: dict[str, object]) -> None:
        if self._simple_device(payload) != "gld":
            raise ValueError("Target CH is a GLD setting")
        value = str(payload.get("value") or "").upper().removeprefix("0X")
        if not __import__("re").fullmatch(r"[0-9A-F]{4}", value) or not 0x0010 <= int(value, 16) <= 0x0FFF:
            raise ValueError("Target CH ID must be 0010-0FFF")
        host = self.server.server_address[0] or "127.0.0.1"
        state = simple_device_state(host, "gld")
        if not state.get("connected") or not state.get("info"):
            raise RuntimeError("connect and identify the GLD first")
        result = send_and_confirm(host, "gld", f'SET_CH_ADDRESS_JSON {{"chId":"{value}","reboot":true}}', "SET_CH_ADDRESS")
        readback = wait_for_readback(host, "gld", str(state["port"]))
        stored = str((readback.get("info") or {}).get("targetChId") or "").upper().removeprefix("0X")
        if stored != value:
            raise RuntimeError(f"firmware ACK was received but Target CH read-back differs: {stored or '-'}")
        add_activity("gld", "Set Target CH", f"{state.get('port')}; {value} saved and read back")
        json_response(self, {"ok": True, "confirmation": result, "readback": readback})

    def _simple_config_root_gateway(self, payload: dict[str, object]) -> None:
        if self._simple_device(payload) != "ch":
            raise ValueError("Root Gateway is a CH setting")
        value = str(payload.get("value") or "").upper().removeprefix("0X")
        if not __import__("re").fullmatch(r"[0-9A-F]{4}", value) or not 0x0001 <= int(value, 16) <= 0x000F:
            raise ValueError("Root Gateway ID must be 0001-000F")
        host = self.server.server_address[0] or "127.0.0.1"
        state = simple_device_state(host, "ch")
        if not state.get("connected") or not state.get("info"):
            raise RuntimeError("connect and identify the CH first")
        result = send_and_confirm(host, "ch", f'SET_ROOT_GATEWAY_JSON {{"gatewayId":"{value}"}}', "SET_ROOT_GATEWAY_JSON")
        readback = wait_for_readback(host, "ch", str(state["port"]))
        stored = str((readback.get("info") or {}).get("rootGatewayId") or "").upper().removeprefix("0X")
        if stored != value:
            raise RuntimeError(f"firmware ACK was received but Root Gateway read-back differs: {stored or '-'}")
        add_activity("ch", "Set Root Gateway", f"{state.get('port')}; {value} saved and read back")
        json_response(self, {"ok": True, "confirmation": result, "readback": readback})

    def _simple_config_wifi(self, payload: dict[str, object]) -> None:
        if self._simple_device(payload) != "gw":
            raise ValueError("Wi-Fi is a Gateway setting")
        ssid, password = str(payload.get("ssid") or ""), str(payload.get("password") or "")
        if not ssid:
            raise ValueError("Wi-Fi SSID is required")
        host = self.server.server_address[0] or "127.0.0.1"
        state = simple_device_state(host, "gw")
        if not state.get("connected") or not state.get("info"):
            raise RuntimeError("connect and identify the Gateway first")
        result = send_and_confirm(host, "gw", f'SET_WIFI_CONFIG_JSON {json.dumps({"ssid": ssid, "password": password, "reboot": True}, separators=(",", ":"))}', "SET_WIFI_CONFIG")
        readback = wait_for_readback(host, "gw", str(state["port"]))
        wifi_test = send_and_confirm(host, "gw", "TEST_WIFI", "TEST_WIFI")
        if "connected=1" not in str(wifi_test.get("ack") or ""):
            raise RuntimeError("Wi-Fi settings were saved but the Gateway did not connect")
        add_activity("gw", "Set Wi-Fi", f"{state.get('port')}; saved, restarted, and Wi-Fi verified")
        json_response(self, {"ok": True, "confirmation": result, "readback": readback, "wifiTest": wifi_test})

    def _simple_config_mqtt(self, payload: dict[str, object]) -> None:
        if self._simple_device(payload) != "gw":
            raise ValueError("MQTT is a Gateway setting")
        host_name, username, password = str(payload.get("host") or ""), str(payload.get("username") or ""), str(payload.get("password") or "")
        try:
            port = int(payload.get("port"))
        except (TypeError, ValueError) as exc:
            raise ValueError("MQTT port is required") from exc
        if not host_name or not 1 <= port <= 65535:
            raise ValueError("MQTT host and port are required")
        host = self.server.server_address[0] or "127.0.0.1"
        state = simple_device_state(host, "gw")
        if not state.get("connected") or not state.get("info"):
            raise RuntimeError("connect and identify the Gateway first")
        wifi_test = send_and_confirm(host, "gw", "TEST_WIFI", "TEST_WIFI")
        if "connected=1" not in str(wifi_test.get("ack") or ""):
            raise RuntimeError("Wi-Fi must pass its test before MQTT can be configured")
        config = {"host": host_name, "port": port, "username": username, "password": password}
        result = send_and_confirm(host, "gw", f"SET_MQTT_CONFIG_JSON {json.dumps(config, separators=(',', ':'))}", "SET_MQTT_CONFIG")
        time.sleep(1.0)
        mqtt_test = send_and_confirm(host, "gw", "TEST_MQTT", "TEST_MQTT")
        if "connected=1" not in str(mqtt_test.get("ack") or ""):
            raise RuntimeError("MQTT settings were saved but the Gateway did not connect")
        add_activity("gw", "Set MQTT", f"{state.get('port')}; saved and MQTT verified")
        json_response(self, {"ok": True, "confirmation": result, "wifiTest": wifi_test, "mqttTest": mqtt_test})

    def _simple_firmware_upload(self, payload: dict[str, object]) -> None:
        """Flash only the packaged latest production image with explicit NVS-reset consent."""
        device = self._simple_device(payload)
        port = str(payload.get("port") or "").upper()
        if not __import__("re").fullmatch(r"COM\d+", port):
            raise ValueError("valid COM port required")
        env = {"gld": "gld", "ch": "ch", "gw": "gw"}[device]
        reset_nvs = bool(payload.get("resetNvs"))
        if reset_nvs and payload.get("resetNvsConfirmation") != "RESET NVS":
            raise ValueError("Reset NVS requires the explicit confirmation RESET NVS")
        host = self.server.server_address[0] or "127.0.0.1"
        state = simple_device_state(host, device, query=True)
        if not state.get("connected") or not state.get("info"):
            raise RuntimeError("connect and identify the device first")
        if state.get("port") != port:
            raise RuntimeError("selected port must match the identified device")
        package = child_request(host, device, "GET", f"/api/firmware/package?env={env}")
        request: dict[str, object] = {"env": env, "port": port, "manifest": package.get("manifest"), "packageFiles": package.get("packageFiles"), "resetNvs": reset_nvs, "slot": 1}
        info = state.get("info") if isinstance(state.get("info"), dict) else {}
        identifier = info.get("deviceId" if device == "gld" else "chId" if device == "ch" else "gatewayId")
        if not isinstance(identifier, str):
            raise RuntimeError("identified device ID is required before upload")
        request["targetDeviceId"] = identifier.removeprefix("0x").removeprefix("0X")
        result = child_request(host, device, "POST", "/api/firmware/upload", request)
        readback = wait_for_readback(host, device, port, timeout=35.0)
        expected_version = (package.get("manifest") or {}).get("firmwareVersion")
        actual_version = (readback.get("info") or {}).get("firmwareVersion")
        if expected_version and actual_version != expected_version:
            raise RuntimeError(f"flash completed but firmware read-back differs: expected {expected_version}, got {actual_version}")
        add_activity(device, "Firmware upload", f"{port}; latest {env} verified; NVS {'reset' if reset_nvs else 'preserved'}")
        json_response(self, {"upload": result, "readback": readback})

    def _handle_simple_ports(self) -> None:
        from urllib.parse import parse_qs, urlparse
        device = (parse_qs(urlparse(self.path).query).get("device") or [""])[0]
        if device not in CHILD_APPS:
            return json_response(self, {"error": "device must be gld, ch, or gw"}, HTTPStatus.BAD_REQUEST)
        host = self.server.server_address[0] or "127.0.0.1"
        json_response(self, child_request(host, device, "GET", "/api/ports"))

    def _handle_simple_overview(self) -> None:
        host = self.server.server_address[0] or "127.0.0.1"
        devices: dict[str, object] = {}
        for device in CHILD_APPS:
            try:
                devices[device] = simple_device_state(host, device, query=True)
            except Exception as exc:
                devices[device] = {"device": device, "connected": False, "error": str(exc)}
        packages = {device: latest_package(device) for device in CHILD_APPS}
        json_response(self, {"devices": devices, "packages": packages, "activity": simple_activity, "mesh": "Fixed by design; use Expert only to inspect."})

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
