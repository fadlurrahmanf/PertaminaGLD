"""Host-only hotspot package routing and honest post-flash verification gates."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from test_child_package_validators import GLD_BRIDGE as child, load_bridge, package_for

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/operator-hub"))
hub = load_bridge("wireless_package_hub", "apps/operator-hub/bridge.py")
ENVIRONMENTS = {f"model_{number}_dataset_wifi": f"gld_model_{number}_dataset_wifi"
                for number in (1, 2, 3)}


class WirelessPackageSelection(unittest.TestCase):
    environments = ENVIRONMENTS
    catalog_guard = hub.GLD_DATASET_WIFI_ENVIRONMENTS
    title_phrase = "Hotspot Dataset 500 ms"
    mode_phrase = "mode khusus"

    def instance(self):
        handler = object.__new__(hub.Handler)
        handler.server = SimpleNamespace(server_address=("127.0.0.1", 5173))
        return handler

    def test_catalog_adds_three_explicit_models_and_preserves_legacy_choices(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(hub, "HUB_DIR", Path(temporary)):
            for environment in self.environments.values():
                manifest, _ = package_for(child, environment, {})
                latest = Path(temporary) / "firmware-packages" / environment / "latest"
                latest.mkdir(parents=True)
                (latest / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            catalog = hub.firmware_package_options()["gld"]
        for choice, environment in self.environments.items():
            self.assertEqual(catalog["environments"][choice], environment)
            self.assertTrue(catalog["packages"][environment]["available"])
            self.assertFalse(catalog["packages"][environment]["requiresNvsResetBeforeBoot"])
            label = next(model["label"] for model in catalog["models"] if model["value"] == choice)
            self.assertIn(self.title_phrase, label)
            self.assertIn(self.mode_phrase, label)
        for choice, environment in {"gld": "gld", "model_1": "gld_model_1",
                                    "model_2": "gld_model_2", "model_3": "gld_model_3",
                                    "gld_v2": "gld_v2", "gld_atex": "gld_atex"}.items():
            self.assertEqual(catalog["environments"][choice], environment)
        self.assertEqual(self.catalog_guard, frozenset(self.environments.values()))

    def test_missing_new_package_fails_before_any_device_access(self):
        for choice, environment in self.environments.items():
            with (self.subTest(environment=environment),
                  mock.patch.object(hub, "package_manifest_summary", return_value={"available": False}) as package,
                  mock.patch.object(hub, "simple_device_state") as device,
                  mock.patch.object(hub, "child_request") as request):
                with self.assertRaisesRegex(RuntimeError, "unavailable"):
                    self.instance()._simple_firmware_upload(dict(device="gld", port="COM999", model=choice))
                package.assert_called_once_with(environment)
                device.assert_not_called()
                request.assert_not_called()

    def test_unknown_model_cannot_select_an_arbitrary_environment(self):
        with mock.patch.object(hub, "simple_device_state") as device:
            with self.assertRaisesRegex(ValueError, "selected GLD model package"):
                self.instance()._simple_firmware_upload(dict(device="gld", port="COM999",
                    model="model_4_dataset_wifi", env="gld_model_1_dataset_wifi"))
            device.assert_not_called()

    def test_hotspot_initial_or_reset_nvs_rejected_before_any_child_or_device_action(self):
        for choice in self.environments:
            for flags in ({"resetNvs": True, "resetNvsConfirmation": "RESET NVS"},
                          {"initialFirmware": True, "resetNvs": False}):
                with (self.subTest(model=choice, flags=flags),
                      mock.patch.object(hub, "simple_device_state") as device,
                      mock.patch.object(hub, "child_request") as request,
                      mock.patch.object(hub, "package_manifest_summary") as package):
                    with self.assertRaisesRegex(ValueError, "Reset NVS OFF"):
                        self.instance()._simple_firmware_upload(dict(device="gld", port="COM999", model=choice, **flags))
                    device.assert_not_called()
                    request.assert_not_called()
                    package.assert_not_called()

    def exercise_mock_upload(self, choice, environment):
        manifest, files = package_for(child, environment, {})
        package = dict(manifest=manifest, packageFiles=files)
        current = dict(connected=True, port="COM999", info=dict(deviceId="1001", firmwareVersion="1.2.3"))
        responses = []
        def child_request(_host, _device, method, path, payload=None, **_kwargs):
            if method == "GET":
                self.assertEqual(path, f"/api/firmware/package?env={environment}")
                return package
            self.assertEqual(path, "/api/firmware/upload")
            self.assertEqual(payload["env"], environment)
            self.assertEqual(payload["targetDeviceId"], "1001")
            self.assertIs(payload["resetNvs"], False)
            return dict(ok=True, env=environment, nvsReset=False)
        with (mock.patch.object(hub, "package_manifest_summary", return_value={"available": True}),
              mock.patch.object(hub, "simple_device_state", return_value=current),
              mock.patch.object(hub, "child_request", side_effect=child_request) as request,
              mock.patch.object(hub, "wait_for_readback", return_value=current) as readback,
              mock.patch.object(hub, "send_and_confirm") as command,
              mock.patch.object(hub, "add_activity"),
              mock.patch.object(hub, "json_response", side_effect=lambda _handler, value: responses.append(value))):
            self.instance()._simple_firmware_upload(dict(device="gld", port="COM999", model=choice,
                                                       env="ignored-untrusted-env", resetNvs=False))
        return responses[0], request, readback, command

    def test_hotspot_flash_receipt_requires_wireless_verification_without_serial_reconnect(self):
        for choice, environment in self.environments.items():
            with self.subTest(environment=environment):
                result, request, readback, command = self.exercise_mock_upload(choice, environment)
                readback.assert_not_called()
                command.assert_not_called()
                self.assertEqual(request.call_count, 2)
                self.assertTrue(result["flashToolCompleted"])
                self.assertFalse(result["deviceVerified"])
                self.assertIsNone(result["readback"])
                self.assertEqual(result["verificationPending"], "hotspot")
                self.assertEqual(result["selectedEnvironment"], environment)
                self.assertIn("Connect GLD", result["nextStep"])
                self.assertNotIn("flashVerified", result)

    def test_existing_normal_upload_retains_serial_identity_readback(self):
        result, request, readback, _command = self.exercise_mock_upload("model_2", "gld_model_2")
        readback.assert_called_once_with("127.0.0.1", "gld", "COM999", timeout=35.0)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(result["readback"]["info"]["deviceId"], "1001")
        self.assertNotIn("verificationPending", result)

    def test_direct_expert_upload_rejects_hotspot_reset_before_device_or_provisioning(self):
        for environment in self.environments.values():
            manifest, files = package_for(child, environment, {})
            payload = dict(env=environment, port="COM999", targetDeviceId="1001",
                           manifest=manifest, packageFiles=files, resetNvs=True,
                           resetNvsConfirmation="RESET NVS")
            with (self.subTest(environment=environment),
                  mock.patch.object(child, "load_canonical_gld_aes_key") as provision,
                  mock.patch.object(child, "get_serial_bridge") as serial,
                  mock.patch.object(child, "probe_port") as probe,
                  mock.patch.object(child.subprocess, "Popen") as process,
                  mock.patch.object(child.subprocess, "run") as run):
                with self.assertRaisesRegex(RuntimeError, "Reset NVS must be OFF"):
                    child._firmware_upload_reserved(payload)
                for forbidden in (provision, serial, probe, process, run):
                    forbidden.assert_not_called()

    def test_child_validator_remains_strict_for_every_new_environment(self):
        for environment in self.environments.values():
            with self.subTest(environment=environment):
                manifest, files = package_for(child, environment, {})
                validated, _ = child.validate_firmware_package(manifest, files, environment, "1001")
                self.assertEqual(validated["environment"], environment)
                with self.assertRaisesRegex(RuntimeError, "does not match"):
                    child.validate_firmware_package(manifest, files, "gld_model_1", "1001")
                corrupt = copy.deepcopy(manifest)
                corrupt["source"]["firmwareTreeSnapshotSha256"] = "invalid"
                with self.assertRaisesRegex(RuntimeError, "snapshot SHA-256"):
                    child.validate_firmware_package(corrupt, files, environment, "1001")
                corrupt = copy.deepcopy(manifest)
                corrupt["wirelessDatasetPassword"] = "must-never-be-a-manifest-field"
                with self.assertRaisesRegex(RuntimeError, "unsupported schema-v2 fields"):
                    child.validate_firmware_package(corrupt, files, environment, "1001")

    def test_new_environments_do_not_inherit_legacy_downgrade_nvs_reset(self):
        for environment in self.environments.values():
            manifest, _ = package_for(child, environment, {})
            manifest["firmwareVersion"] = "0.8.38"
            manifest["source"]["gitCommit"] = "69a493c32d2500134a21e029820cd4addea1794a"
            self.assertFalse(child.requires_gld1_nvs_reset_before_boot(manifest))
            self.assertFalse(hub.requires_gld1_nvs_reset_before_boot(manifest))


class ReplayPackageSelection(WirelessPackageSelection):
    environments = {f"model_{n}_dataset_replay_wifi": f"gld_model_{n}_dataset_replay_wifi" for n in (1, 2, 3)}
    catalog_guard = hub.GLD_DATASET_REPLAY_ENVIRONMENTS
    title_phrase = "Hotspot buffer 5 menit"
    mode_phrase = "tahap 2"


if __name__ == "__main__":
    unittest.main()
