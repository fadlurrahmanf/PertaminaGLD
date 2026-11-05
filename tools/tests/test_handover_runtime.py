"""Synthetic distribution files only; never reads the real Node-RED profile."""
from pathlib import Path
import importlib.util
import json
import tempfile
import unittest
from unittest import mock

TOOL = Path(__file__).resolve().parents[1] / "handover_runtime.py"
spec = importlib.util.spec_from_file_location("handover_runtime_under_test", TOOL)
runtime = importlib.util.module_from_spec(spec); spec.loader.exec_module(runtime)


class HandoverRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.node = self.root / "node/node.exe"; self.node.parent.mkdir()
        self.node.write_bytes(b"SYNTHETIC-NODE-ONLY" * 120)
        (self.node.parent / "LICENSE").write_text("synthetic Node license")
        self.red = self.root / "node-red"; self.red.mkdir()
        (self.red / "package.json").write_text(json.dumps(dict(name="node-red", version="5.0.1")))
        (self.red / "red.js").write_text("// inert fixture only")
        (self.red / "LICENSE").write_text("synthetic NodeRED license")
        self.modules = self.root / "user-node_modules"; package = self.modules / "example-module"; package.mkdir(parents=True)
        (package / "package.json").write_text(json.dumps(dict(name="example-module", version="1.2.3")))
        (package / "index.js").write_text("module.exports = {};")
        self.output = self.root / "artifacts"; self.dest = self.root / "restored"
        self.version = mock.patch.object(runtime, "_node_version", return_value="26.5.0"); self.version.start()

    def tearDown(self):
        self.version.stop(); self.temp.cleanup()

    def export(self, **kwargs):
        return runtime.export_runtime(self.node, self.red, self.modules, self.output, **kwargs)

    def manifest(self):
        return self.output / runtime.MANIFEST

    def test_export_and_verified_extract_preserve_modules_licenses_and_versions(self):
        result = self.export(max_part_bytes=128)
        self.assertGreater(len(result["parts"]), 1)
        self.assertTrue(all(part["size"] <= 128 for part in result["parts"]))
        meta = runtime.extract_runtime(self.manifest(), self.dest)
        self.assertEqual(meta["nodeVersion"], "26.5.0")
        self.assertEqual(meta["nodeRedVersion"], "5.0.1")
        self.assertEqual(meta["userPackages"], [dict(name="example-module", version="1.2.3")])
        self.assertEqual((self.dest / "node/node.exe").read_bytes(), self.node.read_bytes())
        self.assertEqual((self.dest / "node-red/LICENSE").read_text(), "synthetic NodeRED license")
        self.assertTrue((self.dest / "user-node_modules/example-module/index.js").is_file())
        self.assertNotIn(str(self.root), self.manifest().read_text())

    def test_deterministic_archive_and_public_metadata(self):
        first = self.export(); first_parts = [(self.output / p["path"]).read_bytes() for p in first["parts"]]
        second_output = self.root / "other-artifacts"
        second = runtime.export_runtime(self.node, self.red, self.modules, second_output)
        self.assertEqual(first, second)
        self.assertEqual(first_parts, [(second_output / p["path"]).read_bytes() for p in second["parts"]])

    def test_private_names_cache_and_profile_are_not_read_or_included(self):
        secret = "SYNTHETIC_PRIVATE_DO_NOT_EXPORT"
        for name in (".env", ".env.production", ".npmrc", "credentials.local.json", "flows_cred.json", "private.key", "debug.log", "tokens.json", ".node_repl_history"):
            (self.red / name).write_text(secret)
        (self.red / ".git").mkdir(); (self.red / ".git/private").write_text(secret)
        # User settings are outside the module source and cannot enter archive.
        (self.root / "settings.js").write_text(secret)
        result = self.export()
        names = {item["path"] for item in result["files"]}
        self.assertFalse(any(name.endswith((".env", ".npmrc", "private.key", "debug.log")) for name in names))
        runtime.extract_runtime(self.manifest(), self.dest)
        self.assertFalse(any(secret.encode() in p.read_bytes() for p in self.dest.rglob("*") if p.is_file()))

    def test_existing_destinations_are_preserved(self):
        self.export()
        with self.assertRaisesRegex(ValueError, "new or empty"):
            self.export()
        self.dest.mkdir(); keep = self.dest / "existing-runtime"; keep.write_bytes(b"preserve")
        with self.assertRaisesRegex(ValueError, "new or empty"):
            runtime.extract_runtime(self.manifest(), self.dest)
        self.assertEqual(keep.read_bytes(), b"preserve")

    def test_part_tamper_and_missing_part_fail_without_destination(self):
        result = self.export(); part = self.output / result["parts"][0]["path"]
        part.write_bytes(part.read_bytes() + b"tampered")
        with self.assertRaisesRegex(ValueError, "checksum"):
            runtime.extract_runtime(self.manifest(), self.dest)
        self.assertFalse(self.dest.exists())
        part.unlink()
        with self.assertRaisesRegex(ValueError, "checksum"):
            runtime.extract_runtime(self.manifest(), self.dest)

    def test_file_tamper_rejected_even_if_archive_and_part_hashes_are_updated(self):
        manifest = self.export()
        manifest["files"][0]["sha256"] = "0" * 64
        self.manifest().write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "file checksum"):
            runtime.extract_runtime(self.manifest(), self.dest)
        self.assertFalse(self.dest.exists())

    def test_archive_path_and_case_alias_admission(self):
        self.export(); original = self.manifest().read_text()
        for unsafe in ("../outside", "/absolute", "C:/outside", "node/../outside", "node\\outside", "node/NUL", "node/x.", "node/x:y"):
            with self.subTest(unsafe=unsafe):
                manifest = json.loads(original); manifest["files"][0]["path"] = unsafe
                self.manifest().write_text(json.dumps(manifest))
                with self.assertRaises(ValueError): runtime.extract_runtime(self.manifest(), self.dest)
                self.assertFalse(self.dest.exists())
        manifest = json.loads(original); duplicate = dict(manifest["files"][0]); duplicate["path"] = duplicate["path"].upper();manifest["files"].append(duplicate)
        self.manifest().write_text(json.dumps(manifest))
        with self.assertRaises(ValueError): runtime.extract_runtime(self.manifest(), self.dest)

    def test_linked_distribution_is_rejected_when_symlinks_available(self):
        outside = self.root / "outside"; outside.write_text("synthetic outside")
        link = self.red / "linked"
        try: link.symlink_to(outside)
        except OSError: self.skipTest("Symlink permission unavailable")
        with self.assertRaisesRegex(ValueError, "Linked distribution"):
            self.export()
        self.assertFalse(self.output.exists())

    def test_source_output_recursion_and_wrong_package_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside distribution"):
            runtime.export_runtime(self.node, self.red, self.modules, self.red / "nested-output")
        (self.red / "package.json").write_text(json.dumps(dict(name="other", version="1.0.0")))
        with self.assertRaisesRegex(ValueError, "not Node-RED"):
            self.export()

    def test_inventory_does_not_create_artifacts(self):
        result, entries = runtime.inventory(self.node, self.red, None)
        self.assertEqual(result["userPackages"], [])
        self.assertEqual(result["fileCount"], len(entries))
        self.assertFalse(self.output.exists())


if __name__ == "__main__": unittest.main()
