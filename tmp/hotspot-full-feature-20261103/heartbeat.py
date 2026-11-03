"""Coordinator-invoked snapshot; no background scheduler or hardware access."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
now = datetime.now(timezone.utc)
local = now.astimezone(timezone(timedelta(hours=7)))
ledger_path = HERE / 'compile-ledger.json'
ledger = json.loads(ledger_path.read_text())
rows = []
for task in ledger['tasks']:
    model = task['model']
    receipt_path = HERE / f'model{model}-build-receipt.json'
    if not receipt_path.exists():
        continue
    receipt = json.loads(receipt_path.read_text())
    task.update(worker=f'/root/compile_model{model}_native',
                state=receipt.get('status', 'unknown'),
                started_at=receipt.get('startUtc'), pid=receipt.get('pid'))
    if task['state'] == 'running':
        start = datetime.fromisoformat(task['started_at'])
        start_local = start.astimezone(timezone(timedelta(hours=7)))
        elapsed = str(now-start).split('.')[0]
        rows.append(f'|compile_model{model}_native|3.1 Compile Model {model}|'
                    f'{start_local:%Y-%m-%d %H:%M:%S} Asia/Jakarta|{elapsed}|'
                    f'0/1 build passed|Compiler running; isolated model{model} output|')
ledger_path.write_text(json.dumps(ledger, indent=2))
if ledger.get('rootWork'):
    work = ledger['rootWork']
    start = datetime.fromisoformat(work['startedAt'])
    elapsed = str(now-start).split('.')[0]
    rows.append(f"|Root|{work['item']}|{start.astimezone(timezone(timedelta(hours=7))):%Y-%m-%d %H:%M:%S} Asia/Jakarta|{elapsed}|{work['progress']}|{work['state']}|")
tracker = ROOT / 'docs/GLD-HOTSPOT-FULL-FEATURE-TRACKER.md'
text = tracker.read_text(encoding='utf-8-sig')
old = re.search(r'Last tracker heartbeat: ([\d :-]+)', text)[1].strip()
gap = (local.replace(tzinfo=None)-datetime.strptime(old, '%Y-%m-%d %H:%M:%S')).total_seconds()
text = re.sub(r'Last tracker heartbeat: .*',
              f'Last tracker heartbeat: {local:%Y-%m-%d %H:%M:%S} Asia/Jakarta', text)
start = text.index('## Current work / agent state')
end = text.index('## Evidence log')
text = text[:start] + ('## Current work / agent state\n\n'
    '|Sub-agent / worker|Active work item|Started at|Elapsed|Progress|Activity / state|\n'
    '|---|---|---|---|---|---|\n') + '\n'.join(rows) + '\n\n' + text[end:]
if gap > 60:
    text += f'\n- Heartbeat SLA breach: {gap:.0f}s before {local:%H:%M:%S}, coordinator checks; no backdating.\n'
tracker.write_text(text, encoding='utf-8')
print(json.dumps({'runningCompilers': sum(task['state'] == 'running' for task in ledger['tasks']),
                  'gapSeconds': round(gap)}))
