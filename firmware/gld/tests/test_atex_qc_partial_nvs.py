from pathlib import Path
import os,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[3];SRC=ROOT/'firmware/gld/src/GldUnifiedMain.cpp';CXX=os.environ.get('CXX',r'C:\Users\MSI\.platformio\packages\toolchain-gccmingw32\bin\g++.exe')
def extract(s,signature):
 a=s.index(signature);b=s.index('{',a);depth=0
 for i in range(b,len(s)):
  if s[i]=='{':depth+=1
  elif s[i]=='}':
   depth-=1
   if depth==0:return s[a:i+1]
 raise ValueError(signature)
CPP=r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <map>
#include <string>
using String=std::string;
namespace pgl{namespace firmware{const char* CONFIG_SCHEMA_VERSION="synthetic";}}
constexpr uint8_t GLD_CTRL_WORD_VALUE=0xA3;
struct RuntimeConfig {uint8_t ctrlword=0xA3;char deviceId[17]="1001",wifiSsid[33]="s",wifiPassword[65]="p",mqttHost[65]="host",mqttUser[33]="u",mqttPass[65]="p",topicRoot[65]="t";uint16_t nodeId=0x1001,chId=0x10,mqttPort=1883,lastDownlinkCommandId=7,loraPreamble=8;float loraFreqMHz=921,loraBwKHz=125,loraTcxoVoltage=1.8f,loraXtalVoltage=0;uint8_t loraSf=7,loraCr=5,loraSyncWord=52,aesKeyId=1,aesKey[16]{};int8_t loraTxPowerDbm=10;bool aesKeyPresent=true;}runtimeConfig;
uint32_t loraTxIntervalMs=1000;bool loraTransmitFocus=true,loraTargetTransmitOnly=true,loraAutoTransmit=false;
std::map<std::string,uint32_t> nvs;std::map<std::string,std::string> strings;bool failFirstCtrlword=true, mutateBeforeFail=false,beginFail=false;std::string failKey;
bool radioReady=true,lastInferenceValid=true,atexConfigPersistenceFault=false;
struct Applied{bool valid=true;}workflowAppliedRadio;
int failSessions=0;namespace pgl{namespace gld{namespace datasetworkflowwifi{void failSession(const char*){++failSessions;}}}}
void latchAtexConfigPersistenceFault();
bool runtimeConfigValid();
struct Preferences {
 bool begin(const char*,bool){return !beginFail;} void end(){}
 size_t putString(const char* k,const char* v){strings[k]=v;return std::strlen(v);}String getString(const char* k,const char* d){return strings.count(k)?strings[k]:d;}
 bool isKey(const char* k){return nvs.count(k)>0;}bool remove(const char* k){nvs.erase(k);return true;}
 size_t putUChar(const char* k,uint8_t v){if(std::string(k)=="ctrlword" && failFirstCtrlword){failFirstCtrlword=false;if(mutateBeforeFail)nvs[k]=v;return 0;}nvs[k]=v;return 1;}
 size_t putBool(const char* k,bool v){if(failKey==k)return 0;nvs[k]=v;return 1;}size_t putUShort(const char* k,uint16_t v){nvs[k]=v;return 2;}size_t putShort(const char* k,int16_t v){nvs[k]=uint16_t(v);return 2;}
 size_t putULong(const char* k,uint32_t v){nvs[k]=v;return 4;}size_t putFloat(const char* k,float){nvs[k]=1;return 4;}
 size_t putBytes(const char* k,const void*,size_t n){nvs[k]=1;return n;}
};
'''
POST=r'''
int main(){
 nvs["ctrlword"]=0xA3;nvs["loraQcInt"]=10000;nvs["loraQcFocus"]=0;nvs["loraQcTarget"]=0;nvs["loraQcAutoTx"]=1;
 assert(!saveRuntimeConfig()); // user receives error
 // Before-write fake failure leaves the persisted marker and QC keys unchanged.
 assert(nvs["ctrlword"]==0xA3 && nvs["loraQcInt"]==10000 && nvs["loraQcFocus"]==0 && nvs["loraQcTarget"]==0 && nvs["loraQcAutoTx"]==1);
 assert(runtimeConfig.ctrlword==0 && atexConfigPersistenceFault && !radioReady && !lastInferenceValid && !workflowAppliedRadio.valid && failSessions==1);
 // A reported commit failure may still have changed the marker. No other key
 // is touched; this mock covers both persisted-marker outcomes.
 failFirstCtrlword=true;mutateBeforeFail=true;assert(!saveRuntimeConfig());
 assert(nvs["ctrlword"]==0 && nvs["loraQcInt"]==10000 && nvs["loraQcFocus"]==0 && nvs["loraQcTarget"]==0 && nvs["loraQcAutoTx"]==1);
 // prefs.begin failure latches radio/inference fault before any writes.
 atexConfigPersistenceFault=false;runtimeConfig.ctrlword=0xA3;radioReady=lastInferenceValid=true;beginFail=true;
 assert(!saveRuntimeConfig() && atexConfigPersistenceFault && !radioReady && !lastInferenceValid && !runtimeConfigValid());beginFail=false;
 // A different failure after marker invalidation still leaves writes in NVS;
 // the marker is invalid, and this mitigation does not claim atomicity.
 nvs["ctrlword"]=0xA3;failFirstCtrlword=false;mutateBeforeFail=false;failKey="loraQcTarget";atexConfigPersistenceFault=false;radioReady=lastInferenceValid=true;assert(!saveRuntimeConfig());
 assert(atexConfigPersistenceFault && !radioReady && !lastInferenceValid);
 assert(nvs["ctrlword"]==0 && nvs["loraQcInt"]==1000 && nvs["loraQcFocus"]==1 && nvs["loraQcTarget"]==0 && nvs["loraQcAutoTx"]==0);
}
'''
class Tests(unittest.TestCase):
 def test_real_save_failure_stops_before_writes(self):
  src=SRC.read_text(encoding='utf8');save=extract(src,'bool saveRuntimeConfig()');load=extract(src,'void loadRuntimeConfig()')
  self.assertIn('prefs.getULong("loraQcInt"',load);self.assertIn('prefs.getBool("loraQcFocus"',load);self.assertIn('runtimeConfig.ctrlword != GLD_CTRL_WORD_VALUE',load)
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);f=d/'t.cpp';exe=d/'t.exe';env=dict(os.environ);env['PATH']=str(Path(CXX).parent)+os.pathsep+env['PATH']
   def run(body,atex=1,workflow=1,gld2=1):
    f.write_text(CPP+extract(src,'bool runtimeConfigValid()')+extract(src,'void latchAtexConfigPersistenceFault()')+body+POST,encoding='utf8');subprocess.run([CXX,'-std=c++17','-static','-Wall','-Wextra','-Werror',f'-DPGL_GLD_DATASET_WORKFLOW={workflow}',f'-DPGL_GLD_BOARD_PROFILE_GLD_ATEX={atex}',f'-DPGL_GLD_BOARD_PROFILE_GLD2={gld2}','-DPGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8=1','-I'+str(ROOT/'firmware/gld/include'),str(f),'-o',str(exe)],check=True,env=env);return subprocess.run([str(exe)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode
   self.assertEqual(run(save),0)
   guard='if (!ok) { runtimeConfig.ctrlword = 0; latchAtexConfigPersistenceFault(); prefs.end(); return false; }'
   self.assertEqual(save.count(guard),1)
   # Negative control: remove the guard and the first reboot assertion fails.
   self.assertNotEqual(run(save.replace(guard,'')),0)
   # Legacy GLD1 still follows its prior code path; this mitigation is scoped.
   self.assertNotEqual(run(save,atex=0,workflow=1,gld2=0),0)
 def test_fault_blocks_mutations_and_radio_reinit(self):
  src=SRC.read_text(encoding='utf8');reject=extract(src,'bool rejectWorkflowMutation(');begin=extract(src,'bool beginLoraRadio() {');self.assertIn('if (atexConfigPersistenceFault) return false;',begin);self.assertIn('!atexConfigPersistenceFault',extract(src,'bool datasetWifiReady()'));self.assertIn('doc["configPersistenceFault"] = atexConfigPersistenceFault;',extract(src,'void emitStatusJson()'))
  pre=r"""
#include <cassert>
namespace pgl{namespace gld{enum class GldSerialCommandType{GetStatus,Restart,BeginLora,SetConfig};struct GldSerialCommand{GldSerialCommandType type;};struct GldAtexQcSchedule{enum class State{Idle,StartTx,Transmitting,Receiving,Fault};};struct GldWorkflowRadioSchedule{enum class State{Idle,Transmitting,Receiving,Fault};};namespace datasetworkflowwifi{bool ownsSession(){return false;}}}}
bool atexConfigPersistenceFault=true,workflowSharedSpiQuarantined=false;
struct Schedule{pgl::gld::GldAtexQcSchedule::State value=pgl::gld::GldAtexQcSchedule::State::Idle;bool admissionHeld(){return value!=pgl::gld::GldAtexQcSchedule::State::Idle;} auto state(){return value;}}atexQcSchedule;
struct Workflow{pgl::gld::GldWorkflowRadioSchedule::State value=pgl::gld::GldWorkflowRadioSchedule::State::Idle;auto state(){return value;}}workflowRadioScheduler;
bool workflowReadOnlyCommand(pgl::gld::GldSerialCommandType t){return t==pgl::gld::GldSerialCommandType::GetStatus;}
const char* workflowCommandName(pgl::gld::GldSerialCommandType){return "synthetic";}void emitCommandAck(const char*,const char*,const char*,bool){}
"""
  post=r"""
int main(){using namespace pgl::gld;assert(rejectWorkflowMutation({GldSerialCommandType::BeginLora}));assert(rejectWorkflowMutation({GldSerialCommandType::SetConfig}));assert(!rejectWorkflowMutation({GldSerialCommandType::GetStatus}));assert(!rejectWorkflowMutation({GldSerialCommandType::Restart}));atexQcSchedule.value=GldAtexQcSchedule::State::StartTx;assert(rejectWorkflowMutation({GldSerialCommandType::Restart}));atexQcSchedule.value=GldAtexQcSchedule::State::Receiving;assert(rejectWorkflowMutation({GldSerialCommandType::Restart}));atexQcSchedule.value=GldAtexQcSchedule::State::Fault;assert(!rejectWorkflowMutation({GldSerialCommandType::Restart}));atexQcSchedule.value=GldAtexQcSchedule::State::Idle;workflowRadioScheduler.value=GldWorkflowRadioSchedule::State::Transmitting;assert(rejectWorkflowMutation({GldSerialCommandType::Restart}));workflowRadioScheduler.value=GldWorkflowRadioSchedule::State::Fault;assert(!rejectWorkflowMutation({GldSerialCommandType::Restart}));workflowRadioScheduler.value=GldWorkflowRadioSchedule::State::Idle;atexConfigPersistenceFault=false;assert(!rejectWorkflowMutation({GldSerialCommandType::BeginLora}));}
"""
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);f=d/'x.cpp';exe=d/'x.exe';f.write_text(pre+reject+post,encoding='utf8');env=dict(os.environ);env['PATH']=str(Path(CXX).parent)+os.pathsep+env['PATH'];subprocess.run([CXX,'-std=c++17','-static','-DPGL_GLD_BOARD_PROFILE_GLD_ATEX=1',str(f),'-o',str(exe)],check=True,env=env);subprocess.run([str(exe)],check=True,env=env)
if __name__=='__main__':unittest.main()
