from pathlib import Path
import os, subprocess, tempfile, unittest
ROOT=Path(__file__).resolve().parents[3]
SRC=Path(os.environ.get('ATEX_AUDIT_SOURCE', ROOT/'firmware/gld/src/GldUnifiedMain.cpp'))
CXX=Path(r'C:\Users\MSI\.platformio\packages\toolchain-gccmingw32\bin\g++.exe')

def extract(source,signature):
 start=source.index(signature); brace=source.index('{',start); depth=0
 for i in range(brace,len(source)):
  if source[i]=='{': depth+=1
  elif source[i]=='}':
   depth-=1
   if depth==0:return source[start:i+1]
 raise AssertionError('body not found')

PRE=r'''
#include <ArduinoJson.h>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <cstdint>
struct Config { char deviceId[17]="1001"; uint16_t nodeId=0x1001; } runtimeConfig;
constexpr uint16_t DEFAULT_NODE_ID=0x1001;
std::string ackStatus,ackMessage; bool ackReboot=false,apActive=false,saveOk=true; int saves=0, rebuilds=0, reboots=0;
namespace pgl { namespace gld { namespace datasetworkflowwifi {bool available(){return apActive;} } } }
bool validDeviceId(const char* s) { if(!s||strlen(s)!=4) return false; for(int i=0;i<4;i++) if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='A'&&s[i]<='F')||(s[i]>='a'&&s[i]<='f'))) return false; return true; }
uint16_t nodeIdFromDeviceId(const char* s,uint16_t f){char* end=nullptr;auto v=strtoul(s,&end,16);return !end||*end?f:static_cast<uint16_t>(v);}
void emitCommandAck(const char*,const char* s,const char* m,bool r){ackStatus=s;ackMessage=m;ackReboot=r;}
void copyBounded(char* d,size_t n,const char* s){snprintf(d,n,"%s",s);}
void buildRuntimeTopics(){++rebuilds;} bool saveRuntimeConfig(){++saves;return saveOk;}
void logPrintf(const char*,...){} void rebootAfterAckIfRequested(bool v){if(v)++reboots;}
void reset(){runtimeConfig=Config{};ackStatus.clear();ackMessage.clear();ackReboot=false;apActive=true;saveOk=true;saves=rebuilds=reboots=0;}
'''
POST=r'''
int main(){
 reset();onSetDeviceIdJson("{\"deviceId\":\"1002\",\"reboot\":false}");
#if PGL_GLD_BOARD_PROFILE_GLD_ATEX && PGL_GLD_DATASET_WORKFLOW
 assert(ackStatus=="rejected" && ackMessage.find("reboot:true")!=std::string::npos && !ackReboot && saves==0 && rebuilds==0 && reboots==0 && std::string(runtimeConfig.deviceId)=="1001");
#else
 assert(ackStatus=="ok" && saves==1 && std::string(runtimeConfig.deviceId)=="1002" && !ackReboot && reboots==0);
#endif
 reset();onSetDeviceIdJson("{\"deviceId\":\"1001\",\"reboot\":false}");assert(ackStatus=="ok" && saves==1 && reboots==0 && !ackReboot);
 reset();apActive=false;onSetDeviceIdJson("{\"deviceId\":\"1002\",\"reboot\":false}");assert(ackStatus=="ok" && saves==1 && reboots==0 && !ackReboot);
 reset();onSetDeviceIdJson("{\"deviceId\":\"1002\",\"reboot\":true}");assert(ackStatus=="ok" && saves==1 && reboots==1 && ackReboot);
 reset();saveOk=false;onSetDeviceIdJson("{\"deviceId\":\"1002\",\"reboot\":true}");assert(ackStatus=="error" && saves==1 && reboots==0 && !ackReboot);
 reset();onSetDeviceIdJson("{\"deviceId\":\"1002\",\"nodeId\":\"1003\",\"reboot\":false}");assert(ackStatus=="rejected" && saves==0);
}
'''
class Tests(unittest.TestCase):
 def test_production_handler_all_profiles_and_negative_control(self):
  src=SRC.read_text(encoding='utf8');body=extract(src,'void onSetDeviceIdJson('); test_marker='if (!reboot && pgl::gld::datasetworkflowwifi::available() &&'
  self.assertEqual(body.count(test_marker),1)
  with tempfile.TemporaryDirectory(prefix='atex-id-rebind-') as temp:
   env=dict(os.environ);env['PATH']=str(CXX.parent)+os.pathsep+env['PATH']; cpp=Path(temp)/'case.cpp';exe=Path(temp)/'case.exe'
   for at,wf,mutate in ((1,1,0),(0,1,0),(1,0,0),(1,1,1)):
    handler=body.replace(test_marker,'if (false && pgl::gld::datasetworkflowwifi::available() &&',1) if mutate else body
    cpp.write_text(PRE+handler+POST,encoding='utf8');subprocess.run([str(CXX),'-std=c++17','-static',f'-DPGL_GLD_BOARD_PROFILE_GLD_ATEX={at}',f'-DPGL_GLD_DATASET_WORKFLOW={wf}','-I'+str(ROOT/'firmware/lib/ArduinoJson/src'),str(cpp),'-o',str(exe)],check=True,env=env,timeout=60)
    rc=subprocess.run([str(exe)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30).returncode
    if mutate:self.assertNotEqual(rc,0)
    else:self.assertEqual(rc,0)
if __name__=='__main__': unittest.main()


