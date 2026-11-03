"""Exercise the real Simple Hub upload handler with inert child/device stubs."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from test_child_package_validators import GLD_BRIDGE as child, load_bridge, package_for

hub = load_bridge("native_workflow_upload_hub", "apps/operator-hub/bridge.py")


class NativeWorkflowUpload(unittest.TestCase):
    def upload(self, environment, capabilities=None, *, actual_version="1.2.3", actual_id="1001", **flags):
        manifest, files = package_for(child, environment, {})
        if capabilities is not None:
            manifest["capabilities"] = capabilities
        handler = object.__new__(hub.Handler)
        handler.server = SimpleNamespace(server_address=("127.0.0.1", 5173))
        current = dict(connected=True, port="COM999", info=dict(deviceId="1001"))
        verified = dict(connected=True, port="COM999",
                        info=dict(deviceId=actual_id, firmwareVersion=actual_version))
        responses, posts = [], []

        def request(_host, _device, method, path, payload=None, **_kwargs):
            if method == "GET":
                self.assertEqual(path, f"/api/firmware/package?env={environment}")
                return dict(manifest=manifest, packageFiles=files)
            self.assertEqual(path, "/api/firmware/upload")
            self.assertFalse(payload["resetNvs"])
            self.assertNotIn("resetNvsConfirmation", payload)
            self.assertEqual(payload["targetDeviceId"], "1001")
            posts.append(payload)
            return dict(ok=True, nvsReset=False)

        with (mock.patch.object(hub, "package_manifest_summary", return_value={"available": True}),
              mock.patch.object(hub, "simple_device_state", return_value=current),
              mock.patch.object(hub, "child_request", side_effect=request),
              mock.patch.object(hub, "wait_for_readback", return_value=verified) as readback,
              mock.patch.object(hub, "send_and_confirm") as mutation,
              mock.patch.object(hub, "add_activity"),
              mock.patch.object(hub, "json_response", side_effect=lambda _handler, value: responses.append(value))):
            handler._simple_firmware_upload(dict(device="gld", model=environment.removeprefix("gld_"),
                                                port="COM999", resetNvs=False, **flags))
        mutation.assert_not_called()
        self.assertEqual(len(posts), 1)
        return responses[0], readback

    def test_three_capable_workflows_reconnect_and_verify_identity_and_version(self):
        for model in (1, 2, 3):
            with self.subTest(model=model):
                result, readback = self.upload(f"gld_model_{model}_dataset_workflow_wifi",
                                              {"nativeSerial": True, "datasetWifi": True})
                readback.assert_called_once_with("127.0.0.1", "gld", "COM999", timeout=35.0)
                self.assertEqual(result["readback"]["info"], dict(deviceId="1001", firmwareVersion="1.2.3"))
                self.assertNotIn("verificationPending", result)

    def test_capable_workflow_rejects_wrong_version_or_identity(self):
        for fields, error in ((dict(actual_version="0.0.0"), "firmware read-back differs"),
                              (dict(actual_id="1002"), "identity read-back differs")):
            with self.subTest(fields=fields), self.assertRaisesRegex(RuntimeError, error):
                self.upload("gld_model_1_dataset_workflow_wifi", {"nativeSerial": True}, **fields)

    def test_old_and_unflagged_hotspots_keep_wireless_verification(self):
        for model in (1, 2, 3):
            for suffix, capabilities in (("dataset_wifi", {"nativeSerial": True}),
                                         ("dataset_replay_wifi", {"nativeSerial": True}),
                                         ("dataset_workflow_wifi", None),
                                         ("dataset_workflow_wifi", {"nativeSerial": "true"}),
                                         ("dataset_workflow_wifi", {"nativeSerial": False})):
                with self.subTest(model=model, suffix=suffix, capabilities=capabilities):
                    result, readback = self.upload(f"gld_model_{model}_{suffix}", capabilities)
                    readback.assert_not_called()
                    self.assertEqual(result["verificationPending"], "hotspot")
                    self.assertFalse(result["deviceVerified"])

    def test_normal_model_readback_remains_unchanged(self):
        result, readback = self.upload("gld_model_2")
        readback.assert_called_once()
        self.assertNotIn("verificationPending", result)

    def test_capability_cannot_bypass_reset_or_initial_firmware_restrictions(self):
        for flags in (dict(resetNvs=True, resetNvsConfirmation="RESET NVS"), dict(initialFirmware=True)):
            handler = object.__new__(hub.Handler)
            with (mock.patch.object(hub, "package_manifest_summary") as package,
                  mock.patch.object(hub, "child_request") as request,
                  self.assertRaisesRegex(ValueError, "Reset NVS OFF")):
                handler._simple_firmware_upload(dict(device="gld", model="model_1_dataset_workflow_wifi",
                                                    port="COM999", **flags))
            package.assert_not_called()
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
