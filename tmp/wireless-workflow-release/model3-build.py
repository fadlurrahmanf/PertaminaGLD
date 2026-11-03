"""Authorized Model3 compile-only receipt; never emits private config/header."""
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FW = ROOT / 'firmware'
ENV = 'gld_model_3_dataset_workflow_wifi'
BUILD = FW / '.pio/build' / ENV
ARTIFACT = FW / '.pio/artifacts/gld-dataset-workflow-wifi-20261102' / ENV
RECEIPT = HERE / 'model3-build-receipt.json'
LOG = HERE / 'model3-compile.log'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def stamp():
    now = dt.datetime.now(dt.timezone.utc)
    return now.isoformat(), now.astimezone(dt.timezone(dt.timedelta(hours=7))).isoformat()

def dump(data):
    RECEIPT.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')

def main():
    if RECEIPT.exists() or ARTIFACT.exists():
        raise RuntimeError('Refuse overwrite of existing Model3 workflow attempt/artifact')
    sources = ['firmware/platformio.ini', 'firmware/tools/prepare_dataset_workflow_wifi.py',
        'firmware/gld/src/GldDatasetWorkflowWifi.cpp', 'firmware/gld/include/GldDatasetWorkflowWifi.h',
        'firmware/gld/include/GldDatasetWorkflowBuffer.h', 'firmware/gld/src/GldUnifiedMain.cpp',
        'firmware/gld/include/Gld1FirmwareVersion.h']
    sources += [p.relative_to(ROOT).as_posix() for p in sorted((FW / 'gld/models/model_3').glob('*')) if p.is_file()]
    hashes = {name: sha(ROOT / name) for name in sources}
    start, local = stamp()
    command = [str(Path.home() / '.platformio/penv/Scripts/python.exe'), '-m', 'platformio',
               'run', '-d', 'firmware', '-e', ENV, '-j', '1']
    receipt = dict(environment=ENV, status='building', startUtc=start, startWib=local,
        command=command, buildDirectory=str(BUILD), publicSourceSha256Before=hashes,
        hardwareAction=False, packageUpdate=False, credentialValueDisclosed=False, log=str(LOG))
    with LOG.open('wb') as stream:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        receipt['pid'] = process.pid
        dump(receipt)
        print(json.dumps(dict(status='building', pid=process.pid, startUtc=start, startWib=local)), flush=True)
        code = process.wait()
    receipt['endUtc'], receipt['endWib'] = stamp()
    receipt.update(exitCode=code, status='failed' if code else 'success')
    receipt['publicSourceSha256After'] = {name: sha(ROOT / name) for name in sources}
    receipt['publicSourceUnchanged'] = hashes == receipt['publicSourceSha256After']
    log = LOG.read_text(encoding='utf-8', errors='replace')
    receipt['warnings'] = [line for line in log.splitlines() if 'warning:' in line.lower()]
    receipt['warningCount'] = len(receipt['warnings'])
    receipt['productionPackageHookObserved'] = 'Operator Hub package refreshed:' in log
    dump(receipt)
    if code:
        print(json.dumps(dict(status='failed', exitCode=code, log=str(LOG))), flush=True)
        return code
    if not receipt['publicSourceUnchanged'] or receipt['productionPackageHookObserved'] or '[SUCCESS]' not in log:
        raise RuntimeError('Source or dedicated-build completion boundary failed')
    match = re.search(r'\[SUCCESS\] Took ([\d.]+) seconds', log)
    receipt['pioElapsedSeconds'] = float(match[1]) if match else None
    for key in ('RAM', 'Flash'):
        match = re.search(key + r':\s+\[[^\]]+\]\s+([\d.]+)% \(used (\d+) bytes from (\d+) bytes\)', log)
        if not match:
            raise RuntimeError('Memory report unavailable')
        receipt[key.lower()] = dict(percent=float(match[1]), usedBytes=int(match[2]), capacityBytes=int(match[3]))
    binary = BUILD / 'firmware.bin'
    if dt.datetime.fromtimestamp(binary.stat().st_mtime, dt.timezone.utc) < dt.datetime.fromisoformat(start):
        raise RuntimeError('Binary predates compile')
    spec = importlib.util.spec_from_file_location('workflow_model3_readonly_helpers', FW / 'tools/operator_package_post.py')
    post = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(post)
    ARTIFACT.mkdir(parents=True)
    files = []
    for name, offset in [('bootloader.bin', 0), ('partitions.bin', 0x8000), ('boot_app0.bin', 0xe000), ('firmware.bin', 0x10000)]:
        source = post._required_file(FW, BUILD, name)
        shutil.copyfile(source, ARTIFACT / name)
        if sha(source) != sha(ARTIFACT / name):
            raise RuntimeError('Copied artifact mismatch')
        files.append(dict(path=name, offset=f'0x{offset:08X}', size=source.stat().st_size, sha256=sha(source)))
    receipt.update(artifactDirectory=str(ARTIFACT), artifacts=files,
        firmwareSha256=sha(binary), firmwareSize=binary.stat().st_size,
        flashSetSha256=post._flash_set_sha256(files))
    (ARTIFACT / 'artifact-hashes.json').write_text(json.dumps(dict(environment=ENV, flashFiles=files,
        flashSetSha256=receipt['flashSetSha256']), indent=2), encoding='utf-8')
    dump(receipt)
    print(json.dumps({key: receipt[key] for key in ('status','firmwareSha256','firmwareSize','ram','flash','warningCount','pioElapsedSeconds')}), flush=True)
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps(dict(status='BLOCKED', errorClass=type(error).__name__,
            detail=str(error) if isinstance(error, RuntimeError) else 'Inspect private build receipt/log locally')), flush=True)
        raise SystemExit(1)
