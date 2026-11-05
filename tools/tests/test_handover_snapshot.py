"""Synthetic snapshot/restore fixtures only; no real user data or services."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "handover_snapshot.py"
SPEC = importlib.util.spec_from_file_location("test_handover_snapshot_module", SCRIPT)
snapshot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(snapshot)


class FullHandoverSnapshot(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repo = self.base / "repository"
        self.profile = self.base / "node-red-profile"
        self.history = self.base / "approved-history"
        self.output = self.base / "snapshot"
        self.destination = self.base / "restored"
        self.synthetic = "SYNTHETIC_PASSWORD_NOT_A_REAL_SECRET"
        self.write(self.repo / "server/nodered/.env", (
            '# synthetic only\nGLD_KEY_ID=7\nGLD_AES128_KEY_HEX=00000000000000000000000000000000\n'
            'MQTT_HOST=127.0.0.1\nMQTT_PASS="' + self.synthetic + '"\n'
            'PGL_REPLAY_STATE_PATH=old/replay.json\nPGL_FIELD_TEST_LOG_DIR=old/logs\nCUSTOM_FLAG=unchanged\n').encode())
        self.write(self.repo / "archive/apps/runtime/operator-hub/credentials.local.json",
                   json.dumps(dict(host="127.0.0.1", port=1884, username="synthetic-user", password=self.synthetic)).encode())
        profile_files = {
            "settings.js": b"module.exports = {credentialSecret: 'SYNTHETIC_ONLY'};\r\n",
            "flows.json": b'[{"id":"synthetic-project-tab","type":"tab"}]\n',
            "flows_cred.json": b'{"$":"synthetic-encrypted-fixture"}\n',
            ".config.runtime.json": b'{"_credentialSecret":"synthetic-runtime-key"}\n',
            "package.json": b'{"dependencies":{"synthetic-node":"1.2.3"}}\n',
            "package-lock.json": b'{"lockfileVersion":3}\n',
            "pertamina-gld-replay-state.json": b'{"counter":9}\n',
            "pertamina-gld-topology-bootstrap.json": b'{"gld":["1002"]}\n',
            "context/project/flow.json": b'{"preserved":"context"}\n',
            "pgl-context/pgl_tab/flow.json": b'{"preserved":"topology"}\n',
            "node_modules/personal-dependency/index.js": b"do not copy",
            ".config.users.json": b'{"unrelated-user":"do-not-copy"}',
            "pertamina-gld-backups/old.json": b"do not copy backup",
        }
        for name, raw in profile_files.items():
            self.write(self.profile / name, raw)
        self.csv_sources = []
        for index, name in enumerate(("same.csv", "subfolder/same.csv", "unicode-test.csv"), 1):
            path = self.history / name
            self.write(path, b'\xef\xbb\xbfWaktu (ms),MQ8 (V),Label\r\n500,1.0,test\r\n1000,2.0,test\r\n' + f'{index},3.0,last\r\n'.encode())
            self.csv_sources.append(path)
        self.write(self.history / "unapproved.csv", b"unrelated,do-not-copy\n")
        self.discovery = self.repo / "tmp/full-handover-20261105/csv-discovery.json"
        self.write(self.discovery, json.dumps(dict(datasetCsvCandidates=[dict(path=str(path), size=path.stat().st_size) for path in self.csv_sources])).encode())
        self.write(self.repo / "apps/gld-operator/output/datasets/workflow_synthetic.jsonl", b'{"row":1}\n{"row":2}\n')
        self.write(self.repo / "output/datasets/review.jsonl", b'{"row":3}\n')
        self.write(self.repo / "output/gld-history.jsonl", b'{"row":4}\n')
        self.write(self.repo / "output/personal-notes.jsonl", b'{"unrelated":"not approved"}\n')

    @staticmethod
    def write(path, raw):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def tearDown(self):
        self.temporary.cleanup()

    def export(self):
        return snapshot.export_snapshot(self.repo, self.output, node_red_profile=self.profile, csv_discovery=self.discovery)

    def source_hashes(self):
        return {path: hashlib.sha256(path.read_bytes()).hexdigest()
                for directory in (self.repo, self.profile, self.history)
                for path in directory.rglob("*") if path.is_file()}

    def test_export_preserves_all_approved_bytes_and_excludes_unrelated_data(self):
        before = self.source_hashes()
        summary = self.export()
        self.assertEqual(before, self.source_hashes())
        self.assertEqual(summary["csvFiles"], 3)
        self.assertEqual(summary["ledgerFiles"], 3)
        manifest = snapshot.validate_snapshot(self.output)
        outputs = [item["path"] for item in manifest["files"]]
        self.assertIn("nodered/.config.runtime.json", outputs)
        self.assertFalse(any("node_modules" in path or "backups" in path or ".config.users" in path or "personal-notes" in path for path in outputs))
        csv_records = [item for item in manifest["files"] if item["role"] == "dataset-csv"]
        self.assertEqual(len({record["path"] for record in csv_records}), 3)
        for item in manifest["files"]:
            if "sourcePath" in item:
                self.assertEqual((self.output / item["path"]).read_bytes(), Path(item["sourcePath"]).read_bytes())
        system = json.loads((self.output / "config/system.json").read_text())
        self.assertEqual(system["serverEnv"]["CUSTOM_FLAG"], "unchanged")
        self.assertEqual(system["broker"]["password"], self.synthetic)
        self.assertNotIn(self.synthetic, json.dumps(summary))

    def test_restore_into_new_target_keeps_profile_exact_and_rebases_only_copied_env(self):
        self.export()
        original_manifest = (self.output / snapshot.MANIFEST).read_bytes()
        original_system = (self.output / "config/system.json").read_bytes()
        summary = snapshot.restore(self.output, self.destination)
        self.assertTrue(summary["serverEnvPathsRebased"])
        self.assertEqual(original_manifest, (self.output / snapshot.MANIFEST).read_bytes())
        self.assertEqual(original_system, (self.output / "config/system.json").read_bytes())
        self.assertEqual((self.destination / "nodered/settings.js").read_bytes(), (self.profile / "settings.js").read_bytes())
        self.assertEqual((self.destination / "nodered/flows_cred.json").read_bytes(), (self.profile / "flows_cred.json").read_bytes())
        self.assertEqual((self.destination / "nodered/.config.runtime.json").read_bytes(), (self.profile / ".config.runtime.json").read_bytes())
        env = json.loads((self.destination / "config/system.json").read_text())["serverEnv"]
        self.assertEqual(Path(env["PGL_REPLAY_STATE_PATH"]), self.destination / "nodered/pertamina-gld-replay-state.json")
        self.assertEqual(Path(env["PGL_FIELD_TEST_LOG_DIR"]), self.destination / "history/field-test-logs")
        self.assertEqual(env["CUSTOM_FLAG"], "unchanged")

    def test_nonempty_export_and_restore_destinations_are_never_overwritten(self):
        self.write(self.output / "sentinel", b"keep")
        with self.assertRaises(snapshot.SnapshotError):
            self.export()
        self.assertEqual((self.output / "sentinel").read_bytes(), b"keep")
        (self.output / "sentinel").unlink()
        self.export()
        self.write(self.destination / "sentinel", b"keep")
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.restore(self.output, self.destination)
        self.assertEqual((self.destination / "sentinel").read_bytes(), b"keep")

    def test_tampered_or_unlisted_snapshot_file_blocks_restore_before_publication(self):
        self.export()
        path = self.output / "nodered/flows.json"
        original = path.read_bytes(); path.write_bytes(b"tampered")
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.restore(self.output, self.destination)
        self.assertFalse(self.destination.exists())
        path.write_bytes(original)
        self.write(self.output / "unlisted.txt", b"not in manifest")
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.restore(self.output, self.destination)
        self.assertFalse(self.destination.exists())

    def test_traversal_drive_reserved_and_case_duplicate_paths_are_rejected(self):
        self.export()
        path = self.output / snapshot.MANIFEST; original = path.read_text()
        for unsafe in ("../escape", "config/../../escape", "C:/escape", "config/CON.txt", "config/trailing.", "config\\escape"):
            manifest = json.loads(original); manifest["files"][0]["path"] = unsafe
            path.write_text(json.dumps(manifest))
            with self.subTest(path=unsafe), self.assertRaises(snapshot.SnapshotError):
                snapshot.restore(self.output, self.destination)
        manifest = json.loads(original); duplicate = dict(manifest["files"][0]); duplicate["path"] = duplicate["path"].upper()
        manifest["files"].append(duplicate); path.write_text(json.dumps(manifest))
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.restore(self.output, self.destination)
        self.assertFalse((self.base / "escape").exists())

    def test_failed_restore_discards_only_its_stage_and_preserves_snapshot(self):
        self.export()
        path = self.output / "config/system.json"; path.write_bytes(b'{"schemaVersion":99}')
        manifest_path = self.output / snapshot.MANIFEST; manifest = json.loads(manifest_path.read_text())
        for item in manifest["files"]:
            if item["path"] == "config/system.json":
                item.update(size=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        manifest["totalBytes"] = sum(item["size"] for item in manifest["files"])
        manifest_path.write_text(json.dumps(manifest))
        before = path.read_bytes()
        with self.assertRaises(snapshot.SnapshotError):
            snapshot.restore(self.output, self.destination)
        self.assertFalse(self.destination.exists())
        self.assertEqual(before, path.read_bytes())
        self.assertEqual(list(self.base.glob(".gld-snapshot-*")), [])

    def test_missing_approved_history_fails_atomically_instead_of_silently_omitting_rows(self):
        self.csv_sources[0].unlink()
        with self.assertRaises(snapshot.SnapshotError):
            self.export()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.base.glob(".gld-snapshot-*")), [])

    def test_broken_destination_symlink_is_refused_without_following_it(self):
        outside = self.base / "unintended-target"
        try:
            os.symlink(outside, self.output, target_is_directory=True)
        except OSError:
            self.skipTest("Host does not permit creating synthetic symlinks")
        with self.assertRaises(snapshot.SnapshotError):
            self.export()
        self.assertFalse(outside.exists())


if __name__ == "__main__":
    unittest.main()
