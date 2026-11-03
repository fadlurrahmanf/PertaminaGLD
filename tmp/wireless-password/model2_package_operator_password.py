"""Package only the authorized new Model2 credential artifact, after success.

No compile/upload/service/COM/network actions. The strict live uploader
validator is imported and called only as a pure byte/package validator.
"""
import argparse
import base64
import datetime as dt
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIRMWARE = ROOT / "firmware"
ENV = "gld_model_2_dataset_replay_wifi"
OLD = FIRMWARE / ".pio/artifacts/gld-dataset-replay-wifi-20261102" / ENV
NEW = FIRMWARE / ".pio/artifacts/gld-dataset-replay-wifi-20261102-operator-password" / ENV
CREDENTIAL = FIRMWARE / ".pio/gld-dataset-replay-wifi" / ENV / "credentials.local.json"
FILES = [("bootloader.bin", 0), ("partitions.bin", 0x8000), ("boot_app0.bin", 0xE000), ("firmware.bin", 0x10000)]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def model_identity(binary):
    model = FIRMWARE / "gld/models/model_2"
    metadata = read(model / "model.json")
    header = model / "cnn_gas_datasheet_model_data.h"
    text = header.read_text(encoding="utf-8")
    match = re.search(r"g_cnn_gas_datasheet_2class_model\[\]\s*=\s*\{(.*?)\};", text, re.S)
    require(match is not None, "Model array declaration unavailable")
    blob = bytes(int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]{2})", match.group(1)))
    blob_hash = hashlib.sha256(blob).hexdigest()
    require(blob_hash == metadata["modelSha256"], "Current model array differs from model metadata")
    require(binary.count(blob) == 1, "New image must embed exactly one unchanged Model2 blob")
    require(metadata["profileId"].encode() in binary and b"gld-dataset-wifi/2" in binary, "New image identity/protocol markers differ")
    return dict(environment=ENV, sourceModelEnvironment="gld_model_2", protocol="gld-dataset-wifi/2",
        profileId=metadata["profileId"], sha256=blob_hash, sourceArchiveSha256=metadata["sourceArchiveSha256"],
        size=len(blob), firmwareSha256=hashlib.sha256(binary).hexdigest(), modelHeaderSha256=sha(header),
        normalizeParamsSha256=sha(model / "cnn_gas_datasheet_normalize_params.h"),
        sensitivityTableSha256=sha(model / "cnn_gas_sensitivity_table.h"))


def scan_plaintext_secret(password, files):
    encoded = password.encode("ascii")
    require(all(encoded not in path.read_bytes() for path in files if path.is_file()),
            "Selected credential appears in plaintext metadata or logs; refusing package")


