"""Authorized Model2/COM7 upload through the existing Hub bridge, NVS OFF."""
from pathlib import Path
import datetime as dt
import json
import re
import threading
import time
import urllib.request

HERE = Path(__file__).resolve().parent
BASE = 'http://127.0.0.1:5174'
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
REPORT = HERE/'upload-result.json'
health = json.load(opener.open(BASE+'/api/health', timeout=5))
headers = {'X-GLD-Bridge-Token': health['csrfToken']}
report = {'startedAt': dt.datetime.now().astimezone().isoformat(), 'stage': 'preflight',
          'port': 'COM7', 'model': 2, 'resetNvs': False, 'uploadAttempts': 0}


def save():
    REPORT.write_text(json.dumps(report, indent=2), encoding='utf-8')


def get(path):
    return json.load(opener.open(urllib.request.Request(BASE+'/api/'+path, headers=headers), timeout=6))


def post(path, value, timeout=8):
    request = urllib.request.Request(BASE+'/api/'+path, data=json.dumps(value).encode(),
        headers={**headers, 'Content-Type': 'application/json'}, method='POST')
    return json.load(opener.open(request, timeout=timeout))


def read_device(timeout, settled_profile=None):
    after = get('serial/recent?slot=1&after=0')['sequence']
    current = get('serial/status')
    assert not current['connected'] or current.get('port') == 'COM7'
    if not current['connected']:
        post('serial/connect', {'slot': 1, 'port': 'COM7', 'baud': 115200})
    try:
        deadline = time.monotonic()+timeout
        last_query = 0
        found = {}
        while time.monotonic() < deadline:
            if time.monotonic()-last_query > 2:
                for command in ('GET_INFO', 'GET_STATUS'):
                    post('serial/write', {'slot': 1, 'line': command})
                last_query = time.monotonic()
            data = get(f'serial/recent?slot=1&after={after}')
            for item in data['lines']:
                line = item.get('line', '')
                position = line.find('{')
                if position < 0:
                    continue
                try:
                    value = json.loads(line[position:])
                except ValueError:
                    continue
                if 'GLD_STATUS_JSON' in line[:position]:
                    found['status'] = {key: value.get(key) for key in
                        ('deviceId', 'mode', 'uptimeMs', 'model', 'power', 'bootHealth')}
                elif 'GLD_INFO_JSON' in line[:position]:
                    found['info'] = {key: value.get(key) for key in
                        ('deviceId', 'mode', 'firmwareVersion', 'boardProfile')}
            if 'info' in found and 'status' in found:
                model = found['status'].get('model', {})
                if (settled_profile is None or
                        model.get('activeNullingProfileId') == settled_profile and
                        model.get('boundNullingProfileId') == settled_profile and
                        model.get('profileReady') is True and
                        model.get('inferenceValid') is True):
                    return found
            time.sleep(.25)
        raise TimeoutError('Fresh device readback unavailable')
    finally:
        post('serial/disconnect', {'slot': 1})


def progress():
    try:
        stream = opener.open(urllib.request.Request(BASE+'/api/events', headers=headers), timeout=5)
        event = ''
        for raw in stream:
            line = raw.decode('utf-8', errors='replace').strip()
            if line.startswith('event: '):
                event = line[7:]
            elif line.startswith('data: ') and event == 'upload_progress':
                data = json.loads(line[6:])
                percent = data.get('percent')
                if isinstance(percent, (int, float)):
                    print(f'Upload: {percent:.0f}%', flush=True)
            elif line.startswith('data: ') and event == 'upload_done':
                report['flashDoneEvent'] = True
    except Exception:
        pass


save()
try:
    print('UPLOAD MODEL 2 - COM7 - RESET NVS OFF', flush=True)
    print('Memakai backend yang sedang berjalan; tidak membuka Hub baru.', flush=True)
    usb = [p for p in get('ports')['ports']
           if p.get('vendorId') == 6790 and 'CH340' in p.get('description', '')
           and '(COM7)' in p.get('description', '')]
    assert len(usb) == 1, 'Expected CH340 COM7 unavailable'
    for endpoint in ('dataset-workflow/state', 'wireless-dataset/state', 'wireless-replay/state'):
        state = get(endpoint)
        assert not state.get('connected') and not state.get('cleanup_pending')
        assert state.get('state') in ('disconnected', 'error', 'not_ready')
    report['before'] = read_device(8)
    before = report['before']['status']
    assert before['deviceId'] == '1002' and before['power']['externalPower'] is True
    assert before['mode'] == 'inference' and before['model']['profileReady'] is True
    assert before['model']['activeNullingProfileId'] == 2
    assert before['model']['boundNullingProfileId'] == 2
    report['stage'] = 'readback_checked'
    save()
    environment = 'gld_model_2_dataset_workflow_wifi'
    package = get('firmware/package?env='+environment)
    receipt = json.loads((HERE/'model2-build-receipt.json').read_text())
    expected = receipt['firmwareSha256']
    actual = next(f['sha256'] for f in package['manifest']['flashFiles'] if f['path'] == 'firmware.bin')
    assert actual == expected and package['manifest']['environment'] == environment
    report.update(stage='uploading', firmwareSha256=expected, uploadAttempts=1)
    save()
    threading.Thread(target=progress, daemon=True).start()
    print('Identitas 1002, profil #2 dan catu 24V diperiksa. Memulai flash...', flush=True)
    response = post('firmware/upload', {'env': environment, 'port': 'COM7',
        'targetDeviceId': '1002', 'resetNvs': False, 'slot': 1,
        'manifest': package['manifest'], 'packageFiles': package['packageFiles']}, timeout=240)
    assert response.get('ok') is True and response.get('nvsReset') is False
    assert response.get('verifiedFiles') == 4
    report.update(stage='flash_complete_readback_pending', flashToolCompleted=True,
                  verifiedFiles=4, uploadResult={key: response.get(key) for key in
                    ('ok', 'env', 'port', 'firmwareVersion', 'verifiedFiles', 'nvsReset')})
    save()
    print('Flash selesai. Menunggu status GLD; profil dan binding tidak diubah...', flush=True)
    time.sleep(2)
    report['after'] = read_device(90, settled_profile=2)
    after = report['after']['status']
    assert after['deviceId'] == '1002'
    assert after['model']['activeNullingProfileId'] == before['model']['activeNullingProfileId']
    assert after['model']['boundNullingProfileId'] == before['model']['boundNullingProfileId']
    assert after['model']['productionApproved'] is True
    report.update(stage='complete', status='PASS', profilePreserved=True,
                  bindingPreserved=True, serialDisconnected=True)
    print('PASS: flash terverifikasi, ID1002/profil2/binding2 tetap. COM dilepas untuk uji Wi-Fi.', flush=True)
except Exception as error:
    report.update(status='NEEDS_RECONCILIATION', errorClass=type(error).__name__)
    print('Proses berhenti; perlu pemeriksaan hasil. Tidak mengulang flash otomatis.', flush=True)
finally:
    report['finishedAt'] = dt.datetime.now().astimezone().isoformat()
    save()
input('Tekan Enter untuk menutup terminal upload...')
