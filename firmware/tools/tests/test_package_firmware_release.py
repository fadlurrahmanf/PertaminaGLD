from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "package_firmware_release.py"
SPEC = importlib.util.spec_from_file_location("package_firmware_release", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
packager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packager)


class FirmwarePackageTests(unittest.TestCase):
    def test_flash_set_digest_binds_path_offset_size_and_hash(self) -> None:
        files = [
            {
                "path": "firmware.bin",
                "offset": "0x00010000",
                "size": 3,
                "sha256": "a" * 64,
            }
        ]
        original = packager.flash_set_sha256(files)
        self.assertRegex(original, r"^[0-9a-f]{64}$")
        files[0]["offset"] = "0x00020000"
        self.assertNotEqual(original, packager.flash_set_sha256(files))

    def test_safe_names_reject_path_traversal(self) -> None:
        for value in ("../release", "a/b", "a\\b", "..", ""):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    packager.validate_safe_name(value, "test")
        self.assertEqual(packager.validate_safe_name("gld_field-1", "test"), "gld_field-1")

    def test_version_reader_requires_all_semantic_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = pathlib.Path(temporary)
            header = project / "shared" / "include" / "FirmwareVersion.h"
            header.parent.mkdir(parents=True)
            header.write_text(
                '\n'.join(
                    [
                        'constexpr const char* GLD_FIRMWARE_VERSION = "1.2.3";',
                        'constexpr const char* PROTOCOL_VERSION = "2.0.0";',
                        'constexpr const char* CONFIG_SCHEMA_VERSION = "3.4.5";',
                    ]
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                packager.read_version_constants(project),
                {
                    "GLD_FIRMWARE_VERSION": "1.2.3",
                    "PROTOCOL_VERSION": "2.0.0",
                    "CONFIG_SCHEMA_VERSION": "3.4.5",
                },
            )

    def test_sha256_hashes_binary_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "firmware.bin"
            path.write_bytes(b"abc")
            self.assertEqual(
                packager.sha256(path),
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            )

    def test_git_identity_rejects_dirty_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "packager-test@example.invalid"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Firmware Packager Test"],
                cwd=root,
                check=True,
            )
            source = root / "source.txt"
            source.write_text("clean\n", encoding="utf-8")
            subprocess.run(["git", "add", "source.txt"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "baseline"], cwd=root, check=True)

            commit, state = packager.git_source_identity(root)
            self.assertRegex(commit, r"^[0-9a-f]{40}$")
            self.assertEqual(state, "clean")

            source.write_text("dirty\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "dirty source tree"):
                packager.git_source_identity(root)

    def test_clean_build_removes_stale_artifacts_before_build(self) -> None:
        executable = pathlib.Path("pio")
        project = pathlib.Path("firmware")
        with mock.patch.object(packager, "run_checked", side_effect=["", "SUCCESS"]) as run:
            output = packager.clean_build_environment(executable, project, "gld")
        self.assertEqual(output, "SUCCESS")
        self.assertEqual(
            run.call_args_list,
            [
                mock.call(["pio", "run", "-e", "gld", "-t", "clean"], project),
                mock.call(["pio", "run", "-e", "gld"], project),
            ],
        )

    def test_post_build_identity_check_detects_source_change(self) -> None:
        with mock.patch.object(
            packager,
            "git_source_identity",
            return_value=("b" * 40, "clean"),
        ):
            with self.assertRaisesRegex(RuntimeError, "changed during"):
                packager.verify_source_identity_unchanged(
                    pathlib.Path("."), "a" * 40, "clean"
                )

    def test_post_build_identity_check_accepts_same_clean_revision(self) -> None:
        with mock.patch.object(
            packager,
            "git_source_identity",
            return_value=("a" * 40, "clean"),
        ):
            packager.verify_source_identity_unchanged(
                pathlib.Path("."), "a" * 40, "clean"
            )


if __name__ == "__main__":
    unittest.main()
