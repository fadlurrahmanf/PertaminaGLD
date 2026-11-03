"""Prepare verified final packages; --install swaps only those three directories."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HUB = (ROOT/'apps/operator-hub/firmware-packages').resolve()
ARTIFACT = ROOT/'firmware/.pio/artifacts/gld-dataset-workflow-wifi-20261103-native-features'
NAMES = ('bootloader.bin', 'partitions.bin', 'boot_app0.bin', 'firmware.bin',
         'manifest.json', 'manifest.sha256', 'model-provenance.json')
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
install = '--install' in sys.argv
planned = []
for model in (1, 2, 3):
    env = f'gld_model_{model}_dataset_workflow_wifi'
    parent = (HUB/env).resolve()
    assert parent.parent == HUB
    source = (ARTIFACT/env).resolve()
    validation = json.loads((source/'offline-package-validation.json').read_text())
    assert validation['status'] == 'PASS' and validation['nativeSerial'] is True
    manifest = json.loads((source/'manifest.json').read_text())
    assert manifest['environment'] == env
    assert manifest['capabilities'] == {'nativeSerial': True, 'datasetWifi': True}
    assert sha(source/'manifest.json') == validation['manifestSha256']
    for entry in manifest['flashFiles']:
        assert sha(source/entry['path']) == entry['sha256']
    stage = (parent/'.latest-native-features-20261103').resolve()
    latest = (parent/'latest').resolve()
    backup = (parent/'previous-20261103-before-native-features').resolve()
    assert stage.parent == latest.parent == backup.parent == parent
    if stage.exists():
        assert {p.name for p in stage.iterdir()} == set(NAMES)
        assert all(sha(stage/name) == sha(source/name) for name in NAMES)
    else:
        stage.mkdir()
        for name in NAMES:
            shutil.copy2(source/name, stage/name)
    assert all(sha(stage/name) == sha(source/name) for name in NAMES)
    planned.append((env, source, stage, latest, backup))

result = []
for env, source, stage, latest, backup in planned:
    if install:
        assert latest.is_dir() and not backup.exists(), 'Refuse ambiguous repeated installation'
        latest.rename(backup)
        try:
            stage.rename(latest)
        except BaseException:
            backup.rename(latest)
            raise
        assert all(sha(latest/name) == sha(source/name) for name in NAMES)
    result.append({'environment': env, 'installed': install,
                   'stagedDirectory': str(stage), 'hubDirectory': str(latest),
                   'archiveDirectory': str(backup),
                   'firmwareSha256': sha(source/'firmware.bin')})
(HERE/('installed-packages.json' if install else 'staged-packages.json')).write_text(
    json.dumps(result, indent=2))
print(json.dumps({'status': 'PASS', 'installed': install, 'packages': len(result)}))
