"""Independent verifier negative controls; files only, no services/network."""
import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("replay_evidence_verifier", Path(__file__).with_name("verify_evidence.py"))
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class VerifierTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.audit = []
        self.evidence = dict(schema="gld-replay-e2e/2", mode="pc-simulation", acquisition_clock="virtual-controlled",
            endpoint=dict(host="127.0.0.1", http_port=61998, ws_port=61999), max_window_seen=8, errors=[],
            sessions=[self.session("clean", 601, True), self.session("overflow", 640, False)], audit=self.audit)

    def tearDown(self):
        self.temporary.cleanup()

    def session(self, sid, count, complete):
        originals = [dict(device_id="1002", session_id=sid, seq=index, timestamp_ms=(index + 1) * 500,
            scan_end_ms=(index + 1) * 500 + 230, mode="DATASET", label=sid, nulling_profile_id=1,
            overrun_count=0, sensor_voltage=[index / 1000 + channel / 10 for channel in range(8)],
            sensor_gain=[1] * 8, sensor_status=[0] * 8, feature_order=validator.FEATURES) for index in range(count)]
        path = self.directory / (sid + ".csv")
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(validator.HEADERS)
            for record in originals:
                writer.writerow([record[key] for key in validator.SCALARS] + record["sensor_voltage"]
                    + record["sensor_gain"] + record["sensor_status"] + ["|".join(validator.FEATURES)])
        commands = [dict(cmd="START_DATASET", command_id="start", session_id=sid),
                    dict(cmd="RESUME_DATASET", command_id="resume", session_id=sid, boot_id="a" * 32, label=sid)]
        messages = []
        if complete:
            commands.append(dict(cmd="STOP_DATASET", command_id="stop", session_id=sid))
            messages.append(dict(type="ack", cmd="STOP_DATASET", command_id="stop", session_id=sid, result="ok"))
        messages.append(dict(type="summary", session_id=sid, total_samples=count, incomplete=not complete))
        for prefix in range(1, count + 1):
            self.audit.extend([dict(kind="fsync", session_id=sid, next_seq=prefix),
                               dict(kind="ack", session_id=sid, next_seq=prefix)])
        return dict(session_id=sid, device_id="1002", boot_id="a" * 32, label=sid, csv_path=str(path),
            original_samples=originals, commands=commands, emitted_messages=messages,
            final_snapshot=dict(session_id=sid, count=count, complete=complete, gap_count=0, duplicate_count=0,
                state="complete" if complete else "incomplete", terminal_reason="" if complete else "buffer_full",
                replayed_count=count), checkpoints=[dict(retained_count=count,
                    snapshot=dict(path=str(path), recovery_active=True))])

    def test_full_positive_negative_evidence_accepted(self):
        self.assertEqual(validator.verify(self.evidence)["status"], "PASS")

    def test_ack_before_fsync_is_rejected(self):
        self.audit[0], self.audit[1] = self.audit[1], self.audit[0]
        with self.assertRaisesRegex(ValueError, "ACK preceded"):
            validator.verify(self.evidence)

    def test_one_changed_original_value_is_rejected(self):
        self.evidence["sessions"][0]["original_samples"][23]["sensor_voltage"][7] = 999
        with self.assertRaisesRegex(ValueError, "voltage changed"):
            validator.verify(self.evidence)

    def test_missing_stop_ack_cannot_certify_clean_completion(self):
        self.evidence["sessions"][0]["emitted_messages"] = self.evidence["sessions"][0]["emitted_messages"][1:]
        with self.assertRaisesRegex(ValueError, "Stop ACK"):
            validator.verify(self.evidence)

    def test_no_full_buffer_checkpoint_is_rejected(self):
        self.evidence["sessions"][1]["checkpoints"] = []
        with self.assertRaisesRegex(ValueError, "full640"):
            validator.verify(self.evidence)


if __name__ == "__main__":
    unittest.main()
