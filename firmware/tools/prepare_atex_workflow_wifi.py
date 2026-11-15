"""Prepare an isolated ATEX candidate header using the GLD1 workflow resolver.

This helper is not wired into builds or releases. It creates no credential
configuration and does not rotate an existing candidate header.

Use only in a locally trusted checkout and private workspace. Path checks do not
prevent concurrent filesystem replacement (TOCTOU); inherited ACLs are not
modified. Generated headers and firmware binaries contain the shared password.
"""
from __future__ import annotations

import hmac
import importlib.util
import json
from pathlib import Path
import re
import stat

CANDIDATES = tuple(f"gld_atex_model_{n}_workflow_candidate" for n in (1, 2, 3))
_ERROR = "ATEX workflow credential preparation failed"
_PATTERN = re.compile(r"[A-Za-z0-9_-]{8,63}\Z")


def _valid_password(value):
    return (isinstance(value, str) and _PATTERN.fullmatch(value) is not None
            and not value.upper().startswith("SYNTHETIC_"))


def _reject_redirects(path):
    """Reject existing symlinks and Windows reparse points, including dangling ones."""
    path = Path(path).absolute()
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError()


def _prepare(project, build, environment):
    if environment not in CANDIDATES:
        raise ValueError()
    project = Path(project).absolute()
    _reject_redirects(project)
    _reject_redirects(project / "tools" / Path(__file__).name)
    if not project.is_dir() or (project / "tools" / Path(__file__).name).resolve() != Path(__file__).resolve():
        raise ValueError()
    root = project.parent
    expected = project / ".pio" / "build-atex-private-candidates" / environment
    build = Path(build).absolute()
    _reject_redirects(build)
    if build.resolve() != expected or expected.resolve() != expected:
        raise ValueError()
    header = expected / "private-atex-workflow-wifi" / "GldDatasetWorkflowWifiSecrets.h"
    _reject_redirects(header)
    if header.resolve() != header:
        raise ValueError()

    module_path = root / "apps" / "gld-operator" / "workflow_credentials.py"
    _reject_redirects(module_path)
    _reject_redirects(root / "apps/gld-operator/workflow-connection-profiles.json")
    for number in (1, 2, 3):
        name = f"gld_model_{number}_dataset_workflow_wifi"
        _reject_redirects(project / ".pio/gld-dataset-workflow-wifi" / name / "credentials.local.json")
        package = root / "apps/operator-hub/firmware-packages" / name / "latest"
        _reject_redirects(package / "manifest.json")
        _reject_redirects(package / "firmware.bin")
    spec = importlib.util.spec_from_file_location("_gld_trusted_workflow_resolver", module_path)
    if spec is None or spec.loader is None:
        raise ValueError()
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    password = module.resolve_workflow_password(root)
    if not _valid_password(password):
        raise ValueError()

    paths = [project / ".pio" / "gld-dataset-workflow-wifi" / name / "credentials.local.json"
             for name in CANDIDATES]
    for path in paths:
        _reject_redirects(path)
    if any(path.exists() for path in paths):
        for name, path in zip(CANDIDATES, paths):
            if not path.is_file() or path.stat().st_size > 16384:
                raise ValueError()
            value = json.loads(path.read_text(encoding="utf-8"))
            candidate_password = value.get("password") if isinstance(value, dict) else None
            if (not isinstance(value, dict) or value.get("environment") != name
                    or value.get("protocol") != "gld-dataset-wifi/3"
                    or value.get("username") != "gld"
                    or not _valid_password(candidate_password)
                    or not hmac.compare_digest(password, candidate_password)):
                raise ValueError()

    content = '#pragma once\n#define GLD_DATASET_WORKFLOW_PRIVATE_PASSWORD ' + json.dumps(password) + '\n'
    header.parent.mkdir(parents=True, exist_ok=True)
    try:
        with header.open("x", encoding="utf-8", newline="\n") as output:
            output.write(content)
    except FileExistsError:
        if not header.is_file() or not hmac.compare_digest(header.read_bytes(), content.encode("utf-8")):
            raise ValueError()
    return header


def prepare(project, build, environment):
    """Return a candidate header path; failures never expose credential details."""
    try:
        return _prepare(project, build, environment)
    except Exception:
        raise RuntimeError(_ERROR) from None
