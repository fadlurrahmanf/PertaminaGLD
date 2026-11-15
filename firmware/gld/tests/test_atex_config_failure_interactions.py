from pathlib import Path
import importlib.util,os,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent;CXX=os.environ.get('CXX',r'C:\Users\MSI\.platformio\packages\toolchain-gccmingw32\bin\g++.exe')
spec=importlib.util.spec_from_file_location('qc_harness_synthetic',HERE/'test_atex_qc_runtime_candidate.py');qc=importlib.util.module_from_spec(spec);spec.loader.exec_module(qc)
spec2=importlib.util.spec_from_file_location('dataset_harness_synthetic',HERE/'run_workflow_radio_interaction.py');ds=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(ds)
class Tests(unittest.TestCase):
 def compile(self,folder,name,code):
  f=folder/(name+'.cpp');exe=folder/(name+'.exe');f.write_text(code,encoding='utf8');env=dict(os.environ);env['PATH']=str(Path(CXX).parent)+os.pathsep+env['PATH'];subprocess.run([CXX,'-std=c++17','-static','-DPGL_GLD_BOARD_PROFILE_GLD_ATEX=1','-I'+str(folder),'-I'+str(ROOT/'firmware/gld/include'),str(f),'-o',str(exe)],check=True,env=env);subprocess.run([str(exe)],check=True,env=env)
 def test_qc_tx_rx_and_dataset_lifecycle(self):
  src=(ROOT/'firmware/gld/src/GldUnifiedMain.cpp').read_text(encoding='utf8');latch=ds.function(src,'void latchAtexConfigPersistenceFault()');start=ds.function(src,'bool runAtexLoraTxAttempt(bool scanDuringRx) {');service=ds.function(src,'void serviceAtexQcRadio() {')
  pre=qc.CPP.replace('uint16_t nodeId=0x1001,chId=0x10,lastDownlinkCommandId=5;', 'uint8_t ctrlword=0xA3;uint16_t nodeId=0x1001,chId=0x10,lastDownlinkCommandId=5;')+'\nbool atexConfigPersistenceFault=false; namespace pgl { namespace gld { namespace datasetworkflowwifi { int failed=0; void failSession(const char*){++failed;} } } }\n'
  post=r'''
int main(){using S=pgl::gld::GldAtexQcSchedule::State;
 assert(runAtexLoraTxAttempt(false));serviceAtexQcRadio();assert(radio.starts==1);
 latchAtexConfigPersistenceFault();assert(!radioReady&&!lastInferenceValid&&!workflowAppliedRadio.valid);
 serviceAtexQcRadio();assert(atexQcSchedule.state()==S::Fault && events==1 && pgl::gld::datasetworkflowwifi::gate);
 int sends=radio.starts;serviceAtexQcRadio();assert(radio.starts==sends);
 atexQcSchedule=pgl::gld::GldAtexQcSchedule{};radio=Radio{};radioReady=true;lastInferenceValid=true;workflowAppliedRadio.valid=true;atexConfigPersistenceFault=false;pgl::gld::datasetworkflowwifi::gate=false;loraRxFlag=false;events=0;
 assert(runAtexLoraTxAttempt(false));serviceAtexQcRadio();radio.irq=RADIOLIB_SX126X_IRQ_TX_DONE;loraRxFlag=true;serviceAtexQcRadio();serviceAtexQcRadio();assert(atexQcSchedule.state()==S::Receiving);
 latchAtexConfigPersistenceFault();serviceAtexQcRadio();assert(atexQcSchedule.state()==S::Fault && events==1 && pgl::gld::datasetworkflowwifi::gate);
}
'''
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);self.compile(d,'qc',pre+latch+'\n'+start+'\n'+service+post)
   loop=src[src.index('void loop() {'):];begin=loop.index('    const bool leasedBeforeCommands =');marker='    if (atexQcSchedule.admissionHeld() || !serviceAtexWorkflowRadio()) pgl::gld::datasetworkflowwifi::poll();';end=loop.index(marker,begin)+len(marker)
   for name,text in [('workflow_service.inc',ds.function(src,'bool serviceAtexWorkflowRadio()')),('workflow_reject.inc',ds.function(src,'bool rejectWorkflowMutation(')),('workflow_quarantine.inc',ds.function(loop,'if (workflowSharedSpiQuarantined)')),('workflow_loop_control.inc',loop[begin:end])]: (d/name).write_text(text,encoding='utf8')
   harness=(HERE/'test_workflow_radio_interaction.cpp').read_text(encoding='utf8')
   config_marker='struct Config { bool aesKeyPresent; uint8_t aesKeyId; }'
   assert harness.count(config_marker)==1
   harness=harness.replace(config_marker, 'struct Config { bool aesKeyPresent; uint8_t aesKeyId; uint8_t ctrlword=0xA3; }')
   include_marker='#include "workflow_service.inc"'
   assert harness.count(include_marker)==1
   harness=harness.replace(include_marker, latch+'\n'+include_marker)
   cases=r'''
    reset();startTx();latchAtexConfigPersistenceFault();assert(incomplete && stopped && retained==2 && runtimeConfig.ctrlword==0);step();assert(workflowRadioScheduler.state()==State::Fault && radio.starts==1 && retained==2);step();assert(radio.starts==1);
    reset();startTx();enterRx();latchAtexConfigPersistenceFault();assert(incomplete && stopped && retained==2 && runtimeConfig.ctrlword==0);step();assert(radio.starts==1 && retained==2 && !sampling);
'''
   marker='    std::puts("ATEX production service interaction:';assert marker in harness;harness=harness.replace(marker,cases+marker);self.compile(d,'dataset',harness)
if __name__=='__main__':unittest.main()
