import json, re, math, zipfile
from PIL import Image, ImageDraw, ImageFont

from pathlib import Path
ZIP = str(Path(__file__).resolve().parents[2] / "GLD ATEX.zip")
NAME = "1-PCB_PCB_MotherBoardGLDVer2.json"
X0, Y0, X1, Y1 = 4040, 3590, 4391, 3934  # board bbox + margin (EasyEDA px = 10 mil)
MM = 0.254
CX, CY, RAD = 4215.5, 3762.0, 165.354  # mm per unit


def load():
    with zipfile.ZipFile(ZIP) as z:
        return json.loads(z.read(NAME).decode("utf8"))


def f(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def parse(d):
    out = dict(tracks=[], vias=[], pads=[], comps=[], holes=[], silk=[], areas=[], silk_tracks=[])
    for s in d["shape"]:
        k = s.split("~")[0]
        p = s.split("~")
        if k == "TRACK":
            pts = [f(v) for v in p[4].split()]
            out["tracks"].append(dict(w=f(p[1]), layer=int(p[2]), net=p[3], pts=list(zip(pts[0::2], pts[1::2]))))
        elif k == "VIA":
            out["vias"].append(dict(x=f(p[1]), y=f(p[2]), d=f(p[3]), net=p[4], h=f(p[5]) * 2 if False else f(p[5])))
        elif k == "HOLE":
            out["holes"].append(dict(x=f(p[1]), y=f(p[2]), r=f(p[3])))
        elif k == "COPPERAREA":
            fills = []
            m = re.search(r"(\[\[.*\]\])", s)
            if m:
                fills = json.loads(m.group(1))
            out["areas"].append(dict(layer=int(p[2]), net=p[3], fills=fills))
        elif k == "LIB":
            parts = s.split("#@$")
            h = parts[0].split("~")
            meta = h[3]
            pk = re.search(r"package`([^`]*)`", meta)
            c = dict(x=f(h[1]), y=f(h[2]), pkg=pk.group(1) if pk else "", des="", val="", pads=[], texts=[], tracks=[], layer=1)
            for q in parts[1:]:
                t = q.split("~")
                if t[0] == "HOLE":
                    out["holes"].append(dict(x=f(t[1]), y=f(t[2]), r=f(t[3])))
                if t[0] == "TEXT" and t[1] == "P":
                    c["des"] = t[10]
                    c["texts"].append(q)
                elif t[0] == "TEXT" and t[1] == "N":
                    c["val"] = t[10]
                elif t[0] == "PAD":
                    c["pads"].append(dict(shape=t[1], x=f(t[2]), y=f(t[3]), w=f(t[4]), h=f(t[5]), layer=int(t[6]), net=t[7], num=t[8], hole=f(t[9]), rot=f(t[11]) if len(t) > 11 and t[11] else 0.0))
                elif t[0] == "TRACK" and t[2] == "3":
                    pts = [f(v) for v in t[4].split()]
                    c["tracks"].append(list(zip(pts[0::2], pts[1::2])))
            out["comps"].append(c)
    return out


class R:
    def __init__(self, d, scale=8, mirror=False):
        self.d = d
        self.P = parse(d)
        self.s = scale
        self.mirror = mirror

    def tx(self, x, y):
        sx = (x - X0) * self.s
        if self.mirror:
            sx = (X1 - x) * self.s
        return (sx, (y - Y0) * self.s)

    def render(self, side="top", show_silk=True, show_names=False, dim=False, texts=True, pour=True, tcolor=None, vcolor=None, pourcol=None, padcol=None):
        W = int((X1 - X0) * self.s)
        H = int((Y1 - Y0) * self.s)
        img = Image.new("RGBA", (W, H), (22, 26, 24, 255))
        dr = ImageDraw.Draw(img, "RGBA")
        # board outline polygon
        cx, cy = self.tx(CX, CY)
        rr = RAD * self.s
        dr.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(18, 70, 40, 255), outline=(255, 0, 255, 255), width=3)
        L = 1 if side == "top" else 2
        col = (210, 60, 60, 255) if side == "top" else (70, 110, 230, 255)
        other = (70, 110, 230, 90) if side == "top" else (210, 60, 60, 90)
        # copper pour
        for a in self.P["areas"]:
            if pour and a["layer"] == L:
                for fl in a["fills"]:
                    for path in fl:
                        nums = [f(v) for v in re.findall(r"-?\d+\.?\d*", path)]
                        pts = list(zip(nums[0::2], nums[1::2]))
                        if len(pts) > 2:
                            dr.polygon([self.tx(*p) for p in pts], fill=(pourcol if pourcol else (col[0], col[1], col[2], 60)))
        # opposite-layer tracks faint
        if dim:
            for t in self.P["tracks"]:
                if t["layer"] == (2 if L == 1 else 1) and len(t["pts"]) > 1:
                    dr.line([self.tx(*p) for p in t["pts"]], fill=other, width=max(1, int(t["w"] * self.s)))
        order = sorted(self.P["tracks"], key=lambda t: 1 if (tcolor and tcolor(t)) else 0)
        for t in order:
            if t["layer"] == L and len(t["pts"]) > 1:
                pts = [self.tx(*p) for p in t["pts"]]
                w = max(1, int(t["w"] * self.s))
                c2 = (tcolor(t) if tcolor else None) or col
                dr.line(pts, fill=c2, width=w, joint="curve")
                for p in pts:
                    dr.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=c2)
        # pads
        for c in self.P["comps"]:
            for p in c["pads"]:
                if p["layer"] == L or p["layer"] == 11:
                    self._pad(dr, p, padcol(p) if padcol else None)
        for v in self.P["vias"]:
            x, y = self.tx(v["x"], v["y"])
            r = v["d"] / 2 * self.s
            dr.ellipse([x - r, y - r, x + r, y + r], fill=(vcolor(v) if vcolor and vcolor(v) else (190, 190, 190, 255)))
            rh = v["h"] * self.s  # hole radius
            dr.ellipse([x - rh, y - rh, x + rh, y + rh], fill=(20, 20, 20, 255))
        for h in self.P["holes"]:
            x, y = self.tx(h["x"], h["y"])
            r = h["r"] * self.s
            dr.ellipse([x - r, y - r, x + r, y + r], fill=(10, 10, 10, 255), outline=(255, 255, 255, 255), width=2)
        if show_silk and side == "top":
            for c in self.P["comps"]:
                for tr in c["tracks"]:
                    dr.line([self.tx(*p) for p in tr], fill=(255, 220, 80, 255), width=max(1, int(0.6 * self.s * 0.5)))
                if texts:
                    for q in c["texts"]:
                        self._text(dr, q)
        return img

    def _text(self, dr, q):
        m = re.search(r"~(M [^~]*)~", q)
        if not m:
            return
        for seg in m.group(1).split("M ")[1:]:
            nums = [f(v) for v in re.findall(r"-?\d+\.?\d*", seg)]
            pts = list(zip(nums[0::2], nums[1::2]))
            if len(pts) > 1:
                dr.line([self.tx(*p) for p in pts], fill=(255, 235, 120, 255), width=1)

    def _pad(self, dr, p, gold=None):
        x, y = self.tx(p["x"], p["y"])
        w, h = p["w"] * self.s, p["h"] * self.s
        gold = gold or (225, 190, 70, 255)
        if p["shape"] in ("ELLIPSE",):
            dr.ellipse([x - w / 2, y - h / 2, x + w / 2, y + h / 2], fill=gold)
        else:
            a = math.radians(p["rot"])
            if self.mirror:
                a = -a
            pts = []
            for dx, dy in [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]:
                pts.append((x + dx * math.cos(a) - dy * math.sin(a), y + dx * math.sin(a) + dy * math.cos(a)))
            dr.polygon(pts, fill=gold)
        if p["hole"] > 0:
            r = p["hole"] * self.s
            dr.ellipse([x - r, y - r, x + r, y + r], fill=(15, 15, 15, 255))


