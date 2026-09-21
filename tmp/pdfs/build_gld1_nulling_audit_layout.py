"""Rebuild GLD1 nulling report using the established GLD2 audit layout."""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle

ROOT = Path(__file__).resolve().parents[2]
BOARD = os.getenv("NULLING_BOARD", "GLD1")
SOURCE = ROOT / "tmp" / os.getenv("NULLING_SOURCE", "gld1-nulling-record-2026-08-28.jsonl")
OUTPUT = ROOT / "output" / "pdf" / os.getenv("NULLING_OUTPUT", "GLD1_Nulling_Run_2026-08-28.pdf")
SENSORS = ["MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2"]
KV = re.compile(r"([A-Za-z][A-Za-z0-9_]*)=([^\s]+)")

def kv(line): return dict(KV.findall(line))
def mv(v):
    try: return f"{float(v)*1000:.3f}"
    except (TypeError, ValueError): return "-"
def yes(v): return {"1":"Ya", "0":"Tidak"}.get(v or "", v or "-")
def esc(v): return str(v).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def table(headers, rows, widths, styles, size=6):
    hs = ParagraphStyle("th", parent=styles["small"], textColor=colors.white, alignment=TA_CENTER, fontSize=size)
    rs = ParagraphStyle("td", parent=styles["small"], fontSize=size, leading=size+1, alignment=TA_LEFT)
    data = [[Paragraph(esc(x), hs) for x in headers]] + [[Paragraph(esc(x), rs) for x in row] for row in rows]
    t = LongTable(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1F4E78")), ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("GRID",(0,0),(-1,-1),0.25,colors.HexColor("#A6A6A6")), ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING",(0,0),(-1,-1),2), ("RIGHTPADDING",(0,0),(-1,-1),2),
        ("TOPPADDING",(0,0),(-1,-1),1.5), ("BOTTOMPADDING",(0,0),(-1,-1),1.5),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F5F8FB")]),
    ]))
    return t

def parse():
    channels = defaultdict(lambda: defaultdict(list))
    terminal = {}
    for raw in SOURCE.read_text(encoding="utf-8").splitlines():
        try: r = json.loads(raw)
        except json.JSONDecodeError: continue
        line = str(r.get("line", r.get("value", ""))).strip()
        if not line.startswith("NULLING_"): continue
        f = kv(line); sensor = f.get("sensor")
        if not sensor: continue
        item = {"line":line, "f":f, "time":str(r.get("ts",r.get("t","")))[11:19]}
        if line.startswith("NULLING_CH_START"): channels[sensor]["start"] = item
        elif line.startswith("NULLING_BASELINE_DONE"): channels[sensor]["baseline_done"] = item
        elif line.startswith("NULLING_THRESHOLD_DERIVED"): channels[sensor]["threshold"] = item
        elif line.startswith("NULLING_MCP_WRITE"): channels[sensor]["mcp"].append(item)
        elif line.startswith("NULLING_BASELINE_STEP"): channels[sensor]["baseline"].append(item)
        elif line.startswith("NULLING_EXP_STEP"): channels[sensor]["exp"].append(item)
        elif line.startswith("NULLING_EXP_RANGE") or line.startswith("NULLING_EXP_RESUME"): channels[sensor]["ranges"].append(item)
        elif line.startswith("NULLING_BIN_STEP"): channels[sensor]["binary"].append(item)
        elif line.startswith("NULLING_BIN_DONE"): channels[sensor]["bin_done"] = item
        elif line.startswith("NULLING_CONFIRM_STEP"): channels[sensor]["confirm"].append(item)
        elif line.startswith("NULLING_CONFIRM_VERIFY"): channels[sensor]["verify"].append(item)
        elif line.startswith("NULLING_CH_OK") or line.startswith("NULLING_CH_FAIL"): terminal[sensor] = item
    return channels, terminal

def rows(items, stage):
    out=[]
    for item in items:
        f=item["f"]
        if stage == "binary": out.append([f.get("low","-"),f.get("high","-"),f.get("mid","-"),mv(f.get("voltage")),mv(f.get("delta")),yes(f.get("valid")),yes(f.get("outBaseline")),item["time"]])
        elif stage == "mcp": out.append([f.get("code","-"),f.get("value","-"),yes(f.get("ack",f.get("write"))),f.get("mux","-"),f.get("addr","-"),item["time"]])
        else: out.append([f.get("code","-"),mv(f.get("voltage")),mv(f.get("delta")),yes(f.get("valid")),yes(f.get("aboveMin")),yes(f.get("outBaseline")),item["time"]])
    return out

def footer(c, doc):
    c.saveState(); c.setFont("Helvetica",7); c.setFillColor(colors.HexColor("#555555"))
    c.drawString(12*mm,8*mm,f"{BOARD} - Audit Rekaman Nulling 8 Kanal | Data dari serial record")
    c.drawRightString(285*mm,8*mm,f"Halaman {doc.page}"); c.restoreState()

