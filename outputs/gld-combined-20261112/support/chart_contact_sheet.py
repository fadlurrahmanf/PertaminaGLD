"""Render all repaired native chart caches for scientific/visual QA.

This reads the final XLSX without recalculation and never modifies it. Each PNG
uses every cached x/y point, native series names/colors and chart/axis titles.
It is a data/plot QA rendering, not a claim of Excel's exact layout rendering.
Usage: python chart_contact_sheet.py final.xlsx [--output chart_qa] [--pairs 4]
"""

import argparse
import hashlib
import json
import math
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"c": C, "a": A, "s": S}


def digest(path):
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def relations(zf, part):
    name = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
    if name not in zf.namelist():
        return {}
    out = {}
    for rel in ET.fromstring(zf.read(name)):
        if rel.get("TargetMode") == "External":
            continue
        target = rel.get("Target", "")
        out[rel.get("Id")] = target.lstrip("/") if target.startswith("/") else posixpath.normpath(
            posixpath.join(posixpath.dirname(part), target))
    return out


def chart_owners(zf):
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = relations(zf, "xl/workbook.xml")
    owners = {}
    for sheet in workbook.findall("s:sheets/s:sheet", NS):
        name = sheet.get("name")
        part = rels[sheet.get(f"{{{R}}}id")]
        for drawing in relations(zf, part).values():
            if drawing.startswith("xl/drawings/") and drawing.endswith(".xml"):
                for chart in relations(zf, drawing).values():
                    if re.fullmatch(r"xl/charts/chart\d+\.xml", chart):
                        owners[chart] = name
    return owners


def theme_colors(zf):
    colors = {}
    if "xl/theme/theme1.xml" not in zf.namelist():
        return colors
    root = ET.fromstring(zf.read("xl/theme/theme1.xml"))
    scheme = root.find(".//a:clrScheme", NS)
    if scheme is not None:
        for color in scheme:
            node = next(iter(color), None)
            if node is not None:
                colors[color.tag.rsplit("}", 1)[-1]] = node.get("lastClr") or node.get("val")
    return colors


def title_text(element):
    return "".join(node.text or "" for node in element.iter(f"{{{A}}}t"))


def load_chart(zf, part, theme):
    chart = {"part": part, "title": "", "x_title": "", "y_title": "", "series": []}
    stack, current, axis, axis_position = [], None, None, None
    with zf.open(part) as stream:
        for event, element in ET.iterparse(stream, events=("start", "end")):
            local = element.tag.rsplit("}", 1)[-1]
            if event == "start":
                stack.append(local)
                if local == "ser":
                    current = {"x": [], "y": [], "name": "", "color": None, "width": 0.8}
                elif local in ("xVal", "yVal"):
                    axis = "x" if local == "xVal" else "y"
                elif local == "ln" and current is not None and element.get("w"):
                    current["width"] = int(element.get("w")) / 12700
                continue
            if local == "pt" and axis and current is not None and "numCache" in stack:
                index = int(element.get("idx"))
                if index != len(current[axis]):
                    raise ValueError(f"Non-contiguous native cache in {part}/{axis}")
                value = float(element.findtext("c:v", namespaces=NS))
                if not math.isfinite(value):
                    raise ValueError(f"Nonfinite cached chart point in {part}")
                current[axis].append(value)
                element.clear()
            elif local == "tx" and current is not None:
                name = element.findtext("c:v", namespaces=NS)
                if name is None:
                    name = element.findtext(".//c:strCache/c:pt/c:v", namespaces=NS)
                current["name"] = name or title_text(element)
            elif local in ("srgbClr", "schemeClr") and current is not None and "ln" in stack:
                value = element.get("val")
                if local == "schemeClr":
                    value = theme.get(value)
                if value and re.fullmatch(r"[0-9A-Fa-f]{6}", value):
                    current["color"] = "#" + value
            elif local == "title" and not any(tag in stack for tag in ("valAx", "catAx", "dateAx")):
                chart["title"] = title_text(element)
            elif local in ("valAx", "catAx", "dateAx"):
                pos = element.find("c:axPos", NS)
                title = element.find("c:title", NS)
                if pos is not None and title is not None:
                    key = "x_title" if pos.get("val") in ("b", "t") else "y_title"
                    chart[key] = title_text(title)
                element.clear()
            elif local in ("xVal", "yVal"):
                axis = None
                element.clear()
            elif local == "ser":
                if not current["x"] or len(current["x"]) != len(current["y"]):
                    raise ValueError(f"Incomplete native x/y caches in {part}")
                if not current["name"] or not current["color"]:
                    raise ValueError(f"Native series name/color missing in {part}")
                chart["series"].append(current)
                current = None
                element.clear()
            stack.pop()
    if not chart["title"] or not chart["x_title"] or not chart["y_title"]:
        raise ValueError(f"Native chart/axis title missing in {part}")
    return chart


