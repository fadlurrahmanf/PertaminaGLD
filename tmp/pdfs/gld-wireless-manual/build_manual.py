"""Illustrated Indonesian GLD operator manual from actual captured screenshots.

Preparation/import/--validate-only never writes a PDF. The coordinator must run
the PDF skill's artifact marker immediately before the first authoring run.
Direct UI screenshots and explicitly labelled recorded-actual snapshot viewers
are distinguished. Images remain unedited: ReportLab places the raster and adds vector
rectangles/circles. A crop only clips its viewing window; it is not redaction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DEFAULT_OUTPUT = ROOT / "output/pdf/Manual-GLD-Dataset-Wireless.pdf"
WIDTH, HEIGHT = landscape(A4)
MARGIN = 29
NAVY = colors.HexColor("#15334A")
TEAL = colors.HexColor("#007F83")
ORANGE = colors.HexColor("#E57628")
INK = colors.HexColor("#263D4A")
MUTED = colors.HexColor("#596E7B")
PAPER = colors.HexColor("#F3F6F8")
LINE = colors.HexColor("#D7E1E7")
PALE = colors.HexColor("#E7F3F3")
AMBER = colors.HexColor("#FFF2DF")
RECORDED_CAPTION = "Tampilan ulang status yang direkam saat uji GLD asli; tidak mengendalikan perangkat."

PAGES = {
    "overview": dict(title="Satu sesi, satu file CSV", subtitle="Persiapan sebelum merekam melalui hotspot GLD"),
    "hub": dict(title="1. Masuk melalui Operator Hub", subtitle="Buka console GLD untuk pemantauan Dataset Wireless", steps=[
        ("Buka Expert Console", "Pada halaman GLD di Operator Hub, klik Expert Console. Buka area Dataset Wireless pada console GLD."),
    ]),
    "setup": dict(title="2. Sambungkan laptop dan atur sesi", subtitle="Gunakan hotspot GLD dan mode Buffer 5 menit", steps=[
        ("Pilih mode buffer", "Pilih Buffer 5 menit - tahap 2. Pilihan Langsung - tahap 1 tidak menyediakan pemulihan lima menit."),
        ("Masukkan password hotspot", "Gunakan password yang diberikan untuk perangkat ini. Password tidak dicantumkan dalam panduan."),
        ("Beri label sesi", "Isi kondisi pengujian, misalnya udara_bersih. Label membedakan sesi pada CSV."),
        ("Connect GLD", "Pastikan laptop sudah tersambung ke GLD-DATASET-1002, lalu klik Connect GLD."),
    ]),
    "ready": dict(title="3. Pastikan GLD siap, lalu Start", subtitle="Start Wireless baru dapat dipakai setelah koneksi dan kesiapan GLD dikonfirmasi", steps=[
        ("Periksa identitas dan kesiapan", "Pastikan perangkat yang tampil adalah GLD 1002 dan statusnya siap. Jangan Start bila muncul not ready atau error."),
        ("Start Wireless", "Klik Start Wireless satu kali. Tunggu status recording dan hitungan sampel mulai bertambah."),
    ]),
    "recording": dict(title="Rekam dan pantau delapan sensor", subtitle="CSV ditulis oleh aplikasi di laptop selama sesi berlangsung", steps=[
        ("Mulai satu sesi", "Klik Start Wireless satu kali bila sesi belum dimulai. Setelah berjalan, gunakan sesi yang sama sampai Stop."),
        ("Periksa recording", "Pastikan hitungan sampel tersimpan bertambah. Targetnya satu pembacaan lengkap delapan sensor setiap 500 ms."),
        ("Amati grafik delapan kanal", "Grafik dan tabel menampilkan MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6, serta MQ2."),
        ("Catat lokasi CSV", "Nama dan lokasi file ditampilkan di bawah kontrol. Download CSV nanti mengambil salinan file sesi ini."),
    ]),
    "recovering": dict(title="Ketika Wi-Fi terputus", subtitle="GLD tetap mengambil data selama tetap menyala dan batas penyimpanan belum tercapai", steps=[
        ("Biarkan GLD menyala", "Pertahankan catu 24 V. Jangan me-restart GLD; rekaman tertunda disimpan dalam RAM."),
        ("Kenali recovering", "Aplikasi menunggu koneksi kembali. Biarkan proses Operator Hub di laptop tetap berjalan."),
        ("Sambungkan kembali hotspot", "Dari Wi-Fi laptop, pilih GLD-DATASET-1002 kembali. Pemulihan sesi berjalan otomatis setelah koneksi tersedia."),
        ("Jangan membuat sesi baru", "Jangan menekan Start lagi atau memilih mode lain. Gunakan sesi dan CSV yang sedang dipulihkan."),
    ]),
    "replaying": dict(title="Tunggu data tertunda menyusul", subtitle="replaying beralih menjadi recording setelah rekaman tertunda tertulis ke CSV yang sama", steps=[
        ("Kenali replaying", "Hitungan CSV dapat naik lebih cepat saat data tertunda sedang disalin ke laptop."),
        ("Tunggu recording kembali", "Saat data tertunda sudah menyusul, status kembali recording dan pembacaan terbaru berlanjut."),
        ("Periksa sesi dan file", "Label serta file CSV tetap sama. Waktu yang tercatat adalah waktu pembacaan GLD, bukan waktu pemulihan."),
    ]),
    "complete": dict(title="Akhiri sesi dan unduh CSV", subtitle="Tunggu konfirmasi akhir sebelum menyatakan rekaman lengkap", steps=[
        ("Klik Stop", "Ketika selesai, klik Stop satu kali. Bila koneksi sedang pulih, Stop dapat menunggu konfirmasi GLD."),
        ("Periksa complete", "Tunggu status complete / sesi lengkap. Status incomplete berarti sesi tidak boleh dinyatakan lengkap."),
        ("Download CSV", "Klik Download CSV, simpan file, lalu periksa label dan delapan kolom tegangan sensor."),
    ]),
    "incomplete": dict(title="Jika batas lima menit terlewati", subtitle="Sampling berhenti; rekaman yang masih ditahan tetap dapat dipulihkan selama GLD menyala", steps=[
        ("Kenali incomplete", "Alasan retention_limit berarti batas penyimpanan saat putus koneksi terlewati. Sesi tetap ditandai tidak lengkap."),
        ("Pertahankan catu GLD", "Biarkan GLD menyala. Rekaman tertunda tetap dapat disalin ke CSV; mematikan atau reboot GLD menghapus RAM."),
        ("Unduh dan catat batas sesi", "Download CSV hasil pemulihan. Incomplete tidak berarti seluruh data hilang, tetapi tidak ada pengukuran setelah sampling dihentikan."),
    ]),
    "troubleshoot": dict(title="Jika sesi belum lengkap", subtitle="Simpan CSV yang sudah ada dan gunakan status aplikasi untuk menentukan tindakan berikutnya"),
}


def clean(value):
    text = str(value)
    for char in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212"):
        text = text.replace(char, "-")
    return text


def setup_fonts():
    options = [("GLD", "C:/Windows/Fonts/arial.ttf"),
               ("GLDBold", "C:/Windows/Fonts/arialbd.ttf"),
               ("GLDItalic", "C:/Windows/Fonts/ariali.ttf")]
    for name, filename in options:
        if not Path(filename).is_file():
            raise RuntimeError("Arial fonts are unavailable; resolve fonts before authoring")
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, filename))
    pdfmetrics.registerFontFamily("GLD", normal="GLD", bold="GLDBold", italic="GLDItalic", boldItalic="GLDBold")


def paragraph(text, width, size=10, leading=None, color=INK, bold=False):
    style = ParagraphStyle("manual", fontName="GLDBold" if bold else "GLD", fontSize=size,
        leading=leading or size * 1.35, textColor=color, alignment=TA_LEFT,
        spaceBefore=0, spaceAfter=0, allowWidows=0, allowOrphans=0)
    return Paragraph(escape(clean(text)).replace("\n", "<br/>"), style)


def text(c, content, x, top, width, size=10, color=INK, bold=False, max_height=None):
    item = paragraph(content, width, size=size, color=color, bold=bold)
    _, height = item.wrap(width, HEIGHT)
    if max_height is not None and height > max_height + .1:
        raise ValueError(f"Text exceeds allocated height ({height:.1f}>{max_height}): {clean(content)[:90]}")
    item.drawOn(c, x, top - height)
    return height


def rounded(c, x, y, width, height, fill, stroke=None, radius=8):
    c.setFillColor(fill)
    c.setStrokeColor(stroke or fill)
    c.roundRect(x, y, width, height, radius, fill=1, stroke=int(stroke is not None))


def device_defaults(spec):
    return {"device_id": "1002", "ssid": "GLD-DATASET-1002", "model": "Model 1", "firmware": "0.8.36",
            **spec.get("device", {})}


def definitions(spec):
    screenshots = spec.get("screenshots", spec.get("images", {}))
    default = ["overview", "hub", "setup"]
    if "ready" in screenshots:
        default.append("ready")
    default += ["recording", "recovering", "replaying", "complete"]
    if "incomplete" in screenshots:
        default.append("incomplete")
    default.append("troubleshoot")
    result = []
    for page in spec.get("pages", default):
        entry = {"key": page} if isinstance(page, str) else dict(page)
        key = entry["key"]
        if key not in PAGES:
            raise ValueError(f"Unknown page key: {key}")
        result.append({**PAGES[key], **entry})
    if not 6 <= len(result) <= 10:
        raise ValueError("The manual requires 6..10 pages")
    return result


def load_spec(path):
    spec_path = path.resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        raise ValueError("Spec must be a JSON object")
    screenshots = spec.get("screenshots", spec.get("images", {}))
    if not isinstance(screenshots, dict):
        raise ValueError("screenshots must be a mapping")
    pages = definitions(spec)
    normalized = {}
    for page in pages:
        key = page.get("image", page["key"])
        if page["key"] in {"overview", "troubleshoot"} and key not in screenshots:
            continue
        entry = screenshots.get(key)
        if not isinstance(entry, dict):
            raise ValueError(f"Actual screenshot is missing: {key}")
        kind = entry.get("kind", "actual")
        if kind not in {"actual", "recorded_actual"}:
            raise ValueError(f"UI screenshots must be actual or explicitly recorded_actual: {key}")
        if entry.get("privacy_checked", spec.get("privacy_checked")) is not True:
            raise ValueError(f"Source screenshot privacy must be checked before embedding: {key}")
        entry = dict(entry)
        entry["kind"] = kind
        if kind == "recorded_actual":
            banner = clean(entry.get("archive_banner", ""))
            if (entry.get("archive_banner_visible") is not True or
                    "TAMPILAN ULANG LOG UJI GLD ASLI" not in banner.upper() or
                    "bukan koneksi langsung" not in banner.lower()):
                raise ValueError(f"Recorded-actual viewer must visibly identify its archive status: {key}")
            original = entry.get("recorded_source", entry.get("source_evidence"))
            if not isinstance(original, str) or not original.strip():
                raise ValueError(f"Recorded-actual source evidence must be identified: {key}")
            original = Path(original)
            original = original if original.is_absolute() else spec_path.parent / original
            if not original.is_file():
                raise ValueError(f"Recorded-actual source evidence file is missing: {key}")
            entry["recorded_source"] = str(original.resolve())
            caption = clean(entry.get("caption", RECORDED_CAPTION))
            if RECORDED_CAPTION not in caption:
                raise ValueError(f"Recorded-actual caption must clearly distinguish recorded status from live control: {key}")
            entry["caption"] = caption
        source = Path(entry["path"])
        source = source if source.is_absolute() else spec_path.parent / source
        source = source.resolve()
        if not source.is_file():
            raise ValueError(f"Screenshot file does not exist: {source}")
        with Image.open(source) as image:
            width, height = image.size
            image.verify()
        crop = entry.get("crop", dict(x=0, y=0, w=width, h=height))
        crop = {name: float(crop[name]) for name in ("x", "y", "w", "h")}
        if (crop["w"] <= 0 or crop["h"] <= 0 or crop["x"] < 0 or crop["y"] < 0 or
                crop["x"] + crop["w"] > width + .1 or crop["y"] + crop["h"] > height + .1):
            raise ValueError(f"Invalid source crop: {key}")
        annotations = entry.get("annotations", entry.get("boxes", []))
        if not 1 <= len(annotations) <= 4:
            raise ValueError(f"Use 1..4 numbered callouts per UI screenshot: {key}")
        numbers = set()
        steps = page.get("steps", [])
        resolved = []
        for raw in annotations:
            ann = dict(raw)
            number = ann.get("n")
            if type(number) is not int or not 1 <= number <= 4 or number in numbers:
                raise ValueError(f"Invalid/duplicate annotation number: {key}")
            numbers.add(number)
            for field in ("x", "y", "w", "h"):
                ann[field] = float(ann[field])
            if (ann["w"] <= 0 or ann["h"] <= 0 or ann["x"] < crop["x"] or ann["y"] < crop["y"] or
                    ann["x"] + ann["w"] > crop["x"] + crop["w"] + .5 or
                    ann["y"] + ann["h"] > crop["y"] + crop["h"] + .5):
                raise ValueError(f"Annotation lies outside its source viewport: {key}/{number}")
            fallback = steps[number - 1] if number <= len(steps) else ("Kontrol yang ditunjuk", "Ikuti petunjuk pada tampilan aplikasi.")
            ann["title"] = clean(ann.get("title", fallback[0]))
            ann["body"] = clean(ann.get("body", fallback[1]))
            resolved.append(ann)
        normalized[key] = {**entry, "path": source, "width": width, "height": height,
                           "crop": crop, "annotations": sorted(resolved, key=lambda item: item["n"])}
    results = spec.get("test_results")
    if results is not None and (not isinstance(results, dict) or results.get("kind") != "actual" or results.get("verified") is not True):
        raise ValueError("test_results must explicitly identify verified actual device evidence")
    spec["_pages"], spec["_screenshots"], spec["_path"] = pages, normalized, spec_path
    return spec


def validate_layout(spec):
    """Measure actual text blocks without constructing a PDF canvas."""
    def check(content, width, size, limit, label, bold=False):
        _, height = paragraph(content, width, size=size, bold=bold).wrap(width, HEIGHT)
        if height > limit + .1:
            raise ValueError(f"Shorten {label}; measured {height:.1f} pt exceeds {limit:.1f} pt")
        return height
    for page in spec["_pages"]:
        check(page["title"], WIDTH - 2 * MARGIN, 22, 31, page["key"] + " title", bold=True)
        check(page["subtitle"], WIDTH - 2 * MARGIN, 10, 28, page["key"] + " subtitle")
        entry = spec["_screenshots"].get(page.get("image", page["key"]))
        if not entry:
            continue
        count = len(entry["annotations"])
        width = (WIDTH - 2 * MARGIN - 10 * (count - 1)) / count
        for ann in entry["annotations"]:
            title_height = check(ann["title"], width - 39, 9.4 if count >= 3 else 10.4,
                                 28, f"{page['key']}/{ann['n']} callout title", bold=True)
            body_top = 132 - max(34, title_height + 14)
            check(ann["body"], width - 22, 9 if count >= 3 else 10,
                  body_top - 48, f"{page['key']}/{ann['n']} callout body")
        check(entry.get("caption", "Screenshot aktual perangkat/aplikasi. Kotak dan angka merupakan penanda panduan."),
              WIDTH - 2 * MARGIN - 6, 8.2, 16, page["key"] + " caption")


def header(c, page, number, total, spec, kind):
    c.setFillColor(PAPER)
    c.rect(0, 0, WIDTH, HEIGHT, fill=1, stroke=0)
    c.setFillColor(TEAL)
    c.rect(0, HEIGHT - 8, WIDTH, 8, fill=1, stroke=0)
    text(c, "PANDUAN OPERATOR  /  GLD DATASET WIRELESS", MARGIN, HEIGHT - 22, WIDTH - 2 * MARGIN, 9, TEAL, True)
    if kind == "recorded_actual":
        c.setFont("GLDBold", 8.3)
        c.setFillColor(ORANGE)
        c.drawRightString(WIDTH - MARGIN, HEIGHT - 31, "TAMPILAN ULANG LOG UJI ASLI")
    text(c, page["title"], MARGIN, HEIGHT - 43, WIDTH - 2 * MARGIN, 22, NAVY, True, 31)
    text(c, page["subtitle"], MARGIN, HEIGHT - 76, WIDTH - 2 * MARGIN, 10, MUTED, False, 28)
    c.setStrokeColor(LINE)
    c.line(MARGIN, 30, WIDTH - MARGIN, 30)
    device = device_defaults(spec)
    text(c, f"GLD1 / {device['model']} / ID {device['device_id']}  |  {spec.get('date', '2 November 2026')}", MARGIN, 21, WIDTH - 130, 8, MUTED)
    c.setFont("GLDBold", 8)
    c.setFillColor(MUTED)
    c.drawRightString(WIDTH - MARGIN, 12, f"{number:02d} / {total:02d}")


def number(c, value, x, y, radius=9):
    c.setFillColor(ORANGE)
    c.circle(x, y, radius, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("GLDBold", 9)
    c.drawCentredString(x, y - 3.2, str(value))


def screenshot(c, entry, x, y, width, height):
    crop = entry["crop"]
    scale = min(width / crop["w"], height / crop["h"])
    iw, ih = crop["w"] * scale, crop["h"] * scale
    left, bottom = x + (width - iw) / 2, y + (height - ih) / 2
    rounded(c, x - 5, y - 5, width + 10, height + 10, colors.white, LINE, radius=7)
    c.saveState()
    clip = c.beginPath()
    clip.rect(left, bottom, iw, ih)
    c.clipPath(clip, stroke=0, fill=0)
    c.drawImage(str(entry["path"]), left - crop["x"] * scale,
                bottom - (entry["height"] - crop["y"] - crop["h"]) * scale,
                width=entry["width"] * scale, height=entry["height"] * scale, mask="auto")
    c.restoreState()
    boxes = []
    for ann in entry["annotations"]:
        bx = left + (ann["x"] - crop["x"]) * scale
        by = bottom + (crop["h"] - (ann["y"] - crop["y"]) - ann["h"]) * scale
        bw, bh = ann["w"] * scale, ann["h"] * scale
        c.setLineWidth(1.9)
        c.setStrokeColor(ORANGE)
        c.roundRect(bx, by, bw, bh, min(4, bh / 5), fill=0, stroke=1)
        nx = max(x + 9, min(x + width - 9, bx - 4))
        ny = max(y + 9, min(y + height - 9, by + bh + 4))
        number(c, ann["n"], nx, ny, 8)
        boxes.append(dict(n=ann["n"], x=round(bx, 2), y=round(by, 2), w=round(bw, 2), h=round(bh, 2)))
    return boxes


def step_cards(c, annotations, top=132):
    count = len(annotations)
    gap = 10
    width = (WIDTH - 2 * MARGIN - gap * (count - 1)) / count
    for index, ann in enumerate(annotations):
        x = MARGIN + index * (width + gap)
        rounded(c, x, 40, width, top - 40, colors.white, LINE, 6)
        number(c, ann["n"], x + 15, top - 16, 8)
        title_width = width - 39
        title_size = 9.4 if count >= 3 else 10.4
        title_height = text(c, ann["title"], x + 29, top - 8, title_width, title_size, NAVY, True, 28)
        body_top = top - max(34, title_height + 14)
        text(c, ann["body"], x + 11, body_top, width - 22, 9 if count >= 3 else 10, INK, False, body_top - 48)


def photo_page(c, page, entry, spec):
    frame = dict(x=MARGIN + 4, y=158, w=WIDTH - 2 * MARGIN - 8, h=HEIGHT - 258)
    banner_view = None
    if entry["kind"] == "recorded_actual":
        # Keep the original archive disclosure visible while magnifying the
        # relevant controls. Both windows show the same unedited source raster.
        banner_view = {**entry, "crop": dict(x=0, y=0, w=entry["width"], h=68), "annotations": []}
        screenshot(c, banner_view, frame["x"], frame["y"] + frame["h"] - 44, frame["w"], 44)
        frame["h"] -= 54
    boxes = screenshot(c, entry, frame["x"], frame["y"], frame["w"], frame["h"])
    caption = entry.get("caption", "Screenshot aktual perangkat/aplikasi. Kotak dan angka merupakan penanda panduan.")
    text(c, caption, MARGIN + 3, 149, WIDTH - 2 * MARGIN - 6, 8.2, MUTED, False, 16)
    step_cards(c, entry["annotations"])
    return dict(kind="recorded actual snapshot screenshot" if entry["kind"] == "recorded_actual" else "actual screenshot",
                recordedSource=entry.get("recorded_source"), archiveBanner=entry.get("archive_banner"),
                caption=caption, image=str(entry["path"]),
                imageSha256=hashlib.sha256(entry["path"].read_bytes()).hexdigest(), pdfBoxes=boxes,
                originalRasterUnedited=True, sourceCrop=entry["crop"],
                archiveBannerCrop=banner_view["crop"] if banner_view else None)


def card(c, x, top, width, title, body, fill=colors.white, height=108):
    rounded(c, x, top - height, width, height, fill, LINE, 8)
    text(c, title, x + 13, top - 12, width - 26, 12, NAVY, True, 34)
    text(c, body, x + 13, top - 47, width - 26, 10, INK, False, height - 58)


def overview(c, spec):
    device = device_defaults(spec)
    top, box_w, box_h = 462, 173, 86
    labels = [("GLD 24 V", "Delapan sensor dibaca setiap 500 ms."),
              ("Hotspot GLD", device["ssid"] + ". Tanpa Internet; pilih tetap tersambung."),
              ("Operator Hub", "Proses aplikasi di laptop harus tetap berjalan."),
              ("Grafik + CSV", "Satu sesi diteruskan ke file CSV yang sama.")]
    gap = (WIDTH - 2 * MARGIN - 4 * box_w) / 3
    for index, (title, body) in enumerate(labels):
        x = MARGIN + index * (box_w + gap)
        card(c, x, top, box_w, title, body, PALE, box_h)
        if index < 3:
            ax = x + box_w + 4
            ay = top - box_h / 2
            c.setStrokeColor(TEAL)
            c.setLineWidth(1.6)
            c.line(ax, ay, ax + gap - 8, ay)
            c.line(ax + gap - 13, ay + 4, ax + gap - 8, ay)
            c.line(ax + gap - 13, ay - 4, ax + gap - 8, ay)
    text(c, "Ilustrasi alur operasi - bukan screenshot atau bukti pengukuran.", MARGIN, 365, WIDTH - 2 * MARGIN, 8.5, MUTED)
    col = (WIDTH - 2 * MARGIN - 14) / 2
    card(c, MARGIN, 340, col, "Yang harus siap", "GLD1 memakai catu eksternal 24 V, firmware Buffer 5 menit, dan profil kalibrasi yang sudah valid. Laptop tersambung ke hotspot GLD.", height=104)
    card(c, MARGIN + col + 14, 340, col, "Batas lima menit", "Saat koneksi putus, GLD menyimpan data sementara di RAM. Pada batas 300 detik sampling dihentikan dan sesi ditandai incomplete; data yang masih tersedia tetap dapat diambil selama GLD menyala.", AMBER, height=104)
    rounded(c, MARGIN, 135, WIDTH - 2 * MARGIN, 89, AMBER, LINE)
    text(c, "Tab browser boleh ditutup; proses Operator Hub harus tetap berjalan", MARGIN + 13, 212, WIDTH - 2 * MARGIN - 26, 11, NAVY, True, 17)
    text(c, "Jika proses Operator Hub berhenti atau laptop direstart, penulisan CSV berhenti dan sesi tidak dipulihkan otomatis setelah aplikasi dibuka lagi. RAM GLD tidak bertahan bila GLD mati atau reboot.", MARGIN + 13, 187, WIDTH - 2 * MARGIN - 26, 10, INK, False, 45)
    text(c, f"Perangkat panduan: GLD1 / {device['model']} / ID {device['device_id']} / firmware {device['firmware']}", MARGIN, 119, WIDTH - 2 * MARGIN, 9.5, TEAL, True)
    results = spec.get("test_results")
    if results:
        cases = results.get("cases", [])
        if cases:
            if len(cases) > 2:
                raise ValueError("Use at most two actual test-case summaries on the overview")
            lines = []
            for case in cases:
                outcome = "sesi lengkap" if case.get("complete") else "incomplete / " + str(case.get("reason", "lihat laporan"))
                lines.append(f"Putus {case['outage_seconds']} detik: {case['total_rows']} sampel, "
                             f"{case['replayed_rows']} dipulihkan, {outcome}.")
            text(c, "Uji aktual Model 1 - " + "\n".join(lines), MARGIN, 94, WIDTH - 2 * MARGIN, 8.7, INK, False, 29)
        else:
            metrics = []
            for key, label in (("total_rows", "sampel tersimpan"), ("replayed_rows", "sampel dipulihkan"),
                               ("missing_rows", "sampel hilang"), ("outage_seconds", "detik putus koneksi")):
                if key in results:
                    metrics.append(f"{results[key]} {label}")
            summary = "  |  ".join(metrics) or "Hasil uji aktual dicatat pada laporan sesi."
            text(c, "Uji perangkat aktual terverifikasi: " + summary, MARGIN, 94, WIDTH - 2 * MARGIN, 9.1, INK, False, 29)
        if results.get("csv_match") is True or cases and all(case.get("csv_match") is True for case in cases):
            text(c, "CSV unduhan cocok dengan CSV yang disimpan aplikasi pada pengujian tersebut.", MARGIN, 65, WIDTH - 2 * MARGIN, 8.8, MUTED, False, 17)
    else:
        text(c, "Panduan operasi ini tidak menggantikan pemeriksaan status perangkat dan kelengkapan CSV sesi Anda.", MARGIN, 90, WIDTH - 2 * MARGIN, 9.2, MUTED)
    text(c, "Bukti perangkat pada panduan ini: Model 1. Model 2/3 telah dibangun, belum diverifikasi pada perangkat dalam uji ini.",
         MARGIN, 44, WIDTH - 2 * MARGIN, 7.8, MUTED, False, 12)
    return dict(kind="illustrative operating diagram", actualResultsIncluded=bool(results))


def troubleshoot(c, spec):
    col = (WIDTH - 2 * MARGIN - 14) / 2
    card(c, MARGIN, 466, col, "Tidak dapat Connect GLD", "Periksa GLD tetap mendapat 24 V. Pilih hotspot yang benar pada Wi-Fi laptop dan pastikan koneksi jaringan sudah siap. Gunakan password perangkat yang benar.", height=112)
    card(c, MARGIN + col + 14, 466, col, "Status not ready atau error", "Jangan membuat sesi uji baru. Minta teknisi memeriksa kesiapan delapan sensor dan profil kalibrasi. Halaman pemantauan tidak menggantikan prosedur kalibrasi.", height=112)
    card(c, MARGIN, 340, col, "recovering terlalu lama / batas terlewati", "Sambungkan kembali laptop ke hotspot. Setelah 300 detik tanpa kemajuan, GLD berhenti sampling dan sesi incomplete. Biarkan GLD menyala agar data yang masih ditahan dapat diambil.", AMBER, height=116)
    card(c, MARGIN + col + 14, 340, col, "GLD mati/reboot atau aplikasi PC berhenti", "Simpan CSV yang sudah ada. Jangan menganggap sesi lengkap atau melanjutkan dengan Start baru sebagai pemulihan file lama. RAM GLD dan pemulihan sesi tidak bertahan setelah reboot.", AMBER, height=116)
    rounded(c, MARGIN, 118, WIDTH - 2 * MARGIN, 91, colors.white, LINE)
    text(c, "Catatan administrator - pemasangan firmware", MARGIN + 13, 198, WIDTH - 2 * MARGIN - 26, 11, NAVY, True, 20)
    text(c, "USB/COM digunakan saat memasang firmware; perekaman rutin pada panduan ini memakai Wi-Fi. Untuk paket Hotspot/Buffer pada GLD yang profil kalibrasinya sudah valid, upload dilakukan dengan Reset NVS OFF. Pemasangan atau penggantian firmware ditangani administrator, bukan langkah rutin setiap sesi.", MARGIN + 13, 170, WIDTH - 2 * MARGIN - 26, 9.7, INK, False, 48)
    text(c, "Halaman ini merupakan panduan gejala (ilustratif), bukan screenshot kejadian error pada pengujian perangkat.", MARGIN, 95, WIDTH - 2 * MARGIN, 9, MUTED, False, 28)
    text(c, "Jika tertulis incomplete: simpan file, catat gejala, dan jangan menyatakan seluruh pengukuran telah tersimpan.", MARGIN, 65, WIDTH - 2 * MARGIN, 9.2, TEAL, True, 18)
    return dict(kind="illustrative troubleshooting guidance")


def build(spec, output):
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output), pagesize=(WIDTH, HEIGHT), pageCompression=1)
    c.setTitle("Panduan Operator - GLD Dataset Wireless")
    c.setAuthor("Pertamina GLD / Operator Hub")
    c.setSubject("Panduan bergambar penggunaan Dataset Wireless dengan buffer lima menit")
    report = dict(output=str(output), pageSize="A4 landscape", pages=[], sourceSpec=str(spec["_path"]))
    pages = spec["_pages"]
    for index, page in enumerate(pages, 1):
        image_key = page.get("image", page["key"])
        entry = spec["_screenshots"].get(image_key)
        header(c, page, index, len(pages), spec, entry["kind"] if entry else "illustrative")
        if entry:
            detail = photo_page(c, page, entry, spec)
        elif page["key"] == "overview":
            detail = overview(c, spec)
        elif page["key"] == "troubleshoot":
            detail = troubleshoot(c, spec)
        else:
            raise ValueError("A UI page cannot silently substitute an illustrative screenshot")
        report["pages"].append(dict(number=index, key=page["key"], title=page["title"], **detail))
        c.showPage()
    c.save()
    report["pdfSha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    report["privacy"] = "Input screenshots explicitly checked; overlays do not redact raster contents"
    (HERE / "layout-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--validate-only", action="store_true", help="Read/validate inputs only; no PDF or report is written")
    args = parser.parse_args()
    setup_fonts()
    spec = load_spec(args.spec)
    validate_layout(spec)
    if args.validate_only:
        print(json.dumps(dict(valid=True, pages=len(spec["_pages"]), actualScreenshots=len(spec["_screenshots"]), pdfWritten=False)))
        return
    report = build(spec, args.output)
    print(json.dumps(dict(output=report["output"], pages=len(report["pages"]), sha256=report["pdfSha256"])))


if __name__ == "__main__":
    main()
