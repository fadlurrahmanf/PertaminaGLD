"""ATEX preflight tests with temporary synthetic inputs and a fake SCons env."""
import configparser
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
NAMES = tuple(f"gld_atex_model_{n}_workflow_candidate" for n in (1, 2, 3))
GLD = tuple(f"gld_model_{n}_dataset_workflow_wifi" for n in (1, 2, 3))
SECRET = "fixtureAlpha_2026"


class FakeEnv:
    def __init__(self, project, name):
        self.values = {"$PROJECT_DIR": str(project), "$PIOENV": name,
                       "$BUILD_DIR": str(project / ".pio/build-atex-private-candidates" / name)}
        self.includes = []

    def subst(self, value):
        return self.values[value]

    def Prepend(self, CPPPATH):
        self.includes[0:0] = CPPPATH


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "firmware"
        tools = self.project / "tools"
        tools.mkdir(parents=True)
        for name in ("prepare_atex_workflow_wifi.py", "prepare_atex_workflow_wifi_build.py"):
            (tools / name).write_bytes((ROOT / "firmware/tools" / name).read_bytes())
        resolver = self.root / "apps/gld-operator/workflow_credentials.py"
        resolver.parent.mkdir(parents=True)
        resolver.write_bytes((ROOT / "apps/gld-operator/workflow_credentials.py").read_bytes())
        for name in GLD:
            config = self.project / ".pio/gld-dataset-workflow-wifi" / name / "credentials.local.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps(dict(environment=name, username="gld", password=SECRET,
                protocol="gld-dataset-wifi/3", address="192.168.4.1", port=81, path="/dataset")))
        spec = importlib.util.spec_from_file_location("atex_build_fixture", tools / "prepare_atex_workflow_wifi_build.py")
        self.build_script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.build_script)

    def test_all_candidates_prepend_private_header(self):
        for name in NAMES:
            env = FakeEnv(self.project, name)
            env.includes.append("previous-include")
            self.build_script.configure(env)
            header = Path(env.includes[0]) / "GldDatasetWorkflowWifiSecrets.h"
            self.assertIn(SECRET, header.read_text())
            self.assertEqual(env.includes[1], "previous-include")

    def test_scons_exec_without_file_global(self):
        env = FakeEnv(self.project, NAMES[0])
        source = (self.project / "tools/prepare_atex_workflow_wifi_build.py").read_text()
        namespace = {"env": env, "Import": lambda name: None}
        exec(compile(source, "scons-extra-script", "exec"), namespace)
        self.assertTrue((Path(env.includes[0]) / "GldDatasetWorkflowWifiSecrets.h").is_file())

    def test_cached_objects_fail_without_removal(self):
        env = FakeEnv(self.project, NAMES[0])
        artifact = Path(env.values["$BUILD_DIR"]) / "src/firmware.o"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"fixture")
        with self.assertRaisesRegex(RuntimeError, "^ATEX build preflight failed$"):
            self.build_script.configure(env)
        self.assertTrue(artifact.is_file())
        self.assertFalse(env.includes)

    def test_wrong_build_path_and_gld_environment_rejected(self):
        env = FakeEnv(self.project, NAMES[0])
        env.values["$BUILD_DIR"] = str(self.project / ".pio/build" / NAMES[0])
        with self.assertRaises(RuntimeError):
            self.build_script.configure(env)
        env = FakeEnv(self.project, GLD[0])
        with self.assertRaises(RuntimeError):
            self.build_script.configure(env)
        self.assertFalse(env.includes)

    def test_synthetic_sentinel_fails_closed(self):
        env = FakeEnv(self.project, NAMES[0])
        for name in NAMES:
            path = self.project / ".pio/gld-dataset-workflow-wifi" / name / "credentials.local.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(dict(environment=name, username="gld", protocol="gld-dataset-wifi/3",
                                            password="SYNTHETIC_TEST_ONLY")))
        with self.assertRaises(RuntimeError):
            self.build_script.configure(env)
        self.assertFalse(env.includes)

    def test_only_atex_candidate_script_is_changed(self):
        config = configparser.ConfigParser(interpolation=None, strict=True)
        config.read(ROOT / "firmware/platformio.ini", encoding="utf-8")
        for name in NAMES:
            section = config["env:" + name]
            if name == NAMES[0]:
                self.assertEqual(section["extra_scripts"], "pre:tools/prepare_atex_workflow_wifi_build.py")
            else:
                self.assertEqual(section["extends"], "env:" + NAMES[0])
        for name in GLD:
            self.assertNotIn("prepare_atex_workflow_wifi_build", config["env:" + name].get("extra_scripts", ""))


if __name__ == "__main__":
    unittest.main()
