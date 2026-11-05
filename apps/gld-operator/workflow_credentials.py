"""Resolve dedicated workflow credentials without requiring local build output.

Device identity is established after the Wi-Fi join, so automatic discovery is
safe only when all three configurations agree. Existing private build configs
remain an explicit override. Clean checkouts read the credential already embedded
in each verified shipped image, at release-generated offsets; no guessed default,
plaintext credential sidecar, file creation, or arbitrary path input.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import re

ENVIRONMENTS = tuple(f"gld_model_{model}_dataset_workflow_wifi" for model in (1, 2, 3))


def _read_json(path):
    if not path.is_file() or path.stat().st_size > 16384:
        raise ValueError("configuration unavailable")
    return json.loads(path.read_text(encoding="utf-8"))


def _packaged_passwords(root, profile=None):
    if profile is None:
        profile = _read_json(root / "apps/gld-operator/workflow-connection-profiles.json")
    if (not isinstance(profile, dict) or set(profile) != {"schemaVersion", "protocol", "models"} or
            type(profile["schemaVersion"]) is not int or profile["schemaVersion"] != 1 or
            profile["protocol"] != "gld-dataset-wifi/3" or
            not isinstance(profile["models"], dict) or set(profile["models"]) != set(ENVIRONMENTS)):
        raise ValueError("invalid connection profile")
    passwords = []
    for environment in ENVIRONMENTS:
        entry = profile["models"][environment]
        if not isinstance(entry, dict) or set(entry) != {"firmwareSha256", "passwordOffset", "passwordLength"}:
            raise ValueError("invalid connection entry")
        digest, offset, length = (entry[key] for key in ("firmwareSha256", "passwordOffset", "passwordLength"))
        if (not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None or
                type(offset) is not int or offset < 0 or type(length) is not int or not 8 <= length <= 63):
            raise ValueError("invalid image reference")
        directory = root / "apps/operator-hub/firmware-packages" / environment / "latest"
        manifest = _read_json(directory / "manifest.json")
        if (not isinstance(manifest, dict) or manifest.get("schemaVersion") != 2 or
                manifest.get("packageType") != "pertamina-gld-prebuilt-firmware" or
                manifest.get("environment") != environment or manifest.get("chip") != "esp32s3"):
            raise ValueError("invalid packaged image")
        files = manifest.get("flashFiles")
        firmware = [item for item in files if isinstance(item, dict) and item.get("path") == "firmware.bin"] if isinstance(files, list) else []
        path = directory / "firmware.bin"
        if len(firmware) != 1 or not path.is_file() or not 0 < path.stat().st_size <= 8 * 1024 * 1024:
            raise ValueError("image unavailable")
        binary = path.read_bytes()
        if (hashlib.sha256(binary).hexdigest() != digest or firmware[0].get("sha256") != digest or
                firmware[0].get("size") != len(binary) or offset + length >= len(binary) or
                binary[offset + length] != 0):
            raise ValueError("packaged image differs")
        password = binary[offset:offset + length].decode("ascii")
        if re.fullmatch(r"[A-Za-z0-9_-]{8,63}", password) is None:
            raise ValueError("invalid image credential")
        passwords.append(password)
    return passwords


def resolve_workflow_password(project_root=None):
    root = Path(project_root) if project_root is not None else Path(__file__).resolve().parents[2]
    passwords = []
    try:
        paths = [root / "firmware/.pio/gld-dataset-workflow-wifi" / environment / "credentials.local.json"
                 for environment in ENVIRONMENTS]
        # A present but malformed/partial override must never silently fall back.
        use_packaged = not any(path.exists() for path in paths)
        if use_packaged:
            passwords = _packaged_passwords(root)
        for model in (1, 2, 3):
            if use_packaged:
                break
            environment = f"gld_model_{model}_dataset_workflow_wifi"
            path = root / "firmware" / ".pio" / "gld-dataset-workflow-wifi" / environment / "credentials.local.json"
            value = _read_json(path)
            password = value.get("password") if isinstance(value, dict) else None
            if (not isinstance(value, dict) or value.get("environment") != environment or
                    value.get("protocol") != "gld-dataset-wifi/3" or value.get("username") != "gld" or
                    value.get("address") != "192.168.4.1" or type(value.get("port")) is not int or
                    value["port"] != 81 or value.get("path") != "/dataset" or
                    not isinstance(password, str) or re.fullmatch(r"[A-Za-z0-9_-]{8,63}", password) is None):
                raise ValueError("configuration invalid")
            passwords.append(password)
        if len(set(passwords)) != 1:
            raise ValueError("model configurations disagree")
    except (OSError, ValueError, TypeError, KeyError):
        raise RuntimeError("Kredensial hotspot GLD belum tersedia atau tidak cocok. Periksa paket firmware Operator Hub.") from None
    return passwords[0]
