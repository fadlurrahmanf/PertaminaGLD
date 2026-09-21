"""Preserve old GLD3 package and fingerprint untouched main firmware/packages."""
import hashlib
import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent
REPO = ROOT.parents[1]
PACKAGE = REPO / 'apps/operator-hub/firmware-packages/gld_v3/latest'

def snapshot():
    result = {}
    for base in [REPO / 'firmware', REPO / 'apps/operator-hub/firmware-packages']:
        for path in sorted(base.rglob('*')):
            if not path.is_file() or any(x in path.parts for x in ('.pio', '__pycache__', 'gld_v3')):
                continue
            result[path.relative_to(REPO).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result

if sys.argv[1] == 'backup':
    assert not (ROOT / 'protected-before.json').exists(), 'Do not overwrite baseline'
    shutil.copytree(PACKAGE, ROOT / 'previous-gld3-0.8.30')
    data = snapshot()
    (ROOT / 'protected-before.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    print('Backed up old GLD3; protected main files:', len(data))
elif sys.argv[1] == 'verify':
    old = json.loads((ROOT / 'protected-before.json').read_text(encoding='utf-8'))
    new = snapshot()
    changed = [p for p in old.keys() | new.keys() if old.get(p) != new.get(p)]
    print(json.dumps({'unchanged': not changed, 'files': len(new), 'changed': changed}, indent=2))
    raise SystemExit(bool(changed))
