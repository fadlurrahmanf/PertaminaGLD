"""Offline, nonsecret Node/Node-RED distribution snapshot and checked extraction.

Only explicitly selected distribution trees are read. This tool never snapshots
the Node-RED user profile, starts services, opens a DB or accesses the network.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile

SCHEMA = 1
MAX_PART = 90 * 1024 * 1024
MAX_FILE = 512 * 1024 * 1024
MAX_TOTAL = 4 * 1024 * 1024 * 1024
MAX_ENTRIES = 100000
MANIFEST = "runtime-manifest.json"
EXCLUDED_DIRS = {".git", ".cache", "__pycache__", "logs", ".npm"}
EXCLUDED_FILES = {".npmrc", ".npm-token", ".npm_token", "credentials.local.json",
                  "flows_cred.json", "settings.local.js", "startup.local.json",
                  "credentials.json", "credentials.yaml", "credentials.yml", "token.json", "tokens.json",
                  ".node_repl_history", ".bash_history", ".python_history", "history.json"}
RESERVED = {"con", "prn", "aux", "nul", *[f"com{i}" for i in range(1, 10)],
            *[f"lpt{i}" for i in range(1, 10)]}


class RuntimeErrorSafe(ValueError):
    """Fixed public errors contain no arbitrary file contents or process output."""


def _require(condition, message):
    if not condition:
        raise RuntimeErrorSafe(message)


def _reparse(path):
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _excluded(path):
    name = path.name.lower()
    return (name in EXCLUDED_FILES or name.startswith(".env") or
            name.endswith((".log", ".key", ".pem", ".pfx", ".p12")))


def _safe_relative(value):
    _require(isinstance(value, str) and value and not any(ord(c) < 32 or c in '\\:<>"|?*' for c in value),
             "Unsafe archive path")
    parts = value.split("/")
    _require(not value.startswith("/") and all(part not in ("", ".", "..") and
             part == part.rstrip(" .") and part.split(".")[0].lower() not in RESERVED for part in parts),
             "Unsafe archive path")
    return PurePosixPath(value)


def _walk(root):
    _require(root.is_dir() and not _reparse(root), "Distribution directory unavailable or linked")
    result = []
    for current, dirs, files in os.walk(root, followlinks=False):
        base = Path(current)
        allowed = []
        for name in sorted(dirs):
            child = base / name
            _require(not _reparse(child), "Linked distribution directory refused")
            if name.lower() not in EXCLUDED_DIRS:
                allowed.append(name)
        dirs[:] = allowed
        for name in sorted(files):
            path = base / name
            _require(not _reparse(path), "Linked distribution file refused")
            if not _excluded(path):
                _require(path.is_file(), "Nonregular distribution file refused")
                result.append(path)
    return result


def _package(path):
    _require(path.is_file() and not _reparse(path) and path.stat().st_size <= 1024 * 1024,
             "Package metadata unavailable")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    _require(isinstance(data, dict) and isinstance(data.get("name"), str) and
             isinstance(data.get("version"), str), "Invalid package metadata")
    return {key: data[key] for key in ("name", "version")}


def _node_version(node):
    result = subprocess.run([str(node), "--version"], capture_output=True, text=True,
                            timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    version = result.stdout.strip().removeprefix("v")
    _require(result.returncode == 0 and re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", version),
             "Node version could not be verified")
    return version


def _top_packages(root):
    if root is None or not root.is_dir():
        return []
    packages = []
    for child in sorted(root.iterdir()):
        if child.name.startswith(".") or not child.is_dir():
            continue
        candidates = sorted(child.iterdir()) if child.name.startswith("@") else [child]
        for candidate in candidates:
            if candidate.is_dir() and (candidate / "package.json").is_file():
                packages.append(_package(candidate / "package.json"))
    return packages


def inventory(node_exe, node_red, user_modules=None):
    node, red = Path(node_exe).absolute(), Path(node_red).absolute()
    modules = Path(user_modules).absolute() if user_modules is not None else None
    _require(node.is_file() and not _reparse(node), "Node executable unavailable or linked")
    entries = [("node/node.exe", node)]
    for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "README.md"):
        candidate = node.parent / name
        if candidate.is_file():
            _require(not _reparse(candidate), "Linked Node distribution file refused")
            entries.append(("node/" + name, candidate))
    entries += [("node-red/" + p.relative_to(red).as_posix(), p) for p in _walk(red)]
    if modules is not None and modules.exists():
        entries += [("user-node_modules/" + p.relative_to(modules).as_posix(), p) for p in _walk(modules)]
    entries.sort(key=lambda item: item[0])
    names = [name for name, _ in entries]
    for name in names:
        _safe_relative(name)
    _require(len(entries) <= MAX_ENTRIES and len({name.casefold() for name in names}) == len(names),
             "Distribution paths conflict")
    _require(all(p.stat().st_size <= MAX_FILE for _, p in entries), "Distribution file too large")
    total = sum(p.stat().st_size for _, p in entries)
    _require(total <= MAX_TOTAL, "Distribution snapshot too large")
    package = _package(red / "package.json")
    _require(package["name"] == "node-red", "Selected directory is not Node-RED")
    meta = dict(nodeVersion=_node_version(node), nodeRedVersion=package["version"],
                userPackages=_top_packages(modules), fileCount=len(entries), totalBytes=total,
                layout=dict(node="node/node.exe", nodeRed="node-red/red.js", userModules="user-node_modules"))
    return meta, entries


def _hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _empty_destination(path):
    _require(not path.is_symlink(), "Destination must not be linked")
    _require(not path.exists() or (path.is_dir() and not _reparse(path) and not any(path.iterdir())),
             "Destination must be new or empty; existing runtime is preserved")
    _require(all(not parent.exists() or not _reparse(parent) for parent in path.parents),
             "Destination parent must not be linked")


def export_runtime(node_exe, node_red, user_modules, output, *, max_part_bytes=MAX_PART):
    output = Path(output).absolute()
    _empty_destination(output)
    _require(type(max_part_bytes) is int and 64 <= max_part_bytes <= MAX_PART, "Invalid part size")
    for source in (node_red, user_modules):
        if source is not None:
            _require(not output.is_relative_to(Path(source).resolve()), "Output must be outside distribution sources")
    meta, entries = inventory(node_exe, node_red, user_modules)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="handover-export-", dir=output.parent) as staging:
        stage = Path(staging); archive = stage / "payload.zip"; files = []
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
            for name, source in entries:
                before = source.stat()
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED; info.external_attr = (stat.S_IFREG | 0o644) << 16
                digest = hashlib.sha256(); size = 0
                with source.open("rb") as read, zipped.open(info, "w") as write:
                    for chunk in iter(lambda: read.read(1024 * 1024), b""):
                        digest.update(chunk); size += len(chunk); write.write(chunk)
                after = source.stat()
                _require(before.st_size == after.st_size == size and before.st_mtime_ns == after.st_mtime_ns,
                         "Distribution changed during snapshot")
                files.append(dict(path=name, size=size, sha256=digest.hexdigest()))
        stem = f"node-{meta['nodeVersion']}-nodered-{meta['nodeRedVersion']}.zip"
        _safe_relative(stem)
        parts = []
        with archive.open("rb") as read:
            index = 1
            while chunk := read.read(max_part_bytes):
                name = f"{stem}.{index:03d}"; (stage / name).write_bytes(chunk)
                parts.append(dict(path=name, size=len(chunk), sha256=hashlib.sha256(chunk).hexdigest())); index += 1
        manifest = dict(schemaVersion=SCHEMA, kind="pertamina-gld-offline-runtime", runtime=meta,
                        archiveSha256=_hash(archive), archiveSize=archive.stat().st_size, parts=parts, files=files)
        (stage / MANIFEST).write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        archive.unlink()
        # No existing runtime or artifact directory is overwritten.
        _empty_destination(output)
        if output.exists(): output.rmdir()
        stage.rename(output)
    return manifest


def extract_runtime(manifest_path, destination):
    manifest_path, destination = Path(manifest_path).absolute(), Path(destination).absolute()
    _empty_destination(destination)
    _require(manifest_path.is_file() and manifest_path.stat().st_size <= 32 * 1024 * 1024,
             "Runtime manifest unavailable")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _require(isinstance(manifest, dict) and type(manifest.get("schemaVersion")) is int and manifest.get("schemaVersion") == SCHEMA and
             manifest.get("kind") == "pertamina-gld-offline-runtime", "Invalid runtime manifest")
    files, parts = manifest.get("files"), manifest.get("parts")
    _require(isinstance(files, list) and 0 < len(files) <= MAX_ENTRIES and isinstance(parts, list) and
             0 < len(parts) <= 1000, "Invalid runtime manifest entries")
    expected, seen = {}, set()
    for item in files:
        _require(isinstance(item, dict) and set(item) == {"path", "size", "sha256"}, "Invalid file entry")
        name = str(_safe_relative(item["path"]))
        _require(name.split("/")[0] in ("node", "node-red", "user-node_modules") and "/" in name and
                 name.casefold() not in seen, "Runtime file paths conflict")
        seen.add(name.casefold()); expected[name] = item
        _require(type(item["size"]) is int and 0 <= item["size"] <= MAX_FILE and
                 isinstance(item["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]), "Invalid file checksum")
    _require(sum(item["size"] for item in files) <= MAX_TOTAL, "Runtime extraction too large")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="handover-extract-", dir=destination.parent) as staging:
        stage = Path(staging); archive = stage / "payload.zip"; payload = stage / "runtime"; payload.mkdir()
        with archive.open("wb") as write:
            part_names = set(); part_total = 0
            for item in parts:
                _require(isinstance(item, dict) and set(item) == {"path", "size", "sha256"}, "Invalid part entry")
                name = str(_safe_relative(item["path"]))
                _require("/" not in name and name.casefold() not in part_names and
                         type(item["size"]) is int and 0 < item["size"] <= MAX_PART, "Invalid runtime part")
                part_total += item["size"]
                _require(part_total <= MAX_TOTAL + 64 * 1024 * 1024, "Runtime archive too large")
                part_names.add(name.casefold()); source = manifest_path.parent / name
                _require(source.is_file() and not _reparse(source) and source.stat().st_size == item["size"] and
                         _hash(source) == item["sha256"], "Runtime part checksum differs")
                with source.open("rb") as read: shutil.copyfileobj(read, write)
        _require(archive.stat().st_size == manifest.get("archiveSize") and
                 _hash(archive) == manifest.get("archiveSha256"), "Runtime archive checksum differs")
        with zipfile.ZipFile(archive) as zipped:
            infos = zipped.infolist()
            _require(len(infos) == len(expected) and len({i.filename for i in infos}) == len(infos),
                     "Runtime archive entries differ")
            for info in infos:
                name = str(_safe_relative(info.filename)); item = expected.get(name)
                _require(item is not None and not info.is_dir() and not stat.S_ISLNK(info.external_attr >> 16) and
                         info.file_size == item["size"], "Runtime archive entry differs")
                target = payload.joinpath(*PurePosixPath(name).parts); target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256(); size = 0
                with zipped.open(info) as read, target.open("xb") as write:
                    for chunk in iter(lambda: read.read(1024 * 1024), b""):
                        size += len(chunk); _require(size <= item["size"], "Runtime entry exceeded size")
                        digest.update(chunk); write.write(chunk)
                _require(size == item["size"] and digest.hexdigest() == item["sha256"], "Runtime file checksum differs")
        (payload / "runtime-receipt.json").write_text(json.dumps(manifest["runtime"], sort_keys=True, indent=2) + "\n", encoding="utf-8")
        _empty_destination(destination)
        if destination.exists(): destination.rmdir()
        payload.rename(destination)
    return manifest["runtime"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inventory", action="store_true")
    mode.add_argument("--export", action="store_true")
    mode.add_argument("--extract", type=Path, metavar="MANIFEST")
    parser.add_argument("--node-exe", type=Path, default=Path("C:/Program Files/nodejs/node.exe"))
    parser.add_argument("--node-red", type=Path, default=Path(os.environ.get("APPDATA", "")) / "npm/node_modules/node-red")
    parser.add_argument("--user-modules", type=Path, default=Path.home() / ".node-red/node_modules")
    parser.add_argument("--skip-user-modules", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    try:
        if args.extract:
            _require(args.destination is not None, "Extraction requires explicit --destination")
            result = extract_runtime(args.extract, args.destination)
        elif args.export:
            _require(args.output is not None, "Export requires explicit --output")
            manifest = export_runtime(args.node_exe, args.node_red, None if args.skip_user_modules else args.user_modules, args.output)
            result = dict(status="PASS", runtime=manifest["runtime"], parts=len(manifest["parts"]))
        else:
            result, _ = inventory(args.node_exe, args.node_red, None if args.skip_user_modules else args.user_modules)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        message = str(error) if isinstance(error, RuntimeErrorSafe) else "Runtime inventory/archive validation failed"
        print(json.dumps(dict(status="BLOCKED", reason=message)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
