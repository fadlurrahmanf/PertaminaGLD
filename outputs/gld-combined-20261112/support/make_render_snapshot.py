"""Make a cache-only XLSX byte snapshot for rendering, never for delivery.

Usage: python make_render_snapshot.py FINAL.xlsx [--output render_snapshot.bin]
The source is opened read-only. Only worksheet formula elements are removed;
cached cell values/types/styles and all chart/drawing parts remain unchanged.
No Excel automation, workbook recalculation, or third-party packages are used.
"""

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

# Formula text is XML-escaped, so a literal closing f tag is unambiguous.
# Support both the default spreadsheet namespace and serialized XML prefixes.
FORMULA = re.compile(
    rb"<(?P<tag>(?:[A-Za-z_][A-Za-z0-9_.-]*:)?f)(?=[\s/>])"
    rb"(?:[^>]*?/\s*>|[^>]*>.*?</(?P=tag)\s*>)",
    re.DOTALL,
)
SHEET = re.compile(r"xl/worksheets/sheet\d+\.xml$")


def digest(path):
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parent / "render_snapshot.bin")
    args = parser.parse_args()
    source, target = args.workbook.resolve(), args.output.resolve()
    if source == target:
        raise ValueError("The QA snapshot must never overwrite the deliverable")
    before = digest(source)
    removed = {}
    preserved = {}
    # One ZIP member at a time, byte-regex only: no large worksheet XML DOM.
    with zipfile.ZipFile(source, "r") as zin, zipfile.ZipFile(target, "w") as zout:
        for member in zin.infolist():
            payload = zin.read(member.filename)
            if SHEET.fullmatch(member.filename):
                payload, count = FORMULA.subn(b"", payload)
                removed[member.filename] = count
            if member.filename.startswith(("xl/charts/", "xl/drawings/")):
                preserved[member.filename] = hashlib.sha256(payload).hexdigest()
            zout.writestr(member, payload)
    if digest(source) != before:
        raise RuntimeError("Source workbook changed while preparing the QA snapshot")
    with zipfile.ZipFile(target) as zcheck:
        for name, expected in preserved.items():
            if hashlib.sha256(zcheck.read(name)).hexdigest() != expected:
                raise RuntimeError(f"Chart/drawing unexpectedly changed: {name}")
        for name in removed:
            if FORMULA.search(zcheck.read(name)):
                raise RuntimeError(f"Worksheet formula remained in QA snapshot: {name}")
    print(json.dumps({
        "status": "PASS", "purpose": "cache-only rendering QA; never deliver",
        "source": str(source), "source_sha256": before,
        "source_unchanged": True, "snapshot": str(target),
        "worksheet_formulas_removed": removed,
        "total_formulas_removed": sum(removed.values()),
        "chart_drawing_parts_preserved_byte_for_byte": len(preserved),
        "cached_values_cell_types_styles_preserved": True,
    }, indent=2))


if __name__ == "__main__":
    main()
