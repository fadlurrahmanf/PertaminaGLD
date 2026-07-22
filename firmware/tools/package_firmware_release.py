#!/usr/bin/env python3
"""Build and create a reproducible firmware package for the GLD operator app.

The packager accepts only a clean Git checkout, performs a clean PlatformIO
build itself, then records enough source/toolchain identity for the operator
bridge to validate and flash those exact bytes directly. Performing the build
inside this command prevents stale ignored ``.pio`` artifacts from being
mislabelled with the current Git revision.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from typing import Iterable


MANIFEST_SCHEMA_VERSION = 2
PACKAGE_TYPE = "pertamina-gld-prebuilt-firmware"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
DEVICE_ID_RE = re.compile(r"^[0-9A-F]{4}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")

DEFAULT_FLASH_FILES = (
    ("bootloader.bin", 0x0000),
    ("partitions.bin", 0x8000),
    ("boot_app0.bin", 0xE000),
    ("firmware.bin", 0x10000),
)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_version_constants(project_dir: pathlib.Path) -> dict[str, str]:
    header = project_dir / "shared" / "include" / "FirmwareVersion.h"
    text = header.read_text(encoding="utf-8")
    names = (
        "GLD_FIRMWARE_VERSION",
        "PROTOCOL_VERSION",
        "CONFIG_SCHEMA_VERSION",
    )
    versions: dict[str, str] = {}
    for name in names:
        match = re.search(rf'{name}\s*=\s*"([^"]+)"', text)
        if not match:
            raise ValueError(f"Could not find {name} in {header}")
        value = match.group(1)
        if not SEMVER_RE.fullmatch(value):
            raise ValueError(f"Invalid {name} value {value!r} in {header}")
        versions[name] = value
    return versions


def run_checked(command: list[str], cwd: pathlib.Path) -> str:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"Command failed ({' '.join(command)}): {detail}")
    return completed.stdout.strip()


def git_source_identity(root: pathlib.Path) -> tuple[str, str]:
    repository_root = pathlib.Path(
        run_checked(["git", "rev-parse", "--show-toplevel"], root)
    ).resolve()
    try:
        root.resolve().relative_to(repository_root)
    except ValueError as exc:
        raise RuntimeError(f"{root} is not inside Git repository {repository_root}") from exc

    commit = run_checked(["git", "rev-parse", "HEAD"], repository_root)
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError(f"Unexpected Git revision: {commit!r}")

    status = run_checked(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        repository_root,
    )
    if status:
        changed = "\n".join(status.splitlines()[:20])
        raise RuntimeError(
            "Refusing to package a dirty source tree. Commit or intentionally "
            f"stash all changes first:\n{changed}"
        )
    return commit, "clean"


def verify_source_identity_unchanged(
    root: pathlib.Path, expected_commit: str, expected_state: str
) -> None:
    """Fail if source identity changes while PlatformIO is building.

    The initial clean-tree check prevents stale inputs. Repeating it after the
    build closes the edit/commit-during-build window before any artifact is
    copied into a release package.
    """

    actual_commit, actual_state = git_source_identity(root)
    if (actual_commit, actual_state) != (expected_commit, expected_state):
        raise RuntimeError(
            "Source identity changed during the firmware build; discard these "
            "artifacts and run the packager again"
        )


def find_platformio_executable(explicit: str | None = None) -> pathlib.Path:
    candidates: list[pathlib.Path] = []
    if explicit:
        candidates.append(pathlib.Path(explicit))
    configured = os.environ.get("PLATFORMIO_EXE")
    if configured:
        candidates.append(pathlib.Path(configured))
    discovered = shutil.which("pio") or shutil.which("pio.exe")
    if discovered:
        candidates.append(pathlib.Path(discovered))
    candidates.extend(
        [
            pathlib.Path.home() / ".platformio" / "penv" / "Scripts" / "pio.exe",
            pathlib.Path.home() / ".platformio" / "penv" / "bin" / "pio",
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "PlatformIO executable not found. Pass --platformio-exe or set PLATFORMIO_EXE."
    )


def platformio_core_version(executable: pathlib.Path, project_dir: pathlib.Path) -> str:
    output = run_checked([str(executable), "--version"], project_dir)
    match = re.search(r"(?:version\s+)?(\d+\.\d+\.\d+)", output, re.IGNORECASE)
    if not match:
        raise RuntimeError(f"Could not parse PlatformIO version from {output!r}")
    return match.group(1)


def clean_build_environment(
    executable: pathlib.Path, project_dir: pathlib.Path, environment: str
) -> str:
    run_checked(
        [str(executable), "run", "-e", environment, "-t", "clean"],
        project_dir,
    )
    return run_checked([str(executable), "run", "-e", environment], project_dir)


def platformio_core_dir() -> pathlib.Path:
    configured = os.environ.get("PLATFORMIO_CORE_DIR")
    return pathlib.Path(configured).resolve() if configured else pathlib.Path.home() / ".platformio"


def required_file(project_dir: pathlib.Path, build_dir: pathlib.Path, name: str) -> pathlib.Path:
    candidates = [build_dir / name]
    if name == "boot_app0.bin":
        candidates.append(
            platformio_core_dir()
            / "packages"
            / "framework-arduinoespressif32"
            / "tools"
            / "partitions"
            / "boot_app0.bin"
        )
    for path in candidates:
        if path.is_file() and path.stat().st_size > 0:
            return path.resolve()
    raise FileNotFoundError(
        f"Missing or empty {name}. Checked: "
        + ", ".join(str(candidate) for candidate in candidates)
    )


def validate_safe_name(value: str, label: str) -> str:
    if not SAFE_NAME_RE.fullmatch(value) or value in {".", ".."}:
        raise ValueError(f"Invalid {label}: {value!r}")
    return value


def flash_set_sha256(files: Iterable[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for item in files:
        path = str(item["path"])
        offset = str(item["offset"])
        size = int(item["size"])
        file_hash = str(item["sha256"])
        if not SHA256_RE.fullmatch(file_hash):
            raise ValueError(f"Invalid flash-file SHA-256 for {path!r}")
        digest.update(f"{path}\0{offset}\0{size}\0{file_hash}\n".encode("ascii"))
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", default="firmware", help="PlatformIO project directory")
    parser.add_argument("--env", required=True, help="PlatformIO environment already built")
    parser.add_argument("--device-id", required=True, help="Four-hex-digit GLD ID, e.g. F011")
    parser.add_argument("--board-profile", required=True, help="Exact board profile label")
    parser.add_argument("--chip", default="esp32s3", help="Target chip family")
    parser.add_argument("--baud", type=int, default=460800, help="Direct flasher baud")
    parser.add_argument("--version", help="Firmware version override")
    parser.add_argument("--platformio-exe", help="Explicit PlatformIO executable")
    parser.add_argument("--output-dir", default="firmware/releases", help="Package output directory")
    parser.add_argument("--package-name", help="Exact package folder name")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    invocation_root = pathlib.Path.cwd().resolve()
    project_dir = (invocation_root / args.project_dir).resolve()
    if not project_dir.is_dir():
        raise FileNotFoundError(f"PlatformIO project directory not found: {project_dir}")

    environment = validate_safe_name(args.env, "environment")
    device_id = args.device_id.strip().upper()
    if not DEVICE_ID_RE.fullmatch(device_id):
        raise ValueError(f"Invalid device ID {args.device_id!r}; expected four hexadecimal digits")
    board_profile = args.board_profile.strip()
    if not board_profile or len(board_profile) > 128 or any(ord(char) < 32 for char in board_profile):
        raise ValueError("Invalid board profile")
    chip = validate_safe_name(args.chip.strip().lower(), "chip")
    if args.baud < 9600 or args.baud > 2_000_000:
        raise ValueError("baud must be between 9600 and 2000000")

    versions = read_version_constants(project_dir)
    version = args.version or versions["GLD_FIRMWARE_VERSION"]
    if not SEMVER_RE.fullmatch(version):
        raise ValueError(f"Invalid firmware version: {version!r}")

    git_commit, git_tree_state = git_source_identity(invocation_root)
    pio_executable = find_platformio_executable(args.platformio_exe)
    pio_version = platformio_core_version(pio_executable, project_dir)
    platformio_ini = project_dir / "platformio.ini"
    if not platformio_ini.is_file():
        raise FileNotFoundError(f"Missing PlatformIO configuration: {platformio_ini}")

    build_started_at = dt.datetime.now(dt.timezone.utc)
    clean_build_environment(pio_executable, project_dir, environment)
    build_completed_at = dt.datetime.now(dt.timezone.utc)
    verify_source_identity_unchanged(invocation_root, git_commit, git_tree_state)
    build_dir = project_dir / ".pio" / "build" / environment
    if not build_dir.is_dir():
        raise RuntimeError(f"PlatformIO reported success but did not create {build_dir}")

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    default_name = f"{device_id}_{environment}_v{version}_{stamp}"
    package_name = validate_safe_name(args.package_name or default_name, "package name")
    output_dir = (invocation_root / args.output_dir).resolve()
    package_dir = (output_dir / package_name).resolve()
    try:
        package_dir.relative_to(output_dir)
    except ValueError as exc:
        raise ValueError("Package directory escapes output directory") from exc
    if package_dir.exists():
        raise FileExistsError(f"Package directory already exists: {package_dir}")
    package_dir.mkdir(parents=True)

    flash_files: list[dict[str, object]] = []
    try:
        seen_offsets: set[int] = set()
        for file_name, offset in DEFAULT_FLASH_FILES:
            if offset in seen_offsets:
                raise RuntimeError(f"Duplicate flash offset: 0x{offset:X}")
            seen_offsets.add(offset)
            source = required_file(project_dir, build_dir, file_name)
            target = package_dir / file_name
            shutil.copy2(source, target)
            flash_files.append(
                {
                    "path": file_name,
                    "offset": f"0x{offset:08X}",
                    "size": target.stat().st_size,
                    "sha256": sha256(target),
                }
            )

        manifest = {
            "schemaVersion": MANIFEST_SCHEMA_VERSION,
            "packageType": PACKAGE_TYPE,
            "deviceId": device_id,
            "boardProfile": board_profile,
            "environment": environment,
            "firmwareVersion": version,
            "protocolVersion": versions["PROTOCOL_VERSION"],
            "configSchemaVersion": versions["CONFIG_SCHEMA_VERSION"],
            "chip": chip,
            "baud": args.baud,
            "createdAtUtc": stamp,
            "source": {
                "gitCommit": git_commit,
                "gitTreeState": git_tree_state,
                "platformioCoreVersion": pio_version,
                "platformioIniSha256": sha256(platformio_ini),
                "buildCommand": f"pio run -e {environment} -t clean && pio run -e {environment}",
                "buildStartedAtUtc": build_started_at.strftime("%Y%m%dT%H%M%SZ"),
                "buildCompletedAtUtc": build_completed_at.strftime("%Y%m%dT%H%M%SZ"),
            },
            "flashSetSha256": flash_set_sha256(flash_files),
            "flashFiles": flash_files,
        }
        manifest_path = package_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        (package_dir / "manifest.sha256").write_text(
            f"{sha256(manifest_path)}  manifest.json\n", encoding="ascii"
        )
    except Exception:
        shutil.rmtree(package_dir, ignore_errors=True)
        raise

    print(f"Created verified firmware package: {package_dir}")
    print(f"Source revision: {git_commit}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
