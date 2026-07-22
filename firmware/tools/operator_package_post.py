"""PlatformIO post-build hook: refresh the Operator Hub's offline package.

This deliberately packages the bytes from the build that just succeeded; it
does not run a second clean build.  The package is marked ``deviceId: ANY`` so
the same environment package can be flashed to a selected COM port and then
provisioned with the device identity in the operator console.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import re
import shutil
import subprocess

Import("env")


FLASH_FILES = (
    ("bootloader.bin", 0x0000),
    ("partitions.bin", 0x8000),
    ("boot_app0.bin", 0xE000),
    ("firmware.bin", 0x10000),
)
PROFILE_BY_ENV = {
    "gld": "WROOM-1U-N16R8",
    "gldFieldtest": "WROOM-1U-N16R8 field-test",
    "ch": "CH3 ESP32-S3 R8N16",
    "chFieldtest": "CH3 ESP32-S3 R8N16 field-test",
    "gw": "Gateway ESP32-S3 R8N16",
}


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _version_constants(project_dir: pathlib.Path) -> dict[str, str]:
    text = (project_dir / "shared" / "include" / "FirmwareVersion.h").read_text(encoding="utf-8")
    result: dict[str, str] = {}
    for name in ("GLD_FIRMWARE_VERSION", "PROTOCOL_VERSION", "CONFIG_SCHEMA_VERSION"):
        match = re.search(rf'{name}\s*=\s*"([^"]+)"', text)
        if not match:
            raise RuntimeError(f"Cannot read {name} from FirmwareVersion.h")
        result[name] = match.group(1)
    return result


def _git_commit(repo_root: pathlib.Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _required_file(project_dir: pathlib.Path, build_dir: pathlib.Path, name: str) -> pathlib.Path:
    candidates = [build_dir / name]
    if name == "boot_app0.bin":
        candidates.append(
            pathlib.Path.home() / ".platformio" / "packages" / "framework-arduinoespressif32"
            / "tools" / "partitions" / "boot_app0.bin"
        )
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    raise RuntimeError(f"Missing build artifact: {name}")


def _flash_set_sha256(files: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for item in files:
        digest.update(
            f"{item['path']}\0{item['offset']}\0{item['size']}\0{item['sha256']}\n".encode("ascii")
        )
    return digest.hexdigest()


def write_operator_package(source, target, env):
    environment = str(env["PIOENV"])
    if environment not in PROFILE_BY_ENV:
        return
    project_dir = pathlib.Path(str(env["PROJECT_DIR"])).resolve()
    repo_root = project_dir.parent
    build_dir = pathlib.Path(str(env.subst("$BUILD_DIR"))).resolve()
    output_root = repo_root / "apps" / "operator-hub" / "firmware-packages" / environment
    final_dir = output_root / "latest"
    staging_dir = output_root / ".latest-staging"
    versions = _version_constants(project_dir)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)
    try:
        flash_files: list[dict[str, object]] = []
        for name, offset in FLASH_FILES:
            destination = staging_dir / name
            shutil.copy2(_required_file(project_dir, build_dir, name), destination)
            flash_files.append({
                "path": name,
                "offset": f"0x{offset:08X}",
                "size": destination.stat().st_size,
                "sha256": _sha256(destination),
            })
        manifest = {
            "schemaVersion": 2,
            "packageType": "pertamina-gld-prebuilt-firmware",
            "deviceId": "ANY",
            "boardProfile": PROFILE_BY_ENV[environment],
            "environment": environment,
            "firmwareVersion": versions["GLD_FIRMWARE_VERSION"],
            "protocolVersion": versions["PROTOCOL_VERSION"],
            "configSchemaVersion": versions["CONFIG_SCHEMA_VERSION"],
            "chip": "esp32s3",
            "baud": 460800,
            "createdAtUtc": stamp,
            "source": {
                "gitCommit": _git_commit(repo_root),
                "gitTreeState": "operator-hub-auto",
                "platformioCoreVersion": "PlatformIO post-build hook",
                "platformioIniSha256": _sha256(project_dir / "platformio.ini"),
                "buildCommand": f"pio run -e {environment}",
                "buildStartedAtUtc": stamp,
                "buildCompletedAtUtc": stamp,
            },
            "flashSetSha256": _flash_set_sha256(flash_files),
            "flashFiles": flash_files,
        }
        manifest_path = staging_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        (staging_dir / "manifest.sha256").write_text(
            f"{_sha256(manifest_path)}  manifest.json\n", encoding="ascii"
        )
        if final_dir.exists():
            shutil.rmtree(final_dir)
        staging_dir.replace(final_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    print(f"Operator Hub package refreshed: {final_dir}")


env.AddPostAction("$BUILD_DIR/${PROGNAME}.bin", write_operator_package)
