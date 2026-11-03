"""Authorized private Model3 credential revision; compile/package only."""
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
FW = ROOT / 'firmware'
ENV = 'gld_model_3_dataset_replay_wifi'
HERE = Path(__file__).resolve().parent
RECEIPT = HERE / 'model3-build-receipt.json'
LOG = HERE / 'model3-compile.log'
BUILD = FW / '.pio/build-wireless-stage2-model3' / ENV
DEST = FW / '.pio/artifacts/gld-dataset-replay-wifi-20261102-operator-password' / ENV

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def dump(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')

def stamp():
    now = dt.datetime.now(dt.timezone.utc)
    return now.isoformat(), now.astimezone(dt.timezone(dt.timedelta(hours=7))).isoformat()

def main():
    cred = FW / '.pio/gld-dataset-replay-wifi' / ENV / 'credentials.local.json'
    backup = cred.parent / 'revisions/20261102-operator-password/credentials.local.json'
    if backup.exists() or RECEIPT.exists() or DEST.exists():
        raise RuntimeError('Refuse overwrite of existing Model3 revision')
    source = json.loads((FW / '.pio/gld-dataset-replay-wifi/gld_model_1_dataset_replay_wifi/credentials.local.json').read_text(encoding='utf-8'))
    password = source['password']
    if not isinstance(password, str) or not 8 <= len(password) <= 63:
        raise RuntimeError('Invalid authorized credential configuration')
    current = json.loads(cred.read_text(encoding='utf-8'))
    if current['environment'] != ENV or current['protocol'] != 'gld-dataset-wifi/2':
        raise RuntimeError('Unexpected private Model3 configuration')
    backup.parent.mkdir(parents=True, exist_ok=True)
    with backup.open('xb') as stream:
        stream.write(cred.read_bytes())
    current['password'] = password
    dump(cred, current)
    template = json.loads((HERE / 'model1-build-receipt.json').read_text(encoding='utf-8-sig'))
    paths = [name.replace('/model_1/', '/model_3/') for name in template['sourceSha256Before']]
    paths += ['firmware/gld/include/Gld1FirmwareVersion.h', 'firmware/gld/models/model_3/model.json']
    sources = {name: sha(ROOT / name) for name in dict.fromkeys(paths)}
    spec = importlib.util.spec_from_file_location('model3_readonly_post', FW / 'tools/operator_package_post.py')
    post = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(post)
    started, wib = stamp()
    receipt = dict(environment=ENV, revision='20261102-operator-password', status='building',
        startUtc=started, startWib=wib, sourceSha256Before=sources,
        sourceFingerprintBefore=post._firmware_tree_snapshot_sha256(FW),
        buildDirectory=str(BUILD), credentialFile=str(cred), credentialBackup=str(backup),
        credentialValueDisclosed=False, hardwareAction='none; compile only', log=str(LOG))
    env = os.environ.copy()
    env['PLATFORMIO_BUILD_DIR'] = str(FW / '.pio/build-wireless-stage2-model3')
    env['PLATFORMIO_LIBDEPS_DIR'] = str(FW / '.pio/libdeps-wireless-stage2-model3')
    command = [str(Path.home() / '.platformio/penv/Scripts/python.exe'), '-m', 'platformio', 'run', '-e', ENV]
    with LOG.open('wb') as stream:
        process = subprocess.Popen(command, cwd=FW, env=env, stdout=stream, stderr=subprocess.STDOUT)
        receipt['pid'] = process.pid
        dump(RECEIPT, receipt)
        print(json.dumps(dict(status='building', pid=process.pid, startUtc=started, startWib=wib)), flush=True)
        code = process.wait()
    receipt['endUtc'], receipt['endWib'] = stamp()
    receipt['exitCode'] = code
    receipt['status'] = 'failed' if code else 'success'
    dump(RECEIPT, receipt)
    if code:
        print(json.dumps(dict(status='failed', exitCode=code, log=str(LOG))), flush=True)
        return code
    if any(sha(ROOT / name) != value for name, value in sources.items()):
        raise RuntimeError('Public source changed during Model3 compile')
    log = LOG.read_text(encoding='utf-8', errors='replace')
    if '[SUCCESS]' not in log or 'Operator Hub package refreshed:' in log:
        raise RuntimeError('Unexpected build completion or package hook')
    binary = (BUILD / 'firmware.bin').read_bytes()
    previous = json.loads(backup.read_text(encoding='utf-8'))['password']
    if password.encode() not in binary or previous.encode() in binary:
        raise RuntimeError('Private embedded credential verification failed')
    header = BUILD / 'private-dataset-replay-wifi/GldDatasetReplayWifiSecrets.h'
    if password.encode() not in header.read_bytes():
        raise RuntimeError('Private header verification failed')
    if password.encode() in LOG.read_bytes():
        raise RuntimeError('Credential disclosure detected in private log')
    DEST.mkdir(parents=True)
    artifacts = []
    for name, offset in [('bootloader.bin', 0), ('partitions.bin', 0x8000), ('boot_app0.bin', 0xe000), ('firmware.bin', 0x10000)]:
        origin = post._required_file(FW, BUILD, name)
        shutil.copyfile(origin, DEST / name)
        artifacts.append(dict(path=name, offset=f'0x{offset:08X}', size=(DEST / name).stat().st_size, sha256=sha(DEST / name)))
    dump(DEST / 'artifact-hashes.json', dict(environment=ENV, flashFiles=artifacts, flashSetSha256=post._flash_set_sha256(artifacts)))
    receipt.update(sha256=sha(BUILD / 'firmware.bin'), size=len(binary), artifactDirectory=str(DEST),
        artifacts=artifacts, sourceUnchangedDuringCompile=True,
        privateHeaderMatchesConfiguredCredential=True, binaryContainsConfiguredCredential=True,
        binaryExcludesPreviousCredential=True)
    receipt['usage'] = [line.strip() for line in log.splitlines() if re.match(r'^(RAM|Flash):', line)]
    receipt['warningsSummary'] = dict(compilerWarningCount=sum('warning:' in line.lower() for line in log.splitlines()))
    dump(RECEIPT, receipt)
    print(json.dumps(dict(status='success', sha256=receipt['sha256'], size=len(binary), usage=receipt['usage'])), flush=True)
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps(dict(status='BLOCKED', errorClass=type(exc).__name__, detail=str(exc) if isinstance(exc, RuntimeError) else 'Private build helper failed; inspect locally')), flush=True)
        raise SystemExit(1)
