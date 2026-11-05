"""Snapshot the installed WCH CH340/341 Windows-x64 driver; never install it.

Export is explicit and requires a new output directory. DriverStore discovery
and catalog signature checks are read-only. Installation is a command plan only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

MANIFEST = "driver-manifest.json"
INF_NAME = "ch341ser.inf"
MAX_FILE = 16 * 1024 * 1024
LICENSE_NAMES = {"license", "license.txt", "license.md", "license.rtf", "copying", "copying.txt"}
PAYLOAD = re.compile(r"ch341[a-z0-9_]*\.(?:sys|dll)", re.IGNORECASE)


class DriverError(ValueError):
    """Only fixed safe codes, never arbitrary source contents or process output."""


def _require(value, code="driver_package_invalid"):
    if not value:
        raise DriverError(code)


def _linked(path):
    return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)


def _read(path, limit=MAX_FILE):
    _require(path.is_file() and not _linked(path) and 0 < path.stat().st_size <= limit)
    return path.read_bytes()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _run(args):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _catalog_signed(path):
    if os.name != "nt":
        return False
    # Never splice a path into script code. Use a child-only environment
    # variable; -Command argument splitting differs between PS5 and PS7.
    environment = os.environ.copy(); environment["PGL_HANDOVER_CATALOG_CHECK"] = str(path)
    windows = Path(environment.get("SystemRoot", r"C:\Windows"))
    native_shell = windows / "System32/WindowsPowerShell/v1.0/powershell.exe"
    # A PS7 launcher may export its incompatible PSModulePath into PS5. Use
    # native PS5 modules in this child only, leaving the caller unchanged.
    environment["PSModulePath"] = str(windows / "System32/WindowsPowerShell/v1.0/Modules")
    command = ("$ErrorActionPreference='Stop'; $s=Get-AuthenticodeSignature -LiteralPath "
               "$env:PGL_HANDOVER_CATALOG_CHECK; if($s.Status -eq 'Valid' -and $s.SignerCertificate)"
               "{'VALID'}else{'INVALID'}")
    result = subprocess.run([str(native_shell), "-NoProfile", "-NonInteractive", "-Command", command],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                            env=environment, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return result.returncode == 0 and result.stdout.strip() == "VALID"


def _sections(raw):
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig", errors="replace")
    result, current = {}, None
    for raw_line in text.splitlines():
        line = raw_line.split(";", 1)[0].strip()
        if not line:
            continue
        section = re.fullmatch(r"\[([^\]]+)\]", line)
        if section:
            current = section[1].lower()
            _require(current not in result)
            result[current] = []
        elif current is not None:
            result[current].append(line)
    return result


def _values(sections, section, key):
    return [line.split("=", 1)[1].strip() for line in sections.get(section.lower(), [])
            if "=" in line and line.split("=", 1)[0].strip().lower() == key.lower()]


def _inspect(source):
    _require(source.is_dir() and not _linked(source))
    leaves = {}
    for path in source.iterdir():
        _require(not _linked(path))
        if path.is_file():
            _require(path.name.lower() not in leaves)
            leaves[path.name.lower()] = path
    _require(INF_NAME in leaves)
    sections = _sections(_read(leaves[INF_NAME], 1024 * 1024))
    catalog = _values(sections, "version", "catalogfile")
    _require(len(catalog) == 1 and catalog[0].lower() == "ch341ser.cat" and "ch341ser.cat" in leaves)
    version = _values(sections, "version", "driverver")
    _require(len(version) == 1 and re.fullmatch(r"\d{2}/\d{2}/\d{4}\s*,\s*\d+(?:\.\d+){1,4}", version[0]))
    drivers = sections.get("winchiphead.ntamd64", [])
    installs = set()
    for line in drivers:
        if re.search(r"USB\\VID_1A86&PID_(?:7523|5523|7522|E523)", line, re.IGNORECASE):
            _require("=" in line)
            installs.add(line.split("=", 1)[1].split(",", 1)[0].strip().lower())
    _require(bool(installs))
    names = {INF_NAME, "ch341ser.cat"}
    for install in installs:
        copy_sections = _values(sections, install, "copyfiles")
        _require(bool(copy_sections))
        for value in copy_sections:
            for section in value.split(","):
                section = section.strip().lower()
                if section.startswith("@"):
                    entries = [section[1:]]
                else:
                    _require(section in sections)
                    entries = [line.split(",", 1)[0].strip() for line in sections[section]]
                for name in entries:
                    _require(PAYLOAD.fullmatch(name) is not None and name.lower() in leaves,
                             "driver_required_x64_payload_missing")
                    names.add(name.lower())
    _require(any(name.endswith(".sys") for name in names))
    names.update(name for name in leaves if name in LICENSE_NAMES)
    return {"files": {name: leaves[name] for name in sorted(names)}, "driverVersion": version[0].replace(" ", "")}


def discover_driver(driver_store=None):
    """Find matching signed-driver candidates; never open a device or install."""
    if driver_store is None:
        _require(os.name == "nt", "windows_driver_store_unavailable")
        driver_store = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/DriverStore/FileRepository"
    store = Path(driver_store)
    if not store.is_dir():
        return []
    result = []
    for source in sorted(store.glob("ch341ser.inf_*")):
        try:
            package = _inspect(source)
            result.append({"sourcePath": str(source.resolve()), "infName": INF_NAME,
                           "provider": "WCH", "architecture": "windows-x64",
                           "driverVersion": package["driverVersion"], "fileCount": len(package["files"])})
        except (OSError, ValueError):
            continue
    return result


def published_driver_names():
    """PnPUtil read-only supplementary inventory; no raw localized text exposed."""
    if os.name != "nt":
        return []
    try:
        result = _run(["pnputil.exe", "/enum-drivers"])
        if result.returncode:
            return []
        names = set()
        for block in re.split(r"\r?\n\s*\r?\n", result.stdout):
            if re.search(r"\bch341ser\.inf\b", block, re.IGNORECASE):
                names.update(match.lower() for match in re.findall(r"\boem\d+\.inf\b", block, re.IGNORECASE))
        return sorted(names)
    except (OSError, subprocess.TimeoutExpired):
        return []


def export_driver(output, source=None, driver_store=None):
    """Copy only this vendor package into a NEW directory; never install it."""
    output = Path(output).absolute()
    _require(not output.exists(), "driver_output_must_be_new")
    if source is None:
        candidates = discover_driver(driver_store)
        _require(len(candidates) == 1, "driver_source_missing_or_ambiguous")
        source = candidates[0]["sourcePath"]
    package = _inspect(Path(source))
    _require(_catalog_signed(package["files"]["ch341ser.cat"]), "driver_catalog_signature_not_verified")
    manifest = {"schemaVersion": 1, "packageType": "wch-ch340-ch341-driver", "architecture": "windows-x64",
                "provider": "WCH", "driverVersion": package["driverVersion"], "infName": INF_NAME,
                "catalogSignatureVerifiedAtExport": True, "files": []}
    blobs = {}
    for name, path in package["files"].items():
        raw = _read(path); blobs[name] = raw
        manifest["files"].append({"path": name, "size": len(raw), "sha256": _sha(raw)})
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pgl-driver-export-", dir=output.parent) as stage:
        payload = Path(stage) / "payload"; payload.mkdir()
        for name, raw in blobs.items():
            (payload / name).write_bytes(raw)
        (payload / MANIFEST).write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        validate_driver(payload / MANIFEST)
        _require(not output.exists(), "driver_output_must_be_new")
        payload.rename(output)
    return manifest


def validate_driver(manifest_path):
    """Check all hashes and required x64 INF references without installing."""
    manifest_path = Path(manifest_path)
    manifest = json.loads(_read(manifest_path, 1024 * 1024).decode("utf-8-sig"))
    _require(isinstance(manifest, dict) and manifest.get("schemaVersion") == 1 and
             manifest.get("packageType") == "wch-ch340-ch341-driver" and
             manifest.get("architecture") == "windows-x64" and manifest.get("provider") == "WCH" and
             manifest.get("infName") == INF_NAME and manifest.get("catalogSignatureVerifiedAtExport") is True)
    files = manifest.get("files")
    _require(isinstance(files, list) and 3 <= len(files) <= 30)
    names = set()
    for item in files:
        _require(isinstance(item, dict))
        name = item.get("path")
        _require(isinstance(name, str) and name == name.lower() and name not in names and
                 (name in {INF_NAME, "ch341ser.cat"} | LICENSE_NAMES or PAYLOAD.fullmatch(name) is not None))
        names.add(name)
        _require(type(item.get("size")) is int and 0 < item["size"] <= MAX_FILE and
                 isinstance(item.get("sha256"), str) and re.fullmatch(r"[a-f0-9]{64}", item["sha256"]))
        raw = _read(manifest_path.parent / name)
        _require(len(raw) == item["size"] and _sha(raw) == item["sha256"], "driver_payload_hash_mismatch")
    package = _inspect(manifest_path.parent)
    _require(set(package["files"]) == names and package["driverVersion"] == manifest.get("driverVersion"))
    _require(all(path.is_file() and not _linked(path) for path in manifest_path.parent.iterdir()),
             "driver_extra_payload_refused")
    actual_files = {path.name.lower() for path in manifest_path.parent.iterdir()}
    _require(actual_files == names | {manifest_path.name.lower()}, "driver_extra_payload_refused")
    return manifest


def install_command_plan(manifest_path):
    """Return an explicit administrator command; this function never executes it."""
    validate_driver(manifest_path)
    inf = Path(manifest_path).absolute().parent / INF_NAME
    _require(_catalog_signed(inf.parent / "ch341ser.cat"), "driver_catalog_signature_not_verified")
    return ["pnputil.exe", "/add-driver", str(inf), "/install"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--discover", action="store_true")
    mode.add_argument("--export", type=Path, metavar="NEW_DIRECTORY")
    mode.add_argument("--validate", type=Path, metavar="MANIFEST")
    mode.add_argument("--install-plan", type=Path, metavar="MANIFEST")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--driver-store", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.discover:
            result = {"candidates": discover_driver(args.driver_store), "publishedInfNames": published_driver_names()}
        elif args.export:
            manifest = export_driver(args.export, args.source, args.driver_store)
            result = {"status": "PASS", "fileCount": len(manifest["files"]), "architecture": "windows-x64"}
        elif args.validate:
            manifest = validate_driver(args.validate)
            result = {"status": "PASS", "fileCount": len(manifest["files"]), "architecture": "windows-x64"}
        else:
            result = {"command": install_command_plan(args.install_plan), "executed": False, "administratorRequired": True}
        print(json.dumps(result, sort_keys=True)); return 0
    except Exception as error:
        code = str(error) if isinstance(error, DriverError) else "driver_operation_failed"
        print(json.dumps({"status": "BLOCKED", "code": code, "installed": False})); return 1


if __name__ == "__main__":
    raise SystemExit(main())
