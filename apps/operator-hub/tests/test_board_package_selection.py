from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


HUB_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HUB_DIR))
SPEC = importlib.util.spec_from_file_location("operator_hub_bridge", HUB_DIR / "bridge.py")
assert SPEC and SPEC.loader
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)
import preflight  # noqa: E402


class FirmwareEnvironmentSelectionTests(unittest.TestCase):
    def test_ch_board_mappings_are_exact(self) -> None:
        self.assertEqual(
            bridge.resolve_firmware_environment("ch", {"boardFormFactor": "small"})["environment"],
            "ch_small",
        )
        self.assertEqual(
            bridge.resolve_firmware_environment("ch", {"boardFormFactor": "large"})["environment"],
            "ch_large",
        )

    def test_gateway_board_and_transport_mappings_are_exact(self) -> None:
        expected = {
            ("small", "non_tls"): "gw_small",
            ("large", "non_tls"): "gw_large",
            ("small", "tls"): "gw_small_tls",
            ("large", "tls"): "gw_large_tls",
        }
        for (board, transport), environment in expected.items():
            with self.subTest(board=board, transport=transport):
                selected = bridge.resolve_firmware_environment(
                    "gw",
                    {"boardFormFactor": board, "mqttTransport": transport},
                )
                self.assertEqual(selected["environment"], environment)

    def test_missing_board_selection_never_falls_back_to_legacy_packages(self) -> None:
        for device in ("ch", "gw"):
            with self.subTest(device=device):
                with self.assertRaises(ValueError):
                    bridge.resolve_firmware_environment(device, {})

    def test_partial_or_invalid_new_selection_is_rejected(self) -> None:
        invalid = (
            ("gw", {"boardFormFactor": "small"}),
            ("gw", {"mqttTransport": "tls"}),
            ("gw", {"boardFormFactor": "triangle", "mqttTransport": "tls"}),
            ("ch", {"boardFormFactor": "small", "mqttTransport": "non_tls"}),
        )
        for device, payload in invalid:
            with self.subTest(device=device, payload=payload):
                with self.assertRaises(ValueError):
                    bridge.resolve_firmware_environment(device, payload)

    def test_manifest_environment_must_match_selected_environment(self) -> None:
        package = {
            "manifest": {
                "environment": "gw_small_tls",
                "boardShape": "rectangle",
                "mqttTransport": "tls",
            },
            "packageFiles": {"firmware.bin": "AA=="},
        }
        manifest = bridge.validate_selected_package(package, "gw_small_tls")
        self.assertEqual(manifest["environment"], "gw_small_tls")
        with self.assertRaisesRegex(RuntimeError, "environment mismatch"):
            bridge.validate_selected_package(package, "gw_large_tls")

    def test_manifest_board_and_transport_metadata_must_match_environment(self) -> None:
        package = {
            "manifest": {
                "environment": "gw_small_tls",
                "boardShape": "circle",
                "mqttTransport": "non_tls",
            },
            "packageFiles": {"firmware.bin": "AA=="},
        }
        with self.assertRaisesRegex(RuntimeError, "boardShape mismatch"):
            bridge.validate_selected_package(package, "gw_small_tls")

    def test_catalog_exposes_operator_labels_and_all_environments(self) -> None:
        catalog = bridge.firmware_package_options()
        self.assertEqual([item["label"] for item in catalog["ch"]["boards"]], ["Rectangle (kecil)", "Circle (besar)"])
        self.assertEqual(catalog["gw"]["environments"]["large"]["tls"], "gw_large_tls")
        self.assertEqual(catalog["gld"]["environments"]["gld_v2"], "gld_v2")
        expected = {
            "gld": {"gld_model_1", "gld_model_2", "gld_model_3", "gld_v2"},
            "ch": {"ch_small", "ch_large"},
            "gw": {"gw_small", "gw_large", "gw_small_tls", "gw_large_tls"},
        }
        for device, environments in expected.items():
            with self.subTest(device=device):
                self.assertEqual(set(catalog[device]["packages"]), environments)
                self.assertNotIn(device, catalog[device]["packages"])
                for environment in environments:
                    package = catalog[device]["packages"][environment]
                    manifest_path = HUB_DIR / "firmware-packages" / environment / "latest" / "manifest.json"
                    manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
                    self.assertEqual(package["firmwareVersion"], manifest["firmwareVersion"])

    def test_package_catalog_fails_gracefully_when_manifest_is_missing_or_mismatched(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(bridge, "HUB_DIR", Path(directory)):
            missing = bridge.package_manifest_summary("gw_small_tls")
            self.assertIs(missing["available"], False)
            self.assertEqual(missing["error"], "manifest missing")
            empty_catalog = bridge.firmware_package_options()
            self.assertTrue(
                all(
                    package["available"] is False
                    for device in empty_catalog.values()
                    for package in device["packages"].values()
                )
            )

            latest = Path(directory) / "firmware-packages" / "ch_small" / "latest"
            latest.mkdir(parents=True)
            (latest / "manifest.json").write_text(
                '{"environment":"ch","firmwareVersion":"9.9.9"}',
                encoding="utf-8",
            )
            mismatch = bridge.package_manifest_summary("ch_small")
            self.assertIs(mismatch["available"], False)
            self.assertEqual(mismatch["error"], "manifest environment mismatch")

    def test_upload_rejects_missing_exact_package_before_device_access(self) -> None:
        instance = object.__new__(bridge.Handler)
        with (
            mock.patch.object(
                bridge,
                "package_manifest_summary",
                return_value={"environment": "gld_model_1", "available": False, "error": "manifest missing"},
            ),
            mock.patch.object(bridge, "simple_device_state") as device_state,
        ):
            with self.assertRaisesRegex(RuntimeError, "selected package gld_model_1 is unavailable"):
                instance._simple_firmware_upload({"device": "gld", "port": "COM1", "model": "model_1"})
        device_state.assert_not_called()

    def test_nvs_reset_expects_each_firmware_default_identity(self) -> None:
        current = {"gld": "1200", "ch": "0022", "gw": "0003"}
        for device, default_identity in bridge.DEFAULT_DEVICE_IDENTITIES.items():
            with self.subTest(device=device):
                self.assertEqual(
                    bridge.expected_identity_after_upload(device, current[device], reset_nvs=True),
                    default_identity,
                )

    def test_upload_without_nvs_reset_preserves_identified_identity(self) -> None:
        self.assertEqual(
            bridge.expected_identity_after_upload("gw", "0x0003", reset_nvs=False),
            "0003",
        )
        with self.assertRaisesRegex(RuntimeError, "identified device ID"):
            bridge.expected_identity_after_upload("ch", None, reset_nvs=False)

    def test_preflight_requires_every_selectable_board_package(self) -> None:
        expected = {
            "gld_model_1",
            "gld_model_2",
            "gld_model_3",
            "gld_v2",
            "ch_small",
            "ch_large",
            "gw_small",
            "gw_large",
            "gw_small_tls",
            "gw_large_tls",
        }
        self.assertEqual(set(preflight.REQUIRED_ENVIRONMENTS), expected)
        self.assertTrue(
            {"gld", "gldFieldtest", "ch", "chFieldtest", "gw"}.isdisjoint(
                preflight.REQUIRED_ENVIRONMENTS
            )
        )

    def test_preflight_rejects_manifest_in_the_wrong_environment_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.json"
            manifest_path.write_text(
                '{"environment":"gw_small","flashFiles":[{"path":"firmware.bin","size":1,"sha256":"00"}]}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "does not match"):
                preflight._verify_manifest(manifest_path, "gw_small_tls")

    def test_preflight_never_uses_valid_archive_when_latest_is_corrupt(self) -> None:
        import hashlib
        import json

        with tempfile.TemporaryDirectory() as directory:
            packages = Path(directory) / "firmware-packages"
            archive = packages / "gw_small" / "archive-older"
            latest = packages / "gw_small" / "latest"
            archive.mkdir(parents=True)
            latest.mkdir(parents=True)
            content = b"x"
            manifest = {
                "environment": "gw_small",
                "boardShape": "rectangle",
                "mqttTransport": "non_tls",
                "flashFiles": [{
                    "path": "firmware.bin",
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }],
            }
            (archive / "firmware.bin").write_bytes(content)
            (archive / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (latest / "manifest.json").write_text(
                json.dumps({
                    "environment": "gw_small",
                    "boardShape": "rectangle",
                    "mqttTransport": "non_tls",
                }),
                encoding="utf-8",
            )
            with (
                mock.patch.object(preflight, "FIRMWARE_PACKAGES_DIR", packages),
                mock.patch.object(preflight, "REQUIRED_ENVIRONMENTS", ("gw_small",)),
            ):
                result = preflight._firmware_packages_check()
        self.assertEqual(result["state"], "error")
        self.assertIn("manifest has no flashFiles entries", result["detail"])


class MqttTlsConfigurationTests(unittest.TestCase):
    BASE_PAYLOAD = {
        "host": "broker.example.test",
        "port": 8883,
        "username": "operator",
        "password": "secret",
    }
    TEST_CA = (
        "-----BEGIN CERTIFICATE-----\n"
        + ("A" * 256)
        + "\n-----END CERTIFICATE-----"
    )

    def test_legacy_mqtt_request_remains_non_tls(self) -> None:
        config, transport = bridge.mqtt_configuration_from_payload(dict(self.BASE_PAYLOAD), {})
        self.assertEqual(transport, "non_tls")
        self.assertNotIn("tlsCaPem", config)
        self.assertNotIn("ntpHost", config)

    def test_tls_requires_explicit_firmware_markers_and_adds_exact_fields(self) -> None:
        payload = {
            **self.BASE_PAYLOAD,
            "mqttTransport": "tls",
            "tlsCaPem": self.TEST_CA,
            "ntpHost": "pool.ntp.org",
        }
        with mock.patch.object(bridge.ssl, "PEM_cert_to_DER_cert", return_value=b"certificate" * 20):
            config, transport = bridge.mqtt_configuration_from_payload(
                payload,
                {"mqttTransport": "tls", "tlsCapable": True},
            )
        self.assertEqual(transport, "tls")
        self.assertTrue(config["tlsCaPem"].startswith("-----BEGIN CERTIFICATE-----\n"))
        self.assertTrue(config["tlsCaPem"].endswith("\n-----END CERTIFICATE-----"))
        self.assertEqual(config["ntpHost"], "pool.ntp.org")

    def test_tls_is_fail_closed_without_tls_firmware_marker(self) -> None:
        payload = {
            **self.BASE_PAYLOAD,
            "mqttTransport": "tls",
            "tlsCaPem": self.TEST_CA,
            "ntpHost": "pool.ntp.org",
        }
        with self.assertRaisesRegex(RuntimeError, "does not explicitly identify"):
            bridge.mqtt_configuration_from_payload(payload, {"mqttTransport": "non_tls", "tlsCapable": False})

    def test_non_tls_rejects_stale_tls_material(self) -> None:
        payload = {
            **self.BASE_PAYLOAD,
            "mqttTransport": "non_tls",
            "tlsCaPem": self.TEST_CA,
            "ntpHost": "pool.ntp.org",
        }
        with self.assertRaisesRegex(ValueError, "only valid"):
            bridge.mqtt_configuration_from_payload(payload, {"mqttTransport": "non_tls"})

    def test_tls_contract_matches_firmware_limits(self) -> None:
        with self.assertRaisesRegex(ValueError, "256 to 3900 bytes"):
            bridge.validate_tls_ca_pem("A" * 255)
        with self.assertRaisesRegex(ValueError, "256 to 3900 bytes"):
            bridge.validate_tls_ca_pem("A" * 3901)
        with mock.patch.object(bridge.ssl, "PEM_cert_to_DER_cert", return_value=b"certificate" * 20):
            with self.assertRaisesRegex(ValueError, "exactly one"):
                bridge.validate_tls_ca_pem(f"{self.TEST_CA}\n{self.TEST_CA}")
        with self.assertRaisesRegex(ValueError, "64 UTF-8 bytes"):
            bridge.validate_ntp_host("a" * 65)

    def test_gateway_fields_use_utf8_byte_limits_without_truncation(self) -> None:
        bridge.validate_gateway_text_field("Wi-Fi SSID", "A" * 32, required=True)
        with self.assertRaisesRegex(ValueError, "32 UTF-8 bytes"):
            bridge.validate_gateway_text_field("Wi-Fi SSID", "é" * 17, required=True)
        with self.assertRaisesRegex(ValueError, "64 UTF-8 bytes"):
            bridge.validate_gateway_text_field("MQTT host", "h" * 65, required=True)
        with self.assertRaisesRegex(ValueError, "NUL"):
            bridge.validate_gateway_text_field("MQTT password", "secret\x00tail")

    def test_gateway_serial_command_is_bounded_to_firmware_buffer(self) -> None:
        self.assertLessEqual(
            len(bridge.build_gateway_json_command("SET_MQTT_CONFIG_JSON", {"host": "broker"}).encode("utf-8")),
            bridge.GATEWAY_SERIAL_LINE_MAX_BYTES,
        )
        with self.assertRaisesRegex(ValueError, "firmware accepts at most 6143 bytes"):
            bridge.build_gateway_json_command("SET_MQTT_CONFIG_JSON", {"tlsCaPem": "A" * 6200})

    def test_serial_overflow_ack_is_reported_without_waiting_for_expected_marker(self) -> None:
        with mock.patch.object(
            bridge,
            "child_request",
            side_effect=[
                {"sequence": 7},
                {"ok": True},
                {"lines": [{"line": "GW_CMD_ACK cmd=SERIAL status=error message=line_too_long"}]},
            ],
        ):
            with self.assertRaisesRegex(RuntimeError, "line_too_long"):
                bridge.send_and_confirm(
                    "127.0.0.1",
                    "gw",
                    "SET_MQTT_CONFIG_JSON {}",
                    "SET_MQTT_CONFIG",
                )

    def test_pem_is_canonicalized_before_serialization(self) -> None:
        padded = self.TEST_CA.replace("A" * 256, ("A\n" * 256).strip())
        with mock.patch.object(bridge.ssl, "PEM_cert_to_DER_cert", return_value=b"certificate" * 20):
            canonical = bridge.validate_tls_ca_pem(padded)
        self.assertNotIn("A\nA\nA", canonical)
        self.assertLess(len(canonical.encode("utf-8")), len(padded.encode("utf-8")))

    def test_canonical_pem_must_still_fit_gateway_storage(self) -> None:
        with mock.patch.object(bridge.ssl, "PEM_cert_to_DER_cert", return_value=b"A" * 2850):
            with self.assertRaisesRegex(ValueError, "Canonical Root CA PEM.*3900 bytes"):
                bridge.validate_tls_ca_pem(self.TEST_CA)


class SimpleHubUiContractTests(unittest.TestCase):
    def test_ui_requires_board_and_gateway_transport_choices(self) -> None:
        source = (HUB_DIR / "public" / "js" / "hub.js").read_text(encoding="utf-8")
        for marker in (
            "firmwareUploadBoard",
            "Pilih bentuk board",
            "Rectangle = board kecil. Circle = board besar.",
            "firmwareUploadTransport",
            "Pilih transport MQTT",
            "boardFormFactor",
            "mqttTransport",
        ):
            self.assertIn(marker, source)

    def test_tls_inputs_and_payload_fields_are_present(self) -> None:
        html = (HUB_DIR / "public" / "index.html").read_text(encoding="utf-8")
        source = (HUB_DIR / "public" / "js" / "hub.js").read_text(encoding="utf-8")
        for field_id in ("mqttTransportSelect", "mqttTlsCaInput", "mqttNtpHostInput"):
            self.assertIn(field_id, html)
            self.assertIn(field_id, source)
        self.assertIn("tlsCaPem", source)
        self.assertIn("ntpHost", source)

    def test_tls_provisioning_queries_runtime_transport_markers(self) -> None:
        source = (HUB_DIR / "bridge.py").read_text(encoding="utf-8")
        mqtt_handler = source[source.index("def _simple_config_mqtt"):source.index("def _simple_firmware_upload")]
        self.assertIn('simple_device_state(host, "gw", query=True)', mqtt_handler)

    def test_ui_uses_active_device_version_and_exact_selected_package_catalog(self) -> None:
        source = (HUB_DIR / "public" / "js" / "hub.js").read_text(encoding="utf-8")
        backend = (HUB_DIR / "bridge.py").read_text(encoding="utf-8")
        for marker in (
            "packageOptions.packages",
            "packageCatalog[selectedEnvironment]",
            "selectedPackage.firmwareVersion",
            "info?.firmwareVersion",
            "Versi firmware aktif belum dibaca",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("overview.packages?.[active]", source)
        self.assertNotIn("def latest_package", backend)
        overview_handler = backend[backend.index("def _handle_simple_overview"):backend.index("def _handle_preflight")]
        self.assertNotIn('"packages"', overview_handler)


if __name__ == "__main__":
    unittest.main()
