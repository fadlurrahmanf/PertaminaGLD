"""Repair artifact-tool scatter-chart bindings in an existing XLSX export.

This is an export repair, not a workbook builder. Uses only Python stdlib.
Run only after the full workbook and matching chart manifest have been exported.
The original workbook is replaced atomically only after all checks pass.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import posixpath
import re
import tempfile
import xml.etree.ElementTree as ET
import xml.sax
from xml.sax.handler import ContentHandler, feature_external_ges, feature_namespaces
from xml.sax.saxutils import XMLGenerator
import zipfile


C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"c": C, "a": A, "s": S, "r": R, "p": P}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def q(namespace, name):
    return "{" + namespace + "}" + name


def require(condition, message):
    if not condition:
        raise ValueError(message)


def serialize(root):
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def title_of(root):
    title = root.find("c:chart/c:title", NS)
    return "" if title is None else "".join(node.text or "" for node in title.findall(".//a:t", NS))


def numeric_text(value):
    require(isinstance(value, (float, int)) and not isinstance(value, bool), "Cache contains a non-number")
    require(math.isfinite(value), "Cache contains NaN or infinity")
    return format(value, ".17g")


TARGET_CELL = re.compile(r"^(AE|AF|AG|AH|AI|AJ|AK|AL|AM)([1-9][0-9]*)$")
MA_COLUMNS = dict(zip(("AF", "AG", "AH", "AI", "AJ", "AK", "AL", "AM"), "CDEFGHIJ"))


def expected_cell_formula(reference, last):
    match = TARGET_CELL.fullmatch(reference)
    if match is None:
        return None
    column, row_text = match.groups()
    row = int(row_text)
    if row < 2 or row > last:
        return None
    if column == "AE":
        return (f"IF(AND(ISNUMBER(Summary!$C$5),Summary!$C$5>0),"
                f"IF(A{row}-Summary!$C$5*60000<$A$2,1,"
                f"MATCH(A{row}-Summary!$C$5*60000,$A$2:$A${last},1)+1),NA())")
    source = MA_COLUMNS[column]
    return f"AVERAGE(INDEX(${source}$2:${source}${last},$AE{row}):{source}{row})"


class FormulaPatch(XMLGenerator):
    """Copy one worksheet as XML events, adding formulas before numeric caches.

    Uses no worksheet DOM: even the largest sheet stays bounded by input/output
    buffers rather than retaining a million-cell object tree. Existing styles,
    cell values, AD formulas, and all other XML are preserved semantically.
    """

    def __init__(self, output, last, cell_styles=None):
        super().__init__(output, encoding="utf-8", short_empty_elements=True)
        self.last = last
        self.cell_styles = cell_styles or {}
        self.target = None
        self.inside_value = False
        self.cache_text = []
        self.injected = False
        self.helper_count = self.ma_count = 0
        self.digest = hashlib.sha256()

    def startElement(self, name, attrs):
        local = name.rsplit(":", 1)[-1]
        if local == "c":
            reference = attrs.get("r", "")
            if reference in self.cell_styles:
                attrs = dict(attrs.items())
                attrs["s"] = self.cell_styles[reference]
            formula = expected_cell_formula(reference, self.last)
            self.target = (reference, formula) if formula is not None else None
            self.injected = False
            self.inside_value = False
            self.cache_text = []
            if self.target:
                require(attrs.get("t", "n") == "n", "Expected numeric cached formula cell: " + reference)
        if self.target and local == "f":
            raise ValueError("Formula patch expected an unmodified numeric cache: " + self.target[0])
        if self.target and local == "v":
            require(not self.injected, "Duplicate cached value in " + self.target[0])
            prefix = name[:-1]  # 'v' -> '', 's:v' -> 's:'
            super().startElement(prefix + "f", {})
            super().characters(self.target[1])
            super().endElement(prefix + "f")
            self.injected = True
            self.inside_value = True
        super().startElement(name, attrs)

    def characters(self, content):
        if self.target and self.inside_value:
            self.cache_text.append(content)
        super().characters(content)

    def endElement(self, name):
        local = name.rsplit(":", 1)[-1]
        if local == "v":
            self.inside_value = False
        if local == "c" and self.target:
            reference = self.target[0]
            require(self.injected, "Numeric cache missing for " + reference)
            value = "".join(self.cache_text).strip()
            require(math.isfinite(float(value)), "Non-finite numeric cache: " + reference)
            self.digest.update((reference + "=" + value + "\n").encode("utf-8"))
            if reference.startswith("AE"):
                self.helper_count += 1
            else:
                self.ma_count += 1
        super().endElement(name)
        if local == "c":
            self.target = None


class FormulaAudit(ContentHandler):
    """Read back every injected formula and numeric cache without a sheet DOM."""

    def __init__(self, last):
        super().__init__()
        self.last = last
        self.target = None
        self.part = None
        self.formula_text = []
        self.cache_text = []
        self.helper_count = self.ma_count = 0
        self.digest = hashlib.sha256()

    def startElement(self, name, attrs):
        local = name.rsplit(":", 1)[-1]
        if local == "c":
            reference = attrs.get("r", "")
            formula = expected_cell_formula(reference, self.last)
            self.target = (reference, formula) if formula is not None else None
            self.formula_text, self.cache_text = [], []
            self.part = None
        elif self.target and local in ("f", "v"):
            self.part = local

    def characters(self, content):
        if self.target and self.part == "f":
            self.formula_text.append(content)
        elif self.target and self.part == "v":
            self.cache_text.append(content)

    def endElement(self, name):
        local = name.rsplit(":", 1)[-1]
        if local in ("f", "v"):
            self.part = None
        if local == "c" and self.target:
            reference, expected = self.target
            require("".join(self.formula_text) == expected, "Native MA formula mismatch: " + reference)
            value = "".join(self.cache_text).strip()
            require(math.isfinite(float(value)), "Numeric formula cache missing: " + reference)
            self.digest.update((reference + "=" + value + "\n").encode("utf-8"))
            if reference.startswith("AE"):
                self.helper_count += 1
            else:
                self.ma_count += 1
            self.target = None


def parse_xml_events(data, handler):
    parser = xml.sax.make_parser()
    parser.setFeature(feature_namespaces, False)
    parser.setFeature(feature_external_ges, False)
    parser.setContentHandler(handler)
    parser.parse(io.BytesIO(data))


def repair_raw_formulas(data, dataset, cell_styles=None):
    output = io.BytesIO()
    patch = FormulaPatch(output, dataset["n"] + 1, cell_styles)
    parse_xml_events(data, patch)
    require(patch.helper_count == dataset["n"] and patch.ma_count == 8 * dataset["n"],
            "Not all native helper/MA formula cells were patched: " + dataset["sheetName"])
    print(f"PATCHED {dataset['sheetName']}: {patch.helper_count:,} helper + {patch.ma_count:,} MA formulas; numeric caches preserved", flush=True)
    return output.getvalue(), patch.digest.hexdigest()


class TargetScanComplete(Exception):
    pass


class TargetCellReader(ContentHandler):
    """Inspect only requested cells in the small top-of-sheet summary area."""

    def __init__(self, targets, shared_strings):
        super().__init__()
        self.targets = set(targets)
        self.max_row = max(int(re.search(r"[0-9]+$", ref).group()) for ref in targets)
        self.shared_strings = shared_strings
        self.found = {}
        self.current = None
        self.field = None
        self.value = []

    def startElement(self, name, attrs):
        local = name.rsplit(":", 1)[-1]
        if local == "row" and int(attrs.get("r", "0")) > self.max_row:
            raise TargetScanComplete()
        if local == "c":
            ref = attrs.get("r", "")
            self.current = (ref, attrs.get("s", "0"), attrs.get("t", "n")) if ref in self.targets else None
            self.value = []
            self.field = None
        elif self.current and local in ("v", "t"):
            self.field = local

    def characters(self, content):
        if self.current and self.field:
            self.value.append(content)

    def endElement(self, name):
        local = name.rsplit(":", 1)[-1]
        if local in ("v", "t"):
            self.field = None
        if local == "c" and self.current:
            ref, style, kind = self.current
            value = "".join(self.value)
            if kind == "s":
                value = self.shared_strings[int(value)]
            self.found[ref] = {"style": style, "value": value}
            self.current = None


def read_shared_strings(archive):
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(node.text or "" for node in item.iter(q(S, "t"))) for item in root]


def read_target_cells(archive, filename, targets, shared_strings):
    handler = TargetCellReader(targets, shared_strings)
    parser = xml.sax.make_parser()
    parser.setFeature(feature_namespaces, False)
    parser.setFeature(feature_external_ges, False)
    parser.setContentHandler(handler)
    try:
        with archive.open(filename) as stream:
            parser.parse(stream)
    except TargetScanComplete:
        pass
    return handler.found


def prepare_right_alignment(archive, sheets, datasets):
    """Clone only styles needed by explicitly requested n.a. result cells."""
    root = ET.fromstring(archive.read("xl/styles.xml"))
    cell_xfs = root.find("s:cellXfs", NS)
    require(cell_xfs is not None, "Workbook cellXfs missing")
    shared_strings = read_shared_strings(archive)
    targets = {sheets["Summary"]: [f"D{row}" for row in range(22, 30)] + [f"G{row}" for row in range(9, 14)]}
    for dataset in datasets:
        refs = ["AP7"]
        if dataset["file"] == "dataset-gld3.csv":
            refs += [f"AR{row}" for row in range(11, 19)]
        targets[sheets[dataset["sheetName"]]] = refs
    existing = {ET.tostring(item): str(index) for index, item in enumerate(cell_xfs)}
    clones, changes = {}, {}
    original_count = len(cell_xfs)
    for filename, refs in targets.items():
        inspected = read_target_cells(archive, filename, refs, shared_strings)
        sheet_changes = {}
        for ref, info in inspected.items():
            if info["value"] != "n.a.":
                continue
            style = info["style"]
            if style not in clones:
                require(0 <= int(style) < original_count, "Invalid original cell style ID")
                clone = copy.deepcopy(cell_xfs[int(style)])
                alignment = clone.find("s:alignment", NS)
                if alignment is None:
                    alignment = ET.Element(q(S, "alignment"))
                    position = next((i for i, child in enumerate(clone) if child.tag in (q(S, "protection"), q(S, "extLst"))), len(clone))
                    clone.insert(position, alignment)
                alignment.set("horizontal", "right")
                clone.set("applyAlignment", "1")
                key = ET.tostring(clone)
                if key not in existing:
                    existing[key] = str(len(cell_xfs))
                    cell_xfs.append(clone)
                clones[style] = existing[key]
            sheet_changes[ref] = clones[style]
        if sheet_changes:
            changes[filename] = sheet_changes
    cell_xfs.set("count", str(len(cell_xfs)))
    print(f"FORMAT: right-align {sum(map(len, changes.values()))} n.a. cells using {len(cell_xfs) - original_count} deduplicated style clones", flush=True)
    return serialize(root), changes


def source_values(spec, datasets):
    index, sensor, mode = spec["dataset"], spec["sensor"], spec["mode"]
    require(isinstance(index, int) and 0 <= index < len(datasets), "Invalid dataset index")
    require(isinstance(sensor, int) and 0 <= sensor < 8, "Invalid sensor index")
    require(mode in ("raw", "ma"), "Invalid series mode")
    dataset = datasets[index]
    x, y = dataset["elapsed"], dataset[mode][sensor]
    require(len(x) == len(y) == dataset["n"], "Manifest cache length differs from full dataset length")
    return x, y


def check_formula(formula, dataset):
    # Exact full range is required, not a sampled range or literal data array.
    match = re.fullmatch(r"'((?:[^']|'')+)'!\$([A-Z]+)\$(\d+):\$([A-Z]+)\$(\d+)", formula)
    require(match is not None, "Unsupported chart range formula: " + formula)
    sheet, column1, start, column2, end = match.groups()
    require(sheet.replace("''", "'") == dataset["sheetName"], "Chart formula points to the wrong dataset")
    require(column1 == column2 and int(start) == 2 and int(end) == dataset["n"] + 1,
            "Chart formula must include every source row: " + formula)


def add_numeric_reference(parent, name, formula, values):
    container = ET.SubElement(parent, q(C, name))
    reference = ET.SubElement(container, q(C, "numRef"))
    ET.SubElement(reference, q(C, "f")).text = formula
    cache = ET.SubElement(reference, q(C, "numCache"))
    ET.SubElement(cache, q(C, "formatCode")).text = "General"
    ET.SubElement(cache, q(C, "ptCount"), {"val": str(len(values))})
    for index, value in enumerate(values):
        point = ET.SubElement(cache, q(C, "pt"), {"idx": str(index)})
        ET.SubElement(point, q(C, "v")).text = numeric_text(value)


AXIS_ORDER = ["axId", "scaling", "delete", "axPos", "majorGridlines", "minorGridlines",
              "title", "numFmt", "majorTickMark", "minorTickMark", "tickLblPos", "spPr",
              "txPr", "crossAx", "crosses", "crossesAt", "crossBetween", "majorUnit",
              "minorUnit", "dispUnits", "extLst"]


def set_ordered(parent, namespace, name, attrs, order):
    for element in list(parent):
        if element.tag == q(namespace, name):
            parent.remove(element)
    element = ET.Element(q(namespace, name), attrs)
    rank = order.index(name)
    insertion = len(parent)
    for index, child in enumerate(parent):
        local = child.tag.rsplit("}", 1)[-1]
        if local in order and order.index(local) > rank:
            insertion = index
            break
    parent.insert(insertion, element)
    return element


def repair_chart(data, manifest_chart, datasets):
    root = ET.fromstring(data)
    plot = root.find("c:chart/c:plotArea", NS)
    require(plot is not None, "Chart has no plotArea")
    scatter = plot.find("c:scatterChart", NS)
    require(scatter is not None, "Expected a native scatterChart: " + manifest_chart["title"])
    require(len(plot.findall("c:scatterChart", NS)) == 1, "Multiple scatter groups are not supported")
    style = scatter.find("c:scatterStyle", NS)
    if style is None:
        style = ET.Element(q(C, "scatterStyle"))
        scatter.insert(0, style)
    style.set("val", "line")
    # Exporter may emit no series at all. Rebuild native series from the manifest.
    for element in list(scatter):
        if element.tag == q(C, "ser"):
            scatter.remove(element)
    insertion = next((i for i, el in enumerate(scatter) if el.tag in
                      (q(C, "dLbls"), q(C, "axId"), q(C, "extLst"))), len(scatter))
    for index, spec in enumerate(manifest_chart["series"]):
        x, y = source_values(spec, datasets)
        dataset = datasets[spec["dataset"]]
        for field in ("xFormula", "yFormula"):
            check_formula(spec[field], dataset)
        color = spec["color"].lstrip("#").upper()
        require(re.fullmatch(r"[0-9A-F]{6}", color) is not None, "Invalid line color")
        ser = ET.Element(q(C, "ser"))
        ET.SubElement(ser, q(C, "idx"), {"val": str(index)})
        ET.SubElement(ser, q(C, "order"), {"val": str(index)})
        tx = ET.SubElement(ser, q(C, "tx"))
        ET.SubElement(tx, q(C, "v")).text = spec["name"]
        shape = ET.SubElement(ser, q(C, "spPr"))
        line = ET.SubElement(shape, q(A, "ln"), {"w": "12700"})
        fill = ET.SubElement(line, q(A, "solidFill"))
        ET.SubElement(fill, q(A, "srgbClr"), {"val": color})
        ET.SubElement(line, q(A, "prstDash"), {"val": "solid"})
        marker = ET.SubElement(ser, q(C, "marker"))
        ET.SubElement(marker, q(C, "symbol"), {"val": "none"})
        add_numeric_reference(ser, "xVal", spec["xFormula"], x)
        add_numeric_reference(ser, "yVal", spec["yFormula"], y)
        ET.SubElement(ser, q(C, "smooth"), {"val": "0"})
        scatter.insert(insertion + index, ser)
    axes = plot.findall("c:valAx", NS)
    require(len(axes) == 2, "Expected two numeric scatter axes")
    for axis in axes:
        position = axis.find("c:axPos", NS)
        require(position is not None, "Numeric axis position missing")
        if position.get("val") in ("b", "t"):
            set_ordered(axis, C, "tickLblPos", {"val": "low"}, AXIS_ORDER)
        # crosses on each axis controls where its perpendicular axis crosses it.
        # min on Y places the horizontal axis below negative readings as well.
        for old in list(axis.findall("c:crossesAt", NS)):
            axis.remove(old)
        set_ordered(axis, C, "crosses", {"val": "min"}, AXIS_ORDER)
    return serialize(root)


SHEET_ORDER = ["sheetPr", "dimension", "sheetViews", "sheetFormatPr", "cols", "sheetData",
               "sheetCalcPr", "sheetProtection", "protectedRanges", "scenarios", "autoFilter",
               "sortState", "dataConsolidate", "customSheetViews", "mergeCells", "phoneticPr",
               "conditionalFormatting", "dataValidations", "hyperlinks", "printOptions",
               "pageMargins", "pageSetup", "headerFooter", "rowBreaks", "colBreaks",
               "customProperties", "cellWatches", "ignoredErrors", "smartTags", "drawing",
               "legacyDrawing", "legacyDrawingHF", "picture", "oleObjects", "controls",
               "webPublishItems", "tableParts", "extLst"]

X_AXIS_GUIDE = ("Rentang tampilan: pilih sumbu X > Format Axis > Bounds > Minimum/Maximum (menit). "
                "Default: seluruh rekaman.")


def repair_summary(data, datasets, cell_styles=None):
    root = ET.fromstring(data)
    sheet_data = root.find("s:sheetData", NS)
    require(sheet_data is not None, "Summary sheetData missing")
    for reference, style in (cell_styles or {}).items():
        cell = sheet_data.find(".//s:c[@r='" + reference + "']", NS)
        require(cell is not None, "Right-alignment target missing: " + reference)
        cell.set("s", style)
    row19 = sheet_data.find("s:row[@r='19']", NS)
    if row19 is None:
        row19 = ET.Element(q(S, "row"), {"r": "19"})
        position = next((i for i, row in enumerate(sheet_data) if int(row.get("r", "0")) > 19), len(sheet_data))
        sheet_data.insert(position, row19)
    guide_cell = row19.find("s:c[@r='A19']", NS)
    if guide_cell is None:
        attrs = {"r": "A19"}
        previous = sheet_data.find("s:row[@r='18']/s:c[@r='A18']", NS)
        if previous is not None and previous.get("s") is not None:
            attrs["s"] = previous.get("s")
        guide_cell = ET.Element(q(S, "c"), attrs)
        row19.insert(0, guide_cell)
    # The builder reserves row 19 for this single-line note. Do not overwrite
    # other content or change its font/height; blank styled cells allow overflow.
    for cell in row19:
        if cell is not guide_cell:
            require(not any(cell.find("s:" + name, NS) is not None for name in ("v", "f", "is")),
                    "Summary row 19 contains other content; refusing an overlapping note")
    for child in list(guide_cell):
        if child.tag in (q(S, "v"), q(S, "f"), q(S, "is")):
            guide_cell.remove(child)
    guide_cell.set("t", "inlineStr")
    inline = ET.SubElement(guide_cell, q(S, "is"))
    ET.SubElement(inline, q(S, "t")).text = X_AXIS_GUIDE
    validations = root.find("s:dataValidations", NS)
    if validations is None:
        validations = set_ordered(root, S, "dataValidations", {}, SHEET_ORDER)
    for item in list(validations):
        refs = item.get("sqref", "").split()
        if "C5" in refs:
            refs.remove("C5")
            if refs:
                item.set("sqref", " ".join(refs))
            else:
                validations.remove(item)
    validation = ET.SubElement(validations, q(S, "dataValidation"), {
        "type": "decimal", "operator": "greaterThan", "errorStyle": "stop",
        "allowBlank": "0", "showInputMessage": "1", "showErrorMessage": "1",
        "errorTitle": "Jendela MA tidak valid",
        "error": "Masukkan angka lebih besar dari 0 menit.",
        "promptTitle": "Jendela moving average (menit)",
        "prompt": "Masukkan angka positif, misalnya 0.5, 1, atau 5 menit.", "sqref": "C5"})
    ET.SubElement(validation, q(S, "formula1")).text = "0"
    validations.set("count", str(len(validations)))
    links = root.find("s:hyperlinks", NS)
    if links is None:
        links = set_ordered(root, S, "hyperlinks", {}, SHEET_ORDER)
    for index, dataset in enumerate(datasets):
        cell = "I" + str(9 + index)
        for old in list(links):
            if old.get("ref") == cell:
                links.remove(old)
        ET.SubElement(links, q(S, "hyperlink"), {
            "ref": cell, "location": "'" + dataset["sheetName"].replace("'", "''") + "'!A1",
            "tooltip": "Buka data lengkap: " + dataset["label"]})
    return serialize(root)


def workbook_sheets(archive):
    root = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    paths = {}
    for relation in relationships:
        if relation.get("TargetMode") == "External":
            continue
        target = relation.get("Target", "")
        paths[relation.get("Id")] = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
    sheets = {sheet.get("name"): paths[sheet.get(q(R, "id"))]
              for sheet in root.findall("s:sheets/s:sheet", NS)}
    return root, sheets


def repair_calculation(root):
    calc = root.find("s:calcPr", NS)
    if calc is None:
        order = ["fileVersion", "fileSharing", "workbookPr", "workbookProtection", "bookViews",
                 "sheets", "functionGroups", "externalReferences", "definedNames", "calcPr",
                 "oleSize", "customWorkbookViews", "pivotCaches", "smartTagPr", "smartTagTypes",
                 "webPublishing", "fileRecoveryPr", "webPublishObjects", "extLst"]
        calc = set_ordered(root, S, "calcPr", {}, order)
    calc.set("calcMode", "auto")
    calc.set("fullCalcOnLoad", "1")
    calc.set("forceFullCalc", "1")
    return serialize(root)


def validate_chart(data, spec, datasets):
    root = ET.fromstring(data)
    require(title_of(root) == spec["title"], "Chart title changed")
    scatter = root.find("c:chart/c:plotArea/c:scatterChart", NS)
    require(scatter is not None and scatter.find("c:scatterStyle", NS).get("val") == "line", "Scatter style is not line")
    series = scatter.findall("c:ser", NS)
    require(len(series) == len(spec["series"]), "Wrong chart series count")
    total = 0
    for ser, expected in zip(series, spec["series"]):
        x, y = source_values(expected, datasets)
        require(ser.findtext("c:tx/c:v", namespaces=NS) == expected["name"], "Series name mismatch")
        require(ser.find("c:marker/c:symbol", NS).get("val") == "none", "Marker is visible")
        require(ser.find("c:smooth", NS).get("val") == "0", "Curve smoothing unexpectedly enabled")
        require(ser.find("c:spPr/a:ln/a:solidFill/a:srgbClr", NS).get("val") == expected["color"].lstrip("#").upper(), "Line color mismatch")
        for element, formula, values in (("xVal", expected["xFormula"], x), ("yVal", expected["yFormula"], y)):
            ref = ser.find("c:" + element + "/c:numRef", NS)
            require(ref is not None and ref.findtext("c:f", namespaces=NS) == formula, "Series range formula mismatch")
            cache = ref.find("c:numCache", NS)
            require(cache is not None and cache.find("c:ptCount", NS).get("val") == str(len(values)), "Cache ptCount mismatch")
            points = cache.findall("c:pt", NS)
            require(len(points) == len(values), "Chart data was downsampled")
            for index, (point, value) in enumerate(zip(points, values)):
                require(point.get("idx") == str(index) and point.findtext("c:v", namespaces=NS) == numeric_text(value), "Chart cached value mismatch")
        total += len(x)
    return len(series), total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path, nargs="?", default=Path(__file__).resolve().parent.parent / "GLD_Gabungan.xlsx")
    parser.add_argument("manifest", type=Path, nargs="?", default=Path(__file__).resolve().parent / "chart-manifest.json")
    parser.add_argument("--expected-charts", type=int, default=26)
    args = parser.parse_args()
    workbook = args.workbook.resolve()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    datasets, charts = manifest["datasets"], manifest["charts"]
    require(len(charts) == args.expected_charts, "Unexpected manifest chart count")
    require(len(datasets) == 5, "Expected exactly five recording datasets")
    by_title = {chart["title"]: chart for chart in charts}
    require(len(by_title) == len(charts), "Chart titles must be unique")
    require(sum(dataset["n"] for dataset in datasets) == 65926,
            "Refusing a partial/test manifest: expected all 65,926 source records")
    chart_paths = {}
    raw_cache_hashes = {}
    temporary = None
    try:
        with zipfile.ZipFile(workbook) as source:
            root, sheets = workbook_sheets(source)
            require("Summary" in sheets, "Summary worksheet not found")
            for dataset in datasets:
                require(dataset["sheetName"] in sheets, "Raw worksheet not found")
            raw_paths = {sheets[dataset["sheetName"]]: dataset for dataset in datasets}
            repaired_styles, right_aligned_cells = prepare_right_alignment(source, sheets, datasets)
            for item in source.infolist():
                if re.search(r"(?:^|/)charts/chart[^/]*\.xml$", item.filename):
                    chart_root = ET.fromstring(source.read(item.filename))
                    title = title_of(chart_root)
                    require(title in by_title, "Unrecognized native chart: " + title)
                    require(title not in chart_paths.values(), "Duplicate exported chart title")
                    chart_paths[item.filename] = title
            require(set(chart_paths.values()) == set(by_title), "Exported charts do not match the complete manifest")
            descriptor, name = tempfile.mkstemp(prefix=".gld-chart-repair-", suffix=".xlsx", dir=workbook.parent)
            os.close(descriptor)
            temporary = Path(name)
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as target:
                target.comment = source.comment
                for item in source.infolist():
                    data = source.read(item.filename)
                    if item.filename in chart_paths:
                        data = repair_chart(data, by_title[chart_paths[item.filename]], datasets)
                    elif item.filename == "xl/workbook.xml":
                        data = repair_calculation(root)
                    elif item.filename == "xl/styles.xml":
                        data = repaired_styles
                    elif item.filename == sheets["Summary"]:
                        data = repair_summary(data, datasets, right_aligned_cells.get(item.filename))
                    elif item.filename in raw_paths:
                        data, digest = repair_raw_formulas(data, raw_paths[item.filename], right_aligned_cells.get(item.filename))
                        raw_cache_hashes[item.filename] = digest
                    target.writestr(item, data)
        series_count = point_count = 0
        with zipfile.ZipFile(temporary) as checked:
            require(checked.testzip() is None, "Repaired ZIP failed CRC validation")
            helper_count = ma_count = 0
            for filename, dataset in raw_paths.items():
                audit = FormulaAudit(dataset["n"] + 1)
                parse_xml_events(checked.read(filename), audit)
                require(audit.helper_count == dataset["n"] and audit.ma_count == 8 * dataset["n"],
                        "Wrong native helper/MA formula counts in " + dataset["sheetName"])
                require(audit.digest.hexdigest() == raw_cache_hashes[filename],
                        "Numeric formula caches changed in " + dataset["sheetName"])
                helper_count += audit.helper_count
                ma_count += audit.ma_count
                print(f"VERIFIED {dataset['sheetName']}: all native formulas and unchanged numeric caches", flush=True)
            require(helper_count == 65926 and ma_count == 527408, "Incomplete native formula serialization")
            for filename, title in chart_paths.items():
                count, points = validate_chart(checked.read(filename), by_title[title], datasets)
                series_count += count
                point_count += points
                print(f"VERIFIED {title}: {count} native series, {points:,} full XY pairs, range formulas and caches match")
            check_root, check_sheets = workbook_sheets(checked)
            checked_styles = ET.fromstring(checked.read("xl/styles.xml")).find("s:cellXfs", NS)
            require(int(checked_styles.get("count")) == len(checked_styles), "cellXfs count mismatch")
            shared_strings = read_shared_strings(checked)
            for filename, changes in right_aligned_cells.items():
                cells = read_target_cells(checked, filename, changes, shared_strings)
                for reference, style in changes.items():
                    require(cells[reference]["value"] == "n.a." and cells[reference]["style"] == style,
                            "n.a. value/style changed incorrectly: " + reference)
                    alignment = checked_styles[int(style)].find("s:alignment", NS)
                    require(alignment is not None and alignment.get("horizontal") == "right", "n.a. right alignment missing")
            calc = check_root.find("s:calcPr", NS)
            require(calc.get("calcMode") == "auto" and calc.get("fullCalcOnLoad") == "1", "Automatic recalculation missing")
            summary = ET.fromstring(checked.read(check_sheets["Summary"]))
            require(summary.findtext("s:sheetData/s:row[@r='19']/s:c[@r='A19']/s:is/s:t", namespaces=NS) == X_AXIS_GUIDE,
                    "Summary X-axis range instructions missing")
            validations = summary.findall("s:dataValidations/s:dataValidation", NS)
            found = [item for item in validations if item.get("sqref") == "C5"]
            require(len(found) == 1 and found[0].get("type") == "decimal" and found[0].get("operator") == "greaterThan"
                    and found[0].get("errorStyle") == "stop" and found[0].findtext("s:formula1", namespaces=NS) == "0", "Summary C5 validation missing")
        os.replace(temporary, workbook)
        temporary = None
        print(f"DONE: {len(chart_paths)} charts; {series_count} series; {point_count:,} XY pairs; all 65,926 records retained.")
        print(f"Native formulas: {helper_count:,} window helpers + {ma_count:,} moving averages; caches retained and verified.")
        print("Summary C5: decimal > 0, stop validation; recalculation automatic; five internal raw-data links.")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
