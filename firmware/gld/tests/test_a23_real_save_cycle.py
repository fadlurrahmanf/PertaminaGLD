"""Document partial provisioning with production functions and synthetic NVS.

The passing test demonstrates the current limitation; it does not prove that
partial provisioning is safe, nor model flash power failure or actual AES bytes.
"""
from pathlib import Path
import os,sys,subprocess,tempfile,unittest
sys.path.insert(0,str(Path(__file__).parent))
import test_a23_recovery as baseline
SRC=baseline.SRC
class Tests(unittest.TestCase):
 def test_partial_save_then_reboot_and_provision(self):
  src=SRC.read_text(encoding='utf8');pre=baseline.PRE
  marker='size_t getBytesLength(const char*)'
  methods='''size_t putString(const char*k,const char*v){strings[k]=v;return strlen(v);}bool isKey(const char*k){return nums.count(k);}bool remove(const char*k){nums.erase(k);return true;}size_t putUChar(const char*k,uint8_t v){nums[k]=v;return 1;}size_t putBool(const char*k,bool v){nums[k]=v;return 1;}size_t putUShort(const char*k,uint16_t v){if(std::string(k)=="mqttPort" && failSave)return 0;nums[k]=v;return 2;}size_t putShort(const char*k,int16_t v){nums[k]=v;return 2;}size_t putULong(const char*k,uint32_t v){nums[k]=v;return 4;}size_t putFloat(const char*k,float v){floats[k]=v;return 4;}size_t putBytes(const char*k,const void*,size_t n){nums[k]=1;return n;}'''
  pre=pre.replace('struct Preferences{','bool failSave=false; bool fault=false; void latchAtexConfigPersistenceFault(){fault=true;}\nstruct Preferences{').replace(marker,methods+marker)
  a=pre.index('bool saveRuntimeConfig(){++saved;');b=pre.index('\nvoid rebootAfterAckIfRequested',a);pre=pre[:a]+'bool saveRuntimeConfig();'+pre[b:]
  signatures=['uint16_t nodeIdFromDeviceId(', 'int hexNibble(', 'bool validDeviceId(', 'void applySelfTestAesFallbackIfAllowed(', 'void resetRuntimeConfigDefaults(', 'void loadRuntimeConfig(', 'bool saveRuntimeConfig()', 'void onSetDeviceIdJson(']
  bodies='\n'.join(baseline.extract(src,s) for s in signatures)
  post=r'''int main(){
  strings["schema"]="synthetic";strings["deviceId"]="1A2B";nums["ctrlword"]=0xA3;nums["chId"]=0x25;nums["aesKeySet"]=1;nums["aesKeyId"]=3;nums["aesKey"]=1;nums["loraQcAutoTx"]=1;
  loadRuntimeConfig();assert(runtimeConfig.chId==0x25 && runtimeConfig.aesKeyPresent);
  failSave=true;assert(!saveRuntimeConfig() && nums["ctrlword"]==0 && fault);
  failSave=false;fault=false;loadRuntimeConfig();assert(runtimeConfig.ctrlword==0 && runtimeConfig.chId==0x10 && !runtimeConfig.aesKeyPresent && !loraAutoTransmit);
  onSetDeviceIdJson("{\"deviceId\":\"1A2C\",\"reboot\":false}");assert(ack=="ok" && nums["ctrlword"]==0xA3 && strings["deviceId"]=="1A2C");
  loadRuntimeConfig();assert(runtimeConfig.ctrlword==0xA3 && runtimeConfig.chId==0x10 && !runtimeConfig.aesKeyPresent && !loraAutoTransmit);
 }'''
  env=dict(os.environ);env['PATH']=str(Path(baseline.CXX).parent)+os.pathsep+env['PATH']
  with tempfile.TemporaryDirectory() as d:
   file=Path(d)/'t.cpp';exe=Path(d)/'t.exe'
   def run(body):
    file.write_text(pre+body+post,encoding='utf8');subprocess.run([baseline.CXX,'-std=c++17','-static','-DPGL_GLD_BOARD_PROFILE_WROOM_U1_N16R8=1','-DPGL_GLD_BOARD_PROFILE_GLD_ATEX=1','-DPGL_GLD_BOARD_PROFILE_GLD2=1','-DPGL_GLD_DATASET_WORKFLOW=1','-DGLD_ALLOW_SELFTEST_AES_FALLBACK=0','-I'+str(baseline.ROOT/'firmware/lib/ArduinoJson/src'),str(file),'-o',str(exe)],env=env,check=True);return subprocess.run([str(exe)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode
   self.assertEqual(run(bodies),0)
   old='ok = putStringChecked("deviceId", runtimeConfig.deviceId) && ok;';self.assertEqual(bodies.count(old),1)
   self.assertNotEqual(run(bodies.replace(old,'/* omitted */')),0)
if __name__=='__main__':unittest.main()
