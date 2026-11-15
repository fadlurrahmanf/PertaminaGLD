"""Regression: runtime profile selection must match packager, no deployed files."""
import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIRMWARE = ROOT / "firmware"
SOURCE = FIRMWARE / "gld/src/GldUnifiedMain.cpp"
PACKAGER = FIRMWARE / "tools/operator_package_post.py"


def compiler():
    explicit = os.environ.get("CXX")
    if explicit:
        return explicit
    found = shutil.which("g++")
    fallback = Path.home() / ".platformio/packages/toolchain-gccmingw32/bin/g++.exe"
    return found or (str(fallback) if fallback.is_file() else None)


@unittest.skipUnless(compiler(), "C++ compiler required for runtime selector test")
class RuntimeVersionContract(unittest.TestCase):
    def test_profile_selection_matches_real_packager_and_catches_wrong_guard(self):
        source = SOURCE.read_text(encoding="utf-8")
        match = re.search(r"(?ms)^#if PGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8 && !PGL_GLD_BOARD_PROFILE_GLD2\nconstexpr const char\* GLD_RUNTIME_FIRMWARE_VERSION = pgl::firmware::GLD1_FIRMWARE_VERSION;\n#else\nconstexpr const char\* GLD_RUNTIME_FIRMWARE_VERSION = pgl::firmware::GLD_FIRMWARE_VERSION;\n#endif", source)
        self.assertIsNotNone(match, "runtime version guard changed; reassess board contract")
        selector = match.group(0)
        spec = importlib.util.spec_from_file_location("version_contract_packager", PACKAGER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        versions = {"GLD1_FIRMWARE_VERSION":"1.2.3", "GLD_FIRMWARE_VERSION":"4.5.6", "CH_FIRMWARE_VERSION":"7.8.9", "GATEWAY_FIRMWARE_VERSION":"7.8.9"}
        mutant_all_gld1 = selector.replace("#if PGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8 && !PGL_GLD_BOARD_PROFILE_GLD2", "#if 1", 1)
        mutant_all_gld2 = selector.replace("#if PGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8 && !PGL_GLD_BOARD_PROFILE_GLD2", "#if 0", 1)
        self.assertNotEqual(selector, mutant_all_gld1)
        self.assertNotEqual(selector, mutant_all_gld2)
        with tempfile.TemporaryDirectory(prefix="gld-version-contract-") as temp:
            cpp = Path(temp) / "selector.cpp"
            exe = Path(temp) / ("selector.exe" if os.name == "nt" else "selector")
            def selected(block, wroom, board2):
                cpp.write_text("#include <cstdio>\nnamespace pgl { namespace firmware { constexpr const char* GLD1_FIRMWARE_VERSION=\"1.2.3\"; constexpr const char* GLD_FIRMWARE_VERSION=\"4.5.6\"; } }\n"+block+"\nint main(){std::puts(GLD_RUNTIME_FIRMWARE_VERSION); }\n",encoding="utf-8")
                env = os.environ.copy(); env["PATH"] = str(Path(compiler()).parent) + os.pathsep + env.get("PATH", "")
                cmd = [compiler(), "-std=c++17", f"-DPGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8={wroom}", f"-DPGL_GLD_BOARD_PROFILE_GLD2={board2}", str(cpp), "-o", str(exe)]
                if os.name == "nt": cmd.insert(1,"-static")
                subprocess.run(cmd, check=True, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
                return subprocess.check_output([str(exe)], env=env, text=True, timeout=15).strip()
            for environment, wroom, board2 in (("gld",1,0),("gld_model_1",1,0),("gld_model_2",1,0),("gld_model_3",1,0),("gld_v2",0,1),("gld_atex",0,1),("gld_atex_model_1_workflow_candidate",0,1),("gld_atex_model_2_workflow_candidate",0,1),("gld_atex_model_3_workflow_candidate",0,1)):
                with self.subTest(environment=environment):
                    self.assertEqual(selected(selector, wroom, board2), module._firmware_version(environment, versions))
            self.assertNotEqual(selected(mutant_all_gld2, 1, 0), module._firmware_version("gld", versions))
            self.assertNotEqual(selected(mutant_all_gld1, 0, 1), module._firmware_version("gld_atex", versions))


if __name__ == "__main__":
    unittest.main()
