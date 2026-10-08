"""Build Main-PCB-Schematic-GLD-V4.pdf: per figure = original EasyEDA crop + numbered boundary box per part +
sheet info table (drawing no., revision, date, title, sheet no.) + 'what is this / what does it do' table."""
import re
import subprocess
from html import escape
from pathlib import Path

import content as C
import make_screens as m

HERE = Path(__file__).resolve().parent
TMP = HERE / "_pdf_tmp"
EXE = next(b for b in [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                       r"C:\Program Files\Google\Chrome\Application\chrome.exe"] if Path(b).exists())
blk = {t: (p, parts) for t, p, parts in m.BLOCKS}

SECTIONS = [
    ("24 VDC input", [
        ("24 VDC input, input protection and 24 V to 5 V buck (U36)", "24 VDC input and input protection",
         "24 VDC input, input protection and 5 V rail (buck)"),
        ("Power connector J1, battery input and external 5 V", "24 VDC input and input protection",
         "Power connector J1, battery input and external 5 V"),
    ]),
    ("Input protection", [
        ("Battery load switch (U14)", "Input protection", "Input protection (battery load switch)"),
    ]),
    ("5 V rail", [
        ("5 V power-path mux (U13)", "5 V rail", "5 V rail (power-path mux)"),
        ("Battery boost to about 24 V (U1, TPS61175)", "5 V rail / backup of the +24V rail", "5 V rail (battery boost to 24 V)"),
        ("Battery boost to 5 V (U41, TPS61088)", "5 V rail", "5 V rail (battery boost to 5 V)"),
    ]),
    ("3.3 V rail", [
        ("5 V to 3.3 V buck (U43)", "3.3 V rail", "3.3 V rail (5 V to 3.3 V buck)"),
        ("Always-on 3.3 V LDO and its source selection (U42)", "3.3 V rail", "3.3 V rail (always-on LDO)"),
        ("TPL5010 timer/watchdog (U46)", "3.3 V rail / power latch", "3.3 V rail (TPL5010 timer)"),
        ("ENA latch (U51) and open-drain inverter (U15)", "3.3 V rail / power latch", "3.3 V rail (ENA latch)"),
        ("3V3AON voltage supervisor (U16)", "3.3 V rail / power latch", "3.3 V rail (supervisor)"),
    ]),
    ("MQ heater supply", [
        ("Sensor module connector H2 (one connector as example)", "MQ heater supply and MQ sensor interface",
         "MQ heater supply and sensor (one connector)"),
        ("Sensor module connectors H1-H8", "MQ heater supply and MQ sensor interface",
         "MQ heater supply and sensor (eight connectors)"),
        ("Sensor module enable I/O expander (U12)", "MQ heater supply (module enable)", "Sensor interface (enable expander)"),
    ]),
    ("MQ sensor bridge / analog circuitry", [
        ("VMID bias of about 2.5 V (U3)", "MQ sensor bridge / analog circuitry", "MQ sensor analog circuitry (VMID)"),
        ("Analog +5VA supply filter (L6)", "MQ sensor bridge / analog circuitry", "MQ sensor analog circuitry (+5VA)"),
        ("Sensor module I2C multiplexer (U33)", "MQ sensor bridge / analog circuitry", "Sensor interface (I2C mux)"),
        ("Temperature and humidity sensor (U44)", "MQ sensor bridge / analog circuitry (environment compensation)",
         "Temperature and humidity sensor"),
    ]),
    ("ADC", [
        ("ADS1256 ADC with input filters (AIN), clock and decoupling", "ADC; MQ sensor bridge / analog circuitry", "ADC"),
        ("2.5 V voltage reference and VREF buffer", "ADC", "ADC (voltage reference)"),
    ]),
    ("ESP32-S3", [
        ("ESP32-S3-WROOM-1U-N16R8 with support parts (including status LED)", "ESP32-S3; LED / buzzer driver (LED)", "ESP32-S3"),
        ("USB, CH340C and auto-reset", "ESP32-S3 (programming)", "ESP32-S3 (USB and programming)"),
    ]),
    ("LoRa", [("E22-900MM22S LoRa module and antenna connector", "LoRa", "LoRa")]),
    ("Fan driver", [("5 V fan driver (Q5, J3)", "Fan driver", "Fan driver")]),
    ("LED / buzzer driver", [("24 V alarm output driver (Q4, J2)", "LED / buzzer driver", "LED / buzzer driver (alarm)")]),
    ("RS-485 / Modbus", [("RS-485 transceiver (U47)", "RS-485 / Modbus", "RS-485 / Modbus")]),
]


