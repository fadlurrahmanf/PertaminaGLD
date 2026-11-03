"""One explicitly authorized model compile; run one copy per independent agent."""
from pathlib import Path
import sys,os,json,subprocess,hashlib,datetime as dt,shutil,re
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];FW=ROOT/'firmware'
model=int(sys.argv[1]);assert model in (1,2,3)
env=f'gld_model_{model}_dataset_workflow_wifi'
freeze=json.loads((HERE/'source-freeze-rev4.json').read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def hashes():return {name:sha(ROOT/name) for name in freeze['sourceHashes']}
before=hashes();assert before==freeze['sourceHashes'],'Frozen source differs'
buildroot=FW/('.pio/build' if model==3 else f'.pio/workflow-build-model{model}')
libroot=FW/('.pio/libdeps' if model==3 else f'.pio/workflow-libdeps-model{model}')
build=buildroot/env
artifact=FW/'.pio/artifacts/gld-dataset-workflow-wifi-20261103-inference'/env
receipt=HERE/f'model{model}-build-receipt.json';log=HERE/f'model{model}-compile.log'
assert not receipt.exists() and not artifact.exists(),'Do not overwrite a recorded attempt'
now=lambda:dt.datetime.now(dt.timezone.utc).isoformat()
command=[str(Path.home()/'.platformio/penv/Scripts/python.exe'),'-m','platformio','run','-d','firmware','-e',env,'-j','1']
config=os.environ.copy();config.update(PLATFORMIO_BUILD_DIR=str(buildroot),PLATFORMIO_LIBDEPS_DIR=str(libroot))
data=dict(environment=env,status='building',startUtc=now(),command=command,buildDirectory=str(build),libdepsDirectory=str(libroot),artifactDirectory=str(artifact),sourceHashesBefore=before,hardwareAction=False,log=str(log))
def save():receipt.write_text(json.dumps(data,indent=2),encoding='utf-8')
with log.open('wb') as output:
 p=subprocess.Popen(command,cwd=ROOT,env=config,stdout=output,stderr=subprocess.STDOUT,creationflags=0x08000000)
 data['pid']=p.pid;save();print(json.dumps({'model':model,'pid':p.pid,'startUtc':data['startUtc']}),flush=True)
 code=p.wait()
data.update(endUtc=now(),exitCode=code,sourceHashesAfter=hashes());text=log.read_text(encoding='utf-8',errors='replace')
data['status']='success' if code==0 and data['sourceHashesAfter']==before and '[SUCCESS]' in text else 'failed'
data['warnings']=[s for s in text.splitlines() if 'warning:' in s.lower()]
data['errors']=[s for s in text.splitlines() if 'error:' in s.lower()][:10]
data['memorySummary']=[s for s in text.splitlines() if re.match(r'\s*(RAM|Flash):',s)]
save()
if data['status']!='success':print(json.dumps({'model':model,'status':data['status'],'exitCode':code}));raise SystemExit(1)
assert 'Operator Hub package refreshed:' not in text
artifact.mkdir(parents=True)
files=[]
for name in ('bootloader.bin','partitions.bin','boot_app0.bin','firmware.bin'):
 source=build/name
 if name=='boot_app0.bin' and not source.is_file():source=Path.home()/'.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin'
 shutil.copy2(source,artifact/name);assert sha(source)==sha(artifact/name)
 files.append(dict(name=name,path=str(artifact/name),buildPath=str(source),size=source.stat().st_size,sha256=sha(source)))
data.update(files=files,firmwareSha256=sha(artifact/'firmware.bin'));save()
print(json.dumps({'model':model,'status':data['status'],'firmwareSha256':data['firmwareSha256'],'warnings':len(data['warnings']),'memory':data['memorySummary']}),flush=True)
