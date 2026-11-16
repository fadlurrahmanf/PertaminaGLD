"""Package the separately built, unapproved Board 1 backup model; never flash."""
import base64
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
FW = ROOT / 'firmware'
ENV = 'gld_model_1_h2_dataset_workflow_wifi'
BUILD = FW / '.pio/build' / ENV
DEST = ROOT / 'apps/operator-hub/firmware-packages' / ENV / 'candidate-test'

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def digest(data):
    return hashlib.sha256(data).hexdigest()

def main():
    if DEST.exists():
        raise RuntimeError('Refusing to overwrite an existing package')
    post = load(FW / 'tools/operator_package_post.py', 'h2_package_post')
    sys.path.insert(0, str(ROOT / 'apps/gld-operator'))
    child = load(ROOT / 'apps/gld-operator/bridge.py', 'h2_child_bridge')
    hub = load(ROOT / 'apps/operator-hub/bridge.py', 'h2_hub_bridge')
    preflight = load(ROOT / 'apps/operator-hub/preflight.py', 'h2_preflight')
    model_dir = FW / 'gld/models/model_1_h2'
    metadata = json.loads((model_dir / 'model.json').read_text(encoding='utf-8'))
    header = (model_dir / 'cnn_gas_datasheet_model_data.h').read_text(encoding='utf-8')
    match = re.search(r'g_cnn_gas_datasheet_model\[\]\s*=\s*\{(.*?)\};', header, re.S)
    if not match:
        raise RuntimeError('Model array missing')
    blob = bytes(int(v, 16) for v in re.findall(r'0x([0-9a-fA-F]{2})', match.group(1)))
    binary = (BUILD / 'firmware.bin').read_bytes()
    if digest(blob) != metadata['modelSha256'] or binary.count(blob) != 1 or metadata['profileId'].encode() not in binary:
        raise RuntimeError('Compiled firmware does not contain the expected model and profile')
    if any(marker not in binary for marker in (b'gld-dataset-wifi/3', b'PAUSE_DATASET', b'ACK_SAMPLES',
                                                b'testInferenceEnabled', b'test_inference_enabled')):
        raise RuntimeError('Workflow or test-mode markers missing')
    if 'PRODUCTION_APPROVED = false' not in (model_dir / 'ModelMetadata.h').read_text(encoding='utf-8'):
        raise RuntimeError('Test package must not claim production approval')
    config = json.loads((FW / '.pio/gld-dataset-workflow-wifi' / ENV / 'credentials.local.json').read_text())
    original = json.loads((FW / '.pio/gld-dataset-workflow-wifi/gld_model_1_dataset_workflow_wifi/credentials.local.json').read_text())
    original_binary = (ROOT / 'apps/operator-hub/firmware-packages/gld_model_1_dataset_workflow_wifi/latest/firmware.bin').read_bytes()
    if (config['password'] != original['password'] or config['password'].encode() not in binary or
            config['password'].encode() not in original_binary):
        raise RuntimeError('Workflow credentials do not match the existing Model 1 package')
    files = []
    encoded = {}
    content = {}
    for name, offset in post.FLASH_FILES:
        source = post._required_file(FW, BUILD, name)
        data = source.read_bytes()
        content[name] = data
        encoded[name] = base64.b64encode(data).decode('ascii')
        files.append(dict(path=name, offset=f'0x{offset:08X}', size=len(data), sha256=digest(data)))
    versions = post._version_constants(FW)
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    manifest = dict(schemaVersion=2, packageType='pertamina-gld-prebuilt-firmware', deviceId='ANY',
        boardProfile='WROOM-1U-N16R8 / Model 1 H2 LPG / Dataset Wi-Fi Workflow Protocol 3',
        environment=ENV, firmwareVersion=versions['GLD1_FIRMWARE_VERSION'],
        protocolVersion=versions['PROTOCOL_VERSION'], configSchemaVersion=versions['CONFIG_SCHEMA_VERSION'],
        chip='esp32s3', baud=921600, createdAtUtc=now,
        source=dict(gitCommit=post._git_commit(ROOT), gitTreeState='build-output',
                    gitTreeStateScope='firmware/', firmwareTreeSnapshotSha256=post._firmware_tree_snapshot_sha256(FW),
                    platformioCoreVersion='6.1.19', platformioIniSha256=post._sha256(FW / 'platformio.ini'),
                    buildCommand=f'pio run -e {ENV}', packagedAtUtc=now),
        flashSetSha256=post._flash_set_sha256(files), flashFiles=files,
        capabilities=dict(nativeSerial=True, datasetWifi=True))
    checked, verified = child.validate_firmware_package(manifest, encoded, ENV, '1001')
    if len(verified) != 4 or child.verified_nvs_region(verified) != (0x9000, 0x5000):
        raise RuntimeError('Unexpected verified package layout')
    for item, data in verified:
        start = int(item['offset'], 0)
        if not (start + ((len(data) + 4095) & ~4095) <= 0x9000 or start >= 0xE000):
            raise RuntimeError('Flash erase range overlaps NVS')
    hub.validate_selected_package(dict(manifest=checked, packageFiles=encoded), ENV)
    DEST.mkdir(parents=True)
    for name, data in content.items():
        (DEST / name).write_bytes(data)
    manifest_path = DEST / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    (DEST / 'manifest.sha256').write_text(f'{digest(manifest_path.read_bytes())}  manifest.json\n', encoding='ascii')
    provenance = dict(environment=ENV, profileId=metadata['profileId'], classes=metadata['classes'],
                      sha256=digest(blob), sourceArchiveSha256=metadata['sourceArchiveSha256'],
                      firmwareSha256=digest(binary), productionApproved=False, testInferenceEnabled=True)
    (DEST / 'model-provenance.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
    preflight._verify_manifest(manifest_path, ENV)
    print('PASS: isolated package, source model, class profile, credentials, validators and NVS layout')

if __name__ == '__main__':
    main()
