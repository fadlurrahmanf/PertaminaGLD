#!/usr/bin/env python3
"""Local, operator-confirmed MQ8 duty-cycle test console."""

from __future__ import annotations

import argparse
import csv
import ctypes
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent.parent
PUBLIC_DIR = APP_DIR / "public"
OUTPUT_DIR = APP_DIR / "output"
SESSIONS_DIR = OUTPUT_DIR / "sessions"
SESSION_FILE = OUTPUT_DIR / "mq8-test-session.json"
TOKEN_FILE = OUTPUT_DIR / ".mq8-test-console-token"
RUNNER = REPO_ROOT / "firmware" / "uno" / "tools" / "Invoke-Mq8RecoveryBaselineSweep.ps1"
CONSOLE_RUNNER = APP_DIR / "Invoke-Mq8ConsoleRunner.ps1"
GLD_BRIDGE_URL = "http://127.0.0.1:5174"
APP_VERSION = "2026.08.05-direction-config"


def load_or_create_token() -> str:
    """Keep UI controls usable when only the local web server is restarted."""
    try:
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if len(token) >= 32:
            return token
    except OSError:
        pass
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    temporary = TOKEN_FILE.with_suffix(".tmp")
    temporary.write_text(token, encoding="utf-8")
    temporary.replace(TOKEN_FILE)
    return token


TOKEN = load_or_create_token()
LOCK = threading.Lock()
SESSION: dict[str, object] | None = None
TEST_DUTIES = [15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95]
CLIENT_DISCONNECT_WINERRORS = {64, 995, 10053, 10054}


def is_client_disconnect(exc: BaseException) -> bool:
    """A browser refresh/close is normal, not a console-server failure."""
    if isinstance(exc, (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, TimeoutError)):
        return True
    return isinstance(exc, OSError) and getattr(exc, "winerror", None) in CLIENT_DISCONNECT_WINERRORS


