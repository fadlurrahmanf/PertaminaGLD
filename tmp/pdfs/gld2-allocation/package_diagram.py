from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import hashlib,json,posixpath,re
ROOT=Path(__file__).resolve().parents[3]
asset=ROOT/'output/diagrams/gld2'
pdf=ROOT/'output/pdf/GLD2-Block-Diagram.pdf'
target=ROOT/'output/diagrams/GLD2-Diagram-Lengkap.zip'
files=sorted(p for p in asset.iterdir() if p.is_file())+[pdf]
with ZipFile(target,'w',ZIP_DEFLATED) as z:
 for p in files:z.write(p,p.relative_to(ROOT).as_posix())
 z.writestr('OPEN-FIRST.txt','GLD2 block diagram - English, nine-page power allocation\n\nPDF: output/pdf/GLD2-Block-Diagram.pdf\nOffline viewer: output/diagrams/gld2/index.html\nCalculation basis: output/diagrams/gld2/CALCULATION-NOTES.md\n\nKeep the extracted folder structure for working relative links.\nReference scenario: 24 V only, all eight sensors active, alarm off. Approximate modeled load: 0.332 A / 7.97 W. Active alarm, startup and other exclusions remain outside this subtotal. Former pages 10-17 and the external 5 V input paths have been removed from the diagram.\n')
with ZipFile(target) as z:
 assert z.testzip() is None
 assert len([n for n in z.namelist() if re.search(r'/\d{2}-diagram.svg$',n)])==9
 for p in files:assert z.read(p.relative_to(ROOT).as_posix())==p.read_bytes()
 base='output/diagrams/gld2/'
 viewer=z.read(base+'index.html').decode()
 for link in re.findall(r'(?:src|href)="([^"]+)"',viewer):
  if '://' not in link and not link.startswith('#'):
   assert posixpath.normpath(base+link) in z.namelist(),link
 print(json.dumps(dict(entries=len(z.namelist()),relative_links='OK',pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),zip_sha256=hashlib.sha256(target.read_bytes()).hexdigest()),indent=2))
