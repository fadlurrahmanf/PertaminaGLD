"""Bounded offline-capable runner; Internet restoration independent of Codex."""
from pathlib import Path
import subprocess,sys,uuid,json,os
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from network_guard import restore
done=HERE/('live-'+uuid.uuid4().hex+'.done')
guard=subprocess.Popen([sys.executable,str(HERE/'network_guard.py'),done.name,'180'],creationflags=0x08000000)
try:
    result=subprocess.run(['node',str(HERE/'live-browser.cjs')],cwd=str(HERE.parents[1]),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=165,creationflags=0x08000000)
    output=HERE/os.environ.get('GLD_QA_RUN','real-browser')
    output.mkdir(exist_ok=True)
    (output/'runner.stdout.txt').write_text(result.stdout,encoding='utf-8')
    (output/'runner.stderr.txt').write_text(result.stderr,encoding='utf-8')
    print(result.stdout);print(result.stderr);print('runner_exit',result.returncode)
except subprocess.TimeoutExpired:
    print('runner_timeout; inspect owned session before any retry')
finally:
    report=restore();done.write_text('done',encoding='utf-8');print(json.dumps({'network':report}))
