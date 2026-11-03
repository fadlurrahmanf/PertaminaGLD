from pathlib import Path
import ctypes,ctypes.wintypes,datetime as dt,hashlib,json,os,re,shutil,subprocess,sys
ROOT=Path('D:/Github/PertaminaGLD');HERE=ROOT/'tmp/hotspot-full-feature-20261103';NAME='gld_model_1_dataset_workflow_wifi';receipt=HERE/'model1-build-receipt.json'
expected={'firmware/gld/src/GldUnifiedMain.cpp':'2b93d489b873d173faa008474c7d307aa83af21ed80c9dca3e129a93ebd7c0a6','firmware/gld/src/GldDatasetWorkflowWifi.cpp':'71493a20a62233a8ce7e3e3168ac1573c84039a03a8b3d2f4051606899a808c5','firmware/gld/include/GldDatasetWorkflowWifi.h':'b8222a17ffb3bf3b0d39d4b2b5271366bd2b2f1ea88a53891a4c5ff4d8213888'}
def hashes():return {f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in expected}
before=hashes();assert before==expected,'Frozen source mismatch'
env=os.environ.copy();env['PLATFORMIO_BUILD_DIR']=str(ROOT/'firmware/.pio/workflow-build-model1');env['PLATFORMIO_LIBDEPS_DIR']=str(ROOT/'firmware/.pio/workflow-libdeps-model1')
cmd=['C:/Users/MSI/.platformio/penv/Scripts/python.exe','-m','platformio','run','-d','firmware','-e',NAME,'-j','1'];log=HERE/'model1-build.log'
data={'environment':NAME,'status':'starting','command':cmd,'sourceHashesBefore':before,'buildDirectory':str(Path(env['PLATFORMIO_BUILD_DIR'])/NAME),'libdepsDirectory':env['PLATFORMIO_LIBDEPS_DIR']}
with log.open('w',encoding='utf-8') as output:
 p=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT)
 creation=ctypes.wintypes.FILETIME();exitTime=ctypes.wintypes.FILETIME();kernel=ctypes.wintypes.FILETIME();user=ctypes.wintypes.FILETIME()
 ok=ctypes.windll.kernel32.GetProcessTimes(ctypes.wintypes.HANDLE(p._handle),ctypes.byref(creation),ctypes.byref(exitTime),ctypes.byref(kernel),ctypes.byref(user));assert ok
 stamp=((creation.dwHighDateTime<<32)|creation.dwLowDateTime)/10000000-11644473600
 data.update(status='running',pid=p.pid,startUtc=dt.datetime.fromtimestamp(stamp,dt.timezone.utc).isoformat());receipt.write_text(json.dumps(data,indent=2));print(json.dumps({'status':'running','pid':p.pid,'startUtc':data['startUtc']}),flush=True)
 code=p.wait()
data.update(exitCode=code,endUtc=dt.datetime.now(dt.timezone.utc).isoformat(),sourceHashesAfter=hashes());text=log.read_text(encoding='utf-8',errors='replace');lines=text.splitlines();data['warnings']=[s for s in lines if re.search(r'\bwarning:',s,re.I)];data['errors']=[s for s in lines if re.search(r'\berror:|\*\*\*|FAILED',s,re.I)];data['memorySummary']=[s for s in lines if s.strip().startswith(('RAM:','Flash:'))]
if code==0 and data['sourceHashesAfter']==expected:
 artifact=ROOT/'firmware/.pio/artifacts/gld-dataset-workflow-wifi-20261103-native-features'/NAME;artifact.mkdir(parents=True,exist_ok=True);data['artifactDirectory']=str(artifact);data['files']=[]
 for name in ('bootloader.bin','partitions.bin','firmware.bin','boot_app0.bin'):
  source=Path(data['buildDirectory'])/name if name!='boot_app0.bin' else Path('C:/Users/MSI/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin')
  assert source.is_file(),str(source);target=artifact/name;shutil.copy2(source,target);data['files'].append({'name':name,'path':str(target),'buildPath':str(source),'size':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
 data['status']='success';data['firmwareSha256']=next(f['sha256'] for f in data['files'] if f['name']=='firmware.bin')
else:data['status']='failed'
receipt.write_text(json.dumps(data,indent=2));print(json.dumps({k:data[k] for k in ('status','exitCode','startUtc','endUtc','memorySummary','warnings','errors')}),flush=True)
sys.exit(0 if data['status']=='success' else 1)
