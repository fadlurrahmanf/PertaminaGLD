"""Read-only CSV integrity checks shared by synthetic-wire and real receipts."""
import csv
import hashlib
import io
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'apps/gld-operator'))
from wireless_dataset import CSV_HEADERS, FEATURE_ORDER, VALID_GAINS


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_csv(text, *, device_id, session_id, profile_id, minimum=1, originals=None):
    reader = csv.DictReader(io.StringIO(text))
    assert reader.fieldnames == CSV_HEADERS, 'CSV header/order differs'
    rows = list(reader)
    assert len(rows) >= minimum, 'CSV contains too few rows'
    for seq, row in enumerate(rows):
        assert row['device_id'] == device_id and row['session_id'] == session_id
        assert int(row['seq']) == seq, 'CSV sequence must be contiguous from0'
        assert int(row['nulling_profile_id']) == profile_id
        assert row['feature_order'] == '|'.join(FEATURE_ORDER)
        assert row['mode'] == 'DATASET'
        assert int(row['scan_end_ms']) >= int(row['timestamp_ms'])
        for index, feature in enumerate(FEATURE_ORDER):
            assert math.isfinite(float(row['voltage_' + feature]))
            assert int(row['gain_' + feature]) in VALID_GAINS
            assert 0 <= int(row['status_' + feature]) <= 255
            if originals is not None:
                original = originals[seq]
                assert float(row['voltage_' + feature]) == original['sensor_voltage'][index]
                assert int(row['gain_' + feature]) == original['sensor_gain'][index]
                assert int(row['status_' + feature]) == original['sensor_status'][index]
        if originals is not None:
            original = originals[seq]
            for key in ('device_id', 'session_id', 'seq', 'timestamp_ms', 'scan_end_ms',
                        'mode', 'label', 'nulling_profile_id', 'overrun_count'):
                assert row[key] == str(original[key]), 'Original field differs: ' + key
    times = [int(row['timestamp_ms']) for row in rows]
    deltas = [right - left for left, right in zip(times, times[1:])]
    return dict(count=len(rows), contiguous=True, eight_sensor_fields=True,
        timestamp_delta_min_ms=min(deltas) if deltas else None,
        timestamp_delta_max_ms=max(deltas) if deltas else None,
        timestamp_delta_median_ms=statistics.median(deltas) if deltas else None,
        achieved_hz=(len(rows)-1)*1000/(times[-1]-times[0]) if len(rows)>1 and times[-1]>times[0] else None,
        max_scan_duration_ms=max(int(row['scan_end_ms'])-int(row['timestamp_ms']) for row in rows),
        max_overrun_count=max(int(row['overrun_count']) for row in rows),
        exact_original_fields=originals is not None)
