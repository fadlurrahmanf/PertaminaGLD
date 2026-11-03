"""Private protocol-2 credentials; never reads or changes protocol-1 secrets."""
from __future__ import annotations
import json
import pathlib
import secrets

ENVIRONMENTS = frozenset(f"gld_model_{model}_dataset_replay_wifi" for model in (1, 2, 3))


def prepare(project: pathlib.Path, build: pathlib.Path, name: str) -> pathlib.Path:
    if name not in ENVIRONMENTS:
        raise ValueError("Replay credentials require a dedicated protocol-2 environment")
    directory = project / ".pio" / "gld-dataset-replay-wifi" / name
    directory.mkdir(parents=True, exist_ok=True)
    credential = directory / "credentials.local.json"
    if credential.exists():
        data = json.loads(credential.read_text(encoding="utf-8"))
        password = data.get("password") if isinstance(data, dict) else None
        if (not isinstance(data, dict) or data.get("environment") != name or
                data.get("username") != "gld" or data.get("protocol") != "gld-dataset-wifi/2" or
                not isinstance(password, str) or not 8 <= len(password) <= 63 or
                any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in password)):
            raise ValueError("Invalid replay credentials; refusing silent rotation")
    else:
        password = secrets.token_urlsafe(24)
        data = dict(environment=name, username="gld", password=password,
                    protocol="gld-dataset-wifi/2", address="192.168.4.1", port=81, path="/dataset")
        with credential.open("x", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
    include = build / "private-dataset-replay-wifi"
    include.mkdir(parents=True, exist_ok=True)
    (include / "GldDatasetReplayWifiSecrets.h").write_text(
        "#pragma once\n#define GLD_DATASET_REPLAY_PRIVATE_PASSWORD " + json.dumps(password) + "\n",
        encoding="utf-8")
    return include


try:
    Import("env")
except NameError:
    env = None

if env is not None:
    env.Append(CPPPATH=[str(prepare(pathlib.Path(env.subst("$PROJECT_DIR")),
                                  pathlib.Path(env.subst("$BUILD_DIR")), env.subst("$PIOENV")))])
