"""Private workflow credentials; source preparation is not a build/upload.

The first approved build copies the matching operator password from protocol2
without changing that file. Missing/invalid credentials fail closed; no silent
rotation or new default. Tests must use temporary synthetic credentials only.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

ENVIRONMENTS = frozenset(f"gld_model_{model}_dataset_workflow_wifi" for model in (1, 2, 3))
PROTOCOL = "gld-dataset-wifi/3"


def _validate(data, name, protocol):
    password = data.get("password") if isinstance(data, dict) else None
    if (not isinstance(data, dict) or data.get("environment") != name or
            data.get("username") != "gld" or data.get("protocol") != protocol or
            not isinstance(password, str) or re.fullmatch(r"[A-Za-z0-9_-]{8,63}", password) is None):
        raise ValueError("Invalid workflow credentials; refusing silent rotation")
    return password


def prepare(project: Path, build: Path, name: str) -> Path:
    if name not in ENVIRONMENTS:
        raise ValueError("Workflow credentials require a dedicated protocol-3 environment")
    directory = project / ".pio" / "gld-dataset-workflow-wifi" / name
    credential = directory / "credentials.local.json"
    if credential.exists():
        password = _validate(json.loads(credential.read_text(encoding="utf-8")), name, PROTOCOL)
    else:
        previous_name = name.replace("_dataset_workflow_wifi", "_dataset_replay_wifi")
        previous = project / ".pio" / "gld-dataset-replay-wifi" / previous_name / "credentials.local.json"
        if not previous.is_file():
            raise ValueError("Configure private workflow credentials or matching replay credentials before compiling")
        password = _validate(json.loads(previous.read_text(encoding="utf-8")), previous_name, "gld-dataset-wifi/2")
        directory.mkdir(parents=True, exist_ok=True)
        data = dict(environment=name, username="gld", password=password, protocol=PROTOCOL,
                    address="192.168.4.1", port=81, path="/dataset")
        with credential.open("x", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
    include = build / "private-dataset-workflow-wifi"
    include.mkdir(parents=True, exist_ok=True)
    (include / "GldDatasetWorkflowWifiSecrets.h").write_text(
        "#pragma once\n#define GLD_DATASET_WORKFLOW_PRIVATE_PASSWORD " + json.dumps(password) + "\n",
        encoding="utf-8")
    return include


try:
    Import("env")
except NameError:
    env = None

if env is not None:
    env.Append(CPPPATH=[str(prepare(Path(env.subst("$PROJECT_DIR")),
                                  Path(env.subst("$BUILD_DIR")), env.subst("$PIOENV")))])
