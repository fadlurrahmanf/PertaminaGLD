"""Host-only scope/credential tests; these do not compile firmware or use a board."""
from __future__ import annotations

import configparser
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
MAIN = "firmware/gld/src/GldUnifiedMain.cpp"
INI = "firmware/platformio.ini"


def baseline(path: str) -> str:
    return subprocess.check_output(["git", "show", f"HEAD:{path}"], cwd=ROOT, encoding="utf-8")


def without_wifi_blocks(source: str) -> str:
    """Evaluate only the new feature guards with the flag absent; keep all others."""
    stack = []
    output = []
    for line in source.splitlines(keepends=True):
        directive = line.strip()
        if re.match(r"#\s*(if|ifdef|ifndef)\b", directive):
            feature = "PGL_GLD_DATASET_WIFI" in directive
            enabled = "!defined(PGL_GLD_DATASET_WIFI)" in directive if feature else True
            stack.append([feature, enabled])
            if feature:
                continue
        elif directive.startswith("#else") and stack:
            if stack[-1][0]:
                stack[-1][1] = not stack[-1][1]
                continue
        elif directive.startswith("#endif") and stack:
            feature, _ = stack.pop()
            if feature:
                continue
        if all(not feature or enabled for feature, enabled in stack):
            output.append(line)
    if stack:
        raise AssertionError("Unbalanced conditional guards")
    return "".join(output)


def ini(text: str) -> configparser.ConfigParser:
    result = configparser.ConfigParser(interpolation=None, strict=False)
    result.read_string(text)
    return result


class DatasetWifiScopeTests(unittest.TestCase):
    def test_flag_absent_preserves_all_existing_main_source(self):
        current = (ROOT / MAIN).read_text(encoding="utf-8")
        # Empty lines left at additive boundaries do not change preprocessing.
        meaningful = lambda text: "\n".join(line for line in text.splitlines() if line.strip())
        self.assertEqual(meaningful(without_wifi_blocks(current)), meaningful(baseline(MAIN)))

    def test_existing_platformio_environments_preserved(self):
        old, current = ini(baseline(INI)), ini((ROOT / INI).read_text(encoding="utf-8"))
        for section in old.sections():
            with self.subTest(section=section):
                self.assertEqual(dict(current[section]), dict(old[section]))

    def test_only_three_isolated_models_enable_transport_without_packaging(self):
        config = ini((ROOT / INI).read_text(encoding="utf-8"))
        expected = {f"env:gld_model_{i}_dataset_wifi" for i in (1, 2, 3)}
        flagged = {section for section in config.sections()
                   if "-DPGL_GLD_DATASET_WIFI=1" in config[section].get("build_flags", "")}
        self.assertEqual(flagged, expected)
        for section in expected:
            values = config[section]
            self.assertEqual(values["extends"], section.removesuffix("_dataset_wifi"))
            self.assertEqual(values["extra_scripts"], "pre:tools/prepare_dataset_wifi.py")
            self.assertIn("links2004/WebSockets@2.6.1", values["lib_deps"])
            self.assertIn("-DNODEBUG_WEBSOCKETS", values["build_flags"])
            self.assertIn("+<gld/src/GldDatasetWifi.cpp>", values["build_src_filter"])

    def test_network_library_has_one_owner_and_no_sampler_calls(self):
        source = (ROOT / "firmware/gld/src/GldDatasetWifi.cpp").read_text(encoding="utf-8")
        sampler = source.split("void sampler(void*)", 1)[1].split("void process(", 1)[0]
        self.assertNotRegex(sampler, r"socket\.|WiFi\.|mqtt\.")
        self.assertIn("xQueueSend(outgoing, &message, 0)", source)
        self.assertIn('stopLocked("outbound_queue_full", true)', source)
        self.assertIn('stopLocked("disconnected", true)', source)
        self.assertIn('socket.setAuthorization("gld", password)', source)


class DatasetWifiCredentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "private_wifi_preparer", ROOT / "firmware/tools/prepare_dataset_wifi.py")
        cls.preparer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.preparer)

    def test_random_credentials_are_private_stable_and_distinct_for_each_env(self):
        with tempfile.TemporaryDirectory(prefix="gld-dataset-wifi-test-") as directory:
            project = Path(directory).resolve()
            passwords = []
            for name in sorted(self.preparer.ENVIRONMENTS):
                build = project / ".pio/build" / name
                include = self.preparer.prepare(project, build, name)
                credential = project / ".pio/gld-dataset-wifi" / name / "credentials.local.json"
                self.assertTrue(credential.resolve().is_relative_to(project))
                data = json.loads(credential.read_text(encoding="utf-8"))
                self.assertEqual(data["username"], "gld")
                self.assertTrue(24 <= len(data["password"]) <= 63, "Invalid password length")
                passwords.append(data["password"])
                header = (include / "GldDatasetWifiSecrets.h").read_text(encoding="utf-8")
                self.assertTrue(json.dumps(data["password"]) in header, "Header credential mismatch")
                before = credential.read_bytes()
                self.preparer.prepare(project, build, name)
                self.assertTrue(before == credential.read_bytes(), "Rebuild silently rotated credentials")
            self.assertEqual(len(set(passwords)), 3, "Model environments shared a generated credential")

    def test_normal_environment_rejected_before_writing(self):
        with tempfile.TemporaryDirectory(prefix="gld-dataset-wifi-test-") as directory:
            project = Path(directory).resolve()
            with self.assertRaises(ValueError):
                self.preparer.prepare(project, project / "build", "gld_model_1")
            self.assertFalse((project / ".pio").exists())

    def test_malformed_existing_credentials_fail_closed_without_rotation(self):
        with tempfile.TemporaryDirectory(prefix="gld-dataset-wifi-test-") as directory:
            project = Path(directory).resolve()
            name = "gld_model_1_dataset_wifi"
            target = project / ".pio/gld-dataset-wifi" / name / "credentials.local.json"
            target.parent.mkdir(parents=True)
            target.write_text('{"username":"gld","password":"short"}', encoding="utf-8")
            before = target.read_bytes()
            with self.assertRaises(ValueError):
                self.preparer.prepare(project, project / "build", name)
            self.assertTrue(before == target.read_bytes(), "Malformed credential was overwritten")


if __name__ == "__main__":
    unittest.main()
