"""Protocol1 regression through real Basic-auth RFC6455, synthetic peer only."""
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
APP = ROOT / 'apps/gld-operator'
sys.path[:0] = [str(APP), str(HERE)]
from wireless_dataset_direct import WirelessDatasetDirectCollector
from wireless_dataset import _transport_factory
from csv_evidence import validate_csv


def main():
    path = APP / 'tests/test_wireless_dataset.py'
    spec = importlib.util.spec_from_file_location('dual_legacy_reference', path)
    legacy = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = legacy
    spec.loader.exec_module(legacy)
    source = inspect.getsource(legacy.LoopbackPeer)
    assert source.count('for seq in (0, 1):') == source.count('total_samples=2') == 1
    # Retain the reviewed RFC6455/auth implementation; only increase synthetic
    # acquisition count from2 to8 in this private fixture copy.
    source = source.replace('for seq in (0, 1):', 'for seq in range(8):')
    source = source.replace('total_samples=2', 'total_samples=8')
    namespace = dict(vars(legacy))
    exec(compile(source, 'dual_legacy_reference_8rows', 'exec'), namespace)
    with tempfile.TemporaryDirectory() as output, namespace['LoopbackPeer']() as peer:
        calls = []
        def factory(url, **options):
            assert url == 'ws://192.168.4.1:81/dataset'
            calls.append(url)
            return _transport_factory(peer.url, **options)
        collector = WirelessDatasetDirectCollector(output, websocket_factory=factory, command_timeout=2)
        try:
            state = collector.connect('hotspot-password')
            assert state['protocol'] == 'gld-dataset-wifi/1'
            assert len(calls) == 1 and peer.authenticated
            collector.start('legacy_eight')
            deadline = time.monotonic() + 5
            while collector.snapshot()['count'] < 8 and time.monotonic() < deadline:
                time.sleep(.01)
            assert collector.stop()['complete']
            state = collector.snapshot()
            csv_text = collector.export_csv()['csv']
            template = legacy.Peer()
            template.session_id, template.label = state['session_id'], 'legacy_eight'
            original = [template.sample(seq) for seq in range(8)]
            integrity = validate_csv(csv_text, device_id='1001', session_id=state['session_id'],
                profile_id=5, minimum=8, originals=original)
            assert state['count'] == 8 and len(calls) == 1
            assert peer.commands == ['START_DATASET', 'STOP_DATASET'] and not peer.errors
            report = dict(status='PASS', mode='pc-simulation', hardware=False,
                protocol='gld-dataset-wifi/1', authenticated_rfc6455=True,
                handshakes=1, starts=1, complete=True, integrity=integrity,
                reference_source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                fixture_adaptation='Increase synthetic2-row count to8 only; original source unchanged')
            (HERE / 'legacy-verification-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps(report))
        finally:
            collector.disconnect()


if __name__ == '__main__':
    main()
