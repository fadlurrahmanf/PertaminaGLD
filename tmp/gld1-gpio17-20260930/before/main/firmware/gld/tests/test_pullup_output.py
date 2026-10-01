"""Execute actual alarm output functions on a host; never access hardware.

Checks inverted GPIO41, initial output-latch ordering, AUTO/MANUAL truth table,
logs based on the physical command, and the unchanged GLD2 output sequence.
"""

import os
from pathlib import Path
import subprocess
import tempfile

from test_boot_i2c import ROOT, RUNTIME, compatible_header, compiler_path, definition


STUBS = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdarg>
#include <cstring>
#include <initializer_list>
#include <vector>
#include "BoardPins.h"
#include "GldAlarmControl.h"
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
    beginGld1AlarmOutput();
#if PGL_GLD_BOARD_PROFILE_GLD2
    assert(events.empty());
    drivePhysicalAlarmOutputs(true);
    assert(events.size() == 2);
    assert(events[0].pin == 15 && events[0].value == HIGH);
    assert(events[1].pin == 40 && events[1].value == HIGH);
    events.clear();
    drivePhysicalAlarmOutputs(false);
    assert(events.size() == 2);
    assert(events[0].pin == 40 && events[0].value == LOW);
    assert(events[1].pin == 15 && events[1].value == LOW);
#else
    assert(board::PIN_ALARM_LAMP == 41 && board::PIN_BUZZER == -1);
    assert(events.size() == 3);
    assert(events[0].type == 'w' && events[0].pin == 41 && events[0].value == HIGH);
    assert(events[1].type == 'm' && events[1].pin == 41 && events[1].value == OUTPUT);
    assert(events[2].type == 'w' && events[2].pin == 41 && events[2].value == HIGH);
#endif
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
#if PGL_GLD_BOARD_PROFILE_GLD2
                assert(gpio[40] == (active ? HIGH : LOW));
                assert(gpio[15] == (active ? HIGH : LOW));
                for (const auto& event : events) assert(event.pin != 41);
#else
                assert(gpio[41] == (active ? LOW : HIGH));
                assert(gpio[39] == (active ? LOW : HIGH));
                for (const auto& event : events) assert(event.pin != 40);
                assert(strstr(lastLog, active ? "gpio41Command=LOW" : "gpio41Command=HIGH"));
                assert(strstr(lastLog, active ? "j2LampExpected=HIGH" : "j2LampExpected=LOW"));
                assert(persisted == 0);
#endif
                // Invalid inference requests OFF in AUTO; explicit MANUAL
                // testing remains authoritative, as in the existing runtime.
                driveAlarmOutputs(false);
                const bool afterInvalid = manualMode && manualCommand;
                assert(physicalAlarmCommanded == afterInvalid);
#if !PGL_GLD_BOARD_PROFILE_GLD2
                assert(gpio[41] == (afterInvalid ? LOW : HIGH));
#endif
            }
        }
    }
    puts(PGL_GLD_BOARD_PROFILE_GLD2 ? "GLD2 alarm output: PASS (unchanged sequence)" :
         "GLD1 J2 pull-up output: PASS (startup, AUTO, MANUAL, invalid, commanded logs)");
}
'''


def main():
    source = (ROOT / RUNTIME).read_text(encoding="utf-8")
    setup = definition(source, "setup")
    assert setup.index("beginGld1AlarmOutput();") < setup.index("Serial.begin(115200);")
    functions = ("setGld1AlarmOutput", "beginGld1AlarmOutput", "drivePhysicalAlarmOutputs",
                 "driveAlarmOutputs", "updateAlarmOutputs")
    program = STUBS + "\n".join(definition(source, name) for name in functions) + SCENARIOS
    compiler = compiler_path()
    run_env = dict(os.environ)
    run_env["PATH"] = str(Path(compiler).parent) + os.pathsep + run_env.get("PATH", "")
    with tempfile.TemporaryDirectory(prefix="gld-pullup-") as directory:
        for header in ("BoardPins.h", "BoardPinsGLD2.h", "GldAlarmControl.h"):
            original = (ROOT / "firmware/gld/include" / header).read_text(encoding="utf-8")
            (Path(directory) / header).write_text(compatible_header(original), encoding="utf-8")
        fixture = Path(directory) / "alarm.cpp"
        fixture.write_text(program, encoding="utf-8")
        for gld2 in (0, 1):
            binary = Path(directory) / f"alarm-{gld2}.exe"
            subprocess.run([compiler, "-std=c++17", "-O0", "-Wall", "-Wextra", "-Werror",
                            f"-DPGL_GLD_BOARD_PROFILE_GLD2={gld2}",
                            f"-DPGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8={1 - gld2}",
                            str(fixture), "-o", str(binary)],
                           check=True, env=run_env, timeout=60)
            subprocess.run([str(binary)], check=True, env=run_env, timeout=10)


if __name__ == "__main__":
    main()
