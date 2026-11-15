"""Simple Hub ATEX selection/readback with inert request and serial mocks."""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("atex_test_hub", ROOT / "apps/operator-hub/bridge.py")
hub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hub)


def package(model=1):
    env = f"gld_atex_model_{model}_dataset_workflow_wifi"
    sha = "a" * 64
    manifest = dict(environment=env, firmwareVersion="0.8.30", deviceId="ANY",
        boardProfile="GLD ATEX MotherBoardGLDVer2 / GPIO7 fan",
        capabilities={"nativeSerial": True, "datasetWifi": True},
        flashFiles=[dict(path="firmware.bin", sha256=sha)])
    evidence = dict(environment=env, model=model, profileId=f"profile-{model}", firmwareSha256=sha,
                    boardProfile="GLD ATEX MotherBoardGLDVer2 / GPIO7 fan")
    return dict(manifest=manifest, packageFiles={}, atexEvidence=evidence)


class AtexSimpleHub(unittest.TestCase):
    def run_upload(self, pkg, *, fresh_override=None, board="GLD ATEX MotherBoardGLDVer2", profile="profile-1", preboard="GLD ATEX MotherBoardGLDVer2"):
        handler = object.__new__(hub.Handler)
        handler.server = SimpleNamespace(server_address=("127.0.0.1", 5173))
        writes, responses = [], []
        current = dict(connected=True, port="COM999", info=dict(deviceId="1001", boardProfile=preboard))
        identity = (fresh_override if fresh_override is not None else
                    dict(boardProfile=board, deviceId="1001", modelProfileId=profile, firmwareVersion="0.8.30"))
        verified = dict(connected=True, port="COM999", info={**identity, "model": dict(profileId=identity.get("modelProfileId"))})
        def request(_host, _device, method, path, payload=None, **_kwargs):
            if method == "GET": return pkg
            writes.append((path, payload)); return {"ok": True}
        with (mock.patch.object(hub, "require_atex_release"),
              mock.patch.object(hub, "package_manifest_summary", return_value={"available": True}),
              mock.patch.object(hub, "simple_device_state", return_value=current),
              mock.patch.object(hub, "wait_for_readback", side_effect=AssertionError("ATEX must not use stale readback")),
              mock.patch.object(hub, "wait_for_atex_readback", return_value=verified),
              mock.patch.object(hub, "child_request", side_effect=request),
              mock.patch.object(hub, "add_activity"),
              mock.patch.object(hub, "json_response", side_effect=lambda _h, value: responses.append(value))):
            handler._simple_firmware_upload(dict(device="gld", model="atex_model_1_dataset_workflow_wifi",
                                                port="COM999", resetNvs=False))
        return writes, responses

    def test_three_server_choices_and_native_workflow_guards(self):
        for model in (1, 2, 3):
            name = f"gld_atex_model_{model}_dataset_workflow_wifi"
            self.assertIn(name, hub.GLD_DATASET_WORKFLOW_ENVIRONMENTS)
            self.assertTrue(any(item["environment"] == name for item in hub.GLD_FIRMWARE_MODELS))

    def test_validated_package_requires_correct_board_and_model_readback(self):
        writes, responses = self.run_upload(package())
        self.assertEqual(len(writes), 1)
        self.assertEqual(responses[0]["readback"]["info"]["model"]["profileId"], "profile-1")
        for fields, error in ((dict(board="GLD2"), "board profile"),
                              (dict(profile="other"), "model profile"),
                              (dict(profile=None), "model profile")):
            with self.subTest(fields=fields), self.assertRaisesRegex(RuntimeError, error):
                self.run_upload(package(), **fields)

    def test_nonce_identity_mismatch_never_verifies_upload(self):
        for field, value in (("boardProfile", "GLD2"), ("deviceId", "1002"), ("modelProfileId", "other"), ("firmwareVersion", "0.8.29")):
            identity = dict(boardProfile="GLD ATEX MotherBoardGLDVer2", deviceId="1001", modelProfileId="profile-1", firmwareVersion="0.8.30")
            identity[field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                self.run_upload(package(), fresh_override=identity)
        identity.pop("firmwareVersion")
        with self.assertRaises(RuntimeError):
            self.run_upload(package(), fresh_override=identity)

    def test_missing_or_wrong_evidence_fails_before_flash(self):
        for mode in ("missing", "model", "environment", "hash", "profile"):
            pkg = package()
            if mode == "missing": pkg.pop("atexEvidence")
            elif mode == "model": pkg["atexEvidence"]["model"] = 2
            elif mode == "environment": pkg["atexEvidence"]["environment"] += "-wrong"
            elif mode == "hash": pkg["atexEvidence"]["firmwareSha256"] = "b"*64
            else: pkg["atexEvidence"]["profileId"] = ""
            with self.subTest(mode=mode), self.assertRaisesRegex(RuntimeError, "evidence"):
                self.run_upload(pkg)

    def test_release_gate_holds_selection_and_direct_hub_upload(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "firmware-packages" / package()["manifest"]["environment"] / "latest"
            path.mkdir(parents=True)
            path.joinpath("manifest.json").write_text(json.dumps(package()["manifest"]), encoding="utf-8")
            with mock.patch.object(hub, "HUB_DIR", Path(tmp)), mock.patch.object(hub, "child_request") as request:
                result = hub.package_manifest_summary(package()["manifest"]["environment"])
                self.assertFalse(result["available"])
                self.assertIn("release gate", result["error"])
                request.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, "release gates"):
            hub.require_atex_release("gld_atex")
        handler = object.__new__(hub.Handler)
        with mock.patch.object(hub, "child_request") as request, self.assertRaisesRegex(RuntimeError, "release gates"):
            handler._simple_firmware_upload(dict(device="gld", model="atex_model_1_dataset_workflow_wifi", port="COM999"))
        request.assert_not_called()

    def test_legacy_or_mismatched_preflash_board_is_held(self):
        for preboard in ("GLD2 WROOM-1U-N16R8", "WROOM-1U-N16R8", "", None):
            with self.subTest(preboard=preboard), self.assertRaisesRegex(RuntimeError, "board identity"):
                self.run_upload(package(), preboard=preboard)

    def test_manifest_summary_remains_unavailable_until_child_verified(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "firmware-packages" / package()["manifest"]["environment"] / "latest"
            path.mkdir(parents=True)
            path.joinpath("manifest.json").write_text(json.dumps(package()["manifest"]), encoding="utf-8")
            env = package()["manifest"]["environment"]
            with mock.patch.object(hub, "require_atex_release"), mock.patch.object(hub, "HUB_DIR", Path(tmp)), mock.patch.object(hub, "child_request", side_effect=RuntimeError("not running")):
                self.assertFalse(hub.package_manifest_summary(env)["available"])
            with mock.patch.object(hub, "require_atex_release"), mock.patch.object(hub, "HUB_DIR", Path(tmp)), mock.patch.object(hub, "child_request", return_value=package()):
                self.assertTrue(hub.package_manifest_summary(env)["available"])
            changed = copy.deepcopy(package()); changed["manifest"]["firmwareVersion"] = "9.9.9"
            with mock.patch.object(hub, "require_atex_release"), mock.patch.object(hub, "HUB_DIR", Path(tmp)), mock.patch.object(hub, "child_request", return_value=changed):
                self.assertFalse(hub.package_manifest_summary(env)["available"])

if __name__ == "__main__": unittest.main()
