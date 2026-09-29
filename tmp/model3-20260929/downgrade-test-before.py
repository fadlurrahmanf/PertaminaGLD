"""Hardware-free GLD1 rollback upload ordering and consent regression tests."""
from __future__ import annotations

import base64
import copy
import io
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_child_package_validators import GLD_BRIDGE as child, load_bridge, package_for

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/operator-hub"))
hub = load_bridge("downgrade_hub_bridge", "apps/operator-hub/bridge.py")
BASE = "69a493c32d2500134a21e029820cd4addea1794a"


def make_package(env="gld"):
    manifest, files = package_for(child, env, {})
    manifest["firmwareVersion"] = "0.8.38"
    manifest["source"]["gitCommit"] = BASE
    partition = struct.pack("<HBBII16sI", 0x50AA, 1, 2, 0x9000, 0x5000, b"nvs", 0)
    partition += bytes([255]) * 32
    import hashlib
    entry = {"path": "partitions.bin", "offset": "0x00008000", "size": len(partition),
             "sha256": hashlib.sha256(partition).hexdigest()}
    manifest["flashFiles"].insert(0, entry)
    manifest["flashSetSha256"] = child._manifest_flash_set_sha256(manifest["flashFiles"])
    files["partitions.bin"] = base64.b64encode(partition).decode("ascii")
    return manifest, files


def payload_for(env="gld"):
    manifest, files = make_package(env)
    return {"env": env, "port": "COM999", "targetDeviceId": "1001",
            "resetNvs": True, "resetNvsConfirmation": "RESET NVS",
            "manifest": manifest, "packageFiles": files, "skipPreflight": True}


