"""User explicitly approved Model1 COM7 upload; Reset NVS is strictly false."""
from pathlib import Path
import urllib.request,json,hashlib,time,sys
HERE=Path(__file__).resolve().parent
ORIGIN='http://127.0.0.1:5174';token=''
def request(route,data=None,timeout=15):
    req=urllib.request.Request(ORIGIN+route,data=None if data is None else json.dumps(data).encode(),
        headers={'Origin':ORIGIN,'Content-Type':'application/json','X-GLD-Bridge-Token':token})
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)
token=request('/api/health')['csrfToken']
state=request('/api/dataset-workflow/state')
assert not state['connected'] and not state['cleanup_pending'] and not state['count']
package=request('/api/firmware/package?env=gld_model_1_dataset_workflow_wifi')
manifest=package['manifest'];assert manifest['environment']=='gld_model_1_dataset_workflow_wifi'
revision4='--rev4' in sys.argv
expected=json.loads((HERE/'model1-build-receipt.json').read_text(encoding='utf-8'))['firmwareSha256'] if revision4 else '74e822e4cff5f65918281e2f926b7be96f454b879461da1cb72023a18ff032fe'
assert next(x['sha256'] for x in manifest['flashFiles'] if x['path']=='firmware.bin')==expected
payload=dict(env=manifest['environment'],port='COM7',targetDeviceId='1002',resetNvs=False,
    manifest=manifest,packageFiles=package['packageFiles'],slot=1)
result=request('/api/firmware/upload',payload,135)
assert result.get('nvsReset') is False
result['expectedFirmwareSha256']=expected
(HERE/('upload-model1-inference-result.json' if revision4 else 'upload-model1-result.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
