import importlib.util
import pathlib
import sys
import traceback


def load_module(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent
    test_files = sorted(root.glob("test_*.py"))
    failures = 0
    total = 0

    for test_file in test_files:
        module = load_module(test_file)
        for name in sorted(dir(module)):
            if not name.startswith("test_"):
                continue
            fn = getattr(module, name)
            if not callable(fn):
                continue
            total += 1
            try:
                fn()
                print(f"PASS {test_file.name}::{name}")
            except Exception:
                failures += 1
                print(f"FAIL {test_file.name}::{name}")
                traceback.print_exc()

    print(f"\n{total - failures}/{total} tests passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
