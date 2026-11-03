"""Independent all-field verification of quiescent real-wire simulation files."""
import csv
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_rows import canonical_matches, verify_public_rows, FEATURE_ORDER

HERE=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--browser-evidence',type=Path)
    args=parser.parse_args()
    ready=json.loads((HERE/'ready.json').read_text())
    journal=json.load(urllib.request.urlopen(ready['origin']+'/sim/state',timeout=10))
    state=journal['workflow']
    assert not state['connected'] and not state['cleanup_pending'] and not state['recovery_active']
    assert not journal['errors']
    host=json.loads((HERE/'host-report.json').read_text())
    assert host['status']=='PASS' and host['loaded_source_sha256']==ready['loaded_source_sha256']
    negatives={case['path'] for case in host['cases'] if case.get('negative_fixture') and
               Path(case['path']).is_relative_to(Path(ready['output']))}
    originals={}
    for session in journal['sessions']:
        sid=session['session_id']
        assert sum(command['cmd']=='START_DATASET' for command in session['commands'])==1
        assert all(command.get('session_id')==sid for command in session['commands'])
        for sample in session['original_samples']:
            key=(sid,sample['seq']);assert key not in originals
            originals[key]=sample
    canonical={};public_canonical={};private_count=0
    for path in sorted(Path(ready['output']).rglob('*.jsonl')):
        data=journal['actual_durable_files'][str(path)]
        assert sha(path)==data['sha256']
        entries=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]
        assert entries==data['rows']
        perfile=set()
        for entry in entries:
            key=(entry['session_id'],entry['seq'])
            assert key not in perfile and key in originals
            canonical_matches(entry,originals[key])
            assert entry['boot_id']==journal['device']['boot_id']
            assert entry['model']==journal['device']['model']
            perfile.add(key)
            if key in canonical:assert canonical[key]==entry
            canonical[key]=entry
            if entry.get('private_cleanup'):private_count+=1
            else:public_canonical[key]=entry
    assert set(canonical)==set(originals),'Some actual acquisition samples are not durably retained'
    files=[];public_rows=positive_rows=0
    for path in sorted((Path(ready['output'])/'public').glob('*.csv')):
        data=journal['actual_durable_files'][str(path)]
        raw=path.read_bytes();negative=str(path) in negatives
        if negative:
            sentinel=b'EXTERNAL_SIMULATION_TAMPER\n'
            assert raw.endswith(sentinel)
            assert hashlib.sha256(raw[:-len(sentinel)]).hexdigest()==data['sha256']
            text=raw[:-len(sentinel)].decode('utf-8')
        else:
            assert hashlib.sha256(raw).hexdigest()==data['sha256']
            text=raw.decode('utf-8')
        reader=csv.DictReader(io.StringIO(text));rows=list(reader)
        assert 'timestamp_ms' in reader.fieldnames
        assert all('voltage_'+feature in reader.fieldnames for feature in FEATURE_ORDER)
        assert rows==data['rows']
        checked=verify_public_rows(rows,public_canonical,originals)
        public_rows+=len(rows)
        if not negative:positive_rows+=len(rows)
        files.append(dict(path=str(path),sha256=sha(path),expected_tamper_control=negative,**checked))
    downloads=[]
    if args.browser_evidence:
        browser=json.loads(args.browser_evidence.read_text(encoding='utf-8'))
        assert browser['ok'] and browser['simulation'] and browser['hardware'] is False
        for download in browser['downloads']:
            path=Path(download['path']);source=Path(download['source_csv'])
            assert source.is_relative_to(Path(ready['output']))
            text=path.read_text(encoding='utf-8-sig')
            reader=csv.DictReader(io.StringIO(text));rows=list(reader)
            source_reader=csv.DictReader(io.StringIO(source.read_text(encoding='utf-8')))
            source_rows=list(source_reader)
            assert reader.fieldnames==source_reader.fieldnames
            assert rows==source_rows[:len(rows)], 'Browser snapshot is not the exact retained file prefix'
            assert len(rows)==download['count'] and sha(path)==download['sha256']
            checked=verify_public_rows(rows,public_canonical,originals)
            downloads.append(dict(path=str(path),source_csv=str(source),sha256=sha(path),
                rows=len(rows),final_source_rows=len(source_rows),historical_prefix=len(rows)<len(source_rows),
                exact_originals=True,**{key:value for key,value in checked.items() if key!='rows'}))
        assert len(downloads)==4
    assert len(journal['durability_audit'])==sum(command['cmd']=='ACK_SAMPLES' for session in journal['sessions'] for command in session['commands'])
    report=dict(status='PASS',mode='pc-simulation',device_validation=False,
        loaded_source_sha256=ready['loaded_source_sha256'],sessions=len(journal['sessions']),
        all_canonical_rows=len(canonical),private_cleanup_rows=private_count,
        public_prefix_rows_verified=public_rows,positive_public_rows=positive_rows,
        expected_tamper_controls=len(negatives),files=files,
        prediction_statuses=sorted({entry['prediction']['status'] for entry in canonical.values()}),
        ack_before_durable_violation=False,actual_fsync_calls=len(journal['fsync_events']),
        wire_ack_checks=len(journal['durability_audit']),
        actual_browser_downloads=downloads,
        evidence='Actual loopback RFC6455 acquisition; actual service ledger/CSV bytes and fsync instrumentation. No hardware or C++ execution claim.')
    (HERE/'verified-journal.json').write_text(json.dumps(journal,indent=2),encoding='utf-8')
    (HERE/'verification-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('status','sessions','all_canonical_rows','private_cleanup_rows','positive_public_rows','public_prefix_rows_verified','expected_tamper_controls','wire_ack_checks')}))

if __name__=='__main__':main()
