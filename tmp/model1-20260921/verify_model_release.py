"""Verify source export, real package validator, embedded model and optional live GET.

No serial operations. --repackage reruns the release hook on existing build output.
--live only reads HTTP health, static assets and prebuilt packages, never overview
(overview queries attached hardware).
"""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import runpy
import sys
import urllib.request
import zipfile

MAIN = Path('D:/Github/PertaminaGLD')
RELEASE = Path('D:/Github/PertaminaGLD-GLD1-69a493c')
ZIP = Path('C:/Users/MSI/Downloads/BOARD GLD 1.zip')
PROFILE = 'cnn-dualbranch-board-1-2class-v2'
sha = lambda blob: hashlib.sha256(blob).hexdigest()
mapping = {
    'cnn_gas_datasheet_model_data.h': 'cnn_gas_datasheet_2class_model_data.h',
    'cnn_gas_datasheet_normalize_params.h': 'cnn_gas_datasheet_2class_normalize_params.h',
    'cnn_gas_sensitivity_table.h': 'cnn_gas_sensitivity_table_2class.h',
}
with zipfile.ZipFile(ZIP) as archive:
    model_blob = archive.read('BOARD GLD 1/cnn_gas_datasheet_2class_int8.tflite')
    for root in (MAIN, RELEASE):
        model_dir = root/'firmware/gld/models/model_1'
        for dst, src in mapping.items():
            assert (model_dir/dst).read_bytes() == archive.read('BOARD GLD 1/'+src), dst
        meta = json.loads((model_dir/'model.json').read_text())
        assert meta['sourceArchiveSha256'] == sha(ZIP.read_bytes())
        assert meta['modelSha256'] == sha(model_blob)
        assert meta['profileId'] == PROFILE
        assert meta['classes'] == ['Clean_Air', 'LPG']
        array = re.search(r'g_cnn_gas_datasheet_2class_model\[\]\s*=\s*\{(.*?)\};',
                          (model_dir/'cnn_gas_datasheet_model_data.h').read_text(), re.S)
        assert bytes(int(h,16) for h in re.findall(r'0x([0-9a-fA-F]{2})', array[1])) == model_blob
print('PASS all 3 headers in both workspaces equal ZIP; embedded array equals INT8 TFLite')

hook = runpy.run_path(str(RELEASE/'firmware/tools/operator_package_post.py'))
if '--repackage' in sys.argv:
    class BuildEnvironment(dict):
        def subst(self, key):
            assert key == '$BUILD_DIR'
            return str(RELEASE/'firmware/.pio/build'/self['PIOENV'])
    for env in ('gld', 'gld_model_1'):
        hook['write_operator_package'](None, None, BuildEnvironment(PIOENV=env, PROJECT_DIR=str(RELEASE/'firmware')))

runpy.run_path(str(RELEASE/'verify_gld1_release.py'))
spec = importlib.util.spec_from_file_location('model_release_hub', MAIN/'apps/operator-hub/bridge.py')
hub = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = hub
spec.loader.exec_module(hub)

def validate(folder, env):
    manifest = json.loads((folder/'manifest.json').read_text())
    provenance = json.loads((folder/'model-provenance.json').read_text())
    firmware = (folder/'firmware.bin').read_bytes()
    assert model_blob in firmware
    assert PROFILE.encode() in firmware
    assert provenance['sha256'] == sha(model_blob)
    assert provenance['firmwareSha256'] == sha(firmware)
    assert provenance['profileId'] == PROFILE
    assert provenance['classes'] == ['Clean_Air', 'LPG']
    assert provenance['environment'] == env
    assert provenance['sourceArchiveSha256'] == sha(ZIP.read_bytes())
    model_dir = RELEASE/'firmware/gld/models/model_1'
    assert provenance['normalizeParamsSha256'] == sha((model_dir/'cnn_gas_datasheet_normalize_params.h').read_bytes())
    assert provenance['sensitivityTableSha256'] == sha((model_dir/'cnn_gas_sensitivity_table.h').read_bytes())
    assert manifest['source']['firmwareTreeSnapshotSha256'] == hook['_firmware_tree_snapshot_sha256'](RELEASE/'firmware')
    assert hub.requires_gld1_nvs_reset_before_boot(manifest)
    print('PASS embedded model/profile, audit hashes, source snapshot and unchanged reset guard:', env)
    return manifest

for env in ('gld', 'gld_model_1'):
    validate(RELEASE/'apps/operator-hub/firmware-packages'/env/'latest', env)

def test_http(child_url, hub_url):
    def get(url, headers=None):
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=10) as response:
            return response.read()
    health = json.loads(get(child_url+'/api/health'))
    assert health['features']['firmwareGld1DowngradeGuard'] is True
    headers = {'X-GLD-Bridge-Token': health['csrfToken']}
    for env in ('gld', 'gld_model_1'):
        folder = MAIN/'apps/operator-hub/firmware-packages'/env/'latest'
        expected = validate(folder, env)
        live = json.loads(get(child_url+'/api/firmware/package?env='+env, headers))
        assert live['manifest'] == expected
        for item in expected['flashFiles']:
            assert base64.b64decode(live['packageFiles'][item['path']], validate=True) == (folder/item['path']).read_bytes()
        print('PASS live Expert/Hub upload endpoint serves exact new build:', env)
    catalog = hub.firmware_package_options()['gld']
    assert catalog['environments']['model_1'] == 'gld_model_1'
    assert catalog['packages']['gld_model_1']['available'] is True
    assert catalog['packages']['gld_model_1']['requiresNvsResetBeforeBoot'] is True
    assert get(child_url+'/js/firmware.js') == (MAIN/'apps/gld-operator/js/firmware.js').read_bytes()
    assert get(hub_url+'/js/hub.js') == (MAIN/'apps/operator-hub/public/js/hub.js').read_bytes()
    print('PASS Simple Hub catalog and live Expert/Simple Hub assets; no board query performed')

if '--live' in sys.argv:
    test_http('http://127.0.0.1:5174', 'http://127.0.0.1:5173')
if '--http-smoke' in sys.argv:
    # Run the actual HTTP handlers on temporary loopback ports. Do not invoke
    # application startup (which launches broker/other bridges), connect a
    # serial port or call /simple/overview (which queries attached hardware).
    from http.server import ThreadingHTTPServer
    import threading
    spec = importlib.util.spec_from_file_location('model_release_child', MAIN/'apps/gld-operator/bridge.py')
    child = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(child)
    servers = []
    try:
        for handler in (child.Handler, hub.Handler):
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
            servers.append(server)
            threading.Thread(target=server.serve_forever, daemon=True).start()
        child_port, hub_port = (server.server_address[1] for server in servers)
        child._register_allowed_origins('127.0.0.1', child_port)
        hub.CHILD_APPS['gld']['port'] = child_port
        test_http(f'http://127.0.0.1:{child_port}', f'http://127.0.0.1:{hub_port}')
        proxied = hub.child_request('127.0.0.1', 'gld', 'GET', '/api/firmware/package?env=gld_model_1')
        assert model_blob in base64.b64decode(proxied['packageFiles']['firmware.bin'])
        assert child.serial_bridges == {}, 'test must not open or create a serial bridge'
        print('PASS Simple Hub actual proxy fetches new Model 1; no COM accessed; temporary HTTP servers stopped')
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
