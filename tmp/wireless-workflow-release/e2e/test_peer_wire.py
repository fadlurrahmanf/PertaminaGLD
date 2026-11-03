"""Protocol3 simulator contract self-tests over actual RFC6455, not backend proof."""
import base64
import csv
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from wire_peer import Engine, PASSWORD, PROTOCOL, FEATURE_ORDER


class PeerWireTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine()
        self.temp = tempfile.TemporaryDirectory()
        self.durable = set()
        self.engine.durability_provider = lambda sid: self.durable
        self.socket = self.engine.factory('ws://192.168.4.1:81/dataset', timeout=2,
            header=['Authorization: Basic ' + base64.b64encode(('gld:' + PASSWORD).encode()).decode()],
            enable_multithread=True, http_no_proxy=['*'], redirect_limit=0)
        self.hello = json.loads(self.socket.recv())
        self.sid = 'c'*32
        self.counter = 0
    def tearDown(self):
        self.socket.close()
        self.engine.close()
        self.temp.cleanup()
    def send(self, kind, **fields):
        self.counter += 1
        command = dict(cmd=kind, command_id=str(self.counter).zfill(32), session_id=self.sid, **fields)
        self.socket.send(json.dumps(command))
        return command
    def until(self, predicate):
        for _ in range(1000):
            value = json.loads(self.socket.recv())
            if predicate(value): return value
        raise AssertionError('No expected frame')
    def start(self, prediction=True):
        self.assertEqual(self.hello['protocol'], PROTOCOL)
        self.send('START_DATASET', label='synthetic_wire', sample_interval_ms=500, prediction_enabled=prediction)
        self.assertEqual(self.until(lambda m:m['type']=='ack')['result'], 'ok')
        self.until(lambda m:m['type']=='status')
    def persist_samples(self, count):
        rows=[]
        for _ in range(count):
            row=self.until(lambda m:m['type']=='sample')
            # Two real files are durable before the peer will accept our ACK.
            for name in ('canonical.jsonl', 'public-projection.jsonl'):
                with (Path(self.temp.name)/name).open('a',encoding='utf-8') as stream:
                    stream.write(json.dumps(row)+'\n');stream.flush();os.fsync(stream.fileno())
            self.durable.add(row['seq'])
            self.socket.send(json.dumps(dict(cmd='ACK_SAMPLES',session_id=self.sid,
                boot_id=self.hello['boot_id'], next_seq=row['seq']+1)))
            rows.append(row)
        return rows
    def test_pause_resume_acquisition_and_nullable_predictions_on_actual_wire(self):
        self.start()
        self.engine.capture(6)
        first=self.persist_samples(6)
        self.assertEqual([r['prediction']['status'] for r in first], ['warmup','warmup','valid','error','valid','not_ready'])
        for row in first:
            if not row['prediction']['valid']:
                self.assertIsNone(row['prediction']['confidence']);self.assertIsNone(row['prediction']['predicted_class'])
        transition=dict(boot_id=self.hello['boot_id'],label='synthetic_wire',nulling_profile_id=1,transition_seq=1)
        pause=self.send('PAUSE_DATASET',**transition)
        self.assertTrue(self.until(lambda m:m['type']=='ack')['paused'])
        self.until(lambda m:m['type']=='status')
        self.engine.control('advance',{'seconds':301})
        self.engine.capture(4)
        self.assertEqual(self.engine.device.total,6)
        self.send('RESUME_DATASET',boot_id=self.hello['boot_id'],label='synthetic_wire',next_seq=6)
        self.assertTrue(self.until(lambda m:m['type']=='ack')['paused'])
        self.assertEqual(self.until(lambda m:m['type']=='status')['state'],'paused')
        self.socket.send(json.dumps(pause))
        self.assertEqual(self.until(lambda m:m['type']=='ack')['detail'],'already_registered')
        self.until(lambda m:m['type']=='status')
        self.send('CONTINUE_DATASET',**dict(transition,transition_seq=2))
        self.assertFalse(self.until(lambda m:m['type']=='ack')['paused'])
        self.until(lambda m:m['type']=='status')
        self.engine.capture(3)
        second=self.persist_samples(3)
        self.assertEqual([r['seq'] for r in second],[6,7,8])
        self.assertGreater(second[0]['timestamp_ms']-first[-1]['timestamp_ms'],300000)
        self.assertEqual(second[0]['prediction']['status'],'warmup')
        self.send('STOP_DATASET')
        self.assertEqual(self.until(lambda m:m['type']=='ack')['result'],'ok')
        summary=self.until(lambda m:m['type']=='summary')
        self.assertEqual(summary['total_samples'],9)
        self.assertFalse(summary['incomplete'])
        self.assertLessEqual(self.engine.device.max_window_seen,8)
        self.assertEqual(len(self.engine.durability_audit),9)
    def test_retention_exact_boundary_stops_without_overwrite(self):
        self.start(False)
        self.engine.control('drop')
        self.engine.capture(599)
        self.assertTrue(self.engine.device.sampling)
        before=list(self.engine.device.records.values())
        self.assertEqual(self.engine.clock()-self.engine.device.ack_since,299.5)
        self.engine.control('advance',{'seconds':.499})
        self.assertTrue(self.engine.device.sampling)
        self.engine.control('advance',{'seconds':.001})
        self.assertEqual(self.engine.clock()-self.engine.device.ack_since,300)
        self.assertFalse(self.engine.device.sampling)
        self.assertEqual(self.engine.device.reason,'retention_limit')
        self.engine.capture(8)
        self.assertEqual(list(self.engine.device.records.values()),before)
    def test_stale_transition_cannot_mutate_later_or_terminal_state(self):
        self.start(False)
        fields=dict(boot_id=self.hello['boot_id'],label='synthetic_wire',nulling_profile_id=1)
        pause=self.send('PAUSE_DATASET',transition_seq=1,**fields)
        self.until(lambda m:m['type']=='ack');self.until(lambda m:m['type']=='status')
        continuation=self.send('CONTINUE_DATASET',transition_seq=2,**fields)
        self.until(lambda m:m['type']=='ack');self.until(lambda m:m['type']=='status')
        self.socket.send(json.dumps(pause))
        self.assertEqual(self.until(lambda m:m['type']=='ack')['result'],'error')
        self.assertTrue(self.engine.device.sampling)
        self.assertEqual(self.engine.device.transition_seq,2)
        self.send('STOP_DATASET');self.until(lambda m:m['type']=='summary')
        self.socket.send(json.dumps(continuation))
        self.assertEqual(self.until(lambda m:m['type']=='ack')['detail'],'already_registered')
        self.assertEqual(self.until(lambda m:m['type']=='status')['state'],'stopped')
        self.assertFalse(self.engine.device.sampling)
    def test_wrong_basic_auth_rejected_before_any_command(self):
        with self.assertRaises(Exception) as caught:
            self.engine.factory('ws://192.168.4.1:81/dataset',timeout=2,
                header=['Authorization: Basic '+base64.b64encode(b'gld:wrong-dummy-only').decode()],
                enable_multithread=True,http_no_proxy=['*'],redirect_limit=0)
        self.assertEqual(getattr(caught.exception,'status_code',None),401)
        self.assertEqual(self.engine.device.commands,[])
    def test_capacity_after_partial_ack_progress_preserves_all_640_records(self):
        self.start(False)
        self.engine.capture(580)
        self.persist_samples(1)
        deadline=time.monotonic()+2
        while self.engine.device.acked!=1 and time.monotonic()<deadline:time.sleep(.005)
        self.assertEqual(self.engine.device.acked,1)
        self.engine.capture(61)
        self.assertFalse(self.engine.device.sampling)
        self.assertEqual(self.engine.device.reason,'buffer_full')
        self.assertEqual(len(self.engine.device.records),640)
        self.assertEqual(sorted(self.engine.device.records),list(range(1,641)))
        before=json.dumps(self.engine.device.records,sort_keys=True)
        self.engine.capture(8)
        self.assertEqual(json.dumps(self.engine.device.records,sort_keys=True),before)
        self.assertLessEqual(self.engine.device.max_window_seen,8)


if __name__=='__main__': unittest.main()
