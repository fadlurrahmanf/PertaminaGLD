"""Independent, read-only verification of the final GLD combined workbook.

Usage: python verify_workbook.py path/to/final.xlsx [--sources path/to/excel]
Uses only Python's standard library. Does not open Excel or modify any files.
"""

import argparse
import csv
import hashlib
import io
import json
import math
import posixpath
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"s": S, "c": C, "r": R, "p": P}
SENSORS = ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"]
DEFS = [
    ("dataset-gld.csv", "Raw Awal", "Awal", 1, 8972,
     "5a42a9712614d4c935935137c3b0776146ea0079217fe6d05a4656a681e6ecbd"),
    ("dataset-gld after nulling.csv", "Raw After Nulling", "After Nulling", 2, 15747,
     "e829258301ac1c6d857bf5b88bab7cf04daf0d908a12c26178da183cc3b396f1"),
    ("dataset-gld3.csv", "Raw Cuplikan", "Cuplikan", 2, 46,
     "1c24c4f07e635fa856e49eac6c47ec1662bf0611a5b8dc91a14e237c7fc81310"),
    ("dataset-gld new 3.csv", "Raw New 3", "New 3", 5, 14414,
     "9c93369d9db76f81362e3c92548f9fc8be9425f3c3676f0e2fe5c5105f46c09b"),
    ("dataset-gld Last.csv", "Raw Last", "Last", 7, 26747,
     "ecfc0fe32ee0aa614a4dc62d04db80c1b8aad851d3970c425f126cffb4ec3877"),
]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def col_number(name):
    value = 0
    for ch in name:
        value = value * 26 + ord(ch) - 64
    return value


def close(actual, expected, context, raw=False):
    require(isinstance(actual, (float, int)) and not isinstance(actual, bool),
            f"{context}: expected numeric cell, got {actual!r}")
    require(math.isfinite(actual), f"{context}: nonfinite value")
    if raw and expected == int(expected):
        require(actual == expected, f"{context}: {actual!r} != {expected!r}")
    else:
        require(math.isclose(actual, expected, rel_tol=5e-15 if raw else 1e-9,
                             abs_tol=1e-18 if raw else 1e-11),
                f"{context}: {actual!r} != {expected!r}")


def load_sources(folder):
    data = {}
    for filename, sheet, label, profile, expected_n, expected_hash in DEFS:
        source = folder / filename
        payload = source.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        require(digest == expected_hash, f"Source changed since audit: {filename}")
        reader = csv.reader(io.StringIO(payload.decode("utf-8-sig")))
        headers = next(reader)
        require(len(headers) == 28, f"{filename}: unexpected header width")
        rows = []
        for index, fields in enumerate(reader, 2):
            require(len(fields) == 28, f"{filename}:{index}: width mismatch")
            row = [value if j == 1 else float(value) for j, value in enumerate(fields)]
            require(all(math.isfinite(v) for j, v in enumerate(row) if j != 1),
                    f"{filename}:{index}: nonfinite value")
            rows.append(row)
        require(len(rows) == expected_n, f"{filename}: not the full audited source")
        times = [row[0] for row in rows]
        require(all(b > a for a, b in zip(times, times[1:])),
                f"{filename}: nonmonotonic time")
        raw = [[row[j + 2] for row in rows] for j in range(8)]
        elapsed = [(v - times[0]) / 60000 for v in times]
        starts, ma, totals, left = [], [[] for _ in SENSORS], [0.0] * 8, 0
        # Independent timestamp-window algorithm; no workbook formula evaluation.
        for i, timestamp in enumerate(times):
            for j in range(8):
                totals[j] += raw[j][i]
            while times[left] <= timestamp - 60000:
                for j in range(8):
                    totals[j] -= raw[j][left]
                left += 1
            starts.append(left + 1)
            for j in range(8):
                ma[j].append(totals[j] / (i - left + 1))
        classes = Counter(row[10] for row in rows)
        first_lpg = next((elapsed[i] for i, row in enumerate(rows) if row[10] == 1), None)
        data[sheet] = dict(filename=filename, sheet=sheet, label=label, profile=profile,
                           path=source, hash=digest, headers=headers, rows=rows,
                           n=len(rows), times=times, elapsed=elapsed, raw=raw, ma=ma,
                           starts=starts, classes=classes, first_lpg=first_lpg,
                           max_gap=max(b - a for a, b in zip(times, times[1:])) / 1000)
    return data


