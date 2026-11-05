"""Synthetic signed-package fixtures only. Never installs or reads live drivers."""
from pathlib import Path
import importlib.util
import json
import tempfile
import unittest
from unittest import mock

TOOL = Path(__file__).resolve().parents[1] / "handover_driver.py"
spec = importlib.util.spec_from_file_location("handover_driver_under_test", TOOL)
driver = importlib.util.module_from_spec(spec); spec.loader.exec_module(driver)
INF = b'''[Version]
Signature = "$Chicago$"
Class = Ports
Provider = %WinChipHead%
DriverVer = 09/16/2024, 3.9.2024.09
CatalogFile = CH341SER.CAT
[WinChipHead.NTamd64]
%CH340SER.DeviceDesc% = CH341SER_Inst.NTamd64, USB\\VID_1A86&PID_7523
[WinChipHead.NTARM64]
%CH340SER.DeviceDesc% = CH341SER_Inst.NTARM64, USB\\VID_1A86&PID_7523
[CH341SER_Inst.NTamd64]
CopyFiles = CH341SER.NT.CopyFiles.SYSA64, CH341SER.CopyFiles.DLLA64
[CH341SER_Inst.NTARM64]
CopyFiles = CH341SER.NT.CopyFiles.SYSM64
[CH341SER.NT.CopyFiles.SYSA64]
CH341S64.SYS, , , 2
[CH341SER.CopyFiles.DLLA64]
CH341PTA64.DLL, , , 2
CH341PORTSA64.DLL, , , 2
[CH341SER.NT.CopyFiles.SYSM64]
CH341M64.SYS, , , 2
'''


class HandoverDriverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.store = self.root / "DriverStore"; self.source = self.store / "ch341ser.inf_amd64_fixture"
        self.source.mkdir(parents=True); self.out = self.root / "export"
        (self.source / "CH341SER.INF").write_bytes(INF)
        for name in ("CH341SER.CAT", "CH341S64.SYS", "CH341PTA64.DLL", "CH341PORTSA64.DLL"):
            (self.source / name).write_bytes(("synthetic-" + name).encode())
        (self.source / "LICENSE.txt").write_text("synthetic license")
        (self.source / "ch341ser.PNF").write_bytes(b"do not export compiled local INF cache")
        (self.source / "other-driver.sys").write_bytes(b"do not export unrelated driver")
        self.signature = mock.patch.object(driver, "_catalog_signed", return_value=True); self.signature.start()
        self.process = mock.patch.object(driver, "_run", side_effect=AssertionError("No installation allowed")); self.process.start()

    def tearDown(self):
        self.process.stop(); self.signature.stop(); self.temp.cleanup()

    def export(self):
        return driver.export_driver(self.out, driver_store=self.store)

    def manifest(self):
        return self.out / driver.MANIFEST

    def test_discovery_and_export_include_required_x64_dlls_without_unrelated_payload(self):
        found = driver.discover_driver(self.store)
        self.assertEqual(len(found), 1); self.assertEqual(found[0]["architecture"], "windows-x64")
        manifest = self.export(); names = {item["path"] for item in manifest["files"]}
        self.assertEqual(names, {"ch341ser.inf", "ch341ser.cat", "ch341s64.sys", "ch341pta64.dll", "ch341portsa64.dll", "license.txt"})
        self.assertEqual(driver.validate_driver(self.manifest()), manifest)
        self.assertEqual((self.out / "ch341ser.inf").read_bytes(), INF)
        self.assertNotIn(str(self.source), self.manifest().read_text())
        self.assertFalse((self.out / "ch341m64.sys").exists())  # Explicitly x64, not ARM64 support.

    def test_install_plan_validates_and_returns_command_without_execution(self):
        self.export(); plan = driver.install_command_plan(self.manifest())
        self.assertEqual(plan, ["pnputil.exe", "/add-driver", str(self.out / "ch341ser.inf"), "/install"])
        driver._run.assert_not_called()

    def test_existing_output_even_empty_is_never_overwritten(self):
        self.out.mkdir(); keep = self.out / "keep.txt"; keep.write_text("preserve")
        with self.assertRaisesRegex(driver.DriverError, "must_be_new"):
            self.export()
        self.assertEqual(keep.read_text(), "preserve")

    def test_missing_required_dll_refuses_discovery_and_export_without_output(self):
        (self.source / "CH341PTA64.DLL").unlink()
        self.assertEqual(driver.discover_driver(self.store), [])
        with self.assertRaisesRegex(driver.DriverError, "payload_missing"):
            driver.export_driver(self.out, source=self.source)
        self.assertFalse(self.out.exists())

    def test_invalid_catalog_signature_refuses_export_or_install_plan(self):
        driver._catalog_signed.return_value = False
        with self.assertRaisesRegex(driver.DriverError, "signature_not_verified"):
            self.export()
        self.assertFalse(self.out.exists())
        driver._catalog_signed.return_value = True; self.export()
        driver._catalog_signed.return_value = False
        with self.assertRaisesRegex(driver.DriverError, "signature_not_verified"):
            driver.install_command_plan(self.manifest())

    def test_tampered_binary_refuses_validation(self):
        self.export(); (self.out / "ch341s64.sys").write_bytes(b"tamper")
        with self.assertRaisesRegex(driver.DriverError, "hash_mismatch"):
            driver.validate_driver(self.manifest())

    def test_manifest_traversal_duplicate_and_unrelated_driver_are_rejected(self):
        self.export(); original = self.manifest().read_text()
        for name in ("../outside.sys", "C:/outside.sys", "other.sys", "ch341ser.inf"):
            with self.subTest(name=name):
                value = json.loads(original); value["files"][-1]["path"] = name
                self.manifest().write_text(json.dumps(value))
                with self.assertRaises(driver.DriverError):
                    driver.validate_driver(self.manifest())

    def test_extra_file_or_directory_is_not_ignored_in_exported_package(self):
        self.export(); extra = self.out / "unrelated.sys"; extra.write_bytes(b"unrelated")
        with self.assertRaisesRegex(driver.DriverError, "extra_payload"):
            driver.validate_driver(self.manifest())
        extra.unlink(); (self.out / "untracked-directory").mkdir()
        with self.assertRaisesRegex(driver.DriverError, "extra_payload"):
            driver.validate_driver(self.manifest())

    def test_ambiguous_source_requires_explicit_choice(self):
        other = self.store / "ch341ser.inf_amd64_other"; other.mkdir()
        for path in self.source.iterdir():
            (other / path.name).write_bytes(path.read_bytes())
        with self.assertRaisesRegex(driver.DriverError, "ambiguous"):
            self.export()
        driver.export_driver(self.out, source=self.source)
        self.assertTrue(self.manifest().is_file())

    def test_linked_payload_is_refused(self):
        # Mock the reparse observation so this test does not require symlink
        # privileges on Windows and never touches an external driver path.
        original = driver._linked
        with mock.patch.object(driver, "_linked", side_effect=lambda p: p.name.lower()=="ch341s64.sys" or original(p)):
            with self.assertRaises(driver.DriverError):
                driver.export_driver(self.out, source=self.source)
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
