"""Production network guards with fake MQTT and ArduinoJson; no hardware/network."""
from pathlib import Path
import os, re, subprocess, tempfile, unittest
ROOT=Path(__file__).resolve().parents[3]; SRC=ROOT/'firmware/gld/src/GldUnifiedMain.cpp'
CXX=os.environ.get('CXX',r'C:\Users\MSI\.platformio\packages\toolchain-gccmingw32\bin\g++.exe')
def extract(src, signature):
    start=src.index(signature); brace=src.index('{',start); depth=0
    for i in range(brace,len(src)):
        if src[i]=='{': depth+=1
        elif src[i]=='}':
            depth-=1
            if depth==0:return src[start:i+1]
    raise AssertionError(signature)
PRE=r"""
#include <ArduinoJson.h>
#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
using byte=unsigned char;
constexpr unsigned char GLD_CTRL_WORD_VALUE=0xA3;
struct Config {unsigned char ctrlword=0; char deviceId[17]="1001", wifiSsid[33]="partial", mqttHost[65]="broker";}runtimeConfig;
bool atexConfigPersistenceFault=false;
struct Mqtt {bool online=true;int loops=0,publishes=0;bool connected(){return online;} void loop(){++loops;} bool publish(const char*,const char*,bool){++publishes;return true;}}mqtt;
char topicData[]="d",topicAck[]="a",topicStatus[]="s",topicSummary[]="u",topicCmd[]="cmd",topicDataset[]="dataset";
int connects=0,cmds=0,datasets=0;bool mqttConnect(){++connects;return true;}
void handleCmdTopic(const char*,unsigned){++cmds;} void handleDatasetTopic(const char*,unsigned){++datasets;}
uint32_t millis(){return 123;} void logPrintf(const char*,...){}
struct DatasetQueuedPayload{char payload[100]="x";size_t len=1;uint32_t seq=1;}datasetQueue[4];
constexpr uint8_t DATASET_QUEUE_CAPACITY=4,DATASET_QUEUE_FLUSH_PER_LOOP=2;
uint8_t datasetQueueCount=1,datasetQueueHead=0;uint32_t datasetQueueRetryCount=0,datasetQueueRetryFailCount=0,datasetPublishFailCount=0,datasetQueueDropped=0,datasetRejectedSamples=0,datasetSeq=0,sessionStartMs=0;
uint8_t nullingProfileId=1,lastDatasetRejectStatus=0,lastDatasetRejectGain=0,lastDatasetRejectOkFiniteCount=0;int lastDatasetRejectChannel=0;bool lastDatasetRejectSaturated=false;char currentLabel[]="test";
namespace pgl{namespace gld{
bool readGldExternalPower(){return true;}
enum class GldMode {NULLING, DATASET};
struct GldWorkflowRadioSchedule {enum class State {Idle,Fault};State state(){return State::Idle;}};
enum class GldDatasetRejectReason {None}; GldDatasetRejectReason unused;
const char* gldDatasetRejectReasonName(GldDatasetRejectReason){return "synthetic";}
struct GldDatasetValidationResult {GldDatasetRejectReason reason;uint8_t okFiniteCount;int channel;};
struct GldDatasetChannelSample {const char* feature;int status,gain;bool saturated;float voltage;};
constexpr int GLD_DATASET_FEATURE_COUNT=8;const char* GLD_DATASET_CANONICAL_FEATURE_ORDER[8]={"1","2","3","4","5","6","7","8"};
}}
pgl::gld::GldDatasetRejectReason lastDatasetRejectReason=pgl::gld::GldDatasetRejectReason::None;
pgl::gld::GldWorkflowRadioSchedule workflowRadioScheduler;
pgl::gld::GldMode currentMode=pgl::gld::GldMode::DATASET;
enum class DatasetState {Idle,Running};DatasetState datasetState=DatasetState::Idle;
bool batteryPowerMode=false,external24VPowerMode=true,nullingRetryArmed=false,fullScaleSweepActive=false,powerTransitionShutdownPending=false,adsReady=true,dacReady=true,nullingProfileApplied=true;
"""
POST=r"""
int main(){
 char data[]="{}"; char cmd[]="cmd";
#if PGL_GLD_BOARD_PROFILE_GLD_ATEX
 assert(!runtimeConfigValid() && !atexNativeConfigTrusted() && !workflowNativeNetworkConfigured());
 mqtt.online=false;maintainMqtt();assert(connects==0);mqtt.online=true;
 maintainMqtt();directConnectedLoop();mqttCallback(cmd,(byte*)data,2);publishCmdAck("x","ok");publishDatasetStatus("x","x");publishDatasetSummary();
 pgl::gld::GldDatasetValidationResult v{pgl::gld::GldDatasetRejectReason::None,0,-1};publishDatasetRejectedStatus(v,nullptr,0);
 flushDatasetQueue();assert(mqtt.loops==0 && mqtt.publishes==0 && cmds==0 && datasetQueueCount==1 && datasetQueueRetryFailCount==0);
 assert(!publishDatasetPayload("x",0,false) && mqtt.publishes==0);
 runtimeConfig.ctrlword=GLD_CTRL_WORD_VALUE;assert(atexNativeConfigTrusted() && workflowNativeNetworkConfigured());
 maintainMqtt();directConnectedLoop();mqttCallback(cmd,(byte*)data,2);assert(mqtt.loops==2 && cmds==1);
 publishCmdAck("x","ok");publishDatasetStatus("x","x");publishDatasetSummary();publishDatasetRejectedStatus(v,nullptr,0);assert(mqtt.publishes==4);
 flushDatasetQueue();assert(datasetQueueCount==0 && mqtt.publishes==5);
 atexConfigPersistenceFault=true;assert(!atexNativeConfigTrusted());maintainMqtt();directConnectedLoop();mqttCallback(cmd,(byte*)data,2);publishCmdAck("x","ok");assert(mqtt.loops==2 && cmds==1 && mqtt.publishes==5);
 atexConfigPersistenceFault=false;std::strcpy(runtimeConfig.wifiSsid,"CHANGE_ME");assert(!atexNativeConfigTrusted());maintainMqtt();assert(mqtt.loops==2);
  // The independent wireless Dataset readiness does not require native Wi-Fi/MQTT.
  runtimeConfig.wifiSsid[0]=0;runtimeConfig.mqttHost[0]=0;assert(!workflowNativeNetworkConfigured() && datasetWifiReady());
#else
 assert(!runtimeConfigValid() && workflowNativeNetworkConfigured());
 maintainMqtt();directConnectedLoop();mqttCallback(cmd,(byte*)data,2);publishCmdAck("x","ok");flushDatasetQueue();assert(mqtt.loops==2 && cmds==1 && mqtt.publishes==2 && datasetQueueCount==0);
#endif
}
"""
class ConfigNetworkGuard(unittest.TestCase):
    def test_production_functions_profiles_and_negative_controls(self):
        src=SRC.read_text(encoding='utf8')
        for name in ('bool connectWifi()', 'bool mqttConnect()'):
            self.assertIn('if (!workflowNativeNetworkConfigured()) return false;',extract(src,name))
        signatures=('bool runtimeConfigValid()', 'bool atexNativeConfigTrusted()', 'bool workflowNativeNetworkConfigured()',
          'bool publishDatasetPayload(', 'void flushDatasetQueue()', 'void maintainMqtt()', 'void publishCmdAck(',
          'void publishDatasetStatus(', 'void publishDatasetRejectedStatus(', 'void publishDatasetSummary()', 'void mqttCallback(char* topic, byte* payload, unsigned int length) {', 'bool datasetWifiReady()')
        bodies=[extract(src,name) for name in signatures]
        # Helper exists only in ATEX build, just as in production source.
        bodies[1]='#if PGL_GLD_BOARD_PROFILE_GLD_ATEX\n'+bodies[1]+'\n#endif\n'
        match=re.search(r'\} else if \(mqtt\.connected\(\)\) \{\n(.*?)\n        \}',src,re.S)
        self.assertIsNotNone(match);direct='void directConnectedLoop() {\n'+match.group(1)+'\n}'
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);f=d/'test.cpp';exe=d/'test.exe';env=dict(os.environ);env['PATH']=str(Path(CXX).parent)+os.pathsep+env['PATH']
            for at,mutate in [(1,0),(0,0),(1,1),(1,2)]:
                parts=list(bodies)
                if mutate==1:parts[1]=parts[1].replace('runtimeConfigValid() && !atexConfigPersistenceFault', 'true')
                if mutate==2:parts[-2]=parts[-2].replace('if (!atexNativeConfigTrusted()) return;', 'if (false) return;')
                f.write_text(PRE+'\n'.join(parts)+direct+POST,encoding='utf8')
                subprocess.run([CXX,'-std=c++17','-static',f'-DPGL_GLD_BOARD_PROFILE_GLD_ATEX={at}','-DPGL_GLD_DATASET_WORKFLOW=1','-I'+str(ROOT/'firmware/lib/ArduinoJson/src'),str(f),'-o',str(exe)],check=True,env=env)
                rc=subprocess.run([str(exe)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode
                if mutate:self.assertNotEqual(rc,0)
                else:self.assertEqual(rc,0)
if __name__=='__main__':unittest.main()
