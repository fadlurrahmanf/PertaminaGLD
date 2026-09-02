from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_PATH = REPO_ROOT / "firmware" / "tools" / "operator_package_post.py"


def load_hook():
    spec = importlib.util.spec_from_file_location("operator_package_post_test", HOOK_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HOOK = load_hook()


class FakePlatformIoEnv(dict):
    def __init__(self, project_dir: Path, build_dir: Path) -> None:
        super().__init__(PIOENV="gld_v2", PROJECT_DIR=str(project_dir))
        self._build_dir = build_dir

    def subst(self, expression: str) -> str:
        if expression != "$BUILD_DIR":
            raise AssertionError(f"unexpected substitution: {expression}")
        return str(self._build_dir)


class OperatorPackageProvenanceTests(unittest.TestCase):
    def test_package_output_does_not_dirty_scoped_firmware_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            project_dir = repo / "firmware"
            shared_include = project_dir / "shared" / "include"
            shared_include.mkdir(parents=True)
            (project_dir / ".gitignore").write_text(".pio\n", encoding="utf-8")
            (project_dir / "platformio.ini").write_text("[platformio]\n", encoding="utf-8")
            (shared_include / "FirmwareVersion.h").write_text(
                "\n".join(
                    (
                        'constexpr const char *GLD_FIRMWARE_VERSION = "0.0.1";',
                        'constexpr const char *CH_FIRMWARE_VERSION = "0.0.2";',
                        'constexpr const char *GATEWAY_FIRMWARE_VERSION = "0.0.3";',
                        'constexpr const char *PROTOCOL_VERSION = "0.0.4";',
                        'constexpr const char *CONFIG_SCHEMA_VERSION = "0.0.5";',
                        "",
                    )
                ),
                encoding="utf-8",
            )

            self._git(repo, "init")
            self._git(repo, "config", "user.email", "provenance-test@example.invalid")
            self._git(repo, "config", "user.name", "Provenance Test")
            self._git(repo, "add", "firmware")
            self._git(repo, "commit", "-m", "fixture")

            build_dir = project_dir / ".pio" / "build" / "gld_v2"
            build_dir.mkdir(parents=True)
            for index, (name, _) in enumerate(HOOK.FLASH_FILES, start=1):
                (build_dir / name).write_bytes(bytes((index,)) * 32)
            fake_env = FakePlatformIoEnv(project_dir, build_dir)

            expected_snapshot = HOOK._firmware_tree_snapshot_sha256(project_dir)
            HOOK.write_operator_package(None, None, fake_env)
            manifest_path = (
                repo / "apps" / "operator-hub" / "firmware-packages"
                / "gld_v2" / "latest" / "manifest.json"
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            source = manifest["source"]
            self.assertEqual(source["gitTreeState"], "clean")
            self.assertEqual(source["gitTreeStateScope"], "firmware/")
            self.assertEqual(source["firmwareTreeSnapshotSha256"], expected_snapshot)
            self.assertRegex(source["packagedAtUtc"], r"^\d{8}T\d{6}Z$")
            self.assertNotIn("buildStartedAtUtc", source)
            self.assertNotIn("buildCompletedAtUtc", source)

            # A prior generated package is outside the declared Git scope and
            # therefore cannot taint provenance for a subsequent build.
            HOOK.write_operator_package(None, None, fake_env)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["source"]["gitTreeState"], "clean")

            (project_dir / "new-source.txt").write_text("uncommitted\n", encoding="utf-8")
            dirty_snapshot = HOOK._firmware_tree_snapshot_sha256(project_dir)
            HOOK.write_operator_package(None, None, fake_env)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["source"]["gitTreeState"], "dirty")
            self.assertEqual(
                manifest["source"]["firmwareTreeSnapshotSha256"], dirty_snapshot
            )

    @staticmethod
    def _git(repo: Path, *args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=repo,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
