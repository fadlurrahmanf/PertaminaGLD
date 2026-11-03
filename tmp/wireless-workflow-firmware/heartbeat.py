from datetime import datetime
from pathlib import Path
import re

p=Path('docs/GLD-WIRELESS-WORKFLOW-FIRMWARE-TRACKER.md')
s=p.read_text(encoding='utf-8');now=datetime.now()
previous=datetime.strptime(re.search(r'Last tracker heartbeat: (.*?) Asia',s)[1],'%Y-%m-%d %H:%M:%S')
gap=(now-previous).total_seconds()
s=re.sub(r'Last tracker heartbeat: .*',f'Last tracker heartbeat: {now:%Y-%m-%d %H:%M:%S} Asia/Jakarta',s,count=1)
def elapsed(m):
    start=datetime.strptime(m[2],'%Y-%m-%d %H:%M:%S')
    return f'{m[1]}{m[2]} Asia/Jakarta|{str(now-start).split(".")[0]}|{m[3]}'
s=re.sub(r'(^\|[^\n]+\|)(2026-11-02 \d\d:\d\d:\d\d) Asia/Jakarta\|[^|]*\|([^\n]*)',elapsed,s,flags=re.M)
if gap>60:s+=f'\n- Heartbeat SLA breach: observed{gap:.0f}s gap during source authoring/review; no backdating.\n'
p.write_text(s,encoding='utf-8')
