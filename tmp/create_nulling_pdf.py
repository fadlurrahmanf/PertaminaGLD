"""Build a landscape PDF mirroring the successful Nulling Details tables."""

from __future__ import annotations

import json
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

SENSORS = ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"]
TOKEN = re.compile(r"([A-Za-z][A-Za-z0-9]*)=([^\s]+)")
CHANNEL = re.compile(r"\bch=(\d+)")


def tokens(line: str) -> dict[str, str]:
    return dict(TOKEN.findall(line))


def trace_for_successes(lines: list[str]) -> dict[int, dict[str, object]]:
    active: dict[int, dict[str, object]] = {}
    successful: dict[int, dict[str, object]] = {}
    for line in lines:
        match = CHANNEL.search(line)
        if not match:
            continue
        ch = int(match.group(1))
        if not 0 <= ch < 8:
            continue
        t = tokens(line)
        if line.startswith("NULLING_CH_START"):
            active[ch] = {
                "channel": ch, "sensor": t.get("sensor", SENSORS[ch]), "baseline": [],
                "exponential": [], "binary": [], "confirm": [], "threshold": None,
                "min_final": None, "min_bracket": None, "final": None,
            }
        item = active.get(ch)
        if item is None:
            continue
        if line.startswith("NULLING_BASELINE_STEP"):
            item["baseline"].append([t.get("code", "-"), t.get("voltage", "-")])
        elif line.startswith("NULLING_EXP_START"):
            item["threshold"] = t.get("threshold")
            item["min_final"] = t.get("minFinalV")
            item["min_bracket"] = t.get("minBracketDac")
        elif line.startswith("NULLING_EXP_STEP"):
            item["exponential"].append([t.get("code", "-"), t.get("voltage", "-"), t.get("delta", "-")])
        elif line.startswith("NULLING_BIN_STEP"):
            item["binary"].append([t.get("high", "-"), t.get("low", "-"), t.get("mid", "-"), t.get("voltage", "-"), t.get("delta", "-")])
        elif line.startswith("NULLING_CONFIRM_STEP"):
            zero = "Ya" if t.get("zeroMargin") == "1" else "Tidak" if t.get("zeroMargin") == "0" else "-"
            rise = "Ya" if t.get("outBaseline") == "1" else "Tidak" if t.get("outBaseline") == "0" else "-"
            item["confirm"].append([t.get("code", "-"), t.get("voltage", "-"), t.get("delta", "-"), zero, rise])
        elif line.startswith("NULLING_CH_OK"):
            item["final"] = {"dac": t.get("dac", "-"), "baseline": t.get("baseline", "-"), "after": t.get("after", "-"), "delta": t.get("delta", "-")}
            successful[ch] = item.copy()
    return successful


