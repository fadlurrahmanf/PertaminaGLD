"""Synthetic local configuration only; no actual credentials/network/device."""
import json
import hashlib
import importlib.util
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


class PortablePackagedCredentials(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.secret = "SYNTHETIC_PACKAGED_ONLY"
        self.profile = self.root / "apps/gld-operator/workflow-connection-profiles.json"
        self.profile.parent.mkdir(parents=True)
        models = {}
        self.packages = []
        for model in (1, 2, 3):
            environment = f"gld_model_{model}_dataset_workflow_wifi"
            directory = self.root / "apps/operator-hub/firmware-packages" / environment / "latest"
            directory.mkdir(parents=True)
            prefix = f"synthetic-model-{model}\0".encode()
            binary = prefix + self.secret.encode() + b"\0end"
            digest = hashlib.sha256(binary).hexdigest()
            (directory / "firmware.bin").write_bytes(binary)
            manifest = dict(schemaVersion=2, packageType="pertamina-gld-prebuilt-firmware",
                environment=environment, chip="esp32s3", flashFiles=[dict(path="firmware.bin", sha256=digest, size=len(binary))])
            (directory / "manifest.json").write_text(json.dumps(manifest))
            models[environment] = dict(firmwareSha256=digest, passwordOffset=len(prefix), passwordLength=len(self.secret))
            self.packages.append(directory)
        self.profile.write_text(json.dumps(dict(schemaVersion=1, protocol="gld-dataset-wifi/3", models=models)))

    def tearDown(self):
        self.directory.cleanup()

    def assert_unavailable(self):
        with self.assertRaisesRegex(RuntimeError, "Kredensial hotspot GLD") as error:
            resolve_workflow_password(self.root)
        self.assertNotIn(self.secret, str(error.exception))
        self.assertNotIn(str(self.root), str(error.exception))

    def test_clean_checkout_uses_all_three_verified_images_without_writing_files(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertFalse((self.root / "firmware/.pio").exists())
        self.assertEqual(resolve_workflow_password(self.root), self.secret)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.assertNotIn(self.secret, self.profile.read_text())

    def test_tamper_or_missing_image_of_each_model_fails_closed(self):
        for directory in self.packages:
            path = directory / "firmware.bin"
            original = path.read_bytes()
            with self.subTest(directory=directory.name):
                path.write_bytes(original + b"changed")
                self.assert_unavailable()
                path.unlink()
                self.assert_unavailable()
                path.write_bytes(original)

    def test_invalid_reference_offsets_and_schema_fail_without_secret_disclosure(self):
        original = self.profile.read_text()
        for field, value in (("passwordOffset", -1), ("passwordOffset", True), ("passwordOffset", 99999),
                             ("passwordLength", 1), ("passwordLength", True), ("firmwareSha256", "0" * 64)):
            profile = json.loads(original)
            profile["models"]["gld_model_2_dataset_workflow_wifi"][field] = value
            self.profile.write_text(json.dumps(profile))
            self.assert_unavailable()
        for field, value in (("schemaVersion", True), ("protocol", "gld-dataset-wifi/2"), ("models", {})):
            profile = json.loads(original); profile[field] = value
            self.profile.write_text(json.dumps(profile)); self.assert_unavailable()

    def test_wrong_manifest_environment_hash_size_and_duplicate_firmware_fail(self):
        path = self.packages[1] / "manifest.json"; original = path.read_text()
        for key, value in (("environment", "gld_model_1_dataset_workflow_wifi"), ("chip", "other")):
            manifest = json.loads(original); manifest[key] = value
            path.write_text(json.dumps(manifest)); self.assert_unavailable()
        for field, value in (("sha256", "0" * 64), ("size", 1)):
            manifest = json.loads(original); manifest["flashFiles"][0][field] = value
            path.write_text(json.dumps(manifest)); self.assert_unavailable()
        manifest = json.loads(original); manifest["flashFiles"] *= 2
        path.write_text(json.dumps(manifest)); self.assert_unavailable()

    def test_verified_images_with_different_passwords_are_rejected(self):
        directory = self.packages[2]
        binary = (directory / "firmware.bin").read_bytes().replace(self.secret.encode(), b"X" * len(self.secret))
        digest = hashlib.sha256(binary).hexdigest(); (directory / "firmware.bin").write_bytes(binary)
        manifest = json.loads((directory / "manifest.json").read_text()); manifest["flashFiles"][0]["sha256"] = digest
        (directory / "manifest.json").write_text(json.dumps(manifest))
        profile = json.loads(self.profile.read_text()); profile["models"]["gld_model_3_dataset_workflow_wifi"]["firmwareSha256"] = digest
        self.profile.write_text(json.dumps(profile)); self.assert_unavailable()

    def test_existing_private_override_preserved_but_partial_override_never_falls_back(self):
        for i in (1, 2, 3):
            environment = f"gld_model_{i}_dataset_workflow_wifi"
            path = self.root / "firmware/.pio/gld-dataset-workflow-wifi" / environment / "credentials.local.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(dict(environment=environment, protocol="gld-dataset-wifi/3", username="gld",
                password="CUSTOM_PRIVATE_SYNTHETIC", address="192.168.4.1", port=81, path="/dataset")))
            if i < 3:
                self.assert_unavailable()
        self.assertEqual(resolve_workflow_password(self.root), "CUSTOM_PRIVATE_SYNTHETIC")

    def test_release_export_regenerates_profiles_without_serializing_credentials(self):
        repo = Path(__file__).resolve().parents[3]
        tool = repo / "firmware/tools/export_workflow_connection_profiles.py"
        spec = importlib.util.spec_from_file_location("test_profile_export", tool)
        exporter = importlib.util.module_from_spec(spec); spec.loader.exec_module(exporter)
        # The export checker deliberately loads the resolver from the target
        # checkout, so this fixture mirrors a release tree rather than mocks.
        (self.profile.parent / "workflow_credentials.py").write_bytes(
            (repo / "apps/gld-operator/workflow_credentials.py").read_bytes())
        private_before = {}
        for i in (1, 2, 3):
            env = f"gld_model_{i}_dataset_workflow_wifi"
            path = self.root / "firmware/.pio/gld-dataset-workflow-wifi" / env / "credentials.local.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(dict(environment=env, protocol="gld-dataset-wifi/3",
                username="gld", password=self.secret)))
            private_before[path] = path.read_bytes()
        expected = self.profile.read_text()
        exporter.export_profiles(self.root)
        self.assertEqual(json.loads(self.profile.read_text()), json.loads(expected))
        self.assertNotIn(self.secret, self.profile.read_text())
        self.assertEqual(private_before, {p: p.read_bytes() for p in private_before})
        # Invalid future package must not replace the previous public profile.
        before = self.profile.read_bytes()
        (self.packages[1] / "firmware.bin").write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            exporter.export_profiles(self.root)
        self.assertEqual(before, self.profile.read_bytes())


if __name__ == "__main__":
    unittest.main()
