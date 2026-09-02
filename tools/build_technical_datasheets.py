from __future__ import annotations

import math
import os
import re
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Flowable,
    Frame,
    HRFlowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from technical_datasheet_content import all_documents
from technical_datasheet_supplements import supplement_groups


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output" / "pdf"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PAGE_W, PAGE_H = A4
MARGIN_X = 16 * mm
TOP_MARGIN = 18 * mm
BOTTOM_MARGIN = 17 * mm
CONTENT_W = PAGE_W - 2 * MARGIN_X
CONTENT_H = PAGE_H - TOP_MARGIN - BOTTOM_MARGIN

INK = HexColor("#171717")
MUTED = HexColor("#5D636A")
ACCENT = HexColor("#005A9C")
ACCENT_DARK = HexColor("#003B67")
RULE = HexColor("#AEB5BC")
RULE_DARK = HexColor("#646B72")
GRAY_1 = HexColor("#F2F3F4")
GRAY_2 = HexColor("#E2E5E8")
GRAY_3 = HexColor("#CBD0D5")
WHITE = colors.white


def register_fonts() -> None:
    font_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    pdfmetrics.registerFont(TTFont("Arial", str(font_dir / "arial.ttf")))
    pdfmetrics.registerFont(TTFont("Arial-Bold", str(font_dir / "arialbd.ttf")))
    pdfmetrics.registerFont(TTFont("Arial-Italic", str(font_dir / "ariali.ttf")))


register_fonts()


def clean_text(value: Any) -> str:
    text = str(value)
    for dash in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015"):
        text = text.replace(dash, "-")
    customer_terms = {
        "gw_small_tls": "Gateway Rectangle - TLS",
        "gw_large_tls": "Gateway Circle - TLS",
        "gw_small": "Gateway Rectangle - standard",
        "gw_large": "Gateway Circle - standard",
        "ch_small": "CH Rectangle",
        "ch_large": "CH Circle",
        "Prototipe Engineering": "Engineering Prototype",
        "Prototipe Sistem Engineering": "Engineering Prototype System",
    }
    for internal_name, product_name in customer_terms.items():
        text = re.sub(rf"\b{re.escape(internal_name)}\b", product_name, text, flags=re.IGNORECASE)
    return text


def safe(value: Any) -> str:
    return escape(clean_text(value)).replace("\n", "<br/>")


SAMPLE = getSampleStyleSheet()
STYLES: dict[str, ParagraphStyle] = {
    "cover_title": ParagraphStyle("cover_title", parent=SAMPLE["Title"], fontName="Arial-Bold", fontSize=28, leading=31, textColor=INK, spaceAfter=0),
    "cover_label": ParagraphStyle("cover_label", parent=SAMPLE["Normal"], fontName="Arial", fontSize=12, leading=14, textColor=MUTED),
    "cover_subtitle": ParagraphStyle("cover_subtitle", parent=SAMPLE["Normal"], fontName="Arial", fontSize=10.2, leading=14, textColor=INK),
    "cover_meta": ParagraphStyle("cover_meta", parent=SAMPLE["Normal"], fontName="Arial", fontSize=7.6, leading=9.5, textColor=MUTED),
    "h1": ParagraphStyle("Heading1", parent=SAMPLE["Heading1"], fontName="Arial-Bold", fontSize=16, leading=19, textColor=ACCENT_DARK, spaceBefore=8, spaceAfter=5, keepWithNext=True),
    "h2": ParagraphStyle("Heading2", parent=SAMPLE["Heading2"], fontName="Arial-Bold", fontSize=11.4, leading=14, textColor=INK, spaceBefore=7, spaceAfter=2.5, keepWithNext=True),
    "lead": ParagraphStyle("lead", parent=SAMPLE["Normal"], fontName="Arial", fontSize=8.7, leading=11.5, textColor=INK, spaceAfter=5, keepWithNext=True),
    "body": ParagraphStyle("body", parent=SAMPLE["Normal"], fontName="Arial", fontSize=8.3, leading=10.9, textColor=INK),
    "body_bold": ParagraphStyle("body_bold", parent=SAMPLE["Normal"], fontName="Arial-Bold", fontSize=8.1, leading=10.5, textColor=INK),
    "small": ParagraphStyle("small", parent=SAMPLE["Normal"], fontName="Arial", fontSize=7.2, leading=9.2, textColor=INK),
    "tiny": ParagraphStyle("tiny", parent=SAMPLE["Normal"], fontName="Arial", fontSize=6.5, leading=8.1, textColor=MUTED),
    "caption": ParagraphStyle("caption", parent=SAMPLE["Normal"], fontName="Arial-Italic", fontSize=7, leading=8.8, textColor=MUTED, alignment=TA_CENTER, spaceBefore=2, spaceAfter=4),
    "table_head": ParagraphStyle("table_head", parent=SAMPLE["Normal"], fontName="Arial-Bold", fontSize=7.1, leading=8.8, textColor=INK, alignment=TA_LEFT),
    "table_key": ParagraphStyle("table_key", parent=SAMPLE["Normal"], fontName="Arial-Bold", fontSize=7.3, leading=9.2, textColor=INK),
    "table_value": ParagraphStyle("table_value", parent=SAMPLE["Normal"], fontName="Arial", fontSize=7.3, leading=9.2, textColor=INK),
    "toc0": ParagraphStyle("toc0", parent=SAMPLE["Normal"], fontName="Arial-Bold", fontSize=8.5, leading=10, leftIndent=0, firstLineIndent=0, textColor=ACCENT_DARK, spaceBefore=3),
    "toc1": ParagraphStyle("toc1", parent=SAMPLE["Normal"], fontName="Arial", fontSize=7.15, leading=8.5, leftIndent=7 * mm, firstLineIndent=0, textColor=INK),
}


