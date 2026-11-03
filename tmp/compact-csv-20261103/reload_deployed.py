"""Replace only idle duplicate GLD runtimes; preserve embedded broker identity."""
from pathlib import Path
import subprocess,json,sys,os,re,time,urllib.request,hashlib
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
origin='http://127.0.0.1:5174'
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
health=json.load(opener.open(origin+'/api/health',timeout=5));headers={'X-GLD-Bridge-Token':health['csrfToken']}
def get(route):return json.load(opener.open(urllib.request.Request(origin+route,headers=headers),timeout=5))
s=get('/api/dataset-workflow/state');assert not any(s[k] for k in ['connected','count','csv_path','ledger_path','cleanup_pending'])
assert all(not v.get('connected') for v in health.get('slots',{}).values())
for route in ['/api/wireless-dataset/state','/api/wireless-replay/state']:
 v=get(route);assert not v.get('connected') and not v.get('recovery_active') and v.get('state') not in ['recording','recovering','replaying','stopping','stop_pending']
broker=health['mqttBroker'];assert broker['running'] and broker['authRequired']
script="Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -in @(28708,2580) } | Select-Object ProcessId,ExecutablePath,CommandLine | ConvertTo-Json"
r=subprocess.run(['powershell','-NoProfile','-Command',script],capture_output=True,text=True,check=True,creationflags=0x08000000);processes=json.loads(r.stdout);assert len(processes)==2
for p in processes:
 assert Path(p['ExecutablePath']).resolve()==(ROOT/'apps/gld-operator/python-embed/python.exe').resolve()
 assert re.search(r'\bbridge\.py\b',p['CommandLine']) and '--port 5174' in p['CommandLine']
port=int(broker['port'])
script=f'@(Get-NetTCPConnection -OwningProcess 28708 -LocalPort {port} -State Established -ErrorAction SilentlyContinue).Count'
r=subprocess.run(['powershell','-NoProfile','-Command',script],capture_output=True,text=True,check=True,creationflags=0x08000000);assert int(r.stdout.strip())==0,'Do not interrupt MQTT clients'
# The current Hub keeps this existing private file outside its public subtree.
cfg_path=ROOT/'archive/apps/runtime/operator-hub/credentials.local.json'
cfg=json.loads(cfg_path.read_text(encoding='utf-8'));assert cfg['host']==broker['host'] and int(cfg['port'])==port
assert isinstance(cfg['username'],str) and isinstance(cfg['password'],str) and len(cfg['password'])>=16
before=hashlib.sha256(cfg_path.read_bytes()).hexdigest()
env=os.environ.copy();env.update(GLD_BENCH_MQTT_USER=cfg['username'],GLD_BENCH_MQTT_PASSWORD=cfg['password'])
subprocess.run(['powershell','-NoProfile','-Command','Stop-Process -Id 28708,2580'],check=True,capture_output=True,creationflags=0x08000000)
args=[str(ROOT/'apps/gld-operator/python-embed/python.exe'),'-u',str(ROOT/'apps/gld-operator/bridge.py'),'--host','127.0.0.1','--port','5174','--no-open','--mqtt-broker-host',broker['host'],'--mqtt-broker-port',str(port)]
with (HERE/'deployed.stdout.log').open('wb') as stdout,(HERE/'deployed.stderr.log').open('wb') as stderr:
 child=subprocess.Popen(args,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,creationflags=0x08000000)
assert before==hashlib.sha256(cfg_path.read_bytes()).hexdigest()
report=dict(new_pid=child.pid,replaced_idle_pids=[28708,2580],mqtt_connections_before=0,broker_host_port_and_auth_preserved=True,credential_file_unchanged=True,other_processes_touched=False)
(HERE/'deployment.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
