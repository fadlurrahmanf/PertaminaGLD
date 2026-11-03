"""Model1-only compile receipt; no upload, hardware, or package publication."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
ENV = "gld_model_1_dataset_workflow_wifi"
OUT = Path(__file__).resolve().parent
LOG = OUT / "model1-compile-attempt2.log"
RECEIPT = OUT / "model1-build-attempt2.json"
BUILD_ROOT = ROOT / "firmware/.pio/workflow-build-model1"
LIBDEPS_ROOT = ROOT / "firmware/.pio/workflow-libdeps-model1"
BUILD = BUILD_ROOT / ENV
ARTIFACT = ROOT / "firmware/.pio/artifacts/gld-dataset-workflow-wifi-20261102" / ENV
PYTHON = "C:/Users/MSI/.platformio/penv/Scripts/python.exe"
PUBLIC = ["firmware/platformio.ini", "firmware/tools/prepare_dataset_workflow_wifi.py",
          "firmware/gld/src/GldDatasetWorkflowWifi.cpp", "firmware/gld/include/GldDatasetWorkflowWifi.h",
          "firmware/gld/include/GldDatasetWorkflowBuffer.h", "firmware/gld/src/GldUnifiedMain.cpp",
          "firmware/gld/models/model_1/ModelMetadata.h", "firmware/gld/models/model_1/model_data.cpp",
          "firmware/gld/models/model_1/model_data.h"]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def sources():
    return {name: digest(ROOT / name) for name in PUBLIC}

def stamp():
    now = dt.datetime.now(dt.timezone.utc)
    return now.isoformat(), now.astimezone(dt.timezone(dt.timedelta(hours=7))).isoformat()

OUT.mkdir(parents=True, exist_ok=True)
before = sources()
start_utc, start_wib = stamp()
started = time.monotonic()
command = [PYTHON, "-m", "platformio", "run", "-d", "firmware", "-e", ENV, "-j", "1"]
with LOG.open("w", encoding="utf-8") as log:
    process_env = os.environ.copy()
    process_env.update(PLATFORMIO_BUILD_DIR=str(BUILD_ROOT), PLATFORMIO_LIBDEPS_DIR=str(LIBDEPS_ROOT))
    process = subprocess.Popen(command, cwd=ROOT, env=process_env, stdout=log, stderr=subprocess.STDOUT)
    print(json.dumps({"environment": ENV, "pid": process.pid, "startUtc": start_utc,
                      "startWib": start_wib, "log": str(LOG)}), flush=True)
    receipt = dict(environment=ENV, status="running", pid=process.pid,
        startUtc=start_utc, startWib=start_wib, sourceHashesBefore=before,
        log=str(LOG), command=command, buildDirectory=str(BUILD), libdepsDirectory=str(LIBDEPS_ROOT))
    RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    code = process.wait()
end_utc, end_wib = stamp()
after = sources()
lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
memory = [line.strip() for line in lines if re.match(r"\s*(RAM|Flash):", line)]
warnings = [line.strip() for line in lines if "warning:" in line.lower() or "Obsolete PIO Core" in line]
errors = [line.strip() for line in lines if "error:" in line.lower() or line.startswith("*** [")]
receipt.update(status="success" if code == 0 else "failed", exitCode=code,
    endUtc=end_utc, endWib=end_wib, elapsedSeconds=round(time.monotonic()-started, 3),
    sourceHashesAfter=after, sourceUnchanged=before == after,
    sourceFingerprint=hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
    memorySummary=memory, warnings=warnings, firstErrors=errors[:8])
if code == 0:
    assert before == after, "Public source changed during compile"
    paths = {name: BUILD / name for name in ("bootloader.bin", "partitions.bin", "firmware.bin")}
    paths["boot_app0.bin"] = Path("C:/Users/MSI/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin")
    assert all(path.is_file() for path in paths.values()), "Required flash artifact missing"
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for name, path in paths.items():
        target = ARTIFACT / name
        shutil.copy2(path, target)
        assert digest(target) == digest(path)
        artifacts.append(dict(name=name, path=str(target), buildPath=str(path),
                              sha256=digest(target), sizeBytes=target.stat().st_size))
    receipt.update(artifactDirectory=str(ARTIFACT), artifacts=artifacts,
                   firmwareSha256=digest(BUILD / "firmware.bin"),
                   firmwareSizeBytes=(BUILD / "firmware.bin").stat().st_size)
RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: receipt[key] for key in ("status", "exitCode", "endUtc", "endWib",
    "elapsedSeconds", "sourceUnchanged", "memorySummary", "warnings", "firstErrors")}), flush=True)
raise SystemExit(code)
