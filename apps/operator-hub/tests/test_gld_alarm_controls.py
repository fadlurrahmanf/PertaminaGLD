from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


HUB_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HUB_DIR))
SPEC = importlib.util.spec_from_file_location("operator_hub_alarm_bridge", HUB_DIR / "bridge.py")
assert SPEC and SPEC.loader
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


def alarm_state(
    mode: str = "auto",
    *,
    manual: bool = False,
    inference: bool = False,
    physical: bool | None = None,
    available: bool = True,
) -> dict[str, object]:
    if physical is None:
        physical = manual if mode == "manual" else inference
    return {
        "device": "gld",
        "connected": True,
        "port": "COM_TEST",
        "info": {
            "deviceId": "1001",
            "alarmControl": {
                "available": available,
                "mode": mode,
                "defaultMode": "auto",
                "modePersisted": False,
                "sessionOnly": True,
                "resetsToAutoOnBoot": True,
                "manualOnly": mode == "manual",
                "manualCommanded": manual,
                "inferenceAlarm": inference,
                "physicalCommanded": physical,
                "outputDrive": "steady_24v",
                "externalDevicePattern": "self_pulsed_1s_on_1s_off",
            },
        },
    }


def handler() -> bridge.Handler:
    instance = object.__new__(bridge.Handler)
    instance.server = SimpleNamespace(server_address=("127.0.0.1", 0))
    return instance


class AlarmStatusContractTests(unittest.TestCase):
    def test_complete_session_only_contract_is_accepted(self) -> None:
        alarm = bridge.require_gld_alarm_control(alarm_state("manual"))
        self.assertEqual(alarm["mode"], "manual")
        self.assertIs(alarm["sessionOnly"], True)
        self.assertIs(alarm["modePersisted"], False)

    def test_missing_or_persisted_contract_fails_closed(self) -> None:
        missing = alarm_state()
        del missing["info"]["alarmControl"]["sessionOnly"]
        with self.assertRaisesRegex(RuntimeError, "sessionOnly is not boolean"):
            bridge.require_gld_alarm_control(missing)

        persisted = alarm_state()
        persisted["info"]["alarmControl"]["modePersisted"] = True
        with self.assertRaisesRegex(RuntimeError, "volatile and session-only"):
            bridge.require_gld_alarm_control(persisted)

    def test_unavailable_alarm_hardware_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "does not expose"):
            bridge.require_gld_alarm_control(alarm_state(available=False))

    def test_query_merges_fresh_status_into_gld_info(self) -> None:
        runtime = alarm_state()["info"]
        with (
            mock.patch.object(
                bridge,
                "child_request",
                side_effect=[
                    {"connected": True, "port": "COM_TEST"},
                    {"sequence": 10},
                    {},
                    {"sequence": 20},
                    {},
                ],
            ),
            mock.patch.object(
                bridge,
                "recent_matching",
                side_effect=[{"deviceId": "1001"}, runtime],
            ),
        ):
            state = bridge.simple_device_state("127.0.0.1", "gld", query=True)
        self.assertEqual(state["info"]["deviceId"], "1001")
        self.assertEqual(state["info"]["alarmControl"]["mode"], "auto")


