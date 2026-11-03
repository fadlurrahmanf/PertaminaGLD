"""Read-only loopback SSE observer; never sends any POST/action."""
import json
from pathlib import Path
import time
import urllib.request

HERE=Path(__file__).resolve().parent
ready=json.loads((HERE/'ready.json').read_text())
origin=ready['origin']
health=json.load(urllib.request.urlopen(origin+'/api/health',timeout=5))
assert health['simulation'] is True
token=health['csrfToken']
report=dict(mode='pc-simulation',readonly=True,pid_fixture=ready['pid'],events=[],errors=[])
deadline=time.monotonic()+90
try:
    while time.monotonic()<deadline:
        req=urllib.request.Request(origin+'/api/events?token='+token,headers={'Origin':origin})
        try:
            with urllib.request.urlopen(req,timeout=5) as stream:
                event=''
                for raw in stream:
                    if time.monotonic()>=deadline:break
                    line=raw.decode('utf-8').strip()
                    if line.startswith('event:'):event=line[6:].strip()
                    elif line.startswith('data:') and event=='dataset_workflow':
                        payload=json.loads(line[5:].strip())
                        report['events'].append(dict(namespace=event,payload=payload,host_monotonic_s=time.monotonic()))
                        (HERE/'sse-observation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        except OSError as error:
            report['errors'].append(type(error).__name__)
            time.sleep(.1)
finally:
    report['status']='PASS' if report['events'] else 'NO_EVENTS_OBSERVED'
    (HERE/'sse-observation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(status=report['status'],workflow_events=len(report['events']),readonly=True)))
