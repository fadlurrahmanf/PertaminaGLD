"""Visible, one-shot, read-only GLD Hello diagnostic. Never changes Wi-Fi."""
from pathlib import Path
import base64
import datetime as dt
import ipaddress
import json
import re
import socket
import subprocess
import sys
import time
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/'apps/gld-operator'))
TARGET = 'GLD-DATASET-1002'
REPORT = HERE/'local-result.json'
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
STATE = {}


def command(args):
    return subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
        errors='replace', timeout=12,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout


def associated():
    text = command(['netsh', 'wlan', 'show', 'interfaces'])
    return TARGET in re.findall(r'^\s*SSID\s*:\s*(.*?)\s*$', text, re.M)


def on_link():
    text = command(['powershell', '-NoProfile', '-Command',
        "Find-NetRoute -RemoteIPAddress 192.168.4.1 | Select-Object IPAddress,NextHop,DestinationPrefix | ConvertTo-Json -Compress"])
    values = json.loads(text)
    values = values if isinstance(values, list) else [values]
    addresses = [v.get('IPAddress') for v in values if v.get('IPAddress')]
    return (any(ipaddress.ip_address(a) in ipaddress.ip_network('192.168.4.0/24')
                and a != '192.168.4.1' for a in addresses)
            and any(v.get('DestinationPrefix') == '192.168.4.0/24'
                    and v.get('NextHop') == '0.0.0.0' for v in values))


def workspace_busy():
    health = json.load(opener.open('http://127.0.0.1:5174/api/health', timeout=3))
    request = urllib.request.Request('http://127.0.0.1:5174/api/dataset-workflow/state',
        headers={'X-GLD-Bridge-Token': health['csrfToken']})
    state = json.load(opener.open(request, timeout=3))
    return bool(state.get('connected') or state.get('cleanup_pending') or
                state.get('state') in {'connecting', 'recording', 'starting', 'paused',
                    'recovering', 'replaying', 'stopping', 'stop_pending'})


def diagnose():
    result = STATE
    result.update({'capturedAt': dt.datetime.now().astimezone().isoformat(),
              'target': TARGET, 'commandsSent': [], 'wifiChanged': False,
              'serialOpened': False, 'configurationChanged': False,
              'diagnosticVersion': 2, 'stage': 'wait_association'})
    print('DIAGNOSTIK GLD - BACA SAJA', flush=True)
    print('Sambungkan Windows ke GLD-DATASET-1002.', flush=True)
    print('Biarkan Operator Hub terbuka. Tunggu hasil; jangan klik Connect selama pemeriksaan.', flush=True)
    print('Tidak memerlukan internet. Tidak memulai rekaman atau mengubah kalibrasi.', flush=True)
    deadline = time.monotonic()+600
    while time.monotonic() < deadline:
        if associated():
            try:
                if on_link():
                    break
            except (ValueError, OSError):
                pass
        time.sleep(1)
    else:
        result['outcome'] = 'target_association_or_dhcp_not_observed'
        return result
    result['associated'] = result['directSubnetRoute'] = True
    result['stage'] = 'check_workspace'
    if workspace_busy():
        result['outcome'] = 'workspace_already_connected_or_busy_no_probe'
        return result
    try:
        result['stage'] = 'tcp81'
        connection = socket.create_connection(('192.168.4.1', 81), timeout=5)
        connection.close()
        result['tcp81'] = 'reachable'
    except OSError as error:
        result.update(outcome='tcp_unreachable', errorClass=type(error).__name__,
                      errorNumber=getattr(error, 'winerror', None))
        return result
    # Credentials stay in memory; authenticate only after checking the GLD SSID
    # and on-link route, never through the Internet/default gateway.
    if not associated() or not on_link():
        result['outcome'] = 'network_changed_before_authentication'
        return result
    from workflow_credentials import resolve_workflow_password
    from wireless_dataset import _transport_factory
    result['stage'] = 'load_credentials'
    password = resolve_workflow_password(ROOT)
    authorization = base64.b64encode(('gld:'+password).encode('ascii')).decode('ascii')
    ws = None
    try:
        result['stage'] = 'websocket_handshake'
        ws = _transport_factory('ws://192.168.4.1:81/dataset', timeout=5,
            header=['Authorization: Basic '+authorization],
            http_no_proxy=['*'], redirect_limit=0, enable_multithread=True)
        result['stage'] = 'receive_hello'
        raw = ws.recv()
        if not isinstance(raw, str) or len(raw) > 16384:
            raise ValueError('Invalid Hello frame')
        hello = json.loads(raw)
        permitted = ('type', 'protocol', 'device_id', 'ready', 'reason',
            'nulling_profile_id', 'interval_ms', 'retention_ms', 'capacity',
            'sampling', 'paused', 'incomplete', 'oldest_seq', 'acked_next_seq',
            'total_samples', 'prediction_ready', 'prediction_enabled', 'transition_seq')
        result['hello'] = {key: hello.get(key) for key in permitted}
        result['model'] = {key: hello.get('model', {}).get(key) for key in
            ('profile_id', 'scaler_profile_id', 'production_approved',
             'runtime_version', 'output_elements', 'class_map')}
        result['capabilities'] = {key: hello.get('capabilities', {}).get(key) for key in
            ('pause', 'continue', 'durable_replay', 'requires_protocol3_client', 'prediction')}
        result['outcome'] = 'hello_received'
        from wireless_dataset_workflow import WorkflowCollector
        from wireless_dataset_replay import ProtocolError
        probe = WorkflowCollector(HERE/'unused', persist=lambda *args: None,
            cutoff=lambda *args: None, expected_device_id='1002', autostart_worker=False)
        try:
            probe._hello(hello, False)
            result.update(protocolCheck='PASS', effectiveReady=probe.ready,
                          deviceReason=probe.error)
        except ProtocolError as error:
            result.update(protocolCheck='REJECTED', deviceReason=str(error))
    except Exception as error:
        result.update(outcome='websocket_or_hello_failed', errorClass=type(error).__name__,
                      httpStatus=getattr(error, 'status_code', None))
    finally:
        if ws is not None:
            ws.close()
    return result


REPORT.write_text(json.dumps({'outcome': 'waiting_for_gld', 'diagnosticVersion': 2,
    'startedAt': dt.datetime.now().astimezone().isoformat(), 'commandsSent': [],
    'configurationChanged': False}, indent=2), encoding='utf-8')
try:
    result = diagnose()
except Exception as error:
    result = dict(STATE, outcome='diagnostic_failed', errorClass=type(error).__name__)
REPORT.write_text(json.dumps(result, indent=2), encoding='utf-8')
print('\nHASIL: '+result['outcome'], flush=True)
if 'hello' in result:
    print(json.dumps(result['hello'], indent=2), flush=True)
print('Hasil tersimpan. Sambungkan kembali internet lalu beri tahu Codex.', flush=True)
input('Tekan Enter untuk menutup jendela ini...')
