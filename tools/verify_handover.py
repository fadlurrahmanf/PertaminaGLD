"""Verify committed inputs and an isolated clean-checkout full-stack handover.

Default mode runs only the copied stack, on offset ports, and retains diagnostics.
No source .env/profile, developer node_modules, original DB, or hardware is used.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import time
import uuid

PREFIXES = ("apps/gld-operator", "apps/ch-operator", "apps/gw-operator",
            "apps/operator-hub", "apps/lib", "server/nodered", "tools")
ROOT_FILES = (".gitignore", ".gitattributes", "start-handover.bat", "verifikasi-handover.bat",
              "start-pertamina-gld-system.bat")
NEW_FILES = ("apps/gld-operator/workflow-connection-profiles.json", "tools/verify_handover.py")
EXCLUDED_PARTS = {".git", ".pio", "node_modules", "__pycache__", ".pytest_cache", "output",
                  "logs", "mockups", "tmp", "archive", "release", "release-comfix", "dist", ".vite"}
EXCLUDED_FILES = {"credentials.local.json", "startup.local.json", "settings.local.js", "flows_cred.json"}
MAX_MANIFEST = 32 * 1024 * 1024
STATIC_LABELS = {
    "snapshot": "Snapshot konfigurasi, profil Node-RED dan history: hash cocok",
    "plaintext_authorization": "Persetujuan dan hash konfigurasi plaintext",
    "windows-x64": "Paket runtime Node.js dan Node-RED: hash cocok",
    "database-windows-x64": "Paket runtime database: hash cocok",
    "bundled_ch340_driver": "Paket driver CH340 dan tanda tangan katalog valid",
    "gld_python_pyserial": "Runtime Python dan serial GLD tersedia",
    "ch_python_pyserial": "Runtime Python dan serial CH tersedia",
    "shared_esptool": "ESPTool untuk upload firmware tersedia",
    "vendored_websocket": "Library koneksi Dataset tersedia",
    "workflow_model_1": "Paket firmware Model 1 lengkap dan valid",
    "workflow_model_2": "Paket firmware Model 2 lengkap dan valid",
    "workflow_model_3": "Paket firmware Model 3 lengkap dan valid",
    "workflow_connection_profiles": "Kredensial otomatis ketiga model cocok dengan paket",
    "system_state_config": "Konfigurasi AES dan MQTT tersedia serta valid",
    "deployment_database_config": "Konfigurasi deployment dan database valid",
}
OPTIONAL_LABELS = {
    "node_nodered_runtime": "Pemeriksaan runtime yang sudah diekstrak pada tahap statis",
    "windows_ch340_driver": "Driver CH340 teramati pada Windows ini",
    "driver_signature": "Tanda tangan driver perangkat yang teramati",
}
FULL_TESTS = (
    ("mqttAuthentication", "Autentikasi MQTT berhasil"),
    ("aesRoundTrip", "Enkripsi/dekripsi AES lokal berhasil"),
    ("aesMqttNodeRedDecrypt", "Paket AES melalui MQTT berhasil didekripsi Node-RED"),
    ("nodeRedDatabaseInsert", "Node-RED berhasil menulis dan membaca database"),
    ("nodeRedCsvWrite", "Node-RED berhasil menulis CSV"),
)
SYMBOLS = {"pass": "✓", "fail": "✗", "warn": "!", "skip": "-", "pending": "…"}


class VerificationError(ValueError):
    """Fixed, safe diagnostic messages only."""


def require(condition, code):
    if not condition:
        raise VerificationError(code)


def read_json(path):
    require(path.is_file() and 0 < path.stat().st_size <= MAX_MANIFEST, "MANIFEST_UNAVAILABLE")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(value):
    require(isinstance(value, str) and value and not any(ord(c) < 32 or c in '\\:<>"|?*' for c in value), "UNSAFE_INPUT_PATH")
    parts = value.split("/")
    require(not value.startswith("/") and all(part not in ("", ".", "..") and part == part.rstrip(" .") for part in parts), "UNSAFE_INPUT_PATH")
    return PurePosixPath(value).as_posix()


def linked(path):
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def load_tool(root, name):
    spec = importlib.util.spec_from_file_location("handover_verifier_" + name, root / "tools" / (name + ".py"))
    require(spec is not None and spec.loader is not None, "HANDOVER_TOOL_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def runtime_parts(manifest_path, expected_kind):
    """Check split-archive byte/hash integrity without extraction or processes."""
    value = read_json(manifest_path)
    require(isinstance(value, dict) and value.get("schemaVersion") == 1 and value.get("kind") == expected_kind and
            isinstance(value.get("parts"), list) and 0 < len(value["parts"]) <= 1000, "RUNTIME_MANIFEST_INVALID")
    names, archive, total, paths = set(), hashlib.sha256(), 0, []
    for item in value["parts"]:
        require(isinstance(item, dict), "RUNTIME_PART_INVALID")
        name = safe_relative(item.get("path"))
        require("/" not in name and name.casefold() not in names and type(item.get("size")) is int and
                0 < item["size"] <= 128 * 1024 * 1024 and isinstance(item.get("sha256"), str) and
                re.fullmatch(r"[0-9a-f]{64}", item["sha256"]), "RUNTIME_PART_INVALID")
        names.add(name.casefold()); path = manifest_path.parent / name
        require(path.is_file() and not linked(path) and path.stat().st_size == item["size"], "RUNTIME_PART_UNAVAILABLE")
        part = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                part.update(chunk); archive.update(chunk); total += len(chunk)
        require(part.hexdigest() == item["sha256"], "RUNTIME_PART_CHECKSUM_FAILED")
        paths.append(path)
    require(total == value.get("archiveSize") and archive.hexdigest() == value.get("archiveSha256"), "RUNTIME_ARCHIVE_CHECKSUM_FAILED")
    return paths


def driver_signature_check():
    if os.name != "nt":
        return dict(status="skip", code="DRIVER_SIGNATURE_NOT_APPLICABLE")
    command = ("$ErrorActionPreference='Stop'; @(Get-CimInstance Win32_PnPSignedDriver | "
               "Where-Object { $_.DeviceID -match 'VID_1A86' -or $_.DeviceName -match 'CH34[01]' } | "
               "Select-Object IsSigned) | ConvertTo-Json -Compress")
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        require(result.returncode == 0, "DRIVER_QUERY_FAILED")
        records = json.loads(result.stdout or "[]")
        if isinstance(records, dict): records = [records]
        require(isinstance(records, list) and all(isinstance(item, dict) for item in records), "DRIVER_QUERY_FAILED")
        if not records: return dict(status="skip", code="NO_CH340_DEVICE_OBSERVED")
        signed = sum(item.get("IsSigned") is True for item in records)
        return dict(status="pass" if signed == len(records) else "warn", code="DRIVER_SIGNATURE_INVENTORY",
                    observed=len(records), signed=signed, hardwareTested=False)
    except Exception:
        return dict(status="skip", code="DRIVER_SIGNATURE_QUERY_UNAVAILABLE")


def static_checks(root):
    root = Path(root)
    checks, approved, state_files = [], [], set()
    try:
        snapshot = load_tool(root, "handover_snapshot").validate_snapshot(root / "handover/state")
        approved.extend(["handover/state/snapshot-manifest.json"] +
                        ["handover/state/" + safe_relative(item["path"]) for item in snapshot["files"]])
        state_files = {"handover/state/" + safe_relative(item["path"]) for item in snapshot["files"]}
        checks.append(dict(name="snapshot", status="pass", code="SNAPSHOT_HASHES_VERIFIED", files=len(snapshot["files"]),
                           historyFiles=sum(item.get("role") in {"dataset-csv", "dataset-ledger"} for item in snapshot["files"])))
    except Exception:
        checks.append(dict(name="snapshot", status="fail", code="SNAPSHOT_INVALID"))
    try:
        allowed, errors = load_tool(root, "check_repository_secrets").approved_handover_files(root)
        require(not errors and state_files and state_files | {"handover/deployment.json"} <= allowed,
                "PLAINTEXT_AUTHORIZATION_INVALID")
        checks.append(dict(name="plaintext_authorization", status="pass", code="PLAINTEXT_HASH_PINS_VERIFIED"))
    except Exception:
        checks.append(dict(name="plaintext_authorization", status="fail", code="PLAINTEXT_AUTHORIZATION_INVALID"))
    for directory, manifest_name, kind in (
        ("windows-x64", "runtime-manifest.json", "pertamina-gld-offline-runtime"),
        ("database-windows-x64", "database-runtime-manifest.json", "pertamina-gld-mariadb-runtime"),
    ):
        try:
            manifest = root / "handover/runtime" / directory / manifest_name
            parts = runtime_parts(manifest, kind)
            approved.extend([manifest.relative_to(root).as_posix()] + [path.relative_to(root).as_posix() for path in parts])
            checks.append(dict(name=directory, status="pass", code="RUNTIME_ARCHIVE_HASHES_VERIFIED", parts=len(parts)))
        except Exception:
            checks.append(dict(name=directory, status="fail", code="RUNTIME_ARCHIVE_INVALID"))
    try:
        driver_path = root / "handover/drivers/ch340-windows-x64/driver-manifest.json"
        tool = load_tool(root, "handover_driver")
        driver = tool.validate_driver(driver_path)
        if os.name == "nt":
            require(tool._catalog_signed(driver_path.parent / "ch341ser.cat"), "DRIVER_CATALOG_SIGNATURE_INVALID")
        approved.extend([driver_path.relative_to(root).as_posix()] +
                        [(driver_path.parent / safe_relative(item["path"])).relative_to(root).as_posix() for item in driver["files"]])
        checks.append(dict(name="bundled_ch340_driver", status="pass", code="DRIVER_PAYLOAD_HASHES_VERIFIED",
                           files=len(driver["files"]), catalogSignatureRechecked=os.name == "nt"))
    except Exception:
        checks.append(dict(name="bundled_ch340_driver", status="fail", code="DRIVER_BUNDLE_OR_SIGNATURE_INVALID"))
    try:
        result = load_tool(root, "handover_check").check(root, state_config=root / "handover/state/config/system.json")
        checks.extend(result["checks"])
    except Exception:
        checks.append(dict(name="host_preflight", status="fail", code="HOST_PREFLIGHT_FAILED"))
    checks.append(dict(name="driver_signature", **driver_signature_check()))
    approved.extend("handover/" + name for name in ("deployment.json", "plaintext-authorization.json", "README.md", "status.json")
                    if (root / "handover" / name).is_file())
    return dict(ok=not any(item.get("status") == "fail" for item in checks), checks=checks,
                approvedHandoverFiles=sorted(set(approved)))


def source_allowed(relative):
    parts = PurePosixPath(relative).parts
    if any(part.lower() in EXCLUDED_PARTS for part in parts): return False
    name = parts[-1].lower()
    if name in EXCLUDED_FILES or name.endswith((".pyc", ".pyo", ".log")): return False
    if (name == ".env" or name.startswith(".env.")) and name != ".env.example": return False
    if relative.startswith("apps/operator-hub/firmware-packages/"):
        return len(parts) >= 6 and parts[4] == "latest"
    return any(relative == prefix or relative.startswith(prefix + "/") for prefix in PREFIXES) or relative in ROOT_FILES or relative in NEW_FILES


def _git(root, executable, arguments, *, data=None):
    return subprocess.run([executable, "-C", str(root), *arguments], input=data, capture_output=True)


def select_export_files(root, approved_handover, git_executable=None):
    root = Path(root)
    executable = git_executable if git_executable is not None else shutil.which("git")
    tracked, changed, git_ok = set(), set(), False
    if executable:
        result = _git(root, executable, ["ls-files", "-z"])
        if result.returncode == 0:
            tracked = set(result.stdout.decode("utf-8").rstrip("\0").split("\0")) - {""}
            diff = _git(root, executable, ["diff", "--name-only", "-z", "HEAD"])
            changed = set(diff.stdout.decode("utf-8").rstrip("\0").split("\0")) - {""} if diff.returncode == 0 else set(tracked)
            git_ok = True
    selected = {name for name in tracked if source_allowed(name)}
    if not git_ok:
        for prefix in PREFIXES:
            directory = root / prefix
            if directory.is_dir():
                for current, dirs, files in os.walk(directory, followlinks=False):
                    base = Path(current)
                    dirs[:] = [name for name in dirs if name.lower() not in EXCLUDED_PARTS and not linked(base / name)]
                    for name in files:
                        relative = (base / name).relative_to(root).as_posix()
                        if source_allowed(relative): selected.add(relative)
    pending = [*ROOT_FILES, *NEW_FILES]
    for pattern in ("handover*.py", "handover*.cjs", "handover*.js"):
        pending.extend(path.relative_to(root).as_posix() for path in (root / "tools").glob(pattern))
    selected.update(name for name in pending if (root / name).is_file() and source_allowed(name))
    approved = {safe_relative(name) for name in approved_handover}
    require(all(name.startswith("handover/") for name in approved), "HANDOVER_ALLOWLIST_INVALID")
    selected.update(approved)
    selected = sorted(selected)
    require(selected and all((root / name).is_file() for name in selected), "REQUIRED_EXPORT_INPUT_MISSING")
    ignored = set()
    if git_ok:
        result = _git(root, executable, ["check-ignore", "--no-index", "-z", "--stdin"],
                      data=b"\0".join(name.encode() for name in selected) + b"\0")
        ignored = set(result.stdout.decode("utf-8").rstrip("\0").split("\0")) - {""}
    committed = git_ok and all(name in tracked and name not in changed for name in selected)
    eligible = git_ok and all(name in tracked or name not in ignored for name in selected)
    return selected, dict(gitAvailable=git_ok, inputFiles=len(selected), inputsCommitEligible=eligible,
        committed=committed, needsCommitPush=not committed, pushVerified=False,
        untrackedInputs=sum(name not in tracked for name in selected), modifiedTrackedInputs=sum(name in changed for name in selected))


def copy_export(root, destination, files):
    root, destination = Path(root).resolve(), Path(destination).absolute()
    require(not destination.exists(), "CLEAN_EXPORT_DESTINATION_EXISTS")
    destination.mkdir(parents=True)
    bytes_copied = 0
    for relative in files:
        relative = safe_relative(relative); source = root / relative
        require(source.is_file() and not linked(source) and
                all(not linked(parent) for parent in source.parents if parent.is_relative_to(root) and parent != root), "LINKED_EXPORT_INPUT_REFUSED")
        target = destination / relative; target.parent.mkdir(parents=True, exist_ok=True)
        before = sha(source); shutil.copyfile(source, target)
        require(sha(target) == before == sha(source), "EXPORT_COPY_CHECKSUM_FAILED")
        bytes_copied += target.stat().st_size
    return dict(files=len(files), bytes=bytes_copied)


def run_child(command, *, cwd, log, timeout=600):
    """Never terminate unknown children; retain workspace on timeout/failure."""
    environment = dict(os.environ)
    for key in list(environment):
        if (key.upper() in {"NODE_PATH", "NODE_OPTIONS", "PYTHONPATH", "PYTHONHOME", "MYSQL_HOME", "MARIADB_HOME", "OPENSSL_CONF", "OPENSSL_MODULES"} or
                key.upper().startswith(("PGL_", "GLD_", "MQTT_", "MYSQL_", "NODE_RED_"))):
            environment.pop(key, None)
    profile = Path(cwd) / ".verification-user"
    for relative in ("AppData/Roaming", "AppData/Local", "Temp"):
        (profile / relative).mkdir(parents=True, exist_ok=True)
    environment.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", USERPROFILE=str(profile),
        APPDATA=str(profile / "AppData/Roaming"), LOCALAPPDATA=str(profile / "AppData/Local"),
        TEMP=str(profile / "Temp"), TMP=str(profile / "Temp"))
    with Path(log).open("wb") as stream:
        process = subprocess.Popen(command, cwd=str(cwd), stdout=stream, stderr=subprocess.STDOUT,
                                   env=environment)
        try:
            return dict(returnCode=process.wait(timeout=timeout), timedOut=False)
        except subprocess.TimeoutExpired:
            return dict(returnCode=None, timedOut=True, childPid=process.pid, workspaceRetained=True)


def _safe_stack_result(path):
    result = read_json(path)
    require(isinstance(result, dict), "STACK_RESULT_INVALID")
    safe = {"status": result.get("status") if result.get("status") in {"PASS", "failed", "cleanup_failed", "stopped_by_operator"} else "UNKNOWN"}
    tests = result.get("selfTest", {})
    safe["selfTest"] = {key: tests[key] for key in ("mqttAuthentication", "nodeRedDatabaseInsert", "nodeRedCsvWrite", "aesRoundTrip", "aesMqttNodeRedDecrypt", "historyFiles", "historyRows", "historyByteMismatches", "hardwareTested")
                        if isinstance(tests, dict) and key in tests and type(tests[key]) in (bool, int)}
    safe["ports"] = {key: value for key, value in result.get("ports", {}).items()
                     if key in {"hub", "nodeRed", "mqtt", "database", "gld", "ch", "gw"} and type(value) is int and 1024 <= value <= 65535}
    return safe


def _status(value):
    return value if value in {"pass", "fail", "warn", "skip"} else "skip"


def build_checklist(report, *, final=True):
    """Build labels from fixed vocabulary; never echo config/HTTP payloads."""
    rows = []
    checks = report.get("static", {}).get("checks", [])
    observed = {item.get("name"): item for item in checks if isinstance(item, dict)}

    def add(name, label, status, required=True, detail=None):
        item = dict(id=name, label=label, status=status, required=required)
        if detail is not None: item["detail"] = detail
        rows.append(item)

    for name, label in STATIC_LABELS.items():
        check = observed.get(name)
        state = _status(check.get("status")) if check else ("fail" if final else "pending")
        add(name, label, state)
    for name, label in OPTIONAL_LABELS.items():
        if name in observed:
            add(name, label, _status(observed[name].get("status")), required=False)
    git = report.get("gitInputs")
    if isinstance(git, dict):
        state = "pass" if git.get("inputsCommitEligible") is True else ("warn" if git.get("gitAvailable") else "skip")
        add("git_commit_eligible", "File yang diperlukan dapat dimasukkan ke commit Git", state, required=False)
        state = "pass" if git.get("committed") is True else "warn"
        add("git_committed", "Perubahan handover sudah masuk commit lokal", state, required=False)
    if report.get("mode") != "static-only":
        copy = report.get("cleanExport")
        add("clean_export", "Salinan bersih dibuat tanpa konfigurasi lokal tersembunyi",
            "pass" if isinstance(copy, dict) and type(copy.get("files")) is int and copy["files"] > 0 else ("skip" if final else "pending"))
        child, stack = report.get("child", {}), report.get("stack", {})
        child_done = isinstance(child, dict) and not child.get("timedOut") and child.get("returnCode") is not None
        stack_pass = child_done and child.get("returnCode") == 0 and stack.get("status") == "PASS"
        state = "pass" if stack_pass else ("fail" if child_done or child.get("timedOut") else ("skip" if final else "pending"))
        add("copied_stack", "Hub, bridge dan layanan stack salinan berhasil dijalankan", state)
        tests = stack.get("selfTest", {}) if isinstance(stack, dict) else {}
        for name, label in FULL_TESTS:
            state = "pass" if tests.get(name) is True else ("fail" if child_done else ("skip" if final else "pending"))
            add(name, label, state)
        files, count, mismatches = (tests.get(key) for key in ("historyFiles", "historyRows", "historyByteMismatches"))
        expected = observed.get("snapshot", {}).get("historyFiles")
        history_ok = (type(files) is int and files > 0 and type(count) is int and count >= 0 and
                      type(mismatches) is int and mismatches == 0 and
                      (type(expected) is not int or files == expected))
        detail = None
        if type(files) is int and type(count) is int and type(mismatches) is int:
            detail = dict(files=files, rows=count, byteMismatches=mismatches)
        add("history_integrity", "History CSV/ledger lengkap dan byte seluruh file cocok",
            "pass" if history_ok else ("fail" if child_done else ("skip" if final else "pending")), detail=detail)
        state = "pass" if report.get("ownedServicesStopped") is True else (
            "fail" if child_done or child.get("timedOut") else ("skip" if final else "pending"))
        add("owned_cleanup", "Semua layanan yang dibuat pengujian sudah dihentikan", state)
    add("physical_hardware", "GLD/CH/Gateway fisik dan radio belum diuji oleh pemeriksaan ini", "skip", required=False)
    return rows


def decorate_report(report):
    rows = build_checklist(report)
    required = [item for item in rows if item["required"]]
    passed = sum(item["status"] == "pass" for item in required)
    failed = sum(item["status"] == "fail" for item in required)
    skipped = sum(item["status"] == "skip" for item in required)
    if report.get("status") != "PASS" or passed != len(required):
        if report.get("status") == "PASS":
            report.setdefault("failureCode", "REQUIRED_CHECKLIST_MISSING_OR_FAILED")
        report["status"] = "FAIL"
    report["checklist"] = rows
    report["summary"] = dict(total=len(required), tested=passed + failed, passed=passed, failed=failed,
        skipped=skipped, informationalSkipped=sum(item["status"] == "skip" for item in rows if not item["required"]),
        informationalWarnings=sum(item["status"] == "warn" for item in rows if not item["required"]))
    if report["status"] == "PASS":
        code = "STATIC_CHECKS_PASSED_FULL_STACK_NOT_RUN" if report.get("mode") == "static-only" else "SOFTWARE_HANDOVER_PASSED"
    else:
        code = "STATIC_CHECKS_FAILED" if report.get("mode") == "static-only" else "SOFTWARE_HANDOVER_FAILED"
    report["conclusion"] = dict(code=code, softwarePassed=report["status"] == "PASS", hardwareVerified=False,
                                githubPushVerified=False)
    return report


def _check_line(item, position=None, total=None):
    prefix = f" {position:02d}/{total:02d}" if position is not None else " Info"
    line = f"[{SYMBOLS[item['status']]}]{prefix}  {item['label']}"
    detail = item.get("detail")
    if isinstance(detail, dict):
        number = lambda value: f"{value:,}".replace(",", ".")
        line += f" ({number(detail['files'])} file, {number(detail['rows'])} baris, {number(detail['byteMismatches'])} beda byte)"
    print(line, flush=True)


def render_completed(report, printed):
    rows = build_checklist(report, final=False)
    total = sum(item["required"] for item in rows)
    position = 0
    for item in rows:
        if item["required"]: position += 1
        if item["status"] == "pending" or item["id"] in printed: continue
        _check_line(item, position if item["required"] else None, total)
        printed.add(item["id"])


def render_report(report, path=None):
    decorate_report(report)
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW("Verifikasi_Handover_GLD")
        except Exception:
            pass
    print("\nDAFTAR HASIL VERIFIKASI HANDOVER", flush=True)
    rows, summary = report["checklist"], report["summary"]
    position = 0
    for item in rows:
        if item["required"]:
            position += 1; _check_line(item, position, summary["total"])
    print("\nINFORMASI TAMBAHAN (tidak menambah hitungan lulus)", flush=True)
    for item in rows:
        if not item["required"]: _check_line(item)
    print(f"\nRINGKASAN: {summary['tested']:02d}/{summary['total']:02d} diuji | "
          f"{summary['passed']} lulus | {summary['failed']} gagal | {summary['skipped']} dilewati", flush=True)
    print(f"Informasi: {summary['informationalSkipped']} dilewati, {summary['informationalWarnings']} perlu diperhatikan.", flush=True)
    if report["status"] == "PASS":
        conclusion = ("Pemeriksaan statis LULUS. Uji fungsi stack belum dijalankan." if report.get("mode") == "static-only"
                      else "SOFTWARE HANDOVER LULUS. Uji stack salinan dan penghentian layanan berhasil.")
    else:
        conclusion = "VERIFIKASI GAGAL / BELUM LENGKAP. Periksa tanda silang atau bagian yang dilewati."
    print("KESIMPULAN: " + conclusion, flush=True)
    print("Perangkat fisik/radio dan operasi pada PC pengganti belum dibuktikan oleh laporan ini.", flush=True)
    git = report.get("gitInputs", {})
    if git.get("needsCommitPush"):
        print("GIT: perubahan lokal masih perlu commit/push; hasil uji ini bukan bukti sudah tersedia di GitHub.", flush=True)
    elif not git.get("pushVerified"):
        print("GIT: status push ke GitHub tidak diperiksa oleh laporan ini.", flush=True)
    if path is not None: print("Laporan: " + str(path), flush=True)


def show_report(path):
    """Render a saved report only: no writes, checks, copies or services."""
    path = Path(path)
    report = read_json(path)
    require(isinstance(report, dict), "VERIFICATION_REPORT_INVALID")
    render_report(report, path)
    return report


def verify(repo_root, *, static_only=False, output_root=None, git_executable=None,
           static_runner=static_checks, child_runner=run_child):
    root = Path(repo_root).resolve()
    output = Path(output_root) if output_root is not None else root / "output/handover-verification"
    report_dir = output / (dt.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8])
    report_dir.mkdir(parents=True, exist_ok=False)
    report_path = report_dir / "report.json"
    report = dict(schemaVersion=1, capturedAt=dt.datetime.now().astimezone().isoformat(),
                  mode="static-only" if static_only else "clean-export-full-stack", status="running",
                  hardwareTested=False, sourceDatabaseTouched=False, workspaceRetained=True)
    printed = set()

    def save():
        temporary = report_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        temporary.replace(report_path)
    save()
    try:
        print("Memeriksa paket, konfigurasi, runtime dan profil ketiga model...", flush=True)
        checked = static_runner(root)
        report["static"] = {key: value for key, value in checked.items() if key != "approvedHandoverFiles"}
        render_completed(report, printed)
        require(checked.get("ok") is True, "STATIC_CHECKS_FAILED")
        files, git_state = select_export_files(root, checked["approvedHandoverFiles"], git_executable)
        report["gitInputs"] = git_state; save()
        render_completed(report, printed)
        if static_only:
            report.update(status="PASS", servicesStarted=False)
        else:
            print("Membuat salinan bersih tanpa konfigurasi lokal tersembunyi...", flush=True)
            clean = report_dir / "clean-checkout"
            report["cleanExport"] = copy_export(root, clean, files); save()
            render_completed(report, printed)
            executable = clean / "apps/gld-operator/python-embed/python.exe"
            require(executable.is_file() and (clean / "tools/handover_stack.py").is_file(), "COPIED_STACK_RUNTIME_UNAVAILABLE")
            work = clean / "archive/apps/runtime/verification"
            command = [str(executable), "-B", str(clean / "tools/handover_stack.py"), "--self-test", "--local-only",
                       "--port-offset", "10000", "--repo-root", str(clean), "--work-root", str(work), "--no-browser"]
            print("Menguji stack salinan pada port terpisah; database sumber tidak dipakai...", flush=True)
            child = child_runner(command, cwd=clean, log=report_dir / "stack-diagnostic.log", timeout=600)
            report["child"] = child; save()
            require(not child.get("timedOut"), "CHILD_STILL_RUNNING_WORKSPACE_RETAINED")
            result = _safe_stack_result(work / "stack-result.json")
            report["stack"] = result
            require(child.get("returnCode") == 0 and result["status"] == "PASS", "STACK_TEST_OR_OWNED_CLEANUP_FAILED")
            report.update(servicesStarted=True, ownedServicesStopped=True)
            require(all(result.get("selfTest", {}).get(name) is True for name, _label in FULL_TESTS), "REQUIRED_SOFTWARE_TEST_MISSING_OR_FAILED")
            report.update(status="PASS")
    except Exception as error:
        report.update(status="FAIL", failureCode=str(error) if isinstance(error, VerificationError) else "VERIFICATION_FAILED_INSPECT_LOCAL_DIAGNOSTICS")
    finally:
        report["finishedAt"] = dt.datetime.now().astimezone().isoformat()
        decorate_report(report); save()
    render_report(report, report_path)
    return report


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--static-only", action="store_true")
    parser.add_argument("--show-report", type=Path, help="Tampilkan laporan tersimpan tanpa menjalankan ulang pengujian")
    args = parser.parse_args(argv)
    try:
        result = show_report(args.show_report) if args.show_report is not None else verify(args.repo_root, static_only=args.static_only)
    except Exception:
        print("VERIFIKASI GAGAL: laporan tidak dapat dibaca atau format tidak valid.", flush=True)
        return 1
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
