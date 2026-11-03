"""Independent wire→canonical→CSV mapping; never imports production projector."""
import math
import re
from datetime import datetime
from wire_peer import FEATURE_ORDER

PREDICTION_FIELDS=('enabled','status','valid','predicted_class','gas_class','confidence','inference_duration_ms')

def canonical_matches(entry, original):
    for key,value in original.items():
        if key!='type': assert entry[key]==value, 'Canonical field differs: '+key
    if entry.get('private_cleanup'):
        assert entry['row_id'] is None, 'Quarantine must not claim a public row ID'
    else:
        assert type(entry['row_id']) is int and entry['row_id']>=0
    assert type(entry['segment_id']) is int and entry['segment_id']>=1
    assert isinstance(entry['boot_id'],str) and len(entry['boot_id'])==32
    stamp=entry['label_timestamp'];assert re.fullmatch(r'\d{2}:\d{2} (Senin|Selasa|Rabu|Kamis|Jumat|Sabtu|Minggu) \d{2}/\d{2}/\d{2}',stamp)
    clock,day,date=stamp.split(' ');parsed=datetime.strptime(clock+' '+date,'%H:%M %d/%m/%y');assert day==('Senin','Selasa','Rabu','Kamis','Jumat','Sabtu','Minggu')[parsed.weekday()]
    assert entry['display_label']==stamp+' '+original['label']
    prediction=entry['prediction']
    if prediction['valid']:
        assert prediction['status']=='valid' and prediction['enabled']
        assert 0<=prediction['confidence']<=1 and math.isfinite(prediction['confidence'])
        model=entry['model'];index=prediction['predicted_class']
        assert type(index) is int and 0<=index<model['output_elements']
        assert prediction['gas_class']==model['class_map'][index]
    else:
        assert all(prediction[key] is None for key in ('predicted_class','gas_class','confidence'))


def public_matches(row, entry):
    assert all('voltage_'+name in row for name in FEATURE_ORDER)
    assert 'timestamp_ms' in row
    for prefix in ('gain','status'):
        present=[prefix+'_'+name in row for name in FEATURE_ORDER]
        assert all(present) or not any(present), 'Partial sensor metadata projection'
    prediction_present=['prediction_'+name in row for name in PREDICTION_FIELDS]
    assert all(prediction_present) or not any(prediction_present)
    for key,cell in row.items():
        if key.startswith(('voltage_','gain_','status_')):
            prefix,feature=key.split('_',1)
            source={'voltage':'sensor_voltage','gain':'sensor_gain','status':'sensor_status'}[prefix]
            expected=entry[source][FEATURE_ORDER.index(feature)]
        elif key.startswith('prediction_'):
            expected=entry['prediction'][key[len('prediction_'):]]
        elif key in ('model_profile_id','scaler_profile_id','runtime_version'):
            expected=entry['model'][{'model_profile_id':'profile_id','scaler_profile_id':'scaler_profile_id','runtime_version':'runtime_version'}[key]]
        elif key=='feature_order': expected='|'.join(entry['feature_order'])
        else:
            assert key in entry, 'Unknown CSV field: '+key
            expected=entry[key]
        if expected is None: assert cell=='', 'Invalid prediction must serialize empty/null'
        elif type(expected) is bool: assert cell==str(expected)
        elif isinstance(expected,float): assert math.isfinite(float(cell)) and float(cell)==expected
        elif type(expected) is int: assert int(cell)==expected
        else: assert cell==str(expected), 'CSV field differs: '+key


def verify_public_rows(rows, canonical_by_key, originals_by_key):
    seen=set();last_segment=0;last_seq={};segment_sids={}
    for index,row in enumerate(rows):
        key=(row['session_id'],int(row['seq']))
        assert key not in seen and key in canonical_by_key and key in originals_by_key
        entry=canonical_by_key[key]
        canonical_matches(entry, originals_by_key[key])
        public_matches(row, entry)
        assert int(row['row_id'])==index
        segment=int(row['segment_id'])
        assert segment in (last_segment,last_segment+1) and segment>=1
        assert segment_sids.setdefault(segment,key[0])==key[0]
        assert key[1]==last_seq.get(key[0],-1)+1
        seen.add(key);last_seq[key[0]]=key[1];last_segment=segment
    return dict(rows=len(rows),segments=last_segment,all_fields_exact=True,
        eight_sensor_values=True,unique_session_seq=True)