def json_response(handler: SimpleHTTPRequestHandler, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    try:
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(body)
    except BaseException as exc:
        if not is_client_disconnect(exc):
            raise


def csv_response(handler: SimpleHTTPRequestHandler, path: Path, filename: str) -> None:
    """Download the complete valid-only live CSV for the active session."""
    if not path.exists():
        raise RuntimeError("CSV live sesi belum tersedia.")
    try:
        body = path.read_bytes()
    except OSError as exc:
        raise RuntimeError("CSV live tidak dapat dibaca saat ini.") from exc
    try:
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", "text/csv; charset=utf-8")
        handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(body)
    except BaseException as exc:
        if not is_client_disconnect(exc):
            raise


def read_json(handler: SimpleHTTPRequestHandler) -> dict[str, object]:
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError as exc:
        raise ValueError("Content-Length tidak valid") from exc
    if length < 2 or length > 4096:
        raise ValueError("Ukuran request tidak valid")
    body = json.loads(handler.rfile.read(length).decode("utf-8"))
    if not isinstance(body, dict):
        raise ValueError("JSON object diperlukan")
    return body


def is_alive(snapshot: dict[str, object]) -> bool:
    process = snapshot.get("process")
    if isinstance(process, subprocess.Popen):
        return process.poll() is None
    try:
        pid = int(snapshot["pid"])
        if os.name == "nt":
            process_handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not process_handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                if not ctypes.windll.kernel32.GetExitCodeProcess(process_handle, ctypes.byref(exit_code)):
                    return False
                return exit_code.value == 259  # STILL_ACTIVE
            finally:
                ctypes.windll.kernel32.CloseHandle(process_handle)
        os.kill(pid, 0)
        return True
    except (KeyError, TypeError, ValueError, OSError, ctypes.ArgumentError):
        return False


def output_path(value: object) -> Path:
    candidate = Path(str(value)).resolve()
    root = OUTPUT_DIR.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Path sesi berada di luar output console")
    return candidate


def ensure_gld_bridge_ready() -> None:
    """Fail before opening Uno when the telemetry owner is unavailable."""
    try:
        with urllib.request.urlopen(f"{GLD_BRIDGE_URL}/api/health", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError("GLD Operator bridge 5174 tidak dapat dihubungi. Jalankan dan hubungkan GLD di COM3 terlebih dahulu.") from exc
    slot = payload.get("slots", {}).get("1", {}) if isinstance(payload, dict) else {}
    if payload.get("appId") != "gld-operator" or not slot.get("connected") or str(slot.get("port", "")).upper() != "COM3":
        raise RuntimeError("GLD Operator harus aktif dan terhubung ke COM3 sebelum test MQ8 dimulai.")


def gld_serial_recent(after: int = 0) -> dict[str, object]:
    """Read GLD Operator's in-memory serial log without touching COM3."""
    after = max(0, after)
    try:
        with urllib.request.urlopen(f"{GLD_BRIDGE_URL}/api/health", timeout=2) as response:
            health = json.loads(response.read().decode("utf-8"))
        token = str(health.get("csrfToken", ""))
        if len(token) < 16:
            raise RuntimeError("token GLD Operator tidak tersedia")
        request = urllib.request.Request(
            f"{GLD_BRIDGE_URL}/api/serial/recent?slot=1&after={after}",
            headers={"X-GLD-Bridge-Token": token},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        lines = payload.get("lines", []) if isinstance(payload, dict) else []
        safe_lines = [item for item in lines if isinstance(item, dict) and isinstance(item.get("line"), str)]
        return {"connected": bool(health.get("slots", {}).get("1", {}).get("connected")), "sequence": int(payload.get("sequence", after)), "lines": safe_lines}
    except (OSError, ValueError, TypeError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"connected": False, "sequence": after, "lines": [], "error": str(exc)}


def save_session(snapshot: dict[str, object]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data = {key: str(snapshot[key]) for key in ("stamp", "output", "control", "config", "progress", "live", "stdout", "stderr")}
    data["pid"] = int(snapshot["pid"])
    temporary = SESSION_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    temporary.replace(SESSION_FILE)


def load_session() -> dict[str, object] | None:
    if not SESSION_FILE.exists():
        return None
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        snapshot: dict[str, object] = {
            "pid": int(data["pid"]), "stamp": str(data["stamp"]),
            "output": output_path(data.get("output", Path(str(data["live"])).parent)),
            "control": output_path(data["control"]), "config": output_path(data.get("config", Path(str(data["control"])).with_name("MQ8_TEST_CONFIG.json"))), "progress": output_path(data["progress"]),
            "live": output_path(data["live"]), "stdout": output_path(data["stdout"]),
            "stderr": output_path(data["stderr"]), "process": None,
        }
        return snapshot
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def session_snapshot() -> dict[str, object] | None:
    with LOCK:
        return dict(SESSION) if SESSION else None


def close_completed_log_handles() -> None:
    """Release Windows log locks as soon as an in-memory runner exits."""
    with LOCK:
        if not SESSION or not isinstance(SESSION.get("process"), subprocess.Popen):
            return
        if SESSION["process"].poll() is None:
            return
        for key in ("stdoutHandle", "stderrHandle"):
            handle = SESSION.get(key)
            if handle and not handle.closed:
                handle.close()


def session_path(name: str) -> Path | None:
    with LOCK:
        if not SESSION:
            return None
        value = SESSION.get(name)
    return value if isinstance(value, Path) else None


def write_control(command: str) -> None:
    path = session_path("control")
    snapshot = session_snapshot()
    if path is None or snapshot is None or not is_alive(snapshot):
        raise RuntimeError("Tidak ada sesi aktif.")
    path.write_text(command, encoding="utf-8")


def direction_confirmation_seconds(value: object) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Konfirmasi arah harus berupa angka 1 sampai 120 detik.") from exc
    if not 1 <= seconds <= 120:
        raise ValueError("Konfirmasi arah harus 1 sampai 120 detik.")
    return seconds


def write_direction_config(seconds: float) -> None:
    path = session_path("config")
    snapshot = session_snapshot()
    if path is None or snapshot is None or not is_alive(snapshot):
        raise RuntimeError("Tidak ada sesi aktif.")
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"directionConfirmSeconds": seconds}, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def parse_progress(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"state": "BELUM_DIMULAI"}
    text = path.read_text(encoding="utf-8", errors="replace")
    def match(pattern: str, default: str = "") -> str:
        found = re.search(pattern, text, re.MULTILINE)
        return found.group(1).strip() if found else default
    details = match(r"- Keterangan: (.+)")
    metric = re.search(
        r"rentang 60dtk=([-+0-9.]+)/([-+0-9.]+) mV; tren 1m=([-+0-9.]+)/([-+0-9.]+) mV/menit",
        details,
        re.IGNORECASE,
    )
    stable_hold = re.search(r"Stabil berturut-turut: \*\*([-+0-9.,]+) menit\*\* / syarat ([-+0-9.,]+) menit", text, re.IGNORECASE)
    direction_confirm = re.search(r"Konfirmasi arah: \*\*([-+0-9.,]+) detik\*\*", text, re.IGNORECASE)
    return {
        "state": match(r"- Status: \*\*(.+?)\*\*", "RECORDING"),
        "duty": match(r"- Duty aktif: \*\*(.+?)\*\*"),
        "phase": match(r"- Fase: \*\*(.+?)\*\*"),
        "stage": match(r"- Tahap: (.+)"),
        "mq8Status": match(r"Status MQ8: \*\*(.+?)\*\*"),
        "phaseMode": match(r"- Mode fase: \*\*(.+?)\*\*", "Manual"),
        "duration": match(r"Durasi fase: \*\*(.+?)\*\*"),
        "samples": match(r"- Sampel tersimpan: (.+)"),
        "phaseCsv": match(r"- CSV fase: (.+)"),
        "details": details,
        "rangeMv": float(metric.group(1)) if metric else None,
        "rangeLimitMv": float(metric.group(2)) if metric else None,
        "trendMvPerMin": float(metric.group(3)) if metric else None,
        "trendLimitMvPerMin": float(metric.group(4)) if metric else None,
        "stableHoldMinutes": float(stable_hold.group(1).replace(",", ".")) if stable_hold else 0.0,
        "stableHoldTargetMinutes": float(stable_hold.group(2).replace(",", ".")) if stable_hold else 3.0,
        "directionConfirmSeconds": float(direction_confirm.group(1).replace(",", ".")) if direction_confirm else 10.0,
        "raw": text[-4000:],
    }


def live_points(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                try:
                    gain = row.get("mq8_gain", "")
                    rows.append({"elapsed": float(row["elapsed_s"]), "mv": float(row["mq8_v"]) * 1000.0, "gain": float(gain) if gain not in ("", None) else None, "phase": row.get("phase", ""), "duty": row.get("duty_pct", "")})
                except (KeyError, TypeError, ValueError):
                    continue
    except OSError:
        return []
    return rows[-1800:]


def latest_phase_gain(progress: dict[str, object]) -> float | None:
    """Read just the last raw phase row so older sessions also show gain."""
    raw_path = str(progress.get("phaseCsv", "")).strip()
    if not raw_path:
        return None
    try:
        path = output_path(raw_path)
        with path.open("rb") as source:
            header = source.readline().decode("utf-8-sig", errors="replace").rstrip("\r\n")
            source.seek(max(0, path.stat().st_size - 65536))
            tail = source.read().decode("utf-8", errors="replace").splitlines()
        if not header or not tail:
            return None
        row = next(csv.DictReader([header, tail[-1]]), None)
        if not row:
            return None
        status = json.loads(row.get("status_json", "{}"))
        telemetry = status.get("telemetry", {}) if isinstance(status, dict) else {}
        order = telemetry.get("featureOrder", [])
        gains = telemetry.get("sensorGain", [])
        index = order.index("MQ8")
        return float(gains[index]) if index < len(gains) else None
    except (OSError, ValueError, TypeError, json.JSONDecodeError, StopIteration):
        return None


def output_files(directory: Path, stamp: str) -> list[str]:
    return [item.name for item in sorted(directory.glob(f"MQ8_RECOVERY_{stamp}_*.csv"), key=lambda item: item.name)]


def runner_error(path: Path, alive: bool) -> str:
    if alive or not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-1600:].strip()
    except OSError:
        return ""


def final_io8_confirmation(path: Path, alive: bool) -> str:
    if alive or not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    confirmed = re.findall(r"^FINAL_IO8=(.+)$", text, re.MULTILINE)
    if confirmed:
        return confirmed[-1].strip()
    failed = re.findall(r"^FINAL_IO8_UNCONFIRMED=(.+)$", text, re.MULTILINE)
    return f"TIDAK_TERVERIFIKASI: {failed[-1].strip()}" if failed else ""


def write_operator_progress(directory: Path, stamp: str, progress: dict[str, object], alive: bool, error: str = "", final_io8: str = "") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "MQ8_TEST_PROGRESS.md"
    lines = [
        "# MQ8 Test Console",
        "",
        f"- Sesi: `{stamp}`",
        f"- Runner: **{'AKTIF' if alive else 'SELESAI / BERHENTI'}**",
        f"- Fase: **{progress.get('phase') or '-'}**",
        f"- Duty aktif: **{progress.get('duty') or '-'}**",
        f"- Status pembacaan MQ8: **{progress.get('mq8Status') or '-'}**",
        f"- Durasi fase: {progress.get('duration') or '-'}",
        f"- Sampel valid tersimpan: {progress.get('samples') or '0'}",
        "",
        f"Mode fase: **{progress.get('phaseMode') or 'Manual'}**.",
    ]
    if final_io8:
        lines.extend(["", f"- Konfirmasi IO8 akhir: **{final_io8}**"])
    if error:
        lines.extend(["", "## Error runner", "", "```text", error, "```"])
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination


def current_status() -> dict[str, object]:
    snapshot = session_snapshot()
    if not snapshot:
        return {"version": APP_VERSION, "active": False, "state": "BELUM_DIMULAI", "duties": TEST_DUTIES, "outputDir": str(OUTPUT_DIR)}
    stamp = str(snapshot["stamp"])
    directory = snapshot["output"] if isinstance(snapshot.get("output"), Path) else OUTPUT_DIR
    progress = parse_progress(snapshot["progress"])
    alive = is_alive(snapshot)
    if not alive:
        close_completed_log_handles()
    error = runner_error(snapshot["stderr"], alive)
    final_io8 = final_io8_confirmation(snapshot["stdout"], alive)
    points = live_points(snapshot["live"])
    if points and not isinstance(points[-1].get("gain"), float):
        points[-1]["gain"] = latest_phase_gain(progress)
    operator_progress = write_operator_progress(directory, stamp, progress, alive, error, final_io8)
    return {
        "version": APP_VERSION,
        "active": alive,
        "state": "MENUNGGU_OPERATOR" if alive else "SELESAI / BERHENTI",
        "exitCode": snapshot["process"].poll() if isinstance(snapshot.get("process"), subprocess.Popen) else None,
        "runnerError": error,
        "finalIo8": final_io8,
        "stamp": stamp,
        "duties": TEST_DUTIES,
        "progress": progress,
        "points": points,
        "files": output_files(directory, stamp),
        "outputDir": str(directory),
        "progressFile": str(operator_progress),
    }


def start_session(mode: str = "manual", direction_seconds: object = 10) -> dict[str, object]:
    global SESSION
    with LOCK:
        if SESSION and is_alive(SESSION):
            raise RuntimeError("Sesi masih aktif. Hentikan dengan aman atau tandai fase stabil.")
        if not CONSOLE_RUNNER.exists():
            raise RuntimeError(f"Runner console tidak ditemukan: {CONSOLE_RUNNER}")
        ensure_gld_bridge_ready()
        if mode not in {"manual", "auto"}:
            raise ValueError("Mode sesi harus manual atau auto.")
        direction_seconds = direction_confirmation_seconds(direction_seconds)
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        directory = SESSIONS_DIR / stamp
        directory.mkdir(parents=True, exist_ok=False)
        control = directory / f"MQ8_RECOVERY_BASELINE_{stamp}_CONTROL.txt"
        config = directory / "MQ8_TEST_CONFIG.json"
        config.write_text(json.dumps({"directionConfirmSeconds": direction_seconds}, separators=(",", ":")), encoding="utf-8")
        arguments = ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(CONSOLE_RUNNER), "-SessionStamp", stamp, "-OutputDirectory", str(directory), "-StartMode", mode, "-DirectionConfirmSeconds", str(direction_seconds), "-ConfigFile", str(config)]
        stdout_path = directory / f"MQ8_RECOVERY_BASELINE_{stamp}_runner.out.log"
        stderr_path = directory / f"MQ8_RECOVERY_BASELINE_{stamp}_runner.err.log"
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        stdout_handle = stdout_path.open("wb")
        stderr_handle = stderr_path.open("wb")
        process = subprocess.Popen(["powershell.exe", *arguments], cwd=str(REPO_ROOT), creationflags=creationflags, stdout=stdout_handle, stderr=stderr_handle)
        SESSION = {
            "process": process, "pid": process.pid,
            "stamp": stamp, "output": directory,
            "control": control, "config": config,
            "progress": directory / "HOT_DUTY_SWEEP_PROGRESS.md",
            "live": directory / f"MQ8_RECOVERY_BASELINE_{stamp}_live.csv",
            "stdout": stdout_path,
            "stdoutHandle": stdout_handle,
            "stderr": stderr_path,
            "stderrHandle": stderr_handle,
        }
        save_session(SESSION)
    return current_status()


# If the console web server is restarted mid-test, reattach to the persisted
# runner metadata instead of presenting an idle screen while IO8 is still run.
SESSION = load_session()


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".css": "text/css"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        pass

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/bootstrap":
            return json_response(self, {"apiToken": TOKEN, "version": APP_VERSION, "duties": TEST_DUTIES, "outputDir": str(OUTPUT_DIR)})
        if path == "/api/status":
            return json_response(self, current_status())
        if path == "/api/gld-log":
            query = self.path.split("?", 1)[1] if "?" in self.path else ""
            after = 0
            match = re.search(r"(?:^|&)after=(\d+)(?:&|$)", query)
            if match:
                after = int(match.group(1))
            return json_response(self, gld_serial_recent(after))
        if path == "/api/gld-events":
            return self.serve_gld_events()
        return super().do_GET()

    def serve_gld_events(self) -> None:
        """Same-origin SSE proxy for GLD serial events; it never owns COM3."""
        try:
            with urllib.request.urlopen(f"{GLD_BRIDGE_URL}/api/health", timeout=2) as response:
                health = json.loads(response.read().decode("utf-8"))
            token = str(health.get("csrfToken", ""))
            if len(token) < 16:
                raise RuntimeError("token GLD Operator tidak tersedia")
            upstream_url = f"{GLD_BRIDGE_URL}/api/events?token={urllib.parse.quote(token, safe='')}"
            upstream = urllib.request.urlopen(upstream_url, timeout=30)
        except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
            return json_response(self, {"error": f"stream GLD tidak tersedia: {exc}"}, HTTPStatus.BAD_GATEWAY)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            for raw in upstream:
                self.wfile.write(raw)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            upstream.close()

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.headers.get("X-MQ8-Test-Token") != TOKEN:
                return json_response(self, {"error": "token API tidak valid"}, HTTPStatus.FORBIDDEN)
            body = read_json(self)
            path = self.path.split("?", 1)[0]
            if path == "/api/start":
                return json_response(self, start_session(str(body.get("mode", "manual")).lower(), body.get("directionConfirmSeconds", 10)))
            if path == "/api/next":
                write_control("NEXT")
                return json_response(self, {"ok": True, "message": "Fase ditandai stabil; runner sedang pindah ke tahap berikutnya."})
            if path == "/api/mode":
                mode = str(body.get("mode", "")).lower()
                if mode not in {"manual", "auto"}:
                    raise ValueError("Mode harus manual atau auto.")
                write_control("MANUAL" if mode == "manual" else "AUTO")
                return json_response(self, {"ok": True, "message": "Mode Auto aktif: minimum 10 menit dan Stabil 3 menit." if mode == "auto" else "Mode Manual aktif: menunggu tombol Stabil."})
            if path == "/api/direction-confirmation":
                seconds = direction_confirmation_seconds(body.get("seconds"))
                write_direction_config(seconds)
                return json_response(self, {"ok": True, "message": f"Konfirmasi arah diubah menjadi {seconds:g} detik."})
            if path == "/api/stop":
                write_control("STOP")
                return json_response(self, {"ok": True, "message": "Stop aman diminta. Runner akan mengembalikan IO8 ke HIGH 100%."})
            if path == "/api/restart":
                write_control("STOP")
                return json_response(self, {"ok": True, "message": "Sesi dihentikan aman. Data tetap di folder sesi lama; setelah IO8 HIGH 100% terkonfirmasi, tekan Mulai baseline untuk sesi baru."})
            if path == "/api/export":
                snapshot = session_snapshot()
                if not snapshot:
                    raise RuntimeError("Belum ada sesi untuk diekspor.")
                live = snapshot["live"]
                if not isinstance(live, Path):
                    raise RuntimeError("File live sesi tidak valid.")
                return csv_response(self, live, f"MQ8_live_valid_{snapshot['stamp']}.csv")
            return json_response(self, {"error": "endpoint tidak ditemukan"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            return json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)


class ConsoleHttpServer(ThreadingHTTPServer):
    """Suppress only expected local-browser disconnects before a handler starts."""

    daemon_threads = True

    def handle_error(self, request: object, client_address: object) -> None:
        exc = sys.exc_info()[1]
        if exc is not None and is_client_disconnect(exc):
            return
        super().handle_error(request, client_address)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=5188, type=int)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("MQ8 Test Console hanya boleh dibuka pada loopback lokal.")
    server = ConsoleHttpServer((args.host, args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"MQ8_TEST_CONSOLE {url}", flush=True)
    if args.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