def paragraph(value: Any, style: str = "body") -> Paragraph:
    return Paragraph(safe(value), STYLES[style])


def heading(value: str, level: int, bookmark: str) -> Paragraph:
    result = Paragraph(safe(value), STYLES["h1" if level == 0 else "h2"])
    result._bookmark_name = bookmark  # type: ignore[attr-defined]
    result._outline_level = level  # type: ignore[attr-defined]
    return result


def normalized_label(value: Any) -> str:
    return re.sub(r"\s+", " ", clean_text(value)).strip().casefold()


def compact_table(headers: Iterable[Any], rows: Iterable[Iterable[Any]], widths: list[float] | None = None) -> Table:
    header_list = list(headers)
    row_list = [list(row) for row in rows]
    date_columns = {index for index, item in enumerate(header_list) if normalized_label(item) in {"tanggal", "date", "tanggal terbit", "issue date"}}
    if date_columns:
        header_list = [item for index, item in enumerate(header_list) if index not in date_columns]
        row_list = [[item for index, item in enumerate(row) if index not in date_columns] for row in row_list]
        if widths:
            widths = [value for index, value in enumerate(widths) if index not in date_columns]
    normalized_headers = {normalized_label(item) for item in header_list}
    if normalized_headers & {"rev", "revisi", "revision"} and normalized_headers & {"perubahan", "change"}:
        revision_label = "Pembaruan struktur dan spesifikasi teknis." if "perubahan" in normalized_headers else "Updated technical structure and specifications."
        row_list = [["3.0", revision_label]]
        header_list = [item for item in header_list if normalized_label(item) in {"rev", "revisi", "revision", "perubahan", "change"}]
        widths = [0.18, 0.82]
    if not header_list:
        raise ValueError("Table cannot be empty after column filtering")
    if widths is None or len(widths) != len(header_list):
        widths = [1.0] * len(header_list)
    total = sum(widths)
    col_widths = [CONTENT_W * value / total for value in widths]
    data = [[paragraph(item, "table_head") for item in header_list]]
    data.extend([[paragraph(item, "table_value") for item in row] for row in row_list])
    result = Table(data, colWidths=col_widths, repeatRows=1, splitByRow=1, hAlign="LEFT")
    style: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), GRAY_2),
        ("TEXTCOLOR", (0, 0), (-1, 0), INK),
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, RULE_DARK),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, RULE_DARK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4.2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4.2),
        ("TOPPADDING", (0, 0), (-1, -1), 3.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
    ]
    for index in range(2, len(data), 2):
        style.append(("BACKGROUND", (0, index), (-1, index), HexColor("#FAFAFA")))
    result.setStyle(TableStyle(style))
    return result


def key_value_table(rows: Iterable[tuple[Any, Any]], key_width_mm: float = 45) -> Table:
    data = [[paragraph(key, "table_key"), paragraph(value, "table_value")] for key, value in rows]
    key_width = key_width_mm * mm
    result = Table(data, colWidths=[key_width, CONTENT_W - key_width], splitByRow=1, hAlign="LEFT")
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), GRAY_1),
        ("LINEABOVE", (0, 0), (-1, 0), 0.6, RULE_DARK),
        ("LINEBELOW", (0, -1), (-1, -1), 0.6, RULE_DARK),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return result


def summary_table(items: list[tuple[Any, Any]]) -> Table:
    rows: list[list[Paragraph]] = []
    for start in range(0, len(items), 2):
        pair = items[start:start + 2]
        row: list[Paragraph] = []
        for label, value in pair:
            row.extend([paragraph(label, "table_key"), paragraph(value, "table_value")])
        while len(row) < 4:
            row.extend([paragraph("", "table_key"), paragraph("", "table_value")])
        rows.append(row)
    result = Table(rows, colWidths=[CONTENT_W * value for value in [0.17, 0.33, 0.17, 0.33]], hAlign="LEFT")
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), GRAY_1),
        ("BACKGROUND", (2, 0), (2, -1), GRAY_1),
        ("LINEABOVE", (0, 0), (-1, 0), 0.6, RULE_DARK),
        ("LINEBELOW", (0, -1), (-1, -1), 0.6, RULE_DARK),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return result


def bullets_flowable(items: Iterable[Any]) -> ListFlowable:
    entries = [ListItem(paragraph(item, "body"), leftIndent=5 * mm) for item in items]
    return ListFlowable(entries, bulletType="bullet", start="circle", leftIndent=5 * mm, bulletFontName="Arial", bulletFontSize=6.5, bulletColor=INK, spaceBefore=1, spaceAfter=3)


