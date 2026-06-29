"""
Convert Pertamina_GLD_Visual_End_to_End.md to PDF using reportlab.
- Mermaid diagrams rendered to PNG via mmdc
- Markdown converted using custom parser
- PDF built with reportlab Platypus
"""

import re
import os
import subprocess
import sys
import base64
from pathlib import Path
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, HRFlowable, Preformatted
)
from reportlab.platypus import Image as RLImage
from reportlab.platypus.flowables import Flowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ─── paths ──────────────────────────────────────────────────────────────────
import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--input",  default="D:/PertaminaGLD/Pertamina_GLD_Visual_End_to_End.md")
_ap.add_argument("--output", default="D:/PertaminaGLD/Pertamina_GLD_Visual_End_to_End_System_Explanation.pdf")
_args, _ = _ap.parse_known_args()

MD_FILE  = Path(_args.input)
PDF_FILE = Path(_args.output)
MMDC     = "C:/Users/asus/AppData/Roaming/npm/mmdc.cmd"
WORK_DIR = Path("D:/PertaminaGLD/_mermaid_tmp")
WORK_DIR.mkdir(exist_ok=True)
DOC_TITLE = "Pertamina GLD"

# ─── colours ────────────────────────────────────────────────────────────────
NAVY    = colors.HexColor("#00356b")
BLUE    = colors.HexColor("#004080")
LBLUE   = colors.HexColor("#c8daea")
STRIP   = colors.HexColor("#f0f4fa")
AMBER   = colors.HexColor("#f09020")
AMBER_BG= colors.HexColor("#fffbf0")
CODE_BG = colors.HexColor("#eef1f7")
CODE_FG = colors.HexColor("#1e2236")
WHITE   = colors.white
BLACK   = colors.black
GRAY    = colors.HexColor("#333333")
DKGRAY  = colors.black

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

# ─── styles ─────────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()

def S(name, **kw):
    return ParagraphStyle(name, **kw)

sTitle = S("DocTitle",
           fontName="Helvetica-Bold", fontSize=22,
           textColor=NAVY, spaceAfter=20, alignment=TA_LEFT)

sH1 = S("H1", fontName="Helvetica-Bold", fontSize=15,
        textColor=NAVY, spaceBefore=14, spaceAfter=4)

sH2 = S("H2", fontName="Helvetica-Bold", fontSize=12,
        textColor=BLUE, spaceBefore=12, spaceAfter=3)

sH3 = S("H3", fontName="Helvetica-Bold", fontSize=10.5,
        textColor=DKGRAY, spaceBefore=10, spaceAfter=2)

sH4 = S("H4", fontName="Helvetica-Bold", fontSize=9.5,
        textColor=DKGRAY, spaceBefore=8, spaceAfter=2)

sBody = S("Body", fontName="Helvetica", fontSize=9,
          leading=14, textColor=DKGRAY, spaceAfter=6)

sCode = S("Code", fontName="Courier", fontSize=7.5,
          leading=11, textColor=CODE_FG,
          backColor=CODE_BG, spaceAfter=6,
          leftIndent=8, rightIndent=8,
          borderPad=6)

sCodeInline = S("CodeInline", fontName="Courier", fontSize=8,
                textColor=colors.HexColor("#002255"),
                backColor=CODE_BG)

sNote = S("Note", fontName="Helvetica-Oblique", fontSize=8.5,
          textColor=colors.HexColor("#3a2600"),
          backColor=AMBER_BG, leftIndent=10, rightIndent=4,
          spaceAfter=6, spaceBefore=4,
          borderPad=4)

sTH = S("TH", fontName="Helvetica-Bold", fontSize=8,
        textColor=WHITE, alignment=TA_LEFT)

sTD = S("TD", fontName="Helvetica", fontSize=8,
        textColor=DKGRAY, alignment=TA_LEFT, leading=11)

sTDCode = S("TDCode", fontName="Courier", fontSize=7.5,
            textColor=colors.HexColor("#002255"), alignment=TA_LEFT, leading=11)

sCaption = S("Caption", fontName="Helvetica-Oblique", fontSize=8,
             textColor=DKGRAY, alignment=TA_CENTER, spaceBefore=2, spaceAfter=8)

sMeta = S("Meta", fontName="Helvetica", fontSize=8.5,
          textColor=DKGRAY, spaceAfter=6, leading=14)

sBullet = S("Bullet", fontName="Helvetica", fontSize=9,
            leading=13, textColor=DKGRAY,
            leftIndent=14, spaceAfter=2,
            bulletFontName="Helvetica", bulletFontSize=9)


# ─── custom flowables ───────────────────────────────────────────────────────

