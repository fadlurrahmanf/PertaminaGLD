"""Scale-safe XLSX fallback after artifact-tool full export exhausted 12 GB."""
from pathlib import Path
import bisect
import csv
import hashlib
import json
import math
import os
import statistics
import tempfile
import xlsxwriter
from xlsxwriter.utility import xl_col_to_name

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent.parent
SUPPORT = OUT / "support"
SENSORS = ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"]
NOTES = [
    "Perubahan kecil selama rekaman.",
    "Kenaikan multikanal; LPG muncul menjelang akhir.",
    "Cuplikan 22,54 detik; bukan New 3. MA memakai jendela parsial.",
    "MQ4, MQ7, MQ6 naik pada bagian akhir.",
    "Lima kanal naik di bagian akhir; seluruh prediksi Clear.",
]


def main():
    manifest = json.loads((SUPPORT / "chart-manifest.json").read_text(encoding="utf-8"))
    datasets = manifest["datasets"]
    assert len(datasets) == 5 and sum(d["n"] for d in datasets) == 65926
    assert len(manifest["charts"]) == 26
    for d in datasets:
        content = (ROOT / "excel" / d["file"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == d["hash"], d["file"] + " changed since manifest"
        with (ROOT / "excel" / d["file"]).open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.reader(stream)
            d["headers"] = next(reader)
            d["rows"] = [[v if j == 1 else float(v) for j, v in enumerate(row)] for row in reader]
        assert len(d["rows"]) == d["n"] and all(len(row) == 28 for row in d["rows"])
        d["times"] = [row[0] for row in d["rows"]]
        assert all(b > a for a, b in zip(d["times"], d["times"][1:]))
        d["duration"] = (d["times"][-1] - d["times"][0]) / 60000
        d["clear"] = sum(row[10] == 0 for row in d["rows"])
        d["lpg"] = sum(row[10] == 1 for row in d["rows"])
        d["first_lpg"] = next(((row[0] - d["t0"]) / 60000 for row in d["rows"] if row[10] == 1), "n.a.")
        d["max_gap"] = max((b - a) / 1000 for a, b in zip(d["times"], d["times"][1:]))
        d["first_means"] = [statistics.mean(row[j + 2] for row in d["rows"] if row[0] < d["t0"] + 600000) * 1000 for j in range(8)]
        d["last_means"] = [statistics.mean(row[j + 2] for row in d["rows"] if row[0] >= d["end"] - 600000) * 1000 for j in range(8)]
        d["deltas"] = [b - a if d["duration"] >= 20 else "n.a." for a, b in zip(d["first_means"], d["last_means"])]
        assert all(len(v) == d["n"] for v in d["raw"] + d["ma"])
    fd, tmp = tempfile.mkstemp(prefix=".gld-fallback-", suffix=".xlsx", dir=OUT)
    os.close(fd)
    workbook = xlsxwriter.Workbook(tmp, {"constant_memory": True, "tmpdir": str(SUPPORT)})
    base = {"font_name": "Arial", "font_size": 10, "font_color": "#243B53"}
    fmt = {"base": workbook.add_format(base),
           "title": workbook.add_format({**base, "font_size": 15, "bold": True, "font_color": "#172554"}),
           "header": workbook.add_format({**base, "bold": True, "font_color": "#FFFFFF", "bg_color": "#243B53", "text_wrap": True, "valign": "vcenter", "align": "center"}),
           "input": workbook.add_format({**base, "font_size": 11, "bold": True, "font_color": "#92400E", "bg_color": "#FEF3C7", "num_format": "0.00"}),
           "int": workbook.add_format({**base, "num_format": "0"}),
           "count": workbook.add_format({**base, "num_format": "#,##0"}),
           "two": workbook.add_format({**base, "num_format": "0.00", "align": "right"}),
           "delta": workbook.add_format({**base, "num_format": "0.00;[Red]-0.00;0.00", "align": "right"}),
           "volt": workbook.add_format({**base, "num_format": "0.000000000"}),
           "six": workbook.add_format({**base, "num_format": "0.000000"}),
           "confidence": workbook.add_format({**base, "num_format": "0.00000000"}),
           "link": workbook.add_format({**base, "font_color": "#2563EB", "underline": 1}),
           "note": workbook.add_format({**base, "text_wrap": True, "valign": "vcenter"})}
    summary = workbook.add_worksheet("Summary")
    individual = workbook.add_worksheet("Grafik Rekaman")
    sheets = {"Summary": summary, "Grafik Rekaman": individual}
    for d in datasets:
        sheets[d["sheetName"]] = workbook.add_worksheet(d["sheetName"])
    for sh in (summary, individual):
        sh.hide_gridlines(2)
        sh.set_default_row(21)
        sh.set_column("A:Q", 12, fmt["base"])
        sh.set_landscape()
        sh.set_paper(9)
        sh.fit_to_pages(1, 0)
    summary.set_tab_color("#243B53")
    individual.set_tab_color("#55718B")
    summary.set_column("A:A", 22, fmt["base"])
    summary.set_column("I:I", 22, fmt["base"])
    summary.freeze_panes(8, 1)
    individual.write("A2", "Grafik setiap rekaman", fmt["title"])
    individual.write("A3", "Kiri: seluruh sampel mentah. Kanan: moving average mengikuti Summary!C5. Satuan tegangan V.", fmt["base"])
    # Constant-memory requires row-ascending writes, including the front sheets.
    summary.write("A2", "GLD1004 — gabungan rekaman sensor", fmt["title"])
    summary.write("A3", "Lima rekaman dari folder excel. Data asli dan seluruh sampel grafik dipertahankan.", fmt["base"])
    summary.write("A5", "Jendela MA (menit)", fmt["base"])
    summary.write_number("C5", 1, fmt["input"])
    summary.write_formula("D5", '=IF(AND(ISNUMBER(C5),C5>0),"Ubah sel kuning untuk menghitung ulang seluruh MA.","Masukkan angka menit lebih besar dari 0.")', fmt["base"], "Ubah sel kuning untuk menghitung ulang seluruh MA.")
    summary.write("A6", "MA: rata-rata sampel pada (t − jendela, t]. Awal rekaman memakai sampel tersedia; jeda tidak diinterpolasi.", fmt["base"])
    summary.set_row(7, 35)
    summary.write_row("A8", ["Rekaman", "Sampel", "Durasi (menit)", "Profil nulling", "Clear", "LPG", "LPG pertama (menit)", "Jeda maks. (detik)", "Sheet data"], fmt["header"])
    for k, d in enumerate(datasets):
        row = 8 + k
        q = "'" + d["sheetName"] + "'"
        summary.set_row(row, 32)
        summary.write(row, 0, d["label"], fmt["base"])
        summary.write_formula(row, 1, f"={q}!AP5", fmt["count"], d["n"])
        summary.write_formula(row, 2, f"={q}!AS5", fmt["two"], d["duration"])
        summary.write_number(row, 3, d["profile"], fmt["int"])
        summary.write_formula(row, 4, f"={q}!AP6", fmt["count"], d["clear"])
        summary.write_formula(row, 5, f"={q}!AS6", fmt["count"], d["lpg"])
        summary.write_formula(row, 6, f"={q}!AP7", fmt["two"], d["first_lpg"])
        summary.write_formula(row, 7, f"={q}!AS7", fmt["two"], d["max_gap"])
        summary.write(row, 8, d["sheetName"], fmt["link"])
        summary.merge_range(row, 10, row, 16, NOTES[k], fmt["note"])
    notes = {
        15: "Grafik gabungan menyelaraskan menit 0 setiap rekaman; rekaman tidak disambung menjadi satu eksperimen.",
        16: "Profil nulling berbeda. Clear/LPG adalah prediksi model; label clear_air bukan pengukuran gas independen.",
        17: "Grafik per file berada di Grafik Rekaman. Lima sheet Raw memuat data CSV pada kolom A–AB tanpa perubahan.",
        18: "Kolom AD–AM: waktu relatif, indeks awal jendela, dan MA. Grafik dalam volt (V); tabel perubahan dalam mV.",
        19: "Rentang tampilan: pilih sumbu X > Format Axis > Bounds > Minimum/Maximum (menit). Default: seluruh rekaman."}
    for row, value in notes.items():
        summary.write(row - 1, 0, value, fmt["base"])
    summary.write("A20", "Perubahan rata-rata awal–akhir (mV)", fmt["title"])
    summary.set_row(20, 32)
    summary.write_row("A21", ["Sensor"] + [d["label"] for d in datasets], fmt["header"])
    summary.write("H21", "Metode perubahan", fmt["base"])
    for j, sensor in enumerate(SENSORS):
        row = 21 + j
        summary.write(row, 0, sensor, fmt["base"])
        for k, d in enumerate(datasets):
            formula = f"='{d['sheetName']}'!AR{11+j}" if d["duration"] >= 20 else '="n.a."'
            summary.write_formula(row, 1 + k, formula, fmt["delta"], d["deltas"][j])
        explanations = {0: "Rata-rata 10 menit terakhir dikurangi 10 menit pertama.", 1: "Durasi berbeda; angka ini bukan perbandingan laju drift.", 2: "Cuplikan <20 menit tidak dinilai dengan metrik ini."}
        if j in explanations:
            summary.write(row, 7, explanations[j], fmt["base"])
    summary.write("A32", "Perbandingan seluruh rekaman per sensor", fmt["title"])
    for k, d in enumerate(datasets):
        sh = sheets[d["sheetName"]]
        sh.hide_gridlines(2)
        sh.set_default_row(19)
        sh.set_column("A:AM", 15, fmt["base"])
        sh.set_column("B:B", 49, fmt["base"])
        sh.set_column("AO:AV", 18, fmt["base"])
        sh.set_column("AO:AO", 27, fmt["base"])
        sh.freeze_panes(1, 2)
        sh.autofilter(0, 0, d["n"], 27)
        sh.set_row(0, 42)
        sh.write_row(0, 0, d["headers"], fmt["header"])
        sh.write_row(0, 29, ["Waktu relatif (menit)", "Indeks awal MA"] + [sensor + " MA (V)" for sensor in SENSORS], fmt["header"])
        last = d["n"] + 1
        side = {}
        def text(row, col, value, form="base"):
            side.setdefault(row - 1, []).append((col, None, value, form))
        def formula(row, col, value, cached, form="two"):
            side.setdefault(row - 1, []).append((col, value, cached, form))
        text(2, 40, "Ringkasan rekaman", "title")
        text(3, 40, "Sumber: " + d["file"])
        text(4, 40, "Label: " + d["rows"][0][1])
        for row, left, right in ((5, "Sampel", "Menit"), (6, "Clear", "LPG"), (7, "LPG pertama (menit)", "Jeda maks. (detik)")):
            text(row, 40, left)
            text(row, 43, right)
        formula(5, 41, f"=COUNT(A2:A{last})", d["n"], "count")
        formula(5, 44, f"=(A{last}-A2)/60000", d["duration"])
        formula(6, 41, f"=COUNTIFS(K2:K{last},0)", d["clear"], "count")
        formula(6, 44, f"=COUNTIFS(K2:K{last},1)", d["lpg"], "count")
        formula(7, 41, f'=IF(AS6=0,"n.a.",(INDEX(A2:A{last},MATCH(1,K2:K{last},0))-A2)/60000)', d["first_lpg"])
        text(7, 44, d["max_gap"], "two")
        text(8, 40, f"Profil nulling: {d['profile']}; GLD1004; model cnn-dualbranch-board-1-2class-v2.")
        for c, value in enumerate(["Sensor", "Awal 10m (mV)", "Akhir 10m (mV)", "Perubahan (mV)", "Rata-rata (mV)", "Minimum (mV)", "Maksimum (mV)", "MA akhir (V)"]):
            text(10, 40 + c, value, "header")
        for j, sensor in enumerate(SENSORS):
            row, c, ma = 11 + j, xl_col_to_name(j + 2), xl_col_to_name(j + 31)
            value_range = f"{c}2:{c}{last}"
            time_range = f"A2:A{last}"
            text(row, 40, sensor)
            formula(row, 41, f'=AVERAGEIFS({value_range},{time_range},"<"&($A$2+600000))*1000', d["first_means"][j])
            formula(row, 42, f'=AVERAGEIFS({value_range},{time_range},">="&($A${last}-600000))*1000', d["last_means"][j])
            formula(row, 43, f"=AQ{row}-AP{row}" if d["duration"] >= 20 else '="n.a."', d["deltas"][j])
            formula(row, 44, f"=AVERAGE({value_range})*1000", statistics.mean(d["raw"][j]) * 1000)
            formula(row, 45, f"=MIN({value_range})*1000", min(d["raw"][j]) * 1000)
            formula(row, 46, f"=MAX({value_range})*1000", max(d["raw"][j]) * 1000)
            formula(row, 47, f"={ma}{last}", d["ma"][j][-1], "six")
        text(20, 40, "SHA-256: " + d["hash"])
        text(21, 40, NOTES[k])
        for i, record in enumerate(d["rows"]):
            row, excel_row = i + 1, i + 2
            for c, value in enumerate(record):
                formatting = "base" if c == 1 else "volt" if 2 <= c <= 9 else "confidence" if c == 11 else "int"
                sh.write(row, c, value, fmt[formatting])
            sh.write_formula(row, 29, f"=(A{excel_row}-$A$2)/60000", fmt["two"], d["elapsed"][i])
            left = bisect.bisect_right(d["times"], record[0] - 60000, 0, i + 1)
            sh.write_number(row, 30, left + 1, fmt["int"])
            for j in range(8):
                sh.write_number(row, 31 + j, d["ma"][j][i], fmt["volt"])
            if row == 9:
                sh.set_row(row, 38)
            for col, expression, value, formatting in side.get(row, []):
                if expression is None:
                    sh.write(row, col, value, fmt[formatting])
                else:
                    sh.write_formula(row, col, expression, fmt[formatting], value)
        print(f"WRITTEN {d['sheetName']}: {d['n']:,} complete records", flush=True)
    for spec in manifest["charts"]:
        chart = workbook.add_chart({"type": "scatter", "subtype": "straight"})
        for series in spec["series"]:
            chart.add_series({"name": series["name"], "categories": "=" + series["xFormula"], "values": "=" + series["yFormula"],
                              "line": {"color": series["color"], "width": 1.25 if series["mode"] == "ma" else 0.7},
                              "marker": {"type": "none"}, "smooth": False})
        chart.set_title({"name": spec["title"], "name_font": {"name": "Arial", "size": 14}})
        chart.set_legend({"position": "top", "font": {"name": "Arial", "size": 10}})
        if spec["sheet"] == "Summary":
            sensor = spec["series"][0]["sensor"]
            values = [d["raw"][sensor] for d in datasets]
            extent = max(d["duration"] for d in datasets)
        else:
            dataset = datasets[spec["series"][0]["dataset"]]
            values = dataset["raw"]
            extent = dataset["duration"]
        low, high = min(map(min, values)), max(map(max, values))
        padding = max((high - low) * 0.05, 0.0001)
        chart.set_x_axis({"name": "Waktu sejak awal rekaman (menit)", "num_format": "0.0", "label_position": "low", "min": 0, "max": extent * 1.02, "name_font": {"name": "Arial", "size": 10}, "num_font": {"name": "Arial", "size": 9}})
        chart.set_y_axis({"name": "Tegangan (V)", "num_format": "0.0000", "min": low - padding, "max": high + padding, "name_font": {"name": "Arial", "size": 10}, "num_font": {"name": "Arial", "size": 9}, "major_gridlines": {"visible": True, "line": {"color": "#E2E8F0"}}})
        chart.set_chartarea({"border": {"color": "#CBD5E1"}, "fill": {"color": "#FFFFFF"}})
        chart.set_size({"width": 720, "height": 420})
        ma = spec["series"][0]["mode"] == "ma"
        top = 34 + spec["series"][0]["sensor"] * 23 if spec["sheet"] == "Summary" else 6 + spec["series"][0]["dataset"] * 23
        sheets[spec["sheet"]].insert_chart(top - 1, 9 if ma else 0, chart)
    workbook.set_calc_mode("auto")
    workbook.set_properties({"title": "GLD1004 — Gabungan Rekaman Sensor", "subject": "Lima CSV lengkap, grafik mentah dan moving average", "comments": "Seluruh 65.926 rekaman dipertahankan. Jendela MA dalam menit di Summary C5."})
    workbook.close()
    os.replace(tmp, OUT / "GLD_Gabungan.xlsx")
    print("FALLBACK EXPORTED: 7 sheets, 26 native scatter charts, 65,926 full records; native MA formula/cache repair is next.", flush=True)


if __name__ == "__main__":
    main()
