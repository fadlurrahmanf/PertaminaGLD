from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gw_operator_bridge", APP_DIR / "bridge.py")
assert SPEC and SPEC.loader
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class FakeSerial:
    is_open = True

    def __init__(self) -> None:
        self.written = b""

    def write(self, value: bytes) -> None:
        self.written += value

    def flush(self) -> None:
        pass


class SensitiveSerialRedactionTests(unittest.TestCase):
    def test_mqtt_secret_is_written_to_board_but_redacted_from_sse(self) -> None:
        events = bridge.EventHub()
        client = events.add()
        serial_bridge = bridge.SerialBridge(events)
        fake = FakeSerial()
        serial_bridge._serial = fake
        command = 'SET_MQTT_CONFIG_JSON {"password":"secret","tlsCaPem":"certificate"}'

        serial_bridge.write_line(command)

        self.assertIn(b'"secret"', fake.written)
        event = client.get_nowait()
        self.assertEqual(event["event"], "serial_tx")
        self.assertEqual(event["payload"]["line"], "SET_MQTT_CONFIG_JSON [REDACTED]")
        self.assertNotIn("secret", str(event))
        self.assertNotIn("certificate", str(event))

    def test_wifi_password_is_also_redacted(self) -> None:
        events = bridge.EventHub()
        client = events.add()
        serial_bridge = bridge.SerialBridge(events)
        serial_bridge._serial = FakeSerial()

        serial_bridge.write_line('SET_WIFI_CONFIG_JSON {"password":"wifi-secret"}')

        event = client.get_nowait()
        self.assertEqual(event["payload"]["line"], "SET_WIFI_CONFIG_JSON [REDACTED]")


if __name__ == "__main__":
    unittest.main()
