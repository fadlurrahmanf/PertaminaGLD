"""Cross-language runtime-path contract; no launcher imports or execution."""
from __future__ import annotations

import ast
from pathlib import Path, PureWindowsPath
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
HUB = ROOT / "apps/operator-hub/bridge.py"
LAUNCHER = ROOT / "tools/start-pertamina-gld-system.ps1"


def hub_runtime_paths(repo):
    """Evaluate only the three static Path assignments, not bridge startup."""
    values = {"HUB_DIR": repo / "apps/operator-hub", "APPS_DIR": repo / "apps"}

    def evaluate(node):
        if isinstance(node, ast.Name):
            return values[node.id]
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Attribute) and node.attr == "parent":
            return evaluate(node.value).parent
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return evaluate(node.left) / evaluate(node.right)
        raise AssertionError("Runtime root must remain a static repository-relative Path")

    for statement in ast.parse(HUB.read_text(encoding="utf-8")).body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            if isinstance(target, ast.Name) and target.id in {
                "ARCHIVE_APPS_DIR", "RUNTIME_DIR", "BROKER_CREDENTIALS_PATH"
            }:
                values[target.id] = evaluate(statement.value)
    return values


def launcher_runtime_paths(repo):
    """Evaluate the launcher's static Join-Path declarations without PowerShell."""
    values = {"RepoRoot": repo}
    parents = {}
    expected = {"RuntimeDir", "LogDir", "CredentialsPath", "StartupStatePath", "StartupProfilePath"}
    assignments = re.findall(
        r'^\$(\w+)\s*=\s*Join-Path\s+\$(\w+)\s+"([^"]+)"\s*$',
        LAUNCHER.read_text(encoding="utf-8"), re.MULTILINE,
    )
    for target, parent, relative in assignments:
        if target in expected:
            if target in parents:
                raise AssertionError("Runtime paths must be declared once")
            values[target] = values[parent] / relative
            parents[target] = parent
    return values, parents


class FullHandoverRuntimePaths(unittest.TestCase):
    def test_launcher_reads_same_broker_config_as_hub_under_different_checkout_roots(self):
        for location in (r"C:\checkout\PertaminaGLD", r"E:\Other workspace\GLD handover"):
            with self.subTest(root=location):
                repo = PureWindowsPath(location)
                hub = hub_runtime_paths(repo)
                launcher, _ = launcher_runtime_paths(repo)
                self.assertEqual(launcher["RuntimeDir"], hub["RUNTIME_DIR"])
                self.assertEqual(launcher["CredentialsPath"], hub["BROKER_CREDENTIALS_PATH"])
                self.assertTrue(launcher["RuntimeDir"].is_relative_to(repo))

    def test_all_private_runtime_children_derive_from_one_runtime_root(self):
        repo = PureWindowsPath(r"D:\handover")
        paths, parents = launcher_runtime_paths(repo)
        self.assertEqual(parents["RuntimeDir"], "RepoRoot")
        for name, relative in {
            "CredentialsPath": "credentials.local.json",
            "StartupProfilePath": "startup.local.json",
            "StartupStatePath": "startup-flow-state.json",
            "LogDir": "logs",
        }.items():
            with self.subTest(name=name):
                self.assertEqual(parents[name], "RuntimeDir")
                self.assertEqual(paths[name], paths["RuntimeDir"] / relative)

    def test_launcher_does_not_embed_broker_credential_arguments(self):
        source = LAUNCHER.read_text(encoding="utf-8")
        literal = re.compile(r'''--mqtt-broker-(?:password|user)\s+(?!["']?\$)[^\s]+''')
        # Avoid assertion helpers that could print the entire source on failure.
        self.assertFalse(literal.search(source), "Read broker credentials from runtime configuration, never inline literals")


if __name__ == "__main__":
    unittest.main()
