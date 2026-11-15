"""Synthetic-only tests: never access local or packaged project credentials."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("atex_prep", ROOT / "firmware/tools/prepare_atex_workflow_wifi.py")
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)
SECRET = "fixtureAlpha_2026"
OTHER = "fixtureBeta_2026"
GLD = tuple(f"gld_model_{n}_dataset_workflow_wifi" for n in (1, 2, 3))


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "firmware"
        self.project.mkdir()
        helper = self.project / "tools/prepare_atex_workflow_wifi.py"
        helper.parent.mkdir()
        helper.write_bytes((ROOT / "firmware/tools/prepare_atex_workflow_wifi.py").read_bytes())
        fixture_spec = importlib.util.spec_from_file_location("atex_prep_fixture", helper)
        self.helper = importlib.util.module_from_spec(fixture_spec)
        fixture_spec.loader.exec_module(self.helper)
        resolver = self.root / "apps/gld-operator/workflow_credentials.py"
        resolver.parent.mkdir(parents=True)
        resolver.write_bytes((ROOT / "apps/gld-operator/workflow_credentials.py").read_bytes())

    def write_config(self, name, password=SECRET):
        path = self.project / ".pio/gld-dataset-workflow-wifi" / name / "credentials.local.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(environment=name, protocol="gld-dataset-wifi/3", username="gld",
                                        password=password, address="192.168.4.1", port=81, path="/dataset")))
        return path

    def private(self, password=SECRET):
        for name in GLD:
            self.write_config(name, password)

    def packaged(self, passwords=(SECRET, SECRET, SECRET)):
        models = {}
        for name, password in zip(GLD, passwords):
            binary = b"fixture:" + password.encode() + b"\0end"
            digest = hashlib.sha256(binary).hexdigest()
            folder = self.root / "apps/operator-hub/firmware-packages" / name / "latest"
            folder.mkdir(parents=True)
            (folder / "firmware.bin").write_bytes(binary)
            (folder / "manifest.json").write_text(json.dumps(dict(schemaVersion=2,
                packageType="pertamina-gld-prebuilt-firmware", environment=name, chip="esp32s3",
                flashFiles=[dict(path="firmware.bin", sha256=digest, size=len(binary))])))
            models[name] = dict(firmwareSha256=digest, passwordOffset=8, passwordLength=len(password))
        (self.root / "apps/gld-operator/workflow-connection-profiles.json").write_text(json.dumps(
            dict(schemaVersion=1, protocol="gld-dataset-wifi/3", models=models)))

    def build(self, name):
        return self.project / ".pio/build-atex-private-candidates" / name

    def call(self, name=prep.CANDIDATES[0], build=None):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            try:
                return self.helper.prepare(self.project, build or self.build(name), name)
            finally:
                self.assertNotIn(SECRET, output.getvalue())
                self.assertNotIn(OTHER, output.getvalue())

    def fail_closed(self):
        with self.assertRaisesRegex(RuntimeError, "^ATEX workflow credential preparation failed$"):
            self.call()
        self.assertFalse(self.build(prep.CANDIDATES[0]).exists())

    def test_private_all_models_and_idempotence(self):
        self.private()
        for name in prep.CANDIDATES:
            header = self.call(name)
            self.assertIn(SECRET, header.read_text())
            self.assertEqual(header, self.call(name))
        self.assertFalse((self.project / ".pio/gld-dataset-workflow-wifi" / prep.CANDIDATES[0]).exists())

    def test_clean_packaged_source(self):
        self.packaged()
        self.assertIn(SECRET, self.call().read_text())

    def test_missing_partial_mismatch_and_malformed_sources(self):
        self.fail_closed()
        self.packaged()
        self.write_config(GLD[0])
        self.fail_closed()  # partial private override must not fall back
        self.private()
        self.write_config(GLD[1], OTHER)
        self.fail_closed()
        self.write_config(GLD[1]).write_text("{")
        self.fail_closed()

    def test_packaged_mismatch(self):
        self.packaged((SECRET, OTHER, SECRET))
        self.fail_closed()

    def test_packaged_hash_tampering(self):
        self.packaged()
        image = self.root / "apps/operator-hub/firmware-packages" / GLD[0] / "latest/firmware.bin"
        image.write_bytes(b"tampered fixture")
        self.fail_closed()

    def test_private_overrides_packaged_password(self):
        self.packaged((OTHER, OTHER, OTHER))
        self.private()
        self.assertIn(SECRET, self.call().read_text())

    def test_exception_details_are_redacted(self):
        resolver = self.root / "apps/gld-operator/workflow_credentials.py"
        resolver.write_text("def resolve_workflow_password(root):\n    raise ValueError(" + repr(SECRET) + ")\n")
        with self.assertRaises(RuntimeError) as caught:
            self.call()
        self.assertNotIn(SECRET, str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)

    def test_other_project_root_rejected(self):
        self.private()
        with self.assertRaises(RuntimeError):
            prep.prepare(self.project, self.build(prep.CANDIDATES[0]), prep.CANDIDATES[0])

    def test_dangling_candidate_link_rejected(self):
        self.private()
        path = self.project / ".pio/gld-dataset-workflow-wifi" / prep.CANDIDATES[0] / "credentials.local.json"
        path.parent.mkdir(parents=True)
        try:
            path.symlink_to(self.root / "missing")
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error.__class__.__name__}")
        self.fail_closed()

    def test_windows_reparse_attribute_rejected(self):
        info = mock.Mock(st_mode=0, st_file_attributes=0x400)
        with mock.patch.object(Path, "lstat", return_value=info):
            with self.assertRaises(ValueError):
                self.helper._reject_redirects(self.project)

    def test_missing_resolver_and_invalid_candidate_fields(self):
        self.private()
        resolver = self.root / "apps/gld-operator/workflow_credentials.py"
        saved = resolver.read_bytes()
        resolver.unlink()
        self.fail_closed()
        resolver.write_bytes(saved)
        for name in prep.CANDIDATES:
            self.write_config(name)
        path = self.write_config(prep.CANDIDATES[1])
        value = json.loads(path.read_text())
        value["protocol"] = "wrong"
        path.write_text(json.dumps(value))
        self.fail_closed()

    def test_candidate_overrides_must_all_match(self):
        self.private()
        self.write_config(prep.CANDIDATES[0])
        self.fail_closed()
        for name in prep.CANDIDATES:
            self.write_config(name)
        self.write_config(prep.CANDIDATES[2], OTHER)
        self.fail_closed()
        self.write_config(prep.CANDIDATES[2]).write_text("{")
        self.fail_closed()
        self.write_config(prep.CANDIDATES[2])
        self.assertTrue(self.call().is_file())

    def test_synthetic_sentinel_rejected(self):
        self.private("SYNTHETIC_TEST_ONLY")
        self.fail_closed()

    def test_existing_header_is_never_rotated(self):
        self.private()
        header = self.call()
        header.write_text("existing different header")
        with self.assertRaises(RuntimeError):
            self.call()
        self.assertEqual(header.read_text(), "existing different header")

    def test_invalid_environment_and_output_rejected(self):
        self.private()
        for name in ("gld_atex", "gld_model_1_dataset_workflow_wifi", "../bad"):
            with self.assertRaises(RuntimeError):
                self.call(name)
        with self.assertRaises(RuntimeError):
            self.call(build=self.root / "outside")
        self.assertFalse((self.root / "outside").exists())


if __name__ == "__main__":
    unittest.main()
