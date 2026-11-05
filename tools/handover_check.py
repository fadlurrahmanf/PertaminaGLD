"""Read-only, offline handover readiness. Never opens COM/network or logs secrets."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ENVIRONMENTS = tuple(f"gld_model_{n}_dataset_workflow_wifi" for n in (1, 2, 3))
FLASH_FILES = {"bootloader.bin": 0, "partitions.bin": 0x8000,
               "boot_app0.bin": 0xE000, "firmware.bin": 0x10000}
MAX_JSON = 2 * 1024 * 1024


def _json(path):
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_JSON:
        raise ValueError("invalid_json_file")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("invalid_json_object")
    return value


def _sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(value):
    if not value:
        raise ValueError("invalid_configuration")


def _run(args, timeout=15):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _python_runtime(root, child):
    executable = root / "apps" / child / "python-embed/python.exe"
    _require(executable.is_file())
    result = _run([str(executable), "-B", "-c", "import serial; print('PY_SERIAL_OK')"])
    _require(result.returncode == 0 and result.stdout.strip() == "PY_SERIAL_OK")


def _esptool(root):
    base = root / "apps/lib"
    _require((base / "run_esptool.py").is_file() and any(
        (base / folder / "esptool.py").is_file() for folder in ("esptool", "esptool-master")))
    executable = root / "apps/ch-operator/python-embed/python.exe"
    _require(executable.is_file())
    result = _run([str(executable), "-B", str(base / "run_esptool.py"), "version"])
    _require(result.returncode == 0)


def _websocket(root):
    vendor = root / "apps/gld-operator/vendor/wireless/websocket"
    _require(all((vendor / name).is_file() for name in ("__init__.py", "_core.py", "_handshake.py")))


def _package(root, environment):
    directory = root / "apps/operator-hub/firmware-packages" / environment / "latest"
    manifest = _json(directory / "manifest.json")
    _require(manifest.get("schemaVersion") == 2 and
             manifest.get("packageType") == "pertamina-gld-prebuilt-firmware" and
             manifest.get("environment") == environment and manifest.get("chip") == "esp32s3" and
             manifest.get("capabilities", {}).get("nativeSerial") is True and
             manifest.get("capabilities", {}).get("datasetWifi") is True)
    checksum = (directory / "manifest.sha256").read_text(encoding="ascii").strip()
    # Git may normalize JSON line endings. This sidecar predates an explicit
    # eol attribute, so accept only the three exact LF/CRLF representations;
    # hashes of all binary flash files remain byte-exact.
    manifest_bytes = (directory / "manifest.json").read_bytes()
    lf = manifest_bytes.replace(b"\r\n", b"\n")
    manifest_digests = {hashlib.sha256(data).hexdigest() for data in
                        (manifest_bytes, lf, lf.replace(b"\n", b"\r\n"))}
    _require(re.fullmatch(r"[0-9a-f]{64}  manifest\.json", checksum) is not None and
             checksum[:64] in manifest_digests)
    files = manifest.get("flashFiles")
    _require(isinstance(files, list) and len(files) == 4 and
             all(isinstance(item, dict) for item in files) and
             {item.get("path") for item in files} == set(FLASH_FILES))
    for item in files:
        name = item["path"]  # Names are exact allowlisted leaves, no arbitrary paths.
        path = directory / name
        _require(path.is_file() and type(item.get("size")) is int and
                 0 < item["size"] <= 8 * 1024 * 1024 and path.stat().st_size == item["size"] and
                 isinstance(item.get("sha256"), str) and
                 re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is not None and
                 _sha(path) == item["sha256"] and int(str(item.get("offset")), 0) == FLASH_FILES[name])


def _workflow_profiles(root):
    # Load the shipped resolver without creating __pycache__, and explicitly
    # validate the packaged branch rather than a developer's private .pio override.
    source = root / "apps/gld-operator/workflow_credentials.py"
    _require(source.is_file())
    module = {"__file__": str(source), "__name__": "handover_credentials_check"}
    exec(compile(source.read_bytes(), str(source), "exec"), module)
    passwords = module["_packaged_passwords"](root)
    _require(len(passwords) == 3 and len(set(passwords)) == 1)


def _port(value):
    if isinstance(value, str) and re.fullmatch(r"\d{1,5}", value):
        value = int(value)
    return type(value) is int and 1 <= value <= 65535


def _string(value):
    return isinstance(value, str) and bool(value.strip()) and not any(ord(c) < 32 for c in value)


def _state_config(path):
    value = _json(path)
    # This schema is coordinated with the handover state exporter; values
    # are checked only in memory and never returned in readiness output.
    _require(value.get("schemaVersion") == 1 and value.get("storage") == "plaintext")
    env = value.get("serverEnv")
    _require(isinstance(env, dict) and isinstance(env.get("GLD_AES128_KEY_HEX"), str) and
             re.fullmatch(r"[0-9A-Fa-f]{32}", env["GLD_AES128_KEY_HEX"]) is not None)
    key_id = env.get("GLD_KEY_ID")
    if isinstance(key_id, str) and re.fullmatch(r"\d{1,3}", key_id):
        key_id = int(key_id)
    _require(type(key_id) is int and 1 <= key_id <= 255)
    mqtt = value.get("broker")
    _require(isinstance(mqtt, dict) and _string(mqtt.get("host")) and _port(mqtt.get("port")) and
             _string(mqtt.get("username")) and _string(mqtt.get("password")))


def _deployment_database(path):
    value = _json(path)
    database = value.get("database")
    ports = value.get("ports")
    _require(isinstance(database, dict) and _string(database.get("name")) and
             _string(database.get("user")) and _string(database.get("password")) and
             _string(database.get("rootPassword")) and isinstance(ports, dict) and
             all(_port(ports.get(name)) for name in ("hub", "nodeRed", "mqtt", "database")))


def _runtime(root):
    _require((root / "node/node.exe").is_file() and (root / "node-red/red.js").is_file())
    metadata = _json(root / "node-red/package.json")
    _require(metadata.get("name") == "node-red" and isinstance(metadata.get("version"), str) and
             re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", metadata["version"]) is not None)
    result = _run([str(root / "node/node.exe"), "--version"])
    _require(result.returncode == 0 and re.fullmatch(r"v\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", result.stdout.strip()))


def _driver_inventory():
    """Read signed-driver inventory; a connected physical USB is not required."""
    if os.name != "nt":
        return {"status": "skip", "code": "windows_driver_inventory_not_applicable"}
    command = ("$ErrorActionPreference='Stop'; @(Get-CimInstance Win32_PnPSignedDriver | "
               "Where-Object { $_.DeviceID -match 'VID_1A86' -or $_.DeviceName -match 'CH34[01]' } | "
               "Select-Object InfName,DriverProviderName) | ConvertTo-Json -Compress")
    try:
        result = _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command], timeout=30)
        _require(result.returncode == 0)
        raw = json.loads(result.stdout or "[]")
        records = [raw] if isinstance(raw, dict) else raw
        _require(isinstance(records, list) and all(isinstance(item, dict) for item in records))
        infs = sorted({item["InfName"].lower() for item in records
                       if isinstance(item.get("InfName"), str) and
                       re.fullmatch(r"(?:oem\d+|ch341ser|ch340ser)\.inf", item["InfName"], re.IGNORECASE)})
        # Provider/device strings can be uncontrolled. Output only bounded
        # allowlisted labels, never USB serial numbers or raw CIM objects.
        providers = sorted({"WCH" for item in records if isinstance(item.get("DriverProviderName"), str) and
                            re.search(r"wch|qinheng|jiangsu", item["DriverProviderName"], re.IGNORECASE)})
        return {"status": "pass" if infs else "skip", "code": "ch340_driver_present" if infs else "ch340_driver_not_observed",
                "details": {"present": bool(infs), "infNames": infs, "providers": providers,
                            "physicalUsbRequired": False}}
    except Exception:
        return {"status": "skip", "code": "windows_driver_inventory_unavailable"}


def check(repo_root, state_config=None, runtime_root=None):
    """Return allowlisted JSON-compatible statuses; never write or start services.

    state_config and runtime_root are optional explicit restored locations.
    Missing optional inputs are reported as skips, not inferred from this PC.
    Driver absence is informational because no physical USB is required here.
    """
    root = Path(repo_root)
    checks = []
    def perform(name, action, failure):
        try:
            action()
            checks.append({"name": name, "status": "pass", "code": "verified"})
        except Exception:
            checks.append({"name": name, "status": "fail", "code": failure})
    perform("gld_python_pyserial", lambda: _python_runtime(root, "gld-operator"), "gld_python_or_pyserial_unavailable")
    perform("ch_python_pyserial", lambda: _python_runtime(root, "ch-operator"), "ch_python_or_pyserial_unavailable")
    perform("shared_esptool", lambda: _esptool(root), "shared_esptool_unavailable")
    perform("vendored_websocket", lambda: _websocket(root), "vendored_websocket_unavailable")
    for n, environment in enumerate(ENVIRONMENTS, 1):
        perform(f"workflow_model_{n}", lambda env=environment: _package(root, env), "workflow_release_package_invalid")
    perform("workflow_connection_profiles", lambda: _workflow_profiles(root), "workflow_connection_profile_or_release_invalid")
    if state_config is None:
        checks.append({"name": "system_state_config", "status": "skip", "code": "explicit_state_config_not_provided"})
    else:
        perform("system_state_config", lambda: _state_config(Path(state_config)), "system_state_config_invalid")
    deployment = root / "handover/deployment.json"
    if deployment.exists():
        perform("deployment_database_config", lambda: _deployment_database(deployment), "deployment_database_config_invalid")
    if runtime_root is None:
        checks.append({"name": "node_nodered_runtime", "status": "skip", "code": "explicit_runtime_root_not_provided"})
    else:
        perform("node_nodered_runtime", lambda: _runtime(Path(runtime_root)), "node_nodered_runtime_invalid")
    checks.append({"name": "windows_ch340_driver", **_driver_inventory()})
    counts = {state: sum(item["status"] == state for item in checks) for state in ("pass", "fail", "skip")}
    return {"ok": counts["fail"] == 0, "checks": checks, "counts": counts,
            "readOnly": True, "hardwareTested": False, "servicesStarted": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--state-config", type=Path)
    parser.add_argument("--runtime-root", type=Path)
    args = parser.parse_args(argv)
    result = check(args.repo_root, args.state_config, args.runtime_root)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
