from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
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
PULLUP_DRIVE = "active_low_gpio41_uln2003_pullup"


def alarm_state(
    mode: str = "auto",
    *,
    manual: bool = False,
    inference: bool = False,
    physical: bool | None = None,
    available: bool = True,
    output_drive: str = "steady_24v",
) -> dict[str, object]:
    if physical is None:
        physical = manual if mode == "manual" else inference
    state = {
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
                "outputDrive": output_drive,
                "externalDevicePattern": (
                    "steady_high_while_alarm"
                    if output_drive in {"active_high_gpio41_steady", PULLUP_DRIVE}
                    else "self_pulsed_1s_on_1s_off"
                ),
                "singleTrigger": output_drive in {"active_high_gpio41_steady", PULLUP_DRIVE},
            },
        },
    }
    if output_drive == PULLUP_DRIVE:
        state["info"]["alarmControl"].update({
            "requiresExternalPullup": True,
            "gpio41CommandLevel": "LOW" if physical else "HIGH",
            "j2LampExpectedLevel": "HIGH" if physical else "LOW",
        })
    return state


def alarm_contract_cases() -> list[tuple[str, dict, bool]]:
    """The same real validators must accept legacy contracts and reject unsafe new ones."""
    cases = [
        ("legacy GLD2", alarm_state(), True),
        ("legacy GLD1", alarm_state(output_drive="active_high_gpio41_steady"), True),
    ]
    for mode in ("auto", "manual"):
        for enabled in (False, True):
            cases.append((
                f"pullup {mode} {enabled}",
                alarm_state(mode, manual=enabled, inference=enabled, output_drive=PULLUP_DRIVE),
                True,
            ))
    for field, value in (
        ("singleTrigger", False), ("singleTrigger", 1),
        ("requiresExternalPullup", False), ("requiresExternalPullup", 1),
        ("requiresExternalPullup", "true"),
        ("externalDevicePattern", "self_pulsed_1s_on_1s_off"),
        ("gpio41CommandLevel", "LOW"), ("gpio41CommandLevel", "high"),
        ("j2LampExpectedLevel", "HIGH"), ("j2LampExpectedLevel", "low"),
        ("physicalCommanded", 0), ("physicalCommanded", "false"),
        ("manualCommanded", 0), ("inferenceAlarm", "false"),
        ("modePersisted", True), ("sessionOnly", False),
        ("resetsToAutoOnBoot", False), ("mode", "unknown"),
    ):
        state = alarm_state(output_drive=PULLUP_DRIVE)
        state["info"]["alarmControl"][field] = value
        cases.append((f"invalid {field}={value!r}", state, False))
    for field in ("requiresExternalPullup", "singleTrigger", "gpio41CommandLevel", "j2LampExpectedLevel"):
        state = alarm_state(output_drive=PULLUP_DRIVE)
        del state["info"]["alarmControl"][field]
        cases.append((f"missing {field}", state, False))
    for field, value in (("gpio41CommandLevel", "HIGH"), ("j2LampExpectedLevel", "LOW")):
        state = alarm_state(inference=True, output_drive=PULLUP_DRIVE)
        state["info"]["alarmControl"][field] = value
        cases.append((f"alarm ON wrong {field}", state, False))
    return cases


