"""Native SX126x airtime cross-check and production workflow radio service tests.

The service is extracted verbatim; dependencies are fake. The LoRa airtime
body is extracted from the vendored SX126x implementation, not transcribed.
No hardware, device, COM, firmware build, or package operation.
"""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def function(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def vendor_lora(source):
    start = source.index("uint32_t symbolLength_us =", source.index("RadioLibTime_t SX126x::getTimeOnAir("))
    terminator = "return((symbolLength_us * nSymbol_x4) / 4);"
    end = source.index(terminator, start) + len(terminator)
    return source[start:end]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--negative-control", action="store_true")
    parser.add_argument("--negative-control-guard", action="store_true")
    args = parser.parse_args()
    compiler = os.environ.get("MINGW_CXX") or shutil.which("g++") or str(
        Path.home() / ".platformio/packages/toolchain-gccmingw32/bin/g++.exe")
    env = dict(os.environ)
    env["PATH"] = str(Path(compiler).parent) + os.pathsep + env.get("PATH", "")
    scheduler = (ROOT / "firmware/gld/include/GldWorkflowRadioSchedule.h").read_text(encoding="utf-8")
    if args.negative_control:
        marker = "5u * toaUs + 999u"
        if scheduler.count(marker) != 1: raise AssertionError("missing timeout mutation marker")
        scheduler = scheduler.replace(marker, "toaUs + 999u", 1)
    main_source = (ROOT / "firmware/gld/src/GldUnifiedMain.cpp").read_text(encoding="utf-8")
    service = function(main_source, "bool serviceAtexWorkflowRadio()")
    reject = function(main_source, "bool rejectWorkflowMutation(")
    if args.negative_control_guard:
        guard = "if (atexConfigPersistenceFault && command.type == pgl::gld::GldSerialCommandType::Restart)"
        if reject.count(guard) != 1: raise AssertionError("missing guard mutation marker")
        reject = reject.replace(guard, "if (false && command.type == pgl::gld::GldSerialCommandType::Restart)", 1)
    loop_source = main_source[main_source.index("void loop() {"):]
    quarantine = function(loop_source, "if (workflowSharedSpiQuarantined)")
    loop_start = loop_source.index("    const bool leasedBeforeCommands =")
    loop_end_marker = "    if (atexQcSchedule.admissionHeld() || !serviceAtexWorkflowRadio()) pgl::gld::datasetworkflowwifi::poll();"
    loop_end = loop_source.index(loop_end_marker, loop_start) + len(loop_end_marker)
    loop_control = loop_source[loop_start:loop_end]
    vendor = vendor_lora((ROOT / "firmware/lib/RadioLib/src/modules/SX126x/SX126x.cpp").read_text(encoding="utf-8"))
    wide = vendor.replace("symbolLength_us * nSymbol_x4", "uint64_t(symbolLength_us) * nSymbol_x4")
    if wide == vendor: raise AssertionError("vendor multiplication marker changed")
    with tempfile.TemporaryDirectory(prefix="atex-radio-interaction-") as tmp:
        folder = Path(tmp)
        (folder / "GldWorkflowRadioSchedule.h").write_text(scheduler, encoding="utf-8")
        (folder / "workflow_service.inc").write_text(service, encoding="utf-8")
        (folder / "workflow_reject.inc").write_text(reject, encoding="utf-8")
        (folder / "workflow_quarantine.inc").write_text(quarantine, encoding="utf-8")
        (folder / "workflow_loop_control.inc").write_text(loop_control, encoding="utf-8")
        (folder / "vendor_lora.inc").write_text(vendor, encoding="utf-8")
        (folder / "vendor_lora_wide.inc").write_text(wide, encoding="utf-8")
        tests = ("test_workflow_airtime_vendor.cpp",) if args.negative_control else (
            "test_workflow_airtime_vendor.cpp", "test_workflow_radio_interaction.cpp")
        for name in tests:
            binary = folder / (name + ".exe")
            command = [compiler, "-std=c++1z", "-static", "-O0", "-Wall", "-Wextra", "-Werror", "-DPGL_GLD_BOARD_PROFILE_GLD_ATEX=1",
                       "-I", str(folder), str(HERE / name), "-o", str(binary)]
            subprocess.run(command, check=True, env=env, timeout=60)
            result = subprocess.run([str(binary)], env=env, timeout=30)
            if args.negative_control:
                if result.returncode == 0: raise AssertionError("unsafe timeout mutation not detected")
                print("PASS unsafe one-times-airtime timeout mutation rejected")
            elif args.negative_control_guard and name == "test_workflow_radio_interaction.cpp":
                if result.returncode == 0: raise AssertionError("missing persistence-fault restart guard not detected")
                print("PASS missing persistence-fault restart guard mutation rejected")
            elif result.returncode:
                raise subprocess.CalledProcessError(result.returncode, [str(binary)])


if __name__ == "__main__":
    main()
