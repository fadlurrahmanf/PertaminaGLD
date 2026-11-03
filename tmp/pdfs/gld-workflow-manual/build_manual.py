"""Prepare/author an illustrated Indonesian protocol3 operator manual.

Import, --plan-only and --validate-only NEVER create a PDF or a PDF canvas.
The coordinator owns the skill marker and must run it immediately before the
first authoring invocation. All screenshots remain unedited original PNGs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DEFAULT_SPEC = ROOT / "tmp/wireless-workflow-release/browser-output/browser-evidence.json"
DEFAULT_OUTPUT = ROOT / "output/pdf/Manual-GLD-Dataset-Wizard.pdf"
WIDTH, HEIGHT = landscape(A4)
MARGIN, GAP = 28.0, 12.0
NAVY = colors.HexColor("#14334B")
TEAL = colors.HexColor("#007D80")
ORANGE = colors.HexColor("#DB661D")
INK = colors.HexColor("#233D4D")
MUTED = colors.HexColor("#526B79")
PAPER = colors.HexColor("#F3F7F9")
LINE = colors.HexColor("#D1DFE6")
PALE = colors.HexColor("#E8F4F3")
AMBER = colors.HexColor("#FFF1DD")
DISCLOSURE = "SIMULASI PC - sensor contoh; platform Windows diinjeksi untuk uji. Bukan pengoperasian GLD fisik."
CAPTION = "Tangkapan browser simulasi PC asli. PNG tidak diubah; kotak dan angka adalah anotasi vektor panduan."


def item(title, body):
    return dict(title=title, body=body)


CONTROL_TEXT = {
    "wfScan": item("Scan Nearby GLD", "Nyalakan GLD dengan 24 V, lalu pindai hotspot. Pilih perangkat dari daftar hasil scan."),
    "wfDevice": item("Pilih perangkat", "Pilih ID GLD yang benar. Nama hotspot mengikuti GLD-DATASET-xxxx; jangan pilih jaringan lain."),
    "wfPassword": item("Password hotspot wajib", "Masukkan password paket/perangkat sebelum Connect. Jangan menyalin password ke label atau nama file."),
    "wfConnect": item("Connect satu kali", "Klik Connect. Tunggu Windows tersambung dan identitas serta kesiapan GLD dikonfirmasi aplikasi."),
    "wfConnection": item("Indikator koneksi", "Lanjutkan setelah koneksi terverifikasi dan siap. Bila gagal, periksa hotspot, password, 24 V dan profil nulling."),
    "wfChooseFile": item("Pilih file CSV", "Tentukan folder dan nama CSV baru pada pemilih file Windows. Aplikasi tidak menimpa CSV yang sudah ada."),
    "wfPath": item("Periksa lokasi file", "Pastikan folder/nama file benar. Download CSV nanti mengambil salinan file yang sama."),
    "wfPrediction": item("Prediksi opsional", "Aktifkan bila model tersedia. Warmup/error/not_ready menyimpan kelas dan confidence kosong, bukan angka nol pengganti."),
    "wfGain": item("Gain dan status", "Pilih Gain serta Status sensor bila diperlukan di CSV. Kualitas lengkap tetap dicatat di ledger aplikasi."),
    "wfSensorStatus": item("Status sensor", "Kolom ini mencatat status delapan sensor. Hasil prediksi model terpisah dari status kualitas sensor."),
    "wfTiming": item("Waktu selalu tersimpan", "Timestamp GLD selalu masuk CSV. Pilihan ini hanya menambah scan_end/durasi pembacaan dan overrun."),
    "wfMode": item("Pilih kebijakan putus", "Rekam langsung membekukan CSV saat putus. Pulih otomatis memulihkan data tertunda ke sesi dan CSV yang sama."),
    "wfLabel": item("Label pengujian", "Isi kondisi yang benar, misalnya clear_air_test. Label adalah ground truth, bukan hasil prediksi model."),
    "wfLock": item("Lock setelah 7 langkah", "Pastikan tujuh langkah siap/hijau, lalu Lock. Pengaturan dikunci; kontrol Start/Pause/Stop tersedia."),
    "wfControls": item("Kontrol sesi", "Setelah Lock, gunakan Start, Pause dan Stop. Hindari mengubah konfigurasi ketika sesi masih aktif."),
    "wfStart": item("Start / Continue", "Sebelum rekaman pertama tombolnya Start. Setelah Stop terverifikasi, Continue menambah segmen baru dalam CSV yang sama."),
    "wfPause": item("Pause / Resume", "Pause menghentikan akuisisi di GLD setelah dikonfirmasi. Resume melanjutkan sesi yang sama; waktu jeda tidak diisi ulang."),
    "wfStop": item("Stop satu kali", "Klik Stop dan tunggu konfirmasi perangkat serta verifikasi semua baris CSV. Respons tombol saja belum berarti selesai."),
    "wfCount": item("Hitungan tersimpan", "Hitungan bertambah setelah data disimpan aplikasi. Target pembacaan lengkap delapan sensor adalah setiap 500 ms."),
    "wfChart": item("Grafik delapan sensor", "Amati MQ8, MQ135, MQ3, MQ5, MQ4, MQ7, MQ6 dan MQ2. Grafik menampilkan contoh data pada simulasi ini."),
    "wfState": item("Baca status sesi", "Bedakan merekam, jeda, memulihkan, selesai dan tidak lengkap. Jangan menganggap koneksi kembali berarti semua data sudah tersimpan."),
    "wfMessage": item("Ikuti pesan aplikasi", "Tunggu penutupan/pemulihan milik sesi ini. Jangan Start baru, mematikan GLD, atau menganggap incomplete sebagai lengkap."),
    "wfVerification": item("Verifikasi seluruh CSV", "Tunggu status verifikasi cocok: semua baris dan kolom file diperiksa terhadap ledger lengkap, bukan hanya grafik."),
    "wfExport": item("Download CSV", "Unduh salinan file setelah verifikasi. Periksa label, delapan kanal dan keterangan lengkap/tidak lengkap."),
    "wfReset": item("Reset mempertahankan file", "Reset membersihkan form, bukan menghapus CSV/NVS. Jika sedang Pause, aplikasi harus Stop dan verifikasi lebih dahulu."),
    "wfRows": item("Tabel sampel", "Tabel menampilkan sampel terakhir. CSV dan ledger memuat seluruh baris, termasuk yang sudah tidak terlihat di grafik."),
}

PAGES = [
    dict(key="overview", title="Dataset GLD: tujuh langkah sebelum Start", subtitle="Panduan Wizard Dataset - Wi-Fi, delapan sensor, target 500 ms", images=["01-wizard-empty"], kind="overview"),
    dict(key="connect", title="1-4. Hubungkan GLD dan pilih file", subtitle="Scan Nearby GLD, pilih ID, isi password lalu Connect. Setelah indikator hijau, pilih lokasi CSV.", images=["02-device-connected"], crop=dict(x=215,y=90,w=1130,h=375), steps=[
        CONTROL_TEXT[k] for k in ("wfDevice", "wfPassword", "wfConnect", "wfConnection")]),
    dict(key="file_fields", title="5-7. Kolom, mode dan label pengujian", subtitle="Delapan tegangan, timestamp dan identitas selalu disimpan. Gain/status opsional; prediksi yang belum valid tetap kosong.", images=["03-options-ready"], steps=[
        CONTROL_TEXT[k] for k in ("wfChooseFile", "wfPrediction", "wfGain", "wfTiming")]),
    dict(key="lock", title="Lock: tampilkan kontrol rekaman", subtitle="Pastikan tujuh nomor hijau. Setelah dikunci, pengaturan terlihat tetapi tidak dapat diubah.", images=["04-locked"], crop=dict(x=215,y=545,w=1130,h=360), steps=[
        CONTROL_TEXT[k] for k in ("wfMode", "wfLabel", "wfLock", "wfControls")]),
    dict(key="recording", title="Start dan pantau delapan kurva", subtitle="Klik satu kali; tunggu status merekam dan hitungan sampel tersimpan bertambah.", images=["05-recording"], crop=dict(x=215,y=80,w=1135,h=515), steps=[
        CONTROL_TEXT[k] for k in ("wfStart", "wfCount", "wfChart")]),
    dict(key="paused", title="Pause adalah jeda pengukuran di GLD", subtitle="Setelah terkonfirmasi, sensor tidak membuat baris baru sampai Resume.", images=["06-paused"], crop=dict(x=215,y=80,w=1130,h=430), steps=[
        CONTROL_TEXT[k] for k in ("wfPause", "wfState", "wfStop")]),
    dict(key="verified", title="Stop: tunggu verifikasi, lalu OK", subtitle="Notifikasi selesai tampil setelah file nyata dibandingkan dengan seluruh ledger.", images=["07-stop-verified"], steps=[
        item("Periksa hasil verifikasi", "Tunggu pesan seluruh baris/kolom cocok. Jika incomplete, data yang tersimpan tetap berguna tetapi sesi tidak boleh disebut lengkap."),
        item("OK setelah membaca pesan", "Tutup notifikasi dengan OK setelah memahami hasil lengkap/tidak lengkap. OK tidak membuat atau mengulang pengukuran."),
        CONTROL_TEXT["wfExport"]]),
    dict(key="continue", title="Continue: file sama, segmen baru", subtitle="Continue setelah Stop berbeda dari Resume setelah Pause.", images=["08-continue-ready"], crop=dict(x=215,y=80,w=1130,h=430), steps=[
        item("Continue setelah Stop", "Tetap memakai file dan konfigurasi yang sama. GLD mendapat SID baru dan seq mulai 0; row_id global terus bertambah."),
        item("Jangan ubah file dari luar", "Aplikasi memeriksa hash, skema, perangkat, profil dan model sebelum append. Perubahan yang tidak cocok ditolak."),
        CONTROL_TEXT["wfReset"]]),
    dict(key="loss_modes", title="Saat putus: dua kebijakan yang berbeda", subtitle="GLD harus tetap menyala. Kedua mode menyelesaikan hanya sesi yang dimiliki aplikasi.", images=["09-direct-link-lost", "10-replay-link-lost"], kind="comparison", steps=[
        item("A. Rekam langsung", "CSV/hitungan/grafik sesi dibekukan dan ditandai tidak lengkap. Aplikasi hanya menutup serta menguras sesi lama ke ledger privat."),
        item("B. Pulih otomatis", "Sesi dan CSV tetap sama. Data tertunda disalin dengan timestamp aslinya; transport reconnect tidak membatalkan Pause."),
        item("Tunggu penyelesaian", "Jangan Start lagi atau pindah perangkat saat cleanup/pemulihan. Jika dibatalkan, hubungkan GLD yang sama untuk menyelesaikan sesi.")]),
    dict(key="recovered", title="Selesai pulih: simpan hasil dan batasnya", subtitle="Verifikasi file tetap wajib, termasuk sesudah reconnect atau penghentian karena batas buffer.", images=["11-replay-complete"], crop=dict(x=215,y=80,w=1135,h=515), steps=[
        item("Lima menit adalah batas RAM", "Pada 300 detik tanpa kemajuan ACK, sampling dihentikan incomplete. Data yang masih ditahan dapat diambil selama GLD tetap menyala."),
        item("Mati/reboot bukan pemulihan", "Power loss menghapus RAM. Restart proses backend/laptop juga tidak menjamin lanjut sesi. Pertahankan CSV yang sudah tersimpan."),
        item("Jika Connect/Continue gagal", "Periksa 24 V, hotspot/password dan profil. Jika file berubah/model berbeda, jangan paksa append: simpan file lalu Reset dan pilih file baru.")]),
]

CAPTURE_SELECTORS = {
    "01-wizard-empty": ["#wfScan", "#wfLock"],
    "02-device-connected": ["#wfDevice", "#wfPassword", "#wfConnect", "#wfConnection"],
    "03-options-ready": ["#wfChooseFile", "#wfPrediction", "#wfGain", "#wfTiming"],
    "04-locked": ["#wfMode", "#wfLabel", "#wfLock", "#wfControls"],
    "05-recording": ["#wfStart", "#wfCount", "#wfChart"],
    "06-paused": ["#wfPause", "#wfState", "#wfStop"],
    "07-stop-verified": ["verification-popup", "verification-ok", "#wfExport"],
    "08-continue-ready": ["#wfStart", "#wfPath", "#wfReset"],
    "09-direct-link-lost": ["#wfState", "#wfMessage"],
    "10-replay-link-lost": ["#wfState", "#wfMessage"],
    "11-replay-complete": ["#wfVerification", "#wfExport"],
}


def clean(value):
    result = str(value)
    for char in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212"):
        result = result.replace(char, "-")
    return result


def fonts():
    for name, filename in (("WizardArial", "arial.ttf"), ("WizardBold", "arialbd.ttf"), ("WizardItalic", "ariali.ttf")):
        path = Path("C:/Windows/Fonts") / filename
        if not path.is_file():
            raise RuntimeError("Font Arial belum tersedia; selesaikan sebelum membuat PDF.")
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily("WizardArial", normal="WizardArial", bold="WizardBold", italic="WizardItalic", boldItalic="WizardBold")


def paragraph(content, width, size=10, bold=False, color=INK):
    style = ParagraphStyle("wizard", fontName="WizardBold" if bold else "WizardArial", fontSize=size,
        leading=size * 1.28, textColor=color, allowWidows=0, allowOrphans=0, splitLongWords=0)
    result = Paragraph(escape(clean(content)).replace("\n", "<br/>"), style)
    _, height = result.wrap(width, HEIGHT)
    return result, height


def plan():
    return dict(schema="gld-workflow-manual/1", output=str(DEFAULT_OUTPUT), page_count=len(PAGES),
        source_evidence=str(DEFAULT_SPEC), disclosure_every_page=DISCLOSURE, pages=PAGES,
        capture_selectors=CAPTURE_SELECTORS, raster_policy="Original PNG bytes; vector clip/rectangles/number bubbles only.",
        pdf_creation_requires_coordinator_marker=True, current_scope="source preparation only")


def resolve_path(value, spec_path):
    value = Path(value)
    candidates = [value] if value.is_absolute() else [spec_path.parent / value, ROOT / value, HERE / value]
    return next((path.resolve() for path in candidates if path.is_file()), candidates[0].resolve())


def clamp_box(raw, width, height):
    values = {key: float(raw[key]) for key in ("x", "y", "w", "h")}
    if values["w"] <= 0 or values["h"] <= 0:
        raise ValueError("Kotak sumber harus mempunyai ukuran positif.")
    x, y = max(0.0, values["x"]), max(0.0, values["y"])
    right, bottom = min(float(width), values["x"] + values["w"]), min(float(height), values["y"] + values["h"])
    if right <= x or bottom <= y:
        return None
    result = dict(raw, x=x, y=y, w=right-x, h=bottom-y)
    result["source_clipped"] = any(abs(result[key] - values[key]) > .01 for key in values)
    return result


def load_images(path, allow_missing=False):
    spec = json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
    records = spec.get("screenshots", [])
    if isinstance(records, dict):
        records = [dict(value, key=key) for key, value in records.items()]
    if not isinstance(records, list):
        raise ValueError("screenshots harus berupa daftar/mapping metadata screenshot browser.")
    sources, missing = {}, []
    by_key = {record.get("key"): record for record in records if isinstance(record, dict)}
    for key in CAPTURE_SELECTORS:
        raw = by_key.get(key)
        if not raw:
            missing.append(key)
            continue
        source = resolve_path(raw["path"], path)
        if not source.is_file():
            missing.append(key)
            continue
        if source.suffix.lower() != ".png":
            raise ValueError(f"Screenshot harus PNG asli tanpa edit: {key}")
        with Image.open(source) as image:
            width, height = image.size
            image.verify()
        if width <= 0 or height <= 0 or (raw.get("width") and int(raw["width"]) != width) or (raw.get("height") and int(raw["height"]) != height):
            raise ValueError(f"Dimensi metadata berbeda dari PNG asli: {key}")
        boxes, numbers, skipped = [], set(), []
        for entry in raw.get("boxes", []):
            number = entry.get("n")
            if type(number) is not int or not 1 <= number <= 99 or number in numbers:
                raise ValueError(f"Nomor kotak tidak valid/duplikat: {key}")
            numbers.add(number)
            # These DOM positions lie beneath the sticky app header in the
            # captured scroll position. Drawing them would point to the upload
            # button painted above Reset, so omit the occluded callout.
            if key in {"06-paused", "08-continue-ready"} and entry.get("selector") == "#wfReset":
                skipped.append(number)
                continue
            clipped = clamp_box(entry, width, height)
            if clipped:
                boxes.append(clipped)
            else:
                skipped.append(number)
        if not boxes:
            raise ValueError(f"Tidak ada kotak DOM yang terlihat pada screenshot: {key}")
        if len(boxes) > 4:
            raise ValueError(f"Batasi empat kotak per screenshot agar petunjuk mudah dibaca: {key}")
        sources[key] = dict(raw, path=source, width=width, height=height, boxes=sorted(boxes, key=lambda box: box["n"]),
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), skipped_offscreen_boxes=skipped)
    if missing and not allow_missing:
        raise ValueError("Screenshot browser belum tersedia: " + ", ".join(missing))
    return spec, sources, missing


def focus(entry, target_width, target_height):
    if isinstance(entry.get("crop"), dict):
        crop = clamp_box(entry["crop"], entry["width"], entry["height"])
        if crop is None:
            raise ValueError("Viewport screenshot tidak terlihat.")
        return {key: crop[key] for key in ("x", "y", "w", "h")}
    boxes = entry["boxes"]
    left, top = min(box["x"] for box in boxes), min(box["y"] for box in boxes)
    right, bottom = max(box["x"]+box["w"] for box in boxes), max(box["y"]+box["h"] for box in boxes)
    padding = 28
    width = min(entry["width"], max(right-left+2*padding, min(640, entry["width"])))
    context_height = min(240, max(110, target_height*1.25))
    height = min(entry["height"], max(bottom-top+2*padding, min(context_height, entry["height"])))
    aspect = target_width / target_height
    if width / height > aspect:
        height = min(entry["height"], max(height, width/aspect))
    else:
        width = min(entry["width"], max(width, height*aspect))
    x = max(0, min(entry["width"]-width, (left+right-width)/2))
    y = max(0, min(entry["height"]-height, (top+bottom-height)/2))
    return dict(x=x, y=y, w=width, h=height)


def legend_for(page, entry):
    result = []
    for index, box in enumerate(entry["boxes"]):
        selector = str(box.get("selector", ""))
        matched = selector[1:] if selector.startswith("#") and selector[1:] in CONTROL_TEXT else None
        fallback = page.get("steps", [item("Kontrol Wizard", "Ikuti urutan langkah dan status kesiapan aplikasi.")])
        text = CONTROL_TEXT[matched] if matched else fallback[min(index, len(fallback)-1)]
        if page["key"] == "verified" and ("modal" in selector.lower() or "dialog" in selector.lower() or "popup" in selector.lower()):
            if "ok" in selector.lower() or "button" in selector.lower():
                text = item("OK, lalu unduh CSV", "Klik OK setelah membaca hasil. Setelah notifikasi ditutup, gunakan Download CSV untuk mengambil salinan file yang sama.")
            elif "title" in selector.lower():
                text = item("Judul hasil rekaman", "Notifikasi ini muncul setelah verifikasi selesai. Bedakan hasil lengkap dari rekaman tidak lengkap; jangan hanya melihat tombol Stop.")
            else:
                text = page["steps"][0]
        if page["key"] == "continue" and matched == "wfStart":
            text = page["steps"][0]
        result.append(dict(n=box["n"], **text))
    return result


class Layout:
    def __init__(self):
        self.pages = []
        self.page = None
    def begin(self, page, number):
        self.page = dict(number=number, key=page["key"], title=page["title"], rectangles=[], text=[], screenshots=[])
        self.pages.append(self.page)
    def rect(self, role, x, y, width, height):
        if x < -.1 or y < -.1 or width <= 0 or height <= 0 or x+width > WIDTH+.1 or y+height > HEIGHT+.1:
            raise ValueError(f"Layout di luar halaman: {self.page['key']}/{role}")
        value = dict(role=role, x=round(x,2), y=round(y,2), w=round(width,2), h=round(height,2))
        self.page["rectangles"].append(value)
        return value
    def measure(self, content, x, top, width, max_height, size=10, bold=False, role="text", color=INK):
        para, height = paragraph(content, width, size, bold, color)
        if height > max_height+.1:
            raise ValueError(f"Teks meluap {self.page['key']}/{role}: {height:.1f}>{max_height:.1f}pt: {clean(content)[:80]}")
        self.rect(role, x, top-height, width, height)
        self.page["text"].append(dict(role=role, font_size=size, measured_height=round(height,2), allocated_height=max_height, content=clean(content)))
        return para, height


def label(c, layout, content, x, top, width, max_height, size=10, bold=False, color=INK, role="text"):
    paragraph_item, height = layout.measure(content, x, top, width, max_height, size, bold, role, color)
    if c is not None:
        paragraph_item.drawOn(c, x, top-height)
    return height


def panel(c, layout, x, y, width, height, fill=colors.white, role="panel"):
    layout.rect(role, x, y, width, height)
    if c is not None:
        c.setFillColor(fill); c.setStrokeColor(LINE); c.setLineWidth(.65)
        c.roundRect(x, y, width, height, 7, fill=1, stroke=1)


def bubble(c, value, x, y, radius=9):
    if c is not None:
        c.setFillColor(ORANGE); c.setStrokeColor(colors.white); c.setLineWidth(1)
        c.circle(x,y,radius,fill=1,stroke=1)
        c.setFillColor(colors.white); c.setFont("WizardBold", 8 if len(str(value)) > 1 else 9.5)
        c.drawCentredString(x,y-3,str(value))


def header(c, layout, page, number):
    if c is not None:
        c.setFillColor(PAPER); c.rect(0,0,WIDTH,HEIGHT,fill=1,stroke=0)
        c.setFillColor(TEAL); c.rect(0,HEIGHT-6,WIDTH,6,fill=1,stroke=0)
    label(c,layout,"PANDUAN OPERATOR  /  WIZARD DATASET GLD",MARGIN,HEIGHT-17,WIDTH-2*MARGIN,13,9,True,TEAL,"eyebrow")
    label(c,layout,DISCLOSURE,MARGIN,HEIGHT-33,WIDTH-2*MARGIN,16,8.2,False,MUTED,"simulation_disclosure")
    label(c,layout,page["title"],MARGIN,HEIGHT-57,WIDTH-2*MARGIN,33,23,True,NAVY,"title")
    label(c,layout,page["subtitle"],MARGIN,HEIGHT-93,WIDTH-2*MARGIN,28,10,False,MUTED,"subtitle")
    if c is not None:
        c.setStrokeColor(LINE); c.line(MARGIN,30,WIDTH-MARGIN,30)
    label(c,layout,"SIMULASI PC | Sensor contoh | Platform Windows diinjeksi | 2 November 2026",MARGIN,21,WIDTH-130,12,7.7,False,MUTED,"footer")
    if c is not None:
        c.setFont("WizardBold",8); c.setFillColor(MUTED)
        c.drawRightString(WIDTH-MARGIN,13,f"{number:02d} / {len(PAGES):02d}")


def draw_screenshot(c, layout, entry, x, y, width, height, prefix=""):
    layout.rect("screenshot_frame",x,y,width,height)
    crop = focus(entry,width,height)
    scale = min(width/crop["w"],height/crop["h"])
    iw, ih = crop["w"]*scale,crop["h"]*scale
    left, bottom = x+(width-iw)/2,y+(height-ih)/2
    panel(c,layout,x-3,y-3,width+6,height+6,role="image_border")
    if c is not None:
        c.saveState()
        path=c.beginPath(); path.rect(left,bottom,iw,ih); c.clipPath(path,stroke=0,fill=0)
        c.drawImage(str(entry["path"]),left-crop["x"]*scale,
            bottom-(entry["height"]-crop["y"]-crop["h"])*scale,
            width=entry["width"]*scale,height=entry["height"]*scale,mask="auto")
        c.restoreState()
    rendered=[]
    for raw in entry["boxes"]:
        intersect = dict(x=max(raw["x"],crop["x"]),y=max(raw["y"],crop["y"]))
        intersect["w"] = min(raw["x"]+raw["w"],crop["x"]+crop["w"])-intersect["x"]
        intersect["h"] = min(raw["y"]+raw["h"],crop["y"]+crop["h"])-intersect["y"]
        if intersect["w"] <= 0 or intersect["h"] <= 0:
            raise ValueError(f"Kotak panduan di luar viewport fokus: {entry['key']}/{raw['n']}")
        bx=left+(intersect["x"]-crop["x"])*scale
        by=bottom+(crop["h"]-(intersect["y"]-crop["y"])-intersect["h"])*scale
        bw,bh=intersect["w"]*scale,intersect["h"]*scale
        rectangle=layout.rect("vector_callout",bx,by,bw,bh)
        if c is not None:
            c.setLineWidth(1.8); c.setStrokeColor(ORANGE)
            c.roundRect(bx,by,bw,bh,min(4,bh/5),stroke=1,fill=0)
        radius=9
        nx=max(left+radius,min(left+iw-radius,bx-3))
        ny=max(bottom+radius,min(bottom+ih-radius,by+bh+3))
        layout.rect("number_bubble",nx-radius,ny-radius,2*radius,2*radius)
        bubble(c,prefix+str(raw["n"]),nx,ny,radius)
        rendered.append(dict(n=raw["n"],selector=raw.get("selector"),source_clipped=raw["source_clipped"],pdf=rectangle))
    detail=dict(key=entry["key"],path=str(entry["path"]),source_sha256=entry["source_sha256"],
        original_png_unedited=True,source_viewport=crop,scale=round(scale,5),boxes=rendered,
        skipped_offscreen_boxes=entry["skipped_offscreen_boxes"])
    layout.page["screenshots"].append(detail)


def cards(c, layout, items, top=143, bottom=43, size=9.5):
    if not 1 <= len(items) <= 4:
        raise ValueError("Gunakan satu sampai empat kartu petunjuk per halaman.")
    width=(WIDTH-2*MARGIN-GAP*(len(items)-1))/len(items)
    for index, entry in enumerate(items):
        x=MARGIN+index*(width+GAP)
        panel(c,layout,x,bottom,width,top-bottom,role="instruction_card")
        number=entry.get("n",index+1)
        bubble(c,number,x+15,top-16,8)
        title_height=label(c,layout,entry["title"],x+29,top-8,width-39,27,10,True,NAVY,"card_title")
        body_top=top-max(36,title_height+15)
        label(c,layout,entry["body"],x+11,body_top,width-22,body_top-bottom-8,size,False,INK,"card_body")


def overview(c, layout, images):
    width=(WIDTH-2*MARGIN-3*GAP)/4
    top=462
    flow=[("GLD 24 V", "Firmware Wizard Dataset, profil nulling valid dan delapan sensor siap."),
          ("Wi-Fi GLD", "Pilih GLD-DATASET-xxxx. Hotspot perangkat tidak menyediakan Internet."),
          ("7 langkah + Lock", "Perangkat, koneksi, file, kolom, mode dan label harus siap sebelum Start."),
          ("Grafik + CSV", "Backend laptop menyimpan data. Stop menunggu verifikasi seluruh file.")]
    for index,(title,body) in enumerate(flow):
        x=MARGIN+index*(width+GAP)
        panel(c,layout,x,top-87,width,87,PALE,"flow_card")
        label(c,layout,title,x+11,top-11,width-22,18,11,True,NAVY,"flow_title")
        label(c,layout,body,x+11,top-36,width-22,43,9.8,False,INK,"flow_body")
    left_width=366
    panel(c,layout,MARGIN,62,left_width,288,role="prerequisites")
    label(c,layout,"Sebelum memakai GLD fisik",MARGIN+13,336,left_width-26,22,13,True,NAVY,"prerequisites_title")
    lines=[
        ("1. Paket yang sesuai", "Administrator memilih Hotspot Wizard Dataset untuk Model 1/2/3 yang sesuai board. Paket Hotspot/Buffer lama tidak menyediakan seluruh kontrol Wizard."),
        ("2. Pertahankan kalibrasi", "Gunakan profil nulling valid dan catu eksternal 24 V. Untuk pemasangan pada perangkat yang sudah dikalibrasi, Reset NVS harus OFF sesuai prosedur administrator."),
        ("3. Simpan proses backend", "Browser dapat ditutup, tetapi proses Operator Hub/backend harus tetap berjalan. Restart backend/laptop bukan pemulihan sesi yang dijamin."),
    ]
    y=302
    for title,body in lines:
        label(c,layout,title,MARGIN+13,y,left_width-26,18,10.5,True,TEAL,"prereq_step")
        h=label(c,layout,body,MARGIN+13,y-22,left_width-26,58,10,False,INK,"prereq_body")
        y-=max(72,h+32)
    x=MARGIN+left_width+GAP
    image_width=WIDTH-MARGIN-x
    image=images.get("01-wizard-empty")
    if image:
        draw_screenshot(c,layout,image,x,113,image_width,234)
    label(c,layout,"Orientasi layar Wizard: kotak menunjuk kontrol yang benar-benar ada pada tangkapan browser simulasi.",x,99,image_width,34,9,False,MUTED,"overview_caption")
    label(c,layout,"Contoh di seluruh panduan adalah simulasi PC, bukan bukti pengukuran gas atau uji GLD fisik.",MARGIN,49,WIDTH-2*MARGIN,13,8.7,True,TEAL,"overview_limit")


def photo_page(c, layout, page, images):
    key=page["images"][0]
    entry=images.get(key)
    if entry:
        if page.get("crop"):
            entry=dict(entry,crop=page["crop"])
        draw_screenshot(c,layout,entry,MARGIN+3,170,WIDTH-2*MARGIN-6,HEIGHT-296)
        annotations=legend_for(page,entry)
        if page["key"] in {"paused", "continue"}:
            annotations.append(dict(n="!",title="Catatan Reset sesi",body="Reset berada di baris Lock (lihat halaman 4). Reset membersihkan form dan mempertahankan CSV. Saat Pause, aplikasi harus Stop dan memverifikasi file terlebih dahulu."))
    else:
        annotations=[dict(n=index+1,**value) for index,value in enumerate(page.get("steps",[]))]
    label(c,layout,CAPTION,MARGIN,160,WIDTH-2*MARGIN,13,8.1,False,MUTED,"image_caption")
    cards(c,layout,annotations)


def compare_page(c, layout, page, images):
    width=WIDTH-2*MARGIN
    for index,key in enumerate(page["images"]):
        x=MARGIN
        top=467 if index==0 else 318
        image_y=355 if index==0 else 204
        label(c,layout,"A. REKAM LANGSUNG" if index==0 else "B. PULIH OTOMATIS",x,top,width,18,11,True,TEAL,"mode_title")
        if images.get(key):
            draw_screenshot(c,layout,images[key],x+3,image_y,width-6,90,prefix="A" if index==0 else "B")
            annotations=legend_for(page,images[key])
            legend="; ".join(("A" if index==0 else "B")+str(value["n"])+": "+value["title"] for value in annotations)
            label(c,layout,legend+". Tampilan browser simulasi PC.",x,image_y-8,width,15,8.6,False,MUTED,"comparison_legend")
    cards(c,layout,[dict(n=("A","B","!")[index],**value) for index,value in enumerate(page["steps"])],top=172)


def recovered_page(c, layout, page, images):
    entry=images.get(page["images"][0])
    if entry:
        if page.get("crop"):
            entry=dict(entry,crop=page["crop"])
        draw_screenshot(c,layout,entry,MARGIN+3,270,WIDTH-2*MARGIN-6,HEIGHT-396)
        annotations=legend_for(page,entry)
    else:
        annotations=[dict(n=1,**CONTROL_TEXT["wfVerification"]),dict(n=2,**CONTROL_TEXT["wfExport"])]
    label(c,layout,CAPTION,MARGIN,260,WIDTH-2*MARGIN,13,8.1,False,MUTED,"image_caption")
    cards(c,layout,annotations,top=245,bottom=143,size=9.3)
    width=(WIDTH-2*MARGIN-2*GAP)/3
    for index,note in enumerate(page["steps"]):
        x=MARGIN+index*(width+GAP)
        panel(c,layout,x,43,width,89,AMBER,"boundary_note")
        label(c,layout,note["title"],x+10,122,width-20,15,9.8,True,NAVY,"boundary_title")
        label(c,layout,note["body"],x+10,99,width-20,48,8.8,False,INK,"boundary_body")


def render_pass(c, images):
    layout=Layout()
    for number,page in enumerate(PAGES,1):
        layout.begin(page,number)
        header(c,layout,page,number)
        if page.get("kind")=="overview": overview(c,layout,images)
        elif page.get("kind")=="comparison": compare_page(c,layout,page,images)
        elif page["key"]=="recovered": recovered_page(c,layout,page,images)
        else: photo_page(c,layout,page,images)
        if c is not None: c.showPage()
    return layout


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec",type=Path,default=DEFAULT_SPEC)
    parser.add_argument("--output",type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument("--report",type=Path,default=HERE/"layout-report.json")
    parser.add_argument("--plan-only",action="store_true",help="Write manual-plan.json source only; no fonts/images/PDF authoring")
    parser.add_argument("--validate-only",action="store_true",help="Measure text/check screenshots and boxes, no PDF or canvas created")
    parser.add_argument("--allow-missing-images",action="store_true",help="Source-layout validation only; never authorize PDF with missing screenshots")
    args=parser.parse_args()
    if args.plan_only:
        target=HERE/"manual-plan.json"
        target.write_text(json.dumps(plan(),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(dict(plan=str(target),pages=len(PAGES),pdf_written=False)))
        return
    fonts()
    spec,images,missing=load_images(args.spec.resolve(),args.allow_missing_images and args.validate_only)
    measured=render_pass(None,images)
    validation=dict(schema="gld-workflow-manual-layout/1",pages=len(PAGES),page_size="A4 landscape",fonts="Arial",
        plan_valid=True,ready_to_author=not missing,missing_screenshots=missing,
        source_evidence=str(args.spec.resolve()),screenshots_checked=len(images),pdf_written=False,
        simulation_disclosure=DISCLOSURE,layout=measured.pages)
    if args.validate_only:
        print(json.dumps(validation,ensure_ascii=False,indent=2))
        return
    if missing:
        raise ValueError("Tidak boleh membuat PDF dengan screenshot yang hilang.")
    output=args.output.resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    c=canvas.Canvas(str(output),pagesize=(WIDTH,HEIGHT),pageCompression=1)
    c.setTitle("Panduan Operator - GLD Dataset Wizard")
    c.setAuthor("Pertamina GLD / Operator Hub")
    c.setSubject("Panduan ilustrasi browser simulasi PC; bukan uji GLD fisik")
    authored=render_pass(c,images)
    c.save()
    for entry in images.values():
        if hashlib.sha256(entry["path"].read_bytes()).hexdigest()!=entry["source_sha256"]:
            raise RuntimeError("PNG sumber berubah saat authoring; jangan distribusikan PDF.")
    validation.update(pdf_written=True,output=str(output),pdf_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        layout=authored.pages,raster_policy="Original PNGs unchanged; vector viewport clips, rectangles and number bubbles only.",
        visual_qa_required=True)
    args.report.resolve().parent.mkdir(parents=True,exist_ok=True)
    args.report.resolve().write_text(json.dumps(validation,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(dict(output=str(output),pages=len(PAGES),sha256=validation["pdf_sha256"],report=str(args.report.resolve()),visual_qa_required=True)))


if __name__=="__main__":
    main()