def note_flowable(text: Any, lang: str) -> Table:
    prefix = "Catatan" if lang == "ID" else "Note"
    note_style = ParagraphStyle("note_inline", parent=STYLES["body"], fontSize=7.7, leading=10, leftIndent=0, textColor=INK)
    content = Paragraph(f"<b>{prefix}:</b> {safe(text)}", note_style)
    result = Table([[content]], colWidths=[CONTENT_W], hAlign="LEFT")
    result.setStyle(TableStyle([
        ("LINEBEFORE", (0, 0), (0, 0), 2.2, ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return result


class BlockDiagramFlowable(Flowable):
    def __init__(self, nodes: list[tuple[str, str]], links: list[str], height: float = 34 * mm):
        super().__init__()
        self.nodes = nodes
        self.links = links
        self.width = CONTENT_W
        self.height = height

    def draw(self) -> None:
        c = self.canv
        count = max(1, len(self.nodes))
        link_font_size = 5.1
        link_labels = [
            clean_text(self.links[index])[:16] if index < len(self.links) else ""
            for index in range(count - 1)
        ]
        gap_widths = [
            max(8.0, pdfmetrics.stringWidth(text, "Arial", link_font_size) + 4.0)
            for text in link_labels
        ]
        box_w = (self.width - sum(gap_widths)) / count
        box_h = self.height - 12
        node_x: list[float] = []
        x = 0.0
        for index, (label, detail) in enumerate(self.nodes):
            node_x.append(x)
            c.setFillColor(WHITE)
            c.setStrokeColor(RULE_DARK)
            c.setLineWidth(0.6)
            c.rect(x, 6, box_w, box_h, fill=1, stroke=1)
            p1 = Paragraph(safe(label), ParagraphStyle("diagram_label", parent=STYLES["table_key"], fontSize=6.9, leading=8.2, alignment=TA_CENTER))
            _, h1 = p1.wrap(box_w - 8, box_h / 2)
            p1.drawOn(c, x + 4, 6 + box_h - h1 - 5)
            p2 = Paragraph(safe(detail), ParagraphStyle("diagram_detail", parent=STYLES["tiny"], fontSize=6.2, leading=7.5, alignment=TA_CENTER, textColor=MUTED))
            _, h2 = p2.wrap(box_w - 8, box_h / 2)
            p2.drawOn(c, x + 4, 11)
            if index < count - 1:
                x += box_w + gap_widths[index]

        # Draw connectors only after every filled node box is complete, so no
        # later box can occlude a connector or its label.
        for index in range(count - 1):
            x1 = node_x[index] + box_w
            x2 = node_x[index + 1]
            y = 6 + box_h / 2
            c.setStrokeColor(ACCENT)
            c.setFillColor(ACCENT)
            c.setLineWidth(0.8)
            c.line(x1, y, x2, y)
            c.line(x2 - 3, y + 2, x2, y)
            c.line(x2 - 3, y - 2, x2, y)
            c.setFillColor(MUTED)
            c.setFont("Arial", link_font_size)
            c.drawCentredString((x1 + x2) / 2, y + 5, link_labels[index])


class SequenceFlowable(Flowable):
    def __init__(self, actors: list[str], steps: list[tuple[int, int, str]]):
        super().__init__()
        self.actors = actors
        self.steps = steps
        self.width = CONTENT_W
        self.height = max(41 * mm, 28 + 16 * len(steps))

    def draw(self) -> None:
        c = self.canv
        actor_w = self.width / max(1, len(self.actors))
        top = self.height - 17
        centers: list[float] = []
        for index, actor in enumerate(self.actors):
            center = actor_w * (index + 0.5)
            centers.append(center)
            c.setFillColor(GRAY_2)
            c.setStrokeColor(RULE_DARK)
            c.rect(center - actor_w * 0.38, top, actor_w * 0.76, 15, fill=1, stroke=1)
            c.setFillColor(INK)
            c.setFont("Arial-Bold", 5.8)
            c.drawCentredString(center, top + 5, clean_text(actor)[:24])
            c.setStrokeColor(GRAY_3)
            c.setDash(2, 2)
            c.line(center, top, center, 4)
        c.setDash()
        gap = (self.height - 38) / max(1, len(self.steps))
        for index, (source, target, label) in enumerate(self.steps):
            y = top - 15 - index * gap
            x1 = centers[source]
            x2 = centers[target]
            c.setStrokeColor(ACCENT)
            c.setFillColor(ACCENT)
            c.setLineWidth(0.8)
            if source == target:
                half = actor_w * 0.25
                start_x, end_x = x1 - half, x1 + half
                c.line(start_x, y, end_x, y)
                c.line(end_x - 3, y + 2, end_x, y)
                c.line(end_x - 3, y - 2, end_x, y)
                label_x, label_w = x1 - actor_w * 0.45, actor_w * 0.9
            else:
                direction = 1 if x2 >= x1 else -1
                c.line(x1, y, x2, y)
                c.line(x2 - direction * 3, y + 2, x2, y)
                c.line(x2 - direction * 3, y - 2, x2, y)
                label_x, label_w = min(x1, x2), max(36, abs(x2 - x1))
            p = Paragraph(safe(label), ParagraphStyle("sequence_label", parent=STYLES["tiny"], fontSize=5.7, leading=6.7, alignment=TA_CENTER, textColor=INK))
            _, label_h = p.wrap(label_w, 14)
            p.drawOn(c, label_x, y + 2)


class BarChartFlowable(Flowable):
    def __init__(self, labels: list[str], values: list[float], unit: str):
        super().__init__()
        self.labels = labels
        self.values = values
        self.unit = unit
        self.width = CONTENT_W
        self.height = 46 * mm

    def draw(self) -> None:
        c = self.canv
        chart_x, chart_y = 28, 18
        chart_w, chart_h = self.width - 36, self.height - 34
        maximum = max(self.values) * 1.1 if self.values else 1
        c.setFillColor(MUTED)
        c.setFont("Arial-Bold", 6.2)
        c.drawString(0, self.height - 8, clean_text(self.unit))
        for index in range(5):
            y = chart_y + chart_h * index / 4
            c.setStrokeColor(GRAY_3)
            c.setLineWidth(0.3)
            c.line(chart_x, y, chart_x + chart_w, y)
            c.setFillColor(MUTED)
            c.setFont("Arial", 5.3)
            c.drawRightString(chart_x - 4, y - 2, f"{maximum * index / 4:.0f}")
        slot = chart_w / max(1, len(self.values))
        bar_w = slot * 0.56
        for index, (label, value) in enumerate(zip(self.labels, self.values)):
            x = chart_x + index * slot + (slot - bar_w) / 2
            height = chart_h * value / maximum
            c.setFillColor(ACCENT if index == len(self.values) - 1 else HexColor("#5B7E99"))
            c.rect(x, chart_y, bar_w, height, fill=1, stroke=0)
            c.setFillColor(INK)
            c.setFont("Arial-Bold", 5.5)
            c.drawCentredString(x + bar_w / 2, chart_y + height + 3, f"{value:g}")
            c.setFillColor(MUTED)
            c.setFont("Arial", 5.4)
            c.drawCentredString(x + bar_w / 2, chart_y - 9, clean_text(label))


class CoverFlowable(Flowable):
    def __init__(self, data: dict[str, Any], lang: str):
        super().__init__()
        self.data = data
        self.lang = lang
        self.width = PAGE_W - 34 * mm
        self.height = PAGE_H - 27 * mm

    def draw(self) -> None:
        c = self.canv
        width = self.width
        y = self.height
        c.setFillColor(ACCENT)
        c.rect(0, y - 5, 14 * mm, 5, fill=1, stroke=0)
        c.setFillColor(INK)
        c.setFont("Arial-Bold", 8)
        c.drawRightString(width, y - 2, "LAB IoT ITB")
        y -= 19 * mm
        title = Paragraph(safe(self.data["product"]), STYLES["cover_title"])
        _, title_h = title.wrap(width, 40 * mm)
        title.drawOn(c, 0, y - title_h)
        y -= title_h + 4
        subtitle_label = Paragraph(f"Technical Datasheet <font color='#5D636A'>Revision {safe(self.data['revision'])}</font>", STYLES["cover_label"])
        _, label_h = subtitle_label.wrap(width, 18 * mm)
        subtitle_label.drawOn(c, 0, y - label_h)
        y -= label_h + 10
        c.setStrokeColor(ACCENT)
        c.setLineWidth(1.6)
        c.line(0, y, width, y)
        y -= 13
        subtitle = paragraph(self.data["subtitle"], "cover_subtitle")
        _, subtitle_h = subtitle.wrap(width * 0.78, 35 * mm)
        subtitle.drawOn(c, 0, y - subtitle_h)
        y -= subtitle_h + 12
        diagram = BlockDiagramFlowable(self.data["cover_nodes"], self.data["cover_links"], 47 * mm)
        diagram.width = width
        diagram.canv = c
        diagram.drawOn(c, 0, y - diagram.height)
        y -= diagram.height + 12
        facts = self.data["facts"]
        fact_data = [
            [paragraph(label, "tiny") for label, _ in facts],
            [Paragraph(f"<b>{safe(value)}</b>", STYLES["body"]) for _, value in facts],
        ]
        fact_table = Table(fact_data, colWidths=[width / len(facts)] * len(facts), hAlign="LEFT")
        fact_table.setStyle(TableStyle([
            ("LINEABOVE", (0, 0), (-1, 0), 0.7, RULE_DARK),
            ("LINEBELOW", (0, -1), (-1, -1), 0.7, RULE_DARK),
            ("LINEBEFORE", (1, 0), (-1, -1), 0.3, RULE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        _, facts_h = fact_table.wrap(width, 28 * mm)
        fact_table.drawOn(c, 0, y - facts_h)
        y -= facts_h + 13
        heading_text = "Fitur utama" if self.lang == "ID" else "Key features"
        c.setFillColor(ACCENT_DARK)
        c.setFont("Arial-Bold", 10.5)
        c.drawString(0, y, heading_text)
        y -= 11
        feature_items: list[str] = []
        for block in self.data["chapters"][0]["blocks"]:
            if block["type"] == "bullets":
                feature_items.extend(block["items"])
        if not feature_items:
            feature_items = [f"{label}: {value}" for label, value in facts]
        split = math.ceil(len(feature_items) / 2)
        columns = [feature_items[:split], feature_items[split:]]
        feature_cells: list[Flowable] = [bullets_flowable(column) for column in columns]
        while len(feature_cells) < 2:
            feature_cells.append(Spacer(1, 1))
        feature_table = Table([feature_cells], colWidths=[width / 2 - 5, width / 2 - 5], hAlign="LEFT")
        feature_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        _, features_h = feature_table.wrap(width, 62 * mm)
        feature_table.drawOn(c, 0, y - features_h)
        y -= features_h + 13
        overview_heading = "Ikhtisar teknis" if self.lang == "ID" else "Technical overview"
        c.setFillColor(ACCENT_DARK)
        c.setFont("Arial-Bold", 10.5)
        c.drawString(0, y, overview_heading)
        y -= 12
        overview_text = self.data["chapters"][0]["lead"]
        overview = paragraph(overview_text, "body")
        _, overview_h = overview.wrap(width, 25 * mm)
        overview.drawOn(c, 0, y - overview_h)
        y -= overview_h + 9
        profile_heading = "Profil fungsi" if self.lang == "ID" else "Functional profile"
        c.setFillColor(ACCENT_DARK)
        c.setFont("Arial-Bold", 10.5)
        c.drawString(0, y, profile_heading)
        y -= 10
        profile_items: list[tuple[Any, Any]] = []
        for block in self.data["chapters"][0]["blocks"]:
            if block["type"] == "cards":
                profile_items.extend(block["items"])
        if profile_items:
            profile_rows = [[paragraph(label, "table_key"), paragraph(value, "table_value")] for label, value in profile_items]
            profile_table = Table(profile_rows, colWidths=[width * 0.28, width * 0.72], hAlign="LEFT")
            profile_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), GRAY_1),
                ("LINEABOVE", (0, 0), (-1, 0), 0.6, RULE_DARK),
                ("LINEBELOW", (0, -1), (-1, -1), 0.6, RULE_DARK),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2.6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
            ]))
            _, profile_h = profile_table.wrap(width, 38 * mm)
            profile_table.drawOn(c, 0, y - profile_h)
            y -= profile_h + 12

        interface_heading = "Antarmuka operasional" if self.lang == "ID" else "Operational interfaces"
        candidate_chapter = self.data["chapters"][3] if self.data["slug"] == "Whole-System" else self.data["chapters"][1]
        interface_rows: list[list[Paragraph]] = []
        for block in candidate_chapter["blocks"]:
            if block["type"] == "kv":
                interface_rows = [[paragraph(label, "table_key"), paragraph(value, "table_value")] for label, value in block["rows"][:4]]
                break
            if block["type"] == "table":
                interface_rows = [
                    [paragraph(row[0], "table_key"), paragraph(" | ".join(clean_text(item) for item in row[1:]), "table_value")]
                    for row in block["rows"][:4]
                ]
                break
        if interface_rows:
            c.setFillColor(ACCENT_DARK)
            c.setFont("Arial-Bold", 10.5)
            c.drawString(0, y, interface_heading)
            y -= 10
            interface_table = Table(interface_rows, colWidths=[width * 0.28, width * 0.72], hAlign="LEFT")
            interface_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), GRAY_1),
                ("LINEABOVE", (0, 0), (-1, 0), 0.6, RULE_DARK),
                ("LINEBELOW", (0, -1), (-1, -1), 0.6, RULE_DARK),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2.4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4),
            ]))
            _, interface_h = interface_table.wrap(width, 42 * mm)
            interface_table.drawOn(c, 0, y - interface_h)
        baseline = clean_text(self.data["firmware"]).replace(" | ", " / ")
        footer_text = f"{safe(self.data['issuer'])} &nbsp;&nbsp;|&nbsp;&nbsp; {safe(self.data['status'])} &nbsp;&nbsp;|&nbsp;&nbsp; {safe(baseline)}"
        footer = Paragraph(footer_text, STYLES["cover_meta"])
        _, footer_h = footer.wrap(width, 18 * mm)
        footer.drawOn(c, 0, 4 * mm)