class HRule(Flowable):
    def __init__(self, width, color=LBLUE, thickness=1.2):
        super().__init__()
        self.width = width
        self.color = color
        self.thickness = thickness
        self.height = thickness + 4

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, self.thickness / 2, self.width, self.thickness / 2)


class SectionHeading(Flowable):
    """Coloured bar heading used for H2."""
    def __init__(self, text, width, level=2):
        super().__init__()
        self.text = text
        self.width = width
        self.level = level
        self.height = (18 if level == 2 else 14)

    def draw(self):
        c = self.canv
        if self.level == 2:
            c.setFillColor(NAVY)
            c.rect(0, 0, self.width, self.height, fill=1, stroke=0)
            c.setFillColor(WHITE)
            c.setFont("Helvetica-Bold", 11)
            c.drawString(6, 4, self.text)
        else:
            c.setFillColor(STRIP)
            c.rect(0, 0, self.width, self.height, fill=1, stroke=0)
            c.setFillColor(BLUE)
            c.setFont("Helvetica-Bold", 9.5)
            c.drawString(6, 3, self.text)

    def wrap(self, aw, ah):
        return self.width, self.height


# ─── render Mermaid via mmdc ────────────────────────────────────────────────

def render_mermaid(idx: int, src: str) -> Path | None:
    mmd_path = WORK_DIR / f"diag_{idx:02d}.mmd"
    png_path = WORK_DIR / f"diag_{idx:02d}.png"
    mmd_path.write_text(src.strip(), encoding="utf-8")
    r = subprocess.run(
        [MMDC, "-i", str(mmd_path), "-o", str(png_path),
         "--backgroundColor", "white", "--width", "900", "--scale", "2"],
        capture_output=True, text=True, timeout=90
    )
    if r.returncode == 0 and png_path.exists():
        return png_path
    print(f"  [WARN] mmdc failed for diagram {idx}: {r.stderr[:300]}")
    return None


# ─── Markdown parser → flowables ────────────────────────────────────────────

def escape_xml(text: str) -> str:
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))


def process_inline(text: str) -> str:
    """
    Safe inline markdown → reportlab XML.
    Order: extract code spans first → escape XML in non-code parts →
    apply bold/italic only in non-code parts.
    """
    # 1. Split on backtick spans, keep them safe
    parts = re.split(r'(`[^`]+`)', text)
    result_parts = []
    for part in parts:
        if part.startswith('`') and part.endswith('`') and len(part) > 1:
            # code span: escape and wrap, no further markup
            inner = escape_xml(part[1:-1])
            result_parts.append(
                f'<font face="Courier" size="8" color="#003366">{inner}</font>'
            )
        else:
            # non-code: escape XML, then apply bold/italic carefully
            p = escape_xml(part)
            # bold (**text** or __text__) — must not cross code spans
            p = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', p)
            p = re.sub(r'__(.+?)__', r'<b>\1</b>', p)
            # italic only with *word* surrounded by word chars (avoid globbing * )
            # only match * if surrounded by non-space chars
            p = re.sub(r'(?<!\*)\*(?!\s)([^*\n]+?)(?<!\s)\*(?!\*)', r'<i>\1</i>', p)
            result_parts.append(p)
    return ''.join(result_parts)


MERMAID_RE = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)
FENCE_RE   = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
TABLE_RE   = re.compile(r"(\|.+\|\n)+", re.MULTILINE)

