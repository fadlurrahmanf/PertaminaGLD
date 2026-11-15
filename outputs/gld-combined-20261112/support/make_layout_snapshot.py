"""Small QA-only view of the actual exported cells; never a deliverable."""
from pathlib import Path
import zipfile, re, xml.etree.ElementTree as E, posixpath
S='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R='http://schemas.openxmlformats.org/package/2006/relationships'
Q=lambda n:'{'+S+'}'+n
base=Path(__file__).resolve().parent
source=base.parent/'GLD_Gabungan.xlsx'
with zipfile.ZipFile(source) as src, zipfile.ZipFile(base/'layout_snapshot.bin','w',zipfile.ZIP_DEFLATED) as out:
 for name in src.namelist():
  if name.startswith(('xl/charts/','xl/drawings/')):continue
  payload=src.read(name)
  if re.fullmatch(r'xl/worksheets/sheet\d+\.xml',name):
   root=E.fromstring(payload);sheetdata=root.find(Q('sheetData'))
   limit=30 if name.endswith('/sheet1.xml') else 7
   for row in list(sheetdata):
    if int(row.get('r'))>limit:sheetdata.remove(row);continue
    for cell in row.findall(Q('c')):
     for f in cell.findall(Q('f')):cell.remove(f)
   for node in list(root):
    if node.tag in (Q('drawing'),Q('legacyDrawing')):root.remove(node)
   payload=E.tostring(root,encoding='utf-8',xml_declaration=True)
  elif re.fullmatch(r'xl/worksheets/_rels/sheet\d+\.xml.rels',name):
   root=E.fromstring(payload)
   for rel in list(root):
    if rel.get('Type','').endswith('/drawing'):root.remove(rel)
   payload=E.tostring(root,encoding='utf-8',xml_declaration=True)
  elif name=='[Content_Types].xml':
   payload=re.sub(rb'<Override\b(?=[^>]*PartName="/xl/(?:charts|drawings)/)[^>]*/>',b'',payload)
  out.writestr(name,payload)
print('Created layout_snapshot.bin for QA only')