if __name__ == "__main__":
    d = load()
    r = R(d, 6)
    r.render("top", dim=False).convert("RGB").save(r"C:\WINDOWS\Temp\claude\D--Github-PertaminaGLD\1c0bcc39-dc03-497b-b17a-1f7083169733\scratchpad\top.png")
    r.render("bottom", show_silk=False).convert("RGB").save(r"C:\WINDOWS\Temp\claude\D--Github-PertaminaGLD\1c0bcc39-dc03-497b-b17a-1f7083169733\scratchpad\bottom.png")
    print("ok", len(r.P["comps"]), len(r.P["areas"]), [len(a["fills"]) for a in r.P["areas"]])


def render_native(self, side="top"):
    """Tampilan mirip editor EasyEDA: Top merah, Bottom biru, latar hitam, silk kuning."""
    W = int((X1 - X0) * self.s)
    H = int((Y1 - Y0) * self.s)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    dr = ImageDraw.Draw(img, "RGBA")
    cx, cy = self.tx(CX, CY)
    rr = RAD * self.s
    dr.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(255, 0, 255, 255), width=2)
    COL = {1: (255, 0, 0, 255), 2: (0, 0, 255, 255)}
    front = 1 if side == "top" else 2
    order = [3 - front, front]
    for L in order:
        col = COL[L]
        for a in self.P["areas"]:
            if a["layer"] == L:
                for fl in a["fills"]:
                    for path in fl:
                        nums = [f(v) for v in re.findall(r"-?\d+\.?\d*", path)]
                        pts = list(zip(nums[0::2], nums[1::2]))
                        if len(pts) > 2:
                            dr.polygon([self.tx(*p) for p in pts], fill=col)
        for t in self.P["tracks"]:
            if t["layer"] == L and len(t["pts"]) > 1:
                pts = [self.tx(*p) for p in t["pts"]]
                w = max(1, int(t["w"] * self.s))
                dr.line(pts, fill=col, width=w, joint="curve")
                for p in pts:
                    dr.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=col)
        for c in self.P["comps"]:
            for p in c["pads"]:
                if p["layer"] == L or (p["layer"] == 11 and L == front):
                    self._pad(dr, p, col)
    for v in self.P["vias"]:
        x, y = self.tx(v["x"], v["y"])
        r = v["d"] / 2 * self.s
        dr.ellipse([x - r, y - r, x + r, y + r], fill=(60, 60, 60, 255))
        rh = v["h"] * self.s
        dr.ellipse([x - rh, y - rh, x + rh, y + rh], fill=(0, 0, 0, 255))
    for h in self.P["holes"]:
        x, y = self.tx(h["x"], h["y"])
        r = h["r"] * self.s
        dr.ellipse([x - r, y - r, x + r, y + r], fill=(0, 0, 0, 255), outline=(255, 255, 255, 255), width=2)
    if side == "top":
        for c in self.P["comps"]:
            for tr in c["tracks"]:
                dr.line([self.tx(*p) for p in tr], fill=(255, 204, 0, 255), width=max(1, int(self.s * 0.3)))
    return img


R.render_native = render_native
