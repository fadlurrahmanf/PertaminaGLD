#!/usr/bin/env python3
"""GLD Dataset Collector — local web app for 1 Hz sensor streaming over serial.

Polls GET_STATUS at 1 Hz via serial. The GLD firmware updates sensor voltages
every SCAN_INTERVAL_MS (1000 ms) in running mode, so each GET_STATUS returns
fresh readings. No firmware modification required.

Serves the collector UI and bridges serial COM3 communication to the browser
via SSE (Server-Sent Events). Saves to timestamped CSV for the AI/ML team.
"""

from __future__ import annotations

import argparse
import csv
import json
import queue
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

try:
    import serial
    from serial.tools import list_ports
except Exception as exc:
    serial = None
    list_ports = None
    SERIAL_IMPORT_ERROR = str(exc)
else:
    SERIAL_IMPORT_ERROR = ""

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

SENSOR_NAMES = ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"]
ADC_SATURATION_THRESHOLD = 2.49  # ADS1256 VREF=2.5V, anything >= this is clipped
VERSION = "0.4.0"


# ---------------------------------------------------------------------------
# SSE Event Hub
# ---------------------------------------------------------------------------
class EventHub:
    def __init__(self) -> None:
        self._clients: set[queue.Queue[dict[str, Any]]] = set()
        self._lock = threading.Lock()

    def add(self) -> queue.Queue[dict[str, Any]]:
        q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=2000)
        with self._lock:
            self._clients.add(q)
        return q

    def remove(self, client: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._clients.discard(client)

    def emit(self, event: str, data: Any) -> None:
        item = {"event": event, "data": data}
        stale: list[queue.Queue[dict[str, Any]]] = []
        with self._lock:
            clients = list(self._clients)
        for client in clients:
            try:
                client.put_nowait(item)
            except queue.Full:
                stale.append(client)
        if stale:
            with self._lock:
                for c in stale:
                    self._clients.discard(c)


# ---------------------------------------------------------------------------
# Serial Bridge — single owner of the serial port
# ---------------------------------------------------------------------------
class SerialBridge:
    """Thread-safe serial port wrapper. Only one thread reads at a time."""

    def __init__(self, events: EventHub) -> None:
        self.events = events
        self._serial: Any = None
        self._lock = threading.Lock()  # guards _serial reference + read/write
        self.port = ""
        self.baud = 115200

    def list_ports(self) -> list[dict[str, Any]]:
        if list_ports is None:
            raise RuntimeError(f"pyserial unavailable: {SERIAL_IMPORT_ERROR}")
        return [
            {"path": p.device, "description": p.description}
            for p in list_ports.comports()
        ]

    def connect(self, port: str, baud: int = 115200) -> dict[str, Any]:
        if serial is None:
            raise RuntimeError(f"pyserial unavailable: {SERIAL_IMPORT_ERROR}")
        self.disconnect()
        ser = serial.Serial()
        ser.port = port
        ser.baudrate = baud
        ser.timeout = 0.2
        ser.write_timeout = 2
        ser.dtr = False
        ser.rts = False
        ser.open()
        try:
            ser.setDTR(False)
            ser.setRTS(False)
        except Exception:
            pass
        with self._lock:
            self._serial = ser
            self.port = port
            self.baud = baud
        self.events.emit("serial_status", {"connected": True, "port": port})
        return {"connected": True, "port": port}

    def disconnect(self) -> dict[str, Any]:
        with self._lock:
            ser = self._serial
            self._serial = None
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
        self.events.emit("serial_status", {"connected": False})
        return {"connected": False}

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._serial is not None and self._serial.is_open

    def write_line(self, line: str) -> None:
        if not line.endswith("\n"):
            line += "\n"
        with self._lock:
            ser = self._serial
        if ser is None or not ser.is_open:
            raise RuntimeError("serial port is not connected")
        ser.write(line.encode("utf-8", errors="replace"))
        ser.flush()

    def read_json_response(self, prefix: str, timeout_s: float = 2.0) -> dict | None:
        """Blocking read: sends nothing, just reads until prefix line found.

        Caller must have already written the command. This method reads serial
        output and returns the first JSON object after the given prefix.
        All intermediate lines are emitted as serial_rx events.
        """
        buf = b""
        deadline = time.time() + timeout_s
        with self._lock:
            ser = self._serial
            if ser is None or not ser.is_open:
                return None
            while time.time() < deadline:
                try:
                    n = ser.in_waiting
                    chunk = ser.read(n if n else 32)
                except Exception:
                    break
                if chunk:
                    buf += chunk
                    while b"\n" in buf:
                        raw, buf = buf.split(b"\n", 1)
                        line = raw.strip()
                        if not line:
                            continue
                        decoded = line.decode("utf-8", errors="replace")
                        self.events.emit("serial_rx", {"line": decoded})
                        if decoded.startswith(prefix):
                            payload = decoded[len(prefix):]
                            try:
                                return json.loads(payload)
                            except json.JSONDecodeError:
                                pass
                else:
                    time.sleep(0.01)
        return None


# ---------------------------------------------------------------------------
# Sensor Poller — sends GET_STATUS at 1 Hz, parses telemetry
# ---------------------------------------------------------------------------
class SensorPoller:
    """Polls GLD sensors via GET_STATUS at 1 Hz. Sole serial reader while active."""

    def __init__(self, bridge: SerialBridge, events: EventHub, collector: CsvCollector) -> None:
        self.bridge = bridge
        self.events = events
        self.collector = collector
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        # Baseline tracking for auto gas detection
        self._baseline: list[float] | None = None
        self._baseline_samples = 0
        self._baseline_window = 10  # samples to average for baseline

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.active:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def reset_baseline(self) -> None:
        """Reset baseline tracking (call when returning to clean air)."""
        self._baseline = None
        self._baseline_samples = 0

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            t0 = time.time()
            try:
                if not self.bridge.is_connected:
                    break
                self.bridge.write_line("GET_STATUS")
                resp = self.bridge.read_json_response("GLD_STATUS_JSON", timeout_s=2.0)
                if resp:
                    telemetry = resp.get("telemetry", {})
                    voltages = telemetry.get("sensorVoltage", [])
                    gains = telemetry.get("sensorGain", [])
                    statuses = telemetry.get("sensorStatus", [])
                    if len(voltages) == 8:
                        # Detect ADC saturation
                        saturated_channels = [
                            SENSOR_NAMES[i] for i, v in enumerate(voltages)
                            if v >= ADC_SATURATION_THRESHOLD
                        ]
                        is_saturated = len(saturated_channels) > 0

                        # Update baseline (rolling average of first N clean samples)
                        if self._baseline is None:
                            self._baseline = list(voltages)
                            self._baseline_samples = 1
                        elif self._baseline_samples < self._baseline_window:
                            for i in range(8):
                                self._baseline[i] = (
                                    self._baseline[i] * self._baseline_samples + voltages[i]
                                ) / (self._baseline_samples + 1)
                            self._baseline_samples += 1

                        # Compute delta from baseline
                        delta_max = 0.0
                        if self._baseline is not None and self._baseline_samples >= self._baseline_window:
                            for i in range(8):
                                d = abs(voltages[i] - self._baseline[i])
                                if d > delta_max:
                                    delta_max = d

                        gas_threshold = 0.05  # V delta from baseline = gas detected
                        gas_detected = delta_max > gas_threshold

                        sample = {
                            "ts": resp.get("uptimeMs", int(time.time() * 1000)),
                            "v": voltages,
                            "g": gains,
                            "s": statuses,
                            "gasClass": telemetry.get("gasClass"),
                            "confidence": telemetry.get("confidence"),
                            "alarm": telemetry.get("alarm"),
                            "mode": resp.get("mode", ""),
                            "device_id": resp.get("deviceId", ""),
                            "saturated": is_saturated,
                            "saturatedChannels": saturated_channels,
                            "gasDetected": gas_detected,
                            "deltaMax": round(delta_max, 6),
                        }
                        self.events.emit("sensor_data", sample)
                        # Write CSV only when recording is active
                        if self.collector.collecting:
                            self.collector.write_sample(sample)
            except Exception as exc:
                self.events.emit("serial_error", {"message": str(exc)})
            elapsed = time.time() - t0
            remaining = max(0, 1.0 - elapsed)
            self._stop.wait(timeout=remaining)


# ---------------------------------------------------------------------------
# CSV Collector
# ---------------------------------------------------------------------------
class CsvCollector:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._writer: csv.writer | None = None
        self._file: Any = None
        self._sample_count = 0
        self.filename = ""

    @property
    def collecting(self) -> bool:
        with self._lock:
            return self._writer is not None

    @property
    def sample_count(self) -> int:
        with self._lock:
            return self._sample_count

    def start(self, device_id: str = "F001", tag: str = "") -> str:
        with self._lock:
            if self._writer is not None:
                return self.filename
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            if tag:
                self.filename = f"gld_{device_id}_{ts}_{tag}.csv"
            else:
                self.filename = f"gld_{device_id}_{ts}.csv"
            filepath = DATA_DIR / self.filename
            self._file = open(filepath, "w", newline="", encoding="utf-8")
            self._writer = csv.writer(self._file)
            header = ["timestamp_ms", "wall_time"]
            for name in SENSOR_NAMES:
                header.append(f"voltage_{name}")
            header.append("saturated")
            self._writer.writerow(header)
            self._sample_count = 0
            return self.filename

    def write_sample(self, payload: dict) -> None:
        with self._lock:
            if self._writer is None:
                return
            wall_time = datetime.now(timezone.utc).isoformat()
            ts = payload.get("ts", 0)
            v = payload.get("v", [0] * 8)
            saturated = 1 if payload.get("saturated", False) else 0
            row = [ts, wall_time]
            row.extend(v)
            row.append(saturated)
            self._writer.writerow(row)
            self._file.flush()
            self._sample_count += 1

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._writer is None:
                return {"stopped": False}
            self._writer = None
            if self._file:
                self._file.close()
                self._file = None
            count = self._sample_count
            fname = self.filename
            self._sample_count = 0
            self.filename = ""
        return {"stopped": True, "filename": fname, "samples": count}


# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------
events_hub = EventHub()
serial_bridge = SerialBridge(events_hub)
csv_collector = CsvCollector()
sensor_poller = SensorPoller(serial_bridge, events_hub, csv_collector)


class CollectorHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(APP_DIR), **kwargs)

    def do_GET(self) -> None:
        if self.path == "/api/events":
            self._handle_sse()
        elif self.path == "/api/ports":
            self._json_response(serial_bridge.list_ports())
        elif self.path == "/api/status":
            self._json_response({
                "connected": serial_bridge.is_connected,
                "port": serial_bridge.port,
                "collecting": csv_collector.collecting,
                "polling": sensor_poller.active,
                "samples": csv_collector.sample_count,
                "filename": csv_collector.filename,
                "version": VERSION,
            })
        elif self.path == "/api/download_csv":
            self._download_csv()
        else:
            super().do_GET()

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b""
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = {}

        if self.path == "/api/serial/connect":
            port = payload.get("port", "COM3")
            try:
                result = serial_bridge.connect(port)
                sensor_poller.start()  # auto-start streaming on connect
                self._json_response(result)
            except Exception as exc:
                self._json_response({"connected": False, "error": str(exc)})

        elif self.path == "/api/serial/disconnect":
            sensor_poller.stop()
            csv_collector.stop()
            result = serial_bridge.disconnect()
            self._json_response(result)

        elif self.path == "/api/serial/command":
            line = payload.get("line", "")
            prefix = payload.get("prefix", "GLD_CMD_ACK_JSON")
            timeout = payload.get("timeout", 3)
            try:
                serial_bridge.write_line(line)
                resp = serial_bridge.read_json_response(prefix, timeout_s=timeout)
                self._json_response({"ok": resp is not None, "response": resp})
            except Exception as exc:
                self._json_response({"ok": False, "error": str(exc)})

        elif self.path == "/api/collect/start":
            device_id = payload.get("device_id", "F001")
            tag = payload.get("tag", "")
            filename = csv_collector.start(device_id, tag)
            self._json_response({"started": True, "filename": filename})

        elif self.path == "/api/collect/stop":
            result = csv_collector.stop()
            self._json_response(result)

        elif self.path == "/api/reset_baseline":
            sensor_poller.reset_baseline()
            self._json_response({"ok": True, "message": "Baseline reset"})

        elif self.path == "/api/switch_mode":
            mode = payload.get("mode", "running")
            try:
                serial_bridge.write_line(f"SET_MODE {mode}")
                self._json_response(
                    {"ok": True, "mode": mode, "note": "Device will reboot"}
                )
            except Exception as exc:
                self._json_response({"ok": False, "error": str(exc)})

        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def _json_response(self, data: Any) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _handle_sse(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        client_q = events_hub.add()
        try:
            while True:
                try:
                    item = client_q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                event = item["event"]
                data = json.dumps(item["data"])
                msg = f"event: {event}\ndata: {data}\n\n"
                self.wfile.write(msg.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            events_hub.remove(client_q)

    def _download_csv(self) -> None:
        if csv_collector.filename:
            target = DATA_DIR / csv_collector.filename
        else:
            csvs = sorted(DATA_DIR.glob("gld_*.csv"), reverse=True)
            if not csvs:
                self.send_error(HTTPStatus.NOT_FOUND, "No CSV files found")
                return
            target = csvs[0]
        if not target.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/csv")
        self.send_header(
            "Content-Disposition", f'attachment; filename="{target.name}"'
        )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="GLD Dataset Collector")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8081)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), CollectorHandler)
    url = f"http://{args.host}:{args.port}"
    print(f"GLD Dataset Collector v{VERSION}")
    print(f"Serving at {url}")
    print(f"Data directory: {DATA_DIR}")
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        sensor_poller.stop()
        csv_collector.stop()
        serial_bridge.disconnect()
        server.shutdown()


if __name__ == "__main__":
    main()
