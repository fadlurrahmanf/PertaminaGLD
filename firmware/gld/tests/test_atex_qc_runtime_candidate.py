"""Synthetic production-body harness for candidate QC async adapter."""
from pathlib import Path
import os,shutil,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[3]
CXX=os.environ.get('CXX') or shutil.which('g++') or str(Path.home()/'.platformio/packages/toolchain-gccmingw32/bin/g++.exe')
def function(src,name):
 a=src.index(name);o=src.index('{',a);d=1;i=o+1
 while d:d+=(src[i]=='{')-(src[i]=='}');i+=1
 return src[a:i]
CPP=r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cmath>
#include "GldAtexQcSchedule.h"
#include "GldWorkflowRadioSchedule.h"
#define HIGH 1
#define LOW 0
#define RADIOLIB_ERR_NONE 0
#define RADIOLIB_ERR_UNKNOWN -9
#define RADIOLIB_ERR_NULL_POINTER -1
#define RADIOLIB_ERR_PACKET_TOO_LONG -2
#define RADIOLIB_ERR_CRC_MISMATCH -3
#define RADIOLIB_ERR_LORA_HEADER_DAMAGED -4
#define RADIOLIB_SX126X_IRQ_TX_DONE 1
#define RADIOLIB_SX126X_IRQ_RX_DONE 2
namespace pgl {namespace protocol {
constexpr int APPFRAME_OVERHEAD=10,STAR_MAX_PAYLOAD=54,GLD_ENCRYPTED_PAYLOAD_SIZE=28;
enum class FrameStatus{Ok,Error};struct FrameEncodeResult{FrameStatus status;unsigned size;};
uint8_t makeGldSensorTypeFlags(bool,bool){return 1;}
FrameEncodeResult encodeAppFrame(uint8_t,uint16_t,uint16_t,uint8_t,const uint8_t*,uint8_t,uint8_t*,size_t,uint8_t){return {FrameStatus::Ok,38};}
}}
namespace pgl {namespace gld {
enum class GldMode{INFERENCE,DATASET};bool power=true;bool readGldExternalPower(){return power;}
namespace board {enum{PIN_ADS1256_CS,PIN_LORA_RXEN,PIN_LORA_TXEN};}
unsigned reserveCount=0;bool reserveGldTxSequence(uint8_t& x){++reserveCount;x=1;return true;}
namespace datasetworkflowwifi {bool gate=false,lease=false;void setRadioDrainBlocksStart(bool v){gate=v;} bool ownsSession(){return lease;} }
bool parsed=false;bool parseLoRaDownlinkCmd(const uint8_t*,size_t,uint16_t,const uint8_t*,bool,uint16_t& id,GldMode& mode){if(!parsed)return false;id=6;mode=GldMode::DATASET;return true;}
}}
uint32_t clockMs=10000,lastTxMs=0;uint32_t millis(){return clockMs;}
constexpr uint32_t LORA_RX_WINDOW_MS=2000;
bool external24VPowerMode=true,batteryPowerMode=false,radioReady=true,lastInferenceValid=true,loraRxFlag=false,loraTransmitFocus=false,loraTargetTransmitOnly=false;
bool atexQcWantsRx=false,atexQcFocusTx=false,workflowSharedSpiQuarantined=false,lastLoraTxOk=false,lastLoraRxWindowOpened=false;
uint8_t atexQcFrame[64]{};size_t atexQcFrameLen=0;uint8_t txSeq=0;int lastResult=0;uint32_t loraFocusTxAttemptCount=0,loraFocusTxPassCount=0,loraFocusTxFailCount=0;
int16_t lastLoraTxState=0;struct{float bandwidthKhz=125;uint8_t sf=7,cr=5;uint16_t preamble=8;bool valid=true;}workflowAppliedRadio;
struct {uint16_t nodeId=0x1001,chId=0x10,lastDownlinkCommandId=5;uint8_t aesKey[16]{};bool aesKeyPresent=true;}runtimeConfig;
struct GldTxSnapshot{bool valid=false;uint8_t frameLen=0;uint8_t frame[64]{};};
unsigned buildCount=0;bool buildOk=true;bool buildTxSnapshot(int,GldTxSnapshot& s){++buildCount;if(!buildOk)return false;s.valid=true;s.frameLen=38;return true;}
pgl::gld::GldAtexQcSchedule atexQcSchedule;
unsigned previewLen=0;void digitalWrite(int,int){} void onLoRaRxDone(){} void clearAtexLoraTxPreview(){previewLen=0;} void captureAtexLoraTxPreview(const uint8_t*,size_t n){previewLen=n;}
int events=0,modeChanges=0,saveCalls=0;bool saveOk=true;
void emitLoraTxEvent(bool,const char*){events++;}bool saveDownlinkReplayState(){saveCalls++;return saveOk;}void onModeCmd(pgl::gld::GldMode){modeChanges++;}
struct Radio {int starts=0,recvs=0,finishes=0,standbys=0,reads=0,lengths=0;int startError=0,irqError=0,standbyError=0;uint32_t irq=0;
 void setPacketSentAction(void(*)()){}void setPacketReceivedAction(void(*)()){}void clearPacketReceivedAction(){}
 int16_t startTransmit(uint8_t*,size_t){starts++;return startError;}int16_t getIrqFlagsChecked(uint32_t& out){out=irq;return irqError;}
 int16_t finishTransmit(){finishes++;return 0;}int16_t startReceive(){recvs++;return 0;}
 int16_t getPacketLengthChecked(size_t& n){++lengths;n=10;return 0;}int16_t readData(uint8_t*,size_t){++reads;return 0;}int16_t standby(){standbys++;return standbyError;}
} radio,*loraRadio=&radio;
'''
POST=r'''
int main(){using S=pgl::gld::GldAtexQcSchedule::State;
 // Reject invalid radio config before sequence reservation and frame building.
 workflowAppliedRadio.valid=false;loraTransmitFocus=true;assert(!runAtexLoraTxAttempt(false));assert(pgl::gld::reserveCount==0&&buildCount==0&&!pgl::gld::datasetworkflowwifi::gate);
 workflowAppliedRadio.valid=true;loraTransmitFocus=false;
 pgl::gld::datasetworkflowwifi::lease=true;pgl::gld::datasetworkflowwifi::gate=true;assert(!runAtexLoraTxAttempt(false));assert(radio.starts==0&&pgl::gld::datasetworkflowwifi::gate);pgl::gld::datasetworkflowwifi::lease=false;pgl::gld::datasetworkflowwifi::gate=false;
 // Block before touching radio if no inference, despite good power.
 lastInferenceValid=false;assert(!runAtexLoraTxAttempt(false));assert(radio.starts==0&&!pgl::gld::datasetworkflowwifi::gate&&radioReady);
 // Power loss between admission and StartTx must not claim a TX preview.
 lastInferenceValid=true;assert(runAtexLoraTxAttempt(false));assert(previewLen==0&&radio.starts==0);
 pgl::gld::power=false;serviceAtexQcRadio();assert(previewLen==0&&radio.starts==0&&atexQcSchedule.state()==S::Idle);
 pgl::gld::power=true;assert(runAtexLoraTxAttempt(false));assert(pgl::gld::datasetworkflowwifi::gate&&radio.starts==0&&previewLen==0);
 // Dataset START must consult persistent gate while TX/RX are in flight.
 serviceAtexQcRadio();assert(radio.starts==1&&previewLen==38&&atexQcSchedule.state()==S::Transmitting&&pgl::gld::datasetworkflowwifi::gate);
 radio.irq=1;loraRxFlag=true;serviceAtexQcRadio();assert(atexQcSchedule.state()==S::StartRx);
 serviceAtexQcRadio();assert(radio.recvs==1&&atexQcSchedule.state()==S::Receiving&&pgl::gld::datasetworkflowwifi::gate);
 // Checked RX then real production downlink handling and durable replay state.
 pgl::gld::parsed=true;radio.irq=2;loraRxFlag=true;clockMs+=15000;serviceAtexQcRadio();
 assert(lastTxMs==clockMs); // Full TX/RX exceeded interval: no immediate restart.
 assert(atexQcSchedule.state()==S::Idle&&!pgl::gld::datasetworkflowwifi::gate&&saveCalls==1&&modeChanges==1&&runtimeConfig.lastDownlinkCommandId==6);
 // Focus has no RX.
 loraTargetTransmitOnly=true;assert(runAtexLoraTxAttempt(false));serviceAtexQcRadio();radio.irq=1;loraRxFlag=true;serviceAtexQcRadio();
 assert(atexQcSchedule.state()==S::Idle&&radio.recvs==1&&!pgl::gld::datasetworkflowwifi::gate&&loraFocusTxPassCount==1);
 // Focus-to-CH reserves one sequence and also ends without an RX window.
 loraTargetTransmitOnly=false;loraTransmitFocus=true;assert(runAtexLoraTxAttempt(false));assert(pgl::gld::reserveCount==1);
 serviceAtexQcRadio();radio.irq=1;loraRxFlag=true;serviceAtexQcRadio();
 assert(atexQcSchedule.state()==S::Idle&&radio.recvs==1&&loraFocusTxPassCount==2);
 loraTransmitFocus=false;
 // A failed replay persistence leaves the prior command ID and does not change mode.
 loraTargetTransmitOnly=false;saveOk=false;pgl::gld::parsed=true;runtimeConfig.lastDownlinkCommandId=5;
 assert(runAtexLoraTxAttempt(false));serviceAtexQcRadio();radio.irq=1;loraRxFlag=true;serviceAtexQcRadio();serviceAtexQcRadio();
 radio.irq=2;loraRxFlag=true;serviceAtexQcRadio();assert(runtimeConfig.lastDownlinkCommandId==5&&modeChanges==1&&saveCalls==2);
 // Stale DIO flag with no RX_DONE must not read or parse the previous buffer.
 pgl::gld::parsed=true;saveOk=true;assert(runAtexLoraTxAttempt(false));serviceAtexQcRadio();radio.irq=1;loraRxFlag=true;serviceAtexQcRadio();serviceAtexQcRadio();
 int oldReads=radio.reads,oldLengths=radio.lengths;radio.irq=1;loraRxFlag=true;serviceAtexQcRadio();
 assert(atexQcSchedule.state()==S::Fault&&radio.reads==oldReads&&radio.lengths==oldLengths&&modeChanges==1);
 atexQcSchedule=pgl::gld::GldAtexQcSchedule{};radio=Radio{};radioReady=true;workflowSharedSpiQuarantined=false;pgl::gld::datasetworkflowwifi::gate=false;loraRxFlag=false;
 // Checked SPI error with TX IRQ is an uncertain outcome: no retry.
 pgl::gld::parsed=false;saveOk=true;assert(runAtexLoraTxAttempt(false));serviceAtexQcRadio();radio.irq=1;radio.irqError=-77;loraRxFlag=true;serviceAtexQcRadio();
 assert(atexQcSchedule.state()==S::Fault&&!radioReady&&pgl::gld::datasetworkflowwifi::gate);
 int before=radio.starts;serviceAtexQcRadio();assert(before==radio.starts);
 // Test-only reset represents a full board restart/reconciliation.
 atexQcSchedule=pgl::gld::GldAtexQcSchedule{};radio=Radio{};radioReady=true;workflowSharedSpiQuarantined=false;pgl::gld::datasetworkflowwifi::gate=false;loraRxFlag=false;
 // Power loss while on air keeps admission blocked and quarantines SPI.
 assert(runAtexLoraTxAttempt(false));serviceAtexQcRadio();pgl::gld::power=false;serviceAtexQcRadio();
 assert(atexQcSchedule.state()==S::Fault&&pgl::gld::datasetworkflowwifi::gate&&!radioReady&&workflowSharedSpiQuarantined);
}
'''
class Tests(unittest.TestCase):
 def test_production_body(self):
  src=(ROOT/'firmware/gld/src/GldUnifiedMain.cpp').read_text(encoding='utf8')
  start=function(src,'bool runAtexLoraTxAttempt(bool scanDuringRx) {');service=function(src,'void serviceAtexQcRadio() {')
  for section in (start,service): self.assertNotIn('->transmit(',section);self.assertNotIn('while (',section)
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);(d/'test.cpp').write_text(CPP+start+'\n'+service+POST);exe=d/'test.exe';env=dict(os.environ);env['PATH']=str(Path(CXX).parent)+os.pathsep+env.get('PATH',''); source=Path(os.environ.get('GLD_WORKFLOW_SCHEDULE',str(ROOT/'firmware/gld/include/GldWorkflowRadioSchedule.h')));(d/'GldWorkflowRadioSchedule.h').write_text(source.read_text(encoding='utf8'),encoding='utf8')
   subprocess.run([CXX,'-std=c++17','-static','-I'+str(d),'-I'+str(ROOT/'firmware/gld/include'),str(d/'test.cpp'),'-o',str(exe)],check=True,env=env);subprocess.run([str(exe)],check=True,env=env)
 def test_recovery_gates_and_power_priority(self):
  src=(ROOT/'firmware/gld/src/GldUnifiedMain.cpp').read_text(encoding='utf8');loop=src[src.index('void loop() {'):]
  boot='if (!atexQcSchedule.admissionHeld()) maintainBootReportRecovery();'
  ads='if (!atexQcSchedule.admissionHeld()) maintainAdsRecovery("inference_ads_not_ready");'
  self.assertIn(boot,loop);self.assertIn(ads,loop)
  self.assertLess(loop.index('if (powerTransitionShutdownPending)'),loop.index(boot))
  cpp=r"""
#include <cassert>
struct Schedule {bool held=false;bool admissionHeld(){return held;}} atexQcSchedule;
int boot=0,ads=0;void maintainBootReportRecovery(){boot++;}void maintainAdsRecovery(const char*){ads++;}
void tick(){
"""+boot+'\n'+ads+r"""
}
int main(){atexQcSchedule.held=true;tick();assert(boot==0&&ads==0);atexQcSchedule.held=false;tick();assert(boot==1&&ads==1);}
"""
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);(d/'test.cpp').write_text(cpp);exe=d/'test.exe';env=dict(os.environ);env['PATH']=str(Path(CXX).parent)+os.pathsep+env.get('PATH','');subprocess.run([CXX,'-std=c++17','-static',str(d/'test.cpp'),'-o',str(exe)],check=True,env=env);subprocess.run([str(exe)],check=True,env=env)
if __name__=='__main__':unittest.main()
