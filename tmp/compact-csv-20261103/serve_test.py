"""Real HTTP/SSE/WS/UI; synthetic device/native chooser. No hardware access."""
from pathlib import Path
import sys,importlib.util,copy,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];OLD=ROOT/'tmp/workspace-live-20261103/e2e'
sys.path[:0]=[str(OLD),str(ROOT/'apps/gld-operator')]
spec=importlib.util.spec_from_file_location('compact_http_fixture',OLD/'serve_simulation.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.HERE=HERE;m.OUTPUT=HERE/'output'/time.strftime('%Y%m%dT%H%M%S')
BASE=['Waktu (ms)','Label pengujian','MQ8 (V)','MQ135 (V)','MQ3 (V)','MQ5 (V)','MQ4 (V)','MQ7 (V)','MQ6 (V)','MQ2 (V)','Predicted Class','Confidence']
SENSORS=['MQ8','MQ135','MQ3','MQ5','MQ4','MQ7','MQ6','MQ2']
def public_matches(row,entry):
    expected=list(BASE)
    for group in ('Gain','Status'):
        present=[group+' '+s in row for s in SENSORS];assert all(present) or not any(present)
        if all(present):expected += [group+' '+s for s in SENSORS]
    assert list(row)==expected
    assert int(row['Waktu (ms)'])==entry['timestamp_ms']
    assert row['Label pengujian']==entry['display_label']
    for index,name in enumerate(SENSORS):
        assert float(row[name+' (V)'])==entry['sensor_voltage'][index]
        if 'Gain '+name in row:assert int(row['Gain '+name])==entry['sensor_gain'][index]
        if 'Status '+name in row:assert int(row['Status '+name])==entry['sensor_status'][index]
    p=entry['prediction']
    if p['valid']:
        assert int(row['Predicted Class'])==p['predicted_class']
        assert float(row['Confidence'])==p['confidence']
    else:assert row['Predicted Class']==row['Confidence']==''
def durable_prefix(sid):
    with m.audit_lock:files=copy.deepcopy(m.durable_files)
    canonical={}
    for data in files.values():
        if data['kind']!='.jsonl':continue
        for row in data['rows']:
            if row.get('session_id')==sid:canonical[int(row['seq'])]=row
    originals={s['seq']:s for s in m.engine.sessions.get(sid,{}).get('original_samples',[])}
    for seq,record in canonical.items():m.canonical_matches(record,originals[seq])
    snapshot=m.service.snapshot()
    if snapshot['cleanup_pending'] and snapshot['session_id']==sid:return canonical
    public=files.get(snapshot['csv_path'],{}).get('rows',[])
    eligible={}
    for seq,record in canonical.items():
        index=record['row_id']
        if isinstance(index,int) and index<len(public):public_matches(public[index],record);eligible[seq]=record
    return eligible
m.public_matches=public_matches;m.durable_prefix=durable_prefix
if __name__=='__main__':m.main()
