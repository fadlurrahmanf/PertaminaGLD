"""Verify Model3 source, package and optional HTTP delivery; no COM/flash."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import runpy
import sys
import threading
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer

MAIN = Path('D:/Github/PertaminaGLD')
RELEASE = Path('D:/Github/PertaminaGLD-GLD1-69a493c')
ZIP = Path('C:/Users/MSI/Downloads/BOARD GLD 3.zip')
ENV = 'gld_model_3'
PROFILE = 'cnn-dualbranch-board-3-2class-v1'
BASE = '69a493c32d2500134a21e029820cd4addea1794a'
sha = lambda b: hashlib.sha256(b).hexdigest()

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

mapping = {
    'cnn_gas_datasheet_model_data.h': 'cnn_gas_datasheet_2class_model_data.h',
    'cnn_gas_datasheet_normalize_params.h': 'cnn_gas_datasheet_2class_normalize_params.h',
    'cnn_gas_sensitivity_table.h': 'cnn_gas_sensitivity_table_2class.h',
}
with zipfile.ZipFile(ZIP) as archive:
    blob = archive.read('BOARD GLD 3/cnn_gas_datasheet_2class_int8.tflite')
    for root in (MAIN, RELEASE):
        model_dir = root/'firmware/gld/models/model_3'
        for dst, src in mapping.items():
            assert (model_dir/dst).read_bytes() == archive.read('BOARD GLD 3/'+src), dst
        metadata = json.loads((model_dir/'model.json').read_text())
        assert metadata['sourceArchiveSha256'] == sha(ZIP.read_bytes())
        assert metadata['modelSha256'] == sha(blob)
        assert metadata['profileId'] == PROFILE
        assert metadata['classes'] == ['Clean_Air', 'LPG']
        array = re.search(r'g_cnn_gas_datasheet_2class_model\[\]\s*=\s*\{(.*?)\};',
                          (model_dir/'cnn_gas_datasheet_model_data.h').read_text(), re.S)
        assert bytes(int(h,16) for h in re.findall(r'0x([0-9a-fA-F]{2})',array[1])) == blob
        contract = (model_dir/'ModelMetadata.h').read_text()
        assert 'PRODUCTION_APPROVED = true' in contract
        assert 'EXPECTED_OUTPUT_ELEMENTS = 2' in contract
        assert 'CLASS_MAP[EXPECTED_OUTPUT_ELEMENTS] = {0, 1}' in contract
        assert contract.count('"'+PROFILE+'"') == 2
print('PASS source ZIP, 3 headers, actual model blob, 2-class contract and approved gate in both workspaces')
scaler = runpy.run_path(str(MAIN/'firmware/tools/validate_c1_scaler_order.py'))
scaler['validate_slot']('model_3',scaler['physical_order']())
hook = runpy.run_path(str(RELEASE/'firmware/tools/operator_package_post.py'))
child = load_module('model3_child',MAIN/'apps/gld-operator/bridge.py')
hub = load_module('model3_hub',MAIN/'apps/operator-hub/bridge.py')

def validate(folder):
    raw = (folder/'manifest.json').read_bytes()
    manifest = json.loads(raw)
    assert sha(raw) == (folder/'manifest.sha256').read_text().split()[0]
    assert manifest['environment'] == ENV and manifest['firmwareVersion'] == '0.8.38'
    assert manifest['source']['gitCommit'] == BASE
    assert manifest['source']['firmwareTreeSnapshotSha256'] == hook['_firmware_tree_snapshot_sha256'](RELEASE/'firmware')
    files = {item['path']:base64.b64encode((folder/item['path']).read_bytes()).decode()
             for item in manifest['flashFiles']}
    accepted, verified = child.validate_firmware_package(manifest,files,ENV,'1001')
    assert len(verified) == 4
    assert child.verified_nvs_region(verified) == (0x9000,0x5000)
    assert child.requires_gld1_nvs_reset_before_boot(accepted)
    assert hub.requires_gld1_nvs_reset_before_boot(accepted)
    firmware = (folder/'firmware.bin').read_bytes()
    assert firmware == (RELEASE/'firmware/.pio/build'/ENV/'firmware.bin').read_bytes()
    assert blob in firmware and PROFILE.encode() in firmware
    for marker in (b'0.8.38',b'GLD1_BASE_COMMIT=69a493c',b'active_low_gpio41_uln2003_pullup'):
        assert marker in firmware, marker
    for marker in (b'NULLING_STABILITY stage=',b'NULLING_WARMUP'):
        assert marker not in firmware, marker
    provenance = json.loads((folder/'model-provenance.json').read_text())
    assert provenance['environment'] == ENV and provenance['slot'] == 'model_3'
    assert provenance['profileId'] == PROFILE and provenance['size'] == len(blob)
    assert provenance['sha256'] == sha(blob) and provenance['firmwareSha256'] == sha(firmware)
    assert provenance['sourceArchiveSha256'] == sha(ZIP.read_bytes())
    assert provenance['classes'] == ['Clean_Air','LPG']
    model_dir = RELEASE/'firmware/gld/models/model_3'
    assert provenance['normalizeParamsSha256'] == sha((model_dir/'cnn_gas_datasheet_normalize_params.h').read_bytes())
    assert provenance['sensitivityTableSha256'] == sha((model_dir/'cnn_gas_sensitivity_table.h').read_bytes())
    print(json.dumps({'env':ENV,'version':manifest['firmwareVersion'],'size':len(firmware),
                     'sha256':sha(firmware),'result':'PASS actual validator, all hashes, embedded model, reset guard and build equality'}))
    return manifest

relative = Path('apps/operator-hub/firmware-packages')/ENV/'latest'
validate(RELEASE/relative)
if '--published' in sys.argv:
    validate(MAIN/relative)
    catalog = hub.firmware_package_options()['gld']
    assert catalog['environments']['model_3'] == ENV
    assert catalog['packages'][ENV]['available'] is True
    assert catalog['packages'][ENV]['requiresNvsResetBeforeBoot'] is True
    assert next(m for m in catalog['models'] if m['value']=='model_3')['label'] == 'Model 3 - Board 3'
    servers=[]
    try:
        for handler in (child.Handler,hub.Handler):
            server=ThreadingHTTPServer(('127.0.0.1',0),handler)
            servers.append(server)
            threading.Thread(target=server.serve_forever,daemon=True).start()
        child_port,hub_port=(s.server_address[1] for s in servers)
        child._register_allowed_origins('127.0.0.1',child_port)
        hub.CHILD_APPS['gld']['port']=child_port
        package=hub.child_request('127.0.0.1','gld','GET','/api/firmware/package?env='+ENV)
        assert package['manifest']==json.loads((MAIN/relative/'manifest.json').read_text())
        for item in package['manifest']['flashFiles']:
            assert base64.b64decode(package['packageFiles'][item['path']],validate=True)==(MAIN/relative/item['path']).read_bytes()
        for port,url,local in (
            (child_port,'/','apps/gld-operator/index.html'),
            (child_port,'/js/firmware.js','apps/gld-operator/js/firmware.js'),
            (hub_port,'/js/hub.js','apps/operator-hub/public/js/hub.js'),
        ):
            with urllib.request.urlopen(f'http://127.0.0.1:{port}{url}',timeout=10) as response:
                assert response.read()==(MAIN/local).read_bytes()
        assert child.serial_bridges == {}
        print('PASS published Model3 catalog, actual HTTP handlers/proxy, exact served package and UI assets; no COM')
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
