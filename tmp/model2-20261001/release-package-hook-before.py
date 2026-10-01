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
except NameError:
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
    "ch": "CH3 ESP32-S3 R8N16",
    "chFieldtest": "CH3 ESP32-S3 R8N16 field-test",
    "gw": "Gateway ESP32-S3 R8N16",
    "gw_hello_ack_fieldtest": "Gateway ESP32-S3 R8N16 field-test",
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
    isolated = project_dir / "gld" / "include" / "Gld1FirmwareVersion.h"
    if isolated.exists():
        match = re.search(r'GLD1_FIRMWARE_VERSION\s*=\s*"([^"]+)"', isolated.read_text(encoding="utf-8"))
        if not match:
            raise RuntimeError("Missing isolated GLD1 version")
        result["GLD1_FIRMWARE_VERSION"] = match.group(1)
    return result


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
    versions = _version_constants(project_dir)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    # Record source state before staging generated package files.
    tree_state = _git_tree_state(repo_root, project_dir)
    tree_snapshot = _firmware_tree_snapshot_sha256(project_dir)
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
            "firmwareVersion": (versions.get("GLD1_FIRMWARE_VERSION", versions["GLD_FIRMWARE_VERSION"])
                                if environment in {"gld", "gld_model_1", "gld_model_3"}
                                else versions["GLD_FIRMWARE_VERSION"]),
            "protocolVersion": versions["PROTOCOL_VERSION"],
            "configSchemaVersion": versions["CONFIG_SCHEMA_VERSION"],
            "chip": "esp32s3",
            "baud": 921600,
            "createdAtUtc": stamp,
            "source": {
                "gitCommit": _git_commit(repo_root),
                "gitTreeState": tree_state,
                "gitTreeStateScope": "firmware/",
                "firmwareTreeSnapshotSha256": tree_snapshot,
                "platformioCoreVersion": "PlatformIO post-build hook",
                "platformioIniSha256": _sha256(project_dir / "platformio.ini"),
                "buildCommand": f"pio run -e {environment}",
                "packagedAtUtc": stamp,
            },
            "flashSetSha256": _flash_set_sha256(flash_files),
            "flashFiles": flash_files,
        }
        manifest_path = staging_dir / "manifest.json"
        if environment in {"gld", "gld_model_1", "gld_model_3"}:
            model_slot = "model_3" if environment == "gld_model_3" else "model_1"
            model_dir = project_dir / "gld" / "models" / model_slot
            model_meta = json.loads((model_dir / "model.json").read_text(encoding="utf-8"))
            header = (model_dir / "cnn_gas_datasheet_model_data.h").read_text(encoding="utf-8")
            array = re.search(r"g_cnn_gas_datasheet_2class_model\[\]\s*=\s*\{(.*?)\};", header, re.S)
            if not array:
                raise RuntimeError(f"Missing {model_slot} two-class model array")
            blob = bytes(int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]{2})", array.group(1)))
            model_hash = hashlib.sha256(blob).hexdigest()
            if model_hash != model_meta["modelSha256"]:
                raise RuntimeError(f"{model_slot} model export hash mismatch")
            # Keep the strict schema-v2 upload manifest unchanged. This sidecar
            # is audit metadata, never a flash image or an upload API field.
            model_provenance = {
                "environment": environment,
                "firmwareSha256": next(item["sha256"] for item in flash_files if item["path"] == "firmware.bin"),
                "slot": model_slot,
                "profileId": model_meta["profileId"],
                "classes": model_meta["classes"],
                "sha256": model_hash,
                "size": len(blob),
                "sourceArchiveSha256": model_meta["sourceArchiveSha256"],
                "normalizeParamsSha256": _sha256(model_dir / "cnn_gas_datasheet_normalize_params.h"),
                "sensitivityTableSha256": _sha256(model_dir / "cnn_gas_sensitivity_table.h"),
            }
            (staging_dir / "model-provenance.json").write_text(
                json.dumps(model_provenance, indent=2) + "\n", encoding="utf-8"
            )
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