def render_boxed(name, co):
    shown = [d for c in co for d in c["parts"]]
    mg = 8
    x0 = min(m.bb(d)[0] for d in shown) - mg
    y0 = min(m.bb(d)[1] for d in shown) - mg
    x1 = max(m.bb(d)[2] for d in shown) + mg
    y1 = max(m.bb(d)[3] for d in shown) + mg
    cw, ch = x1 - x0, y1 - y0
    s = 3.0
    boxes = []
    for i, c in enumerate(co):
        col = m.PALETTE[i % len(m.PALETTE)]
        for d in c["parts"]:
            b = m.bb(d)
            boxes.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" fill-opacity="0.08" stroke="%s" '
                         'stroke-width="%.2f"/>' % (b[0] - 2, b[1] - 2, b[2] - b[0] + 4, b[3] - b[1] + 4, col, col, 2.2 / s))
            r = 11 / s
            boxes.append('<circle cx="%.1f" cy="%.1f" r="%.2f" fill="%s"/>' % (b[0] - 2, b[1] - 2, r, col))
            boxes.append('<text x="%.1f" y="%.2f" font-size="%.2f" font-weight="bold" fill="#fff" text-anchor="middle" '
                         'font-family="Arial">%d</text>' % (b[0] - 2, b[1] - 2 + r * 0.38, r * 1.3, i + 1))
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="%.1f %.1f %.1f %.1f">'
           '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#fff"/>%s%s%s</svg>'
           % (cw * s, ch * s, x0, y0, cw, ch, x0, y0, cw, ch, m.body, m.wires, "".join(boxes)))
    sp = TMP / (name + ".svg")
    sp.write_text(svg, encoding="utf8")
    png = TMP / (name + ".png")
    subprocess.run([EXE, "--headless", "--disable-gpu", "--hide-scrollbars", "--window-size=%d,%d" % (cw * s, ch * s),
                    "--screenshot=%s" % png, sp.as_uri()], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return png, cw


def main():
    TMP.mkdir(exist_ok=True)
    figs = []
    n = 0
    total = sum(len(f) for _, f in SECTIONS)
    for sec, items in SECTIONS:
        for title, req, bt in items:
            n += 1
            purpose, parts = blk[bt]
            co, left = m.callouts_for(parts)
            assert not left, (title, left)
            png, cw = render_boxed("fig%02d" % n, co)
            figs.append(dict(sec=sec, no=n, title=title, req=req, purpose=purpose, co=co, png=png, cw=cw, total=total))
    fig_of = lambda d: next((f["no"] for f in figs if any(d in c["parts"] for c in f["co"])), None)
    nums = lambda s: ", ".join(str(f["no"]) for f in figs if f["sec"] == s)
    h = ['<!doctype html><html lang="en"><meta charset="utf-8"><title>Main PCB Schematic - GLD V4</title><style>'
         '@page{size:A4 portrait;margin:13mm 12mm}body{font-family:Arial,Helvetica,sans-serif;font-size:10pt;color:#1d2430;margin:0}'
         'h1{font-size:22pt;margin:0 0 4px;color:#1f3a5f}h2{font-size:15pt;margin:0 0 8px;color:#1f3a5f;'
         'border-bottom:2px solid #1f3a5f;padding-bottom:3px}h3{font-size:11.5pt;margin:0 0 5px;color:#1f3a5f}'
         'table{border-collapse:collapse;width:100%;margin:5px 0 8px;font-size:8.8pt}td,th{border:1px solid #aab2bf;'
         'padding:3px 6px;vertical-align:top;text-align:left}th{background:#dce6f4}.fig{break-inside:avoid;margin:0 0 14px}'
         '.pb{break-before:page}.img{text-align:center;margin:4px 0}.img img{border:1px solid #c5ccd8;max-width:100%}'
         '.n{display:inline-block;min-width:16px;height:16px;border-radius:8px;color:#fff;text-align:center;font-weight:700;'
         'font-size:8.5pt;line-height:16px}.sub{font-size:12pt;color:#444;margin:0 0 10px}.small{font-size:9pt}'
         'ul{margin:4px 0 0 18px;padding:0}li{margin:0 0 4px}</style><body>']
    h.append('<h1>Main PCB Schematic</h1><p class="sub">GLD V4 (MotherBoardGLDVer2) - section 6(a).7</p>')
    h.append('<table><tr><th style="width:30%%">Item</th><th>Details</th></tr>'
             '<tr><td>Type</td><td>Actual electrical schematic (not a block diagram), cut into functional blocks from the original '
             'EasyEDA file. Every component has a numbered boundary box; the same number is used in the description table.</td></tr>'
             '<tr><td>Source</td><td>GLD ATEX.zip &gt; 1-Schematic_MotherBoardGLDVer2.json (EasyEDA 6.5.57)</td></tr>'
             '<tr><td>Source revision / date</td><td>1.0 / 2026-07-19 (from the title block of the EasyEDA schematic)</td></tr>'
             '<tr><td>Document number</td><td>PGLD-GLD-V4-MB-SCH-NN (proposed; NN = figure number)</td></tr>'
             '<tr><td>Number of figures</td><td>%d</td></tr></table>' % total)
    h.append('<h2>Coverage of the requirements</h2><table><tr><th style="width:38%">Required content</th><th>Figures / sections</th></tr>')
    cov = [("24 VDC input", "Figures %s" % nums("24 VDC input")),
           ("Input protection", "Figures %s; Figures 1, 2 (F1, D1, L1, L4, F2, Q2) and the protection table" % nums("Input protection")),
           ("5 V rail", "Figures %s; Figure 1 (buck U36)" % nums("5 V rail")),
           ("3.3 V rail", "Figures %s" % nums("3.3 V rail")),
           ("MQ heater supply", "Figures %s" % nums("MQ heater supply")),
           ("MQ sensor bridge / analog circuitry", "Figures %s; AIN input filters in Figure %s" % (nums("MQ sensor bridge / analog circuitry"), nums("ADC").split(",")[0])),
           ("ADC", "Figures %s" % nums("ADC")),
           ("ESP32-S3", "Figures %s" % nums("ESP32-S3")),
           ("LoRa", "Figure %s" % nums("LoRa")),
           ("Fan driver", "Figure %s" % nums("Fan driver")),
           ("LED / buzzer driver", "Figure %s; status LED in Figure %s" % (nums("LED / buzzer driver"), nums("ESP32-S3").split(",")[0])),
           ("RS-485 / Modbus", "Figure %s" % nums("RS-485 / Modbus")),
           ("Protection devices", 'Section "Protection devices" (table)'), ("Grounding", 'Section "Grounding"')]
    h += ["<tr><td>%s</td><td>%s</td></tr>" % (escape(a), escape(b)) for a, b in cov]
    h.append("</table><p class='small'>Every figure carries a sheet information table: drawing/document number, revision, date, title and sheet number.</p>")
    cur = None
    for f in figs:
        if f["sec"] != cur:
            cur = f["sec"]
            h.append('<h2 class="pb">%s</h2>' % escape(cur))
        wmm = max(70, min(182, f["cw"] * 0.45))
        h.append('<div class="fig"><h3>Figure %d - %s</h3>' % (f["no"], escape(f["title"])))
        h.append('<div class="img"><img style="width:%.0fmm" src="%s"></div>' % (wmm, f["png"].as_uri()))
        h.append('<table><tr><th style="width:36%%">Drawing / document no.</th><th>Rev</th><th>Date</th><th style="width:30%%">Title</th><th>Sheet</th></tr>'
                 '<tr><td>PGLD-GLD-V4-MB-SCH-%02d</td><td>1.0</td><td>2026-07-19</td><td>%s</td><td>%d of %d</td></tr></table>'
                 % (f["no"], escape(f["title"]), f["no"], f["total"]))
        h.append('<p class="small"><b>Block function:</b> %s &nbsp; <b>Requirement covered:</b> %s</p>' % (escape(f["purpose"]), escape(f["req"])))
        h.append('<table><tr><th style="width:5%">No</th><th style="width:15%">Component</th><th style="width:33%">What it is</th><th>What it does</th></tr>')
        for i, c in enumerate(f["co"]):
            col = m.PALETTE[i % len(m.PALETTE)]
            h.append('<tr><td><span class="n" style="background:%s">%d</span></td><td>%s</td><td>%s</td><td>%s</td></tr>'
                     % (col, i + 1, escape(", ".join(c["parts"])), escape(c["apa"]), escape(c["fungsi"])))
        h.append("</table></div>")
    h.append('<h2 class="pb">Protection devices</h2><table><tr><th>Designator</th><th>Part</th><th>Location</th><th>Protects against / function</th><th>Figure</th></tr>')
    for des, part, lokasi, fungsi in C.PROTECTION_ROWS:
        ds = [t for t in re.split(r"[/ ]+", des) if re.fullmatch(r"[A-Z]+\d+", t)]
        ns = sorted({fig_of(d) for d in ds if fig_of(d)})
        h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                 % (escape(des), escape(part), escape(lokasi), escape(fungsi), ", ".join(map(str, ns)) or "-"))
    h.append("</table><h2 style='margin-top:18px'>Grounding</h2><ul>")
    h += ["<li>%s</li>" % escape(g) for g in C.GROUNDING_NOTES]
    gf = sorted({fig_of(d) for d in ("J1", "L1", "L6", "USB1", "G1") if fig_of(d)})
    h.append("</ul><p class='small'>Related figures: %s.</p>" % ", ".join(map(str, gf)))
    h.append("<h2 style='margin-top:18px'>Notes for verification</h2><ul>")
    notes = [
        "PTC rating of F1/F2: the part number is MINISMDC260F/16-2; the /16 suffix usually means a 16 V rating, while F1 sits on the 24 V line. Check the datasheet.",
        "Orientation of Q3 and Q2: the source is on the input side (+24V / battery) and the gate goes to GND through 100k. With this orientation the body diode does not appear to block reverse polarity. If reverse-polarity protection is intended, this needs to be checked.",
        "MQ heater supply: the board only provides +5V (pin 2) and VMID (pin 8) on each connector H1-H8. The per-channel heater switch and the sensor load resistor are not on this schematic; they are assumed to be on the sensor module (to be confirmed).",
        "RS-485: there is no 120 ohm termination resistor or A/B bias on the schematic, only TVS D6.",
        "Grounding: there is only one GND net; there is no separate AGND or chassis ground. The connection point to chassis ground/PE is not drawn.",
        "The type of the 24 V alarm load on J2 cannot be determined from the schematic.",
        "The converter output voltages quoted (about 5.0 V, 24 V, 5.3 V) are calculated from the feedback resistors and the typical reference voltage of the IC; they have not been measured.",
        "The figures are rendered from the original schematic file (same appearance as EasyEDA) so that the boundary boxes sit exactly on the components.",
    ]
    h += ["<li>%s</li>" % escape(x) for x in notes]
    h.append("</ul></body></html>")
    hp = TMP / "doc.html"
    hp.write_text("\n".join(h), encoding="utf8")
    pdf = HERE / "Main-PCB-Schematic-GLD-V4.pdf"
    subprocess.run([EXE, "--headless", "--disable-gpu", "--no-pdf-header-footer", "--print-to-pdf=%s" % pdf, hp.as_uri()],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("PDF", pdf.name, "figures", total)


if __name__ == "__main__":
    main()
