"""Execute actual alarm output functions on a host; never access hardware.

Checks active-HIGH GPIO17, initial output-latch ordering, AUTO/MANUAL truth table,
logs based on the physical command, and exact non-alarm baseline source.
Only GLD1 is built; other boards/packages are independently hash-protected.
"""

import os
from pathlib import Path
import subprocess
import tempfile

import re
import shutil

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = "firmware/gld/src/GldUnifiedMain.cpp"
BASE = "69a493c32d2500134a21e029820cd4addea1794a"


def definition(source, name):
    match = re.search(rf"^[\w:]+ {name}\([^;]*?\)\s*\{{", source, re.MULTILINE)
    assert match, name
    depth, end = 1, match.end()
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


def compatible_header(source):
    source = re.sub(r"namespace ([\w]+(?:::\w+)+) \{",
                    lambda m: " ".join(f"namespace {part} {{" for part in m[1].split("::")),
                    source)
    return re.sub(r"\}  // namespace ([\w]+(?:::\w+)+)",
                  lambda m: "}" * len(m[1].split("::")) + " // namespace " + m[1], source)


def compiler_path():
    candidates = [os.environ.get("CXX"), shutil.which("g++"), shutil.which("clang++"),
                  str(Path.home() / ".platformio/packages/toolchain-gccmingw32/bin/g++.exe")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise RuntimeError("Host C++ compiler missing; set CXX")


def assert_baseline_preserved():
    allowed = {
        "firmware/gld/include/BoardPins.h",
        "firmware/gld/include/GldCommandParser.h",
        "firmware/gld/src/GldCommandParser.cpp",
        RUNTIME,
        "firmware/tools/operator_package_post.py",
        # User-authorized Board 1 model-only refresh, 2026-09-21.
        "firmware/gld/models/model_1/cnn_gas_datasheet_model_data.h",
        "firmware/gld/models/model_1/cnn_gas_datasheet_normalize_params.h",
        "firmware/gld/models/model_1/cnn_gas_sensitivity_table.h",
        "firmware/gld/models/model_1/model_data.cpp",
        "firmware/gld/models/model_1/ModelMetadata.h",
        "firmware/gld/models/model_1/model.json",
        # User-authorized Board 2 model alignment, 2026-10-01.
        "firmware/gld/models/model_2/cnn_gas_datasheet_model_data.h",
        "firmware/gld/models/model_2/cnn_gas_datasheet_normalize_params.h",
        "firmware/gld/models/model_2/cnn_gas_sensitivity_table.h",
        "firmware/gld/models/model_2/model_data.cpp",
        "firmware/gld/models/model_2/ModelMetadata.h",
        "firmware/gld/models/model_2/model.json",
        # User-authorized Board 3 model refresh and GLD1 baseline, 2026-09-29.
        "firmware/gld/models/model_3/cnn_gas_datasheet_model_data.h",
        "firmware/gld/models/model_3/cnn_gas_datasheet_normalize_params.h",
        "firmware/gld/models/model_3/cnn_gas_sensitivity_table.h",
        "firmware/gld/models/model_3/model_data.cpp",
        "firmware/gld/models/model_3/ModelMetadata.h",
        "firmware/gld/models/model_3/model.json",
    }
    changed = set(subprocess.check_output(
        ["git", "-c", "core.autocrlf=false", "diff", "--name-only", BASE, "--", "firmware"],
        cwd=ROOT, text=True).splitlines())
    assert changed <= allowed, changed - allowed
    baseline = subprocess.check_output(["git", "show", f"{BASE}:{RUNTIME}"],
                                       cwd=ROOT, text=True, encoding="utf-8")
    current = (ROOT / RUNTIME).read_text(encoding="utf-8")
    for name in ("probeBootI2c", "runInference", "modelProfileMatchesActiveNulling",
                 "applySavedNullingProfileOnly"):
        assert definition(current, name) == definition(baseline, name), name
    nulling = (ROOT / "firmware/gld/src/GldNullingService.cpp").read_text(encoding="utf-8")
    assert re.search(r"SETTLE_MS\s*=\s*5;", nulling)
    assert "STABILITY_WINDOW_COUNT" not in nulling
    assert "readSettledAverage" not in nulling
    assert "NULLING_WARMUP" not in nulling
    assert "NULLING_ALL_SENSORS_WARMUP_MS" not in nulling
    assert 'caps["alarmControlMode"]' in current
    # A persisted radio retry may not command GLD1 physical output by itself.
    pending = current[current.index("batteryFreshAlarmQueued = batteryFreshAlarm &&"):]
    pending = pending[:pending.index("} else if (batteryFreshAlarm)")]
    assert re.search(r"#if PGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8 && !PGL_GLD_BOARD_PROFILE_GLD2"
                     r".*?updateAlarmOutputs\(batteryFreshInferenceValid && batteryFreshAlarm\);"
                     r"\s*#else\s*\(void\)updateAlarmOutputs\(true\);\s*#endif", pending, re.S)
    assert 'lastAlarm = false;\n        driveAlarmOutputs(false);\n        logPrintln("GLD1_ALARM_OUTPUT inference=invalid' in current
    for marker in ('alarmControl["requiresExternalPullup"] = false',
                   'alarmControl["outputDrive"] = "active_high_gpio17_steady"',
                   'alarmControl["resetsToAutoOnBoot"] = true',
                   'case pgl::gld::GldSerialCommandType::SetAlarmModeJson',
                   'GLD1_BASE_COMMIT=69a493c'):
        assert marker in current, marker
    print("69a493c baseline: PASS (runtime preserved; only approved alarm/build metadata and Model 1/2/3 refreshes)")



STUBS = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdarg>
#include <cstring>
#include <initializer_list>
#include <vector>
#include <ArduinoJson.h>
#include "BoardPins.h"
#include "GldAlarmControl.h"
#include "GldNullingProfile.h"
namespace board = pgl::gld::board;
constexpr uint8_t LOW = 0, HIGH = 1, OUTPUT = 3;
constexpr uint8_t ACTIVE_LOW_OUTPUT_ON = LOW, ACTIVE_LOW_OUTPUT_OFF = HIGH;
bool FIELDTEST_MODEL_UNVERIFIED = false;
bool lastAlarm = false, physicalAlarmCommanded = false, manualAlarmCommanded = false;
auto alarmControlMode = pgl::gld::GldAlarmControlMode::Auto;
struct Event { char type; int pin; int value; };
std::vector<Event> events;
int gpio[64]{};
char lastLog[512]{};
int persisted = 0;
int statusEmitted = 0;
char ackStatus[32]{};
void emitStatusJson() { ++statusEmitted; }
void emitCommandAck(const char*, const char* status, const char*, bool persistedAck) {
    assert(!persistedAck);
    snprintf(ackStatus, sizeof(ackStatus), "%s", status);
}
void logPrintln(const char*) {}
namespace pgl { namespace gld {
bool writeGldAlarmLatched(bool) { ++persisted; return true; }
} }
void optionalPinMode(int pin, uint8_t mode) {
    if (pin >= 0) events.push_back({'m', pin, mode});
}
void optionalDigitalWrite(int pin, uint8_t value) {
    if (pin >= 0) { events.push_back({'w', pin, value}); gpio[pin] = value; }
}
void logPrintf(const char* format, ...) {
    va_list args;
    va_start(args, format);
    vsnprintf(lastLog, sizeof(lastLog), format, args);
    va_end(args);
}
'''


SCENARIOS = r'''
int main() {
    pgl::gld::GldNullingProfile profile{};
    assert(!pgl::gld::isNullingProfileValid(profile));
    profile.validMagic = pgl::gld::NULLING_PROFILE_VALID_MAGIC;
    profile.profileId = 1;
    for (auto& ok : profile.channelOk) ok = 1;
    assert(pgl::gld::isNullingProfileValid(profile));
    beginGld1AlarmOutput();
    assert(board::PIN_ALARM_LAMP == 17 && board::PIN_BUZZER == -1);
    for (int pin : {board::PIN_SPI_SCK, board::PIN_SPI_MOSI, board::PIN_SPI_MISO,
                    board::PIN_ADS1256_CS, board::PIN_ADS1256_DRDY, board::PIN_ADS1256_SYNC,
                    board::PIN_LORA_CS, board::PIN_LORA_RST, board::PIN_LORA_BUSY,
                    board::PIN_LORA_DIO1, board::PIN_LORA_RXEN, board::PIN_LORA_TXEN,
                    board::PIN_I2C_SDA, board::PIN_I2C_SCL, board::PIN_STATUS_LED,
                    board::PIN_DC_FAN, board::PIN_TPL5110_DONE, board::PIN_POWER_LATCH_CLR,
                    board::PIN_BATTERY_VOLTAGE, board::PIN_24V_POWER_GOOD,
                    board::PIN_USER_BUTTON, board::PIN_RS485_DIR, board::PIN_RS485_RX,
                    board::PIN_RS485_TX}) assert(pin != 17);
    assert(events.size() == 3);
    assert(events[0].type == 'w' && events[0].pin == 17 && events[0].value == LOW);
    assert(events[1].type == 'm' && events[1].pin == 17 && events[1].value == OUTPUT);
    assert(events[2].type == 'w' && events[2].pin == 17 && events[2].value == LOW);
    for (int repeat = 0; repeat < 20; ++repeat) {
        setGld1AlarmOutput(true);
        assert(gpio[17] == HIGH);
    }
    setGld1AlarmOutput(false);
    assert(gpio[17] == LOW);
    for (bool manualMode : {false, true}) {
        alarmControlMode = manualMode ? pgl::gld::GldAlarmControlMode::Manual :
                                       pgl::gld::GldAlarmControlMode::Auto;
        for (bool manualCommand : {false, true}) {
            manualAlarmCommanded = manualCommand;
            for (bool inference : {false, true}) {
                events.clear();
                assert(updateAlarmOutputs(inference));
                const bool active = manualMode ? manualCommand : inference;
                assert(physicalAlarmCommanded == active);
                assert(lastAlarm == inference);
                assert(gpio[17] == (active ? HIGH : LOW));
                assert(gpio[39] == (active ? LOW : HIGH));
                for (const auto& event : events) assert(event.pin != 40 && event.pin != 41);
                assert(strstr(lastLog, active ? "gpio17Command=HIGH" : "gpio17Command=LOW"));
                assert(persisted == 0);
                // Invalid inference requests OFF in AUTO; explicit MANUAL
                // testing remains authoritative, as in the existing runtime.
                driveAlarmOutputs(false);
                const bool afterInvalid = manualMode && manualCommand;
                assert(physicalAlarmCommanded == afterInvalid);
                assert(gpio[17] == (afterInvalid ? HIGH : LOW));
            }
        }
    }
    puts("GLD1 GPIO17: PASS startup, AUTO, MANUAL, invalid, commanded logs");
    alarmControlMode = pgl::gld::GldAlarmControlMode::Auto;
    manualAlarmCommanded = false;
    lastAlarm = true;
    driveAlarmOutputs(true);
    onSetManualAlarmJson("{\"enabled\":true}");
    assert(strcmp(ackStatus, "rejected") == 0 && !manualAlarmCommanded);
    assert(physicalAlarmCommanded);
    onSetAlarmModeJson("{\"mode\":\"manual\"}");
    assert(strcmp(ackStatus, "ok") == 0 && !physicalAlarmCommanded);
    onSetManualAlarmJson("{\"enabled\":true}");
    assert(manualAlarmCommanded && physicalAlarmCommanded);
    onSetAlarmModeJson("{\"mode\":\"manual\"}");
    assert(!manualAlarmCommanded && !physicalAlarmCommanded);
    onSetManualAlarmJson("{\"enabled\":1}");
    assert(strcmp(ackStatus, "rejected") == 0 && !physicalAlarmCommanded);
    onSetAlarmModeJson("{\"mode\":\"invalid\"}");
    assert(strcmp(ackStatus, "rejected") == 0 && !physicalAlarmCommanded);
    onSetAlarmModeJson("{");
    assert(strcmp(ackStatus, "error") == 0 && !physicalAlarmCommanded);
    onSetAlarmModeJson("{\"mode\":\"auto\"}");
    assert(strcmp(ackStatus, "ok") == 0 && physicalAlarmCommanded);
    assert(!manualAlarmCommanded && statusEmitted == 4);
    // Exact GLD1 pending-radio replay expression, source-guarded above.
    for (bool freshValid : {false, true}) {
        for (bool freshAlarm : {false, true}) {
            updateAlarmOutputs(freshValid && freshAlarm);
            assert(physicalAlarmCommanded == (freshValid && freshAlarm));
        }
    }
    pgl::gld::GldSerialCommand parsed{};
    assert(decodeLine("SET_ALARM_MODE_JSON {\"mode\":\"manual\"}", parsed));
    assert(parsed.type == pgl::gld::GldSerialCommandType::SetAlarmModeJson);
    assert(strcmp(parsed.payload, "{\"mode\":\"manual\"}") == 0);
    assert(decodeLine("SET_MANUAL_ALARM_JSON {\"enabled\":true}", parsed));
    assert(parsed.type == pgl::gld::GldSerialCommandType::SetManualAlarmJson);
    assert(strcmp(parsed.payload, "{\"enabled\":true}") == 0);
    puts("GLD1 alarm serial parser/handlers: PASS payload, modes, clear, invalid input");
}
'''


def main():
    assert_baseline_preserved()
    source = (ROOT / RUNTIME).read_text(encoding="utf-8")
    setup = definition(source, "setup")
    assert setup.index("beginGld1AlarmOutput();") < setup.index("Serial.begin(115200);")
    functions = ("setGld1AlarmOutput", "beginGld1AlarmOutput", "drivePhysicalAlarmOutputs",
                 "driveAlarmOutputs", "updateAlarmOutputs", "onSetAlarmModeJson", "onSetManualAlarmJson")
    parser_header = (ROOT / "firmware/gld/include/GldCommandParser.h").read_text(encoding="utf-8")
    types = parser_header[parser_header.index("enum class GldSerialCommandType"):
                          parser_header.index("// Read USB CDC")]
    parser_source = (ROOT / "firmware/gld/src/GldCommandParser.cpp").read_text(encoding="utf-8")
    parser_fixture = ("namespace pgl { namespace gld {\n"
                      "enum class GldMode : uint8_t { INFERENCE, DATASET, NULLING };\n"
                      "GldMode gldModeFromString(const char*) { return GldMode::INFERENCE; }\n"
                      + types + "\n} }\nusing pgl::gld::GldSerialCommand;\n"
                      "using pgl::gld::GldSerialCommandType;\nusing pgl::gld::gldModeFromString;\n"
                      + definition(parser_source, "decodeLine"))
    program = STUBS + parser_fixture + "\n".join(definition(source, name) for name in functions) + SCENARIOS
    compiler = compiler_path()
    run_env = dict(os.environ)
    run_env["PATH"] = str(Path(compiler).parent) + os.pathsep + run_env.get("PATH", "")
    with tempfile.TemporaryDirectory(prefix="gld-pullup-") as directory:
        for header in ("BoardPins.h", "BoardPinsGLD2.h", "GldAlarmControl.h", "GldNullingProfile.h"):
            original = (ROOT / "firmware/gld/include" / header).read_text(encoding="utf-8")
            (Path(directory) / header).write_text(compatible_header(original), encoding="utf-8")
        fixture = Path(directory) / "alarm.cpp"
        fixture.write_text(program, encoding="utf-8")
        for gld2 in (0,):
            binary = Path(directory) / f"alarm-{gld2}.exe"
            subprocess.run([compiler, "-std=c++17", "-O0", "-Wall", "-Wextra", "-Werror",
                            f"-DPGL_GLD_BOARD_PROFILE_GLD2={gld2}",
                            f"-DPGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8={1 - gld2}",
                            "-I" + str(ROOT / "firmware/lib/ArduinoJson/src"),
                            str(fixture), "-o", str(binary)],
                           check=True, env=run_env, timeout=60)
            subprocess.run([str(binary)], check=True, env=run_env, timeout=10)


if __name__ == "__main__":
    main()
