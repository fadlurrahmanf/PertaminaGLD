"""Negative controls ensure evidence validator rejects changed sensor tuples."""
import csv
import io
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from csv_evidence import validate_csv, CSV_HEADERS, FEATURE_ORDER


class NegativeControls(unittest.TestCase):
    def test_changed_each_sensor_dimension_and_order_is_rejected(self):
        original = dict(device_id='SIM', session_id='synthetic', seq=0, timestamp_ms=1000,
            scan_end_ms=1230, mode='DATASET', label='synthetic', nulling_profile_id=1,
            overrun_count=0, feature_order=FEATURE_ORDER,
            sensor_voltage=[.1 + index/100 for index in range(8)], sensor_gain=[1]*8, sensor_status=[0]*8)
        row = {key: str(original[key]) for key in CSV_HEADERS if key in original and key != 'feature_order'}
        row['feature_order'] = '|'.join(FEATURE_ORDER)
        for index, feature in enumerate(FEATURE_ORDER):
            row['voltage_' + feature] = original['sensor_voltage'][index]
            row['gain_' + feature] = 1
            row['status_' + feature] = 0
        def check(value):
            stream = io.StringIO()
            writer = csv.DictWriter(stream, CSV_HEADERS)
            writer.writeheader()
            writer.writerow(value)
            return validate_csv(stream.getvalue(), device_id='SIM', session_id='synthetic',
                                profile_id=1, originals=[original])
        self.assertEqual(check(row)['count'], 1)
        for key, value in [('voltage_MQ8', .9), ('gain_MQ135', 2), ('status_MQ3', 1),
                           ('timestamp_ms', 999), ('seq', 1), ('feature_order', 'wrong')]:
            with self.subTest(changed=key), self.assertRaises(AssertionError):
                check(dict(row, **{key: value}))


if __name__ == '__main__':
    unittest.main()
