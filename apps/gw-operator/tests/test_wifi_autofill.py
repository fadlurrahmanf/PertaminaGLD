import sys
import unittest
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
import bridge  # noqa: E402


ENGLISH_INTERFACE = """
There is 1 interface on the system:

    Name                   : Wi-Fi
    State                  : connected
    SSID                   : Site Network
    BSSID                  : aa:bb:cc:dd:ee:ff
    Profile                : Site Profile
"""

INDONESIAN_INTERFACE = """
    Nama                   : Wi-Fi
    Status                 : tersambung
    SSID                   : Jaringan Site
    BSSID                  : 11:22:33:44:55:66
    Profil                 : Profil Site
"""


class WifiAutofillTests(unittest.TestCase):
    def test_connected_profile_english_ignores_bssid(self):
        self.assertEqual(
            bridge._connected_wifi_profile(ENGLISH_INTERFACE),
            ("Site Network", "Site Profile"),
        )

    def test_connected_profile_indonesian(self):
        self.assertEqual(
            bridge._connected_wifi_profile(INDONESIAN_INTERFACE),
            ("Jaringan Site", "Profil Site"),
        )

    def test_multiple_connected_interfaces_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError, "More than one"):
            bridge._connected_wifi_profile(ENGLISH_INTERFACE + "\n" + INDONESIAN_INTERFACE)

    def test_disconnected_interface_fails(self):
        with self.assertRaisesRegex(RuntimeError, "not connected"):
            bridge._connected_wifi_profile(ENGLISH_INTERFACE.replace("connected", "disconnected"))

    def test_password_is_returned_without_logging_or_storage(self):
        profile = "Authentication : WPA2-Personal\nKey Content : local-secret\n"
        with patch.object(bridge, "_run_netsh", side_effect=[ENGLISH_INTERFACE, profile]):
            result = bridge.current_wifi_credentials()
        self.assertEqual(result["ssid"], "Site Network")
        self.assertEqual(result["password"], "local-secret")
        self.assertTrue(result["passwordAvailable"])

    def test_unavailable_password_returns_partial_result(self):
        profile = "Authentication : WPA2-Personal\n"
        with patch.object(bridge, "_run_netsh", side_effect=[ENGLISH_INTERFACE, profile]):
            result = bridge.current_wifi_credentials()
        self.assertEqual(result["ssid"], "Site Network")
        self.assertIsNone(result["password"])
        self.assertEqual(result["passwordError"], "saved_password_unavailable")


if __name__ == "__main__":
    unittest.main()
