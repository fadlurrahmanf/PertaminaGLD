"""Render one audit chart per MQ8 heater raw CSV."""

import csv
from pathlib import Path

from html import escape


def read_samples(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.DictReader(stream)
        values = [
            (float(row["elapsed_s"]) / 60.0, float(row["mq8_v"]) * 1000.0)
            for row in rows
            if row.get("mq8_v")
        ]
    return values


def bin_30_seconds(samples):
    groups = {}
    for minute, value in samples:
        index = int((minute * 60.0) // 30.0)
        groups.setdefault(index, []).append(value)
    return [
        ((index * 30.0 + 15.0) / 60.0, sum(values) / len(values))
        for index, values in sorted(groups.items())
    ]


def main():
    repository = Path(__file__).resolve().parents[3]
    raw_dir = repository / "apps" / "operator-hub" / "output" / "mq8-duty-cycle" / "heater" / "raw"
    charts_dir = raw_dir.parent / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    for csv_path in sorted(raw_dir.glob("*.csv")):
        samples = read_samples(csv_path)
        if not samples:
            continue
        binned = bin_30_seconds(samples)
        width, height = 1440, 700
        left, right, top, bottom = 105, 45, 70, 90
        plot_width, plot_height = width - left - right, height - top - bottom
        min_x, max_x = 0.0, max(point[0] for point in samples)
        min_y = min(point[1] for point in samples)
        max_y = max(point[1] for point in samples)
        padding = max((max_y - min_y) * 0.06, 0.25)
        min_y -= padding
        max_y += padding

        def point_to_svg(point):
            x = left + (point[0] - min_x) / max(max_x - min_x, 1e-9) * plot_width
            y = top + (max_y - point[1]) / max(max_y - min_y, 1e-9) * plot_height
            return f"{x:.2f},{y:.2f}"

        raw_points = " ".join(point_to_svg(point) for point in samples)
        bin_points = " ".join(point_to_svg(point) for point in binned)
        horizontal = []
        vertical = []
        labels = []
        for index in range(6):
            y_value = min_y + (max_y - min_y) * index / 5.0
            y = top + plot_height - plot_height * index / 5.0
            horizontal.append(f'<line x1="{left}" y1="{y:.2f}" x2="{width-right}" y2="{y:.2f}" class="grid"/>')
            labels.append(f'<text x="{left-12}" y="{y+5:.2f}" text-anchor="end" class="tick">{y_value:.2f}</text>')
            x_value = min_x + (max_x - min_x) * index / 5.0
            x = left + plot_width * index / 5.0
            vertical.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{height-bottom}" class="grid"/>')
            labels.append(f'<text x="{x:.2f}" y="{height-bottom+28}" text-anchor="middle" class="tick">{x_value:.1f}</text>')

        title = escape(csv_path.stem.replace("_", " "))
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="MQ8 chart for {title}">
<style>.bg{{fill:#ffffff}}.grid{{stroke:#d8d8d8;stroke-width:1}}.axis{{stroke:#333;stroke-width:1.5}}.raw{{fill:none;stroke:#83a6bb;stroke-width:1;stroke-opacity:.55}}.bin{{fill:none;stroke:#e45756;stroke-width:3}}.tick{{font:16px Arial;fill:#333}}.title{{font:600 22px Arial;fill:#111}}.legend{{font:17px Arial;fill:#222}}</style>
<rect class="bg" width="100%" height="100%"/>
<text x="{left}" y="36" class="title">{title}</text>
{''.join(horizontal)}{''.join(vertical)}
<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" class="axis"/><line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" class="axis"/>
<polyline points="{raw_points}" class="raw"/><polyline points="{bin_points}" class="bin"/>
{''.join(labels)}
<text x="{width/2:.2f}" y="{height-25}" text-anchor="middle" class="legend">Elapsed time (minutes)</text><text transform="translate(27 {height/2:.2f}) rotate(-90)" text-anchor="middle" class="legend">MQ8 voltage (mV)</text>
<line x1="{width-330}" y1="35" x2="{width-285}" y2="35" class="raw"/><text x="{width-275}" y="41" class="legend">MQ8 raw</text><line x1="{width-170}" y1="35" x2="{width-125}" y2="35" class="bin"/><text x="{width-115}" y="41" class="legend">Mean 30 s</text>
</svg>'''
        (charts_dir / f"{csv_path.stem}.svg").write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