def package(receipt_path):
    require(NEW.is_dir() and OLD.is_dir(), "Both authorized new and preserved old artifacts must exist")
    before_old = {name: sha(OLD / name) for name, _offset in FILES}
    receipt = read(receipt_path)
    require(receipt.get("environment") == ENV, "Build receipt environment differs")
    exit_code = receipt.get("exitCode", receipt.get("exit_code", receipt.get("exit")))
    require(type(exit_code) is int and exit_code == 0, "New build has not completed successfully")
    require(receipt.get("status") in {"success", "completed", "built"}, "New build receipt is not successful")
    require(receipt.get("hardwareAction") in (None, False, "none", "none; compile only"), "Unexpected hardware action in build receipt")
    require(receipt.get("credentialValueDisclosed") is False, "Credential non-disclosure evidence missing")
    source_before = receipt.get("sourceSha256Before") or {}
    require(bool(source_before), "Public source identity before build is missing")
    require(all((ROOT / name).is_file() and sha(ROOT / name) == value.lower()
                for name, value in source_before.items()), "Public source changed since new build began")
    build = Path(receipt["buildDirectory"])
    if not (build / "firmware.bin").is_file():
        build = build / ENV
    require(sha(NEW / "firmware.bin") == sha(build / "firmware.bin"), "Copied new firmware differs from successful build output")
    require(sha(NEW / "firmware.bin") == str(receipt.get("sha256", "")).lower(), "New binary differs from successful receipt hash")
    require(sha(NEW / "firmware.bin") != before_old["firmware.bin"], "New firmware is unexpectedly identical to old credential image")
    for name, _offset in FILES[:3]:
        require(sha(NEW / name) == before_old[name], "Boot/partition region changed during credential-only rebuild")
    credential = read(CREDENTIAL)
    password = credential.get("password")
    require(isinstance(password, str) and len(password) >= 8, "Private selected credential is unavailable")
    binary = (NEW / "firmware.bin").read_bytes()
    require(password.encode("ascii") in binary, "New image does not embed selected private credential")
    require(password.encode("ascii") not in (OLD / "firmware.bin").read_bytes(), "Old image already contains selected credential; revision identity ambiguous")
    sys.path[:0] = [str(ROOT / "apps/gld-operator"), str(ROOT / "apps/operator-hub")]
    post = load(FIRMWARE / "tools/operator_package_post.py", "operator_password_post_helpers")
    uploader = load(ROOT / "apps/gld-operator/bridge.py", "operator_password_strict_uploader")
    preflight = load(ROOT / "apps/operator-hub/preflight.py", "operator_password_preflight")
    hub = load(ROOT / "apps/operator-hub/bridge.py", "operator_password_hub_validator")
    versions = post._version_constants(FIRMWARE)
    # GLD1 Replay inherits the isolated WROOM GLD1 runtime version, not the
    # shared GLD2/general firmware constant. Credential-only revision keeps it.
    runtime_version = versions["GLD1_FIRMWARE_VERSION"]
    require(runtime_version == read(OLD / "manifest.json")["firmwareVersion"],
            "Credential-only revision must preserve isolated GLD1 runtime version")
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    core = subprocess.run([str(Path.home() / ".platformio/penv/Scripts/python.exe"), "-c",
        "import importlib.metadata; print(importlib.metadata.version('platformio'))"],
        check=True, capture_output=True, text=True).stdout.strip()
    require(bool(re.fullmatch(r"\d+\.\d+\.\d+", core)), "Cannot identify actual PlatformIO version")
    flash = [dict(path=name, offset=f"0x{offset:08X}", size=(NEW / name).stat().st_size, sha256=sha(NEW / name))
             for name, offset in FILES]
    manifest = dict(schemaVersion=2, packageType="pertamina-gld-prebuilt-firmware", deviceId="ANY",
        boardProfile="WROOM-1U-N16R8 / Model 2 / Dataset Wi-Fi Replay Protocol 2", environment=ENV,
        firmwareVersion=runtime_version, protocolVersion=versions["PROTOCOL_VERSION"],
        configSchemaVersion=versions["CONFIG_SCHEMA_VERSION"], chip="esp32s3", baud=921600,
        createdAtUtc=now, source=dict(gitCommit=post._git_commit(ROOT), gitTreeState="build-output",
            gitTreeStateScope="firmware/", firmwareTreeSnapshotSha256=post._firmware_tree_snapshot_sha256(FIRMWARE),
            platformioCoreVersion=core, platformioIniSha256=sha(FIRMWARE / "platformio.ini"),
            buildCommand=f"pio run -e {ENV}", packagedAtUtc=now),
        flashSetSha256=post._flash_set_sha256(flash), flashFiles=flash)
    # Only these four new metadata paths are written. Existing artifacts/packages
    # and the prepared credential/header are never changed by this program.
    provenance = model_identity(binary)
    dump(NEW / "manifest.json", manifest)
    (NEW / "manifest.sha256").write_text(f"{sha(NEW / 'manifest.json')}  manifest.json\n", encoding="ascii")
    dump(NEW / "model-provenance.json", provenance)
    encoded = {name: base64.b64encode((NEW / name).read_bytes()).decode("ascii") for name, _ in FILES}
    checked, verified = uploader.validate_firmware_package(manifest, encoded, ENV, "1002")
    require(len(verified) == 4, "Strict uploader did not verify four regions")
    require(uploader.requires_gld1_nvs_reset_before_boot(checked) is False, "Credential replay image unexpectedly requires NVS reset")
    nvs_offset, nvs_size = uploader.verified_nvs_region(verified)
    require((nvs_offset, nvs_size) == (0x9000, 0x5000), "NVS layout differs from preserved GLD1 partition")
    for item, data in verified:
        offset = int(item["offset"], 0)
        erase_end = (offset + len(data) + 4095) & ~4095
        require(erase_end <= nvs_offset or offset >= nvs_offset + nvs_size,
                "New flash region overlaps preserved NVS")
    preflight._verify_manifest(NEW / "manifest.json", ENV)
    hub.validate_selected_package(dict(manifest=manifest, packageFiles=encoded), ENV)
    files_to_scan = list(NEW.glob("*.json")) + list(NEW.glob("*.sha256")) + list(NEW.glob("*.log"))
    files_to_scan += [Path(receipt_path), Path(receipt.get("log", ""))]
    scan_plaintext_secret(password, files_to_scan)
    unchanged = before_old == {name: sha(OLD / name) for name, _offset in FILES}
    require(unchanged, "Preserved old artifact changed")
    result = dict(environment=ENV, status="PASS", verifiedFiles=4,
        firmwareSha256=sha(NEW / "firmware.bin"), firmwareSize=(NEW / "firmware.bin").stat().st_size,
        manifestSha256=sha(NEW / "manifest.json"), flashSetSha256=manifest["flashSetSha256"],
        sourceSnapshotFreshlyComputed=True, firmwareSnapshotSha256=manifest["source"]["firmwareTreeSnapshotSha256"],
        modelBlobMatchesSourceAndBinary=True, modelUnchanged=True, partitionLayoutUnchanged=True,
        nvsOffset=f"0x{nvs_offset:X}", nvsSize=nvs_size, flashRegionsAvoidNvs=True,
        oldArtifactPreserved=unchanged, secretAbsentFromPlaintextMetadataAndLogs=True,
        strictChildValidator="PASS", hubSelectionValidator="PASS", preflightManifestValidator="PASS",
        actualNewHardwareTest="not performed; user self-upload pending",
        semanticVersion=dict(runtime=runtime_version, source="firmware/gld/include/Gld1FirmwareVersion.h",
            preservedOldArtifactVersion=True,
            isolatedGld1VersionVerified=True),
        buildReceipt=str(Path(receipt_path).resolve()), buildReceiptSha256=sha(receipt_path),
        evidence="Successful incremental build bytes + fresh package/provenance; no clean-build or device proof claimed")
    dump(NEW / "offline-package-validation.json", result)
    scan_plaintext_secret(password, files_to_scan + [NEW / "offline-package-validation.json"])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", default=str(ROOT / "tmp/wireless-password/model2-build-receipt.json"))
    args = parser.parse_args()
    try:
        result = package(args.receipt)
    except Exception as exc:
        # Exceptions are not allowed to reflect the credential, header or payload.
        print(json.dumps(dict(status="BLOCKED", errorClass=type(exc).__name__,
                              detail=str(exc) if isinstance(exc, RuntimeError) else "Packaging validation failed; inspect locally")))
        return 1
    print(json.dumps({key: result[key] for key in ("status", "verifiedFiles", "firmwareSha256",
        "firmwareSize", "manifestSha256", "oldArtifactPreserved", "secretAbsentFromPlaintextMetadataAndLogs")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
