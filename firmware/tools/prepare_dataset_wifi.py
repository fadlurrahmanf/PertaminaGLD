"""Private credentials for the isolated GLD Dataset Wi-Fi builds only.

The stable random password is never printed or included in tracked sources.
Delete the chosen environment's ignored credentials.local.json deliberately to
rotate it on the next explicitly authorised build. Rotation requires reflashing.
"""

from __future__ import annotations

import json
import pathlib
import secrets


ENVIRONMENTS = frozenset({
    "gld_model_1_dataset_wifi", "gld_model_2_dataset_wifi", "gld_model_3_dataset_wifi",
})


def prepare(project: pathlib.Path, build: pathlib.Path, name: str) -> pathlib.Path:
    if name not in ENVIRONMENTS:
        raise ValueError("Dataset Wi-Fi credentials are restricted to dedicated environments")
    directory = project / ".pio" / "gld-dataset-wifi" / name
    directory.mkdir(parents=True, exist_ok=True)
    credential_file = directory / "credentials.local.json"
    if credential_file.exists():
        data = json.loads(credential_file.read_text(encoding="utf-8"))
        password = data.get("password")
        if (data.get("environment") != name or data.get("username") != "gld"
                or not isinstance(password, str) or not 24 <= len(password) <= 63
                or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in password)):
            raise ValueError("Invalid private Dataset Wi-Fi credential file; refusing silent rotation")
    else:
        password = secrets.token_urlsafe(24)
        data = {"environment": name, "username": "gld", "password": password,
                "protocol": "gld-dataset-wifi/1", "address": "192.168.4.1",
                "port": 81, "path": "/dataset"}
        # Exclusive creation refuses to overwrite a credential from a parallel build.
        with credential_file.open("x", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
    private_include = build / "private-dataset-wifi"
    private_include.mkdir(parents=True, exist_ok=True)
    (private_include / "GldDatasetWifiSecrets.h").write_text(
        "#pragma once\n#define GLD_DATASET_WIFI_PRIVATE_PASSWORD "
        + json.dumps(password) + "\n", encoding="utf-8")
    return private_include


try:
    Import("env")
except NameError:
    env = None

if env is not None:
    env.Append(CPPPATH=[str(prepare(pathlib.Path(env.subst("$PROJECT_DIR")),
                                  pathlib.Path(env.subst("$BUILD_DIR")),
                                  env.subst("$PIOENV")))])
