"""Independent real HTTP/SSE/WebSocket-client proof, synthetic device only."""
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import threading
import time
import urllib.request
import urllib.error

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from csv_evidence import validate_csv


def main():
    ready = json.loads((HERE / 'fixture-ready.json').read_text())
    assert ready['simulation'] is True
    origin = ready['origin']
    token = ''
    def request(path, body=None):
        data = None if body is None else json.dumps(body).encode()
        headers = {'Origin': origin, 'Content-Type': 'application/json'}
        if token:
            headers['X-GLD-Bridge-Token'] = token
        req = urllib.request.Request(origin + path, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read())
    health = request('/api/health')
    assert health['simulation'] is True and health['features']['serial'] is False
    token = health['csrfToken']
    report = dict(mode='pc-simulation', hardware=False, cases=[], source='actual HTTP bridge + vendored WS + synthetic protocol2 peer')
    prefixes = {'direct': '/api/wireless-dataset', 'replay': '/api/wireless-replay'}
    def state(mode):
        return request(prefixes[mode] + '/state')
    def op(mode, action, body=None):
        return request(prefixes[mode] + '/' + action, body or {})
    def wait(predicate, seconds=15):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(.03)
        raise AssertionError('Bounded synthetic condition timed out')
    def csv_check(mode, original_count=None):
        snapshot = state(mode)
        exported = op(mode, 'export')
        journal = request('/sim/dual-state')
        original = next(s for s in journal['sessions'] if s['session_id'] == snapshot['session_id'])['original_samples']
        expected = original[:original_count] if original_count is not None else original
        checked = validate_csv(exported['csv'], device_id=snapshot['device_id'], session_id=snapshot['session_id'],
            profile_id=expected[0]['nulling_profile_id'], minimum=8, originals=expected)
        assert checked['count'] == snapshot['count'] == len(expected)
        assert Path(snapshot['path']).read_text(encoding='utf-8') == exported['csv']
        assert not journal['errors'], journal['errors']
        return snapshot, exported, checked
    # Prove inherited hardware routes are denied before touching collectors.
    for path in ('/api/serial/connect', '/api/firmware/upload'):
        try:
            request(path, {})
            raise AssertionError('Hardware write unexpectedly admitted')
        except urllib.error.HTTPError as error:
            assert error.code == 403
    # Actual SSE subscription, no browser required for persistence.
    events, stopped = [], threading.Event()
    def sse():
        req = urllib.request.Request(origin + '/api/events?token=' + token, headers={'Origin': origin})
        try:
            with urllib.request.urlopen(req, timeout=3) as response:
                for raw in response:
                    if stopped.is_set(): break
                    line = raw.decode().strip()
                    if line.startswith('event:'):
                        events.append(line[6:].strip())
        except Exception as error:
            events.append('reader_end:' + type(error).__name__)
    thread = threading.Thread(target=sse, daemon=True)
    thread.start()
    op('direct', 'connect', {'password': ready['password']})
    assert request('/sim/dual-state')['factory_calls'] == 1, 'Protocol detection opened a second handshake'
    op('direct', 'start', {'label': 'direct_clean', 'interval_ms': 500})
    request('/sim/acquire', {'count': 8})
    wait(lambda: state('direct')['count'] == 8)
    assert op('direct', 'stop')['complete']
    first, _, integrity = csv_check('direct')
    report['cases'].append(dict(name='protocol2_direct_clean', result='PASS', integrity=integrity))
    op('direct', 'disconnect')
    op('direct', 'connect', {'password': ready['password']})
    op('direct', 'start', {'label': 'direct_drop', 'interval_ms': 500})
    request('/sim/acquire', {'count': 8})
    wait(lambda: state('direct')['count'] == 8)
    before = state('direct')
    request('/sim/drop', {})
    wait(lambda: state('direct').get('cleanup_pending'))
    frozen = state('direct')
    original_bytes = Path(frozen['path']).read_bytes()
    original_history = frozen['history']
    assert frozen['count'] == 8 and frozen['state'] == 'incomplete' and not frozen['recovery_active']
    try:
        op('replay', 'connect', {'password': ready['password']})
        raise AssertionError('Replay was allowed during owned cleanup')
    except urllib.error.HTTPError:
        pass
    request('/sim/gap', {'count': 8})
    time.sleep(.15)
    assert Path(frozen['path']).read_bytes() == original_bytes
    request('/sim/resume', {})
    wait(lambda: state('direct').get('cleanup_confirmed'), 20)
    after = state('direct')
    assert not after['cleanup_pending'] and after['cleanup_stop_acknowledged']
    assert after['count'] == frozen['count'] and after['history'] == original_history
    assert after['session_id'] == before['session_id'] and after['path'] == before['path']
    assert Path(after['path']).read_bytes() == original_bytes
    _, _, integrity = csv_check('direct', 8)
    journal = request('/sim/dual-state')
    session = next(s for s in journal['sessions'] if s['session_id'] == after['session_id'])
    commands = session['commands']
    assert sum(c['cmd'] == 'START_DATASET' for c in commands) == 1
    assert any(c['cmd'] == 'RESUME_DATASET' for c in commands)
    assert any(c['cmd'] == 'STOP_DATASET' for c in commands)
    assert all(c['session_id'] == after['session_id'] for c in commands)
    durable = journal['durable_rows'][after['session_id']]
    assert [int(row['seq']) for row in durable] == list(range(len(session['original_samples'])))
    report['cases'].append(dict(name='protocol2_direct_drop_cleanup_frozen_original', result='PASS',
        integrity=integrity, original_csv_sha256=hashlib.sha256(original_bytes).hexdigest(),
        cleanup_saved_count=after['cleanup_saved_count'], durable_prefix=len(durable), starts=1))
    op('direct', 'disconnect')
    op('direct', 'connect', {'password': ready['password']})
    op('direct', 'start', {'label': 'direct_again', 'interval_ms': 500})
    request('/sim/acquire', {'count': 8})
    wait(lambda: state('direct')['count'] >= 8)
    assert op('direct', 'stop')['complete']
    _, _, integrity = csv_check('direct')
    report['cases'].append(dict(name='protocol2_next_direct_after_cleanup', result='PASS', integrity=integrity))
    op('direct', 'disconnect')
    op('replay', 'connect', {'password': ready['password']})
    op('replay', 'start', {'label': 'replay_recover', 'interval_ms': 500})
    request('/sim/acquire', {'count': 8})
    wait(lambda: state('replay')['count'] >= 8)
    initial = state('replay')
    request('/sim/drop', {})
    wait(lambda: state('replay')['recovery_active'])
    request('/sim/gap', {'count': 8})
    request('/sim/resume', {})
    wait(lambda: state('replay')['count'] >= initial['count'] + 8 and state('replay')['replayed_count'] > 0, 20)
    assert op('replay', 'stop')['complete']
    final, _, integrity = csv_check('replay')
    assert (final['session_id'], final['path'], final['boot_id']) == (initial['session_id'], initial['path'], initial['boot_id'])
    assert final['gap_count'] == final['duplicate_count'] == 0
    report['cases'].append(dict(name='protocol2_replay_after_direct_same_csv_recovery', result='PASS',
        integrity=integrity, replayed_count=final['replayed_count']))
    op('replay', 'disconnect')
    # Regression: completed replay retains Stop history across an idle connect.
    # After that idle transport disconnects it must release direct admission.
    op('replay', 'connect', {'password': ready['password']})
    idle = op('replay', 'disconnect')
    assert not idle['connected'] and idle['state'] in ('ready', 'not_ready', 'disconnected', 'complete')
    direct_ready = op('direct', 'connect', {'password': ready['password']})
    assert direct_ready['connected'] and direct_ready['ready']
    op('direct', 'disconnect')
    report['cases'].append(dict(name='completed_replay_idle_reconnect_disconnect_releases_direct', result='PASS'))
    request('/sim/manual', {})
    wait(lambda: 'wireless_dataset' in events and 'wireless_dataset_replay' in events)
    stopped.set()
    report.update(status='PASS', sse_events=sorted(set(events)), fixture_pid=ready['pid'])
    (HERE / 'host-verification-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
