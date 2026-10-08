# Jalankan: python gen.py  (butuh Pillow; font Segoe UI Windows)
import math, os, textwrap
from PIL import Image, ImageDraw, ImageFont
import pcbrender as pr
from pcbrender import R, load, CX, CY, RAD, X0, Y0, X1, Y1

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "img")
os.makedirs(OUT, exist_ok=True)
FB = r"C:\Windows\Fonts\segoeuib.ttf"
FR = r"C:\Windows\Fonts\segoeui.ttf"
d = load()
r = R(d, 6)
COMP = {c["des"]: c for c in r.P["comps"]}
PAL = [(231, 76, 60), (52, 152, 219), (46, 204, 113), (243, 156, 18), (155, 89, 182), (26, 188, 156),
       (241, 196, 15), (233, 30, 99), (0, 188, 212), (139, 195, 74), (255, 112, 67), (121, 134, 203),
       (205, 220, 57), (171, 71, 188), (255, 167, 38), (38, 166, 154)]
_cache = {}


def base(side, scale, **kw):
    k = (side, scale, tuple(sorted((a, id(b)) for a, b in kw.items())))
    if k not in _cache:
        rr = R(d, scale)
        _cache[k] = (rr, rr.render_native(side))
    return _cache[k]


def bbox(des, pad=2.5):
    xs, ys = [], []
    for ds in des:
        c = COMP[ds]
        for p in c["pads"]:
            m = max(p["w"], p["h"]) / 2 if p["shape"] != "ELLIPSE" else p["w"] / 2
            xs += [p["x"] - m, p["x"] + m]
            ys += [p["y"] - m, p["y"] + m]
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def font(sz, bold=False):
    return ImageFont.truetype(FB if bold else FR, sz)