def mode_key(title):
    match = re.match(r"^(.*?)\s+[\u2014\u2013-]\s+(Raw|Moving average)\s*\(V\)\s*$", title, re.I)
    if match is None:
        raise ValueError(f"Cannot pair raw/MA chart title: {title!r}")
    return match.group(1), "raw" if match.group(2).lower() == "raw" else "ma"


def plot_native(ax, chart):
    for series in chart["series"]:
        line, = ax.plot(series["x"], series["y"], label=series["name"],
                        color=series["color"], linewidth=max(0.45, series["width"]),
                        marker=None, rasterized=True)
        if len(line.get_xdata()) != len(series["x"]):
            raise ValueError("Rendering dropped data points")
    ax.set_title(chart["title"], loc="left", fontsize=11, fontweight="bold", pad=28)
    ax.set_xlabel(chart["x_title"], fontsize=8)
    ax.set_ylabel(chart["y_title"], fontsize=8)
    ax.tick_params(labelsize=8)
    ax.grid(True, color="#DDE4EC", linewidth=0.5)
    ax.set_axisbelow(True)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.005), ncol=4,
              frameon=False, fontsize=7, handlelength=1.8, columnspacing=1)
    ax.margins(x=0.01)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%.3f"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parent / "chart_qa")
    parser.add_argument("--pairs", type=int, choices=(3, 4, 5), default=4)
    args = parser.parse_args()
    before = digest(args.workbook)
    args.output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"path.simplify": False, "agg.path.chunksize": 10000,
                         "font.family": "DejaVu Sans", "figure.facecolor": "white"})
    pages, checked_charts, checked_series, checked_points = [], 0, 0, 0
    with zipfile.ZipFile(args.workbook) as zf:
        owners, theme = chart_owners(zf), theme_colors(zf)
        if len(owners) != 26:
            raise ValueError(f"Expected26 native charts, found{len(owners)}")
        # Small metadata pass, one chart at a time. Release caches between charts.
        pairs = defaultdict(dict)
        for part in sorted(owners, key=lambda s: int(re.search(r"chart(\d+)", s).group(1))):
            chart = load_chart(zf, part, theme)
            title, mode = mode_key(chart["title"])
            key = (owners[part], title)
            if mode in pairs[key]:
                raise ValueError(f"Duplicate {mode} chart for {key}")
            pairs[key][mode] = part
            del chart
        if len(pairs) != 13 or any(set(pair) != {"raw", "ma"} for pair in pairs.values()):
            raise ValueError("Expected13 complete raw/MA pairs")
        ordered = list(pairs.items())
        for start in range(0, len(ordered), args.pairs):
            batch = ordered[start:start + args.pairs]
            fig, axes = plt.subplots(len(batch), 2, figsize=(20, 3.5 * len(batch)),
                                     squeeze=False, constrained_layout=True)
            page = len(pages) + 1
            fig.suptitle(f"GLD — native chart cache QA · page {page}\n"
                         "Every cached point included · source workbook unchanged", fontsize=13)
            for row, ((owner, title), pair) in enumerate(batch):
                for column, mode in enumerate(("raw", "ma")):
                    chart = load_chart(zf, pair[mode], theme)
                    plot_native(axes[row, column], chart)
                    checked_charts += 1
                    checked_series += len(chart["series"])
                    checked_points += sum(len(s["x"]) for s in chart["series"])
                    del chart
            target = args.output / f"native_charts_{page:02d}.png"
            fig.savefig(target, dpi=160, facecolor="white")
            plt.close(fig)
            pages.append(str(target.resolve()))
    if digest(args.workbook) != before:
        raise RuntimeError("Source workbook changed during visual QA")
    print(json.dumps({"status": "PASS", "source_sha256": before, "source_unchanged": True,
                      "charts_rendered": checked_charts, "series_rendered": checked_series,
                      "xy_pairs_rendered": checked_points, "point_downsampling": False,
                      "pages": pages, "limitation": "Native cache data/plot QA, not Excel pixel-layout rendering"}, indent=2))


if __name__ == "__main__":
    main()
