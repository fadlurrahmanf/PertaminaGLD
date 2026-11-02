"""Bounded host-only regression for Windows evidence reader contention."""
import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("fixture_persistence_test", Path(__file__).with_name("serve_simulation.py"))
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)


@unittest.skipUnless(os.name == "nt", "reproduces Windows file replacement sharing rules")
class Persistence(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        fixture.EVIDENCE = Path(self.directory.name) / "evidence.json"
        fixture.evidence = fixture.Evidence()
        fixture.evidence.save()

    def tearDown(self):
        self.directory.cleanup()

    def test_held_reader_is_diagnostic_and_next_write_recovers(self):
        with fixture.EVIDENCE.open("r", encoding="utf-8"):
            result = fixture.evidence.save()
        self.assertEqual(result["diagnostic_counts"]["evidence_persistence:PermissionError"], 1)
        recovered = fixture.evidence.save()
        self.assertEqual(json.loads(fixture.EVIDENCE.read_text(encoding="utf-8")), recovered)

    def test_evidence_failure_does_not_abort_synthetic_sample_transport(self):
        fixture.evidence.begin(dict(label="persistence_regression", session_id="test_session"))
        class Connection:
            count = 0
            def sendall(self, _frame):
                self.count += 1
        peer = object.__new__(fixture.FakeDevice)
        peer.connection = Connection()
        peer.seq = 0
        peer.base_ms = 0
        peer.next_due = time.monotonic()
        peer.session_id = "test_session"
        peer.label = "persistence_regression"
        with fixture.EVIDENCE.open("r", encoding="utf-8"):
            for _ in range(6):
                peer.sample()
                fixture.evidence.save()
        result = fixture.evidence.save()
        self.assertEqual(peer.seq, 6)
        self.assertEqual(peer.connection.count, 6)
        self.assertEqual(len(result["sessions"][0]["emitted_samples"]), 6)
        self.assertEqual(result["diagnostic_counts"]["evidence_persistence:PermissionError"], 6)
        self.assertEqual(json.loads(fixture.EVIDENCE.read_text(encoding="utf-8")), result)


if __name__ == "__main__":
    unittest.main()
