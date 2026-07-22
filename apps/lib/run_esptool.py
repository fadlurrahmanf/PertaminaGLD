#!/usr/bin/env python3
"""Run the bundled Espressif esptool without PlatformIO.

The Operator bridges invoke this script with their own embedded Python.  It
adds only the checked-in ``apps/lib/esptool`` package to that interpreter,
then forwards every command-line argument to esptool unchanged.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

LIB_DIR = Path(__file__).resolve().parent
ESPTOOL_DIR = LIB_DIR / "esptool"
ESPTOOL_ENTRY = ESPTOOL_DIR / "esptool.py"
VENDOR_DIR = ESPTOOL_DIR / "vendor"


def main() -> int:
    if not ESPTOOL_ENTRY.is_file() or not (ESPTOOL_DIR / "esptool").is_dir() or not VENDOR_DIR.is_dir():
        print("ERROR: bundled apps/lib/esptool runtime is incomplete", file=sys.stderr)
        return 2
    sys.path.insert(0, str(VENDOR_DIR))
    sys.path.insert(0, str(ESPTOOL_DIR))
    sys.argv = [str(ESPTOOL_ENTRY), *sys.argv[1:]]
    runpy.run_path(str(ESPTOOL_ENTRY), run_name="__main__")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"ERROR: bundled esptool failed to start: {exc}", file=sys.stderr)
        raise SystemExit(1)