def detail_table(title: str, headers: list[str], rows: list[list[str]], widths: list[float]) -> list[object]:
    styles = getSampleStyleSheet()
    block: list[object] = [Paragraph(title, styles["Heading4"])]
    data = [headers] + (rows or [["Tidak ada data", *["" for _ in headers[1:]]]])
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B3B43")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.2),
        ("LEADING", (0, 0), (-1, -1), 7.2),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#9AAFB2")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0F5F5")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i, row in enumerate(rows, 1):
        if "Tidak" in row:
            style.append(("TEXTCOLOR", (-1, i), (-1, i), colors.HexColor("#C62828")))
        if "Ya" in row:
            style.append(("TEXTCOLOR", (-1, i), (-1, i), colors.HexColor("#00796B")))
    table.setStyle(TableStyle(style))
    block.extend([table, Spacer(1, 3 * mm)])
    return block


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#52666B"))
    canvas.drawString(12 * mm, 8 * mm, "Pertamina GLD - Live Nulling Details")
    canvas.drawRightString(285 * mm, 8 * mm, f"Page {doc.page}")
    canvas.restoreState()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    capture = json.loads((root / "tmp" / "nulling-live-capture.json").read_text(encoding="utf-8"))
    traces = trace_for_successes(capture["lines"])
    if set(traces) != set(range(8)):
        raise RuntimeError(f"Expected successful details for 8 channels, got {sorted(traces)}")

    output = root / "output" / "pdf" / "gld2-nulling-details-profile-2.pdf"
    doc = SimpleDocTemplate(str(output), pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=14 * mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="SubtitleSmall", parent=styles["Normal"], fontSize=8.5, leading=11, textColor=colors.HexColor("#35535A")))
    story: list[object] = []
    story.append(Paragraph("GLD2 Nulling Details - Profile 2", styles["Title"]))
    story.append(Paragraph("Live COM3 result. Full run completed 7/8; Retry Failed recalibrated MQ4 only. Final NVS save succeeded, then board rebooted to Inference with profileId 2 applied.", styles["SubtitleSmall"]))
    story.append(Spacer(1, 6 * mm))
    summary_rows = []
    for ch in range(8):
        final = traces[ch]["final"]
        summary_rows.append([f"CH{ch + 1}", str(traces[ch]["sensor"]), final["dac"], final["baseline"], final["after"], final["delta"], "Berhasil"])
    summary = Table([["Channel", "Sensor", "DAC akhir", "Baseline (V)", "Final (V)", "Naik (V)", "Status"]] + summary_rows, colWidths=[22*mm, 28*mm, 28*mm, 37*mm, 37*mm, 37*mm, 28*mm])
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0B3B43")), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("GRID", (0,0), (-1,-1), .3, colors.HexColor("#AABABC")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#EDF5F4")]), ("FONTSIZE", (0,0), (-1,-1), 8),
        ("ALIGN", (2,1), (-2,-1), "RIGHT"), ("TEXTCOLOR", (-1,1), (-1,-1), colors.HexColor("#00796B")),
        ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story += [summary, Spacer(1, 5 * mm), Paragraph("Criteria used: V >= -threshold; V - baseline >= threshold; final V >= minimum final voltage. Exponential bracket minimum DAC = 100. Confirm window = Binary result -10 through +10 (21 samples).", styles["SubtitleSmall"]), PageBreak()]

    half = 133 * mm
    for ch in range(8):
        t = traces[ch]
        final = t["final"]
        story.append(Paragraph(f"CH{ch + 1} - {t['sensor']} - Successful", styles["Heading2"]))
        story.append(Paragraph(
            f"Final DAC {final['dac']} | Baseline {final['baseline']} V | Final {final['after']} V | Rise {final['delta']} V | "
            f"Threshold {t['threshold']} V | Min final {t['min_final']} V | Min exponential bracket DAC {t['min_bracket']}",
            styles["SubtitleSmall"],
        ))
        story.append(Spacer(1, 2.5 * mm))
        left = []
        left += detail_table("1. Baseline", ["DAC", "Voltage (V)"], t["baseline"], [25*mm, 48*mm])
        left += detail_table("2. Exponential", ["DAC", "Voltage (V)", "Naik dari baseline (V)"], t["exponential"], [17*mm, 35*mm, 58*mm])
        right = []
        right += detail_table("3. Binary Search", ["High", "Low", "Mid", "Voltage (V)", "Naik (V)"], t["binary"], [17*mm, 17*mm, 17*mm, 42*mm, 40*mm])
        right += detail_table("4. Confirm", ["DAC", "Voltage (V)", "Naik (V)", "Lewati nol", "Naik >= threshold"], t["confirm"], [14*mm, 33*mm, 32*mm, 24*mm, 37*mm])
        layout = Table([[left, right]], colWidths=[half, half], hAlign="LEFT")
        layout.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 3*mm), ("TOPPADDING", (0,0), (-1,-1), 0), ("BOTTOMPADDING", (0,0), (-1,-1), 0)]))
        story.append(layout)
        if ch != 7:
            story.append(PageBreak())

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
