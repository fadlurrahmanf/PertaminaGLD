"""Verify GPIO17 GLD1 packages without opening any serial port."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

MAIN = Path('D:/Github/PertaminaGLD')
RELEASE = Path('D:/Github/PertaminaGLD-GLD1-69a493c')
ROOT = MAIN if '--published' in sys.argv else RELEASE
sha = lambda data: hashlib.sha256(data).hexdigest()

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result

child = module('gpio17_child', MAIN/'apps/gld-operator/bridge.py')
hub = module('gpio17_hub', MAIN/'apps/operator-hub/bridge.py')
for env, slot in [('gld', 'model_1'), ('gld_model_1', 'model_1'), ('gld_model_3', 'model_3')]:
    folder = ROOT/'apps/operator-hub/firmware-packages'/env/'latest'
    raw = (folder/'manifest.json').read_bytes()
    manifest = json.loads(raw)
    assert manifest['firmwareVersion'] == '0.8.38'
    assert manifest['source']['gitCommit'] == '69a493c32d2500134a21e029820cd4addea1794a'
    assert sha(raw) == (folder/'manifest.sha256').read_text().split()[0]
    files = {item['path']: base64.b64encode((folder/item['path']).read_bytes()).decode('ascii')
             for item in manifest['flashFiles']}
    accepted, verified = child.validate_firmware_package(manifest, files, env, '1001')
    hub.validate_selected_package({'manifest': manifest, 'packageFiles': files}, env)
    assert hub.requires_gld1_nvs_reset_before_boot(manifest)
    firmware = (folder/'firmware.bin').read_bytes()
    assert firmware == (RELEASE/'firmware/.pio/build'/env/'firmware.bin').read_bytes()
    for marker in (b'active_high_gpio17_steady', b'gpio17CommandLevel',
                   b'GLD1_BASE_COMMIT=69a493c alarm=GPIO17_ACTIVE_HIGH', b'warmup30s=0'):
        assert marker in firmware, marker
    for absent in (b'gpio41Command', b'j2LampExpected', b'GPIO41_ULN_PULLUP',
                   b'NULLING_WARMUP', b'NULLING_STABILITY stage=', b'GLD1_BOOT_I2C_BEGIN'):
        assert absent not in firmware, absent
    provenance = json.loads((folder/'model-provenance.json').read_text())
    previous = json.loads((MAIN/'tmp/gld1-gpio17-20260930/before/main/apps/operator-hub/firmware-packages'/env/'latest/model-provenance.json').read_text())
    assert provenance['firmwareSha256'] == sha(firmware)
    assert {k:v for k,v in provenance.items() if k != 'firmwareSha256'} == {
        k:v for k,v in previous.items() if k != 'firmwareSha256'}, 'model provenance changed'
    header = (RELEASE/'firmware/gld/models'/slot/'cnn_gas_datasheet_model_data.h').read_text()
    array = re.search(r'g_cnn_gas_datasheet_2class_model\[\]\s*=\s*\{(.*?)\};', header, re.S)
    blob = bytes(int(h, 16) for h in re.findall(r'0x([0-9a-fA-F]{2})', array[1]))
    assert blob in firmware and sha(blob) == provenance['sha256']
    assert provenance['profileId'].encode() in firmware
    print(json.dumps({'environment': env, 'size':len(firmware), 'sha256':sha(firmware),
                      'created':accepted['createdAtUtc'], 'filesVerified':len(verified),
                      'result':'PASS GPIO17, strict validators, build equality, unchanged model, NVS guard'}))
assert child.serial_bridges == {}, 'must not access COM'
