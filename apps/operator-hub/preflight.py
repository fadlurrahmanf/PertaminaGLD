"""Offline readiness checks used before Operator Hub launches its child apps.

The checks are intentionally read-only.  They never download software, install a
driver, open a serial port, or write firmware.  A missing upload dependency does
not prevent the dashboard from opening; it only marks firmware flashing as not
ready.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HUB_DIR = Path(__file__).resolve().parent
APPS_DIR = HUB_DIR.parent
LIB_DIR = APPS_DIR / "lib"
FIRMWARE_PACKAGES_DIR = HUB_DIR / "firmware-packages"
REQUIRED_ENVIRONMENTS = ("gld", "gldFieldtest", "ch", "chFieldtest", "gw")


def find_esptool_entry() -> Path | None:
    """Return an explicitly shared, local esptool entry point if present."""
    for candidate in (
        LIB_DIR / "esptool" / "esptool.py",
        LIB_DIR / "esptool-master" / "esptool.py",
    ):
        if candidate.is_file():
            return candidate
    return None


def _esptool_check(python_exe: Path, entry: Path | None) -> dict[str, str]:
    if entry is None:
        return _check("esptool", "Shared ESPTool", "warn", "No esptool found in apps/lib; portable raw flashing is unavailable.")
    if not python_exe.is_file():
        return _check("esptool", "Shared ESPTool", "warn", f"Found {entry.relative_to(APPS_DIR)}, but no embedded CH Python runtime is available to run it.")
    runner = LIB_DIR / "run_esptool.py"
    if not runner.is_file():
        return _check("esptool", "Shared ESPTool", "warn", f"Found {entry.relative_to(APPS_DIR)}, but apps/lib/run_esptool.py is missing.")
    try:
        probe = subprocess.run(
            [str(python_exe), str(runner), "version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _check("esptool", "Shared ESPTool", "warn", f"Found {entry.relative_to(APPS_DIR)}, but its runtime check failed: {exc}")
    if probe.returncode == 0:
        lines = [line.strip() for line in probe.stdout.splitlines() if line.strip()]
        version = lines[-1] if lines else "unknown version"
        return _check("esptool", "Shared ESPTool", "ok", f"{entry.relative_to(APPS_DIR)} is runnable (v{version}).")
    failure = next((line.strip() for line in reversed(probe.stderr.splitlines()) if line.strip()), "unknown import error")
    return _check("esptool", "Shared ESPTool", "warn", f"Found {entry.relative_to(APPS_DIR)}, but its bundled Python dependencies are incomplete: {failure}")


def _check(check_id: str, label: str, state: str, detail: str) -> dict[str, str]:
    return {"id": check_id, "label": label, "state": state, "detail": detail}


def _port_available(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
        return True
    except OSError:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_manifest(manifest_path: Path) -> None:
    """Raise ValueError/OSError/... if this package's manifest or files don't check out."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    flash_files = manifest.get("flashFiles")
    if not isinstance(flash_files, list) or not flash_files:
        raise ValueError("manifest has no flashFiles entries")
    for item in flash_files:
        path = manifest_path.parent / str(item["path"])
        if not path.is_file() or path.stat().st_size != int(item["size"]):
            raise ValueError(f"{item['path']} is missing or the wrong size")
        if _sha256(path) != str(item["sha256"]).lower():
            raise ValueError(f"{item['path']} hash mismatch")


