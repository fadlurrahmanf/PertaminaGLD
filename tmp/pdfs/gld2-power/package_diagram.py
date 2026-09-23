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
 z.writestr('OPEN-FIRST.txt','GLD2 block diagram - English, power calculation revision\n\nPDF: output/pdf/GLD2-Block-Diagram.pdf\nOffline viewer: output/diagrams/gld2/index.html\nSource notes: output/diagrams/gld2/README.md\n\nKeep the extracted folder structure for working relative links.\nReference calculations are not measured loads; unknown quantities remain variables.\n')
with ZipFile(target) as z:
 assert z.testzip() is None
 for p in files:assert z.read(p.relative_to(ROOT).as_posix())==p.read_bytes()
 base='output/diagrams/gld2/'
 viewer=z.read(base+'index.html').decode()
 for link in re.findall(r'(?:src|href)="([^"]+)"',viewer):
  if '://' not in link and not link.startswith('#'):
   assert posixpath.normpath(base+link) in z.namelist(),link
 print(json.dumps(dict(entries=len(z.namelist()),relative_links='OK',pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),zip_sha256=hashlib.sha256(target.read_bytes()).hexdigest()),indent=2))