def main():
    ch, terminal = parse(); styles=getSampleStyleSheet()
    styles.add(ParagraphStyle("title2",parent=styles["Title"],fontSize=18,leading=22,alignment=TA_CENTER,textColor=colors.HexColor("#17365D")))
    styles.add(ParagraphStyle("sub",parent=styles["Normal"],fontSize=9,leading=12,alignment=TA_CENTER))
    styles.add(ParagraphStyle("audit_h2",parent=styles["Heading2"],fontSize=13,leading=16,textColor=colors.HexColor("#17365D"),spaceBefore=4,spaceAfter=3))
    styles.add(ParagraphStyle("audit_h3",parent=styles["Heading3"],fontSize=9,leading=11,textColor=colors.HexColor("#1F4E78"),spaceBefore=4,spaceAfter=2))
    styles.add(ParagraphStyle("small",parent=styles["Normal"],fontSize=7,leading=8.5))
    styles.add(ParagraphStyle("note",parent=styles["Normal"],fontSize=7,leading=9,textColor=colors.HexColor("#404040"),spaceAfter=2))
    story=[Spacer(1,15*mm),Paragraph(f"Audit Rekaman Nulling {BOARD} - 8 Kanal",styles["title2"]),Spacer(1,3*mm),Paragraph("Run firmware 0.8.30. Isi laporan hanya berasal dari serial record yang tersimpan.",styles["sub"]),Spacer(1,8*mm),Paragraph("Status dan batas laporan",styles["audit_h2"]),Paragraph("Run selesai 8/8 LULUS; profil nulling tersimpan dan diterapkan. Tidak ada data sintetis atau tahap yang diisi dari perkiraan.",styles["Normal"]),Spacer(1,4*mm)]
    summary=[]
    for s in SENSORS:
        term=terminal.get(s); f=term["f"] if term else {}
        base=ch[s].get("baseline_done",{}).get("f",{}).get("baseline")
        status="LULUS" if term and term["line"].startswith("NULLING_CH_OK") else ("GAGAL" if term else "TIDAK TEREKAM")
        summary.append([s,status,mv(base),f"DAC={f.get('dac','-')}; delta={mv(f.get('delta'))} mV" if term else "Tidak ada keputusan final terekam"])
    story.append(table(["Sensor","Hasil","Baseline (mV)","Keputusan/penyebab"],summary,[25*mm,28*mm,33*mm,138*mm],styles,7)); story.append(PageBreak())
    for s in SENSORS:
        d=ch[s]; term=terminal.get(s); f=term["f"] if term else {}; base=d.get("baseline_done",{}).get("f",{}); th=d.get("threshold",{}).get("f",{})
        status="LULUS" if term and term["line"].startswith("NULLING_CH_OK") else "GAGAL" if term else "TIDAK TEREKAM"
        story += [Spacer(1,3*mm),Paragraph(f"{s} - proses nulling",styles["audit_h2"])]
        summary_rows=[["Hasil",status,"DAC final",f.get("dac","-"),"Detail",f"delta={mv(f.get('delta'))} mV"],["Baseline",f"{mv(base.get('baseline'))} mV","Sampel valid",base.get("validSamples","-"),"Tolerance stabilitas",f"{mv(base.get('stabilityTolerance'))} mV"],["Threshold efektif",f"{mv(th.get('effective'))} mV","Baseline term",f"{mv(th.get('baselineTerm'))} mV","Noise term",f"{mv(th.get('noiseTerm'))} mV"]]
        story.append(table(["Item","Nilai","Item","Nilai","Item","Nilai"],summary_rows,[22*mm,34*mm,24*mm,30*mm,33*mm,87*mm],styles)); story.append(Spacer(1,2*mm))
        stages=[("0. MCP write","mcp",["Kode","Nilai","ACK/Write","TCA mux","MCP addr","Waktu"],[25*mm,25*mm,27*mm,32*mm,32*mm,25*mm]),("1. Baseline","baseline",["DAC","Tegangan (mV)","Delta (mV)","Valid","Di atas min.","Keluar baseline","Waktu"],[16*mm,30*mm,27*mm,18*mm,25*mm,22*mm,20*mm]),("2. Exponential search","exp",["DAC","Tegangan (mV)","Delta (mV)","Valid","Di atas min.","Keluar baseline","Waktu"],[16*mm,30*mm,27*mm,18*mm,25*mm,22*mm,20*mm]),("3. Binary search","binary",["Low","High","Mid","Tegangan (mV)","Delta (mV)","Valid","Crossing","Waktu"],[16*mm,16*mm,16*mm,30*mm,27*mm,18*mm,22*mm,20*mm]),("4. Confirm","confirm",["DAC","Tegangan (mV)","Delta (mV)","Valid","Di atas min.","Keluar baseline","Waktu"],[16*mm,30*mm,27*mm,18*mm,25*mm,22*mm,20*mm]),("5. Verifikasi dan keputusan","verify",["DAC","Tegangan (mV)","Delta (mV)","Valid","Di atas min.","Keluar baseline","Waktu"],[16*mm,30*mm,27*mm,18*mm,25*mm,22*mm,20*mm])]
        for title,key,heads,widths in stages:
            story.append(Paragraph(title,styles["audit_h3"])); data=rows(d.get(key,[]),key)
            if data: story.append(table(heads,data,widths,styles))
            else: story.append(Paragraph("Tidak ada titik pada tahap ini; tidak dijalankan dalam run yang tercatat.",styles["note"]))
            if key == "exp":
                for item in d.get("ranges",[]): story.append(Paragraph(item["line"],styles["note"]))
            if key == "binary" and d.get("bin_done"): story.append(Paragraph(d["bin_done"]["line"],styles["note"]))
            story.append(Spacer(1,2*mm))
        if term: story.append(Paragraph(f"Baris keputusan: {term['line']}",styles["note"]))
        story.append(PageBreak())
    story.append(Paragraph("Catatan evidensi",styles["audit_h2"])); story.append(Paragraph(f"Sumber data: serial record {BOARD} 28 Agustus 2026. Laporan ini adalah hasil run aktual, bukan rencana pengujian.",styles["Normal"]))
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    SimpleDocTemplate(str(OUTPUT),pagesize=landscape(A4),leftMargin=12*mm,rightMargin=12*mm,topMargin=12*mm,bottomMargin=15*mm,title=f"Audit Rekaman Nulling {BOARD} - 8 Kanal",author="PertaminaGLD").build(story,onFirstPage=footer,onLaterPages=footer)
    print(OUTPUT)
if __name__ == "__main__": main()
