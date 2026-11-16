"""Per-Windows-user, DPAPI-protected settings for the local Aedes broker."""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path


class _Blob(ctypes.Structure):
    _fields_ = [("size", ctypes.c_uint32), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data: bytes, protect: bool) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Windows user credential protection is unavailable")
    source_buffer = ctypes.create_string_buffer(data, len(data))
    source = _Blob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = _Blob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    operation = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    # CRYPTPROTECT_UI_FORBIDDEN prevents an unattended bridge from showing UI.
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise RuntimeError("Windows could not protect or read the local broker profile")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel32.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


def profile_path() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if not root:
        raise RuntimeError("Windows local application data folder is unavailable")
    return Path(root) / "PertaminaGLD" / "aedes-broker.dpapi"


def save_profile(profile: dict) -> None:
    path = profile_path()
    ciphertext = _crypt(json.dumps(profile, separators=(",", ":")).encode("utf-8"), True)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    try:
        temp.write_bytes(ciphertext)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def load_profile() -> dict | None:
    path = profile_path()
    if not path.is_file():
        return None
    value = json.loads(_crypt(path.read_bytes(), False).decode("utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("username"), str) or not isinstance(value.get("password"), str):
        raise RuntimeError("Local broker profile is invalid")
    port = value.get("port")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise RuntimeError("Local broker profile is invalid")
    return {"username": value["username"], "password": value["password"], "port": port,
            "topicRoot": value.get("topicRoot") or "gld/gateway"}
