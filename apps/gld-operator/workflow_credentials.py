"""Read the dedicated workflow password locally; never return it through HTTP.

Device identity is established after the Wi-Fi join, so automatic discovery is
safe only when all three currently packaged model configurations agree. No
fallback password, file creation, credential rotation, or arbitrary path input.
"""
from __future__ import annotations

import json
from pathlib import Path
import re


def resolve_workflow_password(project_root=None):
    root = Path(project_root) if project_root is not None else Path(__file__).resolve().parents[2]
    passwords = []
    try:
        for model in (1, 2, 3):
            environment = f"gld_model_{model}_dataset_workflow_wifi"
            path = root / "firmware" / ".pio" / "gld-dataset-workflow-wifi" / environment / "credentials.local.json"
            if not path.is_file() or path.stat().st_size > 16384:
                raise ValueError("configuration unavailable")
            value = json.loads(path.read_text(encoding="utf-8"))
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
    except (OSError, ValueError, TypeError):
        raise RuntimeError("Kredensial hotspot GLD belum tersedia atau tidak cocok. Periksa paket firmware Operator Hub.") from None
    return passwords[0]
