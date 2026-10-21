"""Run real nulling C++ on a host with ADC/DAC/NVS doubles, not hardware.

The available Windows MinGW compiler is GCC 5. It predates C++17 nested
namespace syntax, so copy sources into a temporary directory and rewrite only
namespace spelling; never alter decisions, constants or production files.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
INCLUDES = ROOT / "firmware/gld/include"
SOURCE = ROOT / "firmware/gld/src/GldNullingService.cpp"


def legacy_namespaces(text: str) -> str:
    text = text.replace("namespace pgl::gld {", "namespace pgl { namespace gld {")
    text = text.replace("}  // namespace pgl::gld", "}}  // namespace pgl::gld")
    for header in ("SPI.h", "Wire.h", "Arduino.h", "Preferences.h"):
        text = text.replace(f"#include <{header}>", f'#include "{header}"')
    return text


def main() -> None:
    compiler = os.environ.get("MINGW_CXX") or shutil.which("g++")
    if not compiler:
        compiler = str(Path.home() / ".platformio/packages/toolchain-gccmingw32/bin/g++.exe")
    if not Path(compiler).is_file():
        raise SystemExit("Host C++ compiler not found; set MINGW_CXX")
    env = dict(os.environ)
    env["PATH"] = str(Path(compiler).parent) + os.pathsep + env["PATH"]
    with tempfile.TemporaryDirectory(prefix="gld1-nulling-native-") as temp:
        folder = Path(temp)
        for name in ("Arduino.h", "SPI.h", "Wire.h", "Preferences.h"):
            shutil.copy2(HERE / name, folder / name)
        board = (HERE / "BoardPins.h").read_text(encoding="utf-8")
        board = board.replace("namespace pgl::gld::board {", "namespace pgl { namespace gld { namespace board {")
        board = board.rstrip()[:-1] + "}}}\n"
        (folder / "BoardPins.h").write_text(board, encoding="utf-8")
        for name in ("GldAds1256Reader.h", "GldDacMux.h", "GldNullingProfile.h", "GldNullingService.h"):
            text = (INCLUDES / name).read_text(encoding="utf-8")
            (folder / name).write_text(legacy_namespaces(text), encoding="utf-8")
        (folder / SOURCE.name).write_text(legacy_namespaces(SOURCE.read_text(encoding="utf-8")), encoding="utf-8")
        harness = (HERE / "test_nulling_native.cpp").read_text(encoding="utf-8")
        harness = harness.replace('#include "../../src/GldNullingService.cpp"', '#include "GldNullingService.cpp"')
        harness = harness.replace("namespace pgl::gld {", "namespace pgl { namespace gld {")
        harness = harness.replace("\n}\n\nstatic void logLine", "\n}}\n\nstatic void logLine")
        (folder / "test.cpp").write_text(harness, encoding="utf-8")
        exe = folder / ("test.exe" if os.name == "nt" else "test")
        command = [compiler, "-std=c++1z", "-static", "-DPGL_GLD1_FAST_NULLING=1",
                   "-DPGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8=1", "-DPGL_GLD_BOARD_PROFILE_GLD2=0",
                   "-I", folder.as_posix(), (folder / "test.cpp").as_posix(), "-o", exe.as_posix()]
        subprocess.run(command, env=env, check=True)
        subprocess.run([str(exe)], env=env, check=True)
        legacy = folder / ("legacy.exe" if os.name == "nt" else "legacy")
        other_command = [compiler, "-std=c++1z", "-static", "-DNATIVE_SCOPE_ONLY=1",
                         "-DPGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8=0", "-DPGL_GLD_BOARD_PROFILE_GLD2=1",
                         "-I", folder.as_posix(), (folder / "test.cpp").as_posix(), "-o", legacy.as_posix()]
        subprocess.run(other_command, env=env, check=True)
        subprocess.run([str(legacy)], env=env, check=True)
        model3 = folder / ("model3.exe" if os.name == "nt" else "model3")
        model3_command = [compiler, "-std=c++1z", "-static", "-DNATIVE_SCOPE_ONLY=1",
                          "-DPGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8=1", "-DPGL_GLD_BOARD_PROFILE_GLD2=0",
                          "-I", folder.as_posix(), (folder / "test.cpp").as_posix(), "-o", model3.as_posix()]
        subprocess.run(model3_command, env=env, check=True)
        subprocess.run([str(model3)], env=env, check=True)


if __name__ == "__main__":
    main()
