"""SIMULATION ONLY: actual bridge/UI/collectors with injected loopback GLD."""
from __future__ import annotations
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / 'tmp/wireless-stage2/e2e'
sys.path[:0] = [str(OLD), str(ROOT / 'apps/gld-operator')]
import serve_simulation as base
from wire_peer import Engine as BaseEngine, PASSWORD, Server, PROTECTED_PORTS
from wireless_dataset_direct import WirelessDatasetDirectCollector
from wireless_dataset_replay import WirelessDatasetReplayCollector

OUTPUT = HERE / 'fixture-output'
base.OUTPUT, base.EVIDENCE = OUTPUT, HERE / 'fixture-evidence.json'


class Engine(BaseEngine):
    def __init__(self):
        self.durable = {}
        self.collectors = {}
        self.factory_calls = 0
        super().__init__()
        self.auto_capture = False

    def factory(self, url, **options):
        self.factory_calls += 1
        return super().factory(url, **options)

    def fsync(self, descriptor):
        os.fsync(descriptor)
        paths = list(OUTPUT.glob('*.csv'))
        direct = self.collectors.get('direct')
        delegate = direct._delegate if direct else None
        sink = getattr(delegate, '_sink_path', None)
        if sink and sink.is_file():
            paths.append(sink)
        for path in paths:
            with path.open(encoding='utf-8', newline='') as stream:
                rows = list(csv.DictReader(stream))
            for row in rows:
                ledger = self.durable.setdefault(row['session_id'], {})
                seq = int(row['seq'])
                if seq in ledger and ledger[seq] != row:
                    raise RuntimeError('Durable CSV tuple changed')
                ledger[seq] = row

    def command(self, command, peer):
        if command.get('cmd') == 'START_DATASET' and not self.device.sampling:
            # The reused unit-test peer initializes offered_next at handshake;
            # a new session resets sequence space just as firmware START does.
            peer.offered_next = 0
            peer.summary_sent = False
        if command.get('cmd') == 'ACK_SAMPLES':
            rows = self.durable.get(command['session_id'], {})
            if not all(seq in rows for seq in range(command['next_seq'])):
                self.errors.append('ACK_before_fsync_prefix')
                raise RuntimeError('ACK exceeds actual fsynced prefix')
        return super().command(command, peer)


class Handler(base.Handler):
    def body(self, raw, mime='text/html; charset=utf-8', status=200):
        if isinstance(raw, str):
            raw = raw.replace('Stage2 Replay Simulation', 'Dual Mode PC Simulation')
            raw = raw.replace('STAGE2 SIMULATION — choose replay mode.', 'DUAL MODE SIMULATION — synthetic GLD, no hardware.')
        return super().body(raw, mime, status)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/sim/dual-state' and self.allowed():
            evidence = base.save()
            evidence.update(mode='pc-simulation', protocol='gld-dataset-wifi/2',
                collectors={key: value.snapshot() for key, value in base.engine.collectors.items()},
                durable_rows={sid: [rows[key] for key in sorted(rows)] for sid, rows in base.engine.durable.items()},
                factory_calls=base.engine.factory_calls)
            return base.bridge.json_response(self, evidence)
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/sim/acquire' and self.allowed():
            base.engine.auto_capture = False
        if path == '/sim/manual' and self.allowed():
            base.bridge.read_json(self)
            base.engine.auto_capture = False
            return base.bridge.json_response(self, base.save())
        allowed = {f'/api/{prefix}/{action}' for prefix in ('wireless-dataset', 'wireless-replay')
                   for action in ('connect', 'start', 'stop', 'disconnect', 'export')}
        if path in allowed and self.allowed():
            result = base.bridge.Handler.do_POST(self)
            base.save()
            return result
        return super().do_POST()


def main():
    global OUTPUT
    OUTPUT = HERE / 'fixture-output' / (time.strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:6])
    base.OUTPUT = OUTPUT
    OUTPUT.mkdir(parents=True, exist_ok=True)
    base.engine = Engine()
    base.http_server = Server(('127.0.0.1', 0), Handler)
    if base.http_server.server_port in PROTECTED_PORTS:
        raise RuntimeError('Refuse protected port')
    bridge = base.bridge
    bridge.DATASET_OUTPUT_DIR, bridge.SESSION_LOG_DIR = OUTPUT, OUTPUT / 'logs'
    bridge.BRIDGE_ALLOWED_ORIGINS = {f'http://127.0.0.1:{base.http_server.server_port}'}
    bridge.serial_bridges.clear()
    for mode, cls, event in [('direct', WirelessDatasetDirectCollector, 'wireless_dataset'),
                             ('replay', WirelessDatasetReplayCollector, 'wireless_dataset_replay')]:
        collector = cls(OUTPUT, lambda payload, event=event: bridge.events.emit(event, payload),
            websocket_factory=base.engine.factory, fsync=base.engine.fsync,
            command_timeout=3, silence_timeout=3)
        base.engine.collectors[mode] = collector
    bridge.wireless_dataset_collector = base.engine.collectors['direct']
    bridge.wireless_replay_collector = base.engine.collectors['replay']
    base.engine.collector = bridge.wireless_replay_collector
    ready = dict(mode='pc-simulation', simulation=True, pid=os.getpid(),
        origin=f'http://127.0.0.1:{base.http_server.server_port}',
        app_url=f'http://127.0.0.1:{base.http_server.server_port}/gld/',
        http_port=base.http_server.server_port, ws_port=base.engine.server.server_port,
        password=PASSWORD, output=str(OUTPUT))
    ready['loaded_source_sha256'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in ('apps/gld-operator/wireless_dataset_direct.py', 'apps/gld-operator/wireless_dataset_replay.py',
                     'apps/gld-operator/wireless_dataset.py', 'apps/gld-operator/bridge.py')}
    (HERE / 'fixture-ready.json').write_text(json.dumps(ready, indent=2), encoding='utf-8')
    print(json.dumps({key: ready[key] for key in ('mode', 'pid', 'app_url', 'ws_port')}), flush=True)
    try:
        base.http_server.serve_forever(poll_interval=0.03)
    finally:
        for value in base.engine.collectors.values():
            value.disconnect()
        base.engine.close()
        base.http_server.server_close()


if __name__ == '__main__':
    main()
