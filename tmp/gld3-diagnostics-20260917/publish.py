"""Publish only the verified GLD3 package, plus a reproducible scoped source archive."""
import hashlib
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent
EVIDENCE = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT
MAIN = ROOT.parents[1]
WORK = pathlib.Path('D:/Github/PertaminaGLD-GLD3-Diagnostics')
REL_PACKAGE = pathlib.Path('apps/operator-hub/firmware-packages/gld_v3/latest')
SRC = WORK / REL_PACKAGE
manifest_bytes = (SRC / 'manifest.json').read_bytes()
assert hashlib.sha256(manifest_bytes).hexdigest() == (EVIDENCE / 'approved-manifest.sha256').read_text().strip()
manifest = json.loads(manifest_bytes)
upload = json.loads((EVIDENCE / 'upload-summary.json').read_text())
assert json.loads((EVIDENCE / 'bench-verdict.json').read_text())['allChecksPass']
assert upload['flashVerified'] and upload['nvsUnchanged'] and upload['resetCommandSucceeded']
assert upload['firmwareVersion'] == manifest['firmwareVersion'] == '0.8.31'
assert manifest['environment'] == 'gld_v3'
spec = importlib.util.spec_from_file_location('package_hook', WORK / 'firmware/tools/operator_package_post.py')
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)
assert hook._firmware_tree_snapshot_sha256(WORK / 'firmware') == manifest['source']['firmwareTreeSnapshotSha256']
assert upload['firmwareSha256'] == next(r['sha256'] for r in manifest['flashFiles'] if r['path'] == 'firmware.bin')
assert (ROOT / 'previous-gld3-0.8.30/manifest.json').exists()
for row in manifest['flashFiles']:
    assert hashlib.sha256((SRC / row['path']).read_bytes()).hexdigest() == row['sha256']
destination = MAIN / REL_PACKAGE
destination.mkdir(parents=True, exist_ok=True)
for name in ['manifest.json', 'manifest.sha256'] + [r['path'] for r in manifest['flashFiles']]:
    shutil.copy2(SRC / name, destination / name)
    assert (SRC / name).read_bytes() == (destination / name).read_bytes()

files = [
    'firmware/gld/include/BoardPins.h',
    'firmware/gld/include/BoardPinsGLD3.h',
    'firmware/gld/src/GldUnifiedMain.cpp',
    'firmware/gld/tests/test_gld3_diagnostic_contract.py',
    'firmware/platformio.ini',
    'firmware/shared/include/FirmwareVersion.h',
    'firmware/tools/operator_package_post.py',
]
archive = MAIN / 'docs/wiring/GLD3-v0.8.31-source-changes.zip'
assert not archive.exists(), 'Do not overwrite an existing source archive'
patch = subprocess.run(['git', 'diff', '--binary', '--', 'firmware'], cwd=WORK, capture_output=True, check=True).stdout
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for relative in files:
        z.write(WORK / relative, relative)
    z.writestr('tracked-changes.patch', patch)
    z.writestr('README.txt',
        'GLD3 v0.8.31 scoped source changes, not a complete repository.\n'
        'Base commit: dfba98f237b6b1f83c139f49e0e8a1c2e683e5af\n'
        'Validated worktree: D:/Github/PertaminaGLD-GLD3-Diagnostics\n'
        'Do not overlay blindly onto the dirty main/GLD1 checkout.\n'
        'Included paths are the complete changed/new source files over that base.\n'
        'Build from firmware/: pio run -e gld_v3 -j 1\n'
        'Windows linker may require TEMP/TMP/TMPDIR set to a local forward-slash path.\n'
        'See docs/wiring/GLD3-diagnostics-2026-09-17.md in main for verified evidence and limits.\n')
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
print('Published only gld_v3/latest and source changes archive:', archive)
