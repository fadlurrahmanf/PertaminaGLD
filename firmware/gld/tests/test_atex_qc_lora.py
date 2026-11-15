from pathlib import Path
import os,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[3]; MAIN=ROOT/'firmware/gld/src/GldUnifiedMain.cpp'; CXX=os.environ.get('CXX',r'C:\Users\MSI\.platformio\packages\toolchain-gccmingw32\bin\g++.exe')
def extract(s,sign):
 start=s.index(sign); pos=s.index('{',start); depth=0
 for i in range(pos,len(s)):
  if s[i]=='{': depth+=1
  elif s[i]=='}':
   depth-=1
   if depth==0:return s[start:i+1]
 raise ValueError(sign)
class QCLora(unittest.TestCase):
 def test_real_command_handlers_profiles(self):
  src=MAIN.read_text(encoding='utf8');a=extract(src,'void onSetLoraAutoTransmitJson(');b=extract(src,'void onManualLoraTxFromSerialCommand(')
  pre=r'''
#include <ArduinoJson.h>
#include <cassert>
#include <string>
#include <cstdint>
namespace pgl { namespace gld { enum class GldMode {INFERENCE,DATASET}; bool readGldExternalPower(){return true;} } }
bool external24VPowerMode=true,batteryPowerMode=false;
pgl::gld::GldMode currentMode=pgl::gld::GldMode::INFERENCE;
bool loraAutoTransmit=true,radioReady=true,lastLoraTxOk=true,saveOk=true;
void* loraRadio=reinterpret_cast<void*>(1); uint32_t lastTxMs=0;
uint32_t millis(){return 456;} bool saveRuntimeConfig(){return saveOk;}
std::string ack; void emitAtexManualPendingAck(){ack="ok";} void emitCommandAck(const char*,const char* status,const char*,bool){ack=status;}
int atexCalls=0,gld1Calls=0;bool runAtexLoraTxAttempt(){++atexCalls;return true;} void runGld1LoraTxAttempt(){++gld1Calls;}
'''
  post=r'''
int main(){
#if PGL_GLD_BOARD_PROFILE_GLD_ATEX || !PGL_GLD_BOARD_PROFILE_GLD2
 onSetLoraAutoTransmitJson("{\"enabled\":false}");assert(!loraAutoTransmit && ack=="ok" && lastTxMs==456);
 saveOk=false;onSetLoraAutoTransmitJson("{\"enabled\":true}");assert(!loraAutoTransmit && ack=="error");
 onSetLoraAutoTransmitJson("{\"enabled\":1}");assert(ack=="rejected");
 onManualLoraTxFromSerialCommand();assert(ack=="ok");
#if PGL_GLD_BOARD_PROFILE_GLD_ATEX
 assert(atexCalls==1 && gld1Calls==0);
#else
 assert(atexCalls==0 && gld1Calls==1);
#endif
 currentMode=pgl::gld::GldMode::DATASET;onManualLoraTxFromSerialCommand();assert(ack=="rejected");
 currentMode=pgl::gld::GldMode::INFERENCE;loraAutoTransmit=true;onManualLoraTxFromSerialCommand();assert(ack=="rejected");
 loraAutoTransmit=false;radioReady=false;onManualLoraTxFromSerialCommand();assert(ack=="rejected");
#else
 onSetLoraAutoTransmitJson("{\"enabled\":false}");assert(ack=="rejected" && loraAutoTransmit);
 onManualLoraTxFromSerialCommand();assert(ack=="rejected" && !atexCalls && !gld1Calls);
#endif
}
'''
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);f=d/'t.cpp';f.write_text(pre+a+'\n'+b+post,encoding='utf8');env=dict(os.environ);env['PATH']=str(Path(CXX).parent)+os.pathsep+env['PATH']
   for name,atex,gld2 in [('atex',1,1),('gld1',0,0),('gld2',0,1)]:
    exe=d/(name+'.exe');cmd=[CXX,'-std=c++17','-static',f'-DPGL_GLD_BOARD_PROFILE_GLD_ATEX={atex}',f'-DPGL_GLD_BOARD_PROFILE_GLD2={gld2}','-DPGL_GLD_DATASET_WORKFLOW=1','-DPGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8=1','-I'+str(ROOT/'firmware/lib/ArduinoJson/src'),str(f),'-o',str(exe)];subprocess.run(cmd,check=True,env=env);subprocess.run([str(exe)],check=True,env=env)
 def test_atex_pending_ack_actual_serialization(self):
  src=MAIN.read_text(encoding='utf8'); helper=extract(src,'void emitAtexManualPendingAck()')
  pre=r"""
#include <ArduinoJson.h>
#include <cassert>
#include <cstring>
#include <cstdint>
struct Config {const char* deviceId="1001";uint16_t nodeId=0x1001,chId=0x10;} runtimeConfig;
namespace pgl {namespace gld {const char* gldModeName(int){return "inference";}}}
int currentMode=0;uint32_t millis(){return 17;}void formatHex4(uint16_t,char* b,size_t){strcpy(b,"0010");}
bool checked=false;
template <typename T> void rawJsonLine(const char* prefix,T& doc){
 assert(!strcmp(prefix,"GLD_CMD_ACK_JSON"));assert(!strcmp(doc["cmd"].template as<const char*>(),"MANUAL_LORA_TX"));
 assert(!strcmp(doc["status"].template as<const char*>(),"ok"));assert(!strcmp(doc["completion"].template as<const char*>(),"pending"));checked=true;
}
"""
  post='int main(){emitAtexManualPendingAck();assert(checked);}'
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);f=d/'t.cpp';exe=d/'t.exe';f.write_text(pre+helper+post);env=dict(os.environ);env['PATH']=str(Path(CXX).parent)+os.pathsep+env['PATH'];subprocess.run([CXX,'-std=c++17','-static','-I'+str(ROOT/'firmware/lib/ArduinoJson/src'),str(f),'-o',str(exe)],check=True,env=env);subprocess.run([str(exe)],check=True,env=env)
 def test_actual_preview_exact_bytes_and_clear(self):
  src=MAIN.read_text(encoding='utf8'); start=src.index('struct AtexLoraTxPreview {'); end=src.index('\n#endif',start); block=src[start:end]
  pre=r"""
#include <cassert>
#include <cstdint>
#include <cstring>
namespace pgl{namespace protocol{constexpr int APPFRAME_OVERHEAD=10,STAR_MAX_PAYLOAD=54;}}
"""
  post=r"""
int main(){uint8_t data[]={0,0x9a,0xff};char hex[32];captureAtexLoraTxPreview(data,3);writeAtexLoraTxPreviewHex(hex,sizeof(hex));assert(!strcmp(hex,"009AFF") && atexLoraTxPreview.length==3);
 char small[2]={'x',0};writeAtexLoraTxPreviewHex(small,sizeof(small));assert(small[0]==0);
 captureAtexLoraTxPreview(nullptr,3);writeAtexLoraTxPreviewHex(hex,sizeof(hex));assert(!atexLoraTxPreview.valid && !hex[0]);
 captureAtexLoraTxPreview(data,65);assert(!atexLoraTxPreview.valid && atexLoraTxPreview.length==0);}
"""
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);f=d/'t.cpp';exe=d/'t.exe';f.write_text(pre+block+post,encoding='utf8');env=dict(os.environ);env['PATH']=str(Path(CXX).parent)+os.pathsep+env['PATH'];subprocess.run([CXX,'-std=c++17','-static',str(f),'-o',str(exe)],check=True,env=env);subprocess.run([str(exe)],check=True,env=env)
 def test_actual_persistence_expressions(self):
  src=MAIN.read_text(encoding='utf8')
  def atex_block(needle):
   i=src.index(needle); a=src.rfind('#if defined(PGL_GLD_DATASET_WORKFLOW)',0,i); b=src.index('#else',i); return src[src.index('\n',a)+1:b]
  load=atex_block('loraTxIntervalMs = prefs.getULong("loraQcInt"')
  save=atex_block('ok = prefs.putULong("loraQcInt"')
  pre=r"""
#include <cassert>
#include <cstdint>
#include <map>
#include <string>
bool loraTransmitFocus=true,loraTargetTransmitOnly=true,loraAutoTransmit=false,ok=true; uint32_t loraTxIntervalMs=1234;
struct Prefs {std::map<std::string,uint32_t> m;bool fail=false;uint32_t getULong(const char* k,uint32_t d){return m.count(k)?m[k]:d;}bool getBool(const char* k,bool d){return getULong(k,d);}
unsigned putULong(const char* k,uint32_t v){if(fail)return 0;m[k]=v;return sizeof(uint32_t);}unsigned putBool(const char* k,bool v){if(fail)return 0;m[k]=v;return sizeof(uint8_t);}} prefs;
void save(){
"""
  post=r"""
}
int main(){save();assert(ok && prefs.m["loraQcInt"]==1234 && prefs.m["loraQcFocus"]==1 && prefs.m["loraQcTarget"]==1 && prefs.m["loraQcAutoTx"]==0);
 loraTxIntervalMs=10000;loraTransmitFocus=loraTargetTransmitOnly=false;loraAutoTransmit=true;load();assert(loraTxIntervalMs==1234 && loraTransmitFocus && loraTargetTransmitOnly && !loraAutoTransmit);
 prefs.fail=true;ok=true;save();assert(!ok);}
"""
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);f=d/'t.cpp';exe=d/'t.exe';f.write_text(pre+save+'}\nvoid load(){\n'+load+post,encoding='utf8');env=dict(os.environ);env['PATH']=str(Path(CXX).parent)+os.pathsep+env['PATH'];subprocess.run([CXX,'-std=c++17','-static',str(f),'-o',str(exe)],check=True,env=env);subprocess.run([str(exe)],check=True,env=env)
 def test_guarded_scope_and_dataset_exclusion(self):
  s=MAIN.read_text(encoding='utf8');
  for key in ['loraQcInt','loraQcFocus','loraQcTarget','loraQcAutoTx']:
   self.assertIn('prefs.get',s);self.assertIn('prefs.put',s);self.assertGreaterEqual(s.count('"'+key+'"'),4)
  info=extract(s,'void emitInfoJson(');self.assertIn('StaticJsonDocument<3072> doc;',info);self.assertIn('GLD_INFO_JSON_OVERFLOW capacity=3072 ATEX',info)
  service=extract(s,'bool serviceAtexWorkflowRadio(');self.assertIn('loraAutoTransmit && !loraTransmitFocus && !loraTargetTransmitOnly',service)
  run=extract(s,'bool runAtexLoraTxAttempt(bool scanDuringRx) {');self.assertIn('loraTargetTransmitOnly',run);self.assertIn('loraTransmitFocus',run);self.assertNotIn('->transmit(',run)
if __name__=='__main__':unittest.main()