def parse_table(block: str):
    """Parse a Markdown table into a reportlab Table flowable."""
    lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
    rows_raw = []
    for line in lines:
        if re.match(r'\|[-: |]+\|', line):
            continue  # separator line
        cells = [c.strip() for c in line.strip('|').split('|')]
        rows_raw.append(cells)

    if not rows_raw:
        return None

    # determine number of columns
    ncols = max(len(r) for r in rows_raw)

    # pad rows
    padded = []
    for r in rows_raw:
        while len(r) < ncols:
            r.append("")
        padded.append(r[:ncols])

    # build cell content
    table_data = []
    for ri, row in enumerate(padded):
        cells = []
        for ci, cell in enumerate(row):
            raw = process_inline(cell)
            style = sTH if ri == 0 else (sTDCode if '`' in cell else sTD)
            cells.append(Paragraph(raw, style))
        table_data.append(cells)

    col_w = CONTENT_W / ncols

    tbl = Table(table_data, colWidths=[col_w] * ncols, repeatRows=1)

    ts = TableStyle([
        # Header
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('TEXTCOLOR',  (0, 0), (-1, 0), WHITE),
        ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',   (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 5),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
        # Body
        ('FONTNAME',   (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE',   (0, 1), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
        ('GRID', (0, 0), (-1, -1), 0.5, LBLUE),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, STRIP]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ])
    tbl.setStyle(ts)
    return tbl


def md_to_flowables(md_text: str) -> list:
    flowables = []
    mermaid_counter = [0]
    first_h1_done = [False]

    # ── pre-pass: extract mermaid and fenced-code blocks ──────────────
    # We tokenize the document into segments: text segments and special blocks.

    class Token:
        def __init__(self, kind, content):
            self.kind = kind      # 'text' | 'mermaid' | 'fence' | 'table'
            self.content = content

    tokens = []
    pos = 0

    # Combined regex for special blocks
    SPECIAL = re.compile(
        r"(```mermaid\n.*?```|```[^\n]*\n.*?```)",
        re.DOTALL
    )

    for m in SPECIAL.finditer(md_text):
        if m.start() > pos:
            tokens.append(Token('text', md_text[pos:m.start()]))
        block = m.group(0)
        if block.startswith("```mermaid"):
            src = re.match(r"```mermaid\n(.*?)```", block, re.DOTALL).group(1)
            tokens.append(Token('mermaid', src))
        else:
            inner = re.match(r"```[^\n]*\n(.*?)```", block, re.DOTALL).group(1)
            tokens.append(Token('fence', inner))
        pos = m.end()

    if pos < len(md_text):
        tokens.append(Token('text', md_text[pos:]))

    # ── per-token processing ───────────────────────────────────────────
    for tok in tokens:
        if tok.kind == 'mermaid':
            mermaid_counter[0] += 1
            idx = mermaid_counter[0]
            print(f"  Rendering Mermaid diagram {idx} ...")
            png = render_mermaid(idx, tok.content)
            if png:
                img_w = CONTENT_W
                try:
                    import PIL.Image as PILImage
                    with PILImage.open(str(png)) as im:
                        pw, ph = im.size
                    aspect = ph / pw
                    img_h = img_w * aspect
                    if img_h > 180 * mm:
                        img_h = 180 * mm
                        img_w = img_h / aspect
                except Exception:
                    img_h = 120 * mm
                from reportlab.platypus import Image as RLImage
                flowables.append(Spacer(1, 4))
                flowables.append(RLImage(str(png), width=img_w, height=img_h))
            else:
                # fallback: show raw mermaid as code
                escaped = tok.content.replace("&", "&amp;").replace("<", "&lt;")
                flowables.append(Preformatted(tok.content, sCode))
            flowables.append(Spacer(1, 4))
            continue

        if tok.kind == 'fence':
            flowables.append(Preformatted(tok.content.rstrip(), sCode))
            flowables.append(Spacer(1, 4))
            continue

        # ── text token: parse line by line ────────────────────────────
        text_block = tok.content

        # Extract inline tables first
        table_positions = []
        for tm in TABLE_RE.finditer(text_block):
            table_positions.append((tm.start(), tm.end(), tm.group(0)))

        # Build segments list alternating text / table
        segs = []
        prev = 0
        for ts, te, tblock in table_positions:
            if ts > prev:
                segs.append(('text', text_block[prev:ts]))
            segs.append(('table', tblock))
            prev = te
        if prev < len(text_block):
            segs.append(('text', text_block[prev:]))

        for seg_kind, seg_content in segs:
            if seg_kind == 'table':
                tbl = parse_table(seg_content)
                if tbl:
                    flowables.append(tbl)
                    flowables.append(Spacer(1, 4))
                continue

            # parse plain text lines
            lines = seg_content.splitlines()
            i = 0
            while i < len(lines):
                line = lines[i]

                # blank
                if not line.strip():
                    flowables.append(Spacer(1, 3))
                    i += 1
                    continue

                # H1
                if line.startswith('# ') and not line.startswith('## '):
                    txt = process_inline(line[2:].strip())
                    if not first_h1_done[0]:
                        # Push title down so it clears the page top margin
                        flowables.append(Spacer(1, 22 * mm))
                        first_h1_done[0] = True
                    else:
                        flowables.append(Spacer(1, 6))
                    flowables.append(Paragraph(txt, sTitle))
                    flowables.append(HRule(CONTENT_W, NAVY, 2))
                    flowables.append(Spacer(1, 16))
                    i += 1
                    continue

                # H2
                if line.startswith('## ') and not line.startswith('### '):
                    txt = line[3:].strip()
                    flowables.append(Spacer(1, 8))
                    flowables.append(SectionHeading(txt, CONTENT_W, level=2))
                    flowables.append(Spacer(1, 4))
                    i += 1
                    continue

                # H3
                if line.startswith('### ') and not line.startswith('#### '):
                    txt = process_inline(line[4:].strip())
                    flowables.append(Spacer(1, 6))
                    flowables.append(Paragraph(txt, sH2))
                    flowables.append(HRule(CONTENT_W, LBLUE, 0.8))
                    flowables.append(Spacer(1, 2))
                    i += 1
                    continue

                # H4
                if line.startswith('#### '):
                    txt = process_inline(line[5:].strip())
                    flowables.append(Paragraph(txt, sH3))
                    i += 1
                    continue

                # HR
                if re.match(r'^---+$', line.strip()):
                    flowables.append(HRule(CONTENT_W))
                    flowables.append(Spacer(1, 4))
                    i += 1
                    continue

                # blockquote
                if line.startswith('> '):
                    quote_lines = []
                    while i < len(lines) and (lines[i].startswith('> ') or lines[i].startswith('>')):
                        quote_lines.append(lines[i].lstrip('> ').strip())
                        i += 1
                    txt = ' '.join(quote_lines)
                    txt = process_inline(txt)
                    flowables.append(Paragraph(f"⚠ {txt}", sNote))
                    continue

                # unordered list
                if re.match(r'^[-*+] ', line):
                    items = []
                    while i < len(lines) and re.match(r'^[-*+] ', lines[i]):
                        item_txt = process_inline(lines[i][2:].strip())
                        items.append(Paragraph(f"• {item_txt}", sBullet))
                        i += 1
                    flowables.extend(items)
                    flowables.append(Spacer(1, 2))
                    continue

                # ordered list
                if re.match(r'^\d+\. ', line):
                    items = []
                    n = 1
                    while i < len(lines) and re.match(r'^\d+\. ', lines[i]):
                        item_txt = process_inline(re.sub(r'^\d+\. ', '', lines[i]).strip())
                        items.append(Paragraph(f"{n}. {item_txt}", sBullet))
                        n += 1
                        i += 1
                    flowables.extend(items)
                    flowables.append(Spacer(1, 2))
                    continue

                # inline code-fence (single-line)
                if line.strip().startswith('```') and line.strip().endswith('```') and len(line.strip()) > 6:
                    inner = line.strip()[3:-3]
                    flowables.append(Preformatted(inner, sCode))
                    i += 1
                    continue

                # regular paragraph
                txt = process_inline(line.strip())
                if txt:
                    flowables.append(Paragraph(txt, sBody))
                i += 1

    return flowables


# ─── page template ──────────────────────────────────────────────────────────

def on_first_page(canvas, doc):
    _draw_header_footer(canvas, doc, first=True)


def on_later_pages(canvas, doc):
    _draw_header_footer(canvas, doc, first=False)


def _draw_header_footer(canvas, doc, first=False):
    canvas.saveState()
    w, h = A4

    if not first:
        # header bar
        canvas.setFillColor(NAVY)
        canvas.rect(MARGIN, h - 14 * mm, w - 2 * MARGIN, 7 * mm, fill=1, stroke=0)
        canvas.setFillColor(WHITE)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.drawString(MARGIN + 3, h - 10 * mm, DOC_TITLE)
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(w - MARGIN - 3, h - 10 * mm, "CONFIDENTIAL")

    # footer
    canvas.setFillColor(LBLUE)
    canvas.rect(MARGIN, 8 * mm, w - 2 * MARGIN, 0.4 * mm, fill=1, stroke=0)
    canvas.setFillColor(BLACK)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(MARGIN, 5.5 * mm, f"Pertamina GLD © 2026-06-29 — Berdasarkan: design dan firmware yang sedang berjalan")
    canvas.drawRightString(w - MARGIN, 5.5 * mm, f"Halaman {doc.page}")

    canvas.restoreState()


# ─── main ───────────────────────────────────────────────────────────────────

def main():
    global DOC_TITLE
    print(f"Reading {MD_FILE} ...")
    md_text = MD_FILE.read_text(encoding="utf-8")

    import re as _re
    m = _re.search(r'^#\s+(.+)', md_text, _re.MULTILINE)
    DOC_TITLE = m.group(1).strip() if m else "Pertamina GLD"

    print("Building PDF content ...")
    story = md_to_flowables(md_text)

    print(f"Writing PDF -> {PDF_FILE} ...")
    doc = SimpleDocTemplate(
        str(PDF_FILE),
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=18 * mm, bottomMargin=16 * mm,
        title="Penjelasan Visual End-to-End Sistem Pertamina GLD",
        author="Claude Code / Pertamina GLD Team",
        subject="IoT Firmware System Documentation",
    )
    doc.build(story,
              onFirstPage=on_first_page,
              onLaterPages=on_later_pages)

    size_kb = PDF_FILE.stat().st_size // 1024
    print(f"\nPDF berhasil: {PDF_FILE}")
    print(f"   Ukuran: {size_kb} KB")


if __name__ == "__main__":
    # install PIL if needed
    try:
        from PIL import Image
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "-q"])

    main()
