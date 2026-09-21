"""Exact GLD3 COM7 re-upload in bounded blocks; preserve and verify NVS bytes."""
import hashlib
import json
import pathlib
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
root = pathlib.Path(__file__).resolve().parent
workspace = root.parents[1]
package = workspace / 'apps/operator-hub/firmware-packages/gld_v3/latest'
esptool = pathlib.Path(r'C:\Users\MSI\.platformio\packages\tool-esptoolpy\esptool.py')
manifest = json.loads((package / 'manifest.json').read_text(encoding='utf-8'))
assert manifest['environment'] == 'gld_v3'
assert manifest['firmwareVersion'] == '0.8.30' and manifest['chip'] == 'esp32s3'
expected_app_hash = '9238221e0af98a466e750897785c2b9f2cd0cee4ed33e63de759cd4807360f13'
images = {}
for row in manifest['flashFiles']:
    data = (package / row['path']).read_bytes()
    assert len(data) == row['size'] and hashlib.sha256(data).hexdigest() == row['sha256']
    images[row['path']] = data
assert hashlib.sha256(images['firmware.bin']).hexdigest() == expected_app_hash
backup = (root / 'preflash-boot-nvs.bin').read_bytes()
assert len(backup) == 0x10000
before_nvs = backup[0x9000:0xE000]
summary = {'port': 'COM7', 'firmwareVersion': '0.8.30', 'firmwareSha256': expected_app_hash,
           'nvsBeforeSha256': hashlib.sha256(before_nvs).hexdigest(), 'operations': []}

def save():
    (root / 'upload-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')

def operation(name, args, baud=115200, after='no_reset', timeout=45):
    command = [sys.executable, str(esptool), '--chip', 'esp32s3', '--port', 'COM7',
               '--baud', str(baud), '--after', after] + args
    print('START', name, 'baud', baud, flush=True)
    log_path = root / (name + '.log')
    with log_path.open('w', encoding='utf-8') as log:
        try:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
            rc = result.returncode
        except subprocess.TimeoutExpired:
            rc = 124
    log_text = log_path.read_text(encoding='utf-8', errors='replace')
    summary['operations'].append({'name': name, 'baud': baud, 'exitCode': rc,
                                  'writeHashVerified': 'Hash of data verified.' in log_text,
                                  'verifyDigestCount': log_text.count('verify OK (digest matched)')})
    save()
    print('DONE', name, 'exitCode', rc, flush=True)
    if rc:
        print(log_text[-1500:], flush=True)
    return rc, log_text

boot_args = ['write_flash']
for filename, offset in [('bootloader.bin', '0x0'), ('partitions.bin', '0x8000'), ('boot_app0.bin', '0xE000')]:
    boot_args += [offset, str(package / filename)]
rc, boot_log = operation('write-boot', boot_args)
if rc or boot_log.count('Hash of data verified.') != 3:
    raise SystemExit('Boot write not verified; stop.')

blob = images['firmware.bin']
for index, start in enumerate(range(0, len(blob), 0x20000)):
    path = root / f'firmware-block-{index:02d}.bin'
    path.write_bytes(blob[start:start + 0x20000])
    success = False
    for attempt, baud in enumerate([230400, 115200, 115200], 1):
        rc, text = operation(f'write-block-{index:02d}-attempt-{attempt}',
                             ['write_flash', hex(0x10000 + start), str(path)], baud)
        if rc == 0 and 'Hash of data verified.' in text:
            success = True
            break
        time.sleep(0.5)
    if not success:
        raise SystemExit(f'Block {index} not verified; stop for recovery.')

verify_args = ['verify_flash']
for row in manifest['flashFiles']:
    verify_args += [row['offset'], str(package / row['path'])]
rc, verify_log = operation('verify-all-four', verify_args)
summary['flashVerified'] = rc == 0 and verify_log.count('verify OK (digest matched)') == 4
save()
if not summary['flashVerified']:
    raise SystemExit('Full flash verification failed; not accepted.')

rc, _ = operation('read-nvs-after', ['read_flash', '0x9000', '0x5000', str(root / 'postflash-nvs.bin')])
if rc:
    raise SystemExit('NVS preservation check unavailable; stop before normal boot.')
after_nvs = (root / 'postflash-nvs.bin').read_bytes()
summary['nvsAfterSha256'] = hashlib.sha256(after_nvs).hexdigest()
summary['nvsUnchanged'] = before_nvs == after_nvs
save()
if not summary['nvsUnchanged']:
    raise SystemExit('NVS bytes differ; stop before normal boot. Do not restore blindly.')

rc, _ = operation('final-chip-reset', ['read_mac'], after='hard_reset')
summary['resetCommandSucceeded'] = rc == 0
save()
if rc:
    raise SystemExit('Flash verified, normal reset requires follow-up.')
print('PASS: four complete flash images verified; NVS byte-identical; normal reset issued.', flush=True)
