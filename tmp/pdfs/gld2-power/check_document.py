"""Artifact QA: text extents, intersections with block interiors, references, arithmetic."""
from pathlib import Path
import sys, json, re, xml.etree.ElementTree as ET
from pypdf import PdfReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
ROOT=Path(__file__).resolve().parents[3]
HERE=ROOT/'output/diagrams/gld2'
sys.path.insert(0,str(HERE))
from power_budget import calculate,SOURCES
pdfmetrics.registerFont(TTFont('Arial','C:/Windows/Fonts/arial.ttf'))
pdfmetrics.registerFont(TTFont('ArialBold','C:/Windows/Fonts/arialbd.ttf'))
issues=[]
for p in sorted(HERE.glob('[0-9][0-9]-diagram.svg')):
 root=ET.parse(p).getroot(); texts=[]; boxes=[]; segments=[]
 for e in root:
  name=e.tag.split('}')[-1]; a=e.attrib
  if name=='text':
   x,y,size=float(a['x']),float(a['y']),float(a['font-size'])
   s=e.text or ''; w=pdfmetrics.stringWidth(s,'ArialBold' if a.get('font-weight')=='700' else 'Arial',size)
   texts.append((x,y-size*.82,x+w,y+size*.18,s))
  if name=='rect' and a.get('fill')=='white' and a.get('stroke')=='#CCD7DE':
   x,y,w,h=[float(a[k]) for k in ('x','y','width','height')]
   boxes.append((x,y,x+w,y+h))
  if name=='polyline' and a.get('stroke-width')=='1.8':
   pts=[tuple(map(float,c.split(','))) for c in a['points'].split()]
   segments+=list(zip(pts,pts[1:]))
 for i,t in enumerate(texts):
  if t[0]<20 or t[2]>1185 or t[1]<15 or t[3]>785:issues.append((p.name,'text extent',t))
  for u in texts[i+1:]:
   if min(t[2],u[2])-max(t[0],u[0])>1 and min(t[3],u[3])-max(t[1],u[1])>1:issues.append((p.name,'text overlap',t[4],u[4]))
 for a,b in segments:
  for x,y,xx,yy in boxes:
   if a[0]==b[0] and x+.5<a[0]<xx-.5 and min(max(a[1],b[1]),yy-.5)>max(min(a[1],b[1]),y+.5):issues.append((p.name,'line in block',a,b,(x,y,xx,yy)))
   if a[1]==b[1] and y+.5<a[1]<yy-.5 and min(max(a[0],b[0]),xx-.5)>max(min(a[0],b[0]),x+.5):issues.append((p.name,'line in block',a,b,(x,y,xx,yy)))
doc=PdfReader(ROOT/'output/pdf/GLD2-Block-Diagram.pdf')
assert len(doc.pages)==17
diagram_text='\n'.join(p.extract_text() for p in doc.pages[:9])
assert not re.search(r'\b(?:I24|I5|IESP|V24P|IBSW|IB5|IE5|IKIN|IANA|IREFSUP|IMIDSUP|IADSA|IADSD|VA24|VSRC|IAIN|PALBR|ISENSE|VSW)\b',diagram_text)
text='\n'.join(p.extract_text() for p in doc.pages)
assert not re.search(r'\bU\d+\b|\bkanal\b|simultaneously',text,re.I)
assert all(i in text for i,_,_,_ in SOURCES)
assert 'Sensor slot 1 (example)' in text
assert '5.26750' in text and '4.98848' in text and '6.57468' in text
assert all(tuple(map(float,p.mediabox[2:]))==(1200.,800.) for p in doc.pages)
links=sum(len(p.get('/Annots',[])) for p in doc.pages)
assert links==len(SOURCES),(links,len(SOURCES))
saved=json.loads((HERE/'power-calculations.json').read_text())
assert saved==calculate()
report=dict(pages=len(doc.pages),source_links=links,geometry_issues=issues,calculation_reproducible=True)
Path(__file__).with_name('qa-report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report,indent=2))
assert not issues
