"""Real radio/auth/HELLO only. No acquisition, flash, serial or NVS changes."""
from pathlib import Path
import sys, subprocess, time, json, base64, uuid
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(ROOT/'apps/gld-operator'))
from workflow_platform import WindowsWorkflowPlatform
from workflow_credentials import resolve_workflow_password
from wireless_dataset import _transport_factory
from network_guard import restore
done=HERE/('probe-'+uuid.uuid4().hex+'.done')
guard=subprocess.Popen([sys.executable,str(HERE/'network_guard.py'),done.name,'45'],creationflags=0x08000000)
report={'hardware':True,'test':'real authenticated HELLO','upload':False,'reset':False,'sampling':False}
ws=None
try:
    platform=WindowsWorkflowPlatform();report['scan']=platform.scan()
    assert any(d['device_id']=='1002' for d in report['scan']),'Target GLD1002 not visible'
    password=resolve_workflow_password();report['association']=platform.join('GLD-DATASET-1002',password)
    auth=base64.b64encode(('gld:'+password).encode()).decode()
    ws=_transport_factory('ws://192.168.4.1:81/dataset',timeout=8,header=['Authorization: Basic '+auth],http_no_proxy=['*'],redirect_limit=0)
    raw=ws.recv();hello=json.loads(raw)
    # Persist only recognized public telemetry; never auth headers or credentials.
    keys=['type','protocol','device_id','boot_id','session_id','ready','reason','interval_ms','sampling','paused','nulling_profile_id','prediction_ready','model','capabilities','retention_ms','buffer_capacity','buffer_capacity_samples','retained_samples','total_samples','next_seq','oldest_seq','acked_next_seq','buffered_samples','incomplete','transition_seq']
    report['hello']={k:hello[k] for k in keys if k in hello};report['ok']=True
except Exception as exc:
    report['ok']=False;report['error_type']=type(exc).__name__;report['error']=str(exc)[:350]
finally:
    if ws:ws.close()
    report['network']=restore();done.write_text('done',encoding='utf-8')
    (HERE/'real-hello.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
