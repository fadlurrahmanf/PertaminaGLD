"""Reconcile the already-owned notice QA session, never start a new one."""
from pathlib import Path
import sys,subprocess,uuid,json,time,urllib.request
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path[:0]=[str(HERE),str(ROOT/'apps/gld-operator')]
from workflow_platform import WindowsWorkflowPlatform
from network_guard import restore
done=HERE/('close-'+uuid.uuid4().hex+'.done')
subprocess.Popen([sys.executable,str(HERE/'network_guard.py'),done.name,'120'],creationflags=0x08000000)
o='http://127.0.0.1:5174';token='';report={}
def call(route,data=None):
 r=urllib.request.Request(o+route,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json','Origin':o,'X-GLD-Bridge-Token':token})
 with urllib.request.urlopen(r,timeout=20) as f:return json.load(f)
try:
 token=call('/api/health')['csrfToken'];initial=call('/api/dataset-workflow/state');report['original_csv']=initial['csv_path'];report['original_sid']=initial['session_id']
 report['association']=WindowsWorkflowPlatform().join('GLD-DATASET-1002')
 end=time.monotonic()+45
 while time.monotonic()<end:
  s=call('/api/dataset-workflow/state')
  if s['verification']['verified'] or s['connected'] and s['state'] in ('recording','paused'):break
  time.sleep(.3)
 if not s['verification']['verified']:call('/api/dataset-workflow/stop',{})
 end=time.monotonic()+45
 while time.monotonic()<end:
  s=call('/api/dataset-workflow/state')
  if s['verification']['verified'] and not s['cleanup_pending']:break
  time.sleep(.3)
 report['closed']={k:s[k] for k in ['state','connected','count','csv_path','verification','replayed_count','gap_count','duplicate_count','error']}
 assert s['verification']['verified'] and not s['cleanup_pending'],'Owned session not yet verified'
 assert s['csv_path']==initial['csv_path'],'Wrong owned recording'
 reset=call('/api/dataset-workflow/reset',{});assert not reset['connected'] and not reset['csv_path'];report['reset']=True
except Exception as exc:report['error']=str(exc)[:500]
finally:
 report['network']=restore();done.write_text('done',encoding='utf-8');(HERE/'notice-session-reconciled.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
