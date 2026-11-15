"""Keep small voltage ticks distinguishable; preserve all chart data."""
from pathlib import Path
import os,re,tempfile,zipfile
p=Path(__file__).resolve().parent.parent/'GLD_Gabungan.xlsx'
fd,tmp=tempfile.mkstemp(prefix='.axes-',suffix='.tmp',dir=p.parent);os.close(fd)
count=0
try:
 with zipfile.ZipFile(p) as src,zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as out:
  for info in src.infolist():
   b=src.read(info.filename)
   if '/charts/' in info.filename and info.filename.endswith('.xml') and '/_rels/' not in info.filename:
    b,n=re.subn(rb'(<c:numFmt\b[^>]*formatCode=")0\.000(")',rb'\g<1>0.0000\2',b);count+=n
   out.writestr(info,b)
 assert count==26,('Unexpected voltage axis count',count)
 os.replace(tmp,p)
 print('Formatted all 26 voltage axes to 0.0000 V')
finally:
 if os.path.exists(tmp):os.unlink(tmp)