def _firmware_packages_check() -> dict[str, str]:
    if not FIRMWARE_PACKAGES_DIR.is_dir():
        return _check(
            "firmware-packages",
            "Firmware packages",
            "error",
            "No offline release package directory; firmware upload is disabled for all environments.",
        )

    broken: dict[str, str] = {}
    for env in REQUIRED_ENVIRONMENTS:
        env_dir = FIRMWARE_PACKAGES_DIR / env
        manifests = sorted(env_dir.rglob("manifest.json")) if env_dir.is_dir() else []
        if not manifests:
            broken[env] = "no package found"
            continue
        last_error = "unknown error"
        for manifest_path in manifests:
            try:
                _verify_manifest(manifest_path)
                break
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                last_error = str(exc) or type(exc).__name__
        else:
            broken[env] = last_error

    if not broken:
        return _check(
            "firmware-packages", "Firmware packages", "ok",
            f"All {len(REQUIRED_ENVIRONMENTS)} environments have a verified offline package.",
        )
    detail = "; ".join(f"{env}: {reason}" for env, reason in sorted(broken.items()))
    return _check("firmware-packages", "Firmware packages", "error", f"Do not flash - {detail}.")


def _ch340_driver_check() -> dict[str, str]:
    pnputil = shutil.which("pnputil.exe") or shutil.which("pnputil")
    if not pnputil:
        return _check("ch340-driver", "CH340 driver", "warn", "Windows PnPUtil is unavailable; driver state cannot be checked.")
    try:
        result = subprocess.run([pnputil, "/enum-drivers"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _check("ch340-driver", "CH340 driver", "warn", f"Driver Store scan failed: {exc}")
    listing = result.stdout.lower()
    if "ch341ser.inf" in listing and "wch.cn" in listing:
        return _check("ch340-driver", "CH340 driver", "ok", "WCH CH340/CH341 package is installed in the Windows Driver Store.")
    return _check("ch340-driver", "CH340 driver", "warn", "CH340/CH341 package is not installed; it is required only for hardware that identifies as CH340.")


def run_preflight(host: str = "127.0.0.1", hub_port: int = 5173) -> dict[str, Any]:
    """Return a JSON-safe startup report without mutating the host system."""
    checks: list[dict[str, str]] = []
    python_ok = sys.version_info >= (3, 9)
    checks.append(_check(
        "hub-runtime", "Hub Python runtime", "ok" if python_ok else "error",
        f"{Path(sys.executable).name} {sys.version.split()[0]}" if python_ok else "Python 3.9 or newer is required.",
    ))

    ch_python = APPS_DIR / "ch-operator" / "python-embed" / "python.exe"
    checks.append(_check(
        "ch-runtime", "CH Operator runtime", "ok" if ch_python.is_file() else "warn",
        "Bundled CH Python runtime found." if ch_python.is_file() else "CH embedded Python is missing; CH serial and flash features may be unavailable.",
    ))

    checks.append(_esptool_check(ch_python, find_esptool_entry()))
    checks.append(_firmware_packages_check())
    checks.append(_ch340_driver_check())

    hub_port_free = _port_available(host, hub_port)
    checks.append(_check(
        "hub-port", "Operator Hub port", "ok" if hub_port_free else "error",
        f"{host}:{hub_port} is available." if hub_port_free else f"{host}:{hub_port} is already in use; close the existing Hub process or open its current URL.",
    ))
    for name, port in (("GLD", 5174), ("CH", 5273), ("Gateway", 5373)):
        checks.append(_check(
            f"{name.lower()}-port", f"{name} bridge port", "ok" if _port_available(host, port) else "warn",
            f"{host}:{port} is available." if _port_available(host, port) else f"{host}:{port} is occupied; it may be an already-running bridge.",
        ))

    states = {check["id"]: check["state"] for check in checks}
    ready_for_flash = all(states.get(check_id) == "ok" for check_id in ("hub-runtime", "ch-runtime", "esptool", "firmware-packages"))
    return {
        "checkedAtUtc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checks": checks,
        "readyForFlash": ready_for_flash,
        "errorCount": sum(check["state"] == "error" for check in checks),
        "warningCount": sum(check["state"] == "warn" for check in checks),
    }


def print_report(report: dict[str, Any]) -> None:
    for check in report["checks"]:
        print(f"HUB_PREFLIGHT_{check['state'].upper()} {check['id']}: {check['detail']}")
