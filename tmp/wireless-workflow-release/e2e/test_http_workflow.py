"""Actual HTTP/SSE/WS + service persistence against synthetic protocol3 GLD."""
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

HERE=Path(__file__).resolve().parent

def main():
    ready=json.loads((HERE/'ready.json').read_text())
    origin=ready['origin'];token=''
    def call(path,body=None,timeout=10):
        req=urllib.request.Request(origin+path,data=None if body is None else json.dumps(body).encode(),
            headers={'Content-Type':'application/json','Origin':origin,'X-GLD-Bridge-Token':token})
        with urllib.request.urlopen(req,timeout=timeout) as response:return json.load(response)
    health=call('/api/health');token=health['csrfToken']
    assert health['simulation'] and not health['features']['serial']
    def op(action,body=None):return call('/api/dataset-workflow/'+action,body or {})
    def state():return call('/api/dataset-workflow/state')
    def wait(predicate,seconds=20):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            value=predicate()
            if value:return value
            time.sleep(.03)
        raise AssertionError('Bounded fixture condition failed: '+str({k:v for k,v in state().items() if k!='history'}))
    def denied(action,body):
        try:op(action,body)
        except urllib.error.HTTPError as error:
            assert 400<=error.code<600 and json.load(error).get('error')
            return
        raise AssertionError('Invalid action admitted: '+action)
    def prepare(mode,label,fields=None):
        op('scan');op('select',{'device_id':'1002'})
        op('connect',{'device_id':'1002','password':ready['password']})
        op('choose-file')
        op('configure',{'mode':mode,'label':label,'fields':fields or dict(prediction=True,gain=True,status=True,timing=True)})
        locked=op('lock',{'locked':True});assert locked['locked'] and all(locked['steps'].values())
    report=dict(mode='pc-simulation',device_validation=False,cases=[],loaded_source_sha256=ready['loaded_source_sha256'])
    denied('lock',{'locked':True})
    prepare('direct','host_direct_pause')
    denied('configure',{'label':'tamper_locked'})
    op('start');call('/sim/acquire',{'count':8});wait(lambda:state()['count']==8)
    paused=op('pause');assert paused['state']=='paused'
    denied('lock',{'locked':False})
    path=Path(paused['csv_path']);before=path.read_bytes()
    call('/sim/advance',{'seconds':3});call('/sim/acquire',{'count':4})
    assert state()['count']==8 and path.read_bytes()==before
    op('resume');call('/sim/acquire',{'count':4});wait(lambda:state()['count']==12)
    stopped=op('stop');assert stopped['verification']['verified'] and stopped['complete']
    first_sid=call('/sim/state')['device']['session_id']
    op('continue');assert state()['csv_path']==str(path)
    assert call('/sim/state')['device']['session_id']!=first_sid
    call('/sim/acquire',{'count':4});wait(lambda:state()['count']==16)
    stopped=op('stop');assert stopped['verification']['verified'] and stopped['complete']
    report['cases'].append(dict(name='direct_pause_continue_stop_same_csv_new_segment',result='PASS',path=str(path),rows=16))
    snapshot_hash=hashlib.sha256(path.read_bytes()).hexdigest()
    op('reset');assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==snapshot_hash
    prepare('direct','host_direct_loss')
    op('start');call('/sim/acquire',{'count':8});wait(lambda:state()['count']==8)
    path=Path(state()['csv_path']);before=path.read_bytes()
    call('/sim/drop',{});wait(lambda:state()['cleanup_pending'])
    call('/sim/gap',{'count':8});assert path.read_bytes()==before
    call('/sim/resume',{});wait(lambda:state().get('cleanup_confirmed'),30)
    assert state()['count']==8 and path.read_bytes()==before
    old_sid=call('/sim/state')['device']['session_id']
    assert state()['can_continue']
    op('continue');assert call('/sim/state')['device']['session_id']!=old_sid
    call('/sim/acquire',{'count':8});wait(lambda:state()['count']==16)
    continued=op('stop');assert continued['verification']['verified'] and not continued['complete']
    assert path.read_bytes().startswith(before)
    report['cases'].append(dict(name='direct_loss_frozen_private_cleanup_then_next_segment',result='PASS',path=str(path),rows=16))
    op('reset')
    prepare('replay','host_replay_loss')
    op('start');call('/sim/acquire',{'count':8});wait(lambda:state()['count']==8)
    initial=state();sid=call('/sim/state')['device']['session_id']
    call('/sim/drop',{});wait(lambda:state()['recovery_active'])
    call('/sim/gap',{'count':12});call('/sim/resume',{})
    wait(lambda:state()['count']>=20,30)
    stopped=op('stop');assert stopped['verification']['verified'] and stopped['complete']
    assert stopped['csv_path']==initial['csv_path'] and call('/sim/state')['device']['session_id']==sid
    report['cases'].append(dict(name='replay_loss_same_csv_sid',result='PASS',path=stopped['csv_path'],rows=stopped['count']))
    op('reset')
    prepare('replay','host_replay_expiry')
    op('start');call('/sim/acquire',{'count':8});wait(lambda:state()['count']==8)
    call('/sim/drop',{});wait(lambda:state()['recovery_active'])
    call('/sim/gap',{'count':599});call('/sim/advance',{'seconds':.5})
    assert call('/sim/state')['device']['incomplete']
    call('/sim/resume',{})
    wait(lambda:state()['state']=='incomplete' and not state()['recovery_active'],60)
    expired=state();assert not expired['complete']
    report['cases'].append(dict(name='replay_exact_retention_bound_drained_incomplete',result='PASS',path=expired['csv_path'],rows=expired['count']))
    op('reset')
    prepare('direct','host_paused_reset')
    op('start');call('/sim/acquire',{'count':8});wait(lambda:state()['count']==8)
    paused=op('pause');path=Path(paused['csv_path']);before=path.read_bytes()
    sid=call('/sim/state')['device']['session_id']
    reset=op('reset');assert not reset['locked'] and reset['count']==0
    assert path.read_bytes()==before and not call('/sim/state')['device']['sampling']
    commands=next(s for s in call('/sim/state')['sessions'] if s['session_id']==sid)['commands']
    assert any(command['cmd']=='STOP_DATASET' for command in commands)
    report['cases'].append(dict(name='paused_reset_stops_verifies_preserves_file',result='PASS',path=str(path),rows=8))
    prepare('direct','host_minimal_columns',dict(prediction=False,gain=False,status=False,timing=False))
    op('start');call('/sim/acquire',{'count':8});wait(lambda:state()['count']==8)
    stopped=op('stop');assert stopped['verification']['verified']
    path=Path(stopped['csv_path']);header=path.open(encoding='utf-8').readline()
    assert 'timestamp_ms' in header and not any(x in header for x in ('gain_','status_','prediction_','scan_end_ms'))
    report['cases'].append(dict(name='minimal_projection_keeps_timestamp_and_all8_voltages',result='PASS',path=str(path),rows=8))
    op('reset')
    prepare('direct','host_tamper_guard')
    op('start');call('/sim/acquire',{'count':8});wait(lambda:state()['count']==8)
    stopped=op('stop');assert stopped['verification']['verified']
    path=Path(stopped['csv_path']);original=path.read_bytes()
    with path.open('ab') as stream:stream.write(b'EXTERNAL_SIMULATION_TAMPER\n')
    denied('continue',{})
    assert path.read_bytes()==original+b'EXTERNAL_SIMULATION_TAMPER\n'
    report['cases'].append(dict(name='continue_external_tamper_refused',result='PASS',path=str(path),negative_fixture=True))
    op('reset');call('/sim/manual',{})
    report['status']='PASS'
    (HERE/'host-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
