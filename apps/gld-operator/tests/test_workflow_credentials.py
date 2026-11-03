"""Synthetic local configuration only; no actual credentials/network/device."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workflow_credentials import resolve_workflow_password


class PrivateWorkflowCredentials(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.secret = "SYNTHETIC_PRIVATE_ONLY"
        self.paths = []
        for model in (1, 2, 3):
            environment = f"gld_model_{model}_dataset_workflow_wifi"
            path = self.root / "firmware" / ".pio" / "gld-dataset-workflow-wifi" / environment / "credentials.local.json"
            path.parent.mkdir(parents=True)
            value = dict(environment=environment, protocol="gld-dataset-wifi/3", username="gld", password=self.secret,
                address="192.168.4.1", port=81, path="/dataset")
            path.write_text(json.dumps(value), encoding="utf-8")
            self.paths.append(path)

    def tearDown(self):
        self.directory.cleanup()

    def assert_unavailable(self):
        with self.assertRaisesRegex(RuntimeError, "Kredensial hotspot GLD") as error:
            resolve_workflow_password(self.root)
        self.assertNotIn(self.secret, str(error.exception))
        self.assertNotIn(str(self.root), str(error.exception))

    def test_all_three_dedicated_configurations_must_agree_and_are_read_only(self):
        before = {path: path.read_bytes() for path in self.paths}
        self.assertEqual(resolve_workflow_password(self.root), self.secret)
        self.assertEqual({path: path.read_bytes() for path in self.paths}, before)

    def test_missing_model_config_fails_without_guessing_or_creating_files(self):
        self.paths[2].unlink()
        self.assert_unavailable()
        self.assertFalse(self.paths[2].exists())

    def test_conflicting_passwords_fail_before_identity_is_known(self):
        path = self.paths[1]; value = json.loads(path.read_text()); value["password"] = "OTHER_SYNTHETIC_SECRET"
        path.write_text(json.dumps(value)); self.assert_unavailable()

    def test_invalid_json_and_oversize_are_redacted(self):
        path = self.paths[0]; path.write_text(self.secret)
        self.assert_unavailable()
        path.write_text(self.secret * 1000)
        self.assert_unavailable()

    def test_wrong_environment_protocol_or_transport_is_not_used(self):
        path = self.paths[0]; original = json.loads(path.read_text())
        for key, value in (("environment", "gld_model_2_dataset_workflow_wifi"), ("protocol", "gld-dataset-wifi/2"),
                ("username", "other"), ("address", "example.com"), ("port", 1883), ("path", "/other"),
                ("password", "short"), ("port", True)):
            with self.subTest(key=key, value=value):
                altered = dict(original); altered[key] = value
                path.write_text(json.dumps(altered)); self.assert_unavailable()


if __name__ == "__main__":
    unittest.main()
