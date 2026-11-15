from pathlib import Path
import os, subprocess, tempfile, sys
ROOT=Path(__file__).resolve().parents[3]
def extract(text, signature):
 start=text.index(signature); openbrace=text.index('{',start); depth=0
 for i in range(openbrace,len(text)):
  if text[i]=='{': depth+=1
  elif text[i]=='}':
   depth-=1
   if depth==0:return text[start:i+1]
 raise ValueError(signature)
with tempfile.TemporaryDirectory() as d:
 d=Path(d); main=(ROOT/'firmware/gld/src/GldUnifiedMain.cpp').read_text(encoding='utf8'); workflow=(ROOT/'firmware/gld/src/GldDatasetWorkflowWifi.cpp').read_text(encoding='utf8')
 capture=extract(main,'bool captureDatasetWifi(')
 if '--negative-control' in sys.argv:
  needle='workflowCaptureInterrupted = true; return false;'
  assert needle in capture
  capture=capture.replace(needle, 'workflowCaptureInterrupted = true; return true;')
 (d/'capture.inc').write_text(capture,encoding='utf8'); (d/'acquire.inc').write_text(extract(workflow,'void acquireDueSample('),encoding='utf8')
 cxx=os.environ.get('CXX',r'C:\Users\MSI\.platformio\packages\toolchain-gccmingw32\bin\g++.exe');env=dict(os.environ);env['PATH']=str(Path(cxx).parent)+os.pathsep+env['PATH'];exe=d/'test.exe'
 subprocess.run([cxx,'-std=c++17','-static','-Wall','-Wextra','-Werror',f'-I{d}',str(ROOT/'firmware/gld/tests/test_workflow_sample_irq.cpp'),'-o',str(exe)],check=True,env=env);result=subprocess.run([str(exe)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 if '--negative-control' in sys.argv:
  assert result.returncode != 0, 'unsafe partial commit mutation survived'
  print('PASS unsafe partial-commit mutation rejected')
 else:
  assert result.returncode == 0
  print('PASS actual capture+acquire host fakes: eight IRQ positions, retry, sensor error, epoch/power')
