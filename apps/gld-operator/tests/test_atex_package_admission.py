"""Synthetic package admission tests. Never open COM, network or real firmware."""
from __future__ import annotations
import base64
import copy
import hashlib
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

bridge = load("atex_child_bridge", "apps/gld-operator/bridge.py")
validator = load("atex_verifier_test", "firmware/tools/validate_atex_package.py")

def synthetic_package(model):
    env = f"gld_atex_model_{model}_dataset_workflow_wifi"
    blob, _, profile = validator._load_model_contract(model, ROOT / "firmware/gld/models")
    table = bytearray(b"\xff" * 96)
    table[:4] = bytes((0xAA, 0x50, 1, 2))
    table[4:8] = (0x9000).to_bytes(4, "little")
    table[8:12] = (0x5000).to_bytes(4, "little")
    table[32:36] = bytes((0xAA, 0x50, 0, 0x10))
    table[36:40] = (0x10000).to_bytes(4, "little")
    table[40:44] = (0x640000).to_bytes(4, "little")
    firmware = b"TEST-FAKE-IMAGE" + blob + profile.encode() + b"\0" + b"\0".join(validator.MARKERS)
    data = {"bootloader.bin": b"boot", "partitions.bin": bytes(table),
            "boot_app0.bin": b"boot-app", "firmware.bin": firmware}
    entries = [{"path": name, "offset": f"0x{validator.FLASH_LAYOUT[name]:08X}",
                "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
               for name, content in data.items()]
    manifest = dict(schemaVersion=2, packageType="pertamina-gld-prebuilt-firmware", deviceId="ANY",
        boardProfile=validator.ATEX_BOARD_PROFILE, environment=env, firmwareVersion="0.8.30",
        protocolVersion="1.0.0", configSchemaVersion="1.0.0", chip="esp32s3", baud=921600,
        createdAtUtc="20261112T120000Z", capabilities={"nativeSerial": True, "datasetWifi": True},
        source=dict(gitCommit="a"*40, gitTreeState="build-output", platformioCoreVersion="PlatformIO post-build hook",
                    platformioIniSha256="b"*64, buildCommand=f"pio run -e {env}", packagedAtUtc="20261112T120000Z"),
        flashSetSha256=bridge._manifest_flash_set_sha256(entries), flashFiles=entries)
    return manifest, {name: base64.b64encode(content).decode("ascii") for name, content in data.items()}, profile


class AtexAdmission(unittest.TestCase):
    def test_three_environments_are_validated_and_model_bound(self):
        for model in (1, 2, 3):
            manifest, files, profile = synthetic_package(model)
            with self.subTest(model=model):
                evidence = bridge.validate_atex_workflow(manifest, files, manifest["environment"], "1001")
                self.assertEqual(evidence["model"], model)
                self.assertEqual(evidence["profileId"], profile)
                bridge.validate_firmware_package(manifest, files, manifest["environment"], "1001")

    def test_bad_package_fails_before_any_port_access(self):
        manifest, files, _ = synthetic_package(1)
        bad = copy.deepcopy(manifest)
        bad["boardProfile"] = "GLD2"
        payload = dict(env=manifest["environment"], port="COM999", targetDeviceId="1001",
                       manifest=bad, packageFiles=files, resetNvs=False)
        with mock.patch.object(bridge, "require_atex_release"), mock.patch.object(bridge, "slot_holding_port") as port, self.assertRaisesRegex(RuntimeError, "profile"):
            bridge._firmware_upload_reserved(payload)
        port.assert_not_called()

    def test_hash_capability_and_wrong_model_are_rejected(self):
        manifest, files, _ = synthetic_package(1)
        for field in ("hash", "capabilities", "model"):
            m, f = copy.deepcopy(manifest), dict(files)
            if field == "hash": f["firmware.bin"] = base64.b64encode(b"bad").decode()
            elif field == "capabilities": m["capabilities"] = {"nativeSerial": True}
            else:
                m["environment"] = "gld_atex_model_2_dataset_workflow_wifi"
                m["source"]["buildCommand"] = "pio run -e " + m["environment"]
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                bridge.validate_atex_workflow(m, f, m["environment"], "1001")

    def test_preflash_delegates_identity_and_rejects_wrong_slot(self):
        manifest, files, _ = synthetic_package(1)
        payload = dict(env=manifest["environment"], port="COM999", targetDeviceId="1001",
                       manifest=manifest, packageFiles=files, resetNvs=False)
        reservation = bridge.reserve_flash_port("COM999")
        self.assertIsNotNone(reservation)
        self.addCleanup(bridge.release_flash_port, "COM999", reservation)
        fake = mock.Mock()
        fake.challenge_atex_identity.side_effect = RuntimeError("ATEX upload held: invalid challenge")
        with mock.patch.object(bridge, "require_atex_release"), mock.patch.object(bridge, "reject_atex_manifest_before_release"), \
             mock.patch.object(bridge, "slot_holding_port", return_value=1), \
             mock.patch.object(bridge, "get_serial_bridge", return_value=fake), self.assertRaisesRegex(RuntimeError, "invalid challenge"):
            bridge._firmware_upload_reserved(payload, _reservation=reservation)
        fake.challenge_atex_identity.assert_called_once_with("COM999", "1001", 8.0)
        fake.disconnect.assert_not_called()
        with mock.patch.object(bridge, "require_atex_release"), mock.patch.object(bridge, "reject_atex_manifest_before_release"), \
             mock.patch.object(bridge, "slot_holding_port", return_value=None), \
             mock.patch.object(bridge, "get_serial_bridge") as get_bridge, self.assertRaisesRegex(RuntimeError, "selected port"):
            bridge._firmware_upload_reserved(payload, _reservation=reservation)
        get_bridge.assert_not_called()

    def test_gld1_upload_uses_owned_reservation_through_preflight(self):
        manifest = dict(boardProfile="WROOM-1U-N16R8", chip="esp32s3", baud=921600,
                        firmwareVersion="test", protocolVersion="1", source={"gitCommit":"synthetic"})
        files = [({"path":"firmware.bin", "offset":"0x10000"}, b"synthetic-gld1")]
        payload = dict(env="gld", port="COM999", targetDeviceId="1001", resetNvs=False,
                       manifest=manifest, packageFiles={})
        opened = []
        class FakePort:
            def open(self): opened.append("open")
            def close(self): opened.append("close")
        fake_serial = type("FakeSerial", (), {"Serial": staticmethod(FakePort)})
        process = mock.Mock(stdout=[], wait=mock.Mock(return_value=0))
        upload_bridge = mock.Mock()
        with mock.patch.object(bridge, "validate_firmware_package", return_value=(manifest, files)), \
             mock.patch.object(bridge, "requires_gld1_nvs_reset_before_boot", return_value=False), \
             mock.patch.object(bridge, "slot_holding_port", return_value=None), \
             mock.patch.object(bridge, "get_serial_bridge", return_value=upload_bridge), \
             mock.patch.object(bridge, "serial", fake_serial), \
             mock.patch.object(bridge, "wait_for_reenumerated_port"), \
             mock.patch.object(bridge.time, "sleep"), \
             mock.patch.object(bridge, "shared_esptool_command", return_value=["synthetic-esptool"]), \
             mock.patch.object(bridge.subprocess, "Popen", return_value=process):
            result = bridge.firmware_upload(payload)
        self.assertTrue(result["ok"])
        self.assertEqual(opened, ["open", "close"])
        upload_bridge.disconnect.assert_called_once()
        self.assertFalse(bridge.is_flash_port_reserved("com999"))

    def test_release_gate_rejects_valid_package_before_port_reservation_or_disconnect(self):
        for model in (1, 2, 3):
            manifest, files, _ = synthetic_package(model)
            payload = dict(env=manifest["environment"], port="COM999", targetDeviceId="1001",
                           manifest=manifest, packageFiles=files, resetNvs=False)
            with self.subTest(model=model), mock.patch.object(bridge, "reserve_flash_port") as reserve, \
                 mock.patch.object(bridge, "slot_holding_port") as holder:
                with self.assertRaisesRegex(RuntimeError, "release gates"):
                    bridge.firmware_upload(payload)
                with self.assertRaisesRegex(RuntimeError, "release gates"):
                    bridge._firmware_upload_reserved(payload)
                reserve.assert_not_called()
                holder.assert_not_called()

    def test_atex_not_exempt_from_nvs_guards(self):
        manifest, files, _ = synthetic_package(2)
        payload = dict(env=manifest["environment"], port="COM999", targetDeviceId="1001",
                       manifest=manifest, packageFiles=files, resetNvs=True)
        with mock.patch.object(bridge, "require_atex_release"), mock.patch.object(bridge, "reject_atex_manifest_before_release"), mock.patch.object(bridge, "slot_holding_port") as port, self.assertRaisesRegex(RuntimeError, "Reset NVS"):
            bridge._firmware_upload_reserved(payload)
        port.assert_not_called()

    def test_legacy_atex_is_also_held_before_port_reservation(self):
        payload = dict(env="gld_atex", port="COM999", targetDeviceId="1001")
        with mock.patch.object(bridge, "reserve_flash_port") as reserve:
            with self.assertRaisesRegex(RuntimeError, "release gates"):
                bridge.firmware_upload(payload)
            with self.assertRaisesRegex(RuntimeError, "release gates"):
                bridge._firmware_upload_reserved(payload)
            reserve.assert_not_called()

    def test_relabelled_atex_manifest_and_marker_are_held(self):
        payload = dict(env="gld", port="COM999", targetDeviceId="1001",
                       manifest={"boardProfile": "GLD ATEX MotherBoardGLDVer2"})
        with mock.patch.object(bridge, "reserve_flash_port") as reserve:
            with self.assertRaisesRegex(RuntimeError, "release gates"):
                bridge.firmware_upload(payload)
            reserve.assert_not_called()
        payload["manifest"] = {"boardProfile": "WROOM-1U-N16R8"}
        verified = [({"path": "payload.bin"}, b"image GLD ATEX MotherBoardGLDVer2")]
        with mock.patch.object(bridge, "validate_firmware_package", return_value=(payload["manifest"], verified)), \
             mock.patch.object(bridge, "slot_holding_port") as holder:
            with self.assertRaisesRegex(RuntimeError, "release gates"):
                bridge._firmware_upload_reserved(payload)
            holder.assert_not_called()

    def test_known_legacy_atex_binary_is_held_even_if_relabelled(self):
        image = (ROOT / "apps/operator-hub/firmware-packages/gld_atex/latest/firmware.bin").read_bytes()
        self.assertIn(hashlib.sha256(image).hexdigest(), bridge.ATEX_KNOWN_BLOCKED_FIRMWARE_SHA256)
        payload = dict(env="gld", port="COM999", targetDeviceId="1001",
                       manifest={"boardProfile": "WROOM-1U-N16R8"})
        verified = [({"path": "renamed-image.bin"}, image)]
        with mock.patch.object(bridge, "validate_firmware_package", return_value=(payload["manifest"], verified)), \
             mock.patch.object(bridge, "slot_holding_port") as holder:
            with self.assertRaisesRegex(RuntimeError, "release gates"):
                bridge._firmware_upload_reserved(payload)
            holder.assert_not_called()

if __name__ == "__main__": unittest.main()