class DowngradeUploadTests(unittest.TestCase):
    def setUp(self):
        self.history = []
        self.write_exit = 0
        self.erase_exit = 0
        self.erase_timeout = False
        self.serial = mock.Mock()
        self.events = []
        def popen(cmd, **kwargs):
            self.history.append(("popen", cmd))
            process = mock.Mock()
            process.stdout = io.StringIO("Hash of data verified.\n")
            process.wait.return_value = self.write_exit
            return process
        def run(cmd, **kwargs):
            self.history.append(("run", cmd))
            self.assertEqual(kwargs["timeout"], 45)
            if self.erase_timeout:
                raise subprocess.TimeoutExpired(cmd, 45)
            return subprocess.CompletedProcess(cmd, self.erase_exit, "NVS erased\n")
        self.patches = [
            mock.patch.object(child, "get_serial_bridge", return_value=self.serial),
            mock.patch.object(child, "slot_holding_port", return_value=None),
            mock.patch.object(child, "probe_port", side_effect=AssertionError("no hardware")),
            mock.patch.object(child, "shared_esptool_command", side_effect=lambda args: ["esptool", *args]),
            mock.patch.object(child.subprocess, "Popen", side_effect=popen),
            mock.patch.object(child.subprocess, "run", side_effect=run),
            mock.patch.object(child.events, "emit", side_effect=lambda name, data: self.events.append((name, data))),
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_exact_guard_scope(self):
        for env in ("gld", "gld_model_1", "gld_v2", "gld_v3", "gld_model_2", "gld_model_3", "gldFieldtest"):
            for version in ("0.8.38", "0.8.37"):
                for commit in (BASE, "a" * 40):
                    manifest, _ = make_package(env)
                    manifest["firmwareVersion"] = version
                    manifest["source"]["gitCommit"] = commit
                    expected = env in {"gld", "gld_model_1"} and version == "0.8.38" and commit == BASE
                    self.assertEqual(child.requires_gld1_nvs_reset_before_boot(manifest), expected)
                    self.assertEqual(hub.requires_gld1_nvs_reset_before_boot(manifest), expected)

    def test_consent_rejected_before_serial_or_subprocess(self):
        for env in ("gld", "gld_model_1"):
            for reset, confirmation in ((False, ""), (True, ""), ("true", "RESET NVS"), (True, "yes")):
                request = payload_for(env)
                request.update(resetNvs=reset, resetNvsConfirmation=confirmation)
                with self.assertRaisesRegex(RuntimeError, "explicit Reset NVS"):
                    child._firmware_upload_reserved(request)
        self.serial.disconnect.assert_not_called()
        self.assertEqual(self.history, [])

    def test_guard_preerases_then_flashes_without_intervening_boot(self):
        for env in ("gld", "gld_model_1"):
            self.history.clear()
            self.events.clear()
            result = child._firmware_upload_reserved(payload_for(env))
            self.assertTrue(result["nvsReset"])
            self.assertEqual(len(self.history), 2)
            erase, write = self.history[0][1], self.history[1][1]
            self.assertIn("erase_region", erase)
            self.assertEqual(erase[erase.index("--after") + 1], "no_reset")
            self.assertNotIn("--before", erase)
            self.assertEqual(erase[-2:], ["0x9000", "0x5000"])
            self.assertIn("write_flash", write)
            self.assertEqual(write[write.index("--before") + 1], "no_reset")
            self.assertNotIn("--after", write)  # normal hard reset only after successful flash
            self.assertEqual([name for name, _ in self.events].count("upload_done"), 1)

    def test_failed_preerase_does_not_flash_or_report_success(self):
        self.erase_exit = 2
        with self.assertRaisesRegex(RuntimeError, "rollback was not flashed"):
            child._firmware_upload_reserved(payload_for())
        self.assertEqual(len(self.history), 1)
        self.assertIn("erase_region", self.history[0][1])
        self.assertNotIn("upload_done", [name for name, _ in self.events])

    def test_preerase_timeout_does_not_flash(self):
        self.erase_timeout = True
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            child._firmware_upload_reserved(payload_for())
        self.assertEqual(len(self.history), 1)
        self.assertNotIn("upload_done", [name for name, _ in self.events])

    def test_flash_failure_after_erase_does_not_report_success(self):
        self.write_exit = 2
        with self.assertRaisesRegex(RuntimeError, "flash failed"):
            child._firmware_upload_reserved(payload_for())
        self.assertEqual(len(self.history), 2)
        self.assertNotIn("upload_done", [name for name, _ in self.events])

    def test_missing_nvs_rejected_before_hardware(self):
        request = payload_for()
        request["manifest"], request["packageFiles"] = package_for(child, "gld", {})
        request["manifest"]["firmwareVersion"] = "0.8.38"
        request["manifest"]["source"]["gitCommit"] = BASE
        with self.assertRaisesRegex(RuntimeError, "NVS partition"):
            child._firmware_upload_reserved(request)
        self.serial.disconnect.assert_not_called()
        self.assertEqual(self.history, [])

    def test_other_packages_keep_optional_reset_and_normal_order(self):
        for env in ("gld_v2", "gld_v3", "gld_model_2", "gld_model_3", "gldFieldtest", "gld"):
            for reset in (False, True):
                self.history.clear()
                request = payload_for(env)
                if env == "gld":
                    request["manifest"]["firmwareVersion"] = "0.8.37"
                request.update(resetNvs=reset, resetNvsConfirmation="")
                child._firmware_upload_reserved(request)
                self.assertIn("write_flash", self.history[0][1])
                self.assertNotIn("--before", self.history[0][1])
                self.assertNotIn("--after", self.history[0][1])
                self.assertEqual(len(self.history), 2 if reset else 1)
                if reset:
                    self.assertIn("erase_region", self.history[1][1])
                    self.assertNotIn("--after", self.history[1][1])

    def test_hub_summary_exposes_reset_requirement(self):
        with tempfile.TemporaryDirectory(prefix="gld-summary-") as directory:
            for env in ("gld", "gld_model_1", "gld_v2"):
                manifest, _ = make_package(env)
                folder = Path(directory) / "firmware-packages" / env / "latest"
                folder.mkdir(parents=True)
                (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
                with mock.patch.object(hub, "HUB_DIR", Path(directory)):
                    summary = hub.package_manifest_summary(env)
                self.assertEqual(summary["requiresNvsResetBeforeBoot"], env != "gld_v2")


if __name__ == "__main__":
    unittest.main()
