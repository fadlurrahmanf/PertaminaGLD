"""Persistent SIMULATION: actual workflow bridge/UI/service, synthetic GLD/OS."""
from __future__ import annotations
import csv
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
import time
from urllib.parse import urlparse
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from wire_peer import ROOT, APP, Engine, FakeWindowsPlatform, PASSWORD, PROTECTED_PORTS, Server
from verify_rows import canonical_matches, public_matches
sys.path.insert(0, str(APP))
# Reuse audited asset/origin/HTTP protections only. Globals are isolated in this
# process and all output locations are redirected before any request is served.
spec = importlib.util.spec_from_file_location('workflow_fixture_http_base', ROOT / 'tmp/wireless-stage2/e2e/serve_simulation.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
OUTPUT = HERE / 'output' / (time.strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6])
engine = service = platform = http_server = None
durable_files = {}
durability_events = []
evidence_lock = threading.RLock()
audit_lock = threading.RLock()


def persist_snapshot(descriptor):
    """Audit precisely the file whose descriptor actually completed os.fsync."""
    os.fsync(descriptor)
    identity = os.fstat(descriptor)
    matches = []
    for path in OUTPUT.rglob('*'):
        if path.is_file() and path.suffix in {'.csv', '.jsonl'}:
            if os.path.samestat(identity, path.stat()):
                matches.append(path)
    if len(matches) != 1:
        raise RuntimeError('Cannot uniquely identify actual fsynced fixture file')
    path = matches[0]
    text = path.read_text(encoding='utf-8')
    if path.suffix == '.jsonl':
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        with path.open(encoding='utf-8', newline='') as stream:
            rows = list(csv.DictReader(stream))
    with audit_lock:
        durable_files[str(path)] = dict(kind=path.suffix, rows=rows,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        durability_events.append(dict(path=str(path), rows=len(rows),
            host_monotonic_s=time.monotonic(), kind='actual_fsync'))


def durable_prefix(sid):
    canonical, public = {}, {}
    with audit_lock:
        files = list(durable_files.values())
    for data in files:
        for entry in data['rows']:
            # Service canonical schema is a flat raw sample augmented with
            # logical IDs. Supporting `sample` explicitly is not inventing data.
            row = entry.get('sample', entry) if isinstance(entry, dict) else {}
            if row.get('session_id') != sid:
                continue
            seq = int(row['seq'])
            if data['kind'] == '.jsonl': canonical[seq] = entry
            else: public[seq] = entry
    # Private Direct cleanup is ledger-only after the publicly frozen prefix;
    # its ownership/segmentation markers are verified once service schema lands.
    snapshot = service.snapshot() if service is not None else {}
    originals={sample['seq']:sample for sample in engine.sessions.get(sid,{}).get('original_samples',[])}
    for seq,entry in canonical.items():
        canonical_matches(entry, originals[seq])
    if snapshot.get('cleanup_pending') and snapshot.get('session_id')==sid:
        return canonical
    eligible={}
    for seq,entry in canonical.items():
        if seq in public:
            public_matches(public[seq],entry)
            eligible[seq]=entry
    return eligible


def evidence(name=None):
    with evidence_lock:
        return _evidence(name)


def _evidence(name=None):
    result = engine.snapshot()
    with audit_lock:
        files, events = copy.deepcopy(durable_files), copy.deepcopy(durability_events)
    result.update(mode='pc-simulation', device_validation=False,
        workflow=service.snapshot(), platform=dict(simulation=True, joins=platform.joins, picks=platform.picked),
        actual_durable_files=files, fsync_events=events,
        endpoint=dict(http_port=http_server.server_port, ws_port=engine.server.server_port))
    if name:
        result['checkpoint'] = str(name)
    temporary = HERE / 'evidence.pending.json'
    temporary.write_text(json.dumps(result, indent=2), encoding='utf-8')
    os.replace(temporary, HERE / 'evidence.json')
    return result


class Handler(base.Handler):
    def body(self, raw, mime='text/html; charset=utf-8', status=200):
        if isinstance(raw, str):
            raw = raw.replace('Stage2 Replay Simulation', 'SIMULASI Workflow GLD')
            raw = raw.replace('SIMULATION — Protocol 2 replay', 'SIMULASI PC — Workflow protocol3')
            raw = raw.replace('Select five-minute replay.', 'Wizard protokol3; data sintetis.')
            raw = raw.replace('STAGE2 SIMULATION — choose replay mode. Synthetic sensors only.',
                'SIMULASI PC — sensor GLD dan platform Windows sintetis; bukan perangkat asli.')
        return super().body(raw, mime, status)

    def do_GET(self):
        if not self.allowed(): return self.blocked()
        path = urlparse(self.path).path
        if path in {'/sim/state', '/sim/workflow-state'}:
            return base.bridge.json_response(self, evidence())
        if path == '/api/health':
            return base.bridge.json_response(self, dict(ok=True, appId=base.bridge.APP_ID,
                version=base.bridge.VERSION+'-WORKFLOW-SIMULATION', csrfToken=base.bridge.BRIDGE_CSRF_TOKEN,
                simulation=True, features=dict(serial=False, mqtt=False, mqttBroker=False,
                    datasetMonitor=False, datasetOutput=True, datasetWorkflow=True,
                    wirelessDataset=False, wirelessReplay=False, firmwareUpload=False, networkInfo=False),
                slots={}, maxSlots=0, mqttBroker=dict(running=False), errors={}))
        if path in {'/api/wireless-dataset/state', '/api/wireless-replay/state'}:
            return base.bridge.json_response(self, dict(state='disconnected', connected=False,
                ready=False, history=[], count=0, complete=False, simulation=True, unavailable=True))
        if path == '/api/dataset-workflow/state':
            return base.bridge.Handler.do_GET(self)
        return super().do_GET()

    def do_POST(self):
        if not self.allowed(): return self.blocked()
        path = urlparse(self.path).path
        if path.startswith('/sim/'):
            payload = base.bridge.read_json(self)
            action = path.removeprefix('/sim/')
            if action == 'shutdown':
                base.bridge.json_response(self, {'ok': True, 'simulation': True})
                threading.Thread(target=shutdown, daemon=True).start()
                return
            if action != 'checkpoint': engine.control(action, payload)
            return base.bridge.json_response(self, evidence(payload.get('name')))
        allowed = {f'/api/dataset-workflow/{action}' for action in ('scan','select','connect','choose-file',
            'configure','lock','start','pause','resume','stop','continue','reset','disconnect','export')}
        if path in allowed:
            result = base.bridge.Handler.do_POST(self)
            evidence()
            return result
        return self.blocked()


def shutdown():
    evidence('shutdown')
    service.disconnect()
    engine.close()
    http_server.shutdown()


def main():
    global engine, service, platform, http_server
    from dataset_workflow import DatasetWorkflowService
    OUTPUT.mkdir(parents=True, exist_ok=True)
    engine = Engine()
    platform = FakeWindowsPlatform(OUTPUT / 'public')
    service = DatasetWorkflowService(OUTPUT / 'private', platform,
        lambda payload: base.bridge.events.emit('dataset_workflow', payload),
        websocket_factory=engine.factory, fsync=persist_snapshot, command_timeout=3, silence_timeout=3)
    engine.durability_provider = durable_prefix
    engine.collector = service
    http_server = Server(('127.0.0.1', 0), Handler)
    if http_server.server_port in PROTECTED_PORTS:
        raise RuntimeError('Refuse protected port')
    base.engine, base.http_server = engine, http_server
    base.OUTPUT, base.EVIDENCE = OUTPUT, HERE / 'unused-base-evidence.json'
    base.bridge.DATASET_OUTPUT_DIR = OUTPUT
    base.bridge.SESSION_LOG_DIR = OUTPUT / 'logs'
    base.bridge.BRIDGE_ALLOWED_ORIGINS = {f'http://127.0.0.1:{http_server.server_port}'}
    base.bridge.serial_bridges.clear()
    base.bridge.dataset_workflow_service = service
    ready = dict(mode='pc-simulation', device_validation=False, pid=os.getpid(),
        origin=f'http://127.0.0.1:{http_server.server_port}',
        app_url=f'http://127.0.0.1:{http_server.server_port}/gld/',
        http_port=http_server.server_port, ws_port=engine.server.server_port,
        password=PASSWORD, output=str(OUTPUT), evidence=str(HERE / 'evidence.json'))
    ready['loaded_source_sha256'] = {str(path.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (APP/'dataset_workflow.py',APP/'wireless_dataset_workflow.py',APP/'bridge.py')}
    (HERE/'ready.json').write_text(json.dumps(ready,indent=2),encoding='utf-8')
    print(json.dumps({key:ready[key] for key in ('mode','pid','app_url','ws_port')}),flush=True)
    try:
        http_server.serve_forever(poll_interval=.03)
    finally:
        engine.close()
        http_server.server_close()


if __name__=='__main__': main()
