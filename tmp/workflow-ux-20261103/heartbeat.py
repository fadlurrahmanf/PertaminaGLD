from pathlib import Path
from datetime import datetime
import re,json
p=Path('docs/GLD-WIZARD-UX-TRACKER.md');s=p.read_text(encoding='utf-8');now=datetime.now();previous=re.search(r'Last tracker heartbeat: (.*?) Asia',s)
if previous:
 gap=(now-datetime.strptime(previous[1],'%Y-%m-%d %H:%M:%S')).total_seconds()
 if gap>60:s+=f'\n- Heartbeat SLA breach: observed {gap:.0f}s during audit setup/review; no backdating.\n'
s=re.sub(r'Last tracker heartbeat: .*',f'Last tracker heartbeat: {now:%Y-%m-%d %H:%M:%S} Asia/Jakarta',s,count=1)
def elapsed(m):
 start=datetime.strptime(m[2],'%Y-%m-%d %H:%M:%S');return f'{m[1]}{m[2]} Asia/Jakarta|{str(now-start).split(".")[0]}|{m[3]}'
s=re.sub(r'(^\|[^\n]+\|)(2026-11-03 \d\d:\d\d:\d\d) Asia/Jakarta\|[^|]*\|([^\n]*)',elapsed,s,flags=re.M)
p.write_text(s,encoding='utf-8')
