"""Verify the actual locally packaged GLD1 candidate; no device access."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "apps/operator-hub/firmware-packages/gld_model_1/latest"
MODEL = ROOT / "firmware/gld/models/model_1"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    manifest_bytes = (PACKAGE / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    assert (PACKAGE / "manifest.sha256").read_text().split()[0] == sha(manifest_bytes)
    assert manifest["environment"] == "gld_model_1"
    preflight = module("hub_preflight_candidate", "apps/operator-hub/preflight.py")
    preflight._verify_manifest(PACKAGE / "manifest.json", "gld_model_1")
    bridge = module("gld_bridge_candidate", "apps/gld-operator/bridge.py")
    files = {item["path"]: base64.b64encode((PACKAGE / item["path"]).read_bytes()).decode("ascii")
             for item in manifest["flashFiles"]}
    bridge.validate_firmware_package(manifest, files, "gld_model_1", "1001")

    firmware = (PACKAGE / "firmware.bin").read_bytes()
    assert b"NULLING_STABILITY_GUARD=ON" in firmware
    assert b"NULLING_RECOVERY=ON" in firmware
    assert b"NULLING_CONFIRM_SCAN_MAX_POINTS=30" in firmware
    provenance = json.loads((PACKAGE / "model-provenance.json").read_text())
    metadata = json.loads((MODEL / "model.json").read_text())
    assert provenance["firmwareSha256"] == sha(firmware)
    assert provenance["sha256"] == metadata["modelSha256"]
    assert provenance["sourceArchiveSha256"] == metadata["sourceArchiveSha256"]
    assert provenance["profileId"] == metadata["profileId"]
    header = (MODEL / "cnn_gas_datasheet_model_data.h").read_text()
    array = header.split("g_cnn_gas_datasheet_2class_model[] = {", 1)[1].split("};", 1)[0]
    model = bytes(int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]{2})", array))
    assert len(model) == provenance["size"] and sha(model) == provenance["sha256"]
    assert model in firmware
    for name, key in (("cnn_gas_datasheet_normalize_params.h", "normalizeParamsSha256"),
                      ("cnn_gas_sensitivity_table.h", "sensitivityTableSha256")):
        assert sha((MODEL / name).read_bytes()) == provenance[key]
    print(f"PASS: actual GLD1 package, manifest, preflight, uploader, marker and embedded model; firmware SHA256={sha(firmware)}")


if __name__ == "__main__":
    main()
