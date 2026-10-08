"""Beri highlight + legenda di atas screenshot asli EasyEDA.

Posisi dikalibrasi dari lingkaran outline papan (garis ungu) pada tiap screenshot,
lalu koordinat PCB (satuan EasyEDA) diubah ke piksel.
Jalankan: python annotate_easyeda.py   (butuh Pillow; font Segoe UI Windows)
"""
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbrender as pr  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "easyeda")
OUT = os.path.join(HERE, "..", "img")
FB, FR = r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\segoeui.ttf"
CX, CY, RAD = pr.CX, pr.CY, pr.RAD
COMP = {c["des"]: c for c in pr.parse(pr.load())["comps"]}
PAL = [(255, 214, 0), (0, 229, 255), (118, 255, 3), (255, 109, 0), (224, 64, 251), (255, 255, 255),
       (0, 255, 127), (64, 196, 255), (105, 240, 174), (255, 171, 64)]


def font(sz, bold=False):
    return ImageFont.truetype(FB if bold else FR, sz)


def circle_fit(im):
    px = im.convert("RGB").load()
    xs, ys = [], []
    for y in range(im.size[1]):
        for x in range(im.size[0]):
            r, g, b = px[x, y]
            if 100 < r < 170 and g < 50 and 100 < b < 170 and abs(r - b) < 30:
                xs.append(x)
                ys.append(y)
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    k = ((max(xs) - min(xs)) + (max(ys) - min(ys))) / 4 / RAD
    return cx, cy, k


def bbox(des, pad=3):
    xs, ys = [], []
    for ds in des:
        for p in COMP[ds]["pads"]:
            m = max(p["w"], p["h"]) / 2
            xs += [p["x"] - m, p["x"] + m]
            ys += [p["y"] - m, p["y"] + m]
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def wrap(dr, text, fnt, width):
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if dr.textlength(t, font=fnt) <= width:
            cur = t
        else:
            out.append(cur)
            cur = w
    return out + [cur] if cur else out


def annotate(src, dst, items, title, up=2, crop=None):
    im = Image.open(os.path.join(SRC, src)).convert("RGBA")
    if crop:
        im = im.crop(crop)
    cx, cy, k = circle_fit(im)
    im = im.resize((im.size[0] * up, im.size[1] * up), Image.LANCZOS)
    cx, cy, k = cx * up, cy * up, k * up

    def P(x, y):
        return (cx + (x - CX) * k, cy + (y - CY) * k)

    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    marks = []
    for i, it in enumerate(items):
        col = it.get("color") or PAL[i % len(PAL)]
        it["_c"] = col
        rects = list(it.get("rects", []))
        if it.get("des"):
            if it.get("each"):
                rects += [bbox([d], it.get("pad", 3)) for d in it["des"]]
            else:
                rects.append(bbox(it["des"], it.get("pad", 3)))
        for (a, b, c, e) in rects:
            x0, y0 = P(a, b)
            x1, y1 = P(c, e)
            od.rectangle([x0, y0, x1, y1], fill=col + (50,), outline=col + (255,), width=4)
            marks.append((i, x0, y0))
        for (x, y, r) in it.get("circles", []):
            x0, y0 = P(x, y)
            rr = r * k
            od.ellipse([x0 - rr, y0 - rr, x0 + rr, y0 + rr], fill=col + (30,), outline=col + (255,), width=4)
            marks.append((i, x0 - rr * 0.7, y0 - rr * 0.7))
    im = Image.alpha_composite(im, ov)
    dr = ImageDraw.Draw(im)
    fn = font(26, True)
    placed = []
    for i, x, y in marks:
        rad = 17
        while any(math.hypot(x - a, y - b) < 2 * rad for a, b in placed):
            x += rad * 1.6
        placed.append((x, y))
        c = items[i]["_c"]
        dr.ellipse([x - rad, y - rad, x + rad, y + rad], fill=c + (255,), outline=(0, 0, 0, 255), width=3)
        t = str(i + 1)
        w = dr.textlength(t, font=fn)
        dr.text((x - w / 2, y - 16), t, font=fn, fill=(0, 0, 0, 255))
    W = im.size[0]
    fb, fr = font(28, True), font(25)
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    rows = [(it["name"], wrap(tmp, it["fn"], fr, W - 130)) for it in items]
    H = 100 + sum(46 + 32 * len(l) + 14 for _, l in rows) + 10
    out = Image.new("RGB", (W, im.size[1] + H), (255, 255, 255))
    out.paste(im.convert("RGB"), (0, 0))
    o = ImageDraw.Draw(out)
    y = im.size[1] + 14
    o.text((30, y), title, font=font(36, True), fill=(20, 20, 20))
    y += 70
    for it, (head, lines) in zip(items, rows):
        c = it["_c"]
        o.ellipse([30, y + 2, 68, y + 40], fill=c, outline=(0, 0, 0), width=2)
        t = str(items.index(it) + 1)
        w = o.textlength(t, font=fb)
        o.text((49 - w / 2, y + 4), t, font=fb, fill=(0, 0, 0))
        o.text((84, y + 4), head, font=fb, fill=(20, 20, 20))
        y += 46
        for ln in lines:
            o.text((84, y), ln, font=fr, fill=(70, 70, 70))
            y += 32
        y += 14
    out.save(os.path.join(OUT, dst), optimize=True)
    print("saved", dst, out.size)


