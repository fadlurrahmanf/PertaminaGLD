"""Read-only admission checks for isolated GLD ATEX workflow candidates.

This module does not build, install, select, or flash firmware.  The caller
must provide the existing GLD child validator and NVS resolver.  A valid result
is package evidence only, not evidence of the board fitted to a device or of
physical gas-model accuracy.  The canonical environment names and board label
must be integrated consistently with the eventual ATEX release contract.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable

ATEX_BOARD_PROFILE = "GLD ATEX MotherBoardGLDVer2 / GPIO7 fan"
ATEX_ENVIRONMENTS = {
    model: f"gld_atex_model_{model}_dataset_workflow_wifi" for model in (1, 2, 3)
}
FLASH_LAYOUT = {
    "bootloader.bin": 0x0000,
    "partitions.bin": 0x8000,
    "boot_app0.bin": 0xE000,
    "firmware.bin": 0x10000,
}
EXPECTED_NVS = (0x9000, 0x5000)
# default_16MB.csv application slot used by this project's GLD firmware.
APP_END = 0x650000
MARKERS = (b"gld-dataset-wifi/3", b"PAUSE_DATASET", b"CONTINUE_DATASET",
           b"RESUME_DATASET", b"ACK_SAMPLES")
DEFAULT_MODEL_ROOT = Path(__file__).resolve().parents[1] / "gld" / "models"


def _load_model_contract(model: int, model_root: Path) -> tuple[bytes, str, str]:
    directory = model_root / f"model_{model}"
    try:
        metadata = json.loads((directory / "model.json").read_text(encoding="utf-8"))
        header = (directory / "cnn_gas_datasheet_model_data.h").read_text(encoding="utf-8")
        model_metadata = (directory / "ModelMetadata.h").read_text(encoding="utf-8")
        match = re.search(r"g_cnn_gas_datasheet_2class_model\[\]\s*=\s*\{(.*?)\};", header, re.S)
        profile = re.search(r'PROFILE_ID\s*=\s*"([^"]+)"', model_metadata)
        if not match or not profile:
            raise ValueError("model source contract missing")
        # Reject any unsupported/non-byte initializer rather than matching an
        # accidentally empty or partial subset of source text.
        body = match.group(1)
        values = re.findall(r"0x([0-9a-fA-F]{2})", body)
        if not values or re.sub(r"0x[0-9a-fA-F]{2}|[\s,]", "", body):
            raise ValueError("model initializer invalid")
        blob = bytes(int(value, 16) for value in values)
        digest = hashlib.sha256(blob).hexdigest()
        if metadata.get("slot") != f"model_{model}" or metadata.get("modelSha256") != digest:
            raise ValueError("model source digest or slot mismatch")
        if metadata.get("profileId") != profile.group(1):
            raise ValueError("model profile source mismatch")
        return blob, digest, profile.group(1)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("ATEX model source contract is invalid") from exc


def validate_atex_package(
    manifest: Any,
    package_files: Any,
    model: int,
    target_id: str,
    *,
    base_validator: Callable,
    nvs_resolver: Callable,
    model_root: Path = DEFAULT_MODEL_ROOT,
) -> dict[str, Any]:
    """Apply ATEX constraints after reusing the GLD schema/hash validator.

    The existing GLD validator currently rejects ATEX nativeSerial capabilities
    solely because its allowlist contains GLD1 only.  This wrapper verifies the
    capability object exactly, then delegates an otherwise unmodified copy with
    only that field omitted.  It never changes the original or global allowlist.
    Integration can replace this adapter when the base allowlist admits ATEX.
    `model_root` must be a trusted source tree, never chosen by an upload client.
    """
    if type(model) is not int or model not in ATEX_ENVIRONMENTS:
        raise RuntimeError("ATEX model must be 1, 2 or 3")
    env = ATEX_ENVIRONMENTS[model]
    if not isinstance(target_id, str) or not re.fullmatch(r"[0-9A-F]{4}", target_id) or not 0x1001 <= int(target_id, 16) <= 0xFEFF:
        raise RuntimeError("invalid target GLD identity")
    if not isinstance(manifest, dict) or manifest.get("environment") != env:
        raise RuntimeError("ATEX environment and model do not match")
    if manifest.get("boardProfile") != ATEX_BOARD_PROFILE:
        raise RuntimeError("ATEX board profile does not match")
    caps = manifest.get("capabilities")
    if (not isinstance(caps, dict) or set(caps) != {"nativeSerial", "datasetWifi"}
            or caps.get("nativeSerial") is not True or caps.get("datasetWifi") is not True):
        raise RuntimeError("ATEX workflow capabilities invalid")
    base_manifest = dict(manifest)
    del base_manifest["capabilities"]
    _, verified = base_validator(base_manifest, package_files, env, target_id)
    if len(verified) != len(FLASH_LAYOUT):
        raise RuntimeError("ATEX requires exactly four flash files")
    files: dict[str, tuple[int, bytes]] = {}
    for item, content in verified:
        name = item.get("path")
        if name not in FLASH_LAYOUT or name in files:
            raise RuntimeError("ATEX flash file set invalid")
        offset = int(item["offset"], 16)
        if offset != FLASH_LAYOUT[name]:
            raise RuntimeError("ATEX flash offset invalid")
        files[name] = (offset, content)
    if set(files) != set(FLASH_LAYOUT):
        raise RuntimeError("ATEX flash file set invalid")
    if nvs_resolver(verified) != EXPECTED_NVS:
        raise RuntimeError("ATEX NVS layout differs from verified layout")
    table = files["partitions.bin"][1]
    nvs_entries, app_entries, partitions = [], [], []
    for index in range(0, len(table) - 31, 32):
        record = table[index:index + 32]
        magic = int.from_bytes(record[:2], "little")
        if magic == 0xFFFF:
            break
        if magic != 0x50AA:
            continue
        region = (int.from_bytes(record[4:8], "little"), int.from_bytes(record[8:12], "little"))
        if region[0] < 0x9000 or region[0] % 0x1000 or region[1] <= 0 or region[1] % 0x1000 or region[0] + region[1] > 0x1000000:
            raise RuntimeError("ATEX partition range is invalid")
        partitions.append((region[0], region[0] + region[1]))
        if (record[2], record[3]) == (0x01, 0x02):
            nvs_entries.append(region)
        if (record[2], record[3]) == (0x00, 0x10):
            app_entries.append(region)
    partitions.sort()
    if any(left[1] > right[0] for left, right in zip(partitions, partitions[1:])):
        raise RuntimeError("ATEX partition ranges overlap")
    if nvs_entries != [EXPECTED_NVS] or app_entries != [(0x10000, APP_END - 0x10000)]:
        raise RuntimeError("ATEX partition table does not match the approved NVS/app layout")
    # Flash writes erase whole 4 KiB sectors. Check erase intervals, not just
    # byte intervals, against each other, NVS, and the approved app slot.
    ranges = []
    for name, (offset, content) in files.items():
        end = (offset + len(content) + 0xFFF) & ~0xFFF
        if offset < EXPECTED_NVS[0] + EXPECTED_NVS[1] and end > EXPECTED_NVS[0]:
            raise RuntimeError("ATEX flash erase overlaps NVS")
        if name == "firmware.bin" and end > APP_END:
            raise RuntimeError("ATEX firmware exceeds app slot")
        ranges.append((offset, end))
    ranges.sort()
    if any(left[1] > right[0] for left, right in zip(ranges, ranges[1:])):
        raise RuntimeError("ATEX flash erase regions overlap")
    firmware = files["firmware.bin"][1]
    if b"SYNTHETIC_TEST_ONLY" in firmware:
        raise RuntimeError("synthetic candidate is not a release package")
    blob, model_sha, profile = _load_model_contract(model, Path(model_root))
    if firmware.count(blob) != 1 or profile.encode("ascii") not in firmware:
        raise RuntimeError("ATEX firmware model identity mismatch")
    if any(marker not in firmware for marker in MARKERS):
        raise RuntimeError("ATEX firmware workflow marker missing")
    return {"environment": env, "model": model, "modelSha256": model_sha,
            "profileId": profile, "firmwareSha256": hashlib.sha256(firmware).hexdigest(),
            "nvsOffset": EXPECTED_NVS[0], "nvsSize": EXPECTED_NVS[1],
            "boardProfile": ATEX_BOARD_PROFILE}