def wrap(dr, text, fnt, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if dr.textlength(t, font=fnt) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def figure(fname, side, crop, items, title, scale=8, minw=1500, labels=False, **kw):
    if side == "top" and "pourcol" not in kw:
        kw["pourcol"] = (40, 160, 90, 55)
    rr, img = base(side, scale, **kw)
    x0, y0, x1, y1 = crop
    A = (rr.tx(x0, y0), rr.tx(x1, y1))
    px0, py0 = rr.tx(x0, y0)
    px1, py1 = rr.tx(x1, y1)
    if px1 < px0:
        px0, px1 = px1, px0
    im = img.crop((int(px0), int(py0), int(px1), int(py1))).convert("RGBA")
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    fn = font(max(22, int(scale * 3.2)), True)
    boxes = []
    for i, it in enumerate(items):
        col = it.get("color") or PAL[i % len(PAL)]
        it["_col"] = col
        rects = list(it.get("rects", []))
        if it.get("des"):
            if it.get("each"):
                for ds in it["des"]:
                    rects.append(bbox([ds], it.get("pad", 2.5)) + (ds,))
            else:
                rects.append(bbox(it["des"], it.get("pad", 2.5)) + (",".join(it["des"]) if len(it["des"]) < 3 else it["des"][0],))
        for rc in rects:
            a, b, c, e = rc[:4]
            lab = rc[4] if len(rc) > 4 else None
            p0 = rr.tx(a, b)
            p1 = rr.tx(c, e)
            xa, xb = sorted([p0[0], p1[0]])
            ya, yb = sorted([p0[1], p1[1]])
            xa, xb, ya, yb = xa - px0, xb - px0, ya - py0, yb - py0
            od.rectangle([xa, ya, xb, yb], fill=col + (70,), outline=col + (255,), width=4)
            boxes.append((i, xa, ya, xb, yb, col, lab))
    im = Image.alpha_composite(im, ov)
    dr = ImageDraw.Draw(im)
    placed = []
    flab = font(max(16, int(scale * 2.0)), True)
    for (i, xa, ya, xb, yb, col, lab) in boxes:
        if labels and lab:
            tw_ = dr.textlength(lab, font=flab)
            dr.rectangle([xa, yb, xa + tw_ + 8, yb + flab.size + 6], fill=(0, 0, 0, 215))
            dr.text((xa + 4, yb + 1), lab, font=flab, fill=(255, 255, 255, 255))
    for (i, xa, ya, xb, yb, col, lab) in boxes:
        rad = int(scale * 2.2) + 8
        cx, cy = xa, ya
        for _ in range(12):
            if all(math.hypot(cx - px, cy - py) > rad * 1.6 for px, py in placed):
                break
            cx += rad * 1.2
            if cx > xb + rad:
                cx = xa
                cy -= rad * 1.2
        placed.append((cx, cy))
        dr.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=col + (255,), outline=(255, 255, 255, 255), width=3)
        t = str(i + 1)
        w = dr.textlength(t, font=fn)
        dr.text((cx - w / 2, cy - fn.size * 0.62), t, font=fn, fill=(255, 255, 255, 255))
    # legend
    W = max(im.size[0], minw)
    fb, fr = font(26, True), font(24)
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    rows = []
    tw = W - 120
    for i, it in enumerate(items):
        head = f'{it["name"]}'
        if it.get("des"):
            head += "  [" + ", ".join(it["des"][:6]) + (" …" if len(it["des"]) > 6 else "") + "]"
        lines = wrap(tmp, it["fn"], fr, tw)
        rows.append((head, lines))
    H = 90 + sum(40 + 30 * len(l) + 12 for _, l in rows) + 20
    out = Image.new("RGB", (W, im.size[1] + H), (250, 250, 250))
    out.paste(im.convert("RGB"), ((W - im.size[0]) // 2, 0))
    od2 = ImageDraw.Draw(out)
    y = im.size[1] + 14
    od2.text((30, y), title, font=font(34, True), fill=(20, 20, 20))
    y += 64
    for i, (it, (head, lines)) in enumerate(zip(items, rows)):
        col = it["_col"]
        od2.ellipse([30, y + 2, 30 + 38, y + 40], fill=col)
        t = str(i + 1)
        w = od2.textlength(t, font=fb)
        od2.text((49 - w / 2, y + 5), t, font=fb, fill=(255, 255, 255))
        od2.text((84, y + 4), head, font=fb, fill=(20, 20, 20))
        y += 44
        for ln in lines:
            od2.text((84, y), ln, font=fr, fill=(60, 60, 60))
            y += 30
        y += 12
    out.save(os.path.join(OUT, fname), optimize=True)
    print("saved", fname, out.size)


def full(scale=6):
    return (X0, Y0, X1, Y1)


# ---------------------------------------------------------------- net groups
SPI = {"SPI_MISO", "SPI_MOSI", "SPI_SCK", "SPI_CS", "LORA_SS", "LORA_BUSY", "LORA_RST", "DIO1", "TXEN", "RXEN", "DRDY", "ADC_RST", "PDOWN"}
I2C = {"SDA", "SCL"} | {f"SDA{i}" for i in range(8)} | {f"SCL{i}" for i in range(8)} | {f"EN{i}" for i in range(8)}
ORANGE, CYAN, MAG = (255, 140, 0, 255), (0, 230, 255, 255), (255, 70, 220, 255)


def tc_bottom(t):
    if t["w"] >= 3:
        return ORANGE
    if t["net"] in SPI:
        return CYAN
    if t["net"] in I2C:
        return MAG
    return None


# ---------------------------------------------------------------- FIG 1: top
figure("fig01_top_layer.png", "top", full(), [
    dict(name="Tembaga & pad Top (merah)", fn="Jalur, pad SMD, dan pour GND sisi atas. Semua IC, R/C/L, dioda, MOSFET dan modul dipasang di sisi ini.", color=(255, 0, 0)),
    dict(name="Tembaga Bottom (biru, terlihat di sela merah)", fn="Jalur dan pour GND sisi bawah.", color=(0, 0, 255)),
    dict(name="Via (titik abu-abu)", fn="400 via (pad 0,62 mm / bor 0,31 mm): pindah layer dan menyambung pour GND atas–bawah.", color=(120, 120, 120)),
    dict(name="Silk (garis kuning)", fn="Outline footprint komponen.", color=(255, 204, 0)),
    dict(name="Outline papan (garis ungu)", fn="Papan bulat Ø84,0 mm, menyesuaikan casing aluminium (footprint U50).", color=(255, 0, 255)),
], "Gambar 1. Main Board GLD V4 – Top layer", scale=6)

# ---------------------------------------------------------------- FIG 2: bottom
figure("fig02_bottom_layer.png", "bottom", full(), [
    dict(name="Jalur daya lebar (cincin kiri)", fn="Jalur 0,76–1,27 mm pembawa 24V+/24V− dan VBAT_IN dari input VIN ke sisi kiri papan.", rects=[(4075, 3685, 4110, 3890)]),
    dict(name="Jalur daya lebar (cincin bawah)", fn="Jalur 0,76–1,27 mm di sekitar konektor VIN (J1) menuju rangkaian proteksi dan konverter.", rects=[(4138, 3875, 4285, 3915)]),
    dict(name="Jalur daya lebar (sisi kanan)", fn="Jalur 0,76–1,27 mm pembawa +24V/5VBUCK di sisi kanan.", rects=[(4298, 3660, 4340, 3785)]),
    dict(name="Pad through-hole", fn="Hanya konektor THT yang menembus ke Bottom: J1 (VIN), J2 (ALARM), J3 (FAN), J4 (RS485), USB1.", des=["J1", "J2", "J3", "J4", "USB1"], each=True),
], "Gambar 2. Main Board GLD V4 – Bottom layer (biru di depan)", scale=6)

# ---------------------------------------------------------------- FIG 3: dimensi
def dims_fig():
    rr, img = base("top", 6, texts=False, pourcol=(40, 160, 90, 55))
    im = img.convert("RGBA")
    dr = ImageDraw.Draw(im)
    f1 = font(34, True)
    cx, cy = rr.tx(CX, CY)
    rad = RAD * 6
    dr.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=(255, 255, 0, 255), width=6)
    # pitch circle of casing holes
    pr_ = 126 * 6
    for a in range(0, 360, 6):
        a0, a1 = math.radians(a), math.radians(a + 3)
        dr.line([(cx + pr_ * math.cos(a0), cy + pr_ * math.sin(a0)), (cx + pr_ * math.cos(a1), cy + pr_ * math.sin(a1))], fill=(0, 230, 255, 255), width=4)
    # diameter dimension
    y = cy + 0
    dr.line([(cx - rad, y), (cx + rad, y)], fill=(255, 255, 0, 255), width=5)
    for sx in (-1, 1):
        x = cx + sx * rad
        dr.polygon([(x, y), (x - sx * 26, y - 12), (x - sx * 26, y + 12)], fill=(255, 255, 0, 255))
    t = "Ø 84,0 mm"
    w = dr.textlength(t, font=f1)
    dr.rectangle([cx - w / 2 - 10, y - 66, cx + w / 2 + 10, y - 14], fill=(0, 0, 0, 200))
    dr.text((cx - w / 2, y - 62), t, font=f1, fill=(255, 255, 0, 255))
    t2 = "Ø 64,0 mm (pitch lubang casing)"
    w2 = dr.textlength(t2, font=font(28, True))
    dr.rectangle([cx - w2 / 2 - 10, cy + 126 * 6 * 0.38 - 4, cx + w2 / 2 + 10, cy + 126 * 6 * 0.38 + 44], fill=(0, 0, 0, 200))
    dr.text((cx - w2 / 2, cy + 126 * 6 * 0.38), t2, font=font(28, True), fill=(0, 230, 255, 255))
    # center cross
    dr.line([(cx - 20, cy), (cx + 20, cy)], fill=(255, 255, 255, 255), width=3)
    dr.line([(cx, cy - 20), (cx, cy + 20)], fill=(255, 255, 255, 255), width=3)
    return im


def mount_data():
    P = r.P["holes"]
    return P


# ---------------------------------------------------------------- FIG 4 / 5 :
HOLES = {"M1": (4363.138, 3714.756, 5.9055), "M2": (4061.957, 3732.079, 5.9055), "M3": (4132.823, 3893.89, 5.9055), "M4": (4272.587, 3618.3, 5.9055),
         "C1": (4215.5, 3636.016, 6.2992), "C2": (4341.484, 3762, 6.2992), "C3": (4215.5, 3887.984, 6.2992), "C4": (4089.516, 3762, 6.2992)}
hitems = []
for i, (k, (x, y, rd)) in enumerate(HOLES.items()):
    grp = k.startswith("C")
    hitems.append(dict(name=f"{k} – lubang mounting Ø{rd*2*0.254:.1f} mm" + (" (pola casing)" if grp else " (tambahan, dekat tepi)"),
                       fn=(f"Posisi dari pusat papan: X {(x-CX)*0.254:+.1f} mm, Y {(CY-y)*0.254:+.1f} mm. " +
                           ("Satu dari 4 lubang pola casing aluminium (footprint U50, setiap 90° pada lingkaran Ø64 mm); tempat baut pengikat papan ke casing." if grp else
                            "Lubang pengikat tambahan Ø3,0 mm di dekat tepi (r ≈ 39 mm dari pusat), untuk standoff/baut penahan papan agar tidak melentur.")),
                       rects=[(x - rd - 6, y - rd - 6, x + rd + 6, y + rd + 6)], color=PAL[i % len(PAL)]))

# dims figure saved with legend by custom path
im = dims_fig()
W = 2106
rows = [("Outline papan lingkaran Ø84,0 mm", "Diukur dari CIRCLE pada layer BoardOutline (jari-jari 165,35 satuan EasyEDA = 42,0 mm), pusat di koordinat (4215,5 ; 3762,0). Bentuk bulat menyesuaikan casing aluminium."),
        ("Pitch circle Ø64,0 mm", "Lingkaran putus-putus cyan: tempat 4 lubang casing (C1–C4) pada sudut 0°/90°/180°/270°."),
        ("Lapisan", "2 layer tembaga (Top + Bottom), semua komponen SMD di Top; konektor THT menembus ke Bottom. Satuan koordinat EasyEDA 10 mil = 0,254 mm."),
        ("Aturan desain (DRC)", "Clearance 0,15 mm (6 mil); jalur default 0,25 mm; via bor 0,31 mm / pad 0,62 mm.")]
fb, fr = font(26, True), font(24)
tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
wr = [(h, wrap(tmp, t, fr, W - 120)) for h, t in rows]
H = 90 + sum(40 + 30 * len(l) + 12 for _, l in wr) + 20
out = Image.new("RGB", (W, im.size[1] + H), (250, 250, 250))
out.paste(im.convert("RGB"), (0, 0))
od = ImageDraw.Draw(out)
y = im.size[1] + 14
od.text((30, y), "Gambar 3. Dimensi papan (Main Board GLD V4)", font=font(34, True), fill=(20, 20, 20))
y += 64
for h, ls in wr:
    od.text((30, y + 4), "• " + h, font=fb, fill=(20, 20, 20))
    y += 44
    for ln in ls:
        od.text((60, y), ln, font=fr, fill=(60, 60, 60))
        y += 30
    y += 12
out.save(os.path.join(OUT, "fig03_dimensi_papan.png"), optimize=True)
print("saved fig03")

# mounting
figure("fig04_mounting_holes.png", "top", full(), hitems, "Gambar 4. Lubang mounting (8 lubang)", scale=6, texts=False)

# ---------------------------------------------------------------- FIG 5 zone map
Z = [
    dict(name="Input 24 V & proteksi", fn="Daya masuk dari konektor VIN (J1) lewat fuse PTC F1, TVS D1 dan filter common-mode L1 sebelum menjadi rel +24V; D7 meng-OR-kan input 5V eksternal.", rects=[(4175, 3880, 4300, 3931)]),
    dict(name="Buck 24 V → 5 V", fn="LMR51450 (U36) + induktor U40 menurunkan +24V menjadi 5VBUCK; Q3 (P-MOSFET) + D2 zener sebagai saklar/proteksi input, L4 ferrite dan C72/C73 sebagai filter.", rects=[(4318, 3775, 4390, 3862)]),
    dict(name="Boost baterai → +24 V", fn="TPS61175 (U1) + L5 + D12/D13 menaikkan tegangan baterai (VBAT) ke rel +24V.", rects=[(4194, 3798, 4285, 3850)]),
    dict(name="Boost baterai → 5 V + mux daya", fn="TPS61088 (U41) + L2 menghasilkan 5VBOOST; TPS2116 (U13) memilih sumber 5VBUCK/5VBOOST menjadi rel +5V; D3/D10 membentuk OR-diode untuk rel always-on.", rects=[(4064, 3812, 4162, 3870)]),
    dict(name="Proteksi baterai & load switch", fn="Q2 (AO4407, P-MOSFET) mencegah polaritas terbalik baterai; U14 (TPS22964C) menyambung VBAT_IN ke VBAT ketika ENA aktif.", rects=[(4136, 3876, 4172, 3915)]),
    dict(name="Buck +5 V → 3,3 V", fn="TPS62162 (U43) + L3 menghasilkan VCC 3,3 V untuk ESP32-S3, LoRa, dan sensor digital.", rects=[(4255, 3826, 4298, 3850)]),
    dict(name="Watchdog / power-latch always-on", fn="LDO 3V3AON (U42) selalu hidup menyuplai TPL5010 (U46), flip-flop U51, buffer U15 dan supervisor U16 yang menghidupkan / mematikan rel daya utama.", des=["U42", "U46", "U51", "U15", "U16"], each=True),
    dict(name="MCU ESP32-S3", fn="Modul ESP32-S3-WROOM-1U-N16R8: pemroses utama (SPI ke LoRa & ADC, I²C ke sensor, GPIO alarm/kipas); SW1 tombol CFG dan LED1 indikator.", des=["U49", "SW1", "LED1"], each=True),
    dict(name="USB programming", fn="Micro-USB (USB1) + CH340C (U48) + transistor auto-reset (Q1) + ESD (D4, D5, D11): flash firmware dan serial monitor.", des=["USB1", "U48", "Q1", "D4", "D5", "D11"], each=True),
    dict(name="LoRa + antena", fn="Modul E22-900MM22S (SX1262) dan konektor U.FL (G$1) untuk antena eksternal; jalur STAR ke Cluster Head.", des=["U45", "G$1"], each=True),
    dict(name="ADC presisi + referensi", fn="ADS1256 24-bit (U35) membaca 8 kanal analog; kristal 8 MHz (U39), referensi 2,5 V ADR03 (U38), buffer OPA320 (U2 untuk VREF, U3 untuk VMID).", des=["U35", "U39", "U38", "U2", "U3"], each=True),
    dict(name="Mux I²C & ekspander EN", fn="TCA9548A (U33) memisahkan 8 kanal I²C per sensor; PCF8574 (U12) mengendalikan sinyal EN0–7 tiap port.", des=["U33", "U12"], each=True),
    dict(name="Port sensor H1–H8", fn="8 header 2×4 pitch 1,27 mm: +5V, GND, VMID, EN, SDA, SCL, AIN untuk modul sensor.", des=["H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8"], each=True),
    dict(name="RS485", fn="Transceiver THVD1410 (U47) + TVS SM712 (D6) + konektor J4 (A/B).", des=["J4", "U47", "D6"], each=True),
    dict(name="Driver alarm", fn="Konektor J2 + MOSFET Q4 + dioda flyback D8: menyalakan sirene/relay 24 V dari GPIO ALARM.", des=["J2", "Q4", "D8"], each=True),
    dict(name="Driver kipas", fn="Konektor J3 + MOSFET Q5 + dioda flyback D9 untuk kipas 5 V (DC_FAN).", des=["J3", "Q5", "D9"], each=True),
    dict(name="Sensor suhu/RH on-board", fn="SHT40 (U44) mengukur suhu & kelembapan di dalam casing lewat I²C.", des=["U44"], each=True),
]
figure("fig05_zona_penempatan.png", "top", full(), Z, "Gambar 5. Peta zona penempatan komponen (Top layer)", scale=6, texts=False)

# ---------------------------------------------------------------- FIG 6 connectors
CON = [
    dict(name="J1 – VIN (2×3 pin 2,54 mm)", fn="Input daya utama: 24V+, 24V−, 5VEXT (5 V eksternal), GND dan BAT (baterai, lewat F2). Konektor THT besar di tepi bawah.", des=["J1"]),
    dict(name="J2 – ALARM (1×2)", fn="Keluaran ke sirene/beacon 24 V: pin1 = +24V, pin2 = sisi switch Q4 (dikendalikan GPIO ALARM).", des=["J2"]),
    dict(name="J3 – FAN (1×2)", fn="Keluaran kipas 5 V: pin1 = +5V, pin2 = sisi switch Q5 (DC_FAN).", des=["J3"]),
    dict(name="J4 – RS485 (1×2)", fn="Bus RS485 A/B lewat transceiver THVD1410 (U47), terlindungi TVS D6 (SM712).", des=["J4"]),
    dict(name="USB1 – Micro-USB", fn="Flash firmware & serial debug (via CH340C); VBUS juga dapat menyuplai rel always-on lewat D10.", des=["USB1"]),
    dict(name="G$1 – U.FL (ANT)", fn="Konektor antena LoRa eksternal ke modul E22-900MM22S.", des=["G$1"]),
    dict(name="H1–H8 – Port sensor (2×4, 1,27 mm SMD)", fn="Pin: 1 GND, 2 +5V, 3 AINx, 4 SCLx, 5 GND, 6 SDAx, 7 ENx, 8 VMID. Masing-masing satu modul sensor (AIN0–7, kanal I²C 0–7).", des=["H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8"], each=True),
]
figure("fig06_konektor.png", "top", full(), CON, "Gambar 6. Konektor pada Main Board", scale=6, texts=False)


# ---------------------------------------------------------------- FIG 7 power
def tc_power(t):
    if t["w"] >= 3:
        return (255, 140, 0, 255)
    return None


PWR = [
    dict(name="Input & proteksi 24 V", fn="J1, F1 (PTC), D1 (TVS SMBJ33A), L1 (CMC 300 Ω), L4 (ferrite): jalur arus masuk utama berlebar 1,27 mm.", rects=[(4175, 3880, 4300, 3931)]),
    dict(name="Buck 24 V → 5 V", fn="U36, U40 (4,7 µH), Q3, C72/C73 33 µF: konversi daya terbesar; loop arus switching dibuat pendek.", rects=[(4318, 3775, 4390, 3862)]),
    dict(name="Boost +24 V (dari baterai)", fn="U1 + L5 10 µH + D12 SK36 + D13: arus switching tinggi dari baterai.", rects=[(4194, 3798, 4285, 3850)]),
    dict(name="Boost 5 V + mux", fn="U41 + L2 2,2 µH + U13 TPS2116: 5VBOOST dan pemilihan sumber 5V.", rects=[(4064, 3812, 4162, 3870)]),
    dict(name="Proteksi baterai", fn="F2, Q2 (AO4407), U14 (TPS22964C) membawa arus baterai (VBAT_IN → VBAT).", rects=[(4136, 3876, 4172, 3915)]),
]
figure("fig07_area_daya.png", "top", full(), PWR, "Gambar 7. Area high-current / power", scale=6, texts=False, dim=True, tcolor=tc_power)

# ---------------------------------------------------------------- FIG 8 sensor interface
SEN = [
    dict(name="Port sensor H1–H8", fn="Delapan header 8-pin: +5V, GND, VMID (bias tengah), ENx (enable sensor dari PCF8574), SDAx/SCLx (I²C per kanal TCA9548A), AINx (keluaran analog ke ADS1256).", des=["H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8"], each=True),
    dict(name="TCA9548A (U33) – mux I²C", fn="Memecah bus I²C ESP32 menjadi 8 kanal terisolasi (SDA0–7/SCL0–7) agar sensor beralamat sama dapat dipakai bersamaan.", des=["U33"]),
    dict(name="PCF8574 (U12) – ekspander EN", fn="Menyediakan sinyal EN0–EN7 untuk menghidupkan/mematikan tiap sensor.", des=["U12"]),
    dict(name="ADS1256 (U35) + kristal 8 MHz (U39)", fn="ADC 24-bit 8 kanal, SPI ke ESP32 (DRDY/PDOWN/ADC_RST); clock dari kristal 8 MHz dengan C45/C57 20 pF.", des=["U35", "U39"], each=True),
    dict(name="Referensi 2,5 V (U38) & buffer OPA320 (U2)", fn="ADR03 → VREF; U2 membufer VREF ke pin REF ADS1256 (R74 22 Ω, C51/C56 sebagai filter).", des=["U38", "U2"], each=True),
    dict(name="Buffer VMID (U3)", fn="OPA320 follower + R28/R29 menghasilkan VMID (bias tengah analog) untuk modul sensor; filter C29/C38, R11 49,9 Ω.", des=["U3"]),
    dict(name="Suplai analog +5VA", fn="L6 (ferrite 60 Ω) memisahkan +5V menjadi +5VA bersih untuk ADC, referensi dan op-amp.", des=["L6"]),
]
figure("fig08_sensor_interface.png", "top", full(), SEN, "Gambar 8. Sensor interface", scale=6, texts=False)


# ---------------------------------------------------------------- FIG 9 grounding
GND_ITEMS = [
    dict(name="Pour GND (area solid merah/biru)", fn="Satu bidang tembaga GND di Top (merah) dan Bottom (biru) yang mengisi seluruh area bebas hingga tepi papan: jalur balik arus pendek dan perisai EMI untuk sirkuit LoRa/ADC.", color=(255, 0, 0)),
    dict(name="Via GND – stitching (titik abu-abu)", fn="176 dari 400 via bernet GND menyambung pour atas dan bawah, tersebar di antara komponen sehingga impedansi return rendah.", color=(120, 120, 120)),
    dict(name="24V− → GND lewat filter L1", fn="Return input 24 V (24V−) bergabung ke GND sistem lewat belitan negatif choke common-mode L1; TVS D1 menjepit di sisi 24V−.", rects=[(4278, 3878, 4304, 3904)]),
    dict(name="Tidak ada split AGND/DGND", fn="Hanya satu net GND. Area analog (ADS1256, U38, OPA320) dipisah dengan suplai +5VA via ferrite L6, bukan dengan split ground.", rects=[(4222, 3695, 4320, 3800)]),
]
figure("fig09_grounding_top.png", "top", full(), GND_ITEMS, "Gambar 9a. Grounding – Top layer", scale=6)
figure("fig09_grounding_bottom.png", "bottom", full(), GND_ITEMS[:2], "Gambar 9b. Grounding – Bottom layer", scale=6)


# ======================================================= DETAIL ZOOMS (per blok)
def item(name, fn, des, each=True, **k):
    return dict(name=name, fn=fn, des=des, each=each, **k)


figure("fig10_detail_input_proteksi.png", "top", (4130, 3865, 4310, 3934), [
    item("J1 – VIN", "Konektor masuk 2×3 pin 2,54 mm: 24V+, 24V−, 5VEXT, GND, BAT. Satu-satunya jalur daya dari luar selain USB.", ["J1"]),
    item("F1 – PTC fuse (MINISMDC260F)", "Sekering resettable seri pada 24V+; membatasi arus saat hubung singkat.", ["F1"]),
    item("D1 – TVS SMBJ33A", "Penjepit lonjakan tegangan (surge/ESD) 33 V antara input 24V+ dan 24V−.", ["D1"]),
    item("L1 – Common-mode choke ACM7060 (300 Ω)", "Filter noise common-mode pada jalur 24 V dan return; return 24V− menyatu ke GND lewat belitan ini.", ["L1"]),
    item("D7 – Schottky SS54", "Dioda OR untuk input 5V eksternal (5VEXT) ke rel +5V; mencegah arus balik.", ["D7"]),
    item("F2 – PTC fuse baterai", "Sekering resettable pada jalur baterai (pin BAT J1).", ["F2"]),
    item("Q2 – P-MOSFET AO4407", "Proteksi polaritas terbalik baterai; output VBAT_IN.", ["Q2"]),
    item("U14 – Load switch TPS22964C", "Menyambung VBAT_IN ke VBAT hanya ketika ENA aktif (kendali power-latch), sehingga baterai terputus saat sistem sleep.", ["U14"]),
], "Gambar 10. Detail – input daya & proteksi", scale=12, labels=True, texts=False)

figure("fig11_detail_buck_24v.png", "top", (4300, 3770, 4392, 3880), [
    item("U36 – Buck LMR51450", "Regulator buck sinkron: mengubah rel +24V (via Q3) menjadi 5VBUCK; pin PG24 (power-good) dikirim ke ESP32-S3.", ["U36"]),
    item("U40 – Induktor 4,7 µH", "Induktor daya buck 24 V → 5 V (jalur arus tinggi).", ["U40"]),
    item("Q3 – P-MOSFET SI7465DP", "Saklar high-side di input buck; gate dijepit D2 agar Vgs aman.", ["Q3"]),
    item("D2 – Zener 12 V", "Menjepit Vgs Q3 maksimum 12 V.", ["D2"]),
    item("L4 – Ferrite 100 Ω", "Filter manik-manik pada jalur +24V menuju beban switching.", ["L4"]),
    item("C72, C73 – 33 µF", "Kapasitor bulk input/output regulator.", ["C72", "C73"]),
], "Gambar 11. Detail – konversi 24 V → 5 V", scale=14, labels=True, texts=False)

figure("fig12_detail_boost24_3v3_watchdog.png", "top", (4195, 3795, 4300, 3890), [
    item("U1 – Boost TPS61175", "Boost converter VBAT → +24V (lewat D12/D13).", ["U1"]),
    item("L5 – Induktor 10 µH", "Induktor boost +24V (jalur arus tinggi).", ["L5"]),
    item("D12, D13 – Schottky SK36 / SS54", "Dioda penyearah dan OR untuk rel +24V.", ["D12", "D13"]),
    item("U43 – Buck TPS62162", "+5V → VCC 3,3 V (rel utama digital).", ["U43"]),
    item("L3 – Induktor 2,2 µH", "Induktor buck 3,3 V.", ["L3"]),
    item("U46 – TPL5010 (timer watchdog)", "Nano-timer: membangunkan sistem secara periodik dan sebagai watchdog (DONE/WAKE).", ["U46"]),
    item("U51 – Flip-flop SN74AUP1G74", "Latch ENA yang menjaga rel daya tetap hidup sampai MCU selesai.", ["U51"]),
    item("U15 – Buffer SN74LVC1G06", "Open-drain inverter untuk jalur WAKE.", ["U15"]),
    item("U16 – Supervisor TPS3839K33", "Memantau 3V3AON dan menghasilkan PRE (reset/preset).", ["U16"]),
], "Gambar 12. Detail – boost +24 V, buck 3,3 V, dan watchdog", scale=14, labels=True, texts=False)

figure("fig13_detail_boost5v_mux.png", "top", (4060, 3805, 4182, 3885), [
    item("U41 – Boost TPS61088", "Boost VBAT → 5VBOOST (diaktifkan oleh ENA).", ["U41"]),
    item("L2 – Induktor 2,2 µH", "Induktor boost 5 V (jalur arus tinggi).", ["L2"]),
    item("U13 – Power mux TPS2116", "Memilih sumber 5VBUCK atau 5VBOOST menjadi rel +5V; status ST_P dikirim ke ESP32-S3.", ["U13"]),
    item("D3, D10 – BAT54C", "Dual Schottky membentuk OR dari VBAT_IN / 5VBUCK / 5VEXT / VBUS ke input LDO always-on.", ["D3", "D10"]),
    item("U42 – LDO TPS7A0233", "Menghasilkan 3V3AON yang selalu hidup untuk blok watchdog dan latch.", ["U42"]),
], "Gambar 13. Detail – boost 5 V, power-mux, dan LDO always-on", scale=14, labels=True, texts=False)

figure("fig14_detail_mcu_usb.png", "top", (4078, 3625, 4250, 3815), [
    item("U49 – ESP32-S3-WROOM-1U-N16R8", "Modul MCU: Wi-Fi/BLE, flash 16 MB, PSRAM 8 MB; antena eksternal via U.FL pada modul. Menjalankan firmware GLD (SPI ke E22/ADS1256, I²C ke sensor).", ["U49"]),
    item("SW1 – Tombol CFG", "Tombol konfigurasi (CFG) ke GPIO ESP32-S3.", ["SW1"]),
    item("LED1 – LED status", "LED merah indikator status (dikendalikan GPIO LED).", ["LED1"]),
    item("USB1 – Micro-USB", "Port USB untuk flash dan serial debug; VBUS ke rel always-on lewat D10.", ["USB1"]),
    item("U48 – CH340C", "Konverter USB-UART untuk programming dan serial monitor.", ["U48"]),
    item("Q1 – UMH3N", "Dual transistor auto-reset (DTR/RTS → EN dan IO0) agar upload firmware otomatis.", ["Q1"]),
    item("D4, D5, D11 – ESD LESD5D5.0", "Proteksi ESD pada D+, D− dan VBUS port USB.", ["D4", "D5", "D11"]),
], "Gambar 14. Detail – MCU ESP32-S3 dan USB programming", scale=9, labels=True, texts=False)

figure("fig15_detail_lora_antena_fan.png", "top", (4140, 3593, 4262, 3700), [
    item("U45 – LoRa E22-900MM22S (SX1262)", "Modul radio LoRa 22 dBm, antarmuka SPI + BUSY/DIO1/TXEN/RXEN; menghubungkan GLD ke Cluster Head (STAR).", ["U45"]),
    item("G$1 – Konektor U.FL (ANT)", "Titik sambung kabel antena LoRa eksternal.", ["G$1"]),
    item("J3 – FAN", "Konektor kipas 5 V (pin1 +5V, pin2 ke drain Q5).", ["J3"]),
    item("Q5 – MOSFET AO3400A", "Switch low-side kipas, gate dari DC_FAN lewat R42 100 Ω (R43 100 kΩ pull-down).", ["Q5", "R42", "R43"]),
    item("D9 – Dioda flyback SS14", "Menyerap tegangan induktif kipas saat Q5 mati.", ["D9"]),
], "Gambar 15. Detail – LoRa, antena, dan driver kipas", scale=12, labels=True, texts=False)

figure("fig16_detail_adc_sensor.png", "top", (4203, 3655, 4345, 3800), [
    item("U33 – TCA9548A", "Multiplexer I²C 8 kanal (SDA0–7/SCL0–7) ke port sensor.", ["U33"]),
    item("U12 – PCF8574", "Ekspander I²C: menghasilkan EN0–EN7 untuk menyalakan sensor.", ["U12"]),
    item("U35 – ADS1256", "ADC 24-bit 8 kanal (AI0–7) dengan SPI; membaca keluaran analog sensor.", ["U35"]),
    item("U39 – Kristal 8 MHz", "Sumber clock ADS1256 (C45/C57 20 pF).", ["U39"]),
    item("U38 – ADR03 (2,5 V)", "Referensi tegangan presisi untuk ADC.", ["U38"]),
    item("U2 – OPA320 (buffer VREF)", "Op-amp buffer VREF ke pin REF ADS1256 (R74, C51/C56).", ["U2"]),
    item("R65–R72 (49,9 Ω)", "Resistor seri input analog AIN0–7 (anti-aliasing bersama C41–C50 100 nF).", ["R65", "R66", "R67", "R68", "R69", "R70", "R71", "R72"], each=False),
    item("C41–C51 (100 nF)", "Kapasitor filter RC pada input AIN0–7 dan decoupling referensi.", ["C41", "C42", "C43", "C44", "C47", "C48", "C49", "C50", "C51"], each=False),
    item("U44 – SHT40", "Sensor suhu & kelembapan I²C di dalam casing.", ["U44"]),
], "Gambar 16. Detail – akuisisi sensor (ADC, mux I²C, referensi)", scale=12, labels=True, texts=False)

figure("fig17_detail_rs485.png", "top", (4045, 3740, 4125, 3815), [
    item("J4 – RS485", "Konektor 1×2: B (pin1) dan A (pin2).", ["J4"]),
    item("U47 – THVD1410", "Transceiver RS485 3,3 V; arah DIR dikendalikan ESP32-S3 (RX2/TX2).", ["U47"]),
    item("D6 – TVS SM712", "Proteksi surge/ESD pada pasangan A/B RS485.", ["D6"]),
], "Gambar 17. Detail – antarmuka RS485", scale=16, labels=True, texts=False)

figure("fig18_detail_alarm.png", "top", (4325, 3722, 4392, 3780), [
    item("J2 – ALARM", "Konektor keluaran 24 V: pin1 +24V, pin2 sisi switch Q4.", ["J2"]),
    item("Q4 – MOSFET AO3400A", "Switch low-side alarm, gate dari GPIO ALARM lewat R94 100 Ω (R41 100 kΩ pull-down).", ["Q4", "R94", "R41"]),
    item("D8 – Dioda flyback SS14", "Menyerap tegangan induktif beban alarm saat Q4 mati.", ["D8"]),
], "Gambar 18. Detail – driver alarm", scale=18, labels=True, texts=False)
