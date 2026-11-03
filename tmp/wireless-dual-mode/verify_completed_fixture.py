"""Independent read-only verification of all current synthetic sessions/CSVs."""
import csv
import io
import json
from pathlib import Path
import sys
import urllib.request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from csv_evidence import validate_csv, digest, CSV_HEADERS


def main():
    ready = json.loads((HERE / 'fixture-ready.json').read_text())
    journal = json.load(urllib.request.urlopen(ready['origin'] + '/sim/dual-state', timeout=5))
    results = []
    for session in journal['sessions']:
        originals = session['original_samples']
        if not originals:
            continue
        sid = session['session_id']
        paths = list(Path(ready['output']).glob('*_' + sid + '.csv'))
        assert len(paths) == 1, 'Expected exactly one public CSV per session'
        text = paths[0].read_text(encoding='utf-8')
        common = dict(device_id=originals[0]['device_id'], session_id=sid,
                      profile_id=originals[0]['nulling_profile_id'], minimum=1)
        public = validate_csv(text, **common, originals=originals)
        durable = journal['durable_rows'][sid]
        buffer = io.StringIO(newline='')
        writer = csv.DictWriter(buffer, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(durable)
        all_rows = validate_csv(buffer.getvalue(), **common, originals=originals)
        assert all_rows['count'] == len(originals), 'Unpersisted synthetic prefix remains'
        commands = session['commands']
        assert sum(command['cmd'] == 'START_DATASET' for command in commands) == 1
        assert all(command['session_id'] == sid for command in commands)
        for command in commands:
            if command['cmd'] == 'ACK_SAMPLES':
                assert command['next_seq'] <= all_rows['count']
        results.append(dict(session_id=sid, label=session['label'], public_csv=str(paths[0]),
            public_sha256=digest(paths[0]), public_rows=public['count'],
            all_durable_rows=all_rows['count'], exact_all_fields=True, starts=1))
    assert len(results) >= 4 and not journal['errors']
    report = dict(status='PASS', mode='pc-simulation', hardware=False,
        scope='Read-only verification of actual fixture HTTP journal, public CSV bytes and fsynced private ledger',
        sessions=results, public_rows=sum(x['public_rows'] for x in results),
        total_durable_rows=sum(x['all_durable_rows'] for x in results),
        ack_at_send_gate='Fixture refuses ACK lacking actual fsynced prefix; no such errors observed')
    (HERE / 'independent-csv-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (HERE / 'verified-fixture-journal.json').write_text(json.dumps(journal, indent=2), encoding='utf-8')
    print(json.dumps(dict(status='PASS', sessions=len(results), public_rows=report['public_rows'],
                         total_durable_rows=report['total_durable_rows'])))


if __name__ == '__main__':
    main()
