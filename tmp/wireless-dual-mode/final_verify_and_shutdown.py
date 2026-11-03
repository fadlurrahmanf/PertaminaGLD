"""Read-only evidence verification, then stop ONLY the explicitly owned fixture."""
import csv
import io
import json
from pathlib import Path
import socket
import sys
import time
import urllib.request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from csv_evidence import validate_csv, digest


def main():
    ready = json.loads((HERE / 'fixture-ready.json').read_text())
    assert ready['pid'] == 24624 and ready['http_port'] == 56584 and ready['ws_port'] == 56583
    journal = json.loads((HERE / 'verified-fixture-journal.json').read_text())
    independent = json.loads((HERE / 'independent-csv-verification.json').read_text())
    browser_path = HERE / 'browser-output/browser-evidence.json'
    browser = json.loads(browser_path.read_text())
    assert independent['status'] == 'PASS' and len(independent['sessions']) == 8
    assert browser['ok'] is True and browser['device_validation'] is False
    checked = []
    for captured in browser['sessions']:
        sid = captured['session_id']
        original = next(s for s in journal['sessions'] if s['session_id'] == sid)['original_samples']
        source = Path(captured['csv_path'])
        download = HERE / 'browser-output/downloads' / captured['filename']
        assert download.is_file() and source.is_file()
        public_text, download_text = source.read_text(encoding='utf-8'), download.read_text(encoding='utf-8-sig')
        public_rows = list(csv.DictReader(io.StringIO(public_text)))
        download_rows = list(csv.DictReader(io.StringIO(download_text)))
        assert download_rows == public_rows, 'Actual browser download differs from backend CSV'
        integrity = validate_csv(download_text, device_id=original[0]['device_id'], session_id=sid,
            profile_id=original[0]['nulling_profile_id'], minimum=8, originals=original)
        assert integrity['count'] == captured['count']
        checked.append(dict(scenario=captured['scenario'], session_id=sid, rows=integrity['count'],
            complete=captured['complete'], actual_browser_download=str(download),
            download_sha256=digest(download), backend_csv=str(source), backend_sha256=digest(source),
            parsed_all_fields_equal=True, exact_synthetic_originals=True))
    assert len(checked) == 4 and [row['rows'] for row in checked] == [12, 8, 8, 49]
    assert len(browser['screenshots']) == 5
    report = dict(status='PASS', mode='pc-simulation', device_validation=False,
        loaded_source_sha256=ready['loaded_source_sha256'],
        all_sessions=len(independent['sessions']), public_rows=independent['public_rows'],
        total_durable_rows=independent['total_durable_rows'],
        actual_browser_downloads=checked, browser_evidence_sha256=digest(browser_path),
        screenshots_recorded=5, screenshot_visual_review='Root-owned browser evidence; this verifier checks CSV data only',
        fixture_shutdown=dict(pid=ready['pid'], http_port=ready['http_port'], ws_port=ready['ws_port'], requested=False))
    path = HERE / 'final-verification-report.json'
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    request = urllib.request.Request(ready['origin'] + '/sim/shutdown', data=b'{}',
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=5) as response:
        assert json.load(response)['ok']
    report['fixture_shutdown']['requested'] = True
    deadline = time.monotonic() + 10
    def closed(port):
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=.2):
                return False
        except OSError:
            return True
    while time.monotonic() < deadline:
        if all(closed(port) for port in (56584, 56583)):
            break
        time.sleep(.1)
    report['fixture_shutdown'].update(http_closed=closed(56584), ws_closed=closed(56583))
    assert report['fixture_shutdown']['http_closed'] and report['fixture_shutdown']['ws_closed']
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(dict(status='PASS', all_sessions=8, public_rows=report['public_rows'],
        total_durable_rows=report['total_durable_rows'], browser_download_rows=sum(x['rows'] for x in checked),
        downloads=4, fixture_shutdown=report['fixture_shutdown'])))


if __name__ == '__main__':
    main()