GROUPS: dict[str, list[tuple[str, str, list[int]]]] = {
    "GasleakDetector": [
        ("Ikhtisar dan arsitektur", "Overview and architecture", [1, 2, 3]),
        ("Sensor channel dan jalur sinyal", "Sensor channels and signal path", [4, 5, 6, 7, 8, 9]),
        ("Inferensi dan mode operasi", "Inference and operating modes", [10, 11, 12, 13]),
        ("Alarm dan catu daya", "Alarm and power", [14, 15, 16, 17, 18]),
        ("Antarmuka komunikasi", "Communication interfaces", [19, 20, 21]),
        ("Komisioning dan diagnostik", "Commissioning and diagnostics", [22, 23]),
        ("Referensi teknis", "Technical references", [24]),
    ],
    "CH": [
        ("Ikhtisar dan perangkat keras", "Overview and hardware", [1, 2, 3, 4, 5]),
        ("Antarmuka radio", "Radio interfaces", [6, 7, 8, 9]),
        ("Routing dan transport", "Routing and transport", [10, 11, 12, 13, 14, 15]),
        ("Sistem energi", "Power system", [16, 17, 18, 19]),
        ("Komisioning dan referensi", "Commissioning and references", [20, 21]),
    ],
    "Gateway": [
        ("Ikhtisar dan perangkat keras", "Overview and hardware", [1, 2, 3, 4, 5]),
        ("Antarmuka LoRa MESH", "LoRa MESH interface", [6, 7]),
        ("Jaringan IP dan MQTT", "IP networking and MQTT", [8, 9, 10, 11, 12, 13]),
        ("Konfigurasi dan komisioning", "Configuration and commissioning", [14, 15, 16, 17]),
        ("Referensi teknis", "Technical references", [18]),
    ],
    "Server": [
        ("Ikhtisar dan arsitektur", "Overview and architecture", [1, 2, 3]),
        ("Validasi dan keamanan frame", "Frame validation and security", [4, 5, 6]),
        ("Alarm, topologi, dan perintah", "Alarm, topology, and commands", [7, 8, 9]),
        ("Broker, penyimpanan, dan penerapan", "Broker, storage, and deployment", [10, 11, 12, 13, 14]),
        ("Referensi teknis", "Technical references", [15]),
    ],
    "Whole-System": [
        ("Ikhtisar sistem", "System overview", [1, 2, 3, 4]),
        ("Alur operasional", "Operational flows", [5, 6, 7]),
        ("Routing dan RF", "Routing and RF", [8, 9, 10]),
        ("Jaringan dan keamanan", "Networking and security", [11, 12, 13]),
        ("Daya, varian, dan penerapan", "Power, variants, and deployment", [14, 15, 16, 17]),
        ("Referensi teknis", "Technical references", [18]),
    ],
}


