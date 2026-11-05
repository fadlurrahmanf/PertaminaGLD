"""Portable MariaDB distribution and isolated history-reconstruction database.

No source database is queried or dumped. Live data/backup directories are never
packaged. Runtime lifecycle functions operate only on processes started here,
on a dedicated loopback port other than3306 and a tool-owned data directory.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
from ctypes import wintypes
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile

# Windows embedded Python does not add the invoked script directory to sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import handover_runtime as archive_util

MANIFEST = "database-runtime-manifest.json"
OWNER = "handover-database-owner.json"
MAX_PART = archive_util.MAX_PART
_OWNED = {}


def require(condition, message):
    archive_util._require(condition, message)


def _version(source):
    result = subprocess.run([str(source / "bin/mysqld.exe"), "--version"], capture_output=True, timeout=20)
    match = re.search(rb"(\d+\.\d+\.\d+)-MariaDB", result.stdout)
    require(result.returncode == 0 and match is not None, "MariaDB distribution version unavailable")
    return match.group(1).decode("ascii")


def export_runtime(source, output):
    source, output = Path(source).absolute(), Path(output).absolute()
    archive_util._empty_destination(output)
    require(not output.is_relative_to(source.resolve()), "Output must be outside MariaDB distribution")
    entries = []
    for directory in ("bin", "lib", "share"):
        base = source / directory
        if base.exists():
            for path in archive_util._walk(base):
                if path.suffix.lower() not in (".ini", ".cnf"):
                    entries.append((directory + "/" + path.relative_to(base).as_posix(), path))
    for path in sorted(source.iterdir()):
        if path.is_file() and path.name.upper().startswith(("COPYING", "LICENSE", "NOTICE", "THIRDPARTY", "CREDITS")):
            require(not archive_util._reparse(path), "Linked license refused")
            entries.append(("licenses/" + path.name, path))
    names = {name for name, _ in entries}
    require(all("bin/" + name in names for name in ("mysqld.exe", "mysql.exe", "mysqladmin.exe", "mysql_install_db.exe")),
            "MariaDB distribution binaries unavailable")
    require(any(name.startswith("share/") for name in names), "MariaDB shared bootstrap files unavailable")
    require(len(names) == len(entries) and len({n.casefold() for n in names}) == len(names), "MariaDB distribution paths conflict")
    version = _version(source); output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="database-export-", dir=output.parent) as temporary:
        stage = Path(temporary); zipped_path = stage / "payload.zip"; files = []
        with zipfile.ZipFile(zipped_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
            for name, path in sorted(entries):
                archive_util._safe_relative(name); before = path.stat()
                require(before.st_size <= archive_util.MAX_FILE, "MariaDB distribution file too large")
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                digest = hashlib.sha256(); size = 0
                with path.open("rb") as read, zipped.open(info, "w") as write:
                    for chunk in iter(lambda: read.read(1024 * 1024), b""):
                        size += len(chunk); require(size <= archive_util.MAX_FILE, "Distribution grew during snapshot")
                        digest.update(chunk); write.write(chunk)
                after = path.stat()
                require(before.st_size == size == after.st_size and before.st_mtime_ns == after.st_mtime_ns,
                        "MariaDB distribution changed during snapshot")
                files.append(dict(path=name, size=size, sha256=digest.hexdigest()))
        parts = []
        with zipped_path.open("rb") as read:
            index = 1
            while chunk := read.read(MAX_PART):
                name = f"mariadb-{version}-windows-x64.zip.{index:03d}"; (stage / name).write_bytes(chunk)
                parts.append(dict(path=name, size=len(chunk), sha256=hashlib.sha256(chunk).hexdigest())); index += 1
        manifest = dict(schemaVersion=1, kind="pertamina-gld-mariadb-runtime", version=version,
                        archiveSha256=archive_util._hash(zipped_path), archiveSize=zipped_path.stat().st_size,
                        parts=parts, files=files, excludes=["data", "backup", "configuration", "other databases"])
        (stage / MANIFEST).write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        zipped_path.unlink(); archive_util._empty_destination(output)
        if output.exists(): output.rmdir()
        stage.rename(output)
    return manifest


def extract_runtime(manifest, destination):
    """Reuse the already-tested archive admission after a constrained relabel."""
    manifest, destination = Path(manifest).absolute(), Path(destination).absolute()
    require(manifest.is_file() and manifest.stat().st_size <= 32 * 1024 * 1024, "Database runtime manifest unavailable")
    value = json.loads(manifest.read_text(encoding="utf-8"))
    require(value.get("kind") == "pertamina-gld-mariadb-runtime" and type(value.get("schemaVersion")) is int and
            value["schemaVersion"] == 1, "Invalid database runtime manifest")
    # The generic extractor's entry-prefix admission is intentionally narrow;
    # this adapter reconstructs and validates the MariaDB archive independently.
    archive_util._empty_destination(destination)
    files, parts = value.get("files"), value.get("parts")
    require(isinstance(files, list) and 0 < len(files) <= archive_util.MAX_ENTRIES and
            isinstance(parts, list) and 0 < len(parts) <= 1000, "Invalid database runtime entries")
    expected, seen = {}, set()
    for item in files:
        require(isinstance(item, dict) and set(item) == {"path", "size", "sha256"}, "Invalid database file entry")
        name = str(archive_util._safe_relative(item["path"]))
        require(name.split("/")[0] in ("bin", "lib", "share", "licenses") and "/" in name and
                name.casefold() not in seen and type(item["size"]) is int and 0 <= item["size"] <= archive_util.MAX_FILE,
                "Unsafe database runtime entry")
        seen.add(name.casefold()); expected[name] = item
    require(sum(i["size"] for i in files) <= archive_util.MAX_TOTAL, "Database runtime too large")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="database-extract-", dir=destination.parent) as temporary:
        stage = Path(temporary); archive = stage / "payload.zip"; payload = stage / "runtime"; payload.mkdir()
        names, total = set(), 0
        with archive.open("wb") as write:
            for item in parts:
                name = str(archive_util._safe_relative(item.get("path")))
                require("/" not in name and name.casefold() not in names and type(item.get("size")) is int and
                        0 < item["size"] <= MAX_PART, "Invalid database runtime part")
                names.add(name.casefold()); total += item["size"]
                require(total <= archive_util.MAX_TOTAL + 64 * 1024 * 1024, "Database archive too large")
                path = manifest.parent / name
                require(path.is_file() and not archive_util._reparse(path) and path.stat().st_size == item["size"] and
                        archive_util._hash(path) == item.get("sha256"), "Database runtime part checksum differs")
                with path.open("rb") as read: shutil.copyfileobj(read, write)
        require(archive.stat().st_size == value.get("archiveSize") and archive_util._hash(archive) == value.get("archiveSha256"),
                "Database runtime archive checksum differs")
        with zipfile.ZipFile(archive) as zipped:
            infos = zipped.infolist()
            require(len(infos) == len(expected) and len({i.filename for i in infos}) == len(infos), "Database ZIP entries differ")
            for info in infos:
                name = str(archive_util._safe_relative(info.filename)); item = expected.get(name)
                require(item is not None and not info.is_dir() and not stat.S_ISLNK(info.external_attr >> 16) and
                        info.file_size == item["size"], "Database ZIP entry differs")
                path = payload.joinpath(*PurePosixPath(name).parts); path.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256(); size = 0
                with zipped.open(info) as read, path.open("xb") as write:
                    for chunk in iter(lambda: read.read(1024 * 1024), b""):
                        size += len(chunk); require(size <= item["size"], "Database file exceeded size")
                        digest.update(chunk); write.write(chunk)
                require(size == item["size"] and digest.hexdigest() == item["sha256"], "Database file checksum differs")
        (payload / "runtime-receipt.json").write_text(json.dumps(dict(kind=value["kind"], version=value["version"])))
        archive_util._empty_destination(destination)
        if destination.exists(): destination.rmdir()
        payload.rename(destination)
    return dict(version=value["version"], files=len(files))


def _config(config):
    require(isinstance(config, dict) and all(isinstance(config.get(k), str) for k in ("name", "user", "password", "rootPassword")),
            "Database configuration incomplete")
    require(all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", config[k]) for k in ("name", "user")), "Invalid project database identity")
    require(all(config[k] and not any(c in config[k] for c in "\r\n\0") for k in ("password", "rootPassword")),
            "Database passwords must be nonempty single-line values")
    return config


def _port(port):
    require(type(port) is int and 1024 <= port <= 65535 and port != 3306, "An isolated database port other than3306 is required")
    return port


def _owner(data_dir):
    path = Path(data_dir).absolute(); require(path.is_dir() and not archive_util._reparse(path), "Database directory unavailable")
    receipt = path / OWNER
    require(receipt.is_file() and receipt.stat().st_size <= 16384, "Database directory is not owned by handover tool")
    value = json.loads(receipt.read_text())
    require(value.get("kind") == "pertamina-gld-isolated-database" and value.get("dataDir") == str(path.resolve()),
            "Database ownership receipt differs")
    return path, value


def initialize(runtime_dir, data_dir, config, port=33306):
    _config(config); _port(port); runtime_dir, data_dir = Path(runtime_dir).absolute(), Path(data_dir).absolute()
    archive_util._empty_destination(data_dir)
    require(not data_dir.is_relative_to(runtime_dir.resolve()), "Database data must be outside runtime distribution")
    installer = runtime_dir / "bin/mysql_install_db.exe"
    require(installer.is_file(), "MariaDB initializer unavailable")
    # MariaDB's Windows initializer requires a genuinely empty datadir. Keep
    # ownership and diagnostics beside that directory until bootstrap succeeds.
    # An existing reservation prevents an unknown-result operation being retried.
    reservation = data_dir.with_name(data_dir.name + ".handover-initialization.json")
    diagnostics = data_dir.with_name(data_dir.name + ".initialization-diagnostics.log")
    require(not reservation.exists() and not diagnostics.exists() and not reservation.is_symlink() and not diagnostics.is_symlink(),
            "Initialization artifacts already exist; reconcile before retry")
    data_dir.mkdir(parents=True, exist_ok=True)
    owner = dict(kind="pertamina-gld-isolated-database", id=uuid.uuid4().hex, dataDir=str(data_dir.resolve()),
                 port=port, database=config["name"], initialized=False, rootProvisioned=False,
                 initializationState="reserved")
    with reservation.open("x", encoding="utf-8") as stream:
        json.dump(owner, stream, sort_keys=True, indent=2)
    try:
        with diagnostics.open("xb") as log:
            result = subprocess.run([str(installer), "--datadir=" + str(data_dir), "--port=" + str(port)],
                                    cwd=runtime_dir, stdout=log, stderr=subprocess.STDOUT, timeout=180,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        owner["initializerExitCode"] = int(result.returncode)
        require(result.returncode == 0 and (data_dir / "mysql").is_dir(), "DB_INITIALIZE_FAILED: inspect local initialization diagnostics; no automatic retry")
        owner["initialized"] = True; owner["initializationState"] = "complete"
        with (data_dir / OWNER).open("x", encoding="utf-8") as stream:
            json.dump(owner, stream, sort_keys=True, indent=2)
    except Exception:
        owner["initializationState"] = "failed"
        reservation.write_text(json.dumps(owner, sort_keys=True, indent=2), encoding="utf-8")
        raise archive_util.RuntimeErrorSafe("DB_INITIALIZE_FAILED: inspect local initialization diagnostics; no automatic retry") from None
    reservation.write_text(json.dumps(owner, sort_keys=True, indent=2), encoding="utf-8")
    return owner


def _listener_owned(port, pid):
    if os.name != "nt":
        return False  # Actual acceptance is Windows-only; tests use inert stubs.
    class Row(ctypes.Structure):
        _fields_ = [(name, wintypes.DWORD) for name in ("state", "localAddr", "localPort", "remoteAddr", "remotePort", "pid")]
    api = ctypes.windll.iphlpapi.GetExtendedTcpTable; size = wintypes.ULONG(0)
    api(None, ctypes.byref(size), False, socket.AF_INET, 3, 0)
    buffer = ctypes.create_string_buffer(size.value)
    if api(buffer, ctypes.byref(size), False, socket.AF_INET, 3, 0): return False
    count = ctypes.c_uint32.from_buffer(buffer).value
    for index in range(count):
        row = Row.from_buffer(buffer, 4 + index * ctypes.sizeof(Row))
        if (row.pid == pid and socket.ntohs(row.localPort & 0xffff) == port and
                socket.inet_ntoa(struct.pack("<I", row.localAddr)) == "127.0.0.1"):
            return True
    return False


class OwnedDatabase:
    def __init__(self, process, runtime, data, config, port, log):
        self.process, self.runtime, self.data, self.config, self.port, self.log = process, runtime, data, dict(config), port, log


def _connected_owner(port):
    handle = _OWNED.get(port)
    require(handle is not None and handle.process.poll() is None and _listener_owned(port, handle.process.pid),
            "SQL is permitted only on this tool's owned isolated process")
    return handle


def _client_args(runtime_dir, config, port, directory, *, admin=False, bootstrap=False, program="mysql.exe"):
    user = "root" if admin or bootstrap else config["user"]
    password = "" if bootstrap else config["rootPassword"] if admin else config["password"]
    escaped = password.replace("\\", "\\\\").replace('"', '\\"')
    path = Path(directory) / "client.cnf"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(f'[client]\nhost=127.0.0.1\nport={port}\nuser={user}\npassword="{escaped}"\nprotocol=tcp\n')
    path.chmod(0o600)
    return [str(Path(runtime_dir) / "bin" / program), "--defaults-extra-file=" + str(path)]


def run_sql(runtime_dir, config, port, sql, *, admin=False, bootstrap=False):
    _config(config); _port(port); handle = _connected_owner(port)
    require(handle.runtime.resolve() == Path(runtime_dir).resolve(), "SQL runtime differs from owned process")
    require(isinstance(sql, (str, bytes)), "SQL input must be text or bytes")
    with tempfile.TemporaryDirectory(prefix="handover-db-client-") as temporary:
        args = _client_args(runtime_dir, config, port, temporary, admin=admin, bootstrap=bootstrap)
        args += ["--batch", "--raw", "--skip-column-names", "--binary-mode", "--default-character-set=utf8mb4", "--max-allowed-packet=256M"]
        result = subprocess.run(args, input=sql.encode("utf-8") if isinstance(sql, str) else sql,
                                capture_output=True, timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        require(result.returncode == 0, "Isolated project SQL failed; no automatic retry")
        return result.stdout


def _literal(value):
    return "'" + value.replace("'", "''") + "'"  # Provisioning first sets NO_BACKSLASH_ESCAPES.


DATASET_SCHEMA = """CREATE TABLE IF NOT EXISTS gld_dataset (
 id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 device_id VARCHAR(16),node_id INT UNSIGNED,mode VARCHAR(16) DEFAULT 'DATASET',seq INT UNSIGNED,
 timestamp_ms BIGINT UNSIGNED,label VARCHAR(32),nulling_profile_id TINYINT UNSIGNED DEFAULT 0,
 sv0 FLOAT,sv1 FLOAT,sv2 FLOAT,sv3 FLOAT,sv4 FLOAT,sv5 FLOAT,sv6 FLOAT,sv7 FLOAT,
 gain0 TINYINT,gain1 TINYINT,gain2 TINYINT,gain3 TINYINT,gain4 TINYINT,gain5 TINYINT,gain6 TINYINT,gain7 TINYINT
);"""
HISTORY_SCHEMA = """CREATE TABLE IF NOT EXISTS handover_files (
 file_sha256 CHAR(64) PRIMARY KEY,file_kind VARCHAR(16) NOT NULL,byte_count BIGINT UNSIGNED NOT NULL,
 content LONGBLOB NOT NULL,header_json LONGTEXT NOT NULL,row_count BIGINT UNSIGNED NOT NULL,
 imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS handover_sources (
 file_sha256 CHAR(64) NOT NULL,source_path_sha256 CHAR(64) NOT NULL,source_path LONGTEXT NOT NULL,
 PRIMARY KEY(file_sha256,source_path_sha256));
CREATE TABLE IF NOT EXISTS handover_rows (
 file_sha256 CHAR(64) NOT NULL,row_index BIGINT UNSIGNED NOT NULL,row_json LONGTEXT NOT NULL,
 PRIMARY KEY(file_sha256,row_index));"""


def start(runtime_dir, data_dir, config, port=33306, *, timeout=60):
    config = _config(config); _port(port); runtime_dir = Path(runtime_dir).absolute(); data_dir, receipt = _owner(data_dir)
    require(receipt.get("initialized") is True and receipt.get("port") == port and receipt.get("database") == config["name"],
            "Database initialization receipt differs")
    require(port not in _OWNED, "An owned database already uses this port")
    with socket.socket() as probe:
        try: probe.bind(("127.0.0.1", port))
        except OSError: raise archive_util.RuntimeErrorSafe("Isolated database port is occupied") from None
    log = (data_dir / "server-process.log").open("ab")
    args = [str(runtime_dir / "bin/mysqld.exe"), "--no-defaults", "--basedir=" + str(runtime_dir),
            "--datadir=" + str(data_dir), "--port=" + str(port), "--bind-address=127.0.0.1", "--skip-name-resolve",
            "--skip-log-bin", "--max-allowed-packet=256M", "--character-set-server=utf8mb4", "--console"]
    try:
        process = subprocess.Popen(args, cwd=runtime_dir, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        log.close()
        raise archive_util.RuntimeErrorSafe("Isolated database process could not start") from None
    handle = OwnedDatabase(process, runtime_dir, data_dir, config, port, log); _OWNED[port] = handle
    try:
        deadline = time.monotonic() + timeout
        while process.poll() is None and not _listener_owned(port, process.pid) and time.monotonic() < deadline:
            time.sleep(.2)
        _connected_owner(port)
        if not receipt.get("rootProvisioned"):
            name, user = config["name"], config["user"]
            sql = ("SET SESSION sql_mode='NO_BACKSLASH_ESCAPES';" +
                   f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4;" +
                   f"CREATE USER IF NOT EXISTS '{user}'@'127.0.0.1' IDENTIFIED BY {_literal(config['password'])};" +
                   f"ALTER USER '{user}'@'127.0.0.1' IDENTIFIED BY {_literal(config['password'])};" +
                   f"GRANT ALL PRIVILEGES ON `{name}`.* TO '{user}'@'127.0.0.1';" +
                   # mysql_install_db may create a separate passwordless
                   # root@127.0.0.1 which takes precedence for TCP clients.
                   f"CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED BY {_literal(config['rootPassword'])};" +
                   f"ALTER USER 'root'@'127.0.0.1' IDENTIFIED BY {_literal(config['rootPassword'])};" +
                   "GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION;" +
                   f"ALTER USER 'root'@'localhost' IDENTIFIED BY {_literal(config['rootPassword'])}; FLUSH PRIVILEGES;")
            run_sql(runtime_dir, config, port, sql, bootstrap=True)
            receipt["rootProvisioned"] = True; (data_dir / OWNER).write_text(json.dumps(receipt, sort_keys=True, indent=2))
        run_sql(runtime_dir, config, port, f"USE `{config['name']}`;" + DATASET_SCHEMA + HISTORY_SCHEMA)
        return handle
    except Exception:
        stop(handle, force=True)
        raise


def stop(handle, *, force=False):
    require(_OWNED.get(handle.port) is handle, "Refusing to stop an unowned database")
    try:
        if handle.process.poll() is None:
            if _listener_owned(handle.port, handle.process.pid):
                _, receipt = _owner(handle.data)
                with tempfile.TemporaryDirectory(prefix="handover-db-stop-") as temporary:
                    args = _client_args(handle.runtime, handle.config, handle.port, temporary,
                                        admin=True, bootstrap=not receipt.get("rootProvisioned"), program="mysqladmin.exe")
                    try:
                        result = subprocess.run(args + ["shutdown"], capture_output=True, timeout=30,
                                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    except Exception:
                        if not force:
                            raise archive_util.RuntimeErrorSafe("Owned database shutdown failed") from None
                        handle.process.terminate(); handle.process.wait(timeout=15)
                        result = None
                    if result is None: return
                    if result.returncode != 0 and not force:
                        raise archive_util.RuntimeErrorSafe("Owned database shutdown failed; no other process was touched")
            elif not force:
                raise archive_util.RuntimeErrorSafe("Owned database listener is not confirmed")
            try: handle.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                require(force, "Owned database has not stopped")
                handle.process.terminate(); handle.process.wait(timeout=15)
    finally:
        if handle.process.poll() is not None:
            handle.log.close(); _OWNED.pop(handle.port, None)


def _text_hex(value):
    return "CONVERT(0x" + value.encode("utf-8").hex() + " USING utf8mb4)" if value else "''"


def _history_rows(raw, suffix):
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")): text = raw.decode("utf-16")
    else:
        try: text = raw.decode("utf-8-sig")
        except UnicodeDecodeError: text = raw.decode("cp1252", errors="replace")
    if suffix.lower() == ".csv":
        try: dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
        except csv.Error: dialect = csv.excel
        rows = list(csv.reader(io.StringIO(text, newline=""), dialect))
        return "csv", (rows[0] if rows else []), rows[1:]
    rows = []
    for line in text.splitlines():
        if not line.strip(): continue
        try: rows.append(json.loads(line))
        except ValueError: rows.append(dict(unparsed_line=line))
    return "jsonl", [], rows


def import_history(runtime_dir, config, port, history_manifest, *, history_root=None):
    _config(config); _port(port); _connected_owner(port)
    if isinstance(history_manifest, (str, Path)):
        path = Path(history_manifest).absolute(); value = json.loads(path.read_text(encoding="utf-8")); base = path.parent
    else:
        value = history_manifest; require(history_root is not None, "History dictionary requires explicit root"); base = Path(history_root).absolute()
    require(isinstance(value, dict) and isinstance(value.get("files"), list), "History manifest unavailable")
    summaries = []
    for item in value["files"]:
        relative = str(archive_util._safe_relative(item.get("path")))
        path = base.joinpath(*PurePosixPath(relative).parts)
        require(path.is_file() and not archive_util._reparse(path) and path.resolve().is_relative_to(base.resolve()), "History source escaped root")
        raw = path.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
        require(digest == item.get("sha256"), "History source checksum differs")
        kind, header, rows = _history_rows(raw, path.suffix)
        sql = [f"USE `{config['name']}`;START TRANSACTION;",
               f"INSERT IGNORE INTO handover_files(file_sha256,file_kind,byte_count,content,header_json,row_count) VALUES ('{digest}','{kind}',{len(raw)},X'{raw.hex()}',{_text_hex(json.dumps(header,ensure_ascii=False))},{len(rows)});"]
        sources = item.get("sources", [relative]); require(isinstance(sources, list) and all(isinstance(p, str) for p in sources), "History provenance invalid")
        for source in sources:
            source_hash = hashlib.sha256(source.encode()).hexdigest()
            sql.append(f"INSERT IGNORE INTO handover_sources VALUES ('{digest}','{source_hash}',{_text_hex(source)});")
        for index, row in enumerate(rows, 1):
            sql.append(f"INSERT IGNORE INTO handover_rows VALUES ('{digest}',{index},{_text_hex(json.dumps(row,ensure_ascii=False))});")
        sql.append("COMMIT;")
        run_sql(runtime_dir, config, port, "\n".join(sql))
        summaries.append(dict(sha256=digest, bytes=len(raw), rows=len(rows), sources=len(sources), kind=kind))
    return dict(source="CSV/ledger reconstruction; not an existing database dump", files=len(summaries),
                rows=sum(item["rows"] for item in summaries), entries=summaries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--export-runtime", type=Path, metavar="SOURCE")
    mode.add_argument("--extract-runtime", type=Path, metavar="MANIFEST")
    parser.add_argument("--output", type=Path); parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    try:
        if args.export_runtime:
            require(args.output is not None, "Runtime export requires --output")
            result = export_runtime(args.export_runtime, args.output)
            report = dict(status="PASS", version=result["version"], files=len(result["files"]), parts=len(result["parts"]))
        else:
            require(args.destination is not None, "Runtime extraction requires --destination")
            report = extract_runtime(args.extract_runtime, args.destination); report["status"] = "PASS"
        print(json.dumps(report)); return 0
    except Exception as error:
        print(json.dumps(dict(status="BLOCKED", reason=str(error) if isinstance(error, archive_util.RuntimeErrorSafe) else "Database handover validation failed")))
        return 1


if __name__ == "__main__": raise SystemExit(main())
