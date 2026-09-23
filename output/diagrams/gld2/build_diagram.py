"""Build source-derived GLD2 block diagrams: PDF, SVG and offline HTML."""
from pathlib import Path
import json, math, html, csv, textwrap
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PDF=ROOT/'output/pdf/GLD2-Block-Diagram.pdf'
DATA=json.loads((HERE/'source-net-evidence.json').read_text(encoding='utf8'))
C=DATA['components']; W,H=1200,800
pdfmetrics.registerFont(TTFont('Arial','C:/Windows/Fonts/arial.ttf'))
pdfmetrics.registerFont(TTFont('ArialBold','C:/Windows/Fonts/arialbd.ttf'))
P=canvas.Canvas(str(PDF),pagesize=(W,H)); P.setTitle('GLD2 | Schematic Block Diagram'); P.setAuthor('PertaminaGLD')
COL={'ink':'#183044','muted':'#183044','line':'#CCD7DE','power':'#B86518','signal':'#147B75','bus':'#316FC0','control':'#8060AC','warn':'#AD4D35','bg':'#F4F7F9'}
sv=[]; pages=[]; number=0; routed_segments=[]
def esc(x): return html.escape(str(x))
def rect(x,y,w,h,fill='white',stroke=None,r=8):
 P.setFillColor(fill); P.setStrokeColor(stroke or fill); P.roundRect(x,H-y-h,w,h,r,stroke=bool(stroke),fill=1)
 sv.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke or fill}"/>')
def txt(x,y,text,size=13,color=None,bold=False):
 color=color or COL['ink']; font='ArialBold' if bold else 'Arial'
 P.setFont(font,size); P.setFillColor(color); P.drawString(x,H-y-size*.82,str(text))
 sv.append(f'<text x="{x}" y="{y+size*.82}" font-family="Arial,sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{esc(text)}</text>')
def para(x,y,text,width,size=13,color=None,leading=None):
 leading=leading or size*1.4
 for line in str(text).split('\n'):
  words=line.split(); buf=''
  for word in words:
   test=(buf+' '+word).strip()
   if pdfmetrics.stringWidth(test,'Arial',size)>width and buf: txt(x,y,buf,size,color); y+=leading; buf=word
   else: buf=test
  txt(x,y,buf,size,color); y+=leading
 return y
def box(x,y,w,h,title,body='',kind='bus',size=13,title_size=15):
 rect(x,y,w,h,'white',COL['line']); rect(x,y,5,h,COL[kind],r=2)
 txt(x+16,y+14,title,title_size,bold=True)
 if body: para(x+16,y+40,body,w-30,size)
 return (x,y,w,h)
