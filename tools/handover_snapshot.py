"""Snapshot explicitly approved GLD configuration, Node-RED state and history.

Secrets remain plaintext only because the operator explicitly selected that
handover format. This module never prints payloads, contacts services, opens a
database, changes originals, or restores into an active/existing data directory.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile

MANIFEST = "snapshot-manifest.json"
MAX_FILE = 512 * 1024 * 1024
MAX_TOTAL = 2 * 1024 * 1024 * 1024
MAX_FILES = 20000
PROFILE_FILES = (
    "settings.js", "flows.json", "flows_cred.json", ".config.runtime.json",
    "package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock",
    "pertamina-gld-replay-state.json", "pertamina-gld-topology-bootstrap.json",
)
PROFILE_DIRS = ("context", "pgl-context")
RESERVED = {"con", "prn", "aux", "nul", *[f"com{i}" for i in range(1, 10)],
            *[f"lpt{i}" for i in range(1, 10)]}


class SnapshotError(ValueError):
    """Fixed public messages deliberately omit secret values and local paths."""


def _require(condition, message):
    if not condition:
        raise SnapshotError(message)


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _linked(path):
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _safe_relative(value):
    _require(isinstance(value, str) and value and len(value) <= 600 and
             not any(ord(c) < 32 or c in '\\:<>"|?*' for c in value), "Unsafe snapshot path")
    parts = value.split("/")
    _require(not value.startswith("/") and all(
        part not in ("", ".", "..") and part == part.rstrip(" .") and
        part.split(".")[0].lower() not in RESERVED for part in parts), "Unsafe snapshot path")
    return PurePosixPath(value)


def _read(path):
    _require(path.is_file() and not _linked(path), "Snapshot source file unavailable or linked")
    before = path.stat()
    _require(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_FILE, "Snapshot source file too large or nonregular")
    raw = path.read_bytes()
    after = path.stat()
    _require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns) and
             len(raw) == before.st_size, "Snapshot source changed while reading")
    return raw


def _json(raw):
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError):
        raise SnapshotError("Invalid snapshot JSON") from None


def _env(raw):
    try:
        lines = raw.decode("utf-8-sig").splitlines()
    except UnicodeError:
        raise SnapshotError("Invalid server environment encoding") from None
    values = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        _require(separator and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) and key not in values,
                 "Invalid or duplicated server environment key")
        value = value.strip()
        # Match existing launcher's single-line dotenv semantics without eval.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def _new_target(path):
    path = Path(path).absolute()
    _require(all(not _linked(parent) for parent in (path, *path.parents) if os.path.lexists(parent)),
             "Snapshot destination must not be linked")
    path = path.resolve()
    if path.exists():
        _require(path.is_dir() and not _linked(path) and not any(path.iterdir()),
                 "Snapshot destination must be new or empty")
    path.parent.mkdir(parents=True, exist_ok=True)
    _require(not _linked(path.parent), "Snapshot destination parent must not be linked")
    return path


def _cleanup(stage, parent):
    # Only a freshly created, checked staging directory may be removed.
    absolute = stage.resolve()
    _require(absolute.parent == parent.resolve() and absolute.name.startswith(".gld-snapshot-"),
             "Unsafe staging cleanup")
    if stage.exists():
        shutil.rmtree(stage)


def _publish(stage, target):
    if target.exists():
        _require(not any(target.iterdir()), "Snapshot destination became nonempty")
        target.rmdir()  # Empty directory only; never remove user data.
    os.replace(stage, target)


def _walk_allowed(directory):
    _require(directory.is_dir() and not _linked(directory), "Node-RED state directory unavailable or linked")
    for current, dirs, names in os.walk(directory, followlinks=False):
        base = Path(current)
        for name in dirs:
            _require(not _linked(base / name), "Linked Node-RED state directory refused")
        dirs.sort()
        for name in sorted(names):
            path = base / name
            _require(not _linked(path), "Linked Node-RED state file refused")
            yield path


def _discovered_csv(repo, discovery):
    _require(discovery.is_file(), "Approved CSV discovery manifest missing")
    data = _json(_read(discovery))
    items = data.get("datasetCsvCandidates") if isinstance(data, dict) else None
    _require(isinstance(items, list), "Invalid approved CSV discovery manifest")
    paths, seen = [], set()
    for item in items:
        _require(isinstance(item, dict) and isinstance(item.get("path"), str), "Invalid approved CSV entry")
        path = Path(item["path"])
        if not path.is_absolute():
            path = repo / path
        _require(path.suffix.lower() == ".csv", "Approved history entry is not CSV")
        identity = str(path.absolute()).casefold()
        _require(identity not in seen, "Duplicate approved CSV source")
        seen.add(identity)
        paths.append(path)
    return sorted(paths, key=lambda p: str(p).casefold())


def _ledger_paths(repo):
    paths = []
    directory = repo / "apps/gld-operator/output/datasets"
    if directory.is_dir():
        paths.extend(sorted(directory.glob("*.jsonl")))
    output = repo / "output"
    if output.is_dir():
        for path in output.rglob("*.jsonl"):
            parts = [part.lower() for part in path.relative_to(output).parts]
            # Clean-checkout verification retains copied ledgers under output.
            # They are test artefacts, not additional history sources.
            if parts[0] == "handover-verification":
                continue
            if (any(part in {"datasets", "gld", "ledgers"} for part in parts[:-1]) or
                    re.search(r"^(?:workflow|gld|dataset)[_.-]|ledger", path.name, re.IGNORECASE)):
                paths.append(path)
    return sorted(set(paths), key=lambda p: str(p).casefold())


def _history_name(number, path):
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", path.name)
    _require(bool(name), "Invalid history filename")
    return f"{number:03d}-{name}"


def export_snapshot(repo_root, output, *, node_red_profile=None, csv_discovery=None):
    """Copy approved inputs into a NEW snapshot directory; originals unchanged.

    The source-PC Node-RED profile defaults to USERPROFILE/.node-red. A current,
    explicit CSV discovery manifest is required to avoid silently reusing a
    stale list of history files. Tests inject synthetic profile/discovery paths.
    """
    repo = Path(repo_root).resolve()
    profile = Path(node_red_profile) if node_red_profile is not None else Path.home() / ".node-red"
    _require(csv_discovery is not None, "Approved CSV discovery manifest required")
    discovery = Path(csv_discovery)
    target = _new_target(output)
    _require(not target.is_relative_to(profile.absolute()), "Snapshot destination overlaps Node-RED profile")
    stage = Path(tempfile.mkdtemp(prefix=".gld-snapshot-", dir=target.parent))
    records, source_hashes, names, total = [], {}, set(), 0

    def add(relative, raw, role, source=None):
        nonlocal total
        relative = str(_safe_relative(relative))
        _require(relative.casefold() not in names and relative != MANIFEST, "Duplicate snapshot output")
        names.add(relative.casefold())
        total += len(raw)
        _require(len(records) < MAX_FILES and total <= MAX_TOTAL, "Snapshot exceeds approved size limits")
        path = stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        record = dict(path=relative, size=len(raw), sha256=_hash(raw), role=role)
        if source is not None:
            record["sourcePath"] = str(source.absolute())
            source_hashes[source] = record["sha256"]
        records.append(record)

    def copy(source, relative, role):
        add(relative, _read(source), role, source)

    try:
        env_path = repo / "server/nodered/.env"
        env_raw = _read(env_path)
        server_env = _env(env_raw)
        broker_path = repo / "archive/apps/runtime/operator-hub/credentials.local.json"
        broker_raw = _read(broker_path)
        value = _json(broker_raw)
        _require(isinstance(value, dict), "Invalid canonical broker configuration")
        broker = {key: value.get(key) for key in ("host", "port", "username", "password")}
        _require(all(isinstance(broker[key], str) and broker[key] for key in ("host", "username", "password")) and
                 type(broker["port"]) is int and 1 <= broker["port"] <= 65535, "Invalid canonical broker configuration")
        system = dict(schemaVersion=1, storage="plaintext", serverEnv=server_env, broker=broker)
        add("config/system.json", (json.dumps(system, indent=2) + "\n").encode(), "canonical-system-config")
        copy(env_path, "config/source-server.env", "original-server-env")
        copy(broker_path, "config/source-broker.json", "original-broker-config")
        _require(_hash(env_raw) == _hash(_read(env_path)) and _hash(broker_raw) == _hash(_read(broker_path)),
                 "Source configuration changed while exporting")
        _require(profile.is_dir() and not _linked(profile), "Node-RED profile unavailable or linked")
        for name in PROFILE_FILES:
            source = profile / name
            if source.exists():
                copy(source, "nodered/" + name, "nodered-profile")
        for name in PROFILE_DIRS:
            directory = profile / name
            if directory.exists():
                for source in _walk_allowed(directory):
                    copy(source, "nodered/" + source.relative_to(profile).as_posix(), "nodered-context")
        for number, source in enumerate(_discovered_csv(repo, discovery), 1):
            copy(source, "history/csv/" + _history_name(number, source), "dataset-csv")
        for number, source in enumerate(_ledger_paths(repo), 1):
            copy(source, "history/ledger/" + _history_name(number, source), "dataset-ledger")
        for source, digest in source_hashes.items():
            _require(_hash(_read(source)) == digest, "Snapshot source changed before publication")
        manifest = dict(schemaVersion=1, storage="plaintext", createdAt=dt.datetime.now().astimezone().isoformat(),
                        files=records, totalBytes=total)
        (stage / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        validate_snapshot(stage)
        _publish(stage, target)
        return dict(files=len(records), totalBytes=total,
                    csvFiles=sum(item["role"] == "dataset-csv" for item in records),
                    ledgerFiles=sum(item["role"] == "dataset-ledger" for item in records),
                    storage="plaintext", originalSourcesUnchanged=True)
    finally:
        if stage.exists():
            _cleanup(stage, target.parent)


def validate_snapshot(snapshot):
    """Validate all manifest-listed bytes and refuse extra/path-linked files."""
    snapshot = Path(snapshot).absolute()
    _require(snapshot.is_dir() and not _linked(snapshot), "Snapshot directory unavailable or linked")
    raw = _read(snapshot / MANIFEST)
    manifest = _json(raw)
    _require(isinstance(manifest, dict) and manifest.get("schemaVersion") == 1 and
             manifest.get("storage") == "plaintext" and isinstance(manifest.get("files"), list), "Invalid snapshot manifest")
    names, total = set(), 0
    _require(0 < len(manifest["files"]) <= MAX_FILES, "Invalid snapshot file count")
    for item in manifest["files"]:
        _require(isinstance(item, dict), "Invalid snapshot file record")
        relative = str(_safe_relative(item.get("path")))
        _require(relative.startswith(("config/", "nodered/", "history/csv/", "history/ledger/")), "Unsupported snapshot path")
        _require(relative.casefold() not in names, "Duplicate snapshot path")
        names.add(relative.casefold())
        _require(type(item.get("size")) is int and 0 <= item["size"] <= MAX_FILE and
                 isinstance(item.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]), "Invalid snapshot checksum record")
        path = snapshot / relative
        _require(all(parent.exists() and not _linked(parent) for parent in path.parents if parent != snapshot and parent.is_relative_to(snapshot)),
                 "Linked snapshot directory refused")
        content = _read(path)
        _require(len(content) == item["size"] and _hash(content) == item["sha256"], "Snapshot checksum mismatch")
        total += len(content)
        _require(total <= MAX_TOTAL, "Snapshot exceeds approved size limits")
    _require(total == manifest.get("totalBytes") and "config/system.json" in names, "Snapshot totals or system configuration missing")
    actual = {path.relative_to(snapshot).as_posix().casefold() for path in _walk_allowed(snapshot)}
    _require(actual == names | {MANIFEST}, "Unlisted snapshot files refused")
    return manifest


def restore(snapshot, destination):
    """Restore into a NEW/empty target only; never modify live repo/profile."""
    snapshot = Path(snapshot).absolute()
    manifest = validate_snapshot(snapshot)
    target = _new_target(destination)
    _require(not target.is_relative_to(snapshot) and not snapshot.is_relative_to(target), "Restore destination overlaps snapshot")
    stage = Path(tempfile.mkdtemp(prefix=".gld-snapshot-", dir=target.parent))
    try:
        for item in manifest["files"]:
            relative = str(_safe_relative(item["path"]))
            raw = _read(snapshot / relative)
            _require(len(raw) == item["size"] and _hash(raw) == item["sha256"], "Snapshot changed while restoring")
            path = stage / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        path = stage / "config/system.json"
        system = _json(path.read_bytes())
        _require(isinstance(system, dict) and system.get("schemaVersion") == 1 and
                 system.get("storage") == "plaintext" and isinstance(system.get("serverEnv"), dict), "Invalid canonical system configuration")
        env = system["serverEnv"]
        if "PGL_REPLAY_STATE_PATH" in env:
            env["PGL_REPLAY_STATE_PATH"] = str(target / "nodered/pertamina-gld-replay-state.json")
        for key in ("PGL_FIELD_TEST_LOG_DIR", "FIELD_TEST_LOG_DIR"):
            if key in env:
                env[key] = str(target / "history/field-test-logs")
                (stage / "history/field-test-logs").mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(system, indent=2) + "\n", encoding="utf-8")
        (stage / "source-snapshot-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        _publish(stage, target)
        return dict(restoredFiles=len(manifest["files"]), storage="plaintext", sourceSnapshotUnchanged=True,
                    serverEnvPathsRebased=True)
    finally:
        if stage.exists():
            _cleanup(stage, target.parent)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    export = commands.add_parser("export")
    export.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--node-red-profile", type=Path)
    export.add_argument("--csv-discovery", type=Path, required=True)
    check = commands.add_parser("check"); check.add_argument("snapshot", type=Path)
    recover = commands.add_parser("restore"); recover.add_argument("snapshot", type=Path); recover.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        if args.operation == "export":
            result = export_snapshot(args.repo_root, args.output, node_red_profile=args.node_red_profile, csv_discovery=args.csv_discovery)
        elif args.operation == "check":
            manifest = validate_snapshot(args.snapshot)
            result = dict(files=len(manifest["files"]), totalBytes=manifest["totalBytes"], valid=True)
        else:
            result = restore(args.snapshot, args.destination)
        print(json.dumps(dict(status="PASS", **result)))
        return 0
    except Exception as error:
        # Only fixed validation messages are safe to print, never arbitrary I/O
        # exceptions, original data, private paths or credential values.
        reason = str(error) if isinstance(error, SnapshotError) else "Snapshot operation failed; inspect local inputs privately"
        print(json.dumps(dict(status="BLOCKED", reason=reason)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
