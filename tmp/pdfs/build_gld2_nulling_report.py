"""Create an evidence-bounded PDF report from the recorded GLD2 nulling run."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tmp" / "gld2-nulling-record-2026-08-27.jsonl"
OUTPUT = ROOT / "output" / "pdf" / "GLD2_Nulling_Run_2026-08-27.pdf"

MQ_ORDER = ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"]


def parse_kv(line: str) -> dict[str, str]:
    return dict(re.findall(r"([A-Za-z][A-Za-z0-9_]*)=([^\s]+)", line))


def mv(value: str | None) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value) * 1000:.3f}"
    except ValueError:
        return value


def num(value: str | None) -> str:
    return value if value is not None else "-"


def label_bool(value: str | None) -> str:
    return {"1": "Ya", "0": "Tidak"}.get(value or "", value or "-")


def esc(value: object) -> str:
    text = str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(esc(text), style)


def cell(value: object, style: ParagraphStyle) -> Paragraph:
    return p(str(value), style)


def parse_record() -> tuple[dict[str, dict[str, object]], list[str], str | None]:
    channels: dict[str, dict[str, object]] = {}
    service_done: str | None = None
    raw_notes: list[str] = []
    for raw in SOURCE.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not str(rec.get("kind", "")).startswith("rx"):
            continue
        line = str(rec.get("value", "")).strip()
        if not line.startswith("NULLING_"):
            continue
        if line.startswith("NULLING_SERVICE_DONE"):
            service_done = line
            continue
        kv = parse_kv(line)
        sensor = kv.get("sensor")
        if not sensor:
            if "NULLING_SERVICE" in line:
                raw_notes.append(line)
            continue
        d = channels.setdefault(sensor, {
            "start": None, "baseline": None, "baseline_steps": [], "threshold": None,
            "exp": [], "ranges": [], "bin": [], "bin_done": None,
            "confirm_start": [], "confirm": [], "confirm_extend_start": [],
            "confirm_extend": [], "verify": [], "confirm_ok": None,
            "confirm_fail": None, "ch_ok": None, "ch_fail": None,
            "other": [],
        })
        item = {"time": rec.get("t", ""), "line": line, "kv": kv}
        if line.startswith("NULLING_CH_START"):
            d["start"] = item
        elif line.startswith("NULLING_BASELINE_DONE"):
            d["baseline"] = item
        elif line.startswith("NULLING_BASELINE_STEP"):
            d["baseline_steps"].append(item)
        elif line.startswith("NULLING_THRESHOLD_DERIVED"):
            d["threshold"] = item
        elif line.startswith("NULLING_EXP_STEP"):
            d["exp"].append(item)
        elif line.startswith("NULLING_EXP_RANGE") or line.startswith("NULLING_EXP_RESUME"):
            d["ranges"].append(item)
        elif line.startswith("NULLING_BIN_STEP"):
            d["bin"].append(item)
        elif line.startswith("NULLING_BIN_DONE"):
            d["bin_done"] = item
        elif line.startswith("NULLING_CONFIRM_EXTEND_START"):
            d["confirm_extend_start"].append(item)
        elif line.startswith("NULLING_CONFIRM_EXTEND_STEP"):
            d["confirm_extend"].append(item)
        elif line.startswith("NULLING_CONFIRM_START"):
            d["confirm_start"].append(item)
        elif line.startswith("NULLING_CONFIRM_STEP"):
            d["confirm"].append(item)
        elif "VERIFY" in line and line.startswith("NULLING_CONFIRM"):
            d["verify"].append(item)
        elif line.startswith("NULLING_CONFIRM_OK"):
            d["confirm_ok"] = item
        elif line.startswith("NULLING_CONFIRM_FAIL"):
            d["confirm_fail"] = item
        elif line.startswith("NULLING_CH_OK"):
            d["ch_ok"] = item
        elif line.startswith("NULLING_CH_FAIL"):
            d["ch_fail"] = item
        else:
            d["other"].append(item)
    return channels, raw_notes, service_done


def make_table(headers: list[str], rows: list[list[object]], widths: list[float], styles: dict[str, ParagraphStyle], font_size: int = 6) -> LongTable:
    header_style = ParagraphStyle("header-small", parent=styles["small"], textColor=colors.white, alignment=TA_CENTER, fontSize=font_size)
    row_style = ParagraphStyle("row-small", parent=styles["small"], fontSize=font_size, leading=font_size + 1)
    data = [[cell(h, header_style) for h in headers]] + [[cell(v, row_style) for v in row] for row in rows]
    table = LongTable(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#A6A6A6")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F8FB")]),
    ]))
    return table


def result(channel: dict[str, object]) -> tuple[str, str, str]:
    ok = channel["ch_ok"]
    fail = channel["ch_fail"]
    if ok:
        kv = ok["kv"]
        return "LULUS", kv.get("dac", "-"), f"delta={mv(kv.get('delta'))} mV"
    if fail:
        kv = fail["kv"]
        return "GAGAL", "-", f"stage={kv.get('stage', '-')}; reason={kv.get('reason', '-')}; error={kv.get('error', '-')}"
    return "TIDAK TEREKAM", "-", "Tidak ada baris hasil final di rekaman."


def stage_rows(items: list[dict[str, object]], stage: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for item in items:
        kv = item["kv"]
        if stage == "baseline":
            rows.append([kv.get("code", "-"), mv(kv.get("voltage")), label_bool(kv.get("valid")), label_bool(kv.get("write")), item["time"][-8:]])
        elif stage == "exp":
            rows.append([kv.get("code", "-"), mv(kv.get("voltage")), mv(kv.get("delta")), label_bool(kv.get("valid")), label_bool(kv.get("zeroMargin")), label_bool(kv.get("outBaseline")), item["time"][-8:]])
        elif stage == "bin":
            rows.append([kv.get("low", "-"), kv.get("high", "-"), kv.get("mid", "-"), mv(kv.get("voltage")), mv(kv.get("delta")), label_bool(kv.get("valid")), label_bool(kv.get("outBaseline")), item["time"][-8:]])
        else:
            # Confirm log uses outBaseline, not a crossed field. A point is a
            # threshold crossing when it is valid, above min, zero-margin, and
            # outBaseline=1; expose the raw crossing component faithfully.
            rows.append([kv.get("code", "-"), mv(kv.get("voltage")), mv(kv.get("delta")), label_bool(kv.get("valid")), label_bool(kv.get("aboveMin")), label_bool(kv.get("outBaseline")), item["time"][-8:]])
    return rows


def section(story: list, sensor: str, channel: dict[str, object], styles: dict[str, ParagraphStyle]) -> None:
    status, final_dac, detail = result(channel)
    baseline = channel["baseline"]
    threshold = channel["threshold"]
    summary_rows = [[
        "Hasil", status, "DAC final", final_dac, "Detail", detail,
    ]]
    if baseline:
        kv = baseline["kv"]
        summary_rows.append(["Baseline", f"{mv(kv.get('baseline'))} mV", "Sampel valid", kv.get("validSamples", "-"), "Tolerance stabilitas", f"{mv(kv.get('stabilityTolerance'))} mV"])
    if threshold:
        kv = threshold["kv"]
        summary_rows.append(["Threshold efektif", f"{mv(kv.get('effective'))} mV", "Baseline term", f"{mv(kv.get('baselineTerm'))} mV", "Noise term", f"{mv(kv.get('noiseTerm'))} mV"])
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"{sensor} - proses nulling", styles["report_h2"]))
    story.append(make_table(["Item", "Nilai", "Item", "Nilai", "Item", "Nilai"], summary_rows, [22*mm, 34*mm, 24*mm, 30*mm, 33*mm, 87*mm], styles, 6))
    story.append(Spacer(1, 2 * mm))
    if channel["ch_fail"] and not baseline:
        failure = channel["ch_fail"]["kv"]
        story.append(Paragraph(
            f"Tidak ada data tahap berikutnya: run berhenti untuk {sensor} pada tahap {failure.get('stage', '-')}, "
            f"sebelum baseline dimulai. Alasan rekaman: {failure.get('reason', '-')}; error={failure.get('error', '-') }.",
            styles["note"]
        ))
        story.append(Spacer(1, 2 * mm))

    baseline_rows = stage_rows(channel["baseline_steps"], "baseline")
    story.append(Paragraph("0. Baseline", styles["report_h3"]))
    if baseline_rows:
        story.append(make_table(["DAC", "Tegangan (mV)", "Valid", "Write", "Waktu"], baseline_rows, [18*mm, 34*mm, 24*mm, 24*mm, 24*mm], styles))
    else:
        story.append(Paragraph("Tidak ada titik baseline rinci yang terekam.", styles["note"]))
    story.append(Spacer(1, 2 * mm))

    exp_rows = stage_rows(channel["exp"], "exp")
    story.append(Paragraph("1. Exponential search", styles["report_h3"]))
    if exp_rows:
        story.append(make_table(["DAC", "Tegangan (mV)", "Delta (mV)", "Valid", "Zero margin", "Crossing", "Waktu"], exp_rows, [16*mm, 30*mm, 27*mm, 18*mm, 25*mm, 22*mm, 20*mm], styles))
    else:
        story.append(Paragraph("Tidak ada langkah exponential yang terekam.", styles["note"]))
    for item in channel["ranges"]:
        story.append(Paragraph(f"Bracket/lanjutan yang dicatat: {item['line']}", styles["note"]))
    story.append(Spacer(1, 2 * mm))

    bin_rows = stage_rows(channel["bin"], "bin")
    story.append(Paragraph("2. Binary search", styles["report_h3"]))
    if bin_rows:
        story.append(make_table(["Low", "High", "Mid", "Tegangan (mV)", "Delta (mV)", "Valid", "Crossing", "Waktu"], bin_rows, [16*mm, 16*mm, 16*mm, 30*mm, 27*mm, 18*mm, 22*mm, 20*mm], styles))
        if channel["bin_done"]:
            story.append(Paragraph(f"Hasil binary: {channel['bin_done']['line']}", styles["note"]))
    else:
        story.append(Paragraph("Tidak ada langkah binary yang terekam.", styles["note"]))
    story.append(Spacer(1, 2 * mm))

    story.append(Paragraph("3. Confirm lokal", styles["report_h3"]))
    for item in channel["confirm_start"]:
        story.append(Paragraph(item["line"], styles["note"]))
    confirm_rows = stage_rows(channel["confirm"], "confirm")
    if confirm_rows:
        story.append(make_table(["DAC", "Tegangan (mV)", "Delta (mV)", "Valid", "Di atas min.", "Keluar baseline", "Waktu"], confirm_rows, [16*mm, 30*mm, 27*mm, 18*mm, 25*mm, 22*mm, 20*mm], styles))
    else:
        story.append(Paragraph("Tidak ada titik confirm lokal yang terekam.", styles["note"]))
    story.append(Spacer(1, 2 * mm))

    story.append(Paragraph("4. Confirm extension", styles["report_h3"]))
    for item in channel["confirm_extend_start"]:
        story.append(Paragraph(item["line"], styles["note"]))
    extend_rows = stage_rows(channel["confirm_extend"], "confirm")
    if extend_rows:
        story.append(make_table(["DAC", "Tegangan (mV)", "Delta (mV)", "Valid", "Di atas min.", "Keluar baseline", "Waktu"], extend_rows, [16*mm, 30*mm, 27*mm, 18*mm, 25*mm, 22*mm, 20*mm], styles))
    else:
        story.append(Paragraph("Tidak ada extension confirm yang terekam atau tahap ini tidak dijalankan.", styles["note"]))
    story.append(Spacer(1, 2 * mm))

    story.append(Paragraph("5. Verifikasi dan keputusan", styles["report_h3"]))
    verify_rows = []
    for item in channel["verify"]:
        kv = item["kv"]
        verify_rows.append([kv.get("code", "-"), mv(kv.get("voltage")), mv(kv.get("delta")), label_bool(kv.get("valid")), label_bool(kv.get("aboveMin")), label_bool(kv.get("outBaseline")), item["time"][-8:]])
    if verify_rows:
        story.append(make_table(["DAC", "Tegangan (mV)", "Delta (mV)", "Valid", "Di atas min.", "Keluar baseline", "Waktu"], verify_rows, [16*mm, 30*mm, 27*mm, 18*mm, 25*mm, 22*mm, 20*mm], styles))
    terminal = channel["confirm_ok"] or channel["confirm_fail"] or channel["ch_ok"] or channel["ch_fail"]
    if terminal:
        story.append(Paragraph(f"Baris keputusan: {terminal['line']}", styles["note"]))
    story.append(PageBreak())


def page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#555555"))
    canvas.drawString(12 * mm, 8 * mm, "GLD2 - Audit Rekaman Nulling 8 Kanal | Data dari serial record")
    canvas.drawRightString(285 * mm, 8 * mm, f"Halaman {doc.page}")
    canvas.restoreState()


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    channels, raw_notes, done = parse_record()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("title2", parent=styles["Title"], fontSize=18, leading=22, alignment=TA_CENTER, textColor=colors.HexColor("#17365D")))
    styles.add(ParagraphStyle("sub", parent=styles["Normal"], fontSize=9, leading=12, alignment=TA_CENTER))
    styles.add(ParagraphStyle("report_h2", parent=styles["Heading2"], fontSize=13, leading=16, textColor=colors.HexColor("#17365D"), spaceBefore=4, spaceAfter=3))
    styles.add(ParagraphStyle("report_h3", parent=styles["Heading3"], fontSize=9, leading=11, textColor=colors.HexColor("#1F4E78"), spaceBefore=4, spaceAfter=2))
    styles.add(ParagraphStyle("small", parent=styles["Normal"], fontSize=7, leading=8.5, alignment=TA_LEFT))
    styles.add(ParagraphStyle("note", parent=styles["Normal"], fontSize=7, leading=9, textColor=colors.HexColor("#404040"), spaceAfter=2))
    story: list = []
    story += [
        Spacer(1, 15 * mm),
        Paragraph("Audit Rekaman Nulling GLD2 - 8 Kanal", styles["title2"]),
        Spacer(1, 3 * mm),
        Paragraph("Run pembanding sebelum perbaikan algoritma confirm. Isi laporan hanya berasal dari serial record yang tersimpan.", styles["sub"]),
        Spacer(1, 8 * mm),
        Paragraph("Status dan batas laporan", styles["report_h2"]),
        Paragraph("Run selesai dengan PartialSuccess 4/8. Nilai <= 10 mV, bila disebut dalam review, hanyalah label evaluasi operator dan bukan syarat firmware pada run ini. Tidak ada hasil yang diisi dari perkiraan; tahap atau nilai yang tidak terekam ditandai eksplisit.", styles["Normal"]),
        Spacer(1, 4 * mm),
    ]
    summary = []
    for sensor in MQ_ORDER:
        ch = channels.get(sensor, {})
        if not ch:
            summary.append([sensor, "TIDAK TEREKAM", "-", "Tidak ada channel record"])
            continue
        status, dac, detail = result(ch)
        baseline = ch.get("baseline")
        baseline_val = mv(baseline["kv"].get("baseline")) if baseline else "-"
        summary.append([sensor, status, baseline_val, f"DAC={dac}; {detail}"])
    story.append(make_table(["Sensor", "Hasil", "Baseline (mV)", "Keputusan/penyebab"], summary, [25*mm, 28*mm, 33*mm, 138*mm], styles, 7))
    if done:
        story.append(Spacer(1, 4*mm))
        story.append(Paragraph(f"Ringkasan firmware: {done}", styles["note"]))
    story.append(PageBreak())
    for sensor in MQ_ORDER:
        if sensor in channels:
            section(story, sensor, channels[sensor], styles)
    story.append(Paragraph("Catatan evidensi", styles["report_h2"]))
    story.append(Paragraph("Sumber data: file serial record lokal yang dibuat sepanjang run pembanding GLD2 pada 27 Agustus 2026. Laporan ini tidak menyatakan perbaikan firmware sudah dibangun, di-upload, atau lolos pengujian berikutnya.", styles["Normal"]))
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=landscape(A4), leftMargin=12*mm, rightMargin=12*mm, topMargin=12*mm, bottomMargin=15*mm, title="Audit Rekaman Nulling GLD2 - 8 Kanal", author="PertaminaGLD")
    doc.build(story, onFirstPage=page_number, onLaterPages=page_number)
    print(OUTPUT)


if __name__ == "__main__":
    main()
