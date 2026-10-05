"""Static contract checks for GLD Expert's non-secret AES controls."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "gld-operator"


class GldAesOperatorUiTests(unittest.TestCase):
    def test_aes_device_state_is_immediately_after_battery(self):
        html = (APP / "index.html").read_text(encoding="utf-8")
        layout = (APP / "css" / "layout.css").read_text(encoding="utf-8")
        battery = '<span class="strip-gauge"><span>Battery</span><strong id="batteryValue">Unknown</strong></span>'
        aes = '<span class="strip-gauge"><span>AES</span><strong id="aesValue">Unknown</strong></span>'
        self.assertIn(battery, html)
        self.assertIn(aes, html)
        self.assertLess(html.index(battery), html.index(aes))
        self.assertIn("flex-wrap: nowrap", layout)
        self.assertIn("overflow-x: auto", layout)

    def test_running_settings_has_confirmed_non_secret_provision_action(self):
        html = (APP / "index.html").read_text(encoding="utf-8")
        main = (APP / "js" / "main.js").read_text(encoding="utf-8")
        dataset = (APP / "js" / "dataset.js").read_text(encoding="utf-8")
        protocol = (APP / "js" / "serial-protocol.js").read_text(encoding="utf-8")
        bridge = (APP / "js" / "bridge-client.js").read_text(encoding="utf-8")
        for marker in (
            'id="syncRunningAesKeyBtn"',
            'id="refreshRunningAesKeyBtn"',
            'id="runningAesKeyStatus"',
            "syncRunningAesKeyBtn",
            "syncGldAesKey",
            "showConfirm(`Kirim AES key ID ${status.keyId}",
            "renderAesSecurity",
            'setText("aesValue", `Ready #${keyId}`)',
            'security.aesKeySource === "nvs"',
            "resetDeviceSnapshot();",
        ):
            combined = "\n".join((html, main, dataset, protocol, bridge))
            self.assertIn(marker, combined)
        self.assertNotIn("aesKeyHex", html)


if __name__ == "__main__":
    unittest.main()
