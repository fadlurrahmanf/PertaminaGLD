import importlib.util
import threading
import time
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('telemetry_polling', Path(__file__).resolve().parents[1] / 'telemetry_polling.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class PollGateTests(unittest.TestCase):
    def test_poll_never_overlaps_command_and_wrong_response_does_not_release(self):
        gate = module.SerialPollGate()
        token = gate.reserve('GET_TELEMETRY')
        self.assertIsNotNone(token)
        self.assertIsNone(gate.reserve('SET_MODE inference'))
        self.assertFalse(gate.observe('GLD_CMD_ACK_JSON {"cmd":"SET_MODE"}'))
        self.assertFalse(gate.observe('GLD_TELEMETRY_JSON {'))
        self.assertIsNone(gate.reserve('GET_STATUS'))
        self.assertTrue(gate.observe('GLD_TELEMETRY_JSON {}'))
        command = gate.reserve('SET_MODE inference')
        self.assertIsNotNone(command)
        self.assertTrue(gate.wait_response(token, 0))
        self.assertFalse(gate.observe('GLD_TELEMETRY_JSON {}'))
        self.assertTrue(gate.observe('GLD_CMD_ACK_JSON {"cmd":"SET_MODE"}'))
        self.assertTrue(gate.wait_response(command, 0))

    def test_timeout_quarantines_until_connection_reset(self):
        gate = module.SerialPollGate()
        token = gate.reserve('GET_TELEMETRY')
        self.assertFalse(gate.wait_response(token, 0))
        self.assertIsNone(gate.reserve('GET_STATUS'))
        gate.reset()
        self.assertIsNotNone(gate.reserve('GET_STATUS'))
        self.assertFalse(gate.fail(token), 'old generation cannot poison new connection')

    def test_ack_followed_by_status_cannot_satisfy_next_request(self):
        gate = module.SerialPollGate()
        token = gate.reserve('SET_SENSOR_POWER_JSON {}')
        self.assertFalse(gate.observe('GLD_CMD_ACK_JSON {"cmd":"SET_SENSOR_POWER","status":"ok"}'))
        self.assertIsNone(gate.reserve('GET_STATUS'))
        self.assertTrue(gate.observe('GLD_STATUS_JSON {}'))
        self.assertTrue(gate.wait_response(token, 0))
        next_token = gate.reserve('GET_STATUS')
        self.assertIsNotNone(next_token)
        self.assertFalse(gate.wait_response(next_token, 0))

    def test_rejected_ack_does_not_wait_for_status(self):
        gate = module.SerialPollGate()
        token = gate.reserve('SET_ALARM_MODE_JSON {}')
        self.assertTrue(gate.observe('GLD_CMD_ACK_JSON {"cmd":"SET_ALARM_MODE","status":"rejected"}'))
        self.assertTrue(gate.wait_response(token, 0))

    def test_waiter_receives_wire_only_after_reply(self):
        gate = module.SerialPollGate()
        gate.reserve('GET_TELEMETRY')
        result = []
        thread = threading.Thread(target=lambda: result.append(gate.reserve('GET_STATUS', 1)))
        thread.start()
        self.assertTrue(gate.observe('GLD_TELEMETRY_JSON {}'))
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertIsNotNone(result[0])
        self.assertEqual(module.response_kind('GLD_CMD_ACK_JSON not-json'), None)
        self.assertEqual(module.expected_response('RUN_CURRENT_STATE_CHECK'), 'current-state-done')
        self.assertEqual(module.expected_response('SET_SENSOR_POWER_JSON {}'), 'ack:SET_SENSOR_POWER')
        with self.assertRaises(ValueError):
            module.expected_response('  ')

    def test_waiting_operator_has_priority_and_reset_cancels_waiter(self):
        gate = module.SerialPollGate()
        gate.reserve('GET_TELEMETRY')
        results = []
        thread = threading.Thread(target=lambda: results.append(gate.reserve('GET_STATUS', 1)))
        thread.start()
        deadline = time.monotonic() + 1
        while not gate._priority_waiters and time.monotonic() < deadline: time.sleep(.001)
        self.assertEqual(gate._priority_waiters, 1)
        self.assertIsNone(gate.reserve('GET_TELEMETRY'))
        gate.reset()
        thread.join(1)
        self.assertEqual(results, [None])
        self.assertTrue(gate.is_idle())

    def test_background_owner_waits_for_operator_and_stops(self):
        gate = module.SerialPollGate()
        operator = gate.reserve('SET_MODE inference')
        wrote = threading.Event()
        calls = []
        def write(command):
            calls.append(command)
            wrote.set()
            gate.observe('GLD_TELEMETRY_JSON {}')
        poller = module.BackgroundTelemetryPoller(gate, write, response_timeout=.5)
        owner = 'owner-session-123456'
        poller.start(owner, 200)
        self.assertFalse(wrote.wait(.1), 'must not poll while operator owns wire')
        with self.assertRaises(RuntimeError):
            poller.start('different-owner-12345', 200)
        gate.observe('GLD_CMD_ACK_JSON {"cmd":"SET_MODE"}')
        self.assertTrue(gate.wait_response(operator, 0))
        self.assertTrue(wrote.wait(.8))
        poller.stop(owner)
        count = len(calls)
        time.sleep(.25)
        self.assertEqual(len(calls), count)

    def test_timeout_stops_polling_until_new_connection(self):
        gate = module.SerialPollGate()
        error = threading.Event()
        writes = []
        poller = module.BackgroundTelemetryPoller(gate, writes.append,
                                                   lambda _message: error.set(), .05)
        poller.start('owner-session-123456', 200)
        self.assertTrue(error.wait(1))
        self.assertEqual(writes, ['GET_TELEMETRY'])
        self.assertTrue(gate.is_quarantined())
        self.assertIsNone(gate.reserve('GET_STATUS'))

    def test_replay_reports_loss_and_preserves_received_timestamps(self):
        replay = module.TelemetryReplayBuffer(max_items=2)
        for timestamp in (1000, 1500, 2000):
            replay.append('GLD_TELEMETRY_JSON {}', timestamp)
        result = replay.after(0)
        self.assertTrue(result['truncated'])
        self.assertEqual(result['sequence'], 3)
        self.assertEqual([s['receivedMs'] for s in result['samples']], [1500, 2000])
        self.assertFalse(replay.after(1)['truncated'])
        self.assertEqual(len(replay.after(2)['samples']), 1)
        with self.assertRaises(ValueError): replay.after(4)
        with self.assertRaises(ValueError): replay.append('GLD_TELEMETRY_JSON {', 2500)

if __name__ == '__main__': unittest.main()
