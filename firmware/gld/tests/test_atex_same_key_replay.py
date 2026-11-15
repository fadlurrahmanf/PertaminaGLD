from pathlib import Path
import os,subprocess,tempfile,unittest,importlib.util,sys
from unittest import mock
ROOT=Path(__file__).resolve().parents[3]; SRC=ROOT/'firmware/gld/src/GldUnifiedMain.cpp';CXX=os.environ.get('CXX',r'C:\Users\MSI\.platformio\packages\toolchain-gccmingw32\bin\g++.exe')
def extract(s,signature):
 a=s.index(signature);b=s.index('{',a);depth=0
 for i in range(b,len(s)):
  if s[i]=='{':depth+=1
  elif s[i]=='}':
   depth-=1
   if depth==0:return s[a:i+1]
 raise ValueError(signature)
PRE=r'''
#include <ArduinoJson.h>
#include <cassert>
#include <cstring>
#include <cstdint>
#include <cstdio>
#include <cctype>
#include <string>
struct RuntimeConfig {char wifiSsid[33]="ssid",wifiPassword[65]="pw",mqttHost[65]="host",mqttUser[33]="user",mqttPass[65]="pass",topicRoot[65]="topic";uint16_t mqttPort=1883;uint8_t aesKey[16]{},aesKeyId=1;bool aesKeyPresent=true;uint16_t lastDownlinkCommandId=42;}runtimeConfig,persisted;
enum class RuntimeAesKeySource{Nvs};RuntimeAesKeySource runtimeAesKeySource;
std::string ack;int saves=0;bool saveOk=true;
void emitCommandAck(const char*,const char* status,const char*,bool){ack=status;}
bool hasRuntimeLoraPatch(JsonDocument&){return false;}bool applyRuntimeLoraPatch(JsonDocument&,char*,size_t){return true;}
void copyBounded(char* out,size_t n,const char* in){std::memmove(out,in,std::strlen(in)+1);out[n-1]=0;}
void clearRuntimeAesKey(){runtimeConfig.aesKeyPresent=false;runtimeConfig.aesKeyId=0;std::memset(runtimeConfig.aesKey,0,16);}
void buildRuntimeTopics(){}bool saveRuntimeConfig(){++saves;if(!saveOk)return false;persisted=runtimeConfig;return true;}
void logPrintf(const char*,...){}bool applyLoraRuntimeNowIfNeeded(bool,bool&){return true;}void logRuntimeLoraConfig(const char*,bool,bool){}
struct Mqtt{void disconnect(){}}mqtt;struct Wifi{void disconnect(bool){}}WiFi;void rebootAfterAckIfRequested(bool){}
'''
POST=r'''
void reset(){runtimeConfig=RuntimeConfig{};for(int i=0;i<16;++i)runtimeConfig.aesKey[i]=i;persisted=runtimeConfig;ack.clear();saves=0;saveOk=true;}
int main(int argc,char** argv){
 if(argc>1){reset();onSetAppConfigJson(argv[1]);assert(ack=="ok" && persisted.aesKeyPresent && persisted.lastDownlinkCommandId==42);return 0;}
 reset();onSetAppConfigJson("{\"aesKeyHex\":\"000102030405060708090A0B0C0D0E0F\",\"keyId\":1,\"reboot\":false}");assert(ack=="ok"&&saves==1);
#if PGL_GLD_BOARD_PROFILE_GLD_ATEX && PGL_GLD_DATASET_WORKFLOW
 assert(runtimeConfig.lastDownlinkCommandId==42 && persisted.lastDownlinkCommandId==42);
 reset();onSetAppConfigJson("{\"aesKeyHex\":\"000102030405060708090A0B0C0D0E0F\",\"keyId\":2}");assert(ack=="ok" && persisted.lastDownlinkCommandId==42 && persisted.aesKeyId==2);
 reset();onSetAppConfigJson("{\"clearAesKey\":true,\"aesKeyHex\":\"000102030405060708090A0B0C0D0E0F\"}");assert(ack=="ok" && saves==1 && persisted.lastDownlinkCommandId==42 && persisted.aesKeyPresent);
 reset();onSetAppConfigJson("{\"clearAesKey\":true,\"gldAes128KeyHex\":\"100102030405060708090A0B0C0D0E0F\"}");assert(ack=="ok" && persisted.aesKeyPresent && persisted.lastDownlinkCommandId==0);
 const char* invalid[]={"{\"aesKeyHex\":\"\",\"gldAes128KeyHex\":\"000102030405060708090A0B0C0D0E0F\"}","{\"aesKeyHex\":null}","{\"gldAes128KeyHex\":7}","{\"GLD_AES128_KEY_HEX\":\"\"}","{\"aesKeyHex\":\"000102030405060708090A0B0C0D0E0F\",\"gldAes128KeyHex\":\"100102030405060708090A0B0C0D0E0F\"}","{\"GLD_AES128_KEY_HEX\":\"z00102030405060708090A0B0C0D0E0F\"}"};
 for(const char* command:invalid){reset();onSetAppConfigJson(command);assert(ack=="rejected"&&saves==0&&runtimeConfig.lastDownlinkCommandId==42);}
 reset();onSetAppConfigJson("{\"aesKeyHex\":\"000102030405060708090A0B0C0D0E0F\",\"GLD_AES128_KEY_HEX\":\"00:01:02:03:04:05:06:07:08:09:0a:0b:0c:0d:0e:0f\"}");assert(ack=="ok" && persisted.lastDownlinkCommandId==42);
#else
 assert(runtimeConfig.lastDownlinkCommandId==0 && persisted.lastDownlinkCommandId==0);
 reset();onSetAppConfigJson("{\"clearAesKey\":true,\"aesKeyHex\":\"000102030405060708090A0B0C0D0E0F\"}");assert(ack=="ok" && persisted.aesKeyPresent && persisted.lastDownlinkCommandId==0);
#endif
 reset();onSetAppConfigJson("{\"aesKeyHex\":\"100102030405060708090A0B0C0D0E0F\"}");assert(ack=="ok" && persisted.lastDownlinkCommandId==0);
 reset();onSetAppConfigJson("{\"clearAesKey\":true}");assert(ack=="ok" && !persisted.aesKeyPresent && persisted.lastDownlinkCommandId==0);
 reset();onSetAppConfigJson("{\"mqttHost\":\"other\"}");assert(ack=="ok" && persisted.lastDownlinkCommandId==42);
 reset();saveOk=false;onSetAppConfigJson("{\"aesKeyHex\":\"000102030405060708090A0B0C0D0E0F\"}");assert(ack=="error");
}
'''
class Tests(unittest.TestCase):
 def test_profiles_and_mutation(self):
  source=SRC.read_text(encoding='utf8'); body=extract(source,'void onSetAppConfigJson('); parser=extract(source,'int hexNibble(')+'\n'+extract(source,'bool parseAesKeyHex(')
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);env=dict(os.environ);env['PATH']=str(Path(CXX).parent)+os.pathsep+env['PATH']
   def run(atex,workflow,mutated=False):
    f=d/'test.cpp';exe=d/'test.exe';code=body.replace('sameDownlinkKey ? previousDownlinkId : 0', '0') if mutated else body
    f.write_text(PRE+parser+code+POST,encoding='utf8');subprocess.run([CXX,'-std=c++17','-static',f'-DPGL_GLD_BOARD_PROFILE_GLD_ATEX={atex}',f'-DPGL_GLD_DATASET_WORKFLOW={workflow}','-I'+str(ROOT/'firmware/lib/ArduinoJson/src'),str(f),'-o',str(exe)],check=True,env=env);return subprocess.run([str(exe)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode
   self.assertEqual(run(1,1),0);self.assertEqual(run(0,1),0);self.assertEqual(run(1,0),0);self.assertNotEqual(run(1,1,True),0)
   # Real bridge injection helper with a synthetic key, fed to the real
   # production handler. No server config or actual serial device is read.
   sys.path.insert(0,str(ROOT/'apps/gld-operator'));spec=importlib.util.spec_from_file_location('synthetic_gld_bridge',ROOT/'apps/gld-operator/bridge.py');bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
   with mock.patch.object(bridge,'load_canonical_gld_aes_key',return_value={'aesKeyHex':'000102030405060708090A0B0C0D0E0F','keyId':1}):
    line,injected=bridge.inject_canonical_aes_key('SET_APP_CONFIG_JSON {"clearAesKey":true}')
   self.assertTrue(injected);self.assertTrue(line.startswith('SET_APP_CONFIG_JSON '))
   # Recompile ATEX non-mutated; do not print command or synthetic key.
   self.assertEqual(run(1,1),0);subprocess.run([str(d/'test.exe'),line[len('SET_APP_CONFIG_JSON '):]],check=True,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
if __name__=='__main__':unittest.main()
