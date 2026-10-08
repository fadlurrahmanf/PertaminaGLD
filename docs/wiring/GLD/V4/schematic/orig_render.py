"""Render the ORIGINAL EasyEDA schematic (same look as the editor) from the JSON, plus per-part bounding boxes."""
import re
import zipfile
import json
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
ZIP_PATH = HERE.parent / "GLD ATEX.zip"
SCH_NAME = "1-Schematic_MotherBoardGLDVer2.json"
NUM = re.compile(r"-?\d+\.?\d*")


def _pt(sz):
    sz = (sz or "").strip()
    m = re.match(r"([\d.]+)\s*pt", sz)
    return float(m.group(1)) * 4 / 3 if m else (float(sz) if sz.replace('.', '').isdigit() else 9.3)


def text(x, y, s, fill, anchor="start", size="", rot=0, rx=None, ry=None, family="Arial", weight=""):
    anchor = {"start": "start", "end": "end", "middle": "middle"}.get(anchor, "start")
    tr = ' transform="rotate(%s %s %s)"' % (rot, rx if rx is not None else x, ry if ry is not None else y) if rot else ""
    fw = ' font-weight="%s"' % weight if weight else ""
    return '<text x="%s" y="%s" fill="%s" text-anchor="%s" font-size="%.1f" font-family="%s"%s%s>%s</text>' % (
        x, y, fill, anchor, _pt(size), family, fw, tr, escape(s))


def load():
    with zipfile.ZipFile(ZIP_PATH) as z:
        d = json.loads(z.read(SCH_NAME).decode("utf8"))
    return d["schematics"][0]["dataStr"]["shape"]


def sub_shape(p, box):
    """Render one LIB sub-shape; grow bbox list [x0,y0,x1,y1] with geometry."""
    q = p.split("~")
    k = q[0]

    def grow(x, y):
        x, y = float(x), float(y)
        box[0] = min(box[0], x); box[1] = min(box[1], y); box[2] = max(box[2], x); box[3] = max(box[3], y)

    def fill(f):
        return "none" if f in ("none", "", "transparent") else f

    if k == "R":
        x, y, w, h = map(float, (q[1], q[2], q[5], q[6]))
        grow(x, y); grow(x + w, y + h)
        rx = q[3] or 0
        return '<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="%s" stroke="%s" stroke-width="%s"/>' % (
            x, y, w, h, rx, fill(q[10]), q[7], q[8])
    if k == "E":
        cx, cy, rx, ry = map(float, q[1:5])
        grow(cx - rx, cy - ry); grow(cx + rx, cy + ry)
        return '<ellipse cx="%s" cy="%s" rx="%s" ry="%s" fill="%s" stroke="%s" stroke-width="%s"/>' % (
            cx, cy, rx, ry, fill(q[8]), q[5], q[6])
    if k == "PL":
        n = NUM.findall(q[1])
        for i in range(0, len(n) - 1, 2):
            grow(n[i], n[i + 1])
        pts = " ".join("%s,%s" % (n[i], n[i + 1]) for i in range(0, len(n) - 1, 2))
        return '<polyline points="%s" fill="%s" stroke="%s" stroke-width="%s" stroke-linejoin="round"/>' % (
            pts, fill(q[5]), q[2], q[3])
    if k == "PG":
        n = NUM.findall(q[1])
        for i in range(0, len(n) - 1, 2):
            grow(n[i], n[i + 1])
        pts = " ".join("%s,%s" % (n[i], n[i + 1]) for i in range(0, len(n) - 1, 2))
        return '<polygon points="%s" fill="%s" stroke="%s" stroke-width="%s"/>' % (pts, fill(q[5]), q[2], q[3])
    if k == "A":
        n = NUM.findall(q[1])
        grow(n[0], n[1]); grow(n[-2], n[-1])
        return '<path d="%s" fill="%s" stroke="%s" stroke-width="%s"/>' % (q[1], fill(q[5]), q[3], q[4])
    if k == "PT":
        n = NUM.findall(q[1])
        for i in range(0, len(n) - 1, 2):
            grow(n[i], n[i + 1])
        return '<path d="%s" fill="%s" stroke="%s" stroke-width="%s"/>' % (q[1], fill(q[5]) if len(q) > 5 else "none", q[2], q[3])
    if k == "T":
        if q[13] == "1" and q[12]:
            w = len(q[12]) * _pt(q[7]) * 0.55
            if q[14] == "end":
                grow(float(q[2]) - w, float(q[3]))
            else:
                grow(float(q[2]) + w, float(q[3]))
            grow(q[2], float(q[3]) - _pt(q[7]))
            return text(q[2], q[3], q[12], q[5] or "#000080", q[14], q[7], q[4], family=q[6] or "Arial")
        return ""
    if k == "P":
        segs = p.split("^^")
        h = segs[0].split("~")
        grow(h[4], h[5])
        out = []
        path = segs[2].split("~")
        for m in NUM.findall(path[0])[:2]:
            pass
        n = NUM.findall(path[0])
        if len(n) >= 2:
            grow(n[0], n[1])
            # end of pin line
            grow(float(n[0]) + (float(n[2]) if "h" in path[0] and len(n) > 2 else 0), n[1])
        out.append('<path d="%s" fill="none" stroke="%s" stroke-width="1"/>' % (path[0], path[1] if len(path) > 1 else "#880000"))
        for idx in (3, 4):
            t = segs[idx].split("~")
            if t[0] == "1" and t[4]:
                out.append(text(t[1], t[2], t[4], t[8] if len(t) > 8 and t[8] else "#0000FF", t[5], t[7] if len(t) > 7 else "", t[3]))
        if len(segs) > 6 and segs[6].split("~")[0] == "1":
            out.append('<path d="%s" fill="none" stroke="#880000"/>' % segs[6].split("~")[1])
        if len(segs) > 5 and segs[5].split("~")[0] == "1":
            pass
        return "".join(out)
    return ""


