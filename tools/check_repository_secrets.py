#!/usr/bin/env python3
"""Fail when tracked/releasable files contain known exposed secrets.

Known values are represented only by SHA-256 digests so the scanner does not
reintroduce the credentials it is intended to remove. This is a focused guard,
not a substitute for external secret scanning or credential rotation.
"""

from __future__ import annotations

import hashlib
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
    for path in repository_files(root):
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
