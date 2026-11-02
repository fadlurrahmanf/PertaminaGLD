"""Actual vendored WebSocket client with synthetic ephemeral-loopback GLD.

No production services, COM ports, device IP connection, firmware or compiler.
The same wire peer powers the isolated browser E2E fixture.
"""
import csv
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
APP = REPO / "apps/gld-operator"
sys.path.insert(0, str(REPO / "tmp/wireless-stage2/e2e"))
sys.path.insert(0, str(APP))
from wire_peer import Engine, PASSWORD
from wireless_dataset_replay import WirelessDatasetReplayCollector


def eventually(predicate, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("bounded loopback condition timed out")


class ReplayWireTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = Engine()
        self.engine.auto_capture = False
        self.collector = WirelessDatasetReplayCollector(self.directory.name,
            websocket_factory=self.engine.factory, fsync=self.engine.fsync,
            command_timeout=3, silence_timeout=3)
        self.engine.collector = self.collector

    def tearDown(self):
        self.engine.close()
        self.directory.cleanup()

    def begin(self):
        self.assertEqual(self.collector.connect(PASSWORD)["protocol"], "gld-dataset-wifi/2")
        self.assertEqual(self.collector.start("wire_e2e")["state"], "recording")

    def assert_rows_and_durability(self):
        state = self.collector.snapshot()
        session = self.engine.sessions[state["session_id"]]
        with Path(state["path"]).open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), len(session["original_samples"]))
        self.assertEqual(len(rows), state["count"])
        for row, original in zip(rows, session["original_samples"]):
            for key in ("device_id", "session_id", "seq", "timestamp_ms", "scan_end_ms", "mode",
                        "label", "nulling_profile_id", "overrun_count"):
                self.assertEqual(row[key], str(original[key]))
            for index, feature in enumerate(original["feature_order"]):
                self.assertEqual(float(row["voltage_" + feature]), original["sensor_voltage"][index])
                self.assertEqual(int(row["gain_" + feature]), original["sensor_gain"][index])
                self.assertEqual(int(row["status_" + feature]), original["sensor_status"][index])
            self.assertEqual(row["feature_order"], "|".join(original["feature_order"]))
        durable = 0
        for event in self.engine.audit:
            if event["session_id"] != state["session_id"]:
                continue
            if event["kind"] == "fsync":
                durable = max(durable, event["next_seq"])
            elif event["kind"] == "ack":
                self.assertLessEqual(event["next_seq"], durable, "ACK must follow actual flush/fsync")
        self.assertLessEqual(self.engine.device.max_window_seen, 8)

    def test_real_websocket_normal_stop_summary_and_durable_ack(self):
        self.begin()
        self.engine.capture(4)
        eventually(lambda: self.collector.snapshot()["count"] == 4)
        self.assertTrue(self.collector.stop()["complete"])
        self.assertEqual(self.engine.device.acked, 4)
        self.assert_rows_and_durability()

    def test_actual_tcp_eof_resume_preserves_same_csv_and_original_timestamps(self):
        self.begin()
        self.engine.capture(4)
        eventually(lambda: self.engine.device.acked == 4)
        initial = self.collector.snapshot()
        self.engine.control("drop")
        eventually(lambda: self.collector.snapshot()["recovery_active"])
        self.engine.capture(6)
        self.assertEqual(len(self.engine.device.records), 6)
        self.engine.control("resume")
        eventually(lambda: self.collector.snapshot()["count"] >= 10)
        self.assertTrue(self.collector.stop()["complete"])
        final = self.collector.snapshot()
        self.assertEqual((final["path"], final["session_id"]), (initial["path"], initial["session_id"]))
        commands = self.engine.sessions[initial["session_id"]]["commands"]
        self.assertEqual(sum(command["cmd"] == "START_DATASET" for command in commands), 1)
        self.assertGreaterEqual(sum(command["cmd"] == "RESUME_DATASET" for command in commands), 1)
        self.assertGreaterEqual(final["replayed_count"], 6)
        self.assert_rows_and_durability()


if __name__ == "__main__":
    unittest.main()
