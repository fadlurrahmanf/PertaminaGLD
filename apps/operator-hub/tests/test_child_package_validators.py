from __future__ import annotations

import base64
import hashlib
import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def load_bridge(name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CH_BRIDGE = load_bridge("child_ch_bridge", "apps/ch-operator/bridge.py")
GW_BRIDGE = load_bridge("child_gw_bridge", "apps/gw-operator/bridge.py")
GLD_BRIDGE = load_bridge("child_gld_bridge", "apps/gld-operator/bridge.py")


def package_for(bridge, environment: str, extras: dict[str, str]):
    content = b"firmware-test-byte"
    file_hash = hashlib.sha256(content).hexdigest()
    flash_files = [{
        "path": "firmware.bin",
        "offset": "0x00010000",
        "size": len(content),
        "sha256": file_hash,
    }]
    manifest = {
        "schemaVersion": 2,
        "packageType": "pertamina-gld-prebuilt-firmware",
        "deviceId": "ANY",
        "boardProfile": "test profile",
        "environment": environment,
        "firmwareVersion": "1.2.3",
        "protocolVersion": "1.2.3",
        "configSchemaVersion": "1.2.3",
        "chip": "esp32s3",
        "baud": 921600,
        "createdAtUtc": "20260825T120000Z",
        "source": {
            "gitCommit": "a" * 40,
            "gitTreeState": "dirty",
            "gitTreeStateScope": "firmware/",
            "firmwareTreeSnapshotSha256": "b" * 64,
            "platformioCoreVersion": "PlatformIO post-build hook",
            "platformioIniSha256": "c" * 64,
            "buildCommand": f"pio run -e {environment}",
            "packagedAtUtc": "20260825T120001Z",
        },
        "flashSetSha256": bridge._manifest_flash_set_sha256(flash_files),
        "flashFiles": flash_files,
        **extras,
    }
    files = {"firmware.bin": base64.b64encode(content).decode("ascii")}
    return manifest, files


class ChildPackageValidatorTests(unittest.TestCase):
    def test_ch_accepts_board_shape_and_dirty_source_identity(self) -> None:
        manifest, files = package_for(CH_BRIDGE, "ch_small", {"boardShape": "rectangle"})
        validated, _ = CH_BRIDGE.validate_firmware_package(manifest, files, "ch_small", "0010")
        self.assertEqual(validated["boardShape"], "rectangle")

    def test_gateway_accepts_board_transport_and_dirty_source_identity(self) -> None:
        manifest, files = package_for(
            GW_BRIDGE,
            "gw_small_tls",
            {"boardShape": "rectangle", "mqttTransport": "tls"},
        )
        validated, _ = GW_BRIDGE.validate_firmware_package(manifest, files, "gw_small_tls", "0001")
        self.assertEqual(validated["mqttTransport"], "tls")

    def test_gateway_rejects_metadata_for_another_board(self) -> None:
        manifest, files = package_for(
            GW_BRIDGE,
            "gw_small_tls",
            {"boardShape": "circle", "mqttTransport": "tls"},
        )
        with self.assertRaisesRegex(RuntimeError, "boardShape"):
            GW_BRIDGE.validate_firmware_package(manifest, files, "gw_small_tls", "0001")

    def test_legacy_ch_package_remains_accepted_without_new_board_metadata(self) -> None:
        for environment in ("ch", "chFieldtest"):
            with self.subTest(environment=environment):
                manifest, files = package_for(CH_BRIDGE, environment, {})
                validated, _ = CH_BRIDGE.validate_firmware_package(
                    manifest, files, environment, "0010"
                )
                self.assertNotIn("boardShape", validated)

    def test_legacy_gateway_package_remains_accepted_without_new_metadata(self) -> None:
        for environment in ("gw", "gw_hello_ack_fieldtest"):
            with self.subTest(environment=environment):
                manifest, files = package_for(GW_BRIDGE, environment, {})
                validated, _ = GW_BRIDGE.validate_firmware_package(
                    manifest, files, environment, "0001"
                )
                self.assertNotIn("boardShape", validated)
                self.assertNotIn("mqttTransport", validated)

    def test_gld_accepts_dirty_source_identity_hash(self) -> None:
        manifest, files = package_for(GLD_BRIDGE, "gld_v2", {})
        validated, _ = GLD_BRIDGE.validate_firmware_package(manifest, files, "gld_v2", "1001")
        self.assertEqual(validated["source"]["gitTreeState"], "dirty")

    def test_legacy_source_hash_and_build_timestamps_remain_accepted(self) -> None:
        manifest, files = package_for(GLD_BRIDGE, "gld_v2", {})
        source = manifest["source"]
        source.pop("gitTreeStateScope")
        source["firmwareSourceTreeSha256"] = source.pop("firmwareTreeSnapshotSha256")
        source.pop("packagedAtUtc")
        source["buildStartedAtUtc"] = "20260825T120000Z"
        source["buildCompletedAtUtc"] = "20260825T120001Z"
        validated, _ = GLD_BRIDGE.validate_firmware_package(
            manifest, files, "gld_v2", "1001"
        )
        self.assertIn("firmwareSourceTreeSha256", validated["source"])

    def test_rejects_misleading_mixed_package_and_build_timestamps(self) -> None:
        manifest, files = package_for(GLD_BRIDGE, "gld_v2", {})
        manifest["source"]["buildStartedAtUtc"] = "20260825T120000Z"
        manifest["source"]["buildCompletedAtUtc"] = "20260825T120001Z"
        with self.assertRaisesRegex(RuntimeError, "packagedAtUtc or the legacy"):
            GLD_BRIDGE.validate_firmware_package(manifest, files, "gld_v2", "1001")


if __name__ == "__main__":
    unittest.main()
