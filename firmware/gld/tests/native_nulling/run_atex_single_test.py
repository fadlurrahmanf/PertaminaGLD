"""Compile the production single-null handler with fake JSON/ADC/DAC/NVS.

Host-only; no hardware, firmware build, package, or device operations.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def extract(source):
    signature = "void onRunNullingSingleJson(const char* payload)"
    start = source.index(signature)
    brace = source.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def main():
    compiler = os.environ.get("MINGW_CXX") or shutil.which("g++") or str(
        Path.home() / ".platformio/packages/toolchain-gccmingw32/bin/g++.exe")
    env = dict(os.environ)
    env["PATH"] = str(Path(compiler).parent) + os.pathsep + env.get("PATH", "")
    source = (ROOT / "firmware/gld/src/GldUnifiedMain.cpp").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="atex-single-native-") as tmp:
        folder = Path(tmp)
        (folder / "handler.inc").write_text(extract(source), encoding="utf-8")
        shutil.copy2(HERE / "test_atex_single_native.cpp", folder / "test.cpp")
        for name, gld2, atex in (("gld1", 0, 0), ("gld2", 1, 0), ("atex", 1, 1)):
            binary = folder / (name + ".exe")
            command = [compiler, "-std=c++1z", "-static", "-Wall", "-Wextra", "-Werror",
                       "-DPGL_GLD1_FAST_NULLING=1", f"-DPGL_GLD_BOARD_PROFILE_GLD2={gld2}",
                       f"-DPGL_GLD_BOARD_PROFILE_GLD_ATEX={atex}",
                       f"-DPGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8={1-gld2}",
                       "-I", str(folder), str(folder / "test.cpp"), "-o", str(binary)]
            subprocess.run(command, check=True, env=env, timeout=60)
            subprocess.run([str(binary)], check=True, env=env, timeout=10)


if __name__ == "__main__":
    main()