META_NOTE_PATTERNS = (
    "dokumen ini menggunakan nama produk",
    "this document uses the product name",
    "versi indonesia dan english",
    "indonesian and english versions",
    "nomor halaman di footer",
    "footer numbering",
    "dikonfirmasi pemilik",
    "pemilik mengonfirmasi",
    "owner-confirmed",
    "owner confirms",
    "source/build/package",
    "live belum divalidasi",
    "live customer broker has not been validated",
    "tidak menjadi dasar klaim revisi ini",
    "not part of this revision's claim basis",
    "status produk adalah engineering prototype",
    "product status is engineering prototype",
    "tidak ada klaim ip",
    "does not claim product ip",
    "historical live record",
    "record tersebut tidak membuktikan",
    "that record does not prove",
    "bukan klaim akurasi",
    "not a system accuracy claim",
    "tidak boleh ditulis sebagai response time",
    "must not be presented as gas detection response",
    "bukan product certification",
    "is not product certification",
    "tidak ada klaim rf range",
    "does not claim rf range",
    "tidak ditentukan pada revisi ini",
    "not specified in this revision",
    "tidak ada klaim waktu alarm",
    "no end-to-end alarm time",
    "tidak tersedia pada laporan revisi ini",
    "not included in this revision",
    "belum ada drawing/report",
    "no approved drawing/report",
    "belum dikunci",
    "has not been fixed",
    "tidak ada persistent store-and-forward",
    "there is no persistent store-and-forward",
    "tidak ada klaim end-to-end",
    "no end-to-end command acknowledgement",
    "tidak ada bukti broker",
    "no live customer-broker evidence",
    "tidak menggantikan log connack",
    "does not replace connack logs",
    "tidak menyatakan aplikasi sudah live",
    "does not state that the application is live",
    "tidak ada guaranteed delivery",
    "does not claim guaranteed delivery",
    "tidak membuktikan server customer",
    "does not prove that a customer server",
    "dokumen ini tidak menetapkan sla",
    "this document does not set sla",
    "tidak ada klaim broker live",
    "no live broker",
    "tidak menyatakan deployment final",
    "does not state that a current final deployment",
    "datasheet tidak menyatakan semua sampel",
    "does not state that every sample",
    "source tidak menyediakan jaminan",
    "source does not provide an end-to-end",
    "laporan unit/topology/timestamp",
    "unit/topology/timestamp",
    "tidak ada sla pengiriman",
    "no delivery sla",
    "belum menjadi spesifikasi sistem",
    "not yet system specifications",
    "tidak menggantikan validasi",
    "do not replace current hardware",
    "tidak ada gas-specific performance",
    "no gas-specific performance",
)