def js_function(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    start = source.index(f"function {name}(")
    # Top-level function-closing braces are unindented in these source files.
    end = source.index("\n}", start) + 2
    return source[start:end]


def run_node(source: str) -> object:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("Node.js is required for executable UI-contract tests")
    completed = subprocess.run([node, "-e", source], check=True, capture_output=True, text=True, timeout=10)
    return json.loads(completed.stdout)


def handler() -> bridge.Handler:
    instance = object.__new__(bridge.Handler)
    instance.server = SimpleNamespace(server_address=("127.0.0.1", 0))
    return instance


class AlarmStatusContractTests(unittest.TestCase):
    def test_pullup_requires_valid_flags_and_inverse_command_levels(self) -> None:
        for label, state, accepted in alarm_contract_cases():
            with self.subTest(label=label):
                if accepted:
                    self.assertIs(bridge.require_gld_alarm_control(state), state["info"]["alarmControl"])
                else:
                    with self.assertRaises(RuntimeError):
                        bridge.require_gld_alarm_control(state)

    def test_complete_session_only_contract_is_accepted(self) -> None:
        alarm = bridge.require_gld_alarm_control(alarm_state("manual"))
        self.assertEqual(alarm["mode"], "manual")
        self.assertIs(alarm["sessionOnly"], True)
        self.assertIs(alarm["modePersisted"], False)

    def test_gld1_steady_gpio41_contract_is_accepted(self) -> None:
        alarm = bridge.require_gld_alarm_control(
            alarm_state("auto", output_drive="active_high_gpio41_steady")
        )
        self.assertEqual(alarm["externalDevicePattern"], "steady_high_while_alarm")
        self.assertIs(alarm["singleTrigger"], True)

    def test_incomplete_gld1_steady_gpio41_contract_fails_closed(self) -> None:
        state = alarm_state("auto", output_drive="active_high_gpio41_steady")
        state["info"]["alarmControl"]["singleTrigger"] = False
        with self.assertRaisesRegex(RuntimeError, "steady GPIO41 alarm"):
            bridge.require_gld_alarm_control(state)

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
    def test_pullup_manual_output_is_verified_without_claiming_voltage_measurement(self) -> None:
        before = alarm_state("manual", output_drive=PULLUP_DRIVE)
        after = alarm_state("manual", manual=True, output_drive=PULLUP_DRIVE)
        with (
            mock.patch.object(bridge, "simple_device_state", side_effect=[before, after]),
            mock.patch.object(bridge, "send_and_confirm", return_value={"ack": "SET_MANUAL_ALARM ok"}) as send,
            mock.patch.object(bridge, "add_activity"),
            mock.patch.object(bridge, "json_response") as respond,
        ):
            handler()._simple_config_manual_alarm({"device": "gld", "enabled": True})
        send.assert_called_once()
        self.assertIs(respond.call_args.args[1]["readback"], after)
        self.assertEqual(after["info"]["alarmControl"]["gpio41CommandLevel"], "LOW")
        self.assertEqual(after["info"]["alarmControl"]["j2LampExpectedLevel"], "HIGH")

    def test_incomplete_pullup_status_blocks_commands(self) -> None:
        state = alarm_state("manual", output_drive=PULLUP_DRIVE)
        del state["info"]["alarmControl"]["requiresExternalPullup"]
        with (
            mock.patch.object(bridge, "simple_device_state", return_value=state),
            mock.patch.object(bridge, "send_and_confirm") as send,
        ):
            with self.assertRaisesRegex(RuntimeError, "external pull-up"):
                handler()._simple_config_manual_alarm({"device": "gld", "enabled": True})
        send.assert_not_called()

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
    def test_executable_simple_and_expert_contract_validators(self) -> None:
        cases = alarm_contract_cases()
        program = js_function(HUB_DIR / "public" / "js" / "hub.js", "validGldAlarmControl")
        program += "\n" + js_function(HUB_DIR.parent / "gld-operator" / "js" / "serial-protocol.js", "alarmControlContract")
        program += "\nconst cases = " + json.dumps([state["info"] for _, state, _ in cases]) + ";"
        program += "\nconsole.log(JSON.stringify(cases.map(info => [Boolean(validGldAlarmControl(info)), alarmControlContract(info.alarmControl).available])));"
        results = run_node(program)
        for (label, _, accepted), actual in zip(cases, results, strict=True):
            with self.subTest(label=label):
                self.assertEqual(actual, [accepted, accepted])

    def test_expert_legacy_manual_contract_remains_usable(self) -> None:
        program = js_function(HUB_DIR.parent / "gld-operator" / "js" / "serial-protocol.js", "alarmControlContract")
        program += '\nconsole.log(JSON.stringify(alarmControlContract({manualOnly:true, manualCommanded:false})));'
        result = run_node(program)
        self.assertIs(result["legacyManualOnly"], True)
        self.assertIs(result["hasExplicitMode"], False)
        self.assertIs(result["manualOutputAllowed"], True)

    def test_mock_pullup_levels_follow_auto_and_manual_commands(self) -> None:
        source = js_function(HUB_DIR.parent / "gld-operator" / "js" / "mock.js", "createMockStatus")
        source += "\nconst state = {mode:'inference'}; const mockLoraConfig = () => ({}); const rows = [];"
        source += """
for (const mode of ['auto', 'manual']) {
  state.mockAlarmMode = mode;
  for (const inference of [false, true]) {
    Math.random = () => inference ? 1 : 0;
    for (const manual of [false, true]) {
      state.mockManualAlarmCommanded = manual;
      rows.push([mode === 'manual' ? manual : inference, createMockStatus().alarmControl]);
    }
  }
}
console.log(JSON.stringify(rows));
"""
        for expected, alarm in run_node(source):
            with self.subTest(mode=alarm["mode"], expected=expected):
                bridge.require_gld_alarm_control({"connected": True, "info": {"alarmControl": alarm}})
                self.assertEqual(alarm["physicalCommanded"], expected)
                self.assertEqual(alarm["gpio41CommandLevel"], "LOW" if expected else "HIGH")
                self.assertEqual(alarm["j2LampExpectedLevel"], "HIGH" if expected else "LOW")

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
            'alarm.outputDrive === "active_high_gpio41_steady"',
            'alarm.outputDrive === "active_low_gpio41_uln2003_pullup"',
            'alarm.externalDevicePattern === "steady_high_while_alarm"',
            "alarm.singleTrigger === true",
            "alarm.requiresExternalPullup === true",
            "bukan pengukuran tegangan",
            "GPIO40 tidak digunakan",
        ):
            self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()
