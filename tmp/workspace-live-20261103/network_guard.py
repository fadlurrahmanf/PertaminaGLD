"""Bounded independent safety net for this user-authorized GLD radio test."""
from pathlib import Path
import json, re, subprocess, sys, time
HERE=Path(__file__).resolve().parent
def current():
    text=subprocess.run(['netsh','wlan','show','interfaces'],capture_output=True,text=True,creationflags=0x08000000,timeout=10).stdout
    return re.findall(r'^\s*SSID\s*:\s*(.*?)\s*$',text,re.M)
def restore():
    before=current()
    report={'before':before,'restore_requested':False}
    if not before or any(s.startswith('GLD-DATASET-') for s in before):
        r=subprocess.run(['netsh','wlan','connect','name=ITB Guest','interface=Wi-Fi'],capture_output=True,text=True,creationflags=0x08000000,timeout=15)
        report.update(restore_requested=True,result=r.returncode)
        for _ in range(20):
            if 'ITB Guest' in current():break
            time.sleep(.5)
    report['after']=current()
    (HERE/'network-restored.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
if __name__=='__main__':
    done=HERE/sys.argv[1];limit=time.monotonic()+float(sys.argv[2])
    while time.monotonic()<limit and not done.exists():time.sleep(.5)
    # A completion flag is written only after the parent restored Internet.
    # Do not issue a late duplicate restoration into a subsequent radio test.
    if not done.exists():restore()