def line(points,kind='bus',label=None,lx=None,ly=None,dashed=False,arrow=True,label_size=11):
 original=points
 # Rounded crossover bridges: crossings are not electrical junctions.
 routed=[points[0]]; bridges=[]
 for a,b in zip(points,points[1:]):
  horizontal=a[1]==b[1]; vertical=a[0]==b[0]
  crosses=[]
  for c,d in routed_segments:
   if horizontal and c[0]==d[0] and min(a[0],b[0])+9<c[0]<max(a[0],b[0])-9 and min(c[1],d[1])<a[1]<max(c[1],d[1]): crosses.append((c[0],a[1]))
   if vertical and c[1]==d[1] and min(a[1],b[1])+9<c[1]<max(a[1],b[1])-9 and min(c[0],d[0])<a[0]<max(c[0],d[0]): crosses.append((a[0],c[1]))
  for x,y in sorted(set(crosses),key=lambda p:(p[0]-a[0])**2+(p[1]-a[1])**2):
   direction=1 if (b[0]>a[0] if horizontal else b[1]>a[1]) else -1
   bridge=[]
   for k in range(13):
    angle=math.pi*k/12
    along=-7*math.cos(angle)*direction; hump=7*math.sin(angle)
    pt=(x+along,y-hump) if horizontal else (x+hump,y+along)
    routed.append(pt); bridge.append(pt)
   bridges.append(bridge)
  routed.append(b)
 routed_segments.extend(zip(original,original[1:]))
 points=routed
 for bridge in bridges:
  P.setStrokeColor(COL['bg']); P.setLineWidth(6); P.setDash()
  path=P.beginPath(); path.moveTo(bridge[0][0],H-bridge[0][1])
  for x,y in bridge[1:]: path.lineTo(x,H-y)
  P.drawPath(path)
  sv.append('<polyline points="'+' '.join(f'{x},{y}' for x,y in bridge)+f'" fill="none" stroke="{COL["bg"]}" stroke-width="6"/>')
 color=COL[kind]; P.setStrokeColor(color); P.setLineWidth(1.8); P.setDash(5,4) if dashed else P.setDash()
 path=P.beginPath(); path.moveTo(points[0][0],H-points[0][1])
 for x,y in points[1:]: path.lineTo(x,H-y)
 P.drawPath(path); P.setDash()
 sv.append(f'<polyline points="'+ ' '.join(f'{x},{y}' for x,y in points)+f'" fill="none" stroke="{color}" stroke-width="1.8"'+(' stroke-dasharray="5 4"' if dashed else '')+'/>')
 if arrow:
  a,b=points[-2:]; ang=math.atan2(b[1]-a[1],b[0]-a[0]); q=[b,(b[0]-8*math.cos(ang-.45),b[1]-8*math.sin(ang-.45)),(b[0]-8*math.cos(ang+.45),b[1]-8*math.sin(ang+.45))]
  P.setFillColor(color); path=P.beginPath(); path.moveTo(q[0][0],H-q[0][1]); [path.lineTo(x,H-y) for x,y in q[1:]]; path.close(); P.drawPath(path,stroke=0,fill=1)
  sv.append('<polygon points="'+' '.join(f'{x},{y}' for x,y in q)+f'" fill="{color}"/>')
 if label:
  lx=lx if lx is not None else (points[0][0]+points[-1][0])/2
  ly=ly if ly is not None else (points[0][1]+points[-1][1])/2-17
  tw=pdfmetrics.stringWidth(label,'Arial',label_size); rect(lx-3,ly-2,tw+6,label_size+5,'#F4F7F9',r=2); txt(lx,ly,label,label_size,color)
def table(x,y,width,headers,rows,widths=None,rh=31,size=12):
 widths=widths or [width/len(headers)]*len(headers)
 rect(x,y,width,rh,COL['ink'],r=3); xx=x
 for h,w in zip(headers,widths): txt(xx+9,y+9,h,size,'white',True); xx+=w
 for i,row in enumerate(rows):
  yy=y+(i+1)*rh; rect(x,yy,width,rh,'white' if i%2==0 else '#EAF0F4',r=0); xx=x
  for val,w in zip(row,widths):
   assert pdfmetrics.stringWidth(str(val),'Arial',size)<w-15,(val,w)
   txt(xx+9,yy+9,val,size); xx+=w
 return y+(len(rows)+1)*rh
def start(title,subtitle,subtitle_size=13):
 global sv,number,routed_segments
 sv=[]; routed_segments=[]; number+=1; rect(0,0,W,H,COL['bg'],r=0)
 txt(38,24,'PERTAMINA GLD   /   SCHEMATIC BLOCK DIAGRAM',11,COL['signal'],True)
 txt(38,51,title,28,bold=True); txt(38,91,subtitle,subtitle_size,COL['muted'])
def end():
 txt(1035,765,f'{number:02d} / 09',10,COL['muted'])
 name=f'{number:02d}-diagram.svg'; (HERE/name).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'+''.join(sv)+'</svg>',encoding='utf8'); pages.append(name); P.showPage()

from power_budget import B, SOURCES, SENSORS, export
export()
exec(compile((HERE/'allocation_pages.py').read_text(encoding='utf8'),str(HERE/'allocation_pages.py'),'exec'))
P.save()

with (HERE/'component-pins.csv').open('w',newline='',encoding='utf-8-sig') as f:
 w=csv.writer(f); w.writerow(['ref','value','sheet','pin','pin_name','pcb_net','schematic_labels'])
 for ref,c in C.items():
  if not c['pins']: w.writerow([ref,c['value'],c['sheet'],'','','',''])
  for pin,v in c['pins'].items(): w.writerow([ref,c['value'],c['sheet'],pin,v['name'],v['net'],' | '.join(v['schematic_labels'])])
