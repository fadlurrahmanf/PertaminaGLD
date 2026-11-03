"""Verify archived browser/SSE evidence, then stop only the authorized fixture."""
import hashlib
import json
from pathlib import Path
import socket
import time
import urllib.request

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    ready=json.loads((HERE/'ready.json').read_text())
    assert (ready['pid'],ready['http_port'],ready['ws_port'])==(20248,55265,55264)
    report=json.loads((HERE/'verification-report.json').read_text())
    journal=json.loads((HERE/'verified-journal.json').read_text())
    browser_path=HERE.parent/'browser-output/browser-evidence.json'
    browser=json.loads(browser_path.read_text())
    sse_path=HERE/'sse-observation.json';sse=json.loads(sse_path.read_text())
    assert report['status']=='PASS' and browser['ok'] and sse['status']=='PASS'
    assert [row['rows'] for row in report['actual_browser_downloads']]==[20,28,8,50]
    assert report['actual_browser_downloads'][0]['historical_prefix']
    public={}
    for data in journal['actual_durable_files'].values():
        if data['kind']=='.jsonl':
            for row in data['rows']:
                if not row.get('private_cleanup'):
                    public[(row['session_id'],row['seq'])]=row
    sample_count=0
    for event in sse['events']:
        assert event['namespace']=='dataset_workflow'
        payload=event['payload']
        if payload.get('type')=='sample':
            sample=payload['sample'];key=(sample['session_id'],sample['seq'])
            assert sample==public[key] and not sample.get('private_cleanup')
            assert len(sample['sensor_voltage'])==len(sample['sensor_gain'])==len(sample['sensor_status'])==8
            sample_count+=1
    assert sample_count>0 and len(browser['screenshots'])==11
    shots=[]
    for shot in browser['screenshots']:
        path=Path(shot['path']);assert path.is_file()
        shots.append(dict(path=str(path),sha256=sha(path)))
    report.update(browser_evidence_sha256=sha(browser_path),browser_screenshots=shots,
        screenshot_review='Root-owned visual QA/DOM/8-trace proof; this independent verifier checks artifact hashes and sample data.',
        browser_chart=browser['chart'],sse=dict(status='PASS',events=len(sse['events']),
            sample_events=sample_count,state_events=len(sse['events'])-sample_count,
            all_sample_fields_equal_public_canonical=True,private_cleanup_not_exposed=True,sha256=sha(sse_path)),
        host_final_report=str(HERE/'host-final-verification-report.json'),
        fixture_shutdown=dict(pid=20248,http_port=55265,ws_port=55264,requested=False))
    target=HERE/'final-verification-report.json'
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    request=urllib.request.Request(ready['origin']+'/sim/shutdown',data=b'{}',headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=10) as response:
        assert json.load(response)['ok']
    report['fixture_shutdown']['requested']=True
    def closed(port):
        try:
            with socket.create_connection(('127.0.0.1',port),timeout=.2):return False
        except OSError:return True
    deadline=time.monotonic()+10
    while time.monotonic()<deadline and not all(closed(port) for port in (55265,55264)):
        time.sleep(.1)
    report['fixture_shutdown'].update(http_closed=closed(55265),ws_closed=closed(55264))
    assert report['fixture_shutdown']['http_closed'] and report['fixture_shutdown']['ws_closed']
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(status='PASS',sessions=report['sessions'],canonical_rows=report['all_canonical_rows'],
        public_rows=report['positive_public_rows'],private_rows=report['private_cleanup_rows'],
        downloads=[row['rows'] for row in report['actual_browser_downloads']],sse_events=len(sse['events']),
        fixture_shutdown=report['fixture_shutdown'])))

if __name__=='__main__':main()
