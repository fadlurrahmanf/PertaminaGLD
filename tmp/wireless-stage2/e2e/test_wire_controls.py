"""Bounded synthetic fault controls over real loopback WebSocket transport."""
import csv
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wire_peer import APP, Engine, PASSWORD
sys.path.insert(0, str(APP))
from wireless_dataset_replay import WirelessDatasetReplayCollector


def wait(predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("bounded synthetic wire condition timed out")


class WireControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.engine = Engine()
        self.engine.auto_capture = False
        self.collector = WirelessDatasetReplayCollector(self.temporary.name,
            websocket_factory=self.engine.factory, fsync=self.engine.fsync,
            command_timeout=5, silence_timeout=3)
        self.engine.collector = self.collector
        self.collector.connect(PASSWORD)
        self.collector.start("wire_control_test")

    def tearDown(self):
        self.engine.close()
        self.temporary.cleanup()

    def check_rows(self):
        state = self.collector.snapshot()
        with Path(state["path"]).open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        originals = self.engine.sessions[state["session_id"]]["original_samples"]
        self.assertEqual(len(rows), len(originals))
        for row, original in zip(rows, originals):
            self.assertEqual(int(row["seq"]), original["seq"])
            self.assertEqual(int(row["timestamp_ms"]), original["timestamp_ms"])
            self.assertEqual(int(row["scan_end_ms"]), original["scan_end_ms"])
            for index, feature in enumerate(original["feature_order"]):
                self.assertEqual(float(row["voltage_" + feature]), original["sensor_voltage"][index])

    def test_ack_before_virtual_gap_retains_over_six_hundred_and_resumes_clean(self):
        self.engine.capture(3)
        wait(lambda: self.engine.device.acked == 3)
        original_path = self.collector.path
        self.engine.control("prepare-drop", {"count": 10})
        wait(lambda: self.collector.snapshot()["recovery_active"])
        self.engine.control("gap", {"count": 599})
        self.assertGreater(len(self.engine.device.records), 600)
        self.assertLess(self.engine.clock() - self.engine.device.ack_since, 300)
        self.assertTrue(self.engine.device.sampling)
        self.engine.control("resume")
        try:
            wait(lambda: self.collector.snapshot()["count"] >= 612)
        except AssertionError:
            state = self.collector.snapshot()
            self.fail(str({"state": state["state"], "count": state["count"], "error": state["error"],
                           "total": self.engine.device.total, "acked": self.engine.device.acked,
                           "retained": len(self.engine.device.records), "wire_errors": self.engine.errors,
                           "clock": self.engine.clock(), "ack_since": self.engine.device.ack_since}))
        with self.engine.lock:
            self.engine.auto_capture = False
        wait(lambda: not self.engine.device.records)
        self.assertTrue(self.collector.stop()["complete"])
        self.assertEqual(self.collector.path, original_path)
        self.assertGreaterEqual(self.collector.snapshot()["replayed_count"], 608)
        self.assertLessEqual(self.engine.device.max_window_seen, 8)
        self.check_rows()

    def test_capacity_pressure_retains_exactly_640_and_finishes_incomplete(self):
        self.engine.control("overflow")
        wait(lambda: self.collector.snapshot()["recovery_active"])
        self.assertEqual(len(self.engine.device.records), 640)
        self.assertEqual(min(self.engine.device.records), 0)
        self.assertFalse(self.engine.device.sampling)
        self.engine.control("resume")
        wait(lambda: self.collector.snapshot()["state"] == "incomplete")
        state = self.collector.snapshot()
        self.assertEqual(state["count"], 640)
        self.assertEqual(state["terminal_reason"], "buffer_full")
        self.assertFalse(state["complete"])
        self.check_rows()


if __name__ == "__main__":
    unittest.main()
