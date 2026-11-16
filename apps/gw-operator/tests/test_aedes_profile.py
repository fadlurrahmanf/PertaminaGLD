from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

APP = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gw_bridge_aedes_test", APP / "bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class AedesProfileTests(unittest.TestCase):
    def test_only_successful_authenticated_local_test_is_remembered(self):
        config = {"host": "192.168.1.2", "port": 1885, "username": "operator", "password": "test-password"}
        with mock.patch.object(bridge, "local_ipv4", return_value="192.168.1.2"), \
             mock.patch.object(bridge.aedes_profile, "save_profile") as save:
            self.assertFalse(bridge.remember_tested_local_broker(config, {"ok": False}))
            self.assertFalse(bridge.remember_tested_local_broker({**config, "host": "192.168.1.3"}, {"ok": True}))
            self.assertFalse(bridge.remember_tested_local_broker({**config, "password": ""}, {"ok": True}))
            save.assert_not_called()
            self.assertTrue(bridge.remember_tested_local_broker(config, {"ok": True}))
            self.assertEqual(save.call_args.args[0]["port"], 1885)

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI is required")
    def test_windows_profile_is_encrypted_and_round_trips(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            profile = {"username": "sample-user", "password": "sample-private-value", "port": 1885, "topicRoot": "gld/gateway"}
            bridge.aedes_profile.save_profile(profile)
            blob = bridge.aedes_profile.profile_path().read_bytes()
            self.assertNotIn(b"sample-private-value", blob)
            self.assertEqual(bridge.aedes_profile.load_profile(), profile)


if __name__ == "__main__":
    unittest.main()
