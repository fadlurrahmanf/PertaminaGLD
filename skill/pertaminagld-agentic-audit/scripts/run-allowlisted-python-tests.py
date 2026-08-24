"""Run only explicitly supplied Python test modules.

The PowerShell audit helper verifies each module against the reviewed manifest
before invoking this runner. This file intentionally performs no discovery.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import traceback
import unittest


def load_module(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load test module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_module(path: pathlib.Path) -> tuple[int, int]:
    module = load_module(path)
    total = 0
    failures = 0

    for name in sorted(dir(module)):
        candidate = getattr(module, name)
        if not name.startswith("test_") or not callable(candidate):
            continue
        total += 1
        try:
            candidate()
            print(f"PASS {path.name}::{name}")
        except Exception:
            failures += 1
            print(f"FAIL {path.name}::{name}")
            traceback.print_exc()

    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    suite_count = suite.countTestCases()
    if suite_count:
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        total += result.testsRun
        failures += len(result.failures) + len(result.errors) + len(result.unexpectedSuccesses)

    return total, failures


def main(arguments: list[str]) -> int:
    if not arguments:
        print("No allowlisted test modules supplied", file=sys.stderr)
        return 2

    total = 0
    failures = 0
    for argument in arguments:
        path = pathlib.Path(argument).resolve(strict=True)
        module_total, module_failures = run_module(path)
        total += module_total
        failures += module_failures

    print(f"\n{total - failures}/{total} tests passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

