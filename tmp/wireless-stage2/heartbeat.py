from pathlib import Path
from datetime import datetime
import re
p=Path('docs/GLD-WIRELESS-REPLAY-GOAL-TRACKER.md');s=p.read_text(encoding='utf-8');n=datetime.now();old=re.search(r'Last tracker heartbeat: (.*?) Asia',s).group(1);gap=(n-datetime.strptime(old,'%Y-%m-%d %H:%M:%S')).total_seconds();s=re.sub(r'Last tracker heartbeat: .*',f'Last tracker heartbeat: {n:%Y-%m-%d %H:%M:%S} Asia/Jakarta',s,1)
def row(m):
 a=m.group(1);start=m.group(2);rest=m.group(3);return f'{a}{start} Asia/Jakarta|{str(n-datetime.strptime(start,"%Y-%m-%d %H:%M:%S")).split(".")[0]}|{rest}'
s=re.sub(r'(^\|[^\n]+\|)(2026-11-02 \d\d:\d\d:\d\d) Asia/Jakarta\|[^|]*\|([^\n]*)',row,s,flags=re.M)
if gap>60:s+=f'\n- Heartbeat SLA breach observed{gap:.0f}s during API authoring/review; no backdating.\n'
p.write_text(s,encoding='utf-8')
