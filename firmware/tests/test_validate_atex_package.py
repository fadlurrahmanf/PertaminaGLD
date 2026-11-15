"""Synthetic ATEX package admission tests. No device or release writes."""
from __future__ import annotations
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

validator = load("atex_validation", ROOT / "firmware/tools/validate_atex_package.py")
bridge = load("atex_test_gld_bridge", ROOT / "apps/gld-operator/bridge.py")


class AtexPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.model_root = Path(self.tmp.name)
        self.blob = b"\x22\x33\x44\x55\x66\x77\x88\x99"
        for number in (1, 2, 3):
            directory = self.model_root / f"model_{number}"
            directory.mkdir()
            profile = f"synthetic-profile-{number}"
            directory.joinpath("model.json").write_text(json.dumps({
                "slot": f"model_{number}", "modelSha256": hashlib.sha256(self.blob).hexdigest(),
                "profileId": profile}), encoding="utf-8")
            directory.joinpath("ModelMetadata.h").write_text(f'PROFILE_ID = "{profile}";', encoding="utf-8")
            values = ", ".join(f"0x{value:02x}" for value in self.blob)
            directory.joinpath("cnn_gas_datasheet_model_data.h").write_text(
                f"g_cnn_gas_datasheet_2class_model[] = {{{values}}};", encoding="utf-8")
        self.env = validator.ATEX_ENVIRONMENTS[1]
        part = bytearray(b"\xff" * 96)
        part[:4] = bytes((0xAA, 0x50, 0x01, 0x02))
        part[4:8] = (0x9000).to_bytes(4, "little")
        part[8:12] = (0x5000).to_bytes(4, "little")
        part[32:36] = bytes((0xAA, 0x50, 0x00, 0x10))
        part[36:40] = (0x10000).to_bytes(4, "little")
        part[40:44] = (0x640000).to_bytes(4, "little")
        firmware = b"prefix" + self.blob + b"synthetic-profile-1\0" + b"\0".join(validator.MARKERS)
        self.contents = {"bootloader.bin": b"boot", "partitions.bin": bytes(part),
                         "boot_app0.bin": b"boot-app", "firmware.bin": firmware}
        self.manifest = {
            "schemaVersion": 2, "packageType": "pertamina-gld-prebuilt-firmware",
            "deviceId": "ANY", "boardProfile": validator.ATEX_BOARD_PROFILE,
            "environment": self.env, "firmwareVersion": "0.8.30", "protocolVersion": "1.0.0",
            "configSchemaVersion": "1.0.0", "chip": "esp32s3", "baud": 921600,
            "createdAtUtc": "20261112T120000Z",
            "source": {"gitCommit": "a" * 40, "gitTreeState": "build-output",
                       "platformioCoreVersion": "PlatformIO post-build hook",
                       "platformioIniSha256": "b" * 64,
                       "buildCommand": f"pio run -e {self.env}", "packagedAtUtc": "20261112T120000Z"},
            "capabilities": {"nativeSerial": True, "datasetWifi": True},
        }
        self.refresh()

    def tearDown(self):
        self.tmp.cleanup()

    def refresh(self):
        self.files = {name: base64.b64encode(data).decode("ascii") for name, data in self.contents.items()}
        self.manifest["flashFiles"] = [{"path": name, "offset": f"0x{validator.FLASH_LAYOUT[name]:08X}",
            "size": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in self.contents.items()]
        self.manifest["flashSetSha256"] = bridge._manifest_flash_set_sha256(self.manifest["flashFiles"])

    def validate(self, model=1):
        return validator.validate_atex_package(self.manifest, self.files, model, "1001",
            base_validator=bridge.validate_firmware_package, nvs_resolver=bridge.verified_nvs_region,
            model_root=self.model_root)

    def test_valid_model_manifest_and_immutable_input(self):
        before = copy.deepcopy(self.manifest)
        result = self.validate()
        self.assertEqual(result["profileId"], "synthetic-profile-1")
        self.assertEqual(result["nvsOffset"], 0x9000)
        self.assertEqual(self.manifest, before)

    def test_environment_and_board_mismatch_rejected(self):
        for field, value in (("environment", "gld_model_1_dataset_workflow_wifi"),
                             ("environment", "gld_atex_model_1_workflow_candidate"),
                             ("boardProfile", "GLD2")):
            original = self.manifest[field]
            self.manifest[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(RuntimeError): self.validate()
            self.manifest[field] = original
        for model in (0, 4, True, "1", None):
            with self.subTest(model=model), self.assertRaises(RuntimeError): self.validate(model)
        with self.assertRaises(RuntimeError): self.validate(2)

    def test_capability_rejection(self):
        for caps in (None, {}, {"nativeSerial": 1, "datasetWifi": True},
                     {"nativeSerial": True, "datasetWifi": True, "extra": True}):
            self.manifest["capabilities"] = caps
            with self.subTest(caps=caps), self.assertRaises(RuntimeError): self.validate()

    def test_base_validator_rejects_tampered_hash_size_extra_and_missing(self):
        for case in ("hash", "size", "extra", "missing"):
            old_manifest, old_files = copy.deepcopy(self.manifest), dict(self.files)
            if case == "hash": self.manifest["flashFiles"][0]["sha256"] = "0" * 64
            if case == "size": self.manifest["flashFiles"][0]["size"] += 1
            if case == "extra": self.files["extra.bin"] = "AA=="
            if case == "missing": self.files.pop("firmware.bin")
            with self.subTest(case=case), self.assertRaises(RuntimeError): self.validate()
            self.manifest, self.files = old_manifest, old_files

    def test_layout_and_nvs_checks(self):
        self.contents["bootloader.bin"] = b"x" * 0x8001
        self.refresh()
        with self.assertRaisesRegex(RuntimeError, "overlap"): self.validate()
        self.contents["bootloader.bin"] = b"ok"
        part = bytearray(self.contents["partitions.bin"])
        part[4:8] = (0xA000).to_bytes(4, "little")
        self.contents["partitions.bin"] = bytes(part)
        self.refresh()
        with self.assertRaisesRegex(RuntimeError, "NVS"): self.validate()

    def test_wrong_model_duplicate_model_and_missing_workflow_marker(self):
        good = self.contents["firmware.bin"]
        for bad in (good.replace(b"synthetic-profile-1", b"synthetic-profile-2"),
                    good + self.blob, good.replace(b"PAUSE_DATASET", b"NOT_PAUSE")):
            self.contents["firmware.bin"] = bad
            self.refresh()
            with self.subTest(bad=bad[-16:]), self.assertRaises(RuntimeError): self.validate()

    def test_all_three_models_validate_their_own_contract(self):
        for model in (1, 2, 3):
            with self.subTest(model=model):
                self.env = validator.ATEX_ENVIRONMENTS[model]
                self.manifest["environment"] = self.env
                self.manifest["source"]["buildCommand"] = f"pio run -e {self.env}"
                self.contents["firmware.bin"] = (b"prefix" + self.blob +
                    f"synthetic-profile-{model}".encode() + b"\0" + b"\0".join(validator.MARKERS))
                self.refresh()
                self.assertEqual(self.validate(model)["model"], model)

    def test_offset_and_partition_contract_mismatch(self):
        for offset in ("0x00002000", "0x00011000"):
            self.refresh()
            item = next(x for x in self.manifest["flashFiles"] if x["path"] == "firmware.bin")
            item["offset"] = offset
            self.manifest["flashSetSha256"] = bridge._manifest_flash_set_sha256(self.manifest["flashFiles"])
            with self.subTest(offset=offset), self.assertRaisesRegex(RuntimeError, "offset"):
                self.validate()
        original_table = self.contents["partitions.bin"]
        for mutate in ("duplicate_nvs", "wrong_app_size", "overlap_nvs", "outside_flash"):
            table = bytearray(original_table)
            if mutate == "duplicate_nvs": table[64:96] = table[0:32]
            elif mutate == "wrong_app_size": table[40:44] = (0x630000).to_bytes(4, "little")
            else:
                table[64:68] = bytes((0xAA, 0x50, 0x01, 0x81))
                table[68:72] = (0xA000 if mutate == "overlap_nvs" else 0x1000000).to_bytes(4, "little")
                table[72:76] = (0x1000).to_bytes(4, "little")
            self.contents["partitions.bin"] = bytes(table)
            self.refresh()
            with self.subTest(mutate=mutate), self.assertRaisesRegex(RuntimeError, "partition"):
                self.validate()
    def test_synthetic_build_marker_and_bad_target_are_rejected(self):
        self.contents["firmware.bin"] += b"SYNTHETIC_TEST_ONLY"
        self.refresh()
        with self.assertRaisesRegex(RuntimeError, "synthetic candidate"):
            self.validate()
        for identity in ("0000", "FFFF", "100g", "", None):
            with self.subTest(identity=identity), self.assertRaisesRegex(RuntimeError, "identity"):
                validator.validate_atex_package(self.manifest, self.files, 1, identity,
                    base_validator=bridge.validate_firmware_package, nvs_resolver=bridge.verified_nvs_region,
                    model_root=self.model_root)
    def test_untrusted_model_source_or_profile_rejected(self):
        path = self.model_root / "model_1/model.json"
        metadata = json.loads(path.read_text())
        metadata["modelSha256"] = "0" * 64
        path.write_text(json.dumps(metadata))
        with self.assertRaisesRegex(RuntimeError, "model source contract"): self.validate()


if __name__ == "__main__":
    unittest.main()

