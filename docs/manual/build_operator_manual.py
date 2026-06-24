"""
Generator: Manual Operasi GLD - untuk OPERATOR (bukan developer)
Output: gld-operation-manual.pdf
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate
from reportlab.lib.colors import HexColor
import os

# ── Warna Brand ───────────────────────────────────────────────────────────────
ORANGE    = HexColor("#E65C00")
ORANGE_LT = HexColor("#FFF3EB")
DARK      = HexColor("#1A1A2E")
GRAY      = HexColor("#6B7280")
GRAY_LT   = HexColor("#F3F4F6")
GREEN     = HexColor("#15803D")
GREEN_LT  = HexColor("#DCFCE7")
RED       = HexColor("#DC2626")
RED_LT    = HexColor("#FEE2E2")
YELLOW_LT = HexColor("#FEFCE8")
YELLOW    = HexColor("#CA8A04")
BLUE_LT   = HexColor("#EFF6FF")
BLUE      = HexColor("#1D4ED8")
WHITE     = colors.white

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "gld-operation-manual.pdf")

# ── Gaya teks ─────────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()

def s(name, **kw):
    base = styles[name] if name in styles else styles["Normal"]
    return ParagraphStyle(name + "_custom_" + str(id(kw)), parent=base, **kw)

TITLE_STYLE    = s("Title",    fontSize=28, textColor=WHITE,  alignment=TA_CENTER, spaceAfter=6, fontName="Helvetica-Bold")
SUBTITLE_STYLE = s("Normal",   fontSize=13, textColor=ORANGE_LT, alignment=TA_CENTER, spaceAfter=4)
H1             = s("Heading1", fontSize=16, textColor=ORANGE, fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=6)
H2             = s("Heading2", fontSize=12, textColor=DARK,   fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4)
BODY           = s("Normal",   fontSize=10, textColor=DARK,   leading=15, spaceAfter=4)
BODY_J         = s("Normal",   fontSize=10, textColor=DARK,   leading=15, spaceAfter=4, alignment=TA_JUSTIFY)
SMALL          = s("Normal",   fontSize=9,  textColor=GRAY,   leading=13)
BOLD           = s("Normal",   fontSize=10, textColor=DARK,   fontName="Helvetica-Bold", leading=15)
STEP           = s("Normal",   fontSize=10, textColor=DARK,   leading=15, leftIndent=10)
CENTER         = s("Normal",   fontSize=10, textColor=DARK,   alignment=TA_CENTER)
FOOTER_S       = s("Normal",   fontSize=8,  textColor=GRAY,   alignment=TA_CENTER)
TABLE_HDR      = s("Normal",   fontSize=9,  textColor=WHITE,  fontName="Helvetica-Bold", alignment=TA_CENTER)
TABLE_CELL     = s("Normal",   fontSize=9,  textColor=DARK,   leading=13)
TABLE_CELL_C   = s("Normal",   fontSize=9,  textColor=DARK,   leading=13, alignment=TA_CENTER)
WARN_TITLE     = s("Normal",   fontSize=10, textColor=RED,    fontName="Helvetica-Bold")
INFO_TITLE     = s("Normal",   fontSize=10, textColor=BLUE,   fontName="Helvetica-Bold")
NOTE_TITLE     = s("Normal",   fontSize=10, textColor=YELLOW, fontName="Helvetica-Bold")
OK_TITLE       = s("Normal",   fontSize=10, textColor=GREEN,  fontName="Helvetica-Bold")

# ── Helper flowables ──────────────────────────────────────────────────────────
def hr(color=ORANGE, thickness=1.5):
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceAfter=6)

def sp(h=6):
    return Spacer(1, h)

def box(title_style, title_text, body_lines, bg_color, border_color):
    """Kotak info/warning/catatan."""
    content = [[
        Paragraph(title_text, title_style),
        *[Paragraph(line, s("Normal", fontSize=9, textColor=DARK, leading=13))
          for line in body_lines]
    ]]
    # Flatten to single column
    rows = [[Paragraph(title_text, title_style)]] + \
           [[Paragraph(line, s("Normal", fontSize=9, textColor=DARK, leading=13))]
            for line in body_lines]
    tbl = Table(rows, colWidths=[15.5*cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), bg_color),
        ("BOX",        (0,0), (-1,-1), 1.5, border_color),
        ("LEFTPADDING",  (0,0), (-1,-1), 10),
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
        ("TOPPADDING",   (0,0), (0,0),  8),
        ("BOTTOMPADDING",(0,-1),(-1,-1),8),
        ("TOPPADDING",   (0,1), (-1,-1), 2),
    ]))
    return tbl

def warn(lines):
    return box(WARN_TITLE, "⚠  PERINGATAN", lines, RED_LT,    RED)

def info(lines):
    return box(INFO_TITLE, "ℹ  INFORMASI",  lines, BLUE_LT,   BLUE)

def note(lines):
    return box(NOTE_TITLE, "📝  CATATAN",   lines, YELLOW_LT, YELLOW)

def ok_box(lines):
    return box(OK_TITLE,   "✔  KONDISI NORMAL", lines, GREEN_LT, GREEN)

def tbl(data, col_widths, header_row=True, zebra=True):
    """Tabel standar."""
    t = Table(data, colWidths=col_widths)
    style = [
        ("FONTNAME",  (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE",  (0,0), (-1,-1), 9),
        ("VALIGN",    (0,0), (-1,-1), "MIDDLE"),
        ("GRID",      (0,0), (-1,-1), 0.5, HexColor("#D1D5DB")),
        ("LEFTPADDING",  (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
    ]
    if header_row:
        style += [
            ("BACKGROUND", (0,0), (-1,0), ORANGE),
            ("TEXTCOLOR",  (0,0), (-1,0), WHITE),
            ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ]
    if zebra:
        start = 1 if header_row else 0
        for i in range(start, len(data)):
            if i % 2 == (0 if not header_row else 1):
                style.append(("BACKGROUND", (0,i), (-1,i), GRAY_LT))
    t.setStyle(TableStyle(style))
    return t

def numbered_step(n, text):
    data = [[
        Paragraph(f"<b>{n}</b>", s("Normal", fontSize=10, textColor=ORANGE, fontName="Helvetica-Bold", alignment=TA_CENTER)),
        Paragraph(text, BODY)
    ]]
    t = Table(data, colWidths=[0.7*cm, 14.8*cm])
    t.setStyle(TableStyle([
        ("VALIGN",  (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING",   (0,0), (-1,-1), 2),
        ("BOTTOMPADDING",(0,0), (-1,-1), 2),
    ]))
    return t

# ── Header/Footer callback ────────────────────────────────────────────────────
def draw_page_decorations(canvas, doc):
    canvas.saveState()
    w, h = A4

    # Header bar
    canvas.setFillColor(ORANGE)
    canvas.rect(0, h - 1.5*cm, w, 1.5*cm, fill=1, stroke=0)

    if doc.page > 1:
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(WHITE)
        canvas.drawString(1.5*cm, h - 1.0*cm, "MANUAL OPERASI GLD")
        canvas.drawRightString(w - 1.5*cm, h - 1.0*cm, "Pertamina GLD v0.8.0")

    # Footer bar
    canvas.setFillColor(DARK)
    canvas.rect(0, 0, w, 1.0*cm, fill=1, stroke=0)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GRAY_LT)
    canvas.drawString(1.5*cm, 0.35*cm, "Dokumen ini bersifat RAHASIA — hanya untuk operator yang berwenang")
    canvas.drawRightString(w - 1.5*cm, 0.35*cm, f"Halaman {doc.page}")

    canvas.restoreState()

# ── Cover page ────────────────────────────────────────────────────────────────
def cover_page():
    story = []

    # Background box (simulasi dengan tabel)
    cover_bg = Table(
        [[Paragraph("MANUAL OPERASI", TITLE_STYLE)],
         [Paragraph("Gas Leak Detector (GLD)", SUBTITLE_STYLE)],
         [Paragraph("Sistem Pendeteksi Kebocoran Gas", s("Normal", fontSize=11, textColor=HexColor("#FFD4B3"), alignment=TA_CENTER))],
         [Spacer(1, 10)],
         [Paragraph("Versi Firmware: GLD v0.8.0  |  CH v0.6.0", s("Normal", fontSize=9, textColor=HexColor("#FFD4B3"), alignment=TA_CENTER))],
         [Paragraph("2026", s("Normal", fontSize=9, textColor=HexColor("#FFD4B3"), alignment=TA_CENTER))],
        ],
        colWidths=[15.5*cm]
    )
    cover_bg.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), DARK),
        ("BOX",           (0,0), (-1,-1), 3, ORANGE),
        ("TOPPADDING",    (0,0), (-1,-1), 12),
        ("BOTTOMPADDING", (0,-1),(-1,-1), 20),
        ("LEFTPADDING",   (0,0), (-1,-1), 20),
        ("RIGHTPADDING",  (0,0), (-1,-1), 20),
    ]))

    story.append(Spacer(1, 2*cm))
    story.append(cover_bg)
    story.append(Spacer(1, 1*cm))

    # Tagline
    story.append(Paragraph(
        "Dokumen ini ditujukan untuk <b>OPERATOR LAPANGAN</b>.<br/>Berisi prosedur pengoperasian, penanganan alarm, dan panduan troubleshooting sederhana.",
        s("Normal", fontSize=10, textColor=GRAY, alignment=TA_CENTER, leading=16)
    ))
    story.append(Spacer(1, 0.5*cm))

    # Peringatan cover
    cover_warn = Table([[
        Paragraph(
            "<b>⚠  PERHATIAN</b>  Baca seluruh manual ini sebelum mengoperasikan perangkat GLD. "
            "Perangkat ini mendeteksi kebocoran gas berbahaya. Ikuti prosedur dengan benar "
            "untuk keselamatan kerja.",
            s("Normal", fontSize=9, textColor=DARK, leading=14)
        )
    ]], colWidths=[15.5*cm])
    cover_warn.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), HexColor("#FFF3EB")),
        ("BOX",           (0,0), (-1,-1), 2, ORANGE),
        ("LEFTPADDING",   (0,0), (-1,-1), 12),
        ("RIGHTPADDING",  (0,0), (-1,-1), 12),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
    ]))
    story.append(cover_warn)
    story.append(Spacer(1, 1*cm))

    # Revisi info
    rev_data = [
        [Paragraph("Versi", TABLE_HDR), Paragraph("Tanggal", TABLE_HDR), Paragraph("Keterangan", TABLE_HDR)],
        [Paragraph("1.0", TABLE_CELL_C), Paragraph("2026-06-19", TABLE_CELL_C), Paragraph("Rilis awal — GLD v0.8.0", TABLE_CELL)],
    ]
    story.append(tbl(rev_data, [2.5*cm, 4*cm, 9*cm]))

    story.append(PageBreak())
    return story

# ── Daftar Isi ────────────────────────────────────────────────────────────────
def table_of_contents():
    story = [Paragraph("DAFTAR ISI", H1), hr()]
    entries = [
        ("1", "Pengenalan Sistem GLD",                    "3"),
        ("2", "Komponen dan Indikator",                   "4"),
        ("3", "Mode Operasi",                             "5"),
        ("4", "Prosedur Start-Up",                        "6"),
        ("5", "Operasi Normal — Mode Inference",          "7"),
        ("6", "Prosedur Alarm",                           "8"),
        ("7", "Mengganti Mode Operasi",                   "9"),
        ("8", "Prosedur Kalibrasi (Nulling)",            "10"),
        ("9", "Prosedur Pengambilan Data (Dataset)",     "11"),
        ("10","Monitoring dari Komputer / Server",       "12"),
        ("11","Troubleshooting",                         "13"),
        ("12","Checklist Harian Operator",               "14"),
    ]
    toc_data = [[Paragraph(f"<b>{no}.</b> {label}", s("Normal", fontSize=10, textColor=DARK, leading=16)),
                 Paragraph(f"<b>{page}</b>", s("Normal", fontSize=10, textColor=ORANGE, alignment=TA_CENTER))]
                for no, label, page in entries]
    t = Table(toc_data, colWidths=[13.5*cm, 2*cm])
    t.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("LINEBELOW",     (0,0), (-1,-1), 0.3, HexColor("#E5E7EB")),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
    ]))
    story.append(t)
    story.append(PageBreak())
    return story

# ── Bab 1: Pengenalan ─────────────────────────────────────────────────────────
def chapter1():
    story = [Paragraph("1. PENGENALAN SISTEM GLD", H1), hr()]
    story.append(Paragraph(
        "Gas Leak Detector (GLD) adalah perangkat yang secara otomatis mendeteksi kebocoran gas "
        "berbahaya di lingkungan kerja. GLD menggunakan sensor MQ untuk membaca konsentrasi gas, "
        "memproses data dengan kecerdasan buatan (AI), dan mengirimkan hasilnya secara nirkabel ke "
        "server pusat melalui jaringan LoRa.",
        BODY_J
    ))
    story.append(sp())

    # Komponen sistem
    story.append(Paragraph("Komponen Sistem", H2))
    komponen = [
        [Paragraph("Komponen", TABLE_HDR), Paragraph("Fungsi", TABLE_HDR)],
        [Paragraph("<b>GLD (Sensor Node)</b>", TABLE_CELL),
         Paragraph("Membaca 8 sensor gas, menjalankan model AI, mengirim data via LoRa", TABLE_CELL)],
        [Paragraph("<b>CH (Cluster Head)</b>", TABLE_CELL),
         Paragraph("Penerima data dari GLD, meneruskan ke Gateway", TABLE_CELL)],
        [Paragraph("<b>Gateway</b>", TABLE_CELL),
         Paragraph("Meneruskan data dari CH ke server via jaringan WiFi/LAN", TABLE_CELL)],
        [Paragraph("<b>Server / Node-RED</b>", TABLE_CELL),
         Paragraph("Memproses, menyimpan, dan menampilkan data dari semua GLD", TABLE_CELL)],
    ]
    story.append(tbl(komponen, [5*cm, 10.5*cm]))
    story.append(sp(8))

    # Alur data
    story.append(Paragraph("Alur Data", H2))
    alur = Table([[
        Paragraph("GLD", s("Normal", fontSize=9, textColor=WHITE, fontName="Helvetica-Bold", alignment=TA_CENTER)),
        Paragraph("→", s("Normal", fontSize=14, textColor=ORANGE, alignment=TA_CENTER)),
        Paragraph("CH", s("Normal", fontSize=9, textColor=WHITE, fontName="Helvetica-Bold", alignment=TA_CENTER)),
        Paragraph("→", s("Normal", fontSize=14, textColor=ORANGE, alignment=TA_CENTER)),
        Paragraph("Gateway", s("Normal", fontSize=9, textColor=WHITE, fontName="Helvetica-Bold", alignment=TA_CENTER)),
        Paragraph("→", s("Normal", fontSize=14, textColor=ORANGE, alignment=TA_CENTER)),
        Paragraph("Server", s("Normal", fontSize=9, textColor=WHITE, fontName="Helvetica-Bold", alignment=TA_CENTER)),
    ]], colWidths=[2.3*cm, 1*cm, 2.3*cm, 1*cm, 2.7*cm, 1*cm, 2.7*cm])
    alur.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (0,0), ORANGE),
        ("BACKGROUND",    (2,0), (2,0), DARK),
        ("BACKGROUND",    (4,0), (4,0), DARK),
        ("BACKGROUND",    (6,0), (6,0), DARK),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("RIGHTPADDING",  (0,0), (-1,-1), 4),
        ("ALIGN",         (1,0), (1,0), "CENTER"),
        ("ALIGN",         (3,0), (3,0), "CENTER"),
        ("ALIGN",         (5,0), (5,0), "CENTER"),
    ]))
    story.append(alur)
    story.append(sp(8))

    story.append(info([
        "GLD bekerja secara otomatis. Operator cukup memastikan perangkat menyala,",
        "indikator berstatus normal, dan merespons jika alarm berbunyi.",
    ]))
    story.append(PageBreak())
    return story

# ── Bab 2: Komponen dan Indikator ────────────────────────────────────────────
def chapter2():
    story = [Paragraph("2. KOMPONEN DAN INDIKATOR", H1), hr()]

    story.append(Paragraph("Indikator Visual dan Bunyi", H2))
    ind_data = [
        [Paragraph("Indikator", TABLE_HDR), Paragraph("Status", TABLE_HDR), Paragraph("Artinya", TABLE_HDR)],
        [Paragraph("Lampu Alarm (Merah)", TABLE_CELL),
         Paragraph("MENYALA", s("Normal", fontSize=9, textColor=RED, fontName="Helvetica-Bold", leading=13)),
         Paragraph("Gas berbahaya terdeteksi — lakukan prosedur alarm", TABLE_CELL)],
        [Paragraph("Lampu Alarm (Merah)", TABLE_CELL),
         Paragraph("MATI", s("Normal", fontSize=9, textColor=GREEN, fontName="Helvetica-Bold", leading=13)),
         Paragraph("Kondisi normal — tidak ada gas terdeteksi", TABLE_CELL)],
        [Paragraph("Buzzer", TABLE_CELL),
         Paragraph("BERBUNYI", s("Normal", fontSize=9, textColor=RED, fontName="Helvetica-Bold", leading=13)),
         Paragraph("Gas berbahaya terdeteksi — selalu berbarengan dengan lampu alarm", TABLE_CELL)],
        [Paragraph("LED Status", TABLE_CELL),
         Paragraph("MENYALA", s("Normal", fontSize=9, textColor=ORANGE, fontName="Helvetica-Bold", leading=13)),
         Paragraph("GLD sedang aktif mendeteksi gas (mode inference)", TABLE_CELL)],
        [Paragraph("LED Status", TABLE_CELL),
         Paragraph("MATI", s("Normal", fontSize=9, textColor=GRAY, fontName="Helvetica-Bold", leading=13)),
         Paragraph("GLD berada di mode dataset atau nulling, atau belum siap", TABLE_CELL)],
    ]
    story.append(tbl(ind_data, [3.5*cm, 2.5*cm, 9.5*cm]))
    story.append(sp(8))

    story.append(Paragraph("Port dan Koneksi", H2))
    port_data = [
        [Paragraph("Port/Koneksi", TABLE_HDR), Paragraph("Keterangan", TABLE_HDR)],
        [Paragraph("USB (Serial)", TABLE_CELL),    Paragraph("Untuk koneksi komputer, setting mode, dan monitor log", TABLE_CELL)],
        [Paragraph("Antena LoRa", TABLE_CELL),     Paragraph("Antena untuk komunikasi nirkabel ke CH — jangan dilepas saat aktif", TABLE_CELL)],
        [Paragraph("Power Supply", TABLE_CELL),    Paragraph("GLD bisa beroperasi dari baterai atau adaptor 5V external", TABLE_CELL)],
        [Paragraph("WiFi (internal)", TABLE_CELL), Paragraph("Aktif otomatis saat mode dataset atau nulling", TABLE_CELL)],
    ]
    story.append(tbl(port_data, [4.5*cm, 11*cm]))
    story.append(sp(8))

    story.append(warn([
        "Jangan mencabut antena LoRa saat GLD sedang beroperasi.",
        "Jangan membuka casing GLD tanpa instruksi dari teknisi.",
        "Pastikan supply daya stabil. Putusnya daya saat kalibrasi dapat merusak profil sensor.",
    ]))
    story.append(PageBreak())
    return story

# ── Bab 3: Mode Operasi ───────────────────────────────────────────────────────
def chapter3():
    story = [Paragraph("3. MODE OPERASI", H1), hr()]
    story.append(Paragraph(
        "GLD memiliki tiga mode operasi. Setiap mode memiliki fungsi yang berbeda. "
        "Mode yang aktif disimpan di memori GLD dan tidak berubah setelah restart.",
        BODY_J
    ))
    story.append(sp(8))

    mode_data = [
        [Paragraph("Mode", TABLE_HDR), Paragraph("Nama Tampilan", TABLE_HDR),
         Paragraph("Fungsi", TABLE_HDR), Paragraph("Kondisi Normal", TABLE_HDR)],
        [Paragraph("<b>INFERENCE</b>\n(Running)", TABLE_CELL),
         Paragraph("inference", s("Normal", fontSize=9, textColor=ORANGE, fontName="Courier-Bold", leading=13)),
         Paragraph("Mode operasi utama. GLD membaca sensor setiap detik, menjalankan AI, dan mengirim hasil via LoRa ke CH setiap 10 detik.", TABLE_CELL),
         Paragraph("LED Status menyala. Lampu alarm mati. Buzzer mati.", TABLE_CELL)],
        [Paragraph("<b>DATASET</b>\n(Pengambilan Data)", TABLE_CELL),
         Paragraph("dataset", s("Normal", fontSize=9, textColor=BLUE, fontName="Courier-Bold", leading=13)),
         Paragraph("Mode pengambilan data pelatihan. GLD terhubung ke WiFi dan mengirim data sensor ke server via MQTT. Digunakan oleh teknisi.", TABLE_CELL),
         Paragraph("LED Status mati. GLD terhubung ke jaringan WiFi.", TABLE_CELL)],
        [Paragraph("<b>NULLING</b>\n(Kalibrasi)", TABLE_CELL),
         Paragraph("nulling", s("Normal", fontSize=9, textColor=GREEN, fontName="Courier-Bold", leading=13)),
         Paragraph("Mode kalibrasi sensor. GLD menjalankan proses kalibrasi otomatis dan menyimpan profil baseline. Dilakukan setelah pemasangan atau perawatan.", TABLE_CELL),
         Paragraph("LED Status mati. Proses otomatis berjalan setelah boot.", TABLE_CELL)],
    ]
    story.append(tbl(mode_data, [2.8*cm, 2.5*cm, 6*cm, 4.2*cm]))
    story.append(sp(8))

    story.append(info([
        "Untuk operasi harian, GLD harus berada di mode INFERENCE.",
        "Jika GLD berada di mode lain, hubungi teknisi atau ikuti prosedur di Bab 7.",
    ]))
    story.append(PageBreak())
    return story

# ── Bab 4: Prosedur Start-Up ──────────────────────────────────────────────────
def chapter4():
    story = [Paragraph("4. PROSEDUR START-UP", H1), hr()]
    story.append(Paragraph(
        "Ikuti langkah berikut setiap kali GLD dinyalakan atau setelah mati.",
        BODY
    ))
    story.append(sp(6))

    steps = [
        "Pastikan antena LoRa terpasang dengan kencang.",
        "Hubungkan GLD ke sumber daya (adaptor 5V atau pastikan baterai terisi).",
        "GLD akan otomatis menyala dan melakukan boot.",
        "Tunggu ±5 detik hingga GLD selesai inisialisasi.",
        "Periksa indikator:\n  • LED Status menyala → mode inference aktif (normal)\n  • Lampu alarm mati → tidak ada deteksi gas (normal)",
        "GLD siap beroperasi.",
    ]
    for i, step in enumerate(steps, 1):
        story.append(numbered_step(i, step))
        story.append(sp(3))

    story.append(sp(6))
    story.append(ok_box([
        "Kondisi normal setelah start-up:",
        "• LED Status: MENYALA",
        "• Lampu Alarm: MATI",
        "• Buzzer: MATI",
        "• GLD mengirim data ke CH setiap ±10 detik (tidak terlihat secara langsung)",
    ]))
    story.append(sp(8))
    story.append(warn([
        "Jika LED Status tidak menyala dalam 30 detik setelah boot, GLD mungkin mengalami masalah.",
        "Lihat Bab 11 — Troubleshooting atau hubungi teknisi.",
    ]))
    story.append(PageBreak())
    return story

# ── Bab 5: Operasi Normal ─────────────────────────────────────────────────────
def chapter5():
    story = [Paragraph("5. OPERASI NORMAL — MODE INFERENCE", H1), hr()]
    story.append(Paragraph(
        "Saat GLD beroperasi normal di mode inference, perangkat bekerja secara otomatis. "
        "Operator tidak perlu melakukan tindakan apapun selama kondisi normal.",
        BODY_J
    ))
    story.append(sp(8))

    story.append(Paragraph("Yang terjadi secara otomatis:", H2))
    auto_steps = [
        "GLD membaca 8 sensor gas setiap ±1 detik.",
        "Model AI memproses data sensor dan menentukan jenis dan konsentrasi gas.",
        "Setiap ±10 detik, GLD mengirimkan hasil via LoRa ke CH (Cluster Head).",
        "CH meneruskan data ke Gateway, kemudian ke server.",
        "Jika gas berbahaya terdeteksi dengan keyakinan tinggi, alarm aktif.",
    ]
    for i, step in enumerate(auto_steps, 1):
        story.append(numbered_step(i, step))
        story.append(sp(3))

    story.append(sp(8))
    story.append(Paragraph("Tanggung Jawab Operator Harian", H2))
    tugas = [
        [Paragraph("Frekuensi", TABLE_HDR), Paragraph("Tugas Operator", TABLE_HDR)],
        [Paragraph("Setiap hari", TABLE_CELL),   Paragraph("Periksa LED Status menyala. Pastikan tidak ada alarm aktif.", TABLE_CELL)],
        [Paragraph("Setiap hari", TABLE_CELL),   Paragraph("Pastikan antena LoRa terpasang dan tidak tertekuk.", TABLE_CELL)],
        [Paragraph("Setiap minggu", TABLE_CELL), Paragraph("Bersihkan lubang sensor dari debu atau kotoran dengan kuas halus.", TABLE_CELL)],
        [Paragraph("Jika ada alarm", TABLE_CELL),Paragraph("Ikuti prosedur di Bab 6.", TABLE_CELL)],
        [Paragraph("Jika mode berubah", TABLE_CELL),Paragraph("Ikuti prosedur di Bab 7 untuk kembali ke mode inference.", TABLE_CELL)],
    ]
    story.append(tbl(tugas, [3.5*cm, 12*cm]))
    story.append(sp(8))

    story.append(note([
        "GLD mengirim data setiap ±10 detik. Ini adalah perilaku normal.",
        "Tidak ada visual yang terlihat saat GLD mengirim data — ini normal.",
        "LED Status yang menyala terus-menerus adalah tanda operasi normal.",
    ]))
    story.append(PageBreak())
    return story

# ── Bab 6: Prosedur Alarm ─────────────────────────────────────────────────────
def chapter6():
    story = [Paragraph("6. PROSEDUR ALARM", H1), hr()]

    story.append(warn([
        "Alarm berarti GLD mendeteksi kebocoran gas berbahaya.",
        "Tindak segera — jangan abaikan alarm.",
    ]))
    story.append(sp(8))

    story.append(Paragraph("Tanda-Tanda Alarm Aktif", H2))
    tanda_data = [
        [Paragraph("Indikator", TABLE_HDR), Paragraph("Status saat Alarm", TABLE_HDR)],
        [Paragraph("Lampu Alarm", TABLE_CELL), Paragraph("MENYALA MERAH (terus-menerus)", s("Normal", fontSize=9, textColor=RED, fontName="Helvetica-Bold", leading=13))],
        [Paragraph("Buzzer", TABLE_CELL),      Paragraph("BERBUNYI", s("Normal", fontSize=9, textColor=RED, fontName="Helvetica-Bold", leading=13))],
        [Paragraph("LED Status", TABLE_CELL),  Paragraph("Tetap menyala (GLD tetap aktif mendeteksi)", TABLE_CELL)],
    ]
    story.append(tbl(tanda_data, [4*cm, 11.5*cm]))
    story.append(sp(8))

    story.append(Paragraph("Langkah Penanganan Alarm", H2))
    alarm_steps = [
        "<b>JANGAN PANIK.</b> Tetap tenang dan ikuti prosedur ini.",
        "<b>Evaluasi area.</b> Cium udara sekitar untuk mendeteksi bau gas. Jika bau gas kuat, evakuasi area segera.",
        "<b>Jangan nyalakan/matikan perangkat listrik</b> di area tersebut — percikan dapat menyebabkan kebakaran.",
        "<b>Hubungi supervisor atau tim K3</b> sesuai prosedur darurat fasilitas.",
        "<b>Jangan matikan GLD</b> saat alarm aktif — GLD perlu terus memantau.",
        "<b>Setelah area aman</b>, tim teknis akan mengevaluasi kondisi dan mereset alarm jika kebocoran sudah tertangani.",
        "<b>GLD akan otomatis mematikan alarm</b> jika konsentrasi gas kembali normal.",
    ]
    for i, step in enumerate(alarm_steps, 1):
        story.append(numbered_step(i, step))
        story.append(sp(3))

    story.append(sp(8))
    story.append(info([
        "Alarm otomatis mati jika gas sudah tidak terdeteksi — tidak perlu mereset manual.",
        "Server akan menerima notifikasi alarm secara otomatis.",
        "Setiap kejadian alarm dicatat di server untuk audit/laporan.",
    ]))
    story.append(sp(8))

    story.append(Paragraph("Nomor Darurat", H2))
    darurat_data = [
        [Paragraph("Jabatan / Tim", TABLE_HDR), Paragraph("Nomor / Kontak", TABLE_HDR)],
        [Paragraph("Supervisor Area", TABLE_CELL),    Paragraph("— isi sesuai fasilitas —", SMALL)],
        [Paragraph("Tim K3 / HSE", TABLE_CELL),       Paragraph("— isi sesuai fasilitas —", SMALL)],
        [Paragraph("Teknisi GLD", TABLE_CELL),        Paragraph("— isi sesuai fasilitas —", SMALL)],
        [Paragraph("Pemadam Kebakaran", TABLE_CELL),  Paragraph("113", TABLE_CELL)],
    ]
    story.append(tbl(darurat_data, [5*cm, 10.5*cm]))
    story.append(PageBreak())
    return story

# ── Bab 7: Mengganti Mode ─────────────────────────────────────────────────────
def chapter7():
    story = [Paragraph("7. MENGGANTI MODE OPERASI", H1), hr()]
    story.append(Paragraph(
        "Penggantian mode biasanya dilakukan oleh teknisi. Jika operator perlu mengganti mode "
        "(misalnya mengembalikan ke inference setelah kalibrasi), ikuti salah satu cara berikut.",
        BODY_J
    ))
    story.append(sp(8))

    story.append(Paragraph("Cara A — Melalui Komputer (Serial Monitor)", H2))
    story.append(Paragraph(
        "Metode ini membutuhkan komputer dengan aplikasi terminal serial (contoh: PuTTY, Arduino IDE, atau aplikasi bawaan teknisi).",
        BODY
    ))
    serial_steps = [
        "Hubungkan GLD ke komputer menggunakan kabel USB.",
        "Buka aplikasi serial monitor dengan port <b>COM10</b> dan baudrate <b>115200</b>.",
        "Ketik perintah mode yang diinginkan, lalu tekan Enter:",
    ]
    for i, step in enumerate(serial_steps, 1):
        story.append(numbered_step(i, step))
        story.append(sp(2))

    story.append(sp(4))
    cmd_data = [
        [Paragraph("Perintah", TABLE_HDR), Paragraph("Fungsi", TABLE_HDR)],
        [Paragraph("SET_MODE inference", s("Normal", fontSize=9, textColor=DARK, fontName="Courier-Bold", leading=13)),
         Paragraph("Kembali ke mode operasi normal (deteksi gas)", TABLE_CELL)],
        [Paragraph("SET_MODE dataset", s("Normal", fontSize=9, textColor=DARK, fontName="Courier-Bold", leading=13)),
         Paragraph("Masuk ke mode pengambilan data (perlu WiFi)", TABLE_CELL)],
        [Paragraph("SET_MODE nulling", s("Normal", fontSize=9, textColor=DARK, fontName="Courier-Bold", leading=13)),
         Paragraph("Masuk ke mode kalibrasi", TABLE_CELL)],
    ]
    story.append(tbl(cmd_data, [5.5*cm, 10*cm]))
    story.append(sp(4))
    numbered_step(4, "GLD akan restart otomatis dan memulai mode baru.")
    story.append(numbered_step(4, "GLD akan restart otomatis dan memulai mode baru. Tunggu ±5 detik."))
    story.append(sp(8))

    story.append(Paragraph("Cara B — Melalui Jaringan (MQTT, saat mode dataset/nulling)", H2))
    story.append(Paragraph(
        "Saat GLD berada di mode dataset atau nulling dan terhubung ke WiFi, mode dapat diganti "
        "dari komputer yang terhubung ke jaringan yang sama oleh teknisi.",
        BODY
    ))
    story.append(sp(4))
    story.append(note([
        "Cara B membutuhkan alat khusus (MQTT client) dan pengetahuan jaringan.",
        "Jika tidak yakin, gunakan Cara A atau hubungi teknisi.",
    ]))
    story.append(PageBreak())
    return story

# ── Bab 8: Nulling (Kalibrasi) ────────────────────────────────────────────────
def chapter8():
    story = [Paragraph("8. PROSEDUR KALIBRASI (NULLING)", H1), hr()]
    story.append(Paragraph(
        "Kalibrasi (nulling) dilakukan untuk menyetel ulang baseline sensor GLD. "
        "Ini wajib dilakukan setelah pemasangan baru, penggantian sensor, atau jika data sensor "
        "terlihat tidak normal.",
        BODY_J
    ))
    story.append(sp(8))

    story.append(warn([
        "Kalibrasi HANYA boleh dilakukan saat area benar-benar bebas gas.",
        "GLD HARUS menggunakan power supply external (bukan baterai) saat kalibrasi.",
        "Proses kalibrasi berjalan otomatis dan tidak boleh diinterupsi.",
    ]))
    story.append(sp(8))

    story.append(Paragraph("Langkah Kalibrasi", H2))
    null_steps = [
        "Pastikan area bebas gas dan ventilasi baik.",
        "Pastikan GLD terhubung ke adaptor power supply (bukan baterai).",
        "Masuk ke mode nulling melalui Serial Monitor:\n  Ketik: <b>SET_MODE nulling</b>  lalu tekan Enter",
        "GLD akan restart otomatis dan memulai proses kalibrasi.",
        "Tunggu proses selesai. Proses berlangsung ±1–3 menit.",
        "Lihat hasil di Serial Monitor:",
    ]
    for i, step in enumerate(null_steps, 1):
        story.append(numbered_step(i, step))
        story.append(sp(2))

    story.append(sp(6))
    hasil_data = [
        [Paragraph("Hasil", TABLE_HDR), Paragraph("Arti", TABLE_HDR), Paragraph("Tindakan", TABLE_HDR)],
        [Paragraph("PASS", s("Normal", fontSize=9, textColor=GREEN, fontName="Helvetica-Bold", leading=13)),
         Paragraph("Kalibrasi berhasil penuh", TABLE_CELL),
         Paragraph("Lanjutkan ke mode inference", TABLE_CELL)],
        [Paragraph("PARTIAL", s("Normal", fontSize=9, textColor=YELLOW, fontName="Helvetica-Bold", leading=13)),
         Paragraph("Sebagian channel berhasil", TABLE_CELL),
         Paragraph("Hubungi teknisi untuk evaluasi", TABLE_CELL)],
        [Paragraph("FAIL", s("Normal", fontSize=9, textColor=RED, fontName="Helvetica-Bold", leading=13)),
         Paragraph("Kalibrasi gagal", TABLE_CELL),
         Paragraph("Hubungi teknisi — jangan gunakan untuk operasi", TABLE_CELL)],
    ]
    story.append(tbl(hasil_data, [2*cm, 7*cm, 6.5*cm]))
    story.append(sp(8))

    story.append(numbered_step(7, "Setelah kalibrasi selesai, kembali ke mode inference:\n  Ketik: <b>SET_MODE inference</b>  lalu tekan Enter"))
    story.append(PageBreak())
    return story

# ── Bab 9: Dataset ────────────────────────────────────────────────────────────
def chapter9():
    story = [Paragraph("9. PROSEDUR PENGAMBILAN DATA (DATASET)", H1), hr()]
    story.append(Paragraph(
        "Mode dataset digunakan oleh teknisi atau operator terlatih untuk mengumpulkan "
        "data pelatihan model AI. Prosedur ini tidak dilakukan dalam operasi harian normal.",
        BODY_J
    ))
    story.append(sp(8))

    story.append(Paragraph("Persyaratan", H2))
    syarat = [
        [Paragraph("Persyaratan", TABLE_HDR), Paragraph("Keterangan", TABLE_HDR)],
        [Paragraph("Kalibrasi valid", TABLE_CELL),        Paragraph("Profil nulling harus sudah ada sebelum dataset bisa dimulai", TABLE_CELL)],
        [Paragraph("Power supply external", TABLE_CELL),  Paragraph("Dataset tidak boleh dijalankan dengan baterai", TABLE_CELL)],
        [Paragraph("WiFi aktif", TABLE_CELL),             Paragraph("GLD harus terhubung ke jaringan WiFi: CHANGE_ME_WIFI_SSID", TABLE_CELL)],
        [Paragraph("Server aktif", TABLE_CELL),           Paragraph("Server Node-RED harus berjalan untuk menerima data", TABLE_CELL)],
    ]
    story.append(tbl(syarat, [4.5*cm, 11*cm]))
    story.append(sp(8))

    story.append(Paragraph("Langkah Pengambilan Data", H2))
    ds_steps = [
        "Masuk ke mode dataset:\n  Serial: <b>SET_MODE dataset</b>",
        "Tunggu GLD terhubung ke WiFi dan server (±15 detik setelah boot).",
        "Siapkan kondisi gas yang akan direkam (udara bersih, atau gas target sesuai instruksi).",
        "Mulai pengambilan data melalui komputer teknisi dengan perintah yang diberikan.",
        "Tunggu pengambilan data selesai (otomatis berhenti sesuai jumlah sampel).",
        "Verifikasi data tersimpan di server bersama teknisi.",
        "Setelah selesai, kembali ke mode inference:\n  Serial: <b>SET_MODE inference</b>",
    ]
    for i, step in enumerate(ds_steps, 1):
        story.append(numbered_step(i, step))
        story.append(sp(2))

    story.append(sp(8))
    story.append(note([
        "Pelabelan kondisi gas (label) sangat penting untuk kualitas model AI.",
        "Pastikan tidak ada kontaminasi gas lain saat pengambilan data.",
        "Setiap sesi dataset harus didokumentasikan: tanggal, kondisi, label, jumlah sampel.",
    ]))
    story.append(PageBreak())
    return story

# ── Bab 10: Monitoring dari Server ───────────────────────────────────────────
def chapter10():
    story = [Paragraph("10. MONITORING DARI KOMPUTER / SERVER", H1), hr()]
    story.append(Paragraph(
        "Server menerima dan menyimpan semua data dari GLD secara otomatis. "
        "Operator dapat memantau kondisi GLD melalui antarmuka server.",
        BODY_J
    ))
    story.append(sp(8))

    story.append(Paragraph("Data yang Diterima Server", H2))
    data_tbl = [
        [Paragraph("Data", TABLE_HDR), Paragraph("Frekuensi", TABLE_HDR), Paragraph("Keterangan", TABLE_HDR)],
        [Paragraph("Hasil deteksi gas", TABLE_CELL),   Paragraph("Setiap ±10 detik", TABLE_CELL),
         Paragraph("Jenis gas, tingkat keyakinan, status alarm", TABLE_CELL)],
        [Paragraph("Event alarm", TABLE_CELL),          Paragraph("Saat alarm aktif", TABLE_CELL),
         Paragraph("Notifikasi segera dikirim ke server", TABLE_CELL)],
        [Paragraph("Data dataset", TABLE_CELL),         Paragraph("Saat mode dataset", TABLE_CELL),
         Paragraph("Disimpan ke database untuk pelatihan model", TABLE_CELL)],
        [Paragraph("Hasil kalibrasi", TABLE_CELL),      Paragraph("Setelah nulling selesai", TABLE_CELL),
         Paragraph("Profil kalibrasi dan status", TABLE_CELL)],
    ]
    story.append(tbl(data_tbl, [3.5*cm, 3.5*cm, 8.5*cm]))
    story.append(sp(8))

    story.append(Paragraph("Koneksi Jaringan", H2))
    net_data = [
        [Paragraph("Parameter", TABLE_HDR), Paragraph("Nilai", TABLE_HDR)],
        [Paragraph("Alamat Server", TABLE_CELL),       Paragraph("CHANGE_ME_MQTT_HOST", s("Normal", fontSize=9, textColor=DARK, fontName="Courier-Bold", leading=13))],
        [Paragraph("Port MQTT", TABLE_CELL),           Paragraph("1884", s("Normal", fontSize=9, textColor=DARK, fontName="Courier-Bold", leading=13))],
        [Paragraph("Node-RED Dashboard", TABLE_CELL),  Paragraph("http://CHANGE_ME_MQTT_HOST:1880", s("Normal", fontSize=9, textColor=DARK, fontName="Courier-Bold", leading=13))],
    ]
    story.append(tbl(net_data, [5*cm, 10.5*cm]))
    story.append(sp(8))

    story.append(info([
        "Monitoring server aktif selama server menyala dan terhubung ke jaringan.",
        "Jika server tidak menerima data lebih dari beberapa menit, cek koneksi Gateway dan CH.",
        "Hubungi admin server jika butuh akses ke dashboard atau database.",
    ]))
    story.append(PageBreak())
    return story

# ── Bab 11: Troubleshooting ───────────────────────────────────────────────────
def chapter11():
    story = [Paragraph("11. TROUBLESHOOTING", H1), hr()]
    story.append(Paragraph(
        "Gunakan tabel berikut untuk mendiagnosis dan menangani masalah umum. "
        "Jika masalah tidak terselesaikan dengan langkah di bawah, hubungi teknisi.",
        BODY_J
    ))
    story.append(sp(8))

    ts_data = [
        [Paragraph("Gejala", TABLE_HDR),
         Paragraph("Kemungkinan Penyebab", TABLE_HDR),
         Paragraph("Langkah Penanganan Operator", TABLE_HDR)],

        [Paragraph("LED Status tidak menyala setelah boot", TABLE_CELL),
         Paragraph("GLD tidak di mode inference, atau gagal inisialisasi sensor", TABLE_CELL),
         Paragraph("Cek mode GLD. Jika mode sudah inference tapi LED tetap mati, restart dan tunggu 30 detik. Jika masih mati, hubungi teknisi.", TABLE_CELL)],

        [Paragraph("Alarm menyala padahal tidak ada bau gas", TABLE_CELL),
         Paragraph("Kalibrasi sensor sudah kadaluarsa atau ada kontaminan", TABLE_CELL),
         Paragraph("Catat waktu kejadian dan kondisi lingkungan. Laporkan ke teknisi untuk evaluasi kalibrasi ulang.", TABLE_CELL)],

        [Paragraph("GLD tidak mengirim data ke server (server tidak menerima data)", TABLE_CELL),
         Paragraph("CH/Gateway mati, antena lepas, atau GLD tidak di mode inference", TABLE_CELL),
         Paragraph("Periksa antena LoRa terpasang. Periksa LED CH dan Gateway menyala. Pastikan GLD di mode inference. Hubungi teknisi jika perlu.", TABLE_CELL)],

        [Paragraph("GLD tidak bisa masuk mode dataset (WiFi tidak connect)", TABLE_CELL),
         Paragraph("SSID WiFi salah, password berubah, atau WiFi router mati", TABLE_CELL),
         Paragraph("Pastikan WiFi 'CHANGE_ME_WIFI_SSID' aktif. Jika password berubah, hubungi teknisi untuk update konfigurasi.", TABLE_CELL)],

        [Paragraph("Mode berubah sendiri ke dataset/nulling", TABLE_CELL),
         Paragraph("Ada perintah yang tidak disengaja dari komputer atau server", TABLE_CELL),
         Paragraph("Kembalikan ke mode inference via Serial: ketik SET_MODE inference. Laporkan ke teknisi.", TABLE_CELL)],

        [Paragraph("Kalibrasi gagal (FAIL)", TABLE_CELL),
         Paragraph("Sensor rusak, wiring bermasalah, atau ada gas saat kalibrasi", TABLE_CELL),
         Paragraph("Pastikan area benar-benar bebas gas. Coba kalibrasi ulang sekali. Jika masih FAIL, hubungi teknisi.", TABLE_CELL)],

        [Paragraph("GLD tidak merespons perintah Serial", TABLE_CELL),
         Paragraph("Port COM salah, baudrate salah, atau koneksi USB longgar", TABLE_CELL),
         Paragraph("Periksa kabel USB. Pastikan port COM10 dan baudrate 115200. Coba cabut-pasang kabel USB.", TABLE_CELL)],
    ]
    story.append(tbl(ts_data, [3.5*cm, 4.5*cm, 7.5*cm]))
    story.append(sp(8))

    story.append(note([
        "Selalu catat gejala, waktu, dan kondisi sebelum menghubungi teknisi.",
        "Jangan membuka casing atau mengubah konfigurasi di luar prosedur ini.",
    ]))
    story.append(PageBreak())
    return story

# ── Bab 12: Checklist Harian ──────────────────────────────────────────────────
def chapter12():
    story = [Paragraph("12. CHECKLIST HARIAN OPERATOR", H1), hr()]
    story.append(Paragraph(
        "Lakukan pemeriksaan berikut setiap hari pada awal shift.",
        BODY
    ))
    story.append(sp(8))

    checklist = [
        [Paragraph("No.", TABLE_HDR), Paragraph("Item Pemeriksaan", TABLE_HDR),
         Paragraph("Status", TABLE_HDR), Paragraph("Catatan", TABLE_HDR)],
        [Paragraph("1", TABLE_CELL_C),
         Paragraph("LED Status GLD menyala (mode inference aktif)", TABLE_CELL),
         Paragraph("□ Ya  □ Tidak", TABLE_CELL_C), Paragraph("", TABLE_CELL)],
        [Paragraph("2", TABLE_CELL_C),
         Paragraph("Lampu Alarm mati (tidak ada deteksi gas)", TABLE_CELL),
         Paragraph("□ Ya  □ Tidak", TABLE_CELL_C), Paragraph("", TABLE_CELL)],
        [Paragraph("3", TABLE_CELL_C),
         Paragraph("Buzzer mati", TABLE_CELL),
         Paragraph("□ Ya  □ Tidak", TABLE_CELL_C), Paragraph("", TABLE_CELL)],
        [Paragraph("4", TABLE_CELL_C),
         Paragraph("Antena LoRa GLD terpasang dan tidak bengkok", TABLE_CELL),
         Paragraph("□ Ya  □ Tidak", TABLE_CELL_C), Paragraph("", TABLE_CELL)],
        [Paragraph("5", TABLE_CELL_C),
         Paragraph("CH (Cluster Head) menyala dan aktif", TABLE_CELL),
         Paragraph("□ Ya  □ Tidak", TABLE_CELL_C), Paragraph("", TABLE_CELL)],
        [Paragraph("6", TABLE_CELL_C),
         Paragraph("Gateway menyala dan terhubung ke WiFi", TABLE_CELL),
         Paragraph("□ Ya  □ Tidak", TABLE_CELL_C), Paragraph("", TABLE_CELL)],
        [Paragraph("7", TABLE_CELL_C),
         Paragraph("Server menerima data dari GLD (cek dashboard)", TABLE_CELL),
         Paragraph("□ Ya  □ Tidak", TABLE_CELL_C), Paragraph("", TABLE_CELL)],
        [Paragraph("8", TABLE_CELL_C),
         Paragraph("Tidak ada alarm aktif yang belum ditangani", TABLE_CELL),
         Paragraph("□ Ya  □ Tidak", TABLE_CELL_C), Paragraph("", TABLE_CELL)],
        [Paragraph("9", TABLE_CELL_C),
         Paragraph("Lubang sensor bersih dari debu/kotoran (periksa mingguan)", TABLE_CELL),
         Paragraph("□ Ya  □ Tidak", TABLE_CELL_C), Paragraph("", TABLE_CELL)],
        [Paragraph("10", TABLE_CELL_C),
         Paragraph("Tidak ada kabel/power yang longgar", TABLE_CELL),
         Paragraph("□ Ya  □ Tidak", TABLE_CELL_C), Paragraph("", TABLE_CELL)],
    ]
    story.append(tbl(checklist, [1*cm, 7*cm, 3.5*cm, 4*cm]))
    story.append(sp(10))

    # Tanda tangan area
    ttd = Table([
        [Paragraph("Operator:", BODY), Paragraph("Tanggal:", BODY), Paragraph("Shift:", BODY)],
        [Paragraph(" ", BODY), Paragraph(" ", BODY), Paragraph(" ", BODY)],
        [Paragraph("_" * 25, SMALL), Paragraph("_" * 20, SMALL), Paragraph("□ Pagi  □ Siang  □ Malam", SMALL)],
    ], colWidths=[5.5*cm, 5.5*cm, 4.5*cm])
    ttd.setStyle(TableStyle([
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("ALIGN",         (0,0), (-1,-1), "LEFT"),
    ]))
    story.append(ttd)
    story.append(sp(8))

    story.append(note([
        "Simpan checklist yang sudah diisi sebagai dokumen K3.",
        "Jika ada item yang tidak normal, catat dan laporkan ke teknisi atau supervisor.",
    ]))

    return story

# ── Main ──────────────────────────────────────────────────────────────────────
def build_pdf():
    doc = SimpleDocTemplate(
        OUTPUT_PATH,
        pagesize=A4,
        leftMargin=1.5*cm,
        rightMargin=1.5*cm,
        topMargin=2.2*cm,
        bottomMargin=1.8*cm,
        title="Manual Operasi GLD",
        author="Pertamina GLD",
        subject="Panduan Operator Gas Leak Detector",
    )

    story = []
    story += cover_page()
    story += table_of_contents()
    story += chapter1()
    story += chapter2()
    story += chapter3()
    story += chapter4()
    story += chapter5()
    story += chapter6()
    story += chapter7()
    story += chapter8()
    story += chapter9()
    story += chapter10()
    story += chapter11()
    story += chapter12()

    doc.build(story, onFirstPage=draw_page_decorations, onLaterPages=draw_page_decorations)
    print(f"PDF berhasil dibuat: {OUTPUT_PATH}")

if __name__ == "__main__":
    build_pdf()
