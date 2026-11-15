"""Thread-safety regression tests; no hardware or COM operations."""
import importlib.util
from pathlib import Path
import threading
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'apps/gld-operator'))
spec = importlib.util.spec_from_file_location('registry_test_bridge', ROOT/'apps/gld-operator/bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

class RegistryTests(unittest.TestCase):
    def setUp(self):
        with bridge.serial_bridges_lock:
            bridge.serial_bridges.clear()

    def test_concurrent_first_access_publishes_single_bridge(self):
        entered, release, second_started, second_constructor = (threading.Event() for _ in range(4))
        instances, results, failures = [], [], []
        original = bridge.SerialBridge
        def make(*args, **kwargs):
            instance = original(*args, **kwargs)
            instances.append(instance)
            if len(instances) > 1: second_constructor.set()
            entered.set()
            if not release.wait(2): raise RuntimeError('fixture timeout')
            return instance
        def get(mark=False):
            try:
                if mark: second_started.set()
                results.append(bridge.get_serial_bridge(3))
            except Exception as exc: failures.append(exc)
        with mock.patch.object(bridge, 'SerialBridge', side_effect=make):
            one=threading.Thread(target=get, daemon=True); one.start()
            self.assertTrue(entered.wait(1))
            two=threading.Thread(target=get, args=(True,), daemon=True); two.start()
            self.assertTrue(second_started.wait(1))
            try:
                self.assertFalse(second_constructor.wait(0.2), 'duplicate constructor entered')
                self.assertEqual(len(instances), 1)
            finally:
                release.set(); one.join(2); two.join(2)
        self.assertFalse(one.is_alive() or two.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(len(instances), 1)
        self.assertEqual(len(results), 2)
        self.assertIs(results[0], results[1])
        self.assertIs(results[0], bridge.serial_bridges_snapshot()[3])

    def test_snapshot_is_stable_and_calls_do_not_hold_registry_lock(self):
        first=bridge.get_serial_bridge(1)
        old=bridge.serial_bridges_snapshot()
        second=bridge.get_serial_bridge(2)
        self.assertEqual(list(old), [1])
        self.assertIs(old[1], first)
        self.assertIs(bridge.serial_bridges_snapshot()[2], second)
        # A status callback may create a new slot; it must not deadlock or
        # invalidate the iteration in connected_slots_summary.
        first.status=lambda: (bridge.get_serial_bridge(4), {'connected': True, 'port': 'COM999'})[1]
        result=[]
        thread=threading.Thread(target=lambda: result.append(bridge.connected_slots_summary()), daemon=True)
        thread.start(); thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result[0]['1']['port'], 'COM999')
        self.assertIn(4, bridge.serial_bridges_snapshot())

    def test_gld1_disconnected_and_slot_isolation(self):
        one=bridge.get_serial_bridge(1); two=bridge.get_serial_bridge(2)
        self.assertIsNot(one, two)
        self.assertFalse(one.status()['connected'])
        self.assertTrue(one.write_line('GET_INFO', require_connected=False)['skipped'])
        self.assertEqual(bridge.connected_slots_summary(), {})
        self.assertIsNone(bridge.slot_holding_port('COM999'))

if __name__ == '__main__': unittest.main()
