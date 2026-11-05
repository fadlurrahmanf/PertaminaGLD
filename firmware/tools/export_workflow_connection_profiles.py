"""Export public image references for portable Hub connection (no secrets output).

Run after publishing all three final Workflow packages. The credential is already
embedded in each shipped firmware.bin. This descriptor stores only its position
and the exact image hash, never the credential itself. No hardware/build actions.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = "apps/gld-operator/workflow-connection-profiles.json"
ENVIRONMENTS = tuple(f"gld_model_{model}_dataset_workflow_wifi" for model in (1, 2, 3))


def generate(root):
    models, passwords = {}, []
    for environment in ENVIRONMENTS:
        private = root / "firmware/.pio/gld-dataset-workflow-wifi" / environment / "credentials.local.json"
        value = json.loads(private.read_text(encoding="utf-8"))
        password = value.get("password")
        if (value.get("environment") != environment or value.get("protocol") != "gld-dataset-wifi/3" or
                value.get("username") != "gld" or not isinstance(password, str) or
                re.fullmatch(r"[A-Za-z0-9_-]{8,63}", password) is None):
            raise ValueError("Invalid private release configuration")
        passwords.append(password)
        directory = root / "apps/operator-hub/firmware-packages" / environment / "latest"
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        binary = (directory / "firmware.bin").read_bytes()
        digest = hashlib.sha256(binary).hexdigest()
        files = [item for item in manifest["flashFiles"] if item.get("path") == "firmware.bin"]
        if (manifest.get("environment") != environment or len(files) != 1 or
                files[0].get("sha256") != digest or files[0].get("size") != len(binary)):
            raise ValueError("Published release image differs")
        marker = password.encode("ascii") + b"\0"
        offsets = [match.start() for match in re.finditer(re.escape(marker), binary)]
        if len(offsets) != 1:
            raise ValueError("Release credential location is ambiguous")
        models[environment] = dict(firmwareSha256=digest, passwordOffset=offsets[0], passwordLength=len(password))
    if len(set(passwords)) != 1:
        raise ValueError("Three release credentials must agree")
    return dict(schemaVersion=1, protocol="gld-dataset-wifi/3", models=models)


def check(root, profile=None):
    spec = importlib.util.spec_from_file_location("portable_workflow_credentials", root / "apps/gld-operator/workflow_credentials.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    passwords = module._packaged_passwords(root, profile)
    if len(passwords) != 3 or len(set(passwords)) != 1:
        raise ValueError("Three packaged credentials must agree")


def export_profiles(root):
    value = generate(root)
    check(root, value)
    path = root / OUTPUT
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate committed profiles/images; no private build files required")
    args = parser.parse_args()
    try:
        if not args.check:
            export_profiles(ROOT)
        check(ROOT)
    except Exception:
        # No raw exception/config/password/path reflection.
        print("BLOCKED: portable Workflow release profile is missing, inconsistent or invalid.")
        return 1
    print("PASS: portable connection profiles match all three published images; no credential disclosed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
