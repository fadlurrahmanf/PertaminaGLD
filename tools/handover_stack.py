"""Restore and run the Git-ready stack without altering source profiles/services."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import webbrowser

sys.path.insert(0, str(Path(__file__).resolve().parent))
import handover_runtime as runtime_tool
import handover_snapshot as snapshot_tool
import handover_database as db
import handover_check as preflight


def require(condition, code):
    if not condition: raise ValueError(code)


def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8'); temporary.replace(path)


def effective_ports(config, offset):
    require(type(offset) is int and 0 <= offset <= 20000, 'INVALID_PORT_OFFSET')
    ports = {key: int(value) + offset for key, value in config['ports'].items()}
    ports.update(gld=5174 + offset, ch=5273 + offset, gw=5373 + offset)
    require(all(1024 <= port <= 65535 for port in ports.values()) and len(set(ports.values())) == len(ports), 'INVALID_PORTS')
    return ports


def require_free_ports(ports):
    for port in ports.values():
        with socket.socket() as sock:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'): sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try: sock.bind(('0.0.0.0', port))
            except OSError: raise ValueError('PORT_OCCUPIED_' + str(port)) from None


def pid_alive(pid):
    require(type(pid) is int and pid > 0, 'INVALID_LOCK_PID')
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=kernel.OpenProcess(0x1000,False,pid)
        if not handle:
            # Access denied is not evidence that somebody else's process died.
            return ctypes.get_last_error() != 87
        try:
            code=wintypes.DWORD()
            require(kernel.GetExitCodeProcess(handle,ctypes.byref(code)), 'LOCK_OWNER_STATE_UNKNOWN')
            return code.value==259
        finally:kernel.CloseHandle(handle)
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False
    except PermissionError:return True


def acquire_lock(path):
    path=Path(path)
    require(not path.is_symlink(), 'LOCK_PATH_LINKED')
    if path.exists():
        require(path.stat().st_size<4096, 'LOCK_NOT_OWNED_BY_HANDOVER')
        original=path.read_bytes()
        try:value=json.loads(original)
        except ValueError:raise ValueError('LOCK_NOT_OWNED_BY_HANDOVER') from None
        require(value.get('kind')=='pertamina-gld-handover' and value.get('workRoot')==str(path.parent.resolve()),'LOCK_NOT_OWNED_BY_HANDOVER')
        require(not pid_alive(value.get('pid')), 'HANDOVER_ALREADY_RUNNING')
        require(path.read_bytes()==original,'LOCK_OWNER_CHANGED')
        path.unlink()
    with path.open('x',encoding='utf-8') as stream:
        json.dump(dict(kind='pertamina-gld-handover',pid=os.getpid(),workRoot=str(path.parent.resolve())),stream)


def ensure_driver(repo):
    """Use the signed bundled driver only when the PC has no CH341 package.

    This is first-run OS setup by the user-owned visible launcher. Verification
    tests never install drivers. Windows itself presents the elevation prompt.
    """
    import handover_driver as driver
    require(os.name == 'nt', 'WINDOWS_X64_REQUIRED')
    if driver.discover_driver():return 'already_present'
    command = driver.install_command_plan(repo/'handover/drivers/ch340-windows-x64/driver-manifest.json')
    import ctypes
    from ctypes import wintypes
    class ExecuteInfo(ctypes.Structure):
        _fields_=[('cbSize',wintypes.DWORD),('fMask',wintypes.ULONG),('hwnd',wintypes.HWND),
            ('lpVerb',wintypes.LPCWSTR),('lpFile',wintypes.LPCWSTR),('lpParameters',wintypes.LPCWSTR),
            ('lpDirectory',wintypes.LPCWSTR),('nShow',ctypes.c_int),('hInstApp',wintypes.HINSTANCE),
            ('lpIDList',ctypes.c_void_p),('lpClass',wintypes.LPCWSTR),('hkeyClass',wintypes.HKEY),
            ('dwHotKey',wintypes.DWORD),('hIcon',wintypes.HANDLE),('hProcess',wintypes.HANDLE)]
    info=ExecuteInfo();info.cbSize=ctypes.sizeof(info);info.fMask=0x40;info.lpVerb='runas'
    info.lpFile=command[0];info.lpParameters=subprocess.list2cmdline(command[1:]);info.lpDirectory=str(repo);info.nShow=1
    print('Windows meminta izin untuk memasang driver CH340 yang belum tersedia.',flush=True)
    require(ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)), 'CH340_DRIVER_SETUP_NOT_APPROVED')
    try:
        require(ctypes.windll.kernel32.WaitForSingleObject(info.hProcess,120000)==0,'CH340_DRIVER_SETUP_TIMEOUT')
        code=wintypes.DWORD();require(ctypes.windll.kernel32.GetExitCodeProcess(info.hProcess,ctypes.byref(code)), 'CH340_DRIVER_SETUP_RESULT_UNAVAILABLE')
        require(code.value in (0,3010),'CH340_DRIVER_SETUP_FAILED')
    finally:ctypes.windll.kernel32.CloseHandle(info.hProcess)
    require(driver.discover_driver(),'CH340_DRIVER_SETUP_NOT_CONFIRMED')
    return 'installed'


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def api(url, method='GET', payload=None, headers=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method,
        headers={'Content-Type':'application/json', **(headers or {})})
    with OPENER.open(request, timeout=5) as response: return json.load(response)


def wait_json(url, predicate, process, timeout=70):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        require(process.poll() is None, 'CHILD_EXITED_BEFORE_READY')
        try:
            value = api(url)
            if predicate(value): return value
        except (OSError, ValueError): pass
        time.sleep(.4)
    raise ValueError('SERVICE_READY_TIMEOUT')


def prepare(repo, work, offset):
    deployment = read(repo / 'handover/deployment.json'); ports = effective_ports(deployment, offset)
    manifest = snapshot_tool.validate_snapshot(repo / 'handover/state')
    state_hash = digest(repo / 'handover/state/snapshot-manifest.json')
    runtime_manifest = repo / 'handover/runtime/windows-x64/runtime-manifest.json'
    runtime = work / ('runtime-' + digest(runtime_manifest)[:12])
    if not runtime.exists(): runtime_tool.extract_runtime(runtime_manifest, runtime)
    database_manifest = repo / 'handover/runtime/database-windows-x64/database-runtime-manifest.json'
    database_runtime = work / ('database-runtime-' + digest(database_manifest)[:12])
    if not database_runtime.exists(): db.extract_runtime(database_manifest, database_runtime)
    state = work / ('snapshot-' + state_hash[:12])
    if not state.exists(): snapshot_tool.restore(repo / 'handover/state', state)
    system = read(state / 'config/system.json')
    checked = preflight.check(repo, state_config=state / 'config/system.json', runtime_root=runtime)
    require(checked['ok'], 'HANDOVER_PREFLIGHT_FAILED')
    # The existing GLD bridge reads its provisioning key here. Preserve an
    # existing config; only a clean checkout needs this non-destructive restore.
    env_path = repo / 'server/nodered/.env'
    if not env_path.exists():
        env_path.parent.mkdir(parents=True, exist_ok=True)
        with env_path.open('xb') as stream: stream.write((state / 'config/source-server.env').read_bytes())
    else:
        current = snapshot_tool._env(env_path.read_bytes())
        for key in ('GLD_AES128_KEY_HEX', 'GLD_KEY_ID'):
            require(current.get(key) == system['serverEnv'].get(key), 'EXISTING_AES_CONFIG_CONFLICT')
    system['serverEnv']['PGL_FIELD_TEST_LOG_DIR'] = str(work / 'history/field-test-logs')
    hub = work / 'hub'; hub.mkdir(parents=True, exist_ok=True)
    broker = dict(system['broker']); broker.update(port=ports['mqtt'], topicRoot='gld/gateway')
    existing = hub / 'credentials.local.json'
    if existing.exists():
        previous = read(existing)
        require(all(previous.get(key) == broker[key] for key in ('username','password')), 'EXISTING_BROKER_CONFIG_CONFLICT')
    write(existing, broker)
    return dict(deployment=deployment, ports=ports, runtime=runtime, database_runtime=database_runtime,
                state=state, system=system, manifest=manifest, hub=hub, preflight=checked)


def mqtt_publish(host, port, username, password, topic, value):
    def string(value):
        raw = value.encode(); return struct.pack('!H', len(raw)) + raw
    def packet(kind, body):
        length = len(body); encoded = bytearray()
        while True:
            digit = length % 128; length //= 128; encoded.append(digit | (128 if length else 0))
            if not length: return bytes([kind]) + encoded + body
    client = 'handover-check-' + uuid.uuid4().hex[:12]
    connect = b'\x00\x04MQTT\x04\xc2\x00\x1e' + string(client) + string(username) + string(password)
    with socket.create_connection((host, port), timeout=5) as sock:
        sock.settimeout(5); sock.sendall(packet(0x10, connect))
        answer = b''
        while len(answer) < 4:
            chunk = sock.recv(4-len(answer)); require(chunk, 'MQTT_CONNECTION_CLOSED'); answer += chunk
        require(answer == b'\x20\x02\x00\x00', 'MQTT_AUTH_FAILED')
        sock.sendall(packet(0x30, string(topic) + json.dumps(value).encode()))
        # Keep the connection alive until the broker has consumed the publish.
        sock.sendall(b'\xc0\x00'); require(sock.recv(2) == b'\xd0\x00', 'MQTT_PUBLISH_UNCONFIRMED')
        sock.sendall(b'\xe0\x00')


def synthetic_node_id(profile, topology):
    """Keep repeat acceptance from conflicting with durable replay/topology state."""
    require(isinstance(topology, dict) and isinstance(topology.get('nodes'), list),
            'SYNTHETIC_TOPOLOGY_INVALID')
    used = set()
    for node in topology['nodes']:
        if not isinstance(node, dict): continue
        if type(node.get('nodeId')) is int: used.add(node['nodeId'])
        if isinstance(node.get('nodeIdHex'), str):
            try: used.add(int(node['nodeIdHex'], 16))
            except ValueError: pass
    replay = Path(profile) / 'pertamina-gld-replay-state.json'
    if replay.is_file():
        value = read(replay)
        require(isinstance(value, dict) and isinstance(value.get('observations'), dict),
                'SYNTHETIC_REPLAY_STATE_INVALID')
        for key in value['observations']:
            if isinstance(key, str) and key.startswith('production:'):
                try: used.add(int(key.split(':', 1)[1]))
                except ValueError: raise ValueError('SYNTHETIC_REPLAY_STATE_INVALID') from None
    for candidate in range(0xE000, 0xF000):
        if candidate not in used:
            return candidate
    raise ValueError('SYNTHETIC_TEST_IDS_EXHAUSTED')


def self_test(repo, prepared, work, profile):
    cfg = prepared['deployment']['database']; port = prepared['ports']['database']; database_runtime = prepared['database_runtime']
    label = 'handover_' + uuid.uuid4().hex[:10]
    sample = dict(device_id='1002', node_id=0x1002, mode='DATASET', seq=int(time.time()) % 4294967295,
        timestamp_ms=123456789, nulling_profile_id=2, label=label,
        feature_order=['MQ8','MQ135','MQ3','MQ5','MQ4','MQ7','MQ6','MQ2'],
        sensor_voltage=[.1,.2,.3,.4,.5,.6,.7,.8],sensor_gain=[1]*8,sensor_status=[0]*8)
    broker = prepared['system']['broker']
    mqtt_publish(broker['host'], prepared['ports']['mqtt'], broker['username'], broker['password'],
                 'gas-leak-detector/1002/dataset/data', sample)
    end = time.monotonic() + 30; persisted = False
    while time.monotonic() < end:
        value = db.run_sql(database_runtime, cfg, port,
            f"USE `{cfg['name']}`;SELECT COUNT(*) FROM gld_dataset WHERE label='{label}';").strip()
        if value == b'1': persisted=True; break
        time.sleep(.5)
    require(persisted, 'NODERED_MQTT_DATABASE_WRITE_FAILED')
    csv_path = work / 'history/incoming/gld-dataset.csv'
    end=time.monotonic()+10
    while time.monotonic()<end and (not csv_path.is_file() or label not in csv_path.read_text(encoding='utf-8-sig')):time.sleep(.1)
    require(csv_path.is_file() and label in csv_path.read_text(encoding='utf-8-sig'), 'NODERED_CSV_WRITE_FAILED')
    # Use the restored active AES key without putting it in argv or console.
    code = "const c=require('crypto'),fs=require('fs');const s=JSON.parse(fs.readFileSync(0,'utf8'));const k=Buffer.from(s.serverEnv.GLD_AES128_KEY_HEX,'hex'),iv=c.randomBytes(12),p=Buffer.from('handover-check');const e=c.createCipheriv('aes-128-gcm',k,iv);const b=Buffer.concat([e.update(p),e.final()]);const d=c.createDecipheriv('aes-128-gcm',k,iv);d.setAuthTag(e.getAuthTag());if(!Buffer.concat([d.update(b),d.final()]).equals(p))process.exit(1);"
    result = subprocess.run([str(prepared['runtime']/'node/node.exe'),'-e',code], input=json.dumps(prepared['system']).encode(),capture_output=True,timeout=15)
    require(result.returncode == 0, 'AES_ROUNDTRIP_FAILED')
    topology_url=f"http://127.0.0.1:{prepared['ports']['nodeRed']}/pertamina-gld/topology"
    node_id=synthetic_node_id(profile,api(topology_url))
    encrypted=subprocess.run([str(prepared['runtime']/'node/node.exe'),str(repo/'tools/handover_crypto_smoke.cjs'),
                              str(prepared['state']/'config/system.json'),'--node-id',str(node_id)],capture_output=True,timeout=15)
    require(encrypted.returncode==0,'AES_FRAME_GENERATION_FAILED')
    smoke=json.loads(encrypted.stdout)
    for message in smoke['messages']:
        mqtt_publish(broker['host'],prepared['ports']['mqtt'],broker['username'],broker['password'],message['topic'],message['payload'])
    expected=smoke['expected'];end=time.monotonic()+20;decrypted=False
    while time.monotonic()<end:
        topology=api(topology_url)
        node=next((n for n in topology.get('nodes',[]) if n.get('type')=='gld' and n.get('nodeIdHex')==expected['nodeIdHex']),{})
        if (all(node.get(k)==expected[k] for k in smoke['verifyHttp']['requiredNodeFields']) and
                node.get('chIdHex')==expected['chIdHex'] and expected['gatewayIdHex'] in topology.get('gatewayIds',[])):
            decrypted=True;break
        time.sleep(.4)
    require(decrypted,'AES_MQTT_NODERED_DECRYPT_FAILED')
    counts = db.run_sql(database_runtime,cfg,port,f"USE `{cfg['name']}`;SELECT COUNT(*),COALESCE(SUM(row_count),0),COALESCE(SUM(SHA2(content,256)<>file_sha256),0) FROM handover_files;").decode().strip().split('\t')
    return dict(mqttAuthentication=True,nodeRedDatabaseInsert=True,nodeRedCsvWrite=True,aesRoundTrip=True,aesMqttNodeRedDecrypt=True,
                historyFiles=int(counts[0]),historyRows=int(counts[1]),historyByteMismatches=int(counts[2]),hardwareTested=False)


def missing_history_rows(database_rows, history):
    """Check the owned database before trusting an old import receipt.

    Extra hashes from an earlier snapshot are retained. Existing damaged rows
    are never silently overwritten by INSERT IGNORE or treated as complete.
    """
    expected = {item['sha256']: item['size'] for item in history['files']}
    observed = {}
    for line in database_rows.decode('ascii').splitlines():
        fields = line.split('\t')
        require(len(fields) == 5, 'HISTORY_DATABASE_AUDIT_INVALID')
        digest, size, content_digest, declared_rows, actual_rows = fields
        require(digest not in observed and digest and size.isdecimal() and
                declared_rows.isdecimal() and actual_rows.isdecimal(), 'HISTORY_DATABASE_AUDIT_INVALID')
        observed[digest] = (int(size), content_digest, int(declared_rows), int(actual_rows))
    for digest, size in expected.items():
        record = observed.get(digest)
        if record is not None:
            require(record[0] == size and record[1] == digest and record[2] == record[3],
                    'HISTORY_DATABASE_INTEGRITY_FAILED')
    return set(expected) - set(observed)


def verify_history_row_digests(database_rows, history, history_root):
    """Check every derived row against the committed original file bytes."""
    expected = {item['sha256']: item for item in history['files']}
    require(all(re.fullmatch(r'[0-9a-f]{64}', key) for key in expected),
            'HISTORY_DATABASE_AUDIT_INVALID')
    actual = iter(database_rows.decode('ascii').splitlines())
    current = next(actual, None)
    root = Path(history_root).resolve()
    for file_hash, item in sorted(expected.items()):
        path = (root / item['path']).resolve()
        require(path.is_relative_to(root) and path.is_file(), 'HISTORY_SOURCE_INVALID')
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == file_hash, 'HISTORY_SOURCE_INVALID')
        _, _, source_rows = db._history_rows(raw, path.suffix)
        for index, row in enumerate(source_rows, 1):
            require(current is not None, 'HISTORY_DATABASE_INTEGRITY_FAILED')
            fields = current.split('\t')
            require(len(fields) == 3 and fields[0] == file_hash and fields[1] == str(index),
                    'HISTORY_DATABASE_INTEGRITY_FAILED')
            row_hash = hashlib.sha256(json.dumps(row, ensure_ascii=False).encode('utf-8')).hexdigest()
            require(fields[2] == row_hash, 'HISTORY_DATABASE_INTEGRITY_FAILED')
            current = next(actual, None)
        require(current is None or not current.startswith(file_hash + '\t'),
                'HISTORY_DATABASE_INTEGRITY_FAILED')
    require(current is None, 'HISTORY_DATABASE_INTEGRITY_FAILED')


def run(repo, work, offset=0, test_once=False, local_only=False, no_browser=False):
    import handover_nodered as nr
    work.mkdir(parents=True, exist_ok=True)
    cfg=read(repo/'handover/deployment.json');ports=effective_ports(cfg,offset);require_free_ports(ports)
    lock=work/'stack.lock'
    acquire_lock(lock)
    prepared=None;database=None;hub_process=None;node_process=None;handles=[]
    report={'status':'starting','hardwareTested':False,'sourceDatabaseModified':False}
    result_path=work/'stack-result.json'
    try:
        print('Menyiapkan runtime, konfigurasi dan histori...',flush=True)
        if not test_once and offset==0:report['driverSetup']=ensure_driver(repo)
        prepared=prepare(repo,work,offset)
        data=work/'database-data'
        if not data.exists(): db.initialize(prepared['database_runtime'],data,cfg['database'],ports['database'])
        database=db.start(prepared['database_runtime'],data,cfg['database'],ports['database'])
        history={'files':[dict(path=item['path'],sha256=item['sha256'],size=item['size'],sources=[item.get('sourcePath',item['path'])]) for item in prepared['manifest']['files'] if item['role'] in ('dataset-csv','dataset-ledger')]}
        print('Memeriksa histori database...',flush=True)
        receipt=work/'history-import.json';fingerprint=digest(repo/'handover/state/snapshot-manifest.json')
        audit_sql=(f"USE `{cfg['database']['name']}`;SELECT f.file_sha256,f.byte_count,"
                   "LOWER(SHA2(f.content,256)),f.row_count,COALESCE(r.actual,0) "
                   "FROM handover_files f LEFT JOIN (SELECT file_sha256,COUNT(*) actual "
                   "FROM handover_rows GROUP BY file_sha256) r ON r.file_sha256=f.file_sha256;")
        missing=missing_history_rows(db.run_sql(prepared['database_runtime'],cfg['database'],ports['database'],audit_sql),history)
        if not receipt.exists() or read(receipt).get('snapshot') != fingerprint or missing:
            imported=db.import_history(prepared['database_runtime'],cfg['database'],ports['database'],history,history_root=repo/'handover/state')
            write(receipt,{'snapshot':fingerprint,'files':imported['files'],'rows':imported['rows']})
            require(not missing_history_rows(db.run_sql(prepared['database_runtime'],cfg['database'],ports['database'],audit_sql),history),
                    'HISTORY_DATABASE_INTEGRITY_FAILED')
        row_hashes=','.join("'"+item['sha256']+"'" for item in history['files'])
        rows_sql=(f"USE `{cfg['database']['name']}`;SELECT file_sha256,row_index,LOWER(SHA2(row_json,256)) "
                  f"FROM handover_rows WHERE file_sha256 IN ({row_hashes}) ORDER BY file_sha256,row_index;")
        verify_history_row_digests(db.run_sql(prepared['database_runtime'],cfg['database'],ports['database'],rows_sql),
                                   history,repo/'handover/state')
        stop=prepared['hub']/'stop.request'
        if stop.exists(): stop.unlink()
        command=[sys.executable,str(repo/'tools/handover_hub.py'),'--repo-root',str(repo),'--runtime-dir',str(prepared['hub']),
            '--hub-port',str(ports['hub']),'--port-offset',str(offset)]
        if local_only:command.append('--loopback-broker')
        log=(work/'hub.log').open('ab');handles.append(log)
        hub_process=subprocess.Popen(command,cwd=repo,stdout=log,stderr=log)
        hub_status=wait_json(f"http://127.0.0.1:{ports['hub']}/api/status",lambda value:all(value.get('apps',{}).get(key,{}).get('identityOk') for key in ('gld','ch','gw')) and not value.get('mqttDegraded'),hub_process)
        broker=read(prepared['hub']/'credentials.local.json');prepared['system']['broker']=broker
        node_prepared=nr.prepare(repo,prepared['state'],prepared['runtime'],work,prepared['system'],cfg['database'],cfg['ports'],port_offset=offset)
        profile=Path(node_prepared['profile']);flows=Path(node_prepared['flows'])
        prepared['system']['serverEnv']['PGL_REPLAY_STATE_PATH'] = str(profile / 'pertamina-gld-replay-state.json')
        env=os.environ.copy();env.update({str(key):str(value) for key,value in prepared['system']['serverEnv'].items()});env['PGL_NODE_RED_PORT']=str(ports['nodeRed'])
        log=(work/'nodered.log').open('ab');handles.append(log)
        node_stop=work/'nodered.stop.request'
        if node_stop.exists():node_stop.unlink()
        node_process=subprocess.Popen([str(prepared['runtime']/'node/node.exe'),str(repo/'tools/handover_nodered_runner.cjs'),str(prepared['runtime']/'node-red/red.js'),str(profile),str(node_stop)],cwd=work,env=env,stdout=log,stderr=log)
        url=f"http://127.0.0.1:{ports['nodeRed']}"
        wait_json(url+'/flows',lambda value:isinstance(value,(list,dict)),node_process)
        nr.deploy(url,flows,token=prepared['system']['serverEnv'].get('NODE_RED_ADMIN_TOKEN',''))
        wait_json(url+'/pertamina-gld/topology',lambda value:value.get('kind')=='pgl-topology',node_process)
        time.sleep(2)
        effective_local_only = str(broker['host']).startswith('127.')
        report.update(status='ready',ports=ports,preflight=prepared['preflight']['counts'],history=read(receipt),localOnly=effective_local_only)
        if test_once:report.update(selfTest=self_test(repo,prepared,work,profile),status='PASS')
        write(result_path,report)
        print('Hub, MQTT, Node-RED, database dan histori siap.',flush=True)
        if not test_once:
            print(f"Hub http://127.0.0.1:{ports['hub']} | Node-RED {url} | Ctrl+C untuk menutup layanan milik launcher ini.",flush=True)
            if not no_browser:webbrowser.open(f"http://127.0.0.1:{ports['hub']}")
            while hub_process.poll() is None and node_process.poll() is None:time.sleep(.5)
            raise ValueError('OWNED_SERVICE_EXITED')
    except KeyboardInterrupt:report['status']='stopped_by_operator'
    except Exception as error:
        report.update(status='failed',errorClass=type(error).__name__,code=str(error) if isinstance(error,(ValueError,runtime_tool.RuntimeErrorSafe)) else 'HANDOVER_START_FAILED')
        # Fixed codes only; never reflect arbitrary subprocess/HTTP bodies.
        if not re_safe_code(report['code']):report['code']='HANDOVER_START_FAILED'
        print('Handover berhenti: '+report['code']+'. Lihat diagnostik lokal.',flush=True)
    finally:
        if node_process and node_process.poll() is None:
            write(work/'nodered.stop.request',{'requested':True})
            try:node_process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                report.update(status='cleanup_failed',cleanup='OWNED_NODERED_DID_NOT_STOP')
        if hub_process:
            write(prepared['hub']/'stop.request',{'requested':True})
            try:hub_process.wait(timeout=30)
            except subprocess.TimeoutExpired:report.update(status='cleanup_failed',cleanup='OWNED_HUB_DID_NOT_STOP')
        if database:
            try:db.stop(database)
            except Exception:report.update(status='cleanup_failed',cleanup='OWNED_DATABASE_DID_NOT_STOP')
        for stream in handles:stream.close()
        if lock.exists():lock.unlink()
        write(result_path,report)
    return report


def re_safe_code(value):
    return isinstance(value,str) and len(value)<160 and all(c.isupper() or c.isdigit() or c in '_ .' for c in value)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--work-root',type=Path)
    parser.add_argument('--port-offset',type=int,default=0)
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--local-only',action='store_true')
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args();repo=args.repo_root.resolve();work=(args.work_root or repo/'archive/apps/runtime/handover').resolve()
    try:result=run(repo,work,args.port_offset,args.self_test,args.local_only,args.no_browser)
    except Exception as error:
        code=str(error) if isinstance(error,ValueError) and re_safe_code(str(error)) else 'HANDOVER_START_FAILED'
        print('Handover berhenti: '+code+'. Tidak mengambil alih layanan lain.',flush=True)
        return 1
    return 0 if result['status'] in ('PASS','stopped_by_operator') else 1


if __name__=='__main__':raise SystemExit(main())
