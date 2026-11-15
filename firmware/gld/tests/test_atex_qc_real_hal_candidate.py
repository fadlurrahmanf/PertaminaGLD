"""Candidate QC service against actual SX126x/Module and fake HAL, no device."""
from pathlib import Path
import importlib.util, os, subprocess, tempfile, unittest
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];LIB=ROOT/'firmware/lib/RadioLib/src'
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
base=load('busy_fixtures',HERE/'test_atex_radiolib_busy.py');runtime=load('qc_body_fixtures',HERE/'test_atex_qc_runtime_candidate.py')
class Tests(unittest.TestCase):
 def test_busy_fail_closed_on_real_driver(self):
  src=(ROOT/'firmware/gld/src/GldUnifiedMain.cpp').read_text(encoding='utf8')
  start=runtime.function(src,'bool runAtexLoraTxAttempt(bool scanDuringRx) {');service=runtime.function(src,'void serviceAtexQcRadio() {')
  cpp=runtime.CPP
  for line in cpp.splitlines():
   if line.startswith('#define RADIOLIB_'):cpp=cpp.replace(line+'\n','')
  first=cpp.index('struct Radio {');last=cpp.index('} radio,*loraRadio=&radio;',first)+len('} radio,*loraRadio=&radio;')
  cpp=cpp[:first]+'SX126x* loraRadio=nullptr;'+cpp[last:]
  fake=base.HARNESS[base.HARNESS.index('struct FakeHal'):base.HARNESS.index('static void stuckAtEntry()')]
  cpp='#include <new>\n#include <cstring>\n#include "Module.h"\n#include "modules/SX126x/SX126x.h"\n'+fake+'\n'+cpp
  post=r'''int main(){
 FakeHal hal;Module mod(&hal,1,2,3,4);setup(mod);alignas(SX126x) unsigned char storage[sizeof(SX126x)]={};
 loraRadio=new(storage) SX126x(&mod);hal.busyAlways=true;
 assert(runAtexLoraTxAttempt(false));serviceAtexQcRadio();
 assert(atexQcSchedule.state()==pgl::gld::GldAtexQcSchedule::State::Fault);
 assert(!radioReady&&workflowSharedSpiQuarantined&&pgl::gld::datasetworkflowwifi::gate&&hal.txCount==0&&hal.csHigh);
 unsigned count=hal.txCount;serviceAtexQcRadio();assert(hal.txCount==count);
 // Test-only reset represents reboot: BUSY becomes stuck just after SET_TX.
 atexQcSchedule=pgl::gld::GldAtexQcSchedule{};radioReady=true;workflowSharedSpiQuarantined=false;
 pgl::gld::datasetworkflowwifi::gate=false;loraRxFlag=false;
 FakeHal hal2;Module mod2(&hal2,1,2,3,4);setup(mod2);alignas(SX126x) unsigned char storage2[sizeof(SX126x)]={};
 loraRadio=new(storage2) SX126x(&mod2);hal2.busyAfterTx=true;
 assert(runAtexLoraTxAttempt(false));serviceAtexQcRadio();
 assert(hal2.txCount==1&&atexQcSchedule.state()==pgl::gld::GldAtexQcSchedule::State::Fault);
 assert(!radioReady&&pgl::gld::datasetworkflowwifi::gate&&hal2.csHigh);
 serviceAtexQcRadio();assert(hal2.txCount==1);
 }'''
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);(d/'test.cpp').write_text(cpp+start+'\n'+service+post,encoding='utf8');exe=d/'test.exe';env=dict(os.environ)
   compiler=runtime.CXX;env['PATH']=str(Path(compiler).parent)+os.pathsep+env.get('PATH','')
   schedule=Path(os.environ.get('GLD_WORKFLOW_SCHEDULE',str(ROOT/'firmware/gld/include/GldWorkflowRadioSchedule.h')))
   (d/'GldWorkflowRadioSchedule.h').write_text(schedule.read_text(encoding='utf8'),encoding='utf8')
   cmd=[compiler,'-std=c++17','-static','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-DRADIOLIB_SPI_PARANOID=1','-DPGL_GLD_BOARD_PROFILE_GLD_ATEX=1','-DPGL_GLD_DATASET_WORKFLOW=1','-I'+str(d),'-I'+str(ROOT/'firmware/gld/include'),'-I'+str(LIB),str(d/'test.cpp'),str(LIB/'modules/SX126x/SX126x.cpp'),str(LIB/'Module.cpp'),str(LIB/'Hal.cpp'),str(LIB/'protocols/PhysicalLayer/PhysicalLayer.cpp'),str(LIB/'utils/Utils.cpp'),str(LIB/'utils/CRC.cpp'),str(LIB/'utils/FEC.cpp'),str(LIB/'modules/SX126x/SX126x_LR_FHSS.cpp'),'-o',str(exe)]
   for paranoid in ('0','1'):
    cmd[cmd.index('-DRADIOLIB_SPI_PARANOID=1')]='-DRADIOLIB_SPI_PARANOID='+paranoid
    subprocess.run(cmd,check=True,env=env);subprocess.run([str(exe)],check=True,env=env)
    cmd[cmd.index('-DRADIOLIB_SPI_PARANOID='+paranoid)]='-DRADIOLIB_SPI_PARANOID=1'
if __name__=='__main__':unittest.main()