SKIP_CHAPTER_PATTERNS = (
    "matriks bukti dan batas klaim",
    "evidence and claim-boundary matrix",
    "status verifikasi dan batas klaim",
    "verification status and claim boundaries",
    "matriks bukti dan batas klaim sistem",
    "system evidence and claim-boundary matrix",
    "gerbang penerimaan end-to-end",
    "end-to-end acceptance gates",
)


def skip_note(text: Any) -> bool:
    lowered = clean_text(text).casefold()
    return any(pattern in lowered for pattern in META_NOTE_PATTERNS)


def skip_chapter(title: Any) -> bool:
    lowered = clean_text(title).casefold()
    return any(pattern in lowered for pattern in SKIP_CHAPTER_PATTERNS)


def flowables_for_block(block: dict[str, Any], lang: str) -> list[Flowable]:
    kind = block["type"]
    result: list[Flowable] = []
    if kind == "cards":
        result.append(summary_table(block["items"]))
    elif kind == "diagram":
        result.append(KeepTogether([BlockDiagramFlowable(block["nodes"], block["links"]), paragraph(block["caption"], "caption")]))
    elif kind == "layers":
        result.append(KeepTogether([
            compact_table(["Tahap" if lang == "ID" else "Stage", "Deskripsi" if lang == "ID" else "Description"], block["items"], [0.28, 0.72]),
            paragraph(block["caption"], "caption"),
        ]))
    elif kind == "sequence":
        result.append(KeepTogether([SequenceFlowable(block["actors"], block["steps"]), paragraph(block["caption"], "caption")]))
    elif kind == "bar":
        result.append(KeepTogether([BarChartFlowable(block["labels"], block["values"], block["unit"]), paragraph(block["caption"], "caption")]))
    elif kind == "kv":
        result.append(key_value_table(block["rows"], block.get("key_width_mm", 45)))
    elif kind == "table":
        result.append(compact_table(block["headers"], block["rows"], block.get("widths")))
    elif kind == "bullets":
        result.append(bullets_flowable(block["items"]))
    elif kind == "note":
        if not skip_note(block["text"]):
            result.append(note_flowable(block["text"], lang))
    else:
        raise ValueError(f"Unknown block type: {kind}")
    if result:
        result.append(Spacer(1, 4))
    return result


