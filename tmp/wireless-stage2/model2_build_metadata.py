"""Private Model2 build receipt/artifact metadata. No compile/COM/network here."""
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIRMWARE = ROOT / "firmware"
ENV = "gld_model_2_dataset_replay_wifi"
RECEIPT = ROOT / "tmp/wireless-stage2/model2-build-receipt.json"
LOG = ROOT / "tmp/wireless-stage2/compile-model2.log"
BUILD = FIRMWARE / ".pio/build-wireless-stage2-model2" / ENV
ARTIFACT = FIRMWARE / ".pio/artifacts/gld-dataset-replay-wifi-20261102" / ENV


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--pid", type=int, action="append")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("model2_package_readonly_helpers", FIRMWARE / "tools/operator_package_post.py")
    package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8-sig"))
    for phase in ("start", "end"):
        if phase + "Utc" in receipt:
            moment = dt.datetime.fromisoformat(receipt[phase + "Utc"])
            receipt[phase + "Utc"] = moment.astimezone(dt.timezone.utc).isoformat()
            receipt[phase + "Wib"] = moment.astimezone(dt.timezone(dt.timedelta(hours=7))).isoformat()
    fingerprint = package._firmware_tree_snapshot_sha256(FIRMWARE)
    if not args.finalize:
        receipt["sourceFingerprintBefore"] = fingerprint
        receipt["sourceFingerprintScope"] = "firmware tree excluding .pio and Python bytecode/cache; not exact compiler inputs"
        receipt["compilePids"] = args.pid or []
    else:
        if receipt.get("exitCode") != 0:
            raise RuntimeError("Refuse artifact copy without successful compile receipt")
        log = LOG.read_text(encoding="utf-8-sig", errors="replace")
        if "[SUCCESS]" not in log:
            raise RuntimeError("Successful PlatformIO completion missing from log")
        receipt["productionPackageHookObserved"] = "Operator Hub package refreshed:" in log
        if receipt["productionPackageHookObserved"]:
            raise RuntimeError("Unexpected production package hook in dedicated compile")
        started = dt.datetime.fromisoformat(receipt["startUtc"])
        if dt.datetime.fromtimestamp((BUILD / "firmware.bin").stat().st_mtime, dt.timezone.utc) < started:
            raise RuntimeError("Binary predates this compile invocation")
        receipt["sourceFingerprintAfter"] = fingerprint
        receipt["sourceUnchangedDuringCompile"] = receipt.get("sourceFingerprintBefore") == fingerprint
        if not receipt["sourceUnchangedDuringCompile"]:
            raise RuntimeError("Firmware source fingerprint changed during compile")
        for key, label in (("ram", "RAM"), ("flash", "Flash")):
            match = re.search(label + r":\s+\[[^\]]+\]\s+([\d.]+)% \(used (\d+) bytes from (\d+) bytes\)", log)
            if not match:
                raise RuntimeError("Missing memory size report: " + key)
            receipt[key] = dict(percent=float(match[1]), usedBytes=int(match[2]), capacityBytes=int(match[3]))
        receipt["warnings"] = [line.strip() for line in log.splitlines() if "warning:" in line.lower()]
        receipt["warningCount"] = len(receipt["warnings"])
        receipt["buildElapsedSeconds"] = float(re.search(r"\[SUCCESS\] Took ([\d.]+) seconds", log)[1])
        binary = (BUILD / "firmware.bin").read_bytes()
        receipt["identityMarkers"] = {marker: marker.encode("ascii") in binary for marker in
            ("cnn-dualbranch-board-2-2class-v2", "gld-dataset-wifi/2", "GLD-DATASET-", "/dataset")}
        if not all(receipt["identityMarkers"].values()):
            raise RuntimeError("Model2 or replay identity marker missing from binary")
        files = []
        ARTIFACT.mkdir(parents=True, exist_ok=True)
        for name, offset in (("bootloader.bin", "0x00000000"), ("partitions.bin", "0x00008000"),
                             ("boot_app0.bin", "0x0000e000"), ("firmware.bin", "0x00010000")):
            source = package._required_file(FIRMWARE, BUILD, name)
            target = ARTIFACT / name
            checksum = sha(source)
            if target.exists() and sha(target) != checksum:
                raise RuntimeError("Refuse to overwrite an existing different private artifact: " + name)
            if not target.exists():
                shutil.copyfile(source, target)
            if sha(target) != checksum:
                raise RuntimeError("Copied artifact hash differs: " + name)
            files.append(dict(path=name, offset=offset, size=target.stat().st_size, sha256=checksum))
        artifact = dict(environment=ENV, sourceFingerprint=fingerprint,
                        flashFiles=files, flashSetSha256=package._flash_set_sha256(files))
        (ARTIFACT / "artifact-hashes.json").write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
        receipt["artifactDirectory"] = str(ARTIFACT)
        receipt["artifacts"] = files
        receipt["binaryPath"] = str(BUILD / "firmware.bin")
        receipt["binarySha256"] = sha(BUILD / "firmware.bin")
        receipt["binarySize"] = (BUILD / "firmware.bin").stat().st_size
        receipt["status"] = "success_artifacts_verified"
    RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(status=receipt["status"], sourceFingerprint=fingerprint,
                          binarySha256=receipt.get("binarySha256"), warningCount=receipt.get("warningCount"))))


if __name__ == "__main__":
    main()
