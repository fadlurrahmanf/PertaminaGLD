"""Read-only validator for the newly built Model 2 release package."""
from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path

ROOT = Path(r"D:/Github/PertaminaGLD")
PACKAGE = Path(r"D:/Github/PertaminaGLD-GLD1-69a493c/apps/operator-hub/firmware-packages/gld_model_2/latest")
BRIDGE_PATH = ROOT / "apps/gld-operator/bridge.py"

spec = importlib.util.spec_from_file_location("model2_package_validator", BRIDGE_PATH)
assert spec and spec.loader
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
files = {
    entry["path"]: base64.b64encode((PACKAGE / entry["path"]).read_bytes()).decode("ascii")
    for entry in manifest["flashFiles"]
}
validated, _ = bridge.validate_firmware_package(manifest, files, "gld_model_2", "1001")
assert validated["firmwareVersion"] == "0.8.38"
assert validated["source"]["gitCommit"] == "69a493c32d2500134a21e029820cd4addea1794a"
assert b"cnn-dualbranch-board-2-2class-v2" in (PACKAGE / "firmware.bin").read_bytes()
print("PASS actual GLD validator, all flash hashes, Model2 profile marker and base identity")
