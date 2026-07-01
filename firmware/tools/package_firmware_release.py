#!/usr/bin/env python3
"""Create a strict prebuilt firmware package for the GLD operator app.

This script packages existing PlatformIO build artifacts. It intentionally does
not compile firmware; run the appropriate PlatformIO build separately when a new
binary is needed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import shutil
import sys


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


def read_gld_version(project_dir: pathlib.Path) -> str:
    header = project_dir / "shared" / "include" / "FirmwareVersion.h"
    text = header.read_text(encoding="utf-8")
    match = re.search(r'GLD_FIRMWARE_VERSION\s*=\s*"([^"]+)"', text)
    if not match:
        raise ValueError(f"Could not find GLD_FIRMWARE_VERSION in {header}")
    return match.group(1)


def required_file(project_dir: pathlib.Path, build_dir: pathlib.Path, name: str) -> pathlib.Path:
    candidates = [build_dir / name]
    if name == "boot_app0.bin":
        candidates.extend(
            [
                project_dir.parent
                / ".platformio"
                / "packages"
                / "framework-arduinoespressif32"
                / "tools"
                / "partitions"
                / "boot_app0.bin",
                pathlib.Path.home()
                / ".platformio"
                / "packages"
                / "framework-arduinoespressif32"
                / "tools"
                / "partitions"
                / "boot_app0.bin",
            ]
        )
    for path in candidates:
        if path.exists():
            return path
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {name}. Checked: {', '.join(str(candidate) for candidate in candidates)}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", default="firmware", help="PlatformIO project directory")
    parser.add_argument("--env", required=True, help="PlatformIO environment name that was already built")
    parser.add_argument("--device-id", required=True, help="GLD device ID, for example F001")
    parser.add_argument("--board-profile", required=True, help="Board profile label, for example WROOM-1U-N16R8")
    parser.add_argument("--chip", default="esp32s3", help="Target chip family for the flasher")
    parser.add_argument("--baud", type=int, default=460800, help="Upload baud for direct flasher")
    parser.add_argument("--version", help="Firmware version override; defaults to GLD_FIRMWARE_VERSION")
    parser.add_argument("--output-dir", default="firmware/releases", help="Directory where the package folder is created")
    parser.add_argument("--package-name", help="Optional exact package folder name")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = pathlib.Path.cwd()
    project_dir = (root / args.project_dir).resolve()
    build_dir = project_dir / ".pio" / "build" / args.env
    version = args.version or read_gld_version(project_dir)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    package_name = args.package_name or f"{args.device_id}_{args.env}_v{version}_{stamp}"
    output_dir = (root / args.output_dir).resolve()
    package_dir = output_dir / package_name

    if package_dir.exists():
        raise FileExistsError(f"Package directory already exists: {package_dir}")
    package_dir.mkdir(parents=True)

    flash_files = []
    try:
        for file_name, offset in DEFAULT_FLASH_FILES:
            source = required_file(project_dir, build_dir, file_name)
            target = package_dir / file_name
            shutil.copy2(source, target)
            flash_files.append(
                {
                    "path": file_name,
                    "offset": f"0x{offset:04X}",
                    "size": target.stat().st_size,
                    "sha256": sha256(target),
                }
            )

        manifest = {
            "schemaVersion": 1,
            "packageType": "pertamina-gld-prebuilt-firmware",
            "deviceId": args.device_id,
            "boardProfile": args.board_profile,
            "environment": args.env,
            "firmwareVersion": version,
            "protocolVersion": "0.1.0",
            "chip": args.chip,
            "baud": args.baud,
            "createdAtUtc": stamp,
            "sourceBuildDir": str(build_dir),
            "flashFiles": flash_files,
        }
        manifest_path = package_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    except Exception:
        shutil.rmtree(package_dir, ignore_errors=True)
        raise

    print(f"Created firmware package: {package_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
