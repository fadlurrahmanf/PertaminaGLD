"""Negative controls for the independent evidence verifier; no networking."""
import copy
import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("verify_evidence", Path(__file__).with_name("verify_evidence.py"))
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class VerifierTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.evidence = {"schema": "gld-dataset-e2e/1", "mode": "pc-simulation",
                         "endpoint": {"host": "127.0.0.1", "http_port": 35921, "ws_port": 35922},
                         "sessions": [self.session("clean"), self.session("drop")]}

    def tearDown(self):
        self.temporary.cleanup()

    def session(self, name):
        session_id = name + "-session"
        samples = [dict(type="sample", device_id="1001", session_id=session_id,
                        seq=index, timestamp_ms=1000 + index * 500,
                        scan_end_ms=1100 + index * 500, mode="DATASET", label=name,
                        nulling_profile_id=5, overrun_count=0,
                        sensor_voltage=[(index + channel) / 100 for channel in range(8)],
                        sensor_gain=[1] * 8, sensor_status=[0] * 8,
                        feature_order=validator.FEATURES) for index in range(4)]
        path = self.directory / (name + ".csv")
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(validator.HEADERS)
            for row in samples:
                writer.writerow([row[key] for key in validator.SCALARS] + row["sensor_voltage"]
                                + row["sensor_gain"] + row["sensor_status"]
                                + ["|".join(validator.FEATURES)])
        start = dict(cmd="START_DATASET", session_id=session_id, command_id="start-id",
                     sample_interval_ms=500)
        commands = [start]
        messages = [dict(type="ack", result="ok", cmd="START_DATASET", command_id="start-id",
                         session_id=session_id), dict(type="status", state="running", session_id=session_id)] + samples
        summary = None
        snapshot = dict(session_id=session_id, count=4, duplicate_count=0, gap_count=0,
                        connected=name == "clean", state="complete" if name == "clean" else "incomplete",
                        complete=name == "clean", total_samples=4 if name == "clean" else None)
        if name == "clean":
            commands.append(dict(cmd="STOP_DATASET", session_id=session_id, command_id="stop-id"))
            summary = dict(type="summary", session_id=session_id, total_samples=4, incomplete=False)
            messages.extend([dict(type="ack", result="ok", cmd="STOP_DATASET", command_id="stop-id",
                                  session_id=session_id), summary])
            checkpoints = [dict(name=point, host_monotonic_s=moment,
                                snapshot=dict(session_id=session_id, connected=True,
                                              state="recording", count=count))
                           for point, moment, count in [("before_browser_close", 1.0, 1),
                                                        ("after_browser_reopen", 2.5, 3)]]
        else:
            checkpoints = [dict(name=point, host_monotonic_s=moment, snapshot=copy.deepcopy(snapshot))
                           for point, moment in [("after_drop", 3.0), ("after_drop_wait", 4.5)]]
        return dict(name=name, device_id="1001", session_id=session_id, label=name,
                    csv_path=str(path), emitted_samples=samples, emitted_messages=messages,
                    commands=commands, summary=summary, final_snapshot=snapshot,
                    checkpoints=checkpoints, arrival_monotonic_s=[1, 1.51, 2.01, 2.5])

    def test_good_evidence_and_host_jitter_are_accepted(self):
        self.assertEqual(validator.verify(self.evidence, self.directory)["status"], "PASS")

    def test_one_wrong_sensor_value_rejected(self):
        path = Path(self.evidence["sessions"][0]["csv_path"])
        path.write_text(path.read_text().replace(",0.07,", ",9.07,", 1), encoding="utf-8")
        with self.assertRaisesRegex(validator.EvidenceError, "voltage differs"):
            validator.verify(self.evidence, self.directory)

    def test_fabricated_total_rejected(self):
        self.evidence["sessions"][0]["summary"]["total_samples"] = 5
        with self.assertRaisesRegex(validator.EvidenceError, "total/emitted/CSV differ"):
            validator.verify(self.evidence, self.directory)

    def test_protocol_ack_order_rejected(self):
        messages = self.evidence["sessions"][0]["emitted_messages"]
        messages[0], messages[2] = messages[2], messages[0]
        with self.assertRaisesRegex(validator.EvidenceError, "ACK/running status"):
            validator.verify(self.evidence, self.directory)

    def test_missing_browser_continuity_rejected(self):
        self.evidence["sessions"][0]["checkpoints"] = []
        with self.assertRaisesRegex(validator.EvidenceError, "browser-close/reopen"):
            validator.verify(self.evidence, self.directory)

    def test_recording_after_drop_rejected(self):
        self.evidence["sessions"][1]["checkpoints"][1]["snapshot"]["count"] = 5
        with self.assertRaisesRegex(validator.EvidenceError, "recording changed"):
            validator.verify(self.evidence, self.directory)

    def test_protected_production_port_rejected(self):
        self.evidence["endpoint"]["http_port"] = 5174
        with self.assertRaisesRegex(validator.EvidenceError, "Unsafe simulation port"):
            validator.verify(self.evidence, self.directory)


if __name__ == "__main__":
    unittest.main()