def render():
    shapes = load()
    body, bbox, wires = [], {}, []
    for s in shapes:
        k = s.split("~")[0]
        if k == "LIB":
            parts = s.split("#@$")
            h = parts[0].split("~")
            des = None
            for p in parts[1:]:
                q = p.split("~")
                if q[0] == "T" and q[1] == "P":
                    des = q[12]
            box = [1e9, 1e9, -1e9, -1e9]
            g = []
            for p in parts[1:]:
                q = p.split("~")
                if q[0] == "Pimage":
                    g.append('<image x="%s" y="%s" width="%s" height="%s" href="%s"/>' % (q[6], q[7], q[8], q[9], q[10]))
                    continue
                g.append(sub_shape(p, box))
            body.append('<g data-des="%s">%s</g>' % (escape(des or ""), "".join(g)))
            if des and des != "comment" and box[0] < 1e8:
                bbox[des] = tuple(box)
        elif k == "W":
            q = s.split("~")
            n = NUM.findall(q[1])
            pts = " ".join("%s,%s" % (n[i], n[i + 1]) for i in range(0, len(n) - 1, 2))
            wires.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="%s"/>' % (pts, q[2], q[3]))
        elif k == "J":
            q = s.split("~")
            wires.append('<circle cx="%s" cy="%s" r="%s" fill="%s"/>' % (q[1], q[2], q[3], q[4]))
        elif k == "N":
            q = s.split("~")
            wires.append(text(q[8], q[9], q[5], q[4], q[7], q[11], q[3], q[1], q[2], family="Times New Roman"))
        elif k == "F":
            segs = s.split("^^")
            t = segs[2].split("~")
            sub = []
            if t[6] == "1":
                sub.append(text(t[2], t[3], t[0], t[1], t[5], t[8], t[4], family="Times New Roman"))
            dummy = [1e9, 1e9, -1e9, -1e9]
            for seg in segs[3:]:
                if seg.startswith(("PL", "PG", "E", "R", "A", "PT")):
                    sub.append(sub_shape(seg, dummy))
            wires.append("".join(sub))
        elif k == "O":
            q = s.split("~")
            wires.append('<path d="%s" fill="none" stroke="%s" stroke-width="1.5"/>' % (q[4], q[5]))
    return "".join(body), "".join(wires), bbox


if __name__ == "__main__":
    b, w, bb = render()
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -1149 1632 1149" width="3264" height="2298">'
           '<rect x="0" y="-1149" width="1632" height="1149" fill="#fff"/>%s%s</svg>' % (b, w))
    (HERE / "_original_full.svg").write_text(svg, encoding="utf8")
    print(len(bb), "parts with bbox")
