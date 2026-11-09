#!/usr/bin/env python3
"""Fail when tracked/releasable files contain known exposed secrets.

Known values are represented only by SHA-256 digests so the scanner does not
reintroduce the credentials it is intended to remove. This is a focused guard,
not a substitute for external secret scanning or credential rotation.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import subprocess
import sys


KNOWN_EXPOSED_TOKEN_DIGESTS = {
    "d298dcbc3cdee0edf1a803d2cb7e0131a75400f7406faa1d55c34f267c55103e",
    "51a61bfe01f1659d28989a3ac165454ea521a04ba675c28bd394ade943adbd7f",
    "3d1ce129dec1946c4d9f8c75b06cbbba0ae53360e3f0d6b54e1783b5356c282d",
    "916792f2355c8e805ed061388dfd406a9414b1d51dceed87885d5acca088fb61",
    "4a992d5dca3316d2cfb8b84601e28d1256bf44f399b951cef67cac3d5b121ca3",
}
TOKEN_RE = re.compile(r"[A-Za-z0-9_.-]{4,}")
PRIVATE_KEY_MARKERS = (
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
)
# Public esptool upstream test keys and source examples already bundled in Git.
# Exempt only these exact bytes; a changed file is scanned normally.
KNOWN_VENDOR_FIXTURE_SHA256 = {
    "apps/lib/esptool-master/test/secure_images/ecdsa256_secure_boot_signing_key_pkcs8.pem": "1ad4a4bae1017f4ba3e9e57b89dd1077f92c38f66347810a7bd8142ca07e5bc3",
    "apps/lib/esptool-master/test/secure_images/rsa_secure_boot_signing_key.pem": "fbacc9de01c087f61dfe22df94a531e9146da64fb4f1314febf578594d2f1c9d",
    "apps/lib/esptool-master/test/secure_images/rsa_secure_boot_signing_key2.pem": "07a2f08405d9fa24a77ccac2a420e7569757b6468751ce8f92a08b22e5e338d3",
    "apps/lib/esptool-master/test/secure_images/rsa_secure_boot_signing_key3.pem": "56c8e31d22462c092535183958c9fc1f7c44cd643ad12205f446494a4f3be6c4",
    "apps/lib/esptool-master/test/secure_images/rsa_secure_boot_signing_key4.pem": "44bed3a4047e35778ab7463d1df4a0059abd830ad20a6b9f58854976138f5a56",
    "apps/lib/esptool/vendor/cryptography/hazmat/primitives/serialization/ssh.py": "1d5e99a888ea34d68d50be8ce2043234926d67be44b22499b3acb175da81ad62",
    "apps/lib/esptool/vendor/ecdsa/keys.py": "164a6e6cbf4c1827e4089e9a56f5797346ef7b866e06d5373f57514414ed8749",
    "apps/lib/esptool/vendor/ecdsa/test_keys.py": "ade4362ad7ceb0035ae7d0aabef4568d99be49a59fb1c259549684f511722fde",
}
SKIP_SUFFIXES = {
    ".bin",
    ".elf",
    ".exe",
    ".jpg",
    ".jpeg",
    ".png",
    ".pdf",
    ".pyc",
    ".zip",
}
REQUIRED_IGNORED_SECRET_PATHS = (
    ".env",
    "config/gld-crypto.env",
    "config/gld-unified.env",
    "server/nodered/.env",
)


def approved_handover_files(root: pathlib.Path) -> tuple[set[str], list[str]]:
    """Honor the owner's explicit plaintext handover, only for pinned files.

    Local .env paths remain ignored and the general scanner stays active. The
    approval names exact snapshot/deployment files and their original byte hash.
    A changed/new file needs a refreshed intentional handover manifest.
    """
    policy = root / "handover/plaintext-authorization.json"
    if not policy.is_file():
        return set(), []
    try:
        value = json.loads(policy.read_text(encoding="utf-8"))
        if (value.get("schemaVersion") != 1 or value.get("ownerApprovedPlaintext") is not True or
                not isinstance(value.get("files"), dict) or not value["files"]):
            raise ValueError()
        allowed = set()
        for relative, digest in value["files"].items():
            if (not isinstance(relative, str) or "\\" in relative or ".." in pathlib.PurePosixPath(relative).parts or
                    not (relative.startswith("handover/state/") or relative == "handover/deployment.json") or
                    not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None):
                raise ValueError()
            path = root / relative
            if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                return set(), ["handover: approved snapshot bytes changed or missing; refresh explicit approval manifest"]
            allowed.add(relative)
        return allowed, []
    except (OSError, ValueError, TypeError, AttributeError):
        return set(), ["handover: invalid plaintext approval manifest"]


def repository_files(root: pathlib.Path) -> list[pathlib.Path]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    )
    paths = []
    for raw in completed.stdout.split(b"\0"):
        if not raw:
            continue
        relative = pathlib.Path(raw.decode("utf-8", errors="strict"))
        path = root / relative
        relative_posix = relative.as_posix()
        if (
            path.is_file()
            and not path.name.startswith("~$")
            and path.suffix.lower() not in SKIP_SUFFIXES
            and relative_posix != "tools/check_repository_secrets.py"
            and not relative_posix.startswith("tools/tests/")
        ):
            paths.append(path)
    return paths


def exposed_digest_hits(path: pathlib.Path, root: pathlib.Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    hits: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for marker in PRIVATE_KEY_MARKERS:
            if marker in line:
                hits.append(f"{path.relative_to(root)}:{line_number}: private-key material")
        for token in TOKEN_RE.findall(line):
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            if digest in KNOWN_EXPOSED_TOKEN_DIGESTS:
                hits.append(
                    f"{path.relative_to(root)}:{line_number}: known exposed credential or endpoint"
                )
                break
    return hits


def is_pinned_vendor_fixture(path: pathlib.Path, root: pathlib.Path) -> bool:
    relative = path.relative_to(root).as_posix()
    digest = KNOWN_VENDOR_FIXTURE_SHA256.get(relative)
    return digest is not None and hashlib.sha256(path.read_bytes()).hexdigest() == digest


def ignored_secret_path_failures(root: pathlib.Path) -> list[str]:
    failures: list[str] = []
    for relative in REQUIRED_IGNORED_SECRET_PATHS:
        completed = subprocess.run(
            ["git", "check-ignore", "--no-index", "--quiet", "--", relative],
            cwd=root,
            check=False,
        )
        if completed.returncode != 0:
            failures.append(f"{relative}: secret path is not ignored")
    return failures


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    failures = ignored_secret_path_failures(root)
    approved, approval_errors = approved_handover_files(root)
    failures.extend(approval_errors)
    for path in repository_files(root):
        if path.relative_to(root).as_posix() in approved:
            continue
        if is_pinned_vendor_fixture(path, root):
            continue
        failures.extend(exposed_digest_hits(path, root))
    if failures:
        print("Repository secret guard failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Repository secret guard passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
