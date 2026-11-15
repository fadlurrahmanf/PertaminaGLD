"""Production load and device-ID handler with ArduinoJson and synthetic NVS."""
from pathlib import Path
import os,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[3]; SRC=ROOT/'firmware/gld/src/GldUnifiedMain.cpp'; CXX=os.environ.get('CXX',r'C:\Users\MSI\.platformio\packages\toolchain-gccmingw32\bin\g++.exe')
def extract(s,sig):
 a=s.index(sig);b=s.index('{',a);depth=0
 for i in range(b,len(s)):
  if s[i]=='{':depth+=1
  elif s[i]=='}':
   depth-=1
   if depth==0:return s[a:i+1]
 raise ValueError(sig)
PRE=r'''
#include <ArduinoJson.h>
#include <cassert>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <map>
#include <string>
using String=std::string;
namespace pgl{namespace firmware{const char* CONFIG_SCHEMA_VERSION="synthetic";}namespace gld{enum class GldAlarmControlMode{Auto};const char* gldAlarmControlModeName(GldAlarmControlMode){return "auto";}}}
constexpr uint8_t GLD_CTRL_WORD_VALUE=0xA3;constexpr uint16_t DEFAULT_NODE_ID=0x1001;constexpr uint32_t DEFAULT_TX_INTERVAL_MS=10000,LORA_FOCUS_MIN_INTERVAL_MS=1000,LORA_MAX_INTERVAL_MS=600000,LORA_CH_MIN_INTERVAL_MS=3000;
struct RuntimeConfig {uint8_t ctrlword=0;char deviceId[17]="1001",wifiSsid[33]="default",wifiPassword[65]="p",mqttHost[65]="host",mqttUser[33]="u",mqttPass[65]="p",topicRoot[65]="t";uint16_t nodeId=0x1001,chId=0x10,mqttPort=1883,lastDownlinkCommandId=0,loraPreamble=8;float loraFreqMHz=921,loraBwKHz=125,loraTcxoVoltage=1.8f,loraXtalVoltage=0;uint8_t loraSf=7,loraCr=5,loraSyncWord=52,aesKeyId=0,aesKey[16]{};int8_t loraTxPowerDbm=10;bool aesKeyPresent=false;}runtimeConfig;
uint32_t loraTxIntervalMs=10000;bool loraTransmitFocus=false,loraTargetTransmitOnly=false,loraAutoTransmit=true;pgl::gld::GldAlarmControlMode alarmControlMode=pgl::gld::GldAlarmControlMode::Auto; bool manualAlarmCommanded=false;
enum class RuntimeAesKeySource{None,Nvs,SelfTest};RuntimeAesKeySource runtimeAesKeySource=RuntimeAesKeySource::None;
const char* runtimeAesKeySourceName(){return "synthetic";}void logPrintf(const char*,...){}bool sawUntrusted=false;void logPrintln(const char* s){if(std::strcmp(s,"GLD_APP_CONFIG_LOAD=IDENTITY_UNTRUSTED")==0)sawUntrusted=true;}
std::map<std::string,uint32_t> nums;std::map<std::string,float> floats;std::map<std::string,std::string> strings;bool beginOk=true;
struct Preferences{bool begin(const char*,bool){return beginOk;}void end(){}String getString(const char*k,const char*d){return strings.count(k)?strings[k]:d;}uint8_t getUChar(const char*k,uint8_t d){return nums.count(k)?nums[k]:d;}uint16_t getUShort(const char*k,uint16_t d){return nums.count(k)?nums[k]:d;}int16_t getShort(const char*k,int16_t d){return nums.count(k)?nums[k]:d;}uint32_t getULong(const char*k,uint32_t d){return nums.count(k)?nums[k]:d;}bool getBool(const char*k,bool d){return nums.count(k)?nums[k]!=0:d;}float getFloat(const char*k,float d){return floats.count(k)?floats[k]:d;}size_t getBytesLength(const char*){return 16;}size_t getBytes(const char*,void* p,size_t n){std::memset(p,7,n);return n;}};
constexpr const char* DEFAULT_DEVICE_ID_STR="1001"; constexpr uint16_t GLD_CH_ID=0x10; constexpr const char* DEFAULT_WIFI_SSID="default"; constexpr const char* DEFAULT_WIFI_PASSWORD="p"; constexpr const char* DEFAULT_MQTT_HOST="host"; constexpr uint16_t DEFAULT_MQTT_PORT=1883; constexpr const char* DEFAULT_MQTT_USER="u"; constexpr const char* DEFAULT_MQTT_PASS="p"; constexpr const char* DEFAULT_TOPIC_ROOT="t";
void copyBounded(char* p,size_t n,const char* s){std::strncpy(p,s,n-1);p[n-1]=0;}
namespace pgl { namespace config { bool isProvisionableGldId(uint16_t n){return n>=0x1001 && n<=0xFEFF;} } }
void clearRuntimeAesKey(){runtimeConfig.aesKeyPresent=false;runtimeConfig.aesKeyId=0;std::memset(runtimeConfig.aesKey,0,16);}
namespace pgl { namespace gld { namespace selftest { constexpr uint8_t KEY_ID=77; const uint8_t AES_KEY[16]={1,2,3,4}; } } }bool validateRuntimeLoraConfig(RuntimeConfig&,char*,size_t){return true;}
void resetRuntimeLoraDefaults(){runtimeConfig.loraFreqMHz=921;runtimeConfig.loraBwKHz=125;runtimeConfig.loraSf=7;runtimeConfig.loraCr=5;runtimeConfig.loraSyncWord=52;runtimeConfig.loraTxPowerDbm=10;runtimeConfig.loraPreamble=8;runtimeConfig.loraTcxoVoltage=1.8f;runtimeConfig.loraXtalVoltage=0;}void buildRuntimeTopics(){}bool runtimeConfigValid(){return runtimeConfig.ctrlword==GLD_CTRL_WORD_VALUE;}

std::string ack;int saved=0;
void emitCommandAck(const char*,const char* status,const char*,bool){ack=status;}
bool fakeApAvailable=false; namespace pgl { namespace gld { namespace datasetworkflowwifi { bool available(){return fakeApAvailable;} void updateAtexRadioAutoTx(bool){} } } }
uint32_t lastTxMs=0;uint32_t millis(){return 1234;}
bool saveRuntimeConfig(){++saved;if(!beginOk)return false;nums["ctrlword"]=GLD_CTRL_WORD_VALUE;nums["loraQcAutoTx"]=loraAutoTransmit;strings["deviceId"]=runtimeConfig.deviceId;runtimeConfig.ctrlword=GLD_CTRL_WORD_VALUE;return true;}
void rebootAfterAckIfRequested(bool){}
'''
POST=r'''int main(){
 // Retain AP identity but do not mix non-identity values from an incomplete save.
 nums["ctrlword"]=0; nums["aesKeySet"]=1;nums["aesKeyId"]=1;nums["lastCmdId"]=42;nums["loraQcInt"]=1000;nums["loraQcFocus"]=1;nums["loraQcAutoTx"]=1;
 strings["schema"]="synthetic"; strings["deviceId"]="1A2B";strings["wifiSsid"]="PARTIAL";floats["loraFreq"]=922;
 loadRuntimeConfig(); assert(runtimeConfig.ctrlword==0 && runtimeConfig.lastDownlinkCommandId==0);
#if GLD_ALLOW_SELFTEST_AES_FALLBACK
 assert(runtimeConfig.aesKeyPresent && runtimeAesKeySource==RuntimeAesKeySource::SelfTest && runtimeConfig.aesKeyId==77);
#else
 assert(!runtimeConfig.aesKeyPresent);
#endif
 assert(std::string(runtimeConfig.deviceId)=="1A2B" && runtimeConfig.nodeId==0x1A2B);
#if PGL_GLD_BOARD_PROFILE_GLD_ATEX && PGL_GLD_DATASET_WORKFLOW
 assert(std::string(runtimeConfig.wifiSsid)=="default" && runtimeConfig.loraFreqMHz==921 && !loraAutoTransmit);
#else
 assert(std::string(runtimeConfig.wifiSsid)=="PARTIAL" && runtimeConfig.loraFreqMHz==922 && loraAutoTransmit);
#endif
 // Preserve existing ID/node behavior; flag malformed ID as untrusted.
#if PGL_GLD_BOARD_PROFILE_GLD_ATEX && PGL_GLD_DATASET_WORKFLOW
 for (const char* malformed : {"GGGG", "0000", "+ABC", "12"}) {
  strings["deviceId"]=malformed;sawUntrusted=false;loadRuntimeConfig();assert(std::string(runtimeConfig.deviceId)==malformed && runtimeConfig.nodeId==nodeIdFromDeviceId(malformed,DEFAULT_NODE_ID) && !loraAutoTransmit && sawUntrusted);
 }
 for (const char* legacy : {"0001", "FFFF", "abcd"}) {
  strings["deviceId"]=legacy;sawUntrusted=false;loadRuntimeConfig();assert(std::string(runtimeConfig.deviceId)==legacy && runtimeConfig.nodeId==nodeIdFromDeviceId(legacy,0) && !loraAutoTransmit && !sawUntrusted);
 }
#endif
 strings["deviceId"]="1A2B";
 // A complete valid record retains all persisted values and QC setting.
 nums["ctrlword"]=0xA3;nums["loraQcInt"]=10000;nums["loraQcFocus"]=0;nums["loraQcAutoTx"]=0;loadRuntimeConfig();
 assert(runtimeConfig.ctrlword==0xA3);assert(runtimeConfig.aesKeyPresent);assert(runtimeConfig.lastDownlinkCommandId==42);assert(std::string(runtimeConfig.wifiSsid)=="PARTIAL");assert(runtimeConfig.loraFreqMHz==922);
#if PGL_GLD_DATASET_WORKFLOW || !PGL_GLD_BOARD_PROFILE_GLD_ATEX
 assert(!loraAutoTransmit);
#else
 assert(loraAutoTransmit);
#endif
 // Schema mismatch is still invalid; ATEX discards non-identity fields only.
 strings["schema"]="incompatible";loadRuntimeConfig();assert(runtimeConfig.ctrlword==0 && std::string(runtimeConfig.deviceId)=="1A2B");
#if GLD_ALLOW_SELFTEST_AES_FALLBACK
 assert(runtimeConfig.aesKeyPresent && runtimeAesKeySource==RuntimeAesKeySource::SelfTest);
#else
 assert(!runtimeConfig.aesKeyPresent);
#endif
#if PGL_GLD_BOARD_PROFILE_GLD_ATEX && PGL_GLD_DATASET_WORKFLOW
 assert(std::string(runtimeConfig.wifiSsid)=="default" && runtimeConfig.loraFreqMHz==921 && !loraAutoTransmit);
#endif
 // Empty NVS is first boot: serial device-ID provisioning still reaches save.
 nums.clear();strings.clear();floats.clear();loadRuntimeConfig();assert(runtimeConfig.ctrlword==0 && std::string(runtimeConfig.deviceId)=="1001");
#if PGL_GLD_BOARD_PROFILE_GLD_ATEX && PGL_GLD_DATASET_WORKFLOW
 assert(!loraAutoTransmit);
#endif
 ack.clear();saved=0;onSetDeviceIdJson("{\"deviceId\":\"1002\",\"reboot\":false}");assert(ack=="ok" && saved==1 && std::string(runtimeConfig.deviceId)=="1002" && runtimeConfig.ctrlword==0xA3);
 // Simulate reboot after the first successful SET_DEVICE_ID; the persisted
 // Auto OFF state is visible and stays OFF until explicitly enabled.
 loadRuntimeConfig();
#if PGL_GLD_BOARD_PROFILE_GLD_ATEX && PGL_GLD_DATASET_WORKFLOW
 assert(runtimeConfig.ctrlword==GLD_CTRL_WORD_VALUE && !loraAutoTransmit);
 ack.clear();onSetLoraAutoTransmitJson("{\"enabled\":true}");assert(ack=="ok" && loraAutoTransmit && lastTxMs==1234);
 loadRuntimeConfig();assert(runtimeConfig.ctrlword==GLD_CTRL_WORD_VALUE && loraAutoTransmit);
#endif
 // Current AP identity guard remains effective and offers reboot:true path.
 fakeApAvailable=true;ack.clear();saved=0;onSetDeviceIdJson("{\"deviceId\":\"1003\",\"reboot\":false}");
#if PGL_GLD_BOARD_PROFILE_GLD_ATEX && PGL_GLD_DATASET_WORKFLOW
 assert(ack=="rejected" && saved==0 && std::string(runtimeConfig.deviceId)=="1002");
 ack.clear();onSetDeviceIdJson("{\"deviceId\":\"1003\",\"reboot\":true}");assert(ack=="ok" && saved==1);
#else
 assert(ack=="ok" && saved==1);
#endif
 fakeApAvailable=false;
 // Unavailable store does not autonomously start radio; provisioning is not latched.
 beginOk=false;runtimeConfig.ctrlword=0xA3;loadRuntimeConfig();
#if PGL_GLD_BOARD_PROFILE_GLD_ATEX && PGL_GLD_DATASET_WORKFLOW
 assert(runtimeConfig.ctrlword==0 && !loraAutoTransmit);ack.clear();saved=0;onSetDeviceIdJson("{\"deviceId\":\"1003\",\"reboot\":false}");assert(ack=="error" && saved==1);
#endif
}'''
class Tests(unittest.TestCase):
 def test_actual_loader_and_provisioning(self):
  src=SRC.read_text(encoding='utf8'); bodies='\n'.join(extract(src,x) for x in ['uint16_t nodeIdFromDeviceId(', 'int hexNibble(', 'bool validDeviceId(', 'void applySelfTestAesFallbackIfAllowed(', 'void resetRuntimeConfigDefaults(', 'void loadRuntimeConfig(', 'void onSetDeviceIdJson(', 'void onSetLoraAutoTransmitJson('])
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.cpp';exe=Path(d)/'x.exe';p.write_text(PRE+'\n'+bodies+'\n'+POST,encoding='utf8');env=dict(os.environ);env['PATH']=str(Path(CXX).parent)+os.pathsep+env['PATH']
   inc='-I'+str(ROOT/'firmware/lib/ArduinoJson/src')
   for at,wf,st in [(1,1,0),(0,1,0),(1,0,0),(1,1,1)]:
    subprocess.run([CXX,'-std=c++17','-static','-DPGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8=1',f'-DPGL_GLD_BOARD_PROFILE_GLD_ATEX={at}',f'-DPGL_GLD_BOARD_PROFILE_GLD2={at}',f'-DPGL_GLD_DATASET_WORKFLOW={wf}',f'-DGLD_ALLOW_SELFTEST_AES_FALLBACK={st}',inc,str(p),'-o',str(exe)],check=True,env=env)
    subprocess.run([str(exe)],check=True,env=env)
   controls=[('        resetRuntimeConfigDefaults();\n        copyBounded(runtimeConfig.deviceId', '        /* deliberately omitted */\n        copyBounded(runtimeConfig.deviceId'), ('        loraTransmitFocus = loraTargetTransmitOnly = false;\n        loraAutoTransmit = false;', '        loraTransmitFocus = loraTargetTransmitOnly = false;\n        loraAutoTransmit = true;')]
   for old,new in controls:
    self.assertEqual(bodies.count(old),1);p.write_text(PRE+'\n'+bodies.replace(old,new,1)+'\n'+POST,encoding='utf8')
    subprocess.run([CXX,'-std=c++17','-static','-DPGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8=1','-DPGL_GLD_BOARD_PROFILE_GLD_ATEX=1','-DPGL_GLD_BOARD_PROFILE_GLD2=1','-DPGL_GLD_DATASET_WORKFLOW=1','-DGLD_ALLOW_SELFTEST_AES_FALLBACK=0',inc,str(p),'-o',str(exe)],check=True,env=env)
    self.assertNotEqual(subprocess.run([str(exe)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode,0)
if __name__=='__main__':unittest.main()