TOP = [
    dict(name="ESP32-S3", fn="Modul MCU utama: menjalankan firmware GLD, SPI ke LoRa dan ADC, I²C ke sensor, GPIO alarm/kipas.", des=["U49"]),
    dict(name="LoRa E22-900MM22S", fn="Radio LoRa untuk komunikasi ke Cluster Head.", des=["U45"]),
    dict(name="Antena U.FL", fn="Konektor antena LoRa eksternal.", des=["G$1"]),
    dict(name="Port sensor (8 buah)", fn="Delapan header 2×4 yang mengelilingi papan; masing-masing untuk satu modul sensor (garis lingkaran kuning = outline modul).", des=["H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8"], each=True, pad=9, color=(0, 255, 127)),
    dict(name="ADS1256", fn="ADC 24-bit untuk membaca 8 kanal analog sensor.", des=["U35"]),
    dict(name="TCA9548A", fn="Mux I²C 8 kanal, satu kanal per port sensor.", des=["U33"]),
    dict(name="PCF8574", fn="Ekspander I/O: sinyal enable (EN0–EN7) tiap sensor.", des=["U12"]),
    dict(name="Micro-USB", fn="Port USB untuk flash firmware dan serial debug.", des=["USB1"]),
    dict(name="CH340C", fn="Konverter USB ke UART untuk programming dan serial monitor.", des=["U48"]),
    dict(name="Konektor ALARM", fn="Keluaran sirene/beacon 24 V.", des=["J2"]),
    dict(name="Konektor FAN", fn="Keluaran kipas 5 V.", des=["J3"]),
    dict(name="Konektor RS485", fn="Bus RS485 (A/B).", des=["J4"]),
    dict(name="Konektor VIN", fn="Input daya: 24V+, 24V−, 5VEXT, GND, BAT (baterai).", des=["J1"]),
    dict(name="Sekering PTC", fn="Membatasi arus pada jalur 24 V saat hubung singkat.", des=["F1"]),
    dict(name="TVS", fn="Menjepit lonjakan tegangan pada input 24 V.", des=["D1"]),
    dict(name="Filter common-mode", fn="Menyaring noise common-mode pada input 24 V.", des=["L1"]),
    dict(name="Buck 24 V → 5 V", fn="Regulator LMR51450: menurunkan 24 V menjadi 5 V.", des=["U36"]),
    dict(name="Boost baterai → 24 V", fn="TPS61175: menaikkan tegangan baterai ke rel +24V.", des=["U1"]),
    dict(name="Boost baterai → 5 V", fn="TPS61088: menghasilkan 5 V dari baterai.", des=["U41"]),
]

BOTTOM = [
    dict(name="Pour GND Bottom (area biru solid)", fn="Bidang GND sisi bawah mengisi hampir seluruh papan; tersambung ke pour atas lewat via.", rects=[]),
    dict(name="Konektor through-hole", fn="Satu-satunya komponen yang menembus ke Bottom; semua SMD ada di Top.", des=["J1", "J2", "J3", "J4", "USB1"], each=True),
]

