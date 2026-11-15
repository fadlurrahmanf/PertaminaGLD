"""Run the real bridge serial/poller integration using only a fake serial wire."""
import importlib.util
import http.client
import json
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('gld_poll_bridge', ROOT / 'bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

class Wire:
    is_open = True
    def __init__(self): self.writes, self.event = [], threading.Event()
    def write(self, data): self.writes.append(data.decode().strip()); self.event.set()
    def flush(self): pass
    def close(self): self.is_open = False

class PollBridge(unittest.TestCase):
    def test_overflowed_event_client_is_unregistered_for_reconnect(self):
        hub = bridge.EventHub(); client = hub.add()
        for i in range(500): hub.emit('serial_line', {'value':i})
        self.assertTrue(hub.registered(client))
        hub.emit('serial_line', {'value':500})
        self.assertFalse(hub.registered(client))

    def test_stale_reader_cannot_satisfy_new_connection_request(self):
        serial = bridge.SerialBridge(bridge.EventHub())
        wire = Wire(); serial._serial = wire; serial._generation = 2
        token = serial._poll_gate.reserve('GET_TELEMETRY')
        self.assertIsNone(serial._record_line('GLD_TELEMETRY_JSON {}', 1, wire))
        self.assertEqual(serial._poll_gate.pending_response(), 'telemetry')
        self.assertEqual(serial.telemetry_replay(0, '')['samples'], [])
        serial._poll_gate.cancel_unsent(token)
        serial.disconnect()

    def test_old_watchdog_cannot_disable_new_connection_poll(self):
        serial = bridge.SerialBridge(bridge.EventHub())
        serial._serial = Wire(); serial._poll_enabled = True
        old = serial._poll_gate.reserve('GET_STATUS'); epoch = serial._poll_gate.epoch()
        serial._poll_gate.reset()
        new = serial._poll_gate.reserve('GET_TELEMETRY')
        serial._watch_external_poll_gate(old, 'GET_STATUS', epoch)
        self.assertTrue(serial._poll_enabled)
        self.assertEqual(serial._poll_gate.pending_response(), 'telemetry')
        serial._poll_gate.cancel_unsent(new); serial.disconnect()

    def test_old_stop_cannot_disable_new_owner(self):
        serial = bridge.SerialBridge(bridge.EventHub())
        serial._serial = Wire(); serial._poll_enabled = True; serial._poll_version = 1
        class RacingPoller:
            def stop(self, _owner): return True
            def stop_for_disconnect(self): pass
            def join(self, _timeout):
                with serial._poll_lock:
                    serial._poll_version += 1
                    serial._poll_enabled = True
                return True
        serial._poller = RacingPoller()
        self.assertTrue(serial.stop_background_poll('owner-session-123456')['ok'])
        self.assertTrue(serial._poll_enabled)
        serial.disconnect()

    def test_stop_before_delayed_start_cannot_restart_poller(self):
        serial = bridge.SerialBridge(bridge.EventHub())
        serial._serial = Wire()
        owner = 'owner-session-123456'
        serial.stop_background_poll(owner)
        with self.assertRaisesRegex(RuntimeError, 'already stopped'):
            serial.start_background_poll(owner, 200, serial._telemetry_stream)
        self.assertEqual(serial._serial.writes, [])
        serial.disconnect()

    def test_other_owner_cannot_take_over_or_stop_polling(self):
        serial = bridge.SerialBridge(bridge.EventHub())
        wire = Wire(); serial._serial = wire
        owner, other = 'owner-session-123456', 'other-session-123456'
        serial.start_background_poll(owner, 200, serial._telemetry_stream)
        self.assertTrue(wire.event.wait(1))
        with self.assertRaisesRegex(RuntimeError, 'another session'):
            serial.start_background_poll(other, 200, serial._telemetry_stream)
        with self.assertRaisesRegex(RuntimeError, 'another session'):
            serial.stop_background_poll(other)
        serial._record_line('GLD_TELEMETRY_JSON {}')
        self.assertTrue(serial.stop_background_poll(owner)['ok'])
        serial.disconnect()

    def test_poll_cannot_attach_to_a_different_connection(self):
        serial = bridge.SerialBridge(bridge.EventHub())
        serial._serial = Wire()
        with self.assertRaisesRegex(RuntimeError, 'connection changed'):
            serial.start_background_poll('owner-session-123456', 200, 'stale-stream')
        self.assertEqual(serial._serial.writes, [])
        serial.disconnect()

    def test_stop_cancels_start_waiting_for_existing_command(self):
        serial = bridge.SerialBridge(bridge.EventHub())
        wire = Wire(); serial._serial = wire
        serial.write_line('GET_STATUS')
        owner = 'owner-session-123456'; errors = []
        def start():
            try: serial.start_background_poll(owner, 200, serial._telemetry_stream)
            except Exception as error: errors.append(error)
        thread = threading.Thread(target=start); thread.start()
        time.sleep(.05)
        serial.stop_background_poll(owner)
        thread.join(1)
        self.assertFalse(thread.is_alive()); self.assertIn('already stopped', str(errors[0]))
        self.assertEqual(wire.writes, ['GET_STATUS'])
        serial.disconnect()

    def test_existing_request_ownership_and_no_overlap(self):
        serial = bridge.SerialBridge(bridge.EventHub())
        wire = Wire(); serial._serial = wire
        owner = 'owner-session-123456'
        serial.write_line('GET_STATUS')
        wire.event.clear()
        starts, failures = [], []
        def start():
            try: starts.append(serial.start_background_poll(owner, 200, serial._telemetry_stream))
            except Exception as error: failures.append(error)
        starter = threading.Thread(target=start); starter.start()
        self.assertFalse(wire.event.wait(.05), 'poll must wait for existing operator request')
        serial._record_line('GLD_STATUS_JSON {}')
        starter.join(1); self.assertFalse(starter.is_alive()); self.assertFalse(failures)
        self.assertTrue(starts[0]['ok'])
        self.assertTrue(wire.event.wait(1))
        self.assertEqual(wire.writes[-1], 'GET_TELEMETRY')
        errors = []
        thread = threading.Thread(target=lambda: self._write(serial, errors))
        thread.start()
        self.assertNotIn('SET_MODE inference', wire.writes)
        serial._record_line('GLD_TELEMETRY_JSON {}')
        thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors)
        self.assertEqual(wire.writes[-1], 'SET_MODE inference')
        serial._record_line('GLD_CMD_ACK_JSON {"cmd":"SET_MODE"}')
        serial.stop_background_poll(owner)
        serial.disconnect()

    def test_priority_cancel_is_not_blocked_by_missing_poll_response(self):
        serial = bridge.SerialBridge(bridge.EventHub())
        wire = Wire(); serial._serial = wire
        serial.start_background_poll('owner-session-123456', 200, serial._telemetry_stream)
        self.assertTrue(wire.event.wait(1))
        start = time.monotonic()
        serial.write_line('CANCEL_FULLSCALE_SWEEP')
        self.assertLess(time.monotonic() - start, 1)
        self.assertEqual(wire.writes[-1], 'CANCEL_FULLSCALE_SWEEP')
        time.sleep(.25)
        self.assertEqual(wire.writes, ['GET_TELEMETRY', 'CANCEL_FULLSCALE_SWEEP'])
        serial.disconnect()

    def test_priority_cancel_preempts_operator_waiting_on_poll(self):
        serial = bridge.SerialBridge(bridge.EventHub())
        wire = Wire(); serial._serial = wire
        serial.start_background_poll('owner-session-123456', 200, serial._telemetry_stream)
        self.assertTrue(wire.event.wait(1))
        errors = []
        thread = threading.Thread(target=lambda: self._write(serial, errors)); thread.start()
        deadline = time.monotonic() + 1
        while not serial._poll_gate._priority_waiters and time.monotonic() < deadline: time.sleep(.001)
        self.assertEqual(serial._poll_gate._priority_waiters, 1)
        start = time.monotonic(); serial.write_line('CANCEL_FULLSCALE_SWEEP')
        self.assertLess(time.monotonic() - start, 1)
        thread.join(1); self.assertFalse(thread.is_alive()); self.assertTrue(errors)
        self.assertEqual(wire.writes, ['GET_TELEMETRY', 'CANCEL_FULLSCALE_SWEEP'])
        serial.disconnect()

    def test_missing_poll_response_does_not_block_unrelated_operator_command(self):
        serial = bridge.SerialBridge(bridge.EventHub())
        wire = Wire(); serial._serial = wire
        serial._poller._response_timeout = .05
        serial.start_background_poll('owner-session-123456', 200, serial._telemetry_stream)
        deadline = time.monotonic() + 1
        while serial._poll_enabled and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(serial._poll_enabled)
        serial.write_line('GET_STATUS')
        self.assertEqual(wire.writes[-1], 'GET_STATUS')
        with self.assertRaisesRegex(RuntimeError, 'unresolved'):
            serial.write_line('GET_TELEMETRY')
        serial._record_line('GLD_STATUS_JSON {}')
        serial._record_line('GLD_TELEMETRY_JSON {}')
        serial.write_line('GET_TELEMETRY')
        self.assertEqual(wire.writes[-1], 'GET_TELEMETRY')
        with self.assertRaisesRegex(RuntimeError, 'reconnect'):
            serial.start_background_poll('another-owner-123456', 200, serial._telemetry_stream)
        serial.disconnect()

    def test_stop_does_not_release_an_inflight_operator_command(self):
        serial = bridge.SerialBridge(bridge.EventHub())
        wire = Wire(); serial._serial = wire
        owner = 'owner-session-123456'
        serial.start_background_poll(owner, 200, serial._telemetry_stream)
        self.assertTrue(wire.event.wait(1))
        serial._record_line('GLD_TELEMETRY_JSON {}')
        serial.write_line('GET_STATUS')
        with self.assertRaisesRegex(RuntimeError, 'unresolved'):
            serial.stop_background_poll(owner)
        self.assertEqual(serial._poll_gate.pending_response(), 'status')
        serial._record_line('GLD_STATUS_JSON {}')
        self.assertTrue(serial.stop_background_poll(owner)['ok'])
        serial.disconnect()

    def test_json_ack_and_trailing_status_are_serialized(self):
        serial = bridge.SerialBridge(bridge.EventHub())
        wire = Wire(); serial._serial = wire; owner = 'owner-session-123456'
        serial.start_background_poll(owner, 200, serial._telemetry_stream)
        self.assertTrue(wire.event.wait(1)); serial._record_line('GLD_TELEMETRY_JSON {}')
        serial.write_line('SET_ALARM_MODE_JSON {"mode":"auto"}')
        serial._record_line('GLD_CMD_ACK_JSON {"cmd":"SET_ALARM_MODE","status":"ok"}')
        errors=[]
        def read_status():
            try: serial.write_line('GET_STATUS')
            except Exception as error: errors.append(error)
        waiter=threading.Thread(target=read_status); waiter.start()
        time.sleep(.05); self.assertNotIn('GET_STATUS', wire.writes)
        serial._record_line('GLD_STATUS_JSON {}')
        waiter.join(1); self.assertFalse(waiter.is_alive()); self.assertFalse(errors)
        self.assertEqual(wire.writes[-1], 'GET_STATUS')
        serial._record_line('GLD_STATUS_JSON {}')
        serial.stop_background_poll(owner); serial.disconnect()

    def test_poll_and_replay_continue_without_browser_callbacks(self):
        serial = bridge.SerialBridge(bridge.EventHub())
        class AutoWire(Wire):
            def write(self, data):
                super().write(data)
                if data.decode().strip() == 'GET_TELEMETRY':
                    reply = threading.Timer(.01, lambda: serial._record_line('GLD_TELEMETRY_JSON {}'))
                    reply.daemon = True
                    reply.start()
        wire = AutoWire(); serial._serial = wire
        owner = 'owner-session-123456'
        serial.start_background_poll(owner, 200, serial._telemetry_stream)
        time.sleep(.75)
        serial.stop_background_poll(owner)
        replay = serial.telemetry_replay(0, '')
        self.assertGreaterEqual(len(replay['samples']), 3)
        times = [item['receivedMs'] for item in replay['samples']]
        self.assertEqual(times, sorted(times))
        self.assertFalse(replay['truncated'])
        serial.disconnect()

    def test_http_polling_and_replay_on_isolated_loopback(self):
        serial = bridge.SerialBridge(bridge.EventHub())
        class AutoWire(Wire):
            def write(self, data):
                super().write(data)
                if data.decode().strip() == 'GET_TELEMETRY':
                    reply = threading.Timer(.01, lambda: serial._record_line('GLD_TELEMETRY_JSON {}'))
                    reply.daemon = True; reply.start()
        serial._serial = AutoWire()
        original = bridge.serial_bridges.get(1)
        bridge.serial_bridges[1] = serial
        server = bridge.ExclusiveThreadingHTTPServer(('127.0.0.1', 0), bridge.Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        headers = {'X-GLD-Bridge-Token':bridge.BRIDGE_CSRF_TOKEN, 'Content-Type':'application/json'}
        def request(method, path, body=None):
            conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
            response = conn.getresponse(); payload = json.loads(response.read())
            self.assertEqual(response.status, 200, payload)
            return payload
        try:
            status = request('GET', '/api/serial/status?slot=1')
            owner = 'owner-session-http-123'
            request('POST', '/api/serial/poll/start', {'slot':1, 'owner':owner, 'intervalMs':200,
                                                       'stream':status['telemetryStream']})
            time.sleep(.65)  # Browser sends no events or timer callbacks here.
            replay = request('GET', '/api/serial/telemetry-replay?slot=1&after=0')
            self.assertGreaterEqual(len(replay['samples']), 3)
            request('POST', '/api/serial/poll/stop', {'slot':1, 'owner':owner})
        finally:
            conn.close(); server.shutdown(); server.server_close(); worker.join(2); serial.disconnect()
            if original is None: bridge.serial_bridges.pop(1, None)
            else: bridge.serial_bridges[1] = original

    def test_many_operator_requests_never_overlap_background_poll(self):
        serial = bridge.SerialBridge(bridge.EventHub())
        class AutoWire(Wire):
            def __init__(self): super().__init__(); self.lock=threading.Lock(); self.inflight=0; self.overlap=False
            def write(self, data):
                command=data.decode().strip()
                with self.lock:
                    self.overlap |= self.inflight != 0
                    self.inflight += 1
                super().write(data)
                def reply():
                    with self.lock: self.inflight -= 1
                    serial._record_line('GLD_TELEMETRY_JSON {}' if command == 'GET_TELEMETRY' else 'GLD_STATUS_JSON {}')
                timer=threading.Timer(.02, reply); timer.daemon=True; timer.start()
        wire=AutoWire(); serial._serial=wire; owner='owner-session-123456'
        serial.start_background_poll(owner, 200, serial._telemetry_stream)
        errors=[]
        def write():
            try: serial.write_line('GET_STATUS')
            except Exception as error: errors.append(error)
        threads=[threading.Thread(target=write) for _ in range(20)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(6)
        self.assertFalse(any(thread.is_alive() for thread in threads)); self.assertFalse(errors)
        deadline=time.monotonic()+2
        while not serial._poll_gate.is_idle() and time.monotonic()<deadline: time.sleep(.01)
        serial.stop_background_poll(owner)
        self.assertFalse(wire.overlap, 'two serial requests overlapped')
        serial.disconnect()

    def test_stopping_one_slot_does_not_stop_another_slot(self):
        first = bridge.SerialBridge(bridge.EventHub(), slot=1)
        second = bridge.SerialBridge(bridge.EventHub(), slot=2)
        class AutoWire(Wire):
            def __init__(self, serial): super().__init__(); self.serial=serial
            def write(self, data):
                super().write(data)
                if data.decode().strip() == 'GET_TELEMETRY':
                    reply = threading.Timer(.01, lambda: self.serial._record_line('GLD_TELEMETRY_JSON {}'))
                    reply.daemon=True; reply.start()
        one, two = AutoWire(first), AutoWire(second)
        first._serial=one; second._serial=two
        owner1, owner2 = 'first-owner-123456', 'second-owner-123456'
        try:
            first.start_background_poll(owner1, 200, first._telemetry_stream)
            second.start_background_poll(owner2, 200, second._telemetry_stream)
            time.sleep(.55); first.stop_background_poll(owner1)
            before=len(two.writes); time.sleep(.45)
            self.assertGreater(len(two.writes), before)
            second.stop_background_poll(owner2)
        finally:
            first.disconnect(); second.disconnect()
    @staticmethod
    def _write(serial, errors):
        try: serial.write_line('SET_MODE inference')
        except Exception as error: errors.append(error)

if __name__ == '__main__': unittest.main()

