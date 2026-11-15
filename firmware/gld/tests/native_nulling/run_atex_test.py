"""Host nulling test using real service/DAC code and fake physical I2C/ADC/NVS.

No hardware, firmware build, package, or device action. The literal fixture map
is an independent test oracle, not a measurement of a real ATEX board.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
INC = ROOT / "firmware/gld/include"
SRC = ROOT / "firmware/gld/src"


def old_namespace(text):
    text = re.sub(r"namespace ([\w]+(?:::\w+)+) \{ (namespace \w+ = [\w:]+;) \}",
                  lambda m: " ".join(f"namespace {part} {{" for part in m[1].split("::")) +
                  " " + m[2] + " " + "}" * len(m[1].split("::")), text)
    text = re.sub(r"namespace ([\w]+(?:::\w+)+) \{",
                  lambda m: " ".join(f"namespace {part} {{" for part in m[1].split("::")), text)
    text = re.sub(r"\}  // namespace ([\w]+(?:::\w+)+)",
                  lambda m: "}" * len(m[1].split("::")) + " // namespace " + m[1], text)
    for header in ("SPI.h", "Wire.h", "Arduino.h", "Preferences.h", "TCA9548.h"):
        text = text.replace(f"#include <{header}>", f'#include "{header}"')
    return text


def extract_function(text, signature):
    start = text.index(signature)
    opening = text.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


WIRE = r'''#pragma once
#include <cstdint>
#include <cstddef>
class TwoWire {
public:
 bool begin(int, int); void end(); void setTimeOut(uint16_t);
 void beginTransmission(uint8_t); void write(uint8_t); uint8_t endTransmission();
 size_t requestFrom(uint8_t, uint8_t); int available(); int read();
};
extern TwoWire Wire;
'''
TCA = r'''#pragma once
#include <cstdint>
#include "Wire.h"
class TCA9548 {
public:
 TCA9548(uint8_t, TwoWire*) {} void setForced(bool) {} bool begin() {return true;}
 bool selectChannel(uint8_t);
};
'''


def main():
    compiler = os.environ.get("MINGW_CXX") or shutil.which("g++") or str(
        Path.home() / ".platformio/packages/toolchain-gccmingw32/bin/g++.exe")
    env = dict(os.environ)
    env["PATH"] = str(Path(compiler).parent) + os.pathsep + env.get("PATH", "")
    with tempfile.TemporaryDirectory(prefix="atex-nulling-native-") as tmp:
        folder = Path(tmp)
        for name in ("SPI.h", "Arduino.h", "Preferences.h"):
            shutil.copy2(HERE / name, folder / name)
        (folder / "Wire.h").write_text(WIRE, encoding="utf-8")
        (folder / "TCA9548.h").write_text(TCA, encoding="utf-8")
        for name in ("BoardPins.h", "BoardPinsGLD2.h", "BoardPinsGLD3.h", "BoardPinsGLDATEX.h",
                     "GldAds1256Reader.h", "GldDacMux.h", "GldPcf8574.h", "GldNullingProfile.h",
                     "GldNullingService.h"):
            (folder / name).write_text(old_namespace((INC / name).read_text(encoding="utf-8")), encoding="utf-8")
        for name in ("GldDacMux.cpp", "GldNullingService.cpp"):
            (folder / name).write_text(old_namespace((SRC / name).read_text(encoding="utf-8")), encoding="utf-8")
        (folder / "save_gate.inc").write_text(extract_function(
            (SRC / "GldUnifiedMain.cpp").read_text(encoding="utf-8"),
            "bool saveCompleteNullingProfile("), encoding="utf-8")
        adc_source = (SRC / "GldAds1256Reader.cpp").read_text(encoding="utf-8")
        if "muxSingleEnded(adsInputForSensor(channel))" not in adc_source:
            raise AssertionError("ADC reader no longer calls its sensor mapping helper")
        (folder / "adc_gate.inc").write_text(extract_function(
            adc_source, "uint8_t adsInputForSensor("), encoding="utf-8")
        (folder / "test.cpp").write_text(old_namespace(
            (HERE / "test_atex_nulling_native.cpp").read_text(encoding="utf-8")), encoding="utf-8")
        for name, gld2, atex in (("gld1", 0, 0), ("gld2", 1, 0), ("atex", 1, 1)):
            exe = folder / (name + ".exe")
            # GLD1's preprocessor selects one of two internal algorithms;
            # compiling their translation unit into this harness can leave the
            # other internal function unused even though production is valid.
            command = [compiler, "-std=c++1z", "-static", "-O0", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
                       "-DPGL_GLD1_FAST_NULLING=1", f"-DPGL_GLD_BOARD_PROFILE_GLD2={gld2}",
                       f"-DPGL_GLD_BOARD_PROFILE_GLD_ATEX={atex}",
                       f"-DPGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8={1-gld2}",
                       "-I", str(folder), str(folder / "test.cpp"), "-o", str(exe)]
            subprocess.run(command, check=True, env=env, timeout=60)
            subprocess.run([str(exe)], check=True, env=env, timeout=30)


if __name__ == "__main__":
    main()