class FooterCanvas(canvas.Canvas):
    def __init__(self, *args: Any, doc_info: dict[str, str], total_pages: int, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.doc_info = doc_info
        self.total_pages = total_pages
        self.setTitle(doc_info["title"])
        self.setAuthor(doc_info["issuer"])
        self.setSubject(doc_info["subject"])

    def showPage(self) -> None:
        if self._pageNumber > 1:
            self.saveState()
            self.setFillColor(MUTED)
            self.setFont("Arial", 6.5)
            total = str(self.total_pages) if self.total_pages > 0 else "-"
            self.drawRightString(PAGE_W - MARGIN_X, 9.2 * mm, f"{self._pageNumber} / {total}")
            self.restoreState()
        super().showPage()


class DatasheetDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str, data: dict[str, Any], lang: str):
        super().__init__(filename, pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=TOP_MARGIN, bottomMargin=BOTTOM_MARGIN, title=f"Technical Datasheet - {data['product']} - {lang}", author=data["issuer"], subject=f"Engineering technical datasheet for {data['product']}")
        self.data = data
        self.lang = lang
        self.doc_id = f"IOTITB-TDS-{data['slug'].upper()}-{lang}-R{data['revision']}"
        cover = Frame(17 * mm, 12 * mm, PAGE_W - 34 * mm, PAGE_H - 24 * mm, id="cover", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        body = Frame(MARGIN_X, BOTTOM_MARGIN, CONTENT_W, CONTENT_H, id="body", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([PageTemplate(id="Cover", frames=[cover], onPage=self._cover_page), PageTemplate(id="Body", frames=[body], onPage=self._body_page)])

    def _cover_page(self, canv: canvas.Canvas, doc: BaseDocTemplate) -> None:
        canv.setFillColor(WHITE)
        canv.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    def _body_page(self, canv: canvas.Canvas, doc: BaseDocTemplate) -> None:
        canv.saveState()
        canv.setFillColor(WHITE)
        canv.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        canv.setFillColor(INK)
        canv.setFont("Arial-Bold", 7)
        canv.drawString(MARGIN_X, PAGE_H - 10.7 * mm, self.data["product"])
        canv.setFillColor(MUTED)
        canv.setFont("Arial", 6.4)
        canv.drawRightString(PAGE_W - MARGIN_X, PAGE_H - 10.7 * mm, self.doc_id)
        canv.setStrokeColor(RULE_DARK)
        canv.setLineWidth(0.55)
        canv.line(MARGIN_X, PAGE_H - 13 * mm, PAGE_W - MARGIN_X, PAGE_H - 13 * mm)
        canv.line(MARGIN_X, 12.5 * mm, PAGE_W - MARGIN_X, 12.5 * mm)
        canv.setFillColor(MUTED)
        canv.setFont("Arial", 6.4)
        canv.drawString(MARGIN_X, 9.2 * mm, self.data["issuer"])
        canv.restoreState()

    def afterFlowable(self, flowable: Flowable) -> None:
        bookmark = getattr(flowable, "_bookmark_name", None)
        level = getattr(flowable, "_outline_level", None)
        if bookmark is None or level is None:
            return
        text = flowable.getPlainText() if isinstance(flowable, Paragraph) else str(flowable)
        self.canv.bookmarkPage(bookmark)
        self.canv.addOutlineEntry(text, bookmark, level=level, closed=False)
        self.notify("TOCEntry", (level, text, self.page, bookmark))


def identity_flowables(data: dict[str, Any], lang: str) -> list[Flowable]:
    title = "Identifikasi produk" if lang == "ID" else "Product identification"
    rows = [
        (("Produk" if lang == "ID" else "Product"), data["product"]),
        (("Status produk" if lang == "ID" else "Product status"), data["status"]),
        (("Revisi dokumen" if lang == "ID" else "Document revision"), data["revision"]),
        (("Baseline teknis" if lang == "ID" else "Technical baseline"), data["firmware"]),
        (("Penerbit" if lang == "ID" else "Issuer"), data["issuer"]),
    ]
    result: list[Flowable] = [heading(f"1 {title}", 0, "section-01"), key_value_table(rows, 43), Spacer(1, 6)]
    terms_title = "Singkatan" if lang == "ID" else "Abbreviations"
    result.append(heading(f"1.1 {terms_title}", 1, "section-01-01"))
    abbreviations = [
        item for item in data["abbreviations"]
        if "internal" not in clean_text(item[1]).casefold()
    ]
    term_rows: list[list[str]] = []
    split = math.ceil(len(abbreviations) / 2)
    left = abbreviations[:split]
    right = abbreviations[split:]
    for index in range(split):
        row = [left[index][0], left[index][1]]
        row.extend([right[index][0], right[index][1]] if index < len(right) else ["", ""])
        term_rows.append(row)
    result.append(compact_table([("Singkatan" if lang == "ID" else "Abbreviation"), ("Arti" if lang == "ID" else "Meaning"), ("Singkatan" if lang == "ID" else "Abbreviation"), ("Arti" if lang == "ID" else "Meaning")], term_rows, [0.13, 0.37, 0.13, 0.37]))
    result.append(Spacer(1, 6))
    return result


def build_story(data: dict[str, Any], lang: str) -> list[Flowable]:
    story: list[Flowable] = [CoverFlowable(data, lang), NextPageTemplate("Body"), PageBreak()]
    toc_title = "Daftar isi" if lang == "ID" else "Contents"
    story.extend([Paragraph(safe(toc_title), STYLES["h1"]), HRFlowable(width="100%", thickness=0.6, color=RULE_DARK, spaceBefore=0, spaceAfter=6)])
    toc = TableOfContents()
    toc.levelStyles = [STYLES["toc0"], STYLES["toc1"]]
    toc.dotsMinLevel = 0
    story.extend([toc, PageBreak()])
    story.extend(identity_flowables(data, lang))
    configured_groups = GROUPS[data["slug"]]
    rendered_groups: list[dict[str, Any]] = []
    for id_title, en_title, chapter_indices in configured_groups[:-1]:
        chapters = [
            data["chapters"][chapter_index - 1]
            for chapter_index in chapter_indices
            if not skip_chapter(data["chapters"][chapter_index - 1]["title"])
        ]
        if chapters:
            rendered_groups.append({"title": id_title if lang == "ID" else en_title, "subsections": chapters})
    rendered_groups.extend(supplement_groups(data["slug"], lang))
    id_title, en_title, chapter_indices = configured_groups[-1]
    final_chapters = [
        data["chapters"][chapter_index - 1]
        for chapter_index in chapter_indices
        if not skip_chapter(data["chapters"][chapter_index - 1]["title"])
    ]
    if len(final_chapters) == 1:
        rendered_groups.append({"title": final_chapters[0]["title"], "subsections": final_chapters, "single_chapter": True})
    elif final_chapters:
        rendered_groups.append({"title": id_title if lang == "ID" else en_title, "subsections": final_chapters})

    for group_offset, group in enumerate(rendered_groups, start=2):
        group_title = group["title"]
        story.append(CondPageBreak(55 * mm))
        story.append(heading(f"{group_offset} {group_title}", 0, f"section-{group_offset:02d}"))
        if group.get("single_chapter"):
            chapter = group["subsections"][0]
            if chapter.get("lead"):
                story.append(paragraph(chapter["lead"], "lead"))
            for block in chapter["blocks"]:
                story.extend(flowables_for_block(block, lang))
            continue
        for subsection, chapter in enumerate(group["subsections"], start=1):
            if subsection > 1:
                minimum_opening = 38 * mm
                # Whole System 3.2 starts with a tall sequence diagram.  Give
                # that one opening enough room so its heading and lead cannot
                # be stranded at the foot of the previous page.
                if (
                    data["slug"] == "Whole-System"
                    and group_offset == 3
                    and subsection == 2
                    and chapter["blocks"]
                ):
                    first = chapter["blocks"][0]
                    if first["type"] == "sequence":
                        visual_height = max(41 * mm, 28 + 16 * len(first["steps"]))
                        minimum_opening = visual_height + 18 * mm
                # Whole System 4.2 starts with a compact failover matrix and
                # caption; keep its heading and lead with that visual.
                if (
                    data["slug"] == "Whole-System"
                    and group_offset == 4
                    and subsection == 2
                ):
                    minimum_opening = 50 * mm
                # These compact visual sections otherwise leave their heading
                # and lead on the preceding page while the table begins on the
                # next page.
                if data["slug"] == "CH" and group_offset == 5 and subsection == 4:
                    minimum_opening = 58 * mm
                if data["slug"] == "Whole-System" and group_offset == 6 and subsection == 4:
                    minimum_opening = 60 * mm
                story.append(CondPageBreak(minimum_opening))
            story.append(heading(f"{group_offset}.{subsection} {chapter['title']}", 1, f"section-{group_offset:02d}-{subsection:02d}"))
            if chapter.get("lead"):
                story.append(paragraph(chapter["lead"], "lead"))
            for block in chapter["blocks"]:
                story.extend(flowables_for_block(block, lang))
    while story and isinstance(story[-1], Spacer):
        story.pop()
    return story


def build_one(path: Path, data: dict[str, Any], lang: str) -> int:
    doc_info = {"title": f"Technical Datasheet - {data['product']} - {lang}", "issuer": data["issuer"], "subject": f"Engineering technical datasheet for {data['product']}"}
    counting_path = path.with_name(f".{path.stem}.counting.pdf")

    def build_pass(target: Path, total_pages: int) -> None:
        doc = DatasheetDocTemplate(str(target), data, lang)

        def canvas_factory(*args: Any, **kwargs: Any) -> FooterCanvas:
            return FooterCanvas(*args, doc_info=doc_info, total_pages=total_pages, **kwargs)

        doc.multiBuild(build_story(data, lang), canvasmaker=canvas_factory)

    build_pass(counting_path, 0)
    total_pages = len(PdfReader(str(counting_path)).pages)
    build_pass(path, total_pages)
    final_pages = len(PdfReader(str(path)).pages)
    if final_pages != total_pages:
        raise RuntimeError(
            f"Two-pass pagination changed for {path.name}: count pass {total_pages}, final pass {final_pages}"
        )
    counting_path.unlink(missing_ok=True)
    return final_pages


def build_all() -> list[tuple[Path, int]]:
    results: list[tuple[Path, int]] = []
    for lang in ("ID", "EN"):
        for data in all_documents(lang):
            path = OUTPUT_DIR / f"Technical-Datasheet-{data['slug']}-{lang}.pdf"
            pages = build_one(path, data, lang)
            results.append((path, pages))
    return results


def main() -> None:
    for path, pages in build_all():
        print(f"{path} | {pages} pages")


if __name__ == "__main__":
    main()
