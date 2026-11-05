"""Synthetic-only offline fixtures; no COM, service, database or network access."""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from unittest import mock

TOOL = Path(__file__).resolve().parents[1] / "handover_check.py"
spec = importlib.util.spec_from_file_location("handover_check_under_test", TOOL)
check = importlib.util.module_from_spec(spec); spec.loader.exec_module(check)
RESOLVER = TOOL.parents[1] / "apps/gld-operator/workflow_credentials.py"


class HandoverCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.secret = "SYNTHETIC_PRIVATE_MUST_NOT_APPEAR"
        for child in ("gld-operator", "ch-operator"):
            self.put(f"apps/{child}/python-embed/python.exe", b"inert-python")
        self.put("apps/lib/run_esptool.py", b"# inert runner")
        self.put("apps/lib/esptool/esptool.py", b"# inert esptool")
        for name in ("__init__.py", "_core.py", "_handshake.py"):
            self.put("apps/gld-operator/vendor/wireless/websocket/" + name, b"# inert fixture")
        self.put("apps/gld-operator/workflow_credentials.py", RESOLVER.read_bytes())
        profiles = {"schemaVersion": 1, "protocol": "gld-dataset-wifi/3", "models": {}}
        for number, env in enumerate(check.ENVIRONMENTS, 1):
            prefix = f"apps/operator-hub/firmware-packages/{env}/latest/"
            entries = []
            for name, offset in check.FLASH_FILES.items():
                raw = b"fixture-head" + self.secret.encode() + b"\0" + bytes([number])
                if name != "firmware.bin": raw = (name + str(number)).encode()
                self.put(prefix + name, raw)
                entries.append({"path": name, "offset": hex(offset), "size": len(raw),
                                "sha256": hashlib.sha256(raw).hexdigest()})
            manifest = {"schemaVersion": 2, "packageType": "pertamina-gld-prebuilt-firmware",
                        "environment": env, "chip": "esp32s3", "flashFiles": entries,
                        "capabilities": {"nativeSerial": True, "datasetWifi": True}}
            raw = json.dumps(manifest, indent=2).encode()
            self.put(prefix + "manifest.json", raw)
            self.put(prefix + "manifest.sha256", (hashlib.sha256(raw).hexdigest() + "  manifest.json\n").encode())
            profiles["models"][env] = {"firmwareSha256": entries[-1]["sha256"],
                                       "passwordOffset": len(b"fixture-head"), "passwordLength": len(self.secret)}
        self.put("apps/gld-operator/workflow-connection-profiles.json", json.dumps(profiles).encode())
        self.state = self.root / "state/system.json"
        self.system = {"schemaVersion": 1, "storage": "plaintext",
                       "serverEnv": {"GLD_AES128_KEY_HEX": "abcdef1234567890" * 2, "GLD_KEY_ID": "1",
                                     "PGL_COMMAND_AUTH_TOKEN": self.secret, "MQTT_PASS": "different-valid-original"},
                       "broker": {"host": "127.0.0.1", "port": 1884,
                                  "username": self.secret, "password": self.secret}}
        self.put("state/system.json", json.dumps(self.system).encode())
        self.runtime = self.root / "runtime"
        self.put("runtime/node/node.exe", b"inert node")
        self.put("runtime/node-red/red.js", b"// inert Node-RED")
        self.put("runtime/node-red/package.json", b'{"name":"node-red","version":"5.0.1"}')
        self.run_mock = mock.patch.object(check, "_run", side_effect=self.run_fixture); self.run_mock.start()
        self.driver_mock = mock.patch.object(check, "_driver_inventory", return_value={
            "status": "skip", "code": "ch340_driver_not_observed",
            "details": {"present": False, "physicalUsbRequired": False}}); self.driver_mock.start()

    def tearDown(self):
        self.driver_mock.stop(); self.run_mock.stop(); self.temp.cleanup()

    def put(self, relative, data):
        path = self.root / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        return path

    def run_fixture(self, args, **_kwargs):
        if "-c" in args and "import serial" in args[-1]:
            return subprocess.CompletedProcess(args, 0, "PY_SERIAL_OK\n", "")
        if args[-1] == "version":
            return subprocess.CompletedProcess(args, 0, "4.11.0\n", "")
        if args[-1] == "--version":
            return subprocess.CompletedProcess(args, 0, "v26.5.0\n", "")
        self.fail("Unexpected process invocation")

    def result(self):
        return check.check(self.root, self.state, self.runtime)

    def outcome(self, result, name):
        return next(item for item in result["checks"] if item["name"] == name)

    def rewrite_manifest(self, number, mutate):
        folder = self.root / f"apps/operator-hub/firmware-packages/{check.ENVIRONMENTS[number-1]}/latest"
        value = json.loads((folder / "manifest.json").read_text()); mutate(value)
        raw = json.dumps(value).encode(); (folder / "manifest.json").write_bytes(raw)
        (folder / "manifest.sha256").write_text(hashlib.sha256(raw).hexdigest() + "  manifest.json\n")

    def test_complete_fixture_passes_and_output_contains_no_secrets_or_private_paths(self):
        result = self.result(); self.assertTrue(result["ok"])
        self.assertEqual(result["counts"], {"pass": 10, "fail": 0, "skip": 1})
        output = json.dumps(result)
        for private in (self.secret, self.system["serverEnv"]["GLD_AES128_KEY_HEX"], str(self.root), "different-valid-original"):
            self.assertNotIn(private, output)
        self.assertFalse(result["hardwareTested"]); self.assertFalse(result["servicesStarted"])

    def test_clean_checkout_check_ignores_even_partial_private_pio_override(self):
        self.put(f"firmware/.pio/gld-dataset-workflow-wifi/{check.ENVIRONMENTS[0]}/credentials.local.json", b"malformed private override")
        self.assertTrue(self.result()["ok"])

    def test_binary_tamper_fails_model_package_and_public_release_profile(self):
        path = self.root / f"apps/operator-hub/firmware-packages/{check.ENVIRONMENTS[1]}/latest/firmware.bin"
        path.write_bytes(path.read_bytes() + b"tamper")
        result = self.result(); self.assertFalse(result["ok"])
        self.assertEqual(self.outcome(result, "workflow_model_2")["status"], "fail")
        self.assertEqual(self.outcome(result, "workflow_connection_profiles")["status"], "fail")

    def test_bootloader_tamper_is_detected_independently_of_firmware_profile(self):
        path = self.root / f"apps/operator-hub/firmware-packages/{check.ENVIRONMENTS[2]}/latest/bootloader.bin"
        path.write_bytes(b"broken")
        result = self.result(); self.assertFalse(result["ok"])
        self.assertEqual(self.outcome(result, "workflow_model_3")["status"], "fail")
        self.assertEqual(self.outcome(result, "workflow_connection_profiles")["status"], "pass")

    def test_release_profile_hash_or_offset_mismatch_is_rejected(self):
        p = self.root / "apps/gld-operator/workflow-connection-profiles.json"
        value = json.loads(p.read_text()); value["models"][check.ENVIRONMENTS[0]]["firmwareSha256"] = "0" * 64
        p.write_text(json.dumps(value)); result = self.result()
        self.assertFalse(result["ok"])
        self.assertEqual(self.outcome(result, "workflow_connection_profiles")["status"], "fail")

    def test_manifest_tamper_or_wrong_environment_is_rejected(self):
        self.rewrite_manifest(1, lambda value: value.update(environment="different"))
        self.assertEqual(self.outcome(self.result(), "workflow_model_1")["status"], "fail")

    def test_git_lf_crlf_normalization_is_accepted_but_metadata_change_is_not(self):
        folder = self.root / f"apps/operator-hub/firmware-packages/{check.ENVIRONMENTS[0]}/latest"
        p = folder / "manifest.json"; raw = p.read_bytes()
        (folder / "manifest.sha256").write_text(hashlib.sha256(raw.replace(b"\n", b"\r\n")).hexdigest() + "  manifest.json\n")
        self.assertTrue(self.result()["ok"])
        p.write_bytes(raw.replace(b'"esp32s3"', b'"different"'))
        self.assertFalse(self.result()["ok"])

    def test_unsafe_path_duplicate_or_wrong_nvs_overlapping_offset_is_rejected(self):
        for field, bad in (("path", "../private.key"), ("offset", "0x9000")):
            with self.subTest(field=field):
                original = (self.root / f"apps/operator-hub/firmware-packages/{check.ENVIRONMENTS[0]}/latest/manifest.json").read_text()
                self.rewrite_manifest(1, lambda value: value["flashFiles"][0].update({field: bad}))
                self.assertEqual(self.outcome(self.result(), "workflow_model_1")["status"], "fail")
                self.rewrite_manifest(1, lambda value: value.update(json.loads(original)))

    def test_invalid_private_config_has_fixed_error_and_does_not_echo_values(self):
        self.system["serverEnv"]["GLD_AES128_KEY_HEX"] = self.secret
        self.state.write_text(json.dumps(self.system)); result = self.result()
        self.assertEqual(self.outcome(result, "system_state_config")["code"], "system_state_config_invalid")
        self.assertNotIn(self.secret, json.dumps(result))

    def test_missing_optional_state_runtime_and_driver_do_not_require_connected_hardware(self):
        result = check.check(self.root)
        self.assertTrue(result["ok"]); self.assertEqual(result["counts"]["skip"], 3)

    def test_absent_embedded_pyserial_shared_esptool_and_node_runtime_are_reported(self):
        (self.root / "apps/gld-operator/python-embed/python.exe").unlink()
        (self.root / "apps/lib/run_esptool.py").unlink()
        (self.runtime / "node-red/red.js").unlink()
        result = self.result(); self.assertFalse(result["ok"])
        for name in ("gld_python_pyserial", "shared_esptool", "node_nodered_runtime"):
            self.assertEqual(self.outcome(result, name)["status"], "fail")

    def test_deployment_database_settings_are_validated_without_connecting(self):
        value = {"database": {"name": "gld", "user": "operator", "password": self.secret, "rootPassword": self.secret},
                 "ports": {"hub": 5173, "nodeRed": 1880, "mqtt": 1884, "database": 3307}}
        p = self.put("handover/deployment.json", json.dumps(value).encode())
        self.assertTrue(self.result()["ok"])
        value["ports"]["database"] = 0; p.write_text(json.dumps(value))
        result = self.result(); self.assertEqual(self.outcome(result, "deployment_database_config")["status"], "fail")
        self.assertNotIn(self.secret, json.dumps(result))

    def test_checker_does_not_write_files_even_with_private_override(self):
        with mock.patch.object(Path, "write_text", side_effect=AssertionError("No writes")), mock.patch.object(
                Path, "write_bytes", side_effect=AssertionError("No writes")):
            self.assertTrue(self.result()["ok"])


if __name__ == "__main__":
    unittest.main()
