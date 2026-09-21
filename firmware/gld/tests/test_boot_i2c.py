"""Compile and run the actual boot probe against a fake I2C bus.

Only the hardware/services are stubbed; BoardPins, reports, probe functions,
and GLD2 recovery come from the firmware. No COM/hardware is accessed.
Run with --source-ref HEAD --expect-cold-failure to reproduce the old defect.
Uses a host compiler (CXX, PATH, or PlatformIO's installed MinGW). Temporary
board-header copies expand only namespace syntax for older MinGW versions;
all pin/capability values and firmware function bodies remain unchanged.
"""

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[3]
RUNTIME = "firmware/gld/src/GldUnifiedMain.cpp"


def definition(source, name, struct=False):
    pattern = (rf"^struct {name}\s*\{{" if struct else
               rf"^[\w:]+ {name}\([^;]*?\)\s*\{{")
    match = re.search(pattern, source, re.MULTILINE)
    if not match:
        raise AssertionError(f"definition not found: {name}")
    depth = 1
    end = match.end()
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end] + (";" if struct else "")


STUBS = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "BoardPins.h"
namespace board = pgl::gld::board;
constexpr int LOW = 0, HIGH = 1, INPUT_PULLUP = 2, OUTPUT_OPEN_DRAIN = 3;
bool stuckLines = false;
void pinMode(int, int) {}
void digitalWrite(int, int) {}
int digitalRead(int) { return stuckLines ? LOW : HIGH; }
void delayMicroseconds(int) {}
void firmwareServiceTick() {}
void serviceDelay(uint32_t) {}
void logPrintln(const char*) {}
int gld1BeginLogs = 0;
void logPrintf(const char* format, ...) {
    if (strstr(format, "GLD1_BOOT_I2C_BEGIN")) ++gld1BeginLogs;
}
struct FakeWire {
    bool started = false, beginOk = true, tcaPresent = true;
    uint8_t mcpPresent = 0xff, selected = 0, powered = 0;
    uint8_t address = 0, data = 0, selectFailMask = 0, mcpAddress = 0x60;
    bool hasData = false;
    int begins = 0, ends = 0, transmissions = 0, beforeBegin = 0;
    int timeout = 0, sda = -1, scl = -1;
    bool begin(int a, int b) {
        ++begins; sda = a; scl = b; started = beginOk; return started;
    }
    void end() { ++ends; started = false; }
    void setTimeOut(uint16_t value) { timeout = value; }
    void beginTransmission(uint8_t addr) {
        ++transmissions;
        if (!started) ++beforeBegin;
        address = addr; hasData = false;
    }
    void write(uint8_t value) { data = value; hasData = true; }
    uint8_t endTransmission() {
        if (!started || stuckLines) return 4;
        if (address == board::TCA9548A_ADDR) {
            if (!tcaPresent || (hasData && (data & selectFailMask))) return 2;
            if (hasData) selected = data;
            return 0;
        }
        if (board::HAS_PCF8574 && address == board::PCF8574_ADDR) return 0;
        if (address == mcpAddress && (selected & mcpPresent)) {
            if (!board::HAS_PCF8574) return 0;
            for (unsigned i = 0; i < board::SENSOR_COUNT; ++i) {
                if ((selected & (1u << board::SENSOR_TO_MUX_CH[i])) &&
                    (powered & (1u << board::SENSOR_TO_POWER_EN[i]))) return 0;
            }
        }
        return 2;
    }
} Wire;
struct FakePcf {
    bool begin(FakeWire& wire) { return wire.started; }
    bool writeOutputs(uint8_t value) { Wire.powered = value; return Wire.started; }
} pcf8574;
bool pcfReady = false, pcfAllLoadSwitchesOn = false;
bool recoverGld2RootI2cForPcf(const char*);
'''


SCENARIOS = r'''
void resetBus() {
    Wire = FakeWire{};
    pcfReady = pcfAllLoadSwitchesOn = false;
    stuckLines = false;
    gld1BeginLogs = 0;
}
void expectCount(const BootI2cReport& report, unsigned count) {
    assert(report.mcpOkCount == count);
    unsigned actual = 0;
    for (unsigned i = 0; i < board::SENSOR_COUNT; ++i) {
        actual += report.mcpOk[i];
        assert(report.mcpOk[i] == ((report.mcpAddrMask[i] & 1) != 0));
    }
    assert(actual == count);
}
int main() {
#if EXPECT_COLD_FAILURE && !PGL_GLD_BOARD_PROFILE_GLD2
    resetBus();
    const auto cold = probeBootI2c(true);
    assert(!cold.tcaOk);
    expectCount(cold, 0);
    assert(Wire.begins == 0 && Wire.beforeBegin > 0);
    Wire.begin(board::PIN_I2C_SDA, board::PIN_I2C_SCL);
    const auto warm = probeBootI2c(true);
    assert(warm.tcaOk);
    expectCount(warm, 8);
    puts("GLD1 baseline: cold bus fails 0/8; started bus passes 8/8 (reproduced)");
    return 0;
#endif
    for (bool fullScan : {false, true}) {
        resetBus();
        const auto healthy = probeBootI2c(fullScan);
        assert(healthy.tcaOk);
        assert(healthy.fullBusScanPerformed == fullScan);
        expectCount(healthy, 8);
        assert(Wire.beforeBegin == 0 && Wire.begins == 1);
        assert(Wire.sda == 8 && Wire.scl == 9 && Wire.timeout == 50);
        assert(Wire.selected == 0);
#if PGL_GLD_BOARD_PROFILE_GLD2
        assert(gld1BeginLogs == 0 && Wire.ends == 1 && Wire.powered == 0);
#else
        assert(gld1BeginLogs == 1 && Wire.ends == 0);
#endif
        const auto repeated = probeBootI2c(fullScan);
        assert(repeated.tcaOk);
        expectCount(repeated, 8);

        resetBus();
        Wire.tcaPresent = false;
        const auto noTca = probeBootI2c(fullScan);
        assert(!noTca.tcaOk);
        expectCount(noTca, 0);

        for (unsigned missing = 0; missing < board::SENSOR_COUNT; ++missing) {
            resetBus();
            Wire.mcpPresent &= ~(1u << board::SENSOR_TO_MUX_CH[missing]);
            const auto oneMissing = probeBootI2c(fullScan);
            assert(oneMissing.tcaOk && !oneMissing.mcpOk[missing]);
            expectCount(oneMissing, 7);
        }

        resetBus();
        Wire.mcpPresent = 0;
        const auto noMcp = probeBootI2c(fullScan);
        assert(noMcp.tcaOk);
        expectCount(noMcp, 0);

        resetBus();
        Wire.selectFailMask = 1u << board::SENSOR_TO_MUX_CH[3];
        const auto selectFailed = probeBootI2c(fullScan);
        assert(selectFailed.tcaOk && !selectFailed.mcpOk[3]);
        expectCount(selectFailed, 7);

        resetBus();
        Wire.mcpAddress = 0x61;
        const auto wrongAddress = probeBootI2c(fullScan);
        assert(wrongAddress.tcaOk);
        expectCount(wrongAddress, 0);

        resetBus();
        Wire.beginOk = false;
        const auto beginFailed = probeBootI2c(fullScan);
        assert(!beginFailed.tcaOk);
        expectCount(beginFailed, 0);
#if !PGL_GLD_BOARD_PROFILE_GLD2
        assert(Wire.transmissions == 0);
#endif

        resetBus();
        stuckLines = true;
        const auto stuck = probeBootI2c(fullScan);
        assert(!stuck.tcaOk);
        expectCount(stuck, 0);
    }
    puts(PGL_GLD_BOARD_PROFILE_GLD2 ? "GLD2 boot probe: PASS (unchanged path)" :
         "GLD1 boot probe: PASS (cold/warm, missing devices, address/select/init/bus faults)");
}
'''


def compiler_path():
    candidates = [os.environ.get("CXX"), shutil.which("g++"), shutil.which("clang++"),
                  str(Path.home() / ".platformio/packages/toolchain-gccmingw32/bin/g++.exe")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise RuntimeError("Host C++ compiler missing; set CXX to its executable")


def compatible_header(source):
    source = re.sub(r"namespace ([\w]+(?:::\w+)+) \{",
                    lambda m: " ".join(f"namespace {part} {{" for part in m[1].split("::")),
                    source)
    return re.sub(r"\}  // namespace ([\w]+(?:::\w+)+)",
                  lambda m: "}" * len(m[1].split("::")) + " // namespace " + m[1],
                  source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-ref")
    parser.add_argument("--expect-cold-failure", action="store_true")
    args = parser.parse_args()
    source = (subprocess.check_output(["git", "show", f"{args.source_ref}:{RUNTIME}"],
                                     cwd=ROOT, text=True, encoding="utf-8")
              if args.source_ref else (ROOT / RUNTIME).read_text(encoding="utf-8"))
    constants = "\n".join(re.findall(
        r"^constexpr \w+ BOOT_(?:I2C_TIMEOUT_MS|SENSOR_MODULE_POWER_SETTLE_MS) = \d+;",
        source, re.MULTILINE))
    functions = ["copyBounded", "i2cAck", "tcaSelect", "tcaDisableAll",
                 "scanMcpAddressMaskOnSelectedMux", "scanI2cBus", "probeSelectedMcp4725",
                 "recoverGld2RootI2cForPcf", "probeBootI2c"]
    program = ("#include <initializer_list>\n" + STUBS + constants + "\n" +
               definition(source, "BootI2cReport", struct=True) + "\n" +
               "\n".join(definition(source, name) for name in functions) + SCENARIOS)
    compiler = compiler_path()
    run_env = dict(os.environ)
    run_env["PATH"] = str(Path(compiler).parent) + os.pathsep + run_env.get("PATH", "")
    with tempfile.TemporaryDirectory(prefix="gld-boot-i2c-") as directory:
        for header in ("BoardPins.h", "BoardPinsGLD2.h"):
            original = (ROOT / "firmware/gld/include" / header).read_text(encoding="utf-8")
            (Path(directory) / header).write_text(compatible_header(original), encoding="utf-8")
        fixture = Path(directory) / "boot.cpp"
        fixture.write_text(program, encoding="utf-8")
        for gld2 in (0, 1):
            binary = Path(directory) / f"boot-{gld2}.exe"
            command = [compiler, "-std=c++17", "-O0", "-Wall", "-Wextra", "-Werror",
                       "-DARDUINO_ARCH_ESP32=1", f"-DPGL_GLD_BOARD_PROFILE_GLD2={gld2}",
                       f"-DPGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8={1 - gld2}",
                       f"-DEXPECT_COLD_FAILURE={int(args.expect_cold_failure)}",
                       "-I", str(ROOT / "firmware/gld/include"), str(fixture), "-o", str(binary)]
            subprocess.run(command, check=True, env=run_env, timeout=60)
            subprocess.run([str(binary)], check=True, env=run_env, timeout=10)


if __name__ == "__main__":
    main()
