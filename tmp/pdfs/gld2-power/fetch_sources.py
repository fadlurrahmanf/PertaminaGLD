from pathlib import Path
import urllib.request, concurrent.futures, hashlib
from pypdf import PdfReader
BASE = Path(__file__).parent
PARTS = ['ads1256','opa320','tps2116','tps62162','tps7a02','tps61088','lmr51450','tps61175','tps22964','tpl5010','tps3839','sn74aup1g74','sn74lvc1g06','tca9548a','pcf8574','thvd1410']
URLS = {p:f'https://www.ti.com/lit/ds/symlink/{p}.pdf' for p in PARTS}
URLS['adr03']='https://www.analog.com/media/en/technical-documentation/data-sheets/ADR01_02_03_06.pdf'
URLS['esp32s3']='https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf'
def fetch(item):
    part,url=item
    try:
        p=BASE/(part+'.pdf')
        if not p.exists():
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
            p.write_bytes(urllib.request.urlopen(req,timeout=45).read())
        reader=PdfReader(p)
        (BASE/(part+'.txt')).write_text('\n'.join(f'\n--- PDF PAGE {i+1} ---\n'+(pg.extract_text(extraction_mode='layout') or '') for i,pg in enumerate(reader.pages)),encoding='utf8')
        return part,len(reader.pages),hashlib.sha256(p.read_bytes()).hexdigest()
    except Exception as e: return part,str(e)
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    for result in pool.map(fetch,URLS.items()):print(*result)
