"""Web lokal untuk menelusuri konfigurasi TFT_eSPI GC9A01 (next/prev) lalu upload otomatis.
Jalankan:  python web/server.py   lalu buka http://localhost:8765
"""
import itertools, json, os, shutil, subprocess, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer

import serial  # pyserial

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT_COM = "COM5"
PIO = shutil.which("pio") or "pio"

PINSETS = {
    "video":  dict(MOSI=13, SCLK=15, CS=17, DC=21, RST=22),
    "asli":   dict(MOSI=23, SCLK=18, CS=27, DC=26, RST=25),
    "vspi22": dict(MOSI=23, SCLK=18, CS=22, DC=16, RST=4),
}
OPTIONS = {
    "pins":  list(PINSETS),
    "freq":  [4000000, 1000000, 10000000, 27000000, 500000],
    "mode":  [0, 3],
    "invert": [False, True],
    "order": ["RGB", "BGR"],
}
ORDER = ["pins", "freq", "mode", "invert", "order"]  # urutan putar: kiri paling lambat berubah
GRID = [dict(zip(ORDER, c)) for c in itertools.product(*[OPTIONS[k] for k in ORDER])]

HEAD = """[env:esp32dev]
platform = espressif32
board = esp32dev
framework = arduino
monitor_speed = 115200
upload_port = {com}
monitor_port = {com}
lib_deps = bodmer/TFT_eSPI
build_flags =
"""

state = dict(index=0, cfg=dict(GRID[0]), busy=False, log="belum ada upload", result="-", serial="", history=[])
lock = threading.Lock()


def flags(cfg):
    p = PINSETS[cfg["pins"]]
    f = ["-DUSER_SETUP_LOADED=1", "-DGC9A01_DRIVER=1", "-DTFT_WIDTH=240", "-DTFT_HEIGHT=240",
         f"-DTFT_MOSI={p['MOSI']}", f"-DTFT_SCLK={p['SCLK']}", f"-DTFT_CS={p['CS']}",
         f"-DTFT_DC={p['DC']}", f"-DTFT_RST={p['RST']}", "-DTFT_MISO=-1",
         "-DLOAD_GLCD=1", "-DLOAD_FONT2=1", "-DLOAD_FONT4=1",
         f"-DSPI_FREQUENCY={cfg['freq']}"]
    if cfg["mode"] == 3:
        f.append("-DTFT_SPI_MODE=SPI_MODE3")
    if cfg["invert"]:
        f.append("-DTFT_INVERSION_ON=1")
    else:
        f.append("-DTFT_INVERSION_OFF=1")
    f.append("-DTFT_RGB_ORDER=TFT_BGR" if cfg["order"] == "BGR" else "-DTFT_RGB_ORDER=TFT_RGB")
    return f


def apply(cfg):
    with lock:
        if state["busy"]:
            return False
        state["busy"] = True
        state["cfg"] = dict(cfg)
        state["result"] = "upload berjalan..."
        state["serial"] = ""
    threading.Thread(target=worker, args=(dict(cfg),), daemon=True).start()
    return True


def worker(cfg):
    try:
        ini = HEAD.format(com=PORT_COM) + "".join(f"  {x}\n" for x in flags(cfg))
        with open(os.path.join(ROOT, "platformio.ini"), "w", encoding="utf-8") as fh:
            fh.write(ini)
        t0 = time.time()
        r = subprocess.run([PIO, "run", "-t", "upload"], cwd=ROOT, capture_output=True, text=True)
        out = r.stdout + r.stderr
        ok = "[SUCCESS]" in out
        state["log"] = "\n".join(out.strip().splitlines()[-12:])
        ser = ""
        if ok:
            try:
                s = serial.Serial(PORT_COM, 115200, timeout=0.5)
                s.dtr = False; s.rts = True; time.sleep(0.1); s.rts = False
                end = time.time() + 5
                while time.time() < end:
                    line = s.readline()
                    if line:
                        ser += line.decode(errors="replace")
                s.close()
            except Exception as e:  # noqa
                ser = f"(serial gagal dibaca: {e})"
        state["serial"] = ser.strip()
        state["result"] = ("UPLOAD OK" if ok else "UPLOAD GAGAL") + f" ({time.time()-t0:.0f} dtk)"
    except Exception as e:  # noqa
        state["result"] = f"error: {e}"
    finally:
        state["busy"] = False


def label(cfg):
    p = PINSETS[cfg["pins"]]
    return (f"pin={cfg['pins']} (SDA{p['MOSI']} SCL{p['SCLK']} CS{p['CS']} DC{p['DC']} RST{p['RST']}) "
            f"| {cfg['freq']/1e6:g} MHz | mode {cfg['mode']} | invert {'ON' if cfg['invert'] else 'off'} | {cfg['order']}")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(200)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/":
            with open(os.path.join(os.path.dirname(__file__), "index.html"), "rb") as fh:
                self.send(fh.read(), "text/html")
        elif self.path == "/state":
            self.send(json.dumps(dict(state, label=label(state["cfg"]), total=len(GRID),
                                      options=OPTIONS, order=ORDER)))
        else:
            self.send("{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(n) or "{}")
        if self.path in ("/next", "/prev"):
            step = 1 if self.path == "/next" else -1
            state["index"] = (state["index"] + step) % len(GRID)
            ok = apply(GRID[state["index"]])
        elif self.path == "/apply":
            cfg = {k: data[k] for k in ORDER}
            cfg["freq"], cfg["mode"] = int(cfg["freq"]), int(cfg["mode"])
            cfg["invert"] = bool(cfg["invert"])
            if cfg in GRID:
                state["index"] = GRID.index(cfg)
            ok = apply(cfg)
        elif self.path == "/good":
            state["history"].append(label(state["cfg"]))
            with open(os.path.join(ROOT, "web", "konfigurasi_bagus.txt"), "a", encoding="utf-8") as fh:
                fh.write(label(state["cfg"]) + "\n")
            ok = True
        else:
            ok = False
        self.send(json.dumps(dict(ok=ok)))


if __name__ == "__main__":
    srv = HTTPServer(("127.0.0.1", 8765), H)
    print("Buka http://localhost:8765  (Ctrl+C untuk berhenti)")
    srv.serve_forever()