def relation_map(zf, part):
    relpart = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
    if relpart not in zf.namelist():
        return {}
    out = {}
    for rel in ET.fromstring(zf.read(relpart)):
        require(rel.get("TargetMode") != "External", f"External relation in {relpart}")
        target = rel.get("Target", "")
        out[rel.get("Id")] = target.lstrip("/") if target.startswith("/") else posixpath.normpath(
            posixpath.join(posixpath.dirname(part), target))
    return out


def shared_strings(zf):
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    out = []
    with zf.open("xl/sharedStrings.xml") as stream:
        for event, element in ET.iterparse(stream, events=("end",)):
            if element.tag == f"{{{S}}}si":
                out.append("".join(node.text or "" for node in element.iter(f"{{{S}}}t")))
                element.clear()
    return out


def cell_info(cell, strings):
    kind = cell.get("t", "n")
    require(kind != "e", f"Cached Excel error at {cell.get('r')}: {cell.findtext('s:v', namespaces=NS)}")
    formula = cell.find("s:f", NS)
    raw = cell.findtext("s:v", namespaces=NS)
    if kind == "s":
        value = strings[int(raw)] if raw is not None else None
    elif kind == "inlineStr":
        value = "".join(node.text or "" for node in cell.iter(f"{{{S}}}t"))
    elif kind in ("str", "d"):
        value = raw or ""
    elif raw is None:
        value = None
    else:
        value = float(raw)
    require(value not in ("#REF!", "#VALUE!", "#DIV/0!", "#N/A", "#NAME?", "#NUM!", "#SPILL!"),
            f"Error-like cached value at {cell.get('r')}: {value}")
    return value, formula


def validate_sheets(zf, sheets, data, strings):
    summary, cached_count = {}, 0
    for sheet, part in sheets.items():
        seen_rows, d = set(), data.get(sheet)
        with zf.open(part) as stream:
            for event, element in ET.iterparse(stream, events=("end",)):
                if element.tag != f"{{{S}}}row":
                    continue
                row_number = int(element.get("r"))
                cells = {}
                for cell in element.findall("s:c", NS):
                    address = cell.get("r")
                    column = re.match(r"([A-Z]+)", address).group(1)
                    value, formula = cell_info(cell, strings)
                    cells[col_number(column)] = (value, formula)
                    if value is not None:
                        cached_count += 1
                    if sheet == "Summary":
                        summary[address] = value
                if d and row_number == 1:
                    for j, header in enumerate(d["headers"], 1):
                        require(cells.get(j, (None,))[0] == header, f"{sheet}: header {j} mismatch")
                if d and 2 <= row_number <= d["n"] + 1:
                    index = row_number - 2
                    seen_rows.add(index)
                    for j, expected in enumerate(d["rows"][index], 1):
                        value, formula = cells.get(j, (None, None))
                        require(formula is None, f"{sheet}:{row_number}:{j}: raw cell contains formula")
                        if j == 2:
                            require(value == expected, f"{sheet}:{row_number}: label differs")
                        else:
                            close(value, expected, f"{sheet}:{row_number}:{j}", raw=True)
                    value, formula = cells.get(30, (None, None))
                    close(value, d["elapsed"][index], f"{sheet}!AD{row_number}")
                    require(formula is not None, f"{sheet}!AD{row_number}: missing formula")
                    value, formula = cells.get(31, (None, None))
                    close(value, d["starts"][index], f"{sheet}!AE{row_number}")
                    text = formula.text or "" if formula is not None else ""
                    require("Summary!$C$5" in text.replace("'Summary'", "Summary"),
                            f"{sheet}!AE{row_number}: missing adjustable window reference")
                    for j in range(8):
                        value, formula = cells.get(32 + j, (None, None))
                        close(value, d["ma"][j][index], f"{sheet}: MA row {row_number}, {SENSORS[j]}")
                        text = formula.text or "" if formula is not None else ""
                        require(re.search(r"\$?AE\$?" + str(row_number) + r"\b", text),
                                f"{sheet}: MA row {row_number} does not depend on its start index")
                if d and row_number > d["n"] + 1:
                    require(not any(j <= 28 and value is not None for j, (value, _) in cells.items()),
                            f"{sheet}: extra raw rows after original data")
                element.clear()
        if d:
            require(len(seen_rows) == d["n"], f"{sheet}: missing raw/MA rows")
    close(summary.get("C5"), 1, "Summary!C5 default")
    expected_headers = ["Rekaman", "Sampel", "Durasi (menit)", "Profil nulling", "Clear", "LPG",
                        "LPG pertama (menit)", "Jeda maks. (detik)", "Sheet data"]
    for j, header in enumerate(expected_headers):
        require(summary.get(f"{chr(65+j)}8") == header, f"Summary: header {j+1}")
    for k, d in enumerate(data.values(), 9):
        require(summary.get(f"I{k}") == d["sheet"], f"Summary row {k}: raw-sheet link label")
        for column, expected in [("B", d["n"]), ("C", d["elapsed"][-1]), ("D", d["profile"]),
                                 ("E", d["classes"][0]), ("F", d["classes"][1]), ("H", d["max_gap"])]:
            close(summary.get(f"{column}{k}"), expected, f"Summary!{column}{k}")
        if d["first_lpg"] is None:
            require(summary.get(f"G{k}") == "n.a.", f"Summary!G{k}: expected no LPG")
        else:
            close(summary.get(f"G{k}"), d["first_lpg"], f"Summary!G{k}")
    return cached_count