G = (140, 200, 100)
PLACE = [  # screenshot penempatan dibuat manual; di sini hanya legenda fungsi
    dict(name="ESP32-S3", fn="MCU utama: menjalankan firmware dan mengontrol semua blok.", color=G),
    dict(name="LoRa (E22-900MM22S)", fn="Radio LoRa untuk komunikasi ke Cluster Head.", color=G),
    dict(name="Antenna (U.FL)", fn="Konektor antena LoRa eksternal.", color=G),
    dict(name="ADS1256", fn="ADC 24-bit untuk membaca 8 kanal analog sensor.", color=G),
    dict(name="TCA9548", fn="Mux I²C 8 kanal, satu kanal per port sensor.", color=G),
    dict(name="PCF8574", fn="Ekspander I/O untuk sinyal enable (EN0–EN7) tiap sensor.", color=G),
    dict(name="USB", fn="Micro-USB + CH340C untuk flash firmware dan serial monitor.", color=G),
    dict(name="RS485", fn="Transceiver THVD1410 untuk bus RS485.", color=G),
    dict(name="Driver Alarm", fn="MOSFET yang menyalakan sirene/beacon 24 V.", color=G),
    dict(name="Driver Fan", fn="MOSFET yang menyalakan kipas 5 V.", color=G),
    dict(name="SHT40", fn="Sensor suhu dan kelembapan di dalam casing.", color=G),
    dict(name="Power Block", fn="Input daya dan proteksi (konektor VIN, sekering, TVS, filter).", color=G),
    dict(name="TPL5010", fn="Timer watchdog yang membangunkan sistem secara berkala.", color=G),
]

DIM = [
    dict(name="Diameter papan: 84 mm", fn="Papan berbentuk lingkaran (outline ungu), menyesuaikan casing aluminium bulat.", circles=[(CX, CY, RAD)], color=(255, 214, 0)),
    dict(name="Pitch circle lubang casing: Ø64 mm", fn="Empat lubang casing berada pada lingkaran ini, tiap 90°.", circles=[(CX, CY, 126.0)], color=(0, 229, 255)),
]

HOLES_C = [(4215.5, 3636.016), (4341.484, 3762.0), (4215.5, 3887.984), (4089.516, 3762.0)]
HOLES_M = [(4363.138, 3714.756), (4061.957, 3732.079), (4132.823, 3893.89), (4272.587, 3618.3)]
MOUNT = [
    dict(name="Lubang casing (4 buah, Ø3,2 mm)", fn="Empat lubang pola casing aluminium (footprint casing) pada lingkaran Ø64 mm; tempat baut pengikat papan ke casing. Posisi dari pusat: (0, +32), (+32, 0), (0, −32), (−32, 0) mm.", circles=[(x, y, 11) for x, y in HOLES_C], color=(255, 214, 0)),
    dict(name="Lubang tambahan (4 buah, Ø3,0 mm)", fn="Empat lubang pengikat tambahan di dekat tepi papan (±39 mm dari pusat). Peruntukan pastinya (baut casing atau standoff) perlu dikonfirmasi dengan gambar mekanik.", circles=[(x, y, 11) for x, y in HOLES_M], color=(0, 229, 255)),
]

CONN = [
    dict(name="VIN", fn="Input daya 2×3 pin: 24V+, 24V−, 5VEXT, GND, BAT (baterai).", des=["J1"]),
    dict(name="ALARM", fn="Keluaran sirene/beacon 24 V (pin 1 = +24V, pin 2 = sisi switch MOSFET).", des=["J2"]),
    dict(name="FAN", fn="Keluaran kipas 5 V (pin 1 = +5V, pin 2 = sisi switch MOSFET).", des=["J3"]),
    dict(name="RS485", fn="Bus RS485: B (pin 1) dan A (pin 2).", des=["J4"]),
    dict(name="Micro-USB", fn="Flash firmware dan serial debug.", des=["USB1"]),
    dict(name="U.FL (antena)", fn="Konektor antena LoRa eksternal.", des=["G$1"]),
    dict(name="Port sensor (8 buah)", fn="Delapan header 2×4 (pitch 1,27 mm): GND, +5V, AINx, SCLx, SDAx, ENx, VMID. Masing-masing satu modul sensor.", des=["H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8"], each=True, pad=9, color=(0, 255, 127)),
]

POWER = [
    dict(name="Input daya & proteksi", fn="Konektor VIN, sekering, TVS, filter common-mode, ferrite: jalur masuk 24 V.", rects=[(4175, 3880, 4300, 3931)]),
    dict(name="Konverter 24 V → 5 V", fn="Buck LMR51450, induktor 4,7 µH, saklar P-MOSFET: menurunkan 24 V menjadi 5 V.", rects=[(4318, 3775, 4380, 3858)]),
    dict(name="Konverter baterai → 24 V", fn="Boost TPS61175, induktor 10 µH, dioda SK36 dan dioda OR: menaikkan tegangan baterai ke rel +24V.", rects=[(4194, 3798, 4285, 3850)]),
    dict(name="Konverter baterai → 5 V + power-mux", fn="Boost TPS61088, induktor 2,2 µH, power-mux TPS2116: 5 V dari baterai dan pemilihan sumber 5 V.", rects=[(4064, 3812, 4162, 3870)]),
    dict(name="Proteksi baterai", fn="Sekering, P-MOSFET anti-polaritas, load switch: mencegah baterai terbalik dan memutus baterai saat sistem tidur.", rects=[(4136, 3876, 4172, 3915)]),
]

