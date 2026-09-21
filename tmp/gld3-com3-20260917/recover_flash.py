"""Write the exact authorized GLD3 image in independently verified small blocks."""
import hashlib
import json
import pathlib
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
root = pathlib.Path(__file__).resolve().parent
package = root.parents[1] / 'apps/operator-hub/firmware-packages/gld_v3/latest'
esptool = pathlib.Path(r'C:\Users\MSI\.platformio\packages\tool-esptoolpy\esptool.py')
blob = (package / 'firmware.bin').read_bytes()
expected = '9238221e0af98a466e750897785c2b9f2cd0cee4ed33e63de759cd4807360f13'
assert len(blob) == 1044752 and hashlib.sha256(blob).hexdigest() == expected
chunk_size = 0x20000
rows = []
for index, start in enumerate(range(0, len(blob), chunk_size)):
    block = blob[start:start + chunk_size]
    filename = root / f'firmware-block-{index:02d}.bin'
    filename.write_bytes(block)
    offset = 0x10000 + start
    row = {'index': index, 'offset': hex(offset), 'size': len(block), 'sha256': hashlib.sha256(block).hexdigest()}
    rows.append(row)
    print('START', json.dumps(row), flush=True)
    command = [sys.executable, str(esptool), '--chip', 'esp32s3', '--port', 'COM3', '--baud', '230400', '--after', 'no_reset', 'write_flash', hex(offset), str(filename)]
    with (root / f'upload-block-{index:02d}.log').open('w', encoding='utf-8') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=55)
    row['exitCode'] = result.returncode
    print('DONE', index, 'exitCode', result.returncode, flush=True)
    (root / 'recovery-blocks.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    if result.returncode:
        print((root / f'upload-block-{index:02d}.log').read_text(encoding='utf-8')[-2400:], flush=True)
        raise SystemExit(result.returncode)
    time.sleep(0.5)
print('All blocks written; full-image verification still required.', flush=True)
