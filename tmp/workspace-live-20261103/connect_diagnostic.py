from pathlib import Path
import sys,subprocess,uuid,json,urllib.request,urllib.error,time
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from network_guard import restore
done=HERE/('diagnostic-'+uuid.uuid4().hex+'.done');subprocess.Popen([sys.executable,str(HERE/'network_guard.py'),done.name,'65'],creationflags=0x08000000)
o='http://127.0.0.1:5174';token='';report={}
def call(action,payload=None):
 route='/api/health' if action=='health' else '/api/dataset-workflow/'+action
 req=urllib.request.Request(o+route,data=None if payload is None else json.dumps(payload).encode(),headers={'Origin':o,'Content-Type':'application/json','X-GLD-Bridge-Token':token})
 try:
  with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
 except urllib.error.HTTPError as e:return {'http_error':e.code,**json.load(e)}
def summary(s):return {k:s.get(k) for k in ['state','connected','ready','prediction_available','device_id','count','error','http_error']}
try:
 token=call('health')['csrfToken'];s=call('state');assert not s['csv_path'] and not s['count'];call('reset',{})
 report['scan']=call('scan',{})['devices'];call('select',{'device_id':'1002'});report['connect_result']=summary(call('connect',{'device_id':'1002'}));time.sleep(3);report['after_three_seconds']=summary(call('state'))
finally:
 s=call('state')
 if s.get('connected'):report['disconnect']=summary(call('disconnect',{}))
 if not s.get('csv_path'):call('reset',{})
 report['network']=restore();done.write_text('done',encoding='utf-8');(HERE/'connect-diagnostic.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
