// Production capture and acquire bodies compiled with fakes; not timing evidence.
#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#define PGL_GLD_DATASET_WORKFLOW 1
#define PGL_GLD_BOARD_PROFILE_GLD_ATEX 1
uint32_t nowMs=500; uint32_t millis(){return nowMs;}
bool loraRxFlag=false,workflowCaptureInterrupted=false,external24VPowerMode=true,batteryPowerMode=false,powerGood=true;
uint32_t nullingProfileId=1; bool nullingProfileApplied=true;
namespace pgl { namespace gld {
constexpr size_t GLD_DATASET_FEATURE_COUNT=8; constexpr uint8_t GLD_DATASET_STATUS_OK=0;
const char* GLD_DATASET_CANONICAL_FEATURE_ORDER[8]={"0","1","2","3","4","5","6","7"};
namespace board { const char** SENSOR_NAMES=GLD_DATASET_CANONICAL_FEATURE_ORDER; }
namespace datasetwifi { struct Sample {uint32_t timestampMs=0,scanEndMs=0;float voltage[8]{},gain[8]{};uint8_t status[8]{};}; }
struct GldDatasetChannelSample {const char* name;uint8_t status;float voltage,gain;bool saturated;};
bool isGldDatasetGainValid(float g){return g==1;}
struct Valid {bool accepted;}; Valid validateGldDatasetSample(GldDatasetChannelSample*,int,bool,uint32_t){return {true};}
bool readGldExternalPower(){return powerGood;}
} }
struct State {bool sampling=true,predictionEnabled=false;uint32_t acquisitionEpoch=1,nextDue=500,overruns=0;} state;
struct Reading {float voltage=1,gain=1;int status=0;bool saturated=false;};
struct FakeAds {int interruptAt=-1,invalidAt=-1,stopAt=-1,count=0;Reading readChannel(size_t i){++count;if(int(i)==interruptAt)loraRxFlag=true;if(int(i)==stopAt){state.sampling=false;++state.acquisitionEpoch;} Reading r;if(int(i)==invalidAt)r.status=1;return r;}} ads;
#include "capture.inc"
namespace ds=pgl::gld::datasetwifi;
struct Lock { ~Lock() {} };
enum class PredictionStatus {NotReady,Valid,Error};
struct Prediction {PredictionStatus status=PredictionStatus::NotReady;int predictedClass=0,gasClass=0;float confidence=0;uint32_t inferenceDurationMs=0;};
struct Sample {ds::Sample raw;bool predictionEnabled=false;Prediction prediction;};
struct Model {int outputElements=1;const int* classMap=nullptr;} modelInfo;
struct Retained {int count=0;bool append(const Sample&,uint32_t){++count;return true;}bool full(){return false;}} retained;
struct Ack {void arm(uint32_t){}} ackClock;
constexpr uint32_t INTERVAL_MS=500;
void checkLimitLocked(uint32_t){}
bool ready(){return powerGood;} bool (*isReady)()=ready;
bool (*captureSample)(ds::Sample&)=captureDatasetWifi;
bool retry(){return workflowCaptureInterrupted;} bool (*retryInterruptedCapture)()=retry;
void (*predictSample)(const ds::Sample&,Prediction&)=nullptr;
int resets=0;void resetPred(){++resets;} void (*resetPrediction)()=resetPred;
int stops=0;void stopLocked(const char*,bool){++stops;state.sampling=false;}
#include "acquire.inc"
void reset(){state=State{};ads=FakeAds{};retained.count=resets=stops=0;loraRxFlag=workflowCaptureInterrupted=false;powerGood=external24VPowerMode=true;batteryPowerMode=false;}
int main(){
 reset();acquireDueSample();assert(retained.count==1 && ads.count==8 && state.nextDue==1000 && !stops);
 for(int n=0;n<8;++n){reset();ads.interruptAt=n;acquireDueSample();assert(retained.count==0 && workflowCaptureInterrupted && state.nextDue==500 && resets==0 && stops==0);loraRxFlag=false;ads.interruptAt=-1;acquireDueSample();assert(retained.count==1 && state.nextDue==1000 && !stops);}
 reset();loraRxFlag=true;acquireDueSample();assert(retained.count==0 && ads.count==0 && state.nextDue==500);
 reset();ads.interruptAt=3;ads.invalidAt=3;acquireDueSample();assert(retained.count==0 && !workflowCaptureInterrupted && stops==1 && resets==1);
 for(int n=0;n<8;++n){reset();ads.stopAt=n;acquireDueSample();assert(retained.count==0 && !state.sampling);}
 reset();powerGood=false;acquireDueSample();assert(retained.count==0 && stops==1);
}
