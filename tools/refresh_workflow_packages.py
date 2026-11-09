"""Replace the three validated GLD Workflow packages after parallel builds.

Builds are supplied explicitly; this tool never compiles, flashes or opens COM.
Old Hub packages are retained under ignored output for rollback evidence.
"""
from __future__ import annotations

import argparse
import base64
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
FW = ROOT / "firmware"
HUB = ROOT / "apps/operator-hub/firmware-packages"
sys.path[:0] = [str(FW / "tools"), str(ROOT / "apps/gld-operator"), str(ROOT / "apps/operator-hub")]
import package_dataset_workflow as workflow
import export_workflow_connection_profiles as profiles


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_package(model, build, stage, modules, snapshot, core):
    post, uploader, preflight, hub = modules
    env = f"gld_model_{model}_dataset_workflow_wifi"
    old = HUB / env / "latest"
    require(old.is_dir() and not old.is_symlink(), "OLD_FINAL_PACKAGE_MISSING")
    old_manifest = json.loads((old / "manifest.json").read_text(encoding="utf-8"))
    preflight._verify_manifest(old / "manifest.json", env)
    require(old_manifest.get("environment") == env and old_manifest.get("schemaVersion") == 2,
            "OLD_FINAL_PACKAGE_INVALID")
    require(build.is_dir() and not build.is_symlink(), "BUILD_DIRECTORY_MISSING")
    stage.mkdir(parents=True)
    flash = []
    for name, offset in workflow.FILES:
        source = build / name
        if name == "boot_app0.bin" and not source.is_file():
            source = Path.home() / ".platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin"
        require(source.is_file() and not source.is_symlink() and source.stat().st_size > 0,
                "BUILD_IMAGE_MISSING")
        if name != "firmware.bin":
            require(sha(source) == sha(old / name), "BOOT_OR_PARTITION_LAYOUT_CHANGED")
        shutil.copy2(source, stage / name)
        flash.append(dict(path=name, offset=f"0x{offset:08X}", size=(stage / name).stat().st_size,
                          sha256=sha(stage / name)))
    binary = (stage / "firmware.bin").read_bytes()
    require(b"GLD_PG24_COLD_BOOT_CONFIRM" in binary and b"gld-dataset-wifi/3" in binary,
            "WORKFLOW_RECOVERY_IMAGE_MARKERS_MISSING")
    provenance = workflow.model_provenance(model, env, binary)
    versions = post._version_constants(FW)
    require(versions["GLD1_FIRMWARE_VERSION"] == old_manifest["firmwareVersion"] and
            versions["GLD1_FIRMWARE_VERSION"].encode() in binary, "FIRMWARE_VERSION_CHANGED")
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest = copy.deepcopy(old_manifest)
    manifest.update(createdAtUtc=timestamp, flashFiles=flash, flashSetSha256=post._flash_set_sha256(flash))
    # The isolated build directories started empty; this is a packaged build
    # output with an explicit firmware tree snapshot, not a Git-clean claim.
    manifest["source"].update(gitCommit=post._git_commit(ROOT), gitTreeState="build-output",
                              gitTreeStateScope="firmware/", firmwareTreeSnapshotSha256=snapshot,
                              platformioCoreVersion=core, platformioIniSha256=sha(FW / "platformio.ini"),
                              buildCommand=f"pio run -e {env}", packagedAtUtc=timestamp)
    (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (stage / "manifest.sha256").write_text(f"{sha(stage / 'manifest.json')}  manifest.json\n", encoding="ascii")
    (stage / "model-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    encoded = {name: base64.b64encode((stage / name).read_bytes()).decode("ascii") for name, _ in workflow.FILES}
    checked, verified = uploader.validate_firmware_package(manifest, encoded, env, "1002")
    require(len(verified) == 4 and not uploader.requires_gld1_nvs_reset_before_boot(checked),
            "FIRMWARE_CHILD_VALIDATION_FAILED")
    nvs_offset, nvs_size = uploader.verified_nvs_region(verified)
    require((nvs_offset, nvs_size) == (0x9000, 0x5000), "NVS_REGION_CHANGED")
    for item, data in verified:
        start = int(item["offset"], 0)
        end = (start + len(data) + 4095) & ~4095
        require(start % 4096 == 0 and (end <= nvs_offset or start >= nvs_offset + nvs_size),
                "FIRMWARE_ERASE_OVERLAPS_NVS")
    preflight._verify_manifest(stage / "manifest.json", env)
    hub.validate_selected_package(dict(manifest=manifest, packageFiles=encoded), env)
    workflow.private_verification(env, build, binary, list(stage.glob("*.json")) + list(stage.glob("*.sha256")))
    return dict(model=model, environment=env, oldFirmwareSha256=sha(old / "firmware.bin"),
                newFirmwareSha256=sha(stage / "firmware.bin"), manifestSha256=sha(stage / "manifest.json"))


def refresh(builds):
    require(set(builds) == {1, 2, 3}, "THREE_MODEL_BUILDS_REQUIRED")
    modules = (workflow.load(FW / "tools/operator_package_post.py", "refresh_post"),
               workflow.load(ROOT / "apps/gld-operator/bridge.py", "refresh_child"),
               workflow.load(ROOT / "apps/operator-hub/preflight.py", "refresh_preflight"),
               workflow.load(ROOT / "apps/operator-hub/bridge.py", "refresh_hub"))
    core = subprocess.run([str(Path.home() / ".platformio/penv/Scripts/python.exe"), "-c",
                           "import importlib.metadata; print(importlib.metadata.version('platformio'))"],
                          check=True, capture_output=True, text=True).stdout.strip()
    snapshot = modules[0]._firmware_tree_snapshot_sha256(FW)
    archive = ROOT / "output/handover-verification" / ("workflow-refresh-" + uuid.uuid4().hex[:12])
    stage = archive / "stage"; backup = archive / "backup"
    stage.mkdir(parents=True); backup.mkdir()
    old_profile = (ROOT / profiles.OUTPUT).read_bytes()
    results = [build_package(model, builds[model], stage / str(model), modules, snapshot, core)
               for model in (1, 2, 3)]
    require(snapshot == modules[0]._firmware_tree_snapshot_sha256(FW), "FIRMWARE_SOURCE_CHANGED_DURING_PACKAGING")
    installed = []
    try:
        for model in (1, 2, 3):
            destination = HUB / f"gld_model_{model}_dataset_workflow_wifi/latest"
            destination.rename(backup / str(model))
            try:
                (stage / str(model)).rename(destination)
            except Exception:
                (backup / str(model)).rename(destination)
                raise
            installed.append(model)
        profiles.export_profiles(ROOT)
        for model in (1, 2, 3):
            env = f"gld_model_{model}_dataset_workflow_wifi"
            modules[2]._verify_manifest(HUB / env / "latest/manifest.json", env)
        profiles.check(ROOT)
    except Exception:
        profile_path = ROOT / profiles.OUTPUT
        restore = archive / "prior-profiles.json"
        restore.write_bytes(old_profile); restore.replace(profile_path)
        for model in reversed(installed):
            destination = HUB / f"gld_model_{model}_dataset_workflow_wifi/latest"
            destination.rename(stage / str(model))
            (backup / str(model)).rename(destination)
        raise
    receipt = dict(status="PASS", sourceSnapshotSha256=snapshot, packages=results,
                   oldPackagesRetained=str(backup), hardwareAction=False)
    (archive / "release-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for model in (1, 2, 3):
        parser.add_argument(f"--model-{model}-build", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = refresh({model: getattr(args, f"model_{model}_build").resolve() for model in (1, 2, 3)})
        print(json.dumps(result))
        return 0
    except Exception as error:
        print(json.dumps(dict(status="BLOCKED", code=str(error) if isinstance(error, RuntimeError) else
                              "WORKFLOW_PACKAGE_REFRESH_FAILED")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
