"""Validate and package already-built GLD1 workflow images; never build or flash.

Run with the Operator bundled Python. Only protocol3 workflow directories can
be written. Existing packages are protected, and Hub installation is explicit.
Private credential values are checked in memory and never serialized/logged.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
FW = ROOT / "firmware"
ARTIFACT_ROOT = FW / ".pio/artifacts/gld-dataset-workflow-wifi-20261102"
RECEIPT_ROOT = ROOT / "tmp/wireless-workflow-release"
HUB_ROOT = ROOT / "apps/operator-hub/firmware-packages"
FILES = (("bootloader.bin", 0), ("partitions.bin", 0x8000),
         ("boot_app0.bin", 0xE000), ("firmware.bin", 0x10000))
PACKAGE_FILES = tuple(name for name, _ in FILES) + ("manifest.json", "manifest.sha256", "model-provenance.json")
RECEIPTS = {1: "model1-build-receipt.json", 2: "model2-build-receipt-attempt2.json", 3: "model3-build-receipt.json"}


class PackageError(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise PackageError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sources(receipt, when):
    for prefix in ("sourceSha256", "sourceHashes", "publicSourceSha256"):
        value = receipt.get(prefix + when)
        if value:
            return value
    raise PackageError("Receipt public source identity is missing")


def protected_snapshot():
    """Public package/artifact hashes only; never inspect private NVS backups."""
    result = {}
    for path in HUB_ROOT.rglob("*"):
        if path.is_file() and not re.fullmatch(r"gld_model_[123]_dataset_workflow_wifi", path.relative_to(HUB_ROOT).parts[0]):
            result[path.relative_to(ROOT).as_posix()] = sha(path)
    for name in ("gld-dataset-wifi-20261102", "gld-dataset-replay-wifi-20261102",
                 "gld-dataset-replay-wifi-20261102-operator-password"):
        for path in (FW / ".pio/artifacts" / name).rglob("*"):
            if path.is_file():
                result[path.relative_to(ROOT).as_posix()] = sha(path)
    return result


def verify_receipt(model):
    env = f"gld_model_{model}_dataset_workflow_wifi"
    path = RECEIPT_ROOT / RECEIPTS[model]
    receipt = read(path)
    require(receipt.get("environment") == env and receipt.get("status") == "success", "Wrong or unsuccessful build receipt")
    require(receipt.get("exitCode", receipt.get("exit")) == 0, "Build did not exit successfully")
    require(receipt.get("hardwareAction") in (None, False), "Unexpected hardware action in build receipt")
    before, after = sources(receipt, "Before"), sources(receipt, "After")
    require(before == after and bool(before), "Source changed during build")
    require(all((ROOT / name).is_file() and sha(ROOT / name) == checksum for name, checksum in before.items()),
            "Current public build source differs from receipt")
    build = Path(receipt["buildDirectory"])
    artifact = ARTIFACT_ROOT / env
    require(Path(receipt["artifactDirectory"]).resolve() == artifact.resolve(), "Receipt artifact directory differs")
    described = receipt.get("files", receipt.get("artifacts", []))
    entries = {item.get("name", Path(item["path"]).name): item for item in described}
    require(set(entries) == {name for name, _ in FILES}, "Receipt must describe exactly four flash files")
    for name, _ in FILES:
        image = artifact / name
        source = build / name
        if name == "boot_app0.bin" and not source.is_file():
            source = Path.home() / ".platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin"
        require(image.is_file() and source.is_file() and sha(image) == sha(source) == entries[name]["sha256"],
                "Artifact image differs from actual successful build/receipt")
        size = entries[name].get("size", entries[name].get("sizeBytes", entries[name].get("bytes")))
        require(image.stat().st_size == size, "Receipt image size differs")
    require(sha(artifact / "firmware.bin") == receipt.get("firmwareSha256", receipt.get("sha256")), "Firmware receipt hash differs")
    log = Path(receipt["log"])
    require(log.is_file() and "[SUCCESS]" in log.read_text(encoding="utf-8", errors="replace"), "Actual successful build log is missing")
    return env, artifact, build, path, receipt


def model_provenance(model, env, binary):
    directory = FW / f"gld/models/model_{model}"
    metadata = read(directory / "model.json")
    header = directory / "cnn_gas_datasheet_model_data.h"
    match = re.search(r"g_cnn_gas_datasheet_2class_model\[\]\s*=\s*\{(.*?)\};", header.read_text(encoding="utf-8"), re.S)
    require(match is not None, "Public model array is unavailable")
    blob = bytes(int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]{2})", match.group(1)))
    digest = hashlib.sha256(blob).hexdigest()
    require(digest == metadata["modelSha256"] and binary.count(blob) == 1, "Firmware does not embed the exact source model once")
    compiled = re.search(r'PROFILE_ID\s*=\s*"([^"]+)"', (directory / "ModelMetadata.h").read_text(encoding="utf-8"))
    require(compiled is not None and metadata["profileId"] == compiled.group(1) and metadata["profileId"].encode() in binary,
            "Model/profile identity differs")
    for marker in (b"gld-dataset-wifi/3", b"PAUSE_DATASET", b"CONTINUE_DATASET", b"RESUME_DATASET", b"ACK_SAMPLES"):
        require(marker in binary, "Required workflow protocol/control marker missing")
    return dict(environment=env, sourceModelEnvironment=f"gld_model_{model}", protocol="gld-dataset-wifi/3",
                profileId=metadata["profileId"], sha256=digest, size=len(blob),
                sourceArchiveSha256=metadata["sourceArchiveSha256"], firmwareSha256=hashlib.sha256(binary).hexdigest(),
                modelHeaderSha256=sha(header), normalizeParamsSha256=sha(directory / "cnn_gas_datasheet_normalize_params.h"),
                sensitivityTableSha256=sha(directory / "cnn_gas_sensitivity_table.h"))


def private_verification(env, build, binary, paths):
    # Values remain private local variables, including on any failure path.
    from prepare_dataset_workflow_wifi import _validate
    own = read(FW / ".pio/gld-dataset-workflow-wifi" / env / "credentials.local.json")
    password = _validate(own, env, "gld-dataset-wifi/3")
    previous_env = env.replace("_workflow_wifi", "_replay_wifi")
    previous = read(FW / ".pio/gld-dataset-replay-wifi" / previous_env / "credentials.local.json")
    require(password == _validate(previous, previous_env, "gld-dataset-wifi/2"), "Workflow operator credential differs from matching Replay config")
    header = build / "private-dataset-workflow-wifi/GldDatasetWorkflowWifiSecrets.h"
    match = re.search(r'^#define GLD_DATASET_WORKFLOW_PRIVATE_PASSWORD\s+(".*")\s*$', header.read_text(encoding="utf-8"), re.M)
    require(match is not None and json.loads(match.group(1)) == password, "Generated private header differs")
    require(password.encode("ascii") in binary, "Built image does not contain configured credential")
    require(all(password.encode("ascii") not in path.read_bytes() for path in paths if path.is_file()),
            "Private credential appears in plaintext metadata/logs")


def package(model, modules, core, snapshot, install):
    post, uploader, preflight, hub = modules
    env, artifact, build, receipt_path, receipt = verify_receipt(model)
    binary = (artifact / "firmware.bin").read_bytes()
    provenance = model_provenance(model, env, binary)
    versions = post._version_constants(FW)
    version = versions["GLD1_FIRMWARE_VERSION"]
    require(version == "0.8.36" and version.encode() in binary, "Workflow must use isolated GLD1 runtime version 0.8.36")
    flash = [dict(path=name, offset=f"0x{offset:08X}", size=(artifact / name).stat().st_size, sha256=sha(artifact / name)) for name, offset in FILES]
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    existing = artifact / "manifest.json"
    if existing.is_file():
        previous = read(existing)
        require(previous.get("environment") == env and previous.get("flashSetSha256") == post._flash_set_sha256(flash),
                "Refuse replacing an unrelated existing workflow package")
        if previous["source"].get("firmwareTreeSnapshotSha256") == snapshot:
            timestamp = previous["source"]["packagedAtUtc"]
    manifest = dict(schemaVersion=2, packageType="pertamina-gld-prebuilt-firmware", deviceId="ANY",
                    boardProfile=f"WROOM-1U-N16R8 / Model {model} / Dataset Wi-Fi Workflow Protocol 3", environment=env,
                    firmwareVersion=version, protocolVersion=versions["PROTOCOL_VERSION"], configSchemaVersion=versions["CONFIG_SCHEMA_VERSION"],
                    chip="esp32s3", baud=921600, createdAtUtc=timestamp,
                    source=dict(gitCommit=post._git_commit(ROOT), gitTreeState="build-output", gitTreeStateScope="firmware/",
                                firmwareTreeSnapshotSha256=snapshot, platformioCoreVersion=core, platformioIniSha256=sha(FW / "platformio.ini"),
                                buildCommand=f"pio run -e {env}", packagedAtUtc=timestamp),
                    flashSetSha256=post._flash_set_sha256(flash), flashFiles=flash)
    encoded = {name: base64.b64encode((artifact / name).read_bytes()).decode("ascii") for name, _ in FILES}
    checked, verified = uploader.validate_firmware_package(manifest, encoded, env, "1002")
    require(len(verified) == 4 and not uploader.requires_gld1_nvs_reset_before_boot(checked), "Strict child validation or no-reset guard failed")
    offset, size = uploader.verified_nvs_region(verified)
    require((offset, size) == (0x9000, 0x5000), "Unexpected GLD1 NVS layout")
    for item, data in verified:
        start = int(item["offset"], 0)
        erase_end = (start + len(data) + 4095) & ~4095
        require(start % 4096 == 0 and (erase_end <= offset or start >= offset + size), "Flash erase sector overlaps preserved NVS")
    previous_partition = FW / ".pio/artifacts/gld-dataset-replay-wifi-20261102-operator-password" / env.replace("_workflow_wifi", "_replay_wifi") / "partitions.bin"
    require(sha(previous_partition) == sha(artifact / "partitions.bin"), "Partition layout differs from preceding GLD1 package")
    dump(artifact / "manifest.json", manifest)
    (artifact / "manifest.sha256").write_text(f"{sha(artifact / 'manifest.json')}  manifest.json\n", encoding="ascii")
    dump(artifact / "model-provenance.json", provenance)
    preflight._verify_manifest(artifact / "manifest.json", env)
    hub.validate_selected_package(dict(manifest=manifest, packageFiles=encoded), env)
    public = [p for p in artifact.iterdir() if p.is_file() and p.suffix in {".json", ".sha256", ".log"}]
    public += [receipt_path, Path(receipt["log"]), Path(__file__)]
    private_verification(env, build, binary, public)
    destination = HUB_ROOT / env / "latest"
    result = dict(environment=env, status="PASS", verifiedFiles=4, firmwareSha256=sha(artifact / "firmware.bin"),
                  firmwareSize=len(binary), manifestSha256=sha(artifact / "manifest.json"), flashSetSha256=manifest["flashSetSha256"],
                  runtimeVersion=version, protocol="gld-dataset-wifi/3", firmwareSnapshotSha256=snapshot,
                  strictChildValidator="PASS", hubSelectionValidator="PASS", preflightManifestValidator="PASS",
                  modelBlobMatchesSourceAndBinary=True, partitionLayoutUnchanged=True, flashEraseSectorsAvoidNvs=True,
                  nvsOffset="0x9000", nvsSize=0x5000, nvsResetRequired=False,
                  privateCredentialMatchesMatchingReplay=True, privateHeaderAndImageMatch=True,
                  secretAbsentFromPlaintextMetadataAndLogs=True, credentialValueDisclosed=False,
                  buildReceipt=str(receipt_path), buildReceiptSha256=sha(receipt_path),
                  hardwareValidation="not performed; runtime heap, Pause/inference timing and 500ms cadence unmeasured",
                  artifactDirectory=str(artifact), hubDirectory=str(destination), hubInstalled=install)
    dump(artifact / "offline-package-validation.json", result)
    private_verification(env, build, binary, public + [artifact / "offline-package-validation.json"])
    if install:
        require(not destination.exists() or {p.name for p in destination.iterdir()} <= set(PACKAGE_FILES), "Unexpected file in workflow Hub destination")
        for name in PACKAGE_FILES:
            require(not (destination / name).exists() or sha(destination / name) == sha(artifact / name), "Refuse overwriting a different Hub package")
        destination.mkdir(parents=True, exist_ok=True)
        for name in PACKAGE_FILES:
            shutil.copy2(artifact / name, destination / name)
            require(sha(artifact / name) == sha(destination / name), "Hub copy checksum differs")
        preflight._verify_manifest(destination / "manifest.json", env)
        hub.validate_selected_package(dict(manifest=read(destination / "manifest.json"), packageFiles=encoded), env)
        private_verification(env, build, binary, list(destination.glob("*.json")) + list(destination.glob("*.sha256")))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=int, choices=(1, 2, 3), action="append")
    parser.add_argument("--install-hub", action="store_true", help="Copy only validated new workflow packages into their dedicated Hub directories")
    args = parser.parse_args()
    try:
        sys.path[:0] = [str(FW / "tools"), str(ROOT / "apps/gld-operator"), str(ROOT / "apps/operator-hub")]
        modules = (load(FW / "tools/operator_package_post.py", "workflow_package_post"),
                   load(ROOT / "apps/gld-operator/bridge.py", "workflow_package_child"),
                   load(ROOT / "apps/operator-hub/preflight.py", "workflow_package_preflight"),
                   load(ROOT / "apps/operator-hub/bridge.py", "workflow_package_hub"))
        core = subprocess.run([str(Path.home() / ".platformio/penv/Scripts/python.exe"), "-c",
                               "import importlib.metadata; print(importlib.metadata.version('platformio'))"],
                              check=True, capture_output=True, text=True).stdout.strip()
        require(re.fullmatch(r"\d+\.\d+\.\d+", core) is not None, "Cannot determine actual PlatformIO version")
        protected = protected_snapshot()
        snapshot = modules[0]._firmware_tree_snapshot_sha256(FW)
        results = [package(model, modules, core, snapshot, args.install_hub) for model in sorted(set(args.model or (1, 2, 3)))]
        require(protected == protected_snapshot(), "An old protected package/artifact changed")
        require(snapshot == modules[0]._firmware_tree_snapshot_sha256(FW), "Firmware workspace changed during packaging")
        print(json.dumps(dict(status="PASS", oldProtectedFilesUnchanged=len(protected),
                              packages=[{key: item[key] for key in ("environment", "firmwareSha256", "firmwareSize", "manifestSha256", "hubInstalled")} for item in results])))
        return 0
    except Exception as exc:
        # Never reflect validator payloads, credential values or arbitrary errors.
        print(json.dumps(dict(status="BLOCKED", errorClass=type(exc).__name__,
                              reason=str(exc) if isinstance(exc, PackageError) else "Packaging/validator failure; coordinator must inspect the public schema or environment whitelist")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
