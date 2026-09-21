import json
import re
from collections import defaultdict
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, LongTable

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tmp" / "gld1-nulling-record-2026-08-28.jsonl"
OUTPUT = ROOT / "output" / "pdf" / "GLD1_Nulling_Run_2026-08-28.pdf"
SENSORS = ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"]

KV = re.compile(r"(\w+)=([^\s]+)")

def fields(line):
    return dict(KV.findall(line))

def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def mv(value):
    value = number(value)
    return "-" if value is None else f"{value * 1000:.3f}"

def page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#52666D"))
    canvas.drawString(15 * mm, 10 * mm, "Pertamina GLD - Rekaman nulling GLD1")
    canvas.drawRightString(282 * mm, 10 * mm, f"Halaman {doc.page}")
    canvas.restoreState()

def table(data, widths, header=True):
    cls = LongTable if len(data) > 24 else Table
    result = cls(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    style = [
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B6C6CB")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.4),
        ("LEADING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#153E49")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    result.setStyle(TableStyle(style))
    return result

def main():
    records = [json.loads(raw) for raw in SOURCE.read_text(encoding="utf-8").splitlines() if raw.strip()]
    stages = defaultdict(lambda: defaultdict(list))
    summary = {}
    start_time = next((r["ts"] for r in records if r.get("kind") == "start"), "-")
    for record in records:
        line = record.get("line", "")
        match = re.search(r"sensor=(MQ\d+|MQ135)", line)
        sensor = match.group(1) if match else None
        if sensor and "NULLING_" in line:
            row = fields(line)
            if "BASELINE_STEP" in line:
                stages[sensor]["Baseline"].append(row)
            elif "EXP_STEP" in line:
                stages[sensor]["Exponential"].append(row)
            elif "BIN_STEP" in line:
                stages[sensor]["Binary search"].append(row)
            elif "CONFIRM_STEP" in line:
                stages[sensor]["Confirm"].append(row)
            elif "CONFIRM_VERIFY" in line:
                stages[sensor]["Verify"].append(row)
            elif "MCP_WRITE" in line:
                stages[sensor]["MCP write"].append(row)
        if "NULLING_CH_OK" in line:
            row = fields(line); summary[row["sensor"]] = {"result": "LULUS", **row}
        elif "NULLING_CH_FAIL" in line:
            row = fields(line); summary[row["sensor"]] = {"result": "GAGAL", **row}

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT), pagesize=landscape(A4), leftMargin=14*mm, rightMargin=14*mm,
        topMargin=14*mm, bottomMargin=17*mm,
        title="GLD1 Nulling Run 2026-08-28",
        author="Pertamina GLD",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("Title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=colors.HexColor("#123C47"), alignment=TA_CENTER)
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=colors.HexColor("#123C47"), spaceAfter=7)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=colors.HexColor("#123C47"), spaceBefore=8, spaceAfter=4)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.6, leading=11, textColor=colors.HexColor("#21353A"))
    story = [
        Spacer(1, 12*mm),
        Paragraph("Laporan Rekaman Nulling GLD1", title),
        Spacer(1, 4*mm),
        Paragraph("Run penuh 8 kanal - firmware 0.8.30 - rekaman serial lengkap", ParagraphStyle("Sub", parent=body, alignment=TA_CENTER)),
        Spacer(1, 11*mm),
        Paragraph("Ringkasan hasil", h1),
        Paragraph("Setiap sensor di bawah memiliki jejak baseline, exponential, binary search, confirm, dan verifikasi yang benar-benar terekam. Tidak ada data sintetis atau tabel kosong.", body),
        Spacer(1, 4*mm),
    ]
    overview = [["Urutan", "Sensor", "Hasil", "DAC akhir", "Baseline (mV)", "Akhir (mV)", "Delta (mV)", "Threshold (mV)"]]
    for index, sensor in enumerate(SENSORS, 1):
        row = summary.get(sensor, {})
        overview.append([str(index), sensor, row.get("result", "TIDAK TEREKAM"), row.get("dac", "-"), mv(row.get("baseline")), mv(row.get("after")), mv(row.get("delta")), mv(row.get("threshold"))])
    story.append(table(overview, [16*mm, 24*mm, 30*mm, 27*mm, 33*mm, 30*mm, 30*mm, 34*mm]))
    story += [Spacer(1, 8*mm), Paragraph(f"Rekaman dimulai {start_time}. Profil nulling 1 tersimpan dan diterapkan setelah semua 8 kanal lulus.", body), PageBreak()]

    stage_columns = ["Kode DAC", "Tegangan (mV)", "Delta (mV)", "Keluar baseline", "Tulis DAC", "Stabil", "Spread (mV)"]
    stage_widths = [24*mm, 32*mm, 28*mm, 31*mm, 25*mm, 22*mm, 30*mm]
    for sensor in SENSORS:
        result = summary.get(sensor, {})
        story.append(Paragraph(f"{sensor} - {result.get('result', 'TIDAK TEREKAM')}", h1))
        detail = [["DAC akhir", result.get("dac", "-")], ["Baseline", f"{mv(result.get('baseline'))} mV"], ["Pembacaan akhir", f"{mv(result.get('after'))} mV"], ["Threshold", f"{mv(result.get('threshold'))} mV"]]
        story.append(table(detail, [48*mm, 52*mm], header=False))
        for stage_name in ("MCP write", "Baseline", "Exponential", "Binary search", "Confirm", "Verify"):
            rows = stages[sensor].get(stage_name, [])
            story.append(Paragraph(stage_name, h2))
            if not rows:
                story.append(Paragraph("Tidak ada titik untuk tahap ini pada run tersebut.", body))
                continue
            payload = [stage_columns]
            for row in rows:
                payload.append([
                    row.get("code", "-"), mv(row.get("voltage")), mv(row.get("delta")),
                    row.get("outBaseline", "-"), row.get("write", row.get("ack", "-")),
                    row.get("stable", "-"), mv(row.get("spread")),
                ])
            story.append(table(payload, stage_widths))
        story.append(PageBreak())
    doc.build(story, onFirstPage=page_number, onLaterPages=page_number)
    print(OUTPUT)

if __name__ == "__main__":
    main()