def reference(formula, data, axis):
    pattern = r"^'([^']+)'!\$?([A-Z]+)\$?(\d+):\$?([A-Z]+)\$?(\d+)$"
    match = re.match(pattern, (formula or "").lstrip("="))
    require(match is not None, f"Invalid chart numeric reference: {formula!r}")
    name, col1, first, col2, last = match.groups()
    require(name in data, f"Chart points to unknown sheet {name}")
    d = data[name]
    require(col1 == col2 and int(first) == 2 and int(last) == d["n"] + 1,
            f"Chart reference not full source height: {formula}")
    column = col_number(col1)
    if axis == "xVal":
        require(column == 30, f"Chart x axis must use elapsed minutes: {formula}")
        return d["elapsed"], (name, "x", None)
    if 3 <= column <= 10:
        j = column - 3
        return d["raw"][j], (name, "raw", j)
    require(32 <= column <= 39, f"Chart y axis is not voltage/MA: {formula}")
    j = column - 32
    return d["ma"][j], (name, "ma", j)


def validate_charts(zf, sheets, data):
    chart_parts = sorted(n for n in zf.namelist() if re.match(r"xl/charts/chart\d+\.xml$", n))
    require(len(chart_parts) == 26, f"Expected26 native charts, found{len(chart_parts)}")
    owners = {}
    for sheet, part in sheets.items():
        for drawing in relation_map(zf, part).values():
            if not drawing.startswith("xl/drawings/") or not drawing.endswith(".xml"):
                continue
            for target in relation_map(zf, drawing).values():
                if target in chart_parts:
                    require(target not in owners, f"Chart has duplicate owner: {target}")
                    owners[target] = sheet
    require(Counter(owners.values()) == Counter({"Summary": 16, "Grafik Rekaman": 10}),
            f"Chart placement mismatch: {dict(Counter(owners.values()))}")
    identities, total_points, total_series = set(), 0, 0
    for part in chart_parts:
        stack, axis, current, cache, series, scatter = [], None, None, None, [], False
        with zf.open(part) as stream:
            for event, element in ET.iterparse(stream, events=("start", "end")):
                local = element.tag.rsplit("}", 1)[-1]
                if event == "start":
                    stack.append(local)
                    if local == "scatterChart":
                        scatter = True
                    elif local == "ser":
                        current = {}
                    elif local in ("xVal", "yVal"):
                        axis = local
                    elif local == "numRef" and axis:
                        cache = {"count": 0, "declared": None, "values": None, "id": None}
                    continue
                if local == "f" and cache is not None and axis and "numRef" in stack:
                    cache["values"], cache["id"] = reference(element.text, data, axis)
                elif local == "ptCount" and cache is not None and "numCache" in stack:
                    cache["declared"] = int(element.get("val"))
                elif local == "pt" and cache is not None and "numCache" in stack:
                    require(cache["values"] is not None, f"{part}: cache lacks source formula")
                    index = int(element.get("idx"))
                    require(index == cache["count"] and index < len(cache["values"]),
                            f"{part}: sparse, duplicate or extra cached point {index}")
                    value = float(element.findtext("c:v", namespaces=NS))
                    close(value, cache["values"][index], f"{part} {axis} point {index}")
                    cache["count"] += 1
                    total_points += 1
                    element.clear()
                elif local == "numRef" and axis:
                    require(cache and cache["values"] is not None, f"{part}: missing numRef/cache")
                    require(cache["count"] == cache["declared"] == len(cache["values"]),
                            f"{part}: partial chart cache")
                    current[axis] = cache["id"]
                    cache = None
                    element.clear()
                elif local in ("numLit", "strRef", "strLit") and axis:
                    raise AssertionError(f"{part}: {axis} must use numRef")
                elif local in ("xVal", "yVal"):
                    axis = None
                elif local == "ser":
                    require(set(current) == {"xVal", "yVal"}, f"{part}: incomplete scatter series")
                    require(current["xVal"][0] == current["yVal"][0], f"{part}: cross-source x/y")
                    series.append(current["yVal"])
                    total_series += 1
                    current = None
                    element.clear()
                stack.pop()
        require(scatter, f"{part}: not native XY scatter chart")
        if owners[part] == "Summary":
            require(len(series) == 5 and {x[0] for x in series} == set(data),
                    f"{part}: combined chart must contain each source exactly once")
            pairs = {(mode, sensor) for _, mode, sensor in series}
            require(len(pairs) == 1, f"{part}: combined chart mixes sensor/mode")
            mode, sensor = next(iter(pairs))
            identity = ("combined", mode, sensor)
        else:
            require(len(series) == 8 and {x[2] for x in series} == set(range(8)),
                    f"{part}: recording chart must contain all8 sensors exactly once")
            pairs = {(name, mode) for name, mode, _ in series}
            require(len(pairs) == 1, f"{part}: recording chart mixes source/mode")
            name, mode = next(iter(pairs))
            identity = ("individual", name, mode)
        require(identity not in identities, f"Duplicate chart coverage: {identity}")
        identities.add(identity)
    require(total_series == 160, f"Expected160 series, found{total_series}")
    return {"charts": len(chart_parts), "series": total_series, "cached_points_checked": total_points}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--sources", type=Path, default=Path(__file__).resolve().parents[3] / "excel")
    args = parser.parse_args()
    data = load_sources(args.sources)
    with zipfile.ZipFile(args.workbook) as zf:
        require(not any("externalLinks/" in n for n in zf.namelist()), "Workbook has external links")
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = relation_map(zf, "xl/workbook.xml")
        sheets = {node.get("name"): rels[node.get(f"{{{R}}}id")]
                  for node in workbook.findall("s:sheets/s:sheet", NS)}
        expected = ["Summary", "Grafik Rekaman", *data]
        require(list(sheets) == expected, f"Unexpected sheet order/names: {list(sheets)}")
        strings = shared_strings(zf)
        cached_cells = validate_sheets(zf, sheets, data, strings)
        chart_results = validate_charts(zf, sheets, data)
    # Catch a source edited while the check was running.
    for d in data.values():
        require(hashlib.sha256(d["path"].read_bytes()).hexdigest() == d["hash"],
                f"Source changed during verification: {d['filename']}")
    print(json.dumps({"status": "PASS", "workbook": str(args.workbook.resolve()),
                      "sheets": expected, "raw_rows": sum(d["n"] for d in data.values()),
                      "numeric_raw_cells": sum(d["n"] * 27 for d in data.values()),
                      "ma_cells_checked": sum(d["n"] * 8 for d in data.values()),
                      "cached_cells_scanned": cached_cells, **chart_results,
                      "source_hashes_unchanged": True,
                      "window": "1minute; (current_ms-60000,current_ms]; partial available samples"}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2), file=sys.stderr)
        raise
