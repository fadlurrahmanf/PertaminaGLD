"""One isolated compiler, synchronized with the other two by the release gate."""
from pathlib import Path
import argparse
import ctypes
import ctypes.wintypes
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--model', type=int, choices=(1, 2, 3), required=True)
model = parser.parse_args().model
name = f'gld_model_{model}_dataset_workflow_wifi'
expected = json.loads((HERE/'source-freeze.json').read_text())
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
hashes = lambda: {path: sha(ROOT/path) for path in expected}
before = hashes()
assert before == expected, 'Public source changed before build'
build_root = (ROOT/f'firmware/.pio/workflow-build-model{model}').resolve()
build = (build_root/name).resolve()
assert build.is_relative_to((ROOT/'firmware/.pio').resolve())
# Shared workflow source changed; preserve valid dependency caches.
removed = []
env = os.environ.copy()
env['PLATFORMIO_BUILD_DIR'] = str(build_root)
env['PLATFORMIO_LIBDEPS_DIR'] = str(ROOT/f'firmware/.pio/workflow-libdeps-model{model}')
command = ['C:/Users/MSI/.platformio/penv/Scripts/python.exe', '-m', 'platformio',
           'run', '-d', 'firmware', '-e', name, '-j', '1']
receipt_path = HERE/f'model{model}-build-receipt.json'
log = HERE/f'model{model}-build.log'
receipt = dict(environment=name, status='ready', command=command,
               sourceHashesBefore=before, buildDirectory=str(build),
               libdepsDirectory=env['PLATFORMIO_LIBDEPS_DIR'], log=str(log),
               regeneratedBuildOutputs=removed, hardwareAction=False,
               readyUtc=dt.datetime.now(dt.timezone.utc).isoformat())
receipt_path.write_text(json.dumps(receipt, indent=2))
print(json.dumps({'status': 'ready', 'model': model}), flush=True)
deadline = time.monotonic()+180
while not (HERE/'start-compilers.gate').is_file():
    if time.monotonic() > deadline:
        raise TimeoutError('Coordinator compiler start gate not released')
    time.sleep(.1)

def process_times(process):
    created = ctypes.wintypes.FILETIME()
    exited = ctypes.wintypes.FILETIME()
    kernel = ctypes.wintypes.FILETIME()
    user = ctypes.wintypes.FILETIME()
    assert ctypes.windll.kernel32.GetProcessTimes(
        ctypes.wintypes.HANDLE(process._handle), ctypes.byref(created),
        ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user))
    def stamp(value):
        raw = (value.dwHighDateTime << 32) | value.dwLowDateTime
        return dt.datetime.fromtimestamp(raw/10000000-11644473600, dt.timezone.utc).isoformat()
    return stamp(created), stamp(exited) if exited.dwLowDateTime or exited.dwHighDateTime else None

with log.open('w', encoding='utf-8') as stream:
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
    start, _ = process_times(process)
    receipt.update(status='running', pid=process.pid, startUtc=start)
    receipt_path.write_text(json.dumps(receipt, indent=2))
    print(json.dumps({'status': 'running', 'model': model, 'pid': process.pid, 'startUtc': start}), flush=True)
    code = process.wait()
    _, end = process_times(process)
text = log.read_text(encoding='utf-8', errors='replace')
lines = text.splitlines()
receipt.update(exitCode=code, endUtc=end, sourceHashesAfter=hashes(),
    warnings=[line for line in lines if re.search(r'\bwarning:', line, re.I)],
    errors=[line for line in lines if re.search(r'\berror:|^\s*\*\*\*\s+\[|FAILED', line, re.I)],
    memorySummary=[line for line in lines if line.strip().startswith(('RAM:', 'Flash:'))])
receipt['status'] = 'failed'
if code == 0 and receipt['sourceHashesAfter'] == before and '[SUCCESS]' in text:
    artifact = ROOT/'firmware/.pio/artifacts/gld-dataset-workflow-wifi-20261103-bounded-timeout'/name
    artifact.mkdir(parents=True, exist_ok=False)
    receipt.update(status='success', artifactDirectory=str(artifact), files=[])
    for filename in ('bootloader.bin', 'partitions.bin', 'boot_app0.bin', 'firmware.bin'):
        source = build/filename
        if filename == 'boot_app0.bin' and not source.is_file():
            source = Path.home()/'.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin'
        target = artifact/filename
        shutil.copy2(source, target)
        receipt['files'].append(dict(name=filename, path=str(target), buildPath=str(source),
                                     size=target.stat().st_size, sha256=sha(target)))
    receipt['firmwareSha256'] = sha(artifact/'firmware.bin')
receipt_path.write_text(json.dumps(receipt, indent=2))
print(json.dumps({key: receipt[key] for key in ('status', 'exitCode', 'startUtc', 'endUtc',
                                               'memorySummary', 'warnings', 'errors')}), flush=True)
sys.exit(0 if receipt['status'] == 'success' else 1)
