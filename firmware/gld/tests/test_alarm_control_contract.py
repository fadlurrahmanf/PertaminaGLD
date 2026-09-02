"""Source-contract regression checks for GLD AUTO/MANUAL alarm control.

The truth table itself is compile-time asserted in GldAlarmControl.h. These
checks protect the cross-file serial/session/status/UI contract that PlatformIO
cannot exercise without a connected board.
"""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def require(text: str, marker: str, source: str) -> None:
    if marker not in text:
        raise AssertionError(f"missing {marker!r} in {source}")


def forbid(text: str, marker: str, source: str) -> None:
    if marker in text:
        raise AssertionError(f"forbidden {marker!r} in {source}")


def main() -> None:
    header_path = "firmware/gld/include/GldAlarmControl.h"
    parser_header_path = "firmware/gld/include/GldCommandParser.h"
    parser_source_path = "firmware/gld/src/GldCommandParser.cpp"
    runtime_path = "firmware/gld/src/GldUnifiedMain.cpp"
    operator_path = "apps/gld-operator/js/serial-protocol.js"
    mock_path = "apps/gld-operator/js/mock.js"
    page_path = "apps/gld-operator/index.html"

    header = read(header_path)
    parser_header = read(parser_header_path)
    parser_source = read(parser_source_path)
    runtime = read(runtime_path)
    operator = read(operator_path)
    mock = read(mock_path)
    page = read(page_path)

    for marker in (
        "Auto = 0",
        "Manual = 1",
        "must never be loaded from, or written to, NVS",
        "AUTO must follow a valid inference alarm",
        "MANUAL must suppress inference-driven physical output",
        "MANUAL must allow operator alarm testing",
    ):
        require(header, marker, header_path)

    require(parser_header, "SetAlarmModeJson", parser_header_path)
    require(parser_source, '"SET_ALARM_MODE_JSON "', parser_source_path)

    for marker in (
        "alarmControlMode = pgl::gld::GldAlarmControlMode::Auto;",
        "void onSetAlarmModeJson",
        "select manual alarm mode before testing output",
        'telemetry["alarm"] = lastAlarm',
        'alarmControl["modePersisted"] = false',
        'alarmControl["sessionOnly"] = true',
        'alarmControl["resetsToAutoOnBoot"] = true',
        'alarmControl["physicalCommanded"]',
        'alarmControl["externalDevicePattern"] = "self_pulsed_1s_on_1s_off"',
        "PIN_ALARM_ENABLE_BOOST, HIGH",
        "PIN_ALARM_LAMP, HIGH",
        "PIN_ALARM_LAMP, LOW",
        "PIN_ALARM_ENABLE_BOOST, LOW",
    ):
        require(runtime, marker, runtime_path)

    for marker in (
        'prefs.getUChar("alarmMode"',
        'prefs.putUChar("alarmMode"',
        "saveAlarmControlMode",
        "alarmControlModePersisted",
    ):
        forbid(runtime, marker, runtime_path)

    mode_handler = runtime.split("void onSetAlarmModeJson", 1)[1].split(
        "void onSetManualAlarmJson", 1
    )[0]
    apply_markers = (
        "alarmControlMode = nextMode;",
        "manualAlarmCommanded = false;",
        "driveAlarmOutputs(lastAlarm);",
    )
    apply_positions = []
    for marker in apply_markers:
        require(mode_handler, marker, runtime_path)
        apply_positions.append(mode_handler.index(marker))
    if apply_positions != sorted(apply_positions):
        raise AssertionError("alarm mode apply sequence must be mode -> clear manual -> re-drive")
    require(mode_handler, "sessionOnly=1 persisted=0", runtime_path)
    require(mode_handler, "MANUAL TEST active for this session only", runtime_path)
    require(mode_handler, "reboot restores AUTO", runtime_path)
    forbid(mode_handler, "if (nextMode != alarmControlMode)", runtime_path)

    for marker in (
        "function alarmControlContract",
        "const hasExplicitMode =",
        "const legacyManualOnly = !hasExplicitMode",
        "manualOutputAllowed",
        "modeSelect.disabled = alarmModeApplyPending || !available || !hasExplicitMode",
        "Firmware lama terdeteksi",
        "perintah mode baru tidak akan dikirim",
        "setAlarmModeAndWait",
        '"SET_ALARM_MODE"',
        "alarmModeSelectionDirty",
        "MANUAL TEST sementara",
        "reboot mengembalikan AUTO",
    ):
        require(operator, marker, operator_path)

    mode_sender = operator.split("export async function setAlarmModeAndWait", 1)[1].split(
        "function sensorWindowSamples", 1
    )[0]
    require(mode_sender, "if (!contract.hasExplicitMode)", operator_path)
    require(mode_sender, "if (!contract.available)", operator_path)
    guard_pos = mode_sender.index("if (!contract.hasExplicitMode)")
    command_pos = mode_sender.index("SET_ALARM_MODE_JSON")
    if guard_pos > command_pos:
        raise AssertionError("legacy alarm-mode guard must run before SET_ALARM_MODE_JSON")

    manual_sender = operator.split("export async function setManualAlarmAndWait", 1)[1].split(
        "export async function setAlarmModeAndWait", 1
    )[0]
    require(manual_sender, "if (!contract.manualOutputAllowed)", operator_path)
    require(manual_sender, "SET_MANUAL_ALARM_JSON", operator_path)

    require(mock, "state.mockAlarmMode = \"auto\"", mock_path)
    require(mock, "modePersisted: false", mock_path)
    require(mock, "sessionOnly: true", mock_path)
    require(mock, "resetsToAutoOnBoot: true", mock_path)
    require(mock, "state.mockLegacyAlarmContract === true", mock_path)
    require(mock, "? { manualOnly: true, manualCommanded }", mock_path)
    require(mock, "delete info.capabilities.alarmControlMode", mock_path)
    require(mock, "manualOutputAvailable", mock_path)
    require(page, 'option value="auto"', page_path)
    require(page, 'option value="manual"', page_path)
    require(page, "AUTO selalu aktif setelah boot", page_path)
    require(page, "reboot mengembalikan AUTO", page_path)
    require(page, "Firmware lama tetap mendapat kontrol manual ON/OFF", page_path)
    require(page, 'id="alarmControlStatus" class="sensor-power-status" aria-live="polite"', page_path)

    print("GLD alarm control source contract: PASS")


if __name__ == "__main__":
    main()
