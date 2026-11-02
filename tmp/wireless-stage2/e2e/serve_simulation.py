"""Isolated Stage2 browser E2E: real UI/bridge/collector, synthetic loopback GLD."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import threading
from http import HTTPStatus
from pathlib import Path
from urllib.parse import unquote, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from wire_peer import APP, Engine, PASSWORD, PROTECTED_PORTS, Server
sys.path.insert(0, str(APP))
from wireless_dataset_replay import WirelessDatasetReplayCollector

spec = importlib.util.spec_from_file_location("stage2_e2e_actual_bridge", APP / "bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
OUTPUT = HERE / "output"
EVIDENCE = HERE / "evidence.json"
engine = None
http_server = None


def save(name=None):
    evidence = engine.checkpoint(name) if name else engine.snapshot()
    evidence["endpoint"] = dict(host="127.0.0.1", http_port=http_server.server_port,
                                ws_port=engine.server.server_port)
    try:
        EVIDENCE.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    except OSError:
        # A journal reader cannot terminate a synthetic stream or recorder.
        evidence["journal_write_pending"] = True
    return evidence


class Handler(bridge.Handler):
    def log_message(self, *_args):
        pass

    def body(self, raw, mime="text/html; charset=utf-8", status=200):
        raw = raw.encode("utf-8") if isinstance(raw, str) else raw
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def allowed(self):
        origin = f"http://127.0.0.1:{self.server.server_port}"
        return self.headers.get("Host") == origin.removeprefix("http://") and self.headers.get("Origin", origin) == origin

    def blocked(self):
        return bridge.json_response(self, {"error": "SIMULATION: COM/firmware/MQTT/Stage1 writes disabled"}, HTTPStatus.FORBIDDEN)

    def do_GET(self):
        if not self.allowed():
            return self.blocked()
        path = urlparse(self.path).path
        if path == "/":
            return self.body('''<!doctype html><html><head><meta charset="utf-8"><title>Stage2 Replay Simulation</title>
<style>html,body{margin:0;height:100%;font:15px system-ui;background:#102235;color:white}header{padding:10px 18px;background:#8b3e00}h1{margin:0;font-size:18px}iframe{border:0;width:100%;height:calc(100vh - 65px)}</style></head>
<body><header><h1>SIMULATION — Protocol 2 replay · synthetic GLD · no hardware</h1><small>Virtual acquisition clock; real UI/collector/WebSocket client. Select five-minute replay.</small></header><iframe title="GLD Operator simulation" src="/gld/"></iframe></body></html>''')
        if path == "/sim/state":
            return bridge.json_response(self, save())
        if path == "/api/health":
            return bridge.json_response(self, dict(ok=True, appId=bridge.APP_ID,
                version=bridge.VERSION + "-STAGE2-SIMULATION", csrfToken=bridge.BRIDGE_CSRF_TOKEN,
                simulation=True, features=dict(serial=False, mqtt=False, datasetMonitor=False,
                    mqttBroker=False, datasetOutput=True, wirelessDataset=True, wirelessReplay=True,
                    networkInfo=False, firmwareUpload=False), slots={}, maxSlots=0,
                mqttBroker=dict(running=False), errors={}))
        if path.startswith("/api/"):
            try:
                self._require_api_access(path)
            except Exception as error:
                return self._request_error(error)
            if path == "/api/ports":
                return bridge.json_response(self, {"ports": []})
            if path == "/api/serial/status":
                return bridge.json_response(self, {"connected": False, "port": "", "baud": 115200})
            if path == "/api/serial/recent":
                return bridge.json_response(self, {"sequence": 0, "lines": []})
            if path == "/api/network":
                return bridge.json_response(self, {"ssid": "STAGE2-SIMULATION-LOOPBACK", "ipv4": "127.0.0.1"})
            if path == "/api/gld-key-status":
                return bridge.json_response(self, {"configured": False, "keyId": None, "source": None, "nodeRedDeployment": "simulation"})
            if path in {"/api/events", "/api/wireless-replay/state", "/api/wireless-dataset/state", "/api/dataset/output-dir"}:
                return super().do_GET()
            return self.blocked()
        if path.startswith("/gld/"):
            suffix = unquote(path[len("/gld/"):]) or "index.html"
            target = (APP / suffix).resolve()
            if (not target.is_relative_to(APP) or not target.is_file() or target.suffix not in {".html", ".js", ".css"}
                    or suffix not in {"index.html", "style.css"} and not suffix.startswith(("js/", "css/"))):
                return self.body("not found", "text/plain", 404)
            text = target.read_text(encoding="utf-8")
            if suffix == "index.html":
                text = text.replace("<body>", '<body><div style="background:#9d3d00;color:white;padding:8px 14px;font:600 13px system-ui">STAGE2 SIMULATION — choose replay mode. Synthetic sensors only. Test password: ' + PASSWORD + '</div>')
                text = text.replace('href="http://127.0.0.1:5173/"', 'href="/"')
            elif suffix == "js/bridge-client.js":
                text = text.replace('"http://127.0.0.1:5174"', f'"http://127.0.0.1:{self.server.server_port}"')
                text = text.replace('location.port === "5174"', f'location.port === "{self.server.server_port}"')
            return self.body(text, {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}.get(target.suffix, "text/html; charset=utf-8"))
        return self.body("not found", "text/plain", 404)

    def do_POST(self):
        if not self.allowed():
            return self.blocked()
        path = urlparse(self.path).path
        if path.startswith("/sim/"):
            try:
                payload = bridge.read_json(self)
                action = path.removeprefix("/sim/")
                if action == "checkpoint":
                    return bridge.json_response(self, save(str(payload.get("name", "checkpoint"))[:80]))
                if action == "shutdown":
                    bridge.json_response(self, {"ok": True})
                    threading.Thread(target=shutdown, daemon=True).start()
                    return
                engine.control(action, payload)
                return bridge.json_response(self, save())
            except Exception as error:
                return bridge.json_response(self, {"error": type(error).__name__}, HTTPStatus.BAD_REQUEST)
        if path in {"/api/wireless-replay/connect", "/api/wireless-replay/start", "/api/wireless-replay/stop",
                    "/api/wireless-replay/disconnect", "/api/wireless-replay/export"}:
            super().do_POST()
            save()
            return
        return self.blocked()


def callback(payload):
    bridge.events.emit("wireless_dataset_replay", payload)


def shutdown():
    save("shutdown")
    engine.close()
    http_server.shutdown()


def main():
    global engine, http_server
    OUTPUT.mkdir(parents=True, exist_ok=True)
    engine = Engine()
    http_server = Server(("127.0.0.1", 0), Handler)
    if http_server.server_port in PROTECTED_PORTS:
        raise RuntimeError("refusing protected HTTP port")
    bridge.DATASET_OUTPUT_DIR = OUTPUT
    bridge.SESSION_LOG_DIR = OUTPUT / "logs"
    bridge.BRIDGE_ALLOWED_ORIGINS = {f"http://127.0.0.1:{http_server.server_port}"}
    bridge.serial_bridges.clear()
    collector = WirelessDatasetReplayCollector(OUTPUT, callback, websocket_factory=engine.factory,
        fsync=engine.fsync, command_timeout=5, silence_timeout=3)
    engine.collector = collector
    bridge.wireless_replay_collector = collector
    ready = dict(mode="pc-simulation", ui_url=f"http://127.0.0.1:{http_server.server_port}/",
        app_url=f"http://127.0.0.1:{http_server.server_port}/gld/", password=PASSWORD,
        http_port=http_server.server_port, ws_port=engine.server.server_port, pid=os.getpid(),
        evidence_path=str(EVIDENCE), output=str(OUTPUT))
    (HERE / "ready.json").write_text(json.dumps(ready, indent=2), encoding="utf-8")
    save()
    print(json.dumps({"simulation_ready": True, "ui_url": ready["ui_url"], "pid": ready["pid"]}), flush=True)
    try:
        http_server.serve_forever(poll_interval=0.05)
    finally:
        engine.close()
        http_server.server_close()


if __name__ == "__main__":
    main()
