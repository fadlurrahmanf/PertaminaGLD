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

try:
    Import("env")
except NameError:  # Allows host-side provenance tests to import this module.
    env = None


FLASH_FILES = (
    ("bootloader.bin", 0x0000),
    ("partitions.bin", 0x8000),
    ("boot_app0.bin", 0xE000),
    ("firmware.bin", 0x10000),
)
PROFILE_BY_ENV = {
    "gld": "WROOM-1U-N16R8",
    "gld_model_1": "WROOM-1U-N16R8 / Model 1",
    "gld_model_2": "WROOM-1U-N16R8 / Model 2",
    "gld_model_3": "WROOM-1U-N16R8 / Model 3",
    "gld_v2": "GLD2 WROOM-1U-N16R8",
    "gldFieldtest": "WROOM-1U-N16R8 field-test",
    "gldFieldtestSensorlessAlarm": "WROOM-1U-N16R8 sensorless alarm field-test",
    "gldFieldtestSensorlessClear": "WROOM-1U-N16R8 sensorless clear field-test",
    "ch": "CH Circle (besar) ESP32-S3 R8N16 legacy alias",
    "chFieldtest": "CH Circle (besar) ESP32-S3 R8N16 field-test",
    "ch_large": "CH Circle (besar) ESP32-S3 R8N16",
    "ch_small": "CH Rectangle (kecil) ESP32-S3 R8N16",
    "gw": "Gateway Rectangle (kecil) ESP32-S3 R8N16 legacy alias",
    "gw_hello_ack_fieldtest": "Gateway Rectangle (kecil) ESP32-S3 R8N16 field-test",
    "gw_large": "Gateway Circle (besar) ESP32-S3 R8N16 / MQTT non-TLS",
    "gw_small": "Gateway Rectangle (kecil) ESP32-S3 R8N16 / MQTT non-TLS",
    "gw_large_tls": "Gateway Circle (besar) ESP32-S3 R8N16 / MQTT TLS",
    "gw_small_tls": "Gateway Rectangle (kecil) ESP32-S3 R8N16 / MQTT TLS",
}


def _device_kind(environment: str) -> str:
    if environment.startswith("ch"):
        return "ch"
    if environment.startswith("gw"):
        return "gw"
    return "gld"


def _board_shape(environment: str) -> str | None:
    if environment in {"ch", "chFieldtest", "ch_large", "gw_large", "gw_large_tls"}:
        return "circle"
    if environment in {"ch_small", "gw", "gw_hello_ack_fieldtest", "gw_small", "gw_small_tls"}:
        return "rectangle"
    return None


def _mqtt_transport(environment: str) -> str | None:
    if not environment.startswith("gw"):
        return None
    return "tls" if environment.endswith("_tls") else "non_tls"


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _version_constants(project_dir: pathlib.Path) -> dict[str, str]:
    text = (project_dir / "shared" / "include" / "FirmwareVersion.h").read_text(encoding="utf-8")
    result: dict[str, str] = {}
    for name in (
        "GLD_FIRMWARE_VERSION",
        "CH_FIRMWARE_VERSION",
        "GATEWAY_FIRMWARE_VERSION",
        "PROTOCOL_VERSION",
        "CONFIG_SCHEMA_VERSION",
    ):
        match = re.search(rf'{name}\s*=\s*"([^"]+)"', text)
        if not match:
            raise RuntimeError(f"Cannot read {name} from FirmwareVersion.h")
        result[name] = match.group(1)
    return result


def _firmware_version(environment: str, versions: dict[str, str]) -> str:
    kind = _device_kind(environment)
    if kind == "ch":
        return versions["CH_FIRMWARE_VERSION"]
    if kind == "gw":
        return versions["GATEWAY_FIRMWARE_VERSION"]
    return versions["GLD_FIRMWARE_VERSION"]


def _git_commit(repo_root: pathlib.Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _git_tree_state(repo_root: pathlib.Path, scoped_path: pathlib.Path) -> str:
    relative_scope = scoped_path.resolve().relative_to(repo_root.resolve()).as_posix()
    completed = subprocess.run(
        [
            "git", "status", "--porcelain", "--untracked-files=normal",
            "--", relative_scope,
        ],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        return "unknown"
    return "dirty" if completed.stdout.strip() else "clean"


def _firmware_tree_snapshot_sha256(project_dir: pathlib.Path) -> str:
    """Hash a deterministic firmware-workspace snapshot, not compile inputs.

    The snapshot includes every regular file under ``firmware/`` except
    PlatformIO build output and Python cache/bytecode.  It intentionally also
    covers tests, tools, notes, and other non-compile files, so the manifest
    field must not be interpreted as an exact compiler-input identity.
    """
    digest = hashlib.sha256()
    excluded_parts = {".pio", "__pycache__"}
    files = sorted(
        path for path in project_dir.rglob("*")
        if path.is_file()
        and not any(part in excluded_parts for part in path.relative_to(project_dir).parts)
        and path.suffix.lower() not in {".pyc", ".pyo"}
    )
    for path in files:
        relative = path.relative_to(project_dir).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


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
    if staging_dir.exists():
        shutil.rmtree(staging_dir)

    # Capture provenance after removing any stale staging directory, but
    # before creating this package's staging output.  Otherwise the hook makes
    # an otherwise clean repository appear dirty solely because it is running.
    versions = _version_constants(project_dir)
    git_commit = _git_commit(repo_root)
    git_tree_state = _git_tree_state(repo_root, project_dir)
    firmware_tree_snapshot = _firmware_tree_snapshot_sha256(project_dir)

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
        packaged_at = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        manifest = {
            "schemaVersion": 2,
            "packageType": "pertamina-gld-prebuilt-firmware",
            "deviceId": "ANY",
            "boardProfile": PROFILE_BY_ENV[environment],
            "environment": environment,
            "firmwareVersion": _firmware_version(environment, versions),
            "protocolVersion": versions["PROTOCOL_VERSION"],
            "configSchemaVersion": versions["CONFIG_SCHEMA_VERSION"],
            "chip": "esp32s3",
            "baud": 921600,
            "createdAtUtc": packaged_at,
            "source": {
                "gitCommit": git_commit,
                "gitTreeState": git_tree_state,
                "gitTreeStateScope": "firmware/",
                "firmwareTreeSnapshotSha256": firmware_tree_snapshot,
                "platformioCoreVersion": "PlatformIO post-build hook",
                "platformioIniSha256": _sha256(project_dir / "platformio.ini"),
                "buildCommand": f"pio run -e {environment}",
                "packagedAtUtc": packaged_at,
            },
            "flashSetSha256": _flash_set_sha256(flash_files),
            "flashFiles": flash_files,
        }
        board_shape = _board_shape(environment)
        if board_shape is not None:
            manifest["boardShape"] = board_shape
        mqtt_transport = _mqtt_transport(environment)
        if mqtt_transport is not None:
            manifest["mqttTransport"] = mqtt_transport
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


if env is not None:
    env.AddPostAction("$BUILD_DIR/${PROGNAME}.bin", write_operator_package)