class AlarmEndpointTests(unittest.TestCase):
    def test_mode_waits_for_ack_and_verifies_fresh_session_status(self) -> None:
        before = alarm_state("auto")
        after = alarm_state("manual", manual=False, physical=False)
        with (
            mock.patch.object(bridge, "simple_device_state", side_effect=[before, after]) as state,
            mock.patch.object(bridge, "send_and_confirm", return_value={"ack": "SET_ALARM_MODE ok"}) as send,
            mock.patch.object(bridge, "add_activity"),
            mock.patch.object(bridge, "json_response") as respond,
        ):
            handler()._simple_config_alarm_mode({"device": "gld", "mode": "manual"})
        self.assertEqual(state.call_count, 2)
        self.assertTrue(all(call.kwargs.get("query") is True for call in state.call_args_list))
        send.assert_called_once_with(
            "127.0.0.1",
            "gld",
            'SET_ALARM_MODE_JSON {"mode":"manual"}',
            "SET_ALARM_MODE",
        )
        self.assertIs(respond.call_args.args[1]["readback"], after)

    def test_mode_ack_is_not_enough_when_readback_differs(self) -> None:
        with (
            mock.patch.object(bridge, "simple_device_state", side_effect=[alarm_state("auto"), alarm_state("auto")]),
            mock.patch.object(bridge, "send_and_confirm", return_value={"ack": "SET_ALARM_MODE ok"}),
            mock.patch.object(bridge, "add_activity"),
            mock.patch.object(bridge, "json_response"),
        ):
            with self.assertRaisesRegex(RuntimeError, "read-back differs"):
                handler()._simple_config_alarm_mode({"device": "gld", "mode": "manual"})

    def test_manual_output_requires_manual_mode_before_sending(self) -> None:
        with (
            mock.patch.object(bridge, "simple_device_state", return_value=alarm_state("auto")),
            mock.patch.object(bridge, "send_and_confirm") as send,
        ):
            with self.assertRaisesRegex(RuntimeError, "session-only MANUAL"):
                handler()._simple_config_manual_alarm({"device": "gld", "enabled": True})
        send.assert_not_called()

    def test_manual_output_waits_for_ack_and_verifies_commanded_state(self) -> None:
        before = alarm_state("manual", manual=False, physical=False)
        after = alarm_state("manual", manual=True, physical=True)
        with (
            mock.patch.object(bridge, "simple_device_state", side_effect=[before, after]),
            mock.patch.object(bridge, "send_and_confirm", return_value={"ack": "SET_MANUAL_ALARM ok"}) as send,
            mock.patch.object(bridge, "add_activity"),
            mock.patch.object(bridge, "json_response") as respond,
        ):
            handler()._simple_config_manual_alarm({"device": "gld", "enabled": True})
        send.assert_called_once_with(
            "127.0.0.1",
            "gld",
            'SET_MANUAL_ALARM_JSON {"enabled":true}',
            "SET_MANUAL_ALARM",
        )
        self.assertIs(respond.call_args.args[1]["readback"], after)

    def test_manual_output_rejects_non_boolean_and_mismatched_readback(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be boolean"):
            handler()._simple_config_manual_alarm({"device": "gld", "enabled": "true"})

        wrong = alarm_state("manual", manual=True, physical=False)
        with (
            mock.patch.object(bridge, "simple_device_state", side_effect=[alarm_state("manual"), wrong]),
            mock.patch.object(bridge, "send_and_confirm", return_value={"ack": "SET_MANUAL_ALARM ok"}),
            mock.patch.object(bridge, "add_activity"),
            mock.patch.object(bridge, "json_response"),
        ):
            with self.assertRaisesRegex(RuntimeError, "output read-back differs"):
                handler()._simple_config_manual_alarm({"device": "gld", "enabled": True})


class AlarmUiContractTests(unittest.TestCase):
    def test_simple_hub_exposes_fail_closed_session_only_controls(self) -> None:
        html = (HUB_DIR / "public" / "index.html").read_text(encoding="utf-8")
        source = (HUB_DIR / "public" / "js" / "hub.js").read_text(encoding="utf-8")
        for marker in (
            "gldAlarmControlCard",
            "alarmModeSelect",
            "applyAlarmModeBtn",
            "manualAlarmOnBtn",
            "manualAlarmOffBtn",
            "MANUAL — test only / session-only",
            "Reboot selalu kembali ke AUTO",
        ):
            self.assertIn(marker, html)
        for marker in (
            "/api/simple/config/alarm-mode",
            "/api/simple/config/manual-alarm",
            "alarm.modePersisted !== false",
            "alarm.sessionOnly !== true",
            "alarm.resetsToAutoOnBoot !== true",
            "validGldAlarmControl",
        ):
            self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()