SENSOR = [
    dict(name="Port sensor (8 buah)", fn="Delapan header: +5V, GND, VMID, ENx, SDAx/SCLx (I²C per kanal), AINx (analog ke ADC).", des=["H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8"], each=True),
    dict(name="TCA9548A", fn="Mux I²C: memecah bus I²C ESP32 menjadi 8 kanal untuk 8 sensor.", des=["U33"]),
    dict(name="PCF8574", fn="Ekspander I/O: menghasilkan EN0–EN7 untuk menyalakan tiap sensor.", des=["U12"]),
    dict(name="ADS1256 + kristal 8 MHz", fn="ADC 24-bit 8 kanal, SPI ke ESP32; clock dari kristal 8 MHz.", des=["U35", "U39"], each=True),
    dict(name="Referensi 2,5 V + buffer", fn="ADR03 menghasilkan VREF, dibuffer OPA320 ke ADC.", des=["U38", "U2"], each=True),
    dict(name="Buffer VMID", fn="OPA320 follower yang menghasilkan VMID (bias tengah analog) untuk modul sensor.", des=["U3"]),
]

_vias = [v for v in pr.parse(pr.load())["vias"] if v["net"] == "GND"]
_vias.sort(key=lambda v: math.atan2(v["y"] - CY, v["x"] - CX))
GND_VIAS = [(v["x"], v["y"], 9) for v in _vias[:: max(1, len(_vias) // 8)]][:8]
GND = [
    dict(name="Pour GND", fn="Satu bidang tembaga GND (garis hijau mengikuti tepi papan) di Top dan di Bottom, mengisi seluruh area bebas; jalur balik arus pendek dan perisai noise.", circles=[(CX, CY, RAD - 4)], color=(0, 255, 127)),
    dict(name="Via GND (contoh)", fn="176 via GND (dari 400 via) menyambung pour Top dan Bottom; lingkaran biru menandai beberapa contoh yang tersebar di papan.", circles=GND_VIAS, color=(0, 229, 255)),
    dict(name="24V− → GND di filter common-mode", fn="Return input 24 V (24V−) bergabung ke GND sistem lewat belitan negatif choke common-mode.", rects=[(4278, 3878, 4304, 3904)]),
    dict(name="Area analog tanpa split ground", fn="Hanya satu net GND. Area analog (ADS1256, referensi tegangan, OPA320) dipisah lewat suplai +5VA (ferrite), bukan lewat split ground.", rects=[(4222, 3695, 4320, 3800)]),
]

if __name__ == "__main__":
    annotate("top_layer_easyeda.png", "easyeda_01_top_layer.png", TOP, "Top layer – Main Board GLD")
    annotate("bottom_layer_easyeda.png", "easyeda_02_bottom_layer.png", BOTTOM, "Bottom layer – Main Board GLD")
    annotate("placement_easyeda.png", "easyeda_03_placement.png", PLACE, "Component placement – Main Board GLD", up=1, crop=(0, 0, 752, 761))
    annotate("dimension_easyeda.png", "easyeda_04_dimensions.png", DIM, "Board dimensions – Main Board GLD")
    annotate("top_layer_easyeda.png", "easyeda_05_mounting_holes.png", MOUNT, "Mounting holes – Main Board GLD")
    annotate("top_layer_easyeda.png", "easyeda_06_connectors.png", CONN, "Connectors – Main Board GLD")
    annotate("top_layer_easyeda.png", "easyeda_07_power_area.png", POWER, "High-current / power area – Main Board GLD")
    annotate("top_layer_easyeda.png", "easyeda_08_sensor_interface.png", SENSOR, "Sensor interface – Main Board GLD")
    annotate("top_layer_easyeda.png", "easyeda_09a_grounding_top.png", GND, "Grounding arrangement (Top) – Main Board GLD")
    annotate("bottom_layer_easyeda.png", "easyeda_09b_grounding_bottom.png", GND[:2], "Grounding arrangement (Bottom) – Main Board GLD")