viewer='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GLD2 - Block Diagram</title><style>body{margin:0;background:#dfe7ed;color:#183044;font:15px Arial}header{position:sticky;top:0;background:#183044;color:white;padding:16px 24px;z-index:2;display:flex;gap:20px;align-items:center;flex-wrap:wrap}header a{color:#9ee6dd}main{padding:20px;overflow:auto}.page{width:1200px;max-width:none;margin:0 auto 24px;background:white;box-shadow:0 4px 16px #18304424}.page img{width:100%;display:block}select,button{padding:6px}input{vertical-align:middle}nav{display:flex;gap:12px}p{margin:0}@media print{header{display:none}.page{break-after:page;margin:0;width:100%;box-shadow:none}main{padding:0}}</style><header><b>GLD2 | Schematic Block Diagram</b><select id="jump">'''
titles=['Architecture','Main power','Always On','Sensor module','Analog acquisition','Eight sensor loads','ESP32 connections','Alarm branch','24 V power allocation']
viewer+=''.join(f'<option value="p{i}">{i:02d} - {t}</option>' for i,t in enumerate(titles,1))
viewer+='''</select><label>Zoom <input id="zoom" type="range" min="60" max="180" value="100"> <span id="zval">100%</span></label><nav><a href="../../pdf/GLD2-Block-Diagram.pdf">PDF</a><a href="component-pins.csv">All pins (CSV)</a><a href="README.md">Guide</a></nav></header><main>'''
viewer+=''.join(f'<section class="page" id="p{i}"><img src="{n}" alt="Diagram {i}: {esc(titles[i-1])}"></section>' for i,n in enumerate(pages,1))
viewer+='''</main><script>const z=document.querySelector('#zoom');z.oninput=()=>{document.querySelectorAll('.page').forEach(p=>p.style.width=(12*z.value)+'px');document.querySelector('#zval').textContent=z.value+'%'};document.querySelector('#jump').onchange=e=>document.getElementById(e.target.value).scrollIntoView({behavior:'smooth',block:'center'});</script></html>'''
(HERE/'index.html').write_text(viewer,encoding='utf8')
readme='''# GLD2 - schematic block diagram

Open `index.html` to view the nine diagram pages with page selection and zoom, or open `../../pdf/GLD2-Block-Diagram.pdf` for the vector PDF. Former pages 10-17 have been removed. The external 5 V input and its paths are omitted at the user's request; original design files are unchanged.
The SVG files can be edited with Inkscape, Illustrator, or a text editor. Drawing helpers are in `build_diagram.py`, page content in `allocation_pages.py`, and calculations in `allocation_budget.py` and `power_budget.py`.

## Source and scope

- One motherboard sheet (Sheet_1), all 204 component/symbol records, and PCB pad nets from the user-provided ZIP.
- The sensor-module reference image was read separately; its component designators do not match the motherboard.
- `source-net-evidence.json` stores symbol pin names, PCB pad nets, schematic pin coordinates, and traced net labels. No differences were found for pins with a net label. This is not a complete electrical-rules check or PCB-routing validation.
- `component-pins.csv` lists every component pin, including passive components. Case-only rows have no electrical pins.
- The eight configured MQ types come from firmware/gld/include/BoardPinsGLD2.h. Fitted manufacturers are not established: heater calculations explicitly use reference manufacturer datasheets.
- The motherboard +5VA source is absent from the original ZIP. A later user-supplied filter image (5VA.png) supplies the +5V-to-+5VA connection shown here. Module and motherboard analog rails remain distinct.
- Reference-module pins differ from the motherboard header. Module pages show functional connections and load allocation, not a wiring instruction without orientation verification.
- No firmware, build, upload, COM, or hardware measurements were changed.

## Calculations

Brown power connections use calculated voltage/current labels for the 24 V reference scenario. Page 09 allocates load power back to the 24 V source and separates conversion losses. CALCULATION-NOTES.md and allocation-calculations.json retain formulas, source links, assumptions and exclusions outside the PDF. Reference estimates are not measured consumption or guaranteed hardware maxima. Alarm-on demand is excluded until its exact model is identified.

## Regeneration

Run with Python and reportlab from the repository root: `python output/diagrams/gld2/build_diagram.py`. The font is Windows Arial.
The generator outputs the PDF, nine SVG files, HTML, CSV, and README. Its primary input is the extracted `source-net-evidence.json`.

Source ZIP SHA-256: `'''+DATA['sha256']+'`\n'
(HERE/'README.md').write_text(readme,encoding='utf8')
print('Created',PDF,'with',len(pages),'SVG pages')
