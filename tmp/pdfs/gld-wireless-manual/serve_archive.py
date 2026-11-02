"""Read-only REAL GLD snapshot viewer for clearly-labelled manual screenshots.

No production bridge import, WebSocket factory, COM, firmware, Wi-Fi command or
device connection exists. Only an ephemeral127.0.0.1 HTTP archive is served.
"""
import hashlib
import json
import mimetypes
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
APP = ROOT / "apps/gld-operator"
sys.path.insert(0, str(HERE))
from extract_scenes import canonical

BANNER = "TAMPILAN ULANG LOG UJI GLD ASLI - bukan koneksi langsung"
TOKEN = "archive-read-only-no-device-authority"
SCENES = json.loads((HERE / "archive-scenes.json").read_text(encoding="utf-8"))
SOURCE = Path(SCENES["source_path"])
if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != SCENES["source_sha256"]:
    raise RuntimeError("Actual source evidence changed; re-extract explicitly")
for scene in SCENES["scenes"].values():
    if hashlib.sha256(canonical(scene["snapshot"])).hexdigest() != scene["snapshot_sha256"]:
        raise RuntimeError("Extracted actual snapshot integrity mismatch")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def allowed(self):
        authority = f"127.0.0.1:{self.server.server_port}"
        return self.headers.get("Host") == authority and self.headers.get("Origin", "http://" + authority) == "http://" + authority

    def respond(self, value, status=200, mime="application/json; charset=utf-8"):
        raw = json.dumps(value, allow_nan=False).encode("utf-8") if not isinstance(value, (str, bytes)) else value.encode("utf-8") if isinstance(value, str) else value
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(raw)

    def scene(self):
        query = parse_qs(urlparse(self.path).query)
        name = (query.get("archive_scene") or query.get("scene") or ["recording"])[0]
        if name not in SCENES["scenes"]:
            raise ValueError("scene must be ready/recording/replaying")
        return name

    def do_POST(self):
        self.close_connection = True
        return self.respond({"error": "Arsip read-only; semua perintah perangkat dinonaktifkan."}, 403)

    do_PUT = do_DELETE = do_PATCH = do_POST

    def do_GET(self):
        if not self.allowed():
            return self.respond({"error": "archive loopback origin required"}, 403)
        parsed = urlparse(self.path)
        if "mock" in parse_qs(parsed.query):
            return self.respond({"error": "mock data is forbidden in the recorded-actual viewer"}, 403)
        try:
            name = self.scene()
        except ValueError:
            return self.respond({"error": "unknown archive scene"}, 400)
        archived = SCENES["scenes"][name]
        snapshot = archived["snapshot"]
        path = parsed.path
        if path == "/":
            links = "".join(f'<li><a href="/gld/?scene={scene}">{scene}</a></li>' for scene in SCENES["scenes"])
            return self.respond(f"<!doctype html><meta charset=utf-8><title>Arsip Uji GLD Asli</title><h1>{BANNER}</h1><ul>{links}</ul>", mime="text/html; charset=utf-8")
        if path == "/archive/provenance":
            return self.respond({key: value for key, value in SCENES.items() if key != "scenes"} | {
                "scenes": {key: {field: value for field, value in scene.items() if field != "snapshot"}
                           for key, scene in SCENES["scenes"].items()}})
        if path == "/api/health":
            return self.respond(dict(ok=True, appId="gld-operator", version="recorded-actual-archive-viewer",
                csrfToken=TOKEN, simulation=True, displayOnly=True, readOnly=True, archive=True,
                dataOrigin="recorded_actual", liveConnection=False,
                features=dict(serial=False, mqtt=False, mqttBroker=False, datasetMonitor=False,
                    datasetOutput=True, wirelessDataset=False, wirelessReplay=True, networkInfo=False,
                    firmwareUpload=False), slots={}, maxSlots=0, mqttBroker=dict(running=False), errors={}))
        if path == "/api/ports":
            return self.respond({"ports": [], "readOnly": True})
        if path == "/api/wireless-replay/state":
            return self.respond(snapshot)  # Exactly the original recorded object.
        if path == "/api/wireless-dataset/state":
            # Inert viewer transport metadata, never represented as a GLD log.
            return self.respond(dict(state="unavailable", connected=False, ready=False, history=[],
                archiveControlOnly=True, readOnly=True, reason="Only archived protocol2 data is available"))
        if path == "/api/dataset/output-dir":
            return self.respond(dict(path=str(Path(snapshot.get("path") or SOURCE).parent), readOnly=True,
                                     displayOnly=True, exists=True))
        if path == "/api/serial/status":
            return self.respond(dict(connected=False, readOnly=True, archiveControlOnly=True))
        if path == "/api/serial/recent":
            return self.respond(dict(sequence=0, lines=[], readOnly=True))
        if path == "/api/gld-key-status":
            return self.respond(dict(configured=False, source=None, readOnly=True, nodeRedDeployment="not-accessed"))
        if path == "/api/network":
            return self.respond(dict(readOnly=True, displayOnly=True, liveConnection=False))
        if path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            try:
                packet = {"type": "state", **snapshot}
                self.wfile.write(("event: wireless_dataset_replay\ndata: " + json.dumps(packet, allow_nan=False) + "\n\n").encode())
                self.wfile.flush()
                for _ in range(30):
                    time.sleep(1)
                    self.wfile.write(b": archive keepalive; no live device\n\n")
                    self.wfile.flush()
            except (OSError, ConnectionError):
                pass
            return
        if path.startswith("/api/"):
            return self.respond({"error": "No recorded read-only endpoint"}, 404)
        if path.startswith("/gld/"):
            suffix = unquote(path[len("/gld/"):]) or "index.html"
            target = (APP / suffix).resolve()
            if (not target.is_relative_to(APP) or not target.is_file()
                    or suffix not in {"index.html", "style.css"} and not suffix.startswith(("js/", "css/", "assets/"))
                    or target.suffix not in {".html", ".css", ".js", ".svg", ".png", ".ico", ".woff2"}):
                return self.respond({"error": "asset not allowed"}, 404)
            if target.suffix not in {".html", ".css", ".js"}:
                return self.respond(target.read_bytes(), mime=mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            text = target.read_text(encoding="utf-8")
            if suffix == "index.html":
                banner = ('<aside id="recordedActualBanner" role="note" style="position:sticky;top:0;z-index:99999;'
                          'background:#7c3300;color:#fff;padding:12px 18px;font:700 15px system-ui;line-height:1.45">'
                          + BANNER + f'<br><span style="font-weight:400;font-size:12px">Scene: {name} · snapshot asli tanpa perubahan · semua POST diblokir</span></aside>')
                text = text.replace("<body>", "<body>" + banner)
                text = text.replace("<title>GLD Operator</title>", "<title>Arsip Uji GLD Asli — " + name + "</title>")
                text = text.replace('href="http://127.0.0.1:5173/"', 'href="/"')
            elif suffix == "js/bridge-client.js":
                old = 'return onBridgeOrigin ? path : `${DEFAULT_BRIDGE_ORIGIN}${path}`;'
                if text.count(old) != 1:
                    return self.respond({"error": "archive mapping incompatible; refuse production origin fallback"}, 500)
                text = text.replace('"http://127.0.0.1:5174"', f'"http://127.0.0.1:{self.server.server_port}"')
                text = text.replace('location.port === "5174"', f'location.port === "{self.server.server_port}"')
                text = text.replace(old, '''const archiveTarget = new URL(onBridgeOrigin ? path : `${DEFAULT_BRIDGE_ORIGIN}${path}`, location.href);
  archiveTarget.searchParams.set("archive_scene", new URLSearchParams(location.search).get("scene") || "recording");
  return archiveTarget.href;''')
            return self.respond(text, mime={".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}.get(target.suffix, "text/html; charset=utf-8"))
        return self.respond({"error": "not found"}, 404)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    if server.server_port in {1880, 1884, 5173, 5174, 5273, 5373}:
        raise RuntimeError("refuse protected port")
    origin = f"http://127.0.0.1:{server.server_port}"
    ready = dict(kind="recorded_actual_archive", live_connection=False, read_only=True,
        host="127.0.0.1", port=server.server_port, pid=os.getpid(),
        urls={name: origin + "/gld/?scene=" + name for name in SCENES["scenes"]},
        provenance_url=origin + "/archive/provenance", source_sha256=SCENES["source_sha256"])
    (HERE / "archive-ready.json").write_text(json.dumps(ready, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(ready), flush=True)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
