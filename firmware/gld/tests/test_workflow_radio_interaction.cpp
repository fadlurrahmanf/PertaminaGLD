// Executes the extracted production serviceAtexWorkflowRadio against fake
// radio/workflow APIs. The queue/buffer fake models only the relevant contract;
// separate real workflow tests and hardware RF tests remain necessary.
#include "GldWorkflowRadioSchedule.h"
#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <new>

#define LOW 0
#define HIGH 1
#define RADIOLIB_ERR_NONE 0
#define RADIOLIB_ERR_CRC_MISMATCH -7
#define RADIOLIB_ERR_LORA_HEADER_DAMAGED -24
#define RADIOLIB_ERR_PACKET_TOO_LONG -4
#define RADIOLIB_ERR_NULL_POINTER -28
#define RADIOLIB_SX126X_IRQ_TX_DONE 1
#define RADIOLIB_SX126X_IRQ_RX_DONE 2
constexpr uint32_t DEFAULT_TX_INTERVAL_MS = 10000, LORA_RX_WINDOW_MS = 2000;
uint32_t nowMs = 0;
uint32_t millis() { return nowMs; }
int digitalRead(int) { return LOW; }
void digitalWrite(int, int) {}
void logPrintf(const char*, ...) {}
void logPrintln(const char*) {}
void onLoRaRxDone() {}
extern bool loraRxFlag;

namespace pgl { namespace protocol { constexpr size_t APPFRAME_OVERHEAD=10, STAR_MAX_PAYLOAD=54; }
namespace gld {
enum class GldSerialCommandType { GetStatus, Restart, RunNullingSingleJson, SetDeviceIdJson };
struct GldSerialCommand { GldSerialCommandType type; };
namespace board { constexpr int PIN_LORA_BUSY=10, PIN_ADS1256_CS=38, PIN_LORA_RXEN=41, PIN_LORA_TXEN=42; }
bool powerGood = true;
bool readGldExternalPower() { return powerGood; }
namespace datasetworkflowwifi {
bool lease, sampling, paused, stopped, incomplete, summarySent, client, gate, due;
unsigned retained, samples, polls, rejectedStarts;
enum class Command { None, Pause, Stop, Start } command;
bool ownsSession() { return lease; }
bool samplingActive() { return sampling; }
bool sampleDue() { return sampling && due; }
void setRadioDrainBlocksStart(bool blocked) { gate = blocked; }
void failSession(const char*) {
    if (sampling || paused || (lease && !summarySent)) { incomplete=true; sampling=paused=false; stopped=true; }
}
void pollCommands() {
    if (command == Command::Pause && sampling) { sampling=false; paused=true; }
    if (command == Command::Stop && (sampling || paused)) { sampling=paused=false; stopped=true; }
    if (command == Command::Start) {
        if (sampling || paused || retained || !summarySent || gate) ++rejectedStarts;
        else { lease=sampling=true; stopped=false; summarySent=false; }
    }
    command=Command::None;
}
void poll() {
    ++polls;
    pollCommands();
    if (sampleDue()) { assert(!loraRxFlag); ++samples; due=false; }
    if (lease && stopped && summarySent && !client) lease=false;
    if (stopped && !gate && retained == 0) summarySent=true;
}
} } }

struct FakeRadio {
    int irqError=0, lengthError=0, readError=0, standbyError=0, startError=0, finishError=0, rxStartError=0;
    uint32_t irq=0;
    size_t length=10;
    unsigned starts=0, finishes=0, receives=0, standbys=0, lengths=0, reads=0;
    int16_t getIrqFlagsChecked(uint32_t& out) { if (irqError) return irqError; out=irq; return 0; }
    int16_t getPacketLengthChecked(size_t& out) { ++lengths; if (lengthError) return lengthError; out=length; return 0; }
    int16_t readData(uint8_t*, size_t) { ++reads; return readError; }
    int16_t standby() { ++standbys; return standbyError; }
    int16_t startTransmit(const uint8_t*, size_t) { ++starts; return startError; }
    int16_t finishTransmit() { ++finishes; return finishError; }
    int16_t startReceive() { ++receives; return rxStartError; }
    void setPacketSentAction(void(*)()) {}
    void setPacketReceivedAction(void(*)()) {}
    void clearPacketReceivedAction() {}
} radio, *loraRadio=&radio;

using Schedule=pgl::gld::GldWorkflowRadioSchedule;
Schedule workflowRadioScheduler(0, LORA_RX_WINDOW_MS);
struct Snapshot { bool valid=false; uint8_t frameLen=39; uint8_t frame[64]{}; } workflowTxSnapshot;
struct Applied { bool valid; float bandwidthKhz; uint8_t sf,cr; uint16_t preamble; } workflowAppliedRadio;
struct Config { bool aesKeyPresent; uint8_t aesKeyId; } runtimeConfig;
bool external24VPowerMode, batteryPowerMode, lastInferenceValid, radioReady, loraRxFlag;
bool workflowSharedSpiQuarantined=false, atexConfigPersistenceFault=false;
namespace pgl { namespace gld { struct GldAtexQcSchedule { enum class State { Idle, Transmitting, Receiving, Fault }; }; } }
struct FakeQcSchedule {
    bool held=false;
    pgl::gld::GldAtexQcSchedule::State current=pgl::gld::GldAtexQcSchedule::State::Idle;
    bool admissionHeld(){return held;}
    pgl::gld::GldAtexQcSchedule::State state(){return current;}
} atexQcSchedule;
bool loraAutoTransmit=true, loraTransmitFocus=false, loraTargetTransmitOnly=false;
uint32_t lastTxMs;
int16_t lastLoraTxState;
bool lastLoraTxOk,lastLoraRxWindowOpened;
int lastResult=0;
unsigned reserves=0, downlinks=0;
bool buildTxSnapshot(int, Snapshot& out) { ++reserves; out.valid=true; return true; }
void reportWorkflowDownlink(const uint8_t*, size_t) { ++downlinks; }
bool workflowReadOnlyCommand(pgl::gld::GldSerialCommandType type) {
    return type == pgl::gld::GldSerialCommandType::GetStatus;
}
const char* workflowCommandName(pgl::gld::GldSerialCommandType) { return "MOCK"; }
unsigned rejectedCommands=0;
void emitCommandAck(const char*, const char*, const char*, bool) { ++rejectedCommands; }
bool TFBG_CONTINUOUS_BATTERY=false;
uint32_t batteryFaultPowerOffDueMs=0;
unsigned faultArms=0, powerOffs=0, delays=0, adcAfterGuard=0;
void armBatteryFaultPowerOff(const char*) { ++faultArms; batteryFaultPowerOffDueMs=nowMs; }
void completeBatterySessionAndPowerOff(const char*) { ++powerOffs; }
void delay(uint32_t) { ++delays; }

#include "workflow_service.inc"
#include "workflow_reject.inc"

void checkQuarantineGuard() {
#include "workflow_quarantine.inc"
    ++adcAfterGuard;
}

using namespace pgl::gld::datasetworkflowwifi;
using State=Schedule::State;
void step() {
#include "workflow_loop_control.inc"
}
void reset() {
    workflowRadioScheduler.~GldWorkflowRadioSchedule();
    new (&workflowRadioScheduler) Schedule(0, LORA_RX_WINDOW_MS);
    lease=sampling=client=true; paused=stopped=incomplete=summarySent=gate=false;
    retained=2; samples=polls=rejectedStarts=0; command=Command::None; due=false;
    loraAutoTransmit=true; loraTransmitFocus=loraTargetTransmitOnly=false;
    radio=FakeRadio{}; nowMs=10000; lastTxMs=0; loraRxFlag=false;
    external24VPowerMode=lastInferenceValid=radioReady=pgl::gld::powerGood=true;
    batteryPowerMode=workflowSharedSpiQuarantined=atexConfigPersistenceFault=false; runtimeConfig={true,1}; workflowAppliedRadio={true,125.0f,7,5,8};
    workflowTxSnapshot=Snapshot{}; lastLoraTxOk=lastLoraRxWindowOpened=false; atexQcSchedule.held=false; atexQcSchedule.current=pgl::gld::GldAtexQcSchedule::State::Idle;
    reserves=downlinks=rejectedCommands=faultArms=powerOffs=delays=adcAfterGuard=0;
}
void startTx() { step(); assert(workflowRadioScheduler.state()==State::Transmitting && radio.starts==1); }
void enterRx() { radio.irq=RADIOLIB_SX126X_IRQ_TX_DONE; loraRxFlag=true; step(); assert(workflowRadioScheduler.state()==State::Receiving); }

int main() {
    // Due samples compete with TX and IRQ in the actual scheduler/service.
    reset(); due=true; step(); assert(samples==1 && radio.starts==0);
    step(); assert(radio.starts==1);
    reset(); startTx(); due=true; step();
    assert(samples==1 && workflowRadioScheduler.state()==State::Transmitting);
    reset(); startTx(); due=true; radio.irq=RADIOLIB_SX126X_IRQ_TX_DONE; loraRxFlag=true; step();
    assert(samples==1 && radio.finishes==1 && radio.receives==1 && workflowRadioScheduler.state()==State::Receiving);
    reset(); startTx(); enterRx(); due=true; radio.irq=RADIOLIB_SX126X_IRQ_RX_DONE; loraRxFlag=true; step();
    assert(samples==1 && radio.reads==1 && workflowRadioScheduler.state()==State::Idle);
    reset(); due=true; command=Command::Pause; step(); assert(samples==0 && paused && radio.starts==0);
    reset(); due=true; command=Command::Stop; step(); assert(samples==0 && stopped && radio.starts==0);
    reset(); startTx(); enterRx(); due=true; command=Command::Pause; step(); assert(samples==0 && paused);
    reset(); startTx(); enterRx(); due=true; command=Command::Stop; step(); assert(samples==0 && stopped);

    // QC test modes and disabled Auto never emit Dataset radio frames.
    reset(); loraAutoTransmit=false; step(); assert(radio.starts==0);
    reset(); loraTransmitFocus=true; step(); assert(radio.starts==0);
    reset(); loraTargetTransmitOnly=true; step(); assert(radio.starts==0);

    // Device identity must not mutate while session or retained data is owned.
    reset(); lease=true; retained=2; summarySent=false;
    assert(rejectWorkflowMutation({pgl::gld::GldSerialCommandType::SetDeviceIdJson}));
    assert(retained==2 && lease);
    reset(); lease=false; retained=0; summarySent=true;
    assert(!rejectWorkflowMutation({pgl::gld::GldSerialCommandType::SetDeviceIdJson}));

    // A QC transaction keeps the Dataset START gate closed across loops.
    reset(); lease=sampling=false;retained=0;summarySent=true;atexQcSchedule.held=true;command=Command::Start;
    step(); assert(rejectedStarts==1 && !lease && gate && radio.starts==0);

    // A persistence fault blocks restart until the active radio service reaches
    // Idle/Fault; this verifies the current policy, not physical RF cleanup.
    reset(); lease=sampling=false; atexConfigPersistenceFault=true;
    atexQcSchedule.current=pgl::gld::GldAtexQcSchedule::State::Transmitting;
    assert(rejectWorkflowMutation({pgl::gld::GldSerialCommandType::Restart}));
    atexQcSchedule.current=pgl::gld::GldAtexQcSchedule::State::Receiving;
    assert(rejectWorkflowMutation({pgl::gld::GldSerialCommandType::Restart}));
    atexQcSchedule.current=pgl::gld::GldAtexQcSchedule::State::Fault;
    assert(!rejectWorkflowMutation({pgl::gld::GldSerialCommandType::Restart}));
    assert(rejectWorkflowMutation({pgl::gld::GldSerialCommandType::RunNullingSingleJson}));
    assert(!rejectWorkflowMutation({pgl::gld::GldSerialCommandType::GetStatus}));
    reset(); startTx(); atexConfigPersistenceFault=true; lease=sampling=false;
    assert(rejectWorkflowMutation({pgl::gld::GldSerialCommandType::Restart}));
    reset(); startTx(); enterRx(); atexConfigPersistenceFault=true; lease=sampling=false;
    assert(rejectWorkflowMutation({pgl::gld::GldSerialCommandType::Restart}));

    // A control already queued before the scheduling pass prevents new TX.
    reset(); command=Command::Pause; step(); assert(paused && radio.starts==0);
    reset(); command=Command::Stop; step(); assert(stopped && radio.starts==0);
    reset(); startTx(); command=Command::Pause; step(); assert(paused && !sampling);
    step(); assert(workflowRadioScheduler.state()==State::Transmitting && radio.standbys==0 && !incomplete);
    enterRx(); nowMs+=2000; radio.irq=0; step();
    assert(workflowRadioScheduler.state()==State::Idle && paused && !incomplete && radio.starts==1);
    nowMs+=20000; step(); assert(radio.starts==1);

    reset(); startTx(); command=Command::Stop; step(); assert(stopped && !incomplete);
    retained=0; client=false; step(); assert(!summarySent && gate && lease);
    command=Command::Start; step(); assert(rejectedStarts==1 && !sampling && !summarySent);
    enterRx(); nowMs+=2000; radio.irq=0; step();
    assert(workflowRadioScheduler.state()==State::Idle && summarySent && !incomplete && radio.starts==1);
    step(); assert(!lease);

    // Even a released lease must not abort or duplicate an existing TX.
    reset(); startTx(); command=Command::Stop; step(); lease=false; step();
    assert(workflowRadioScheduler.state()==State::Transmitting && radio.starts==1 && !incomplete);
    enterRx(); nowMs+=2000; radio.irq=0; step();
    assert(workflowRadioScheduler.state()==State::Idle && radio.starts==1);

    reset(); startTx(); enterRx(); command=Command::Stop; step(); retained=0; step();
    assert(!summarySent); radio.lengthError=-33; loraRxFlag=true; step();
    assert(workflowRadioScheduler.state()==State::Fault && incomplete && !radioReady && radio.lengths==1);
    step(); assert(summarySent);

    reset(); startTx(); command=Command::Pause; step(); radio.irqError=-33; loraRxFlag=true; step();
    assert(workflowRadioScheduler.state()==State::Fault && incomplete && !radioReady && radio.standbys>0);

    reset(); radio.startError=-33; step();
    assert(workflowRadioScheduler.state()==State::Fault && incomplete && !radioReady && radio.standbys==1);
    reset(); radio.startError=-33; radio.standbyError=-34; step();
    assert(workflowRadioScheduler.state()==State::Fault && incomplete && workflowSharedSpiQuarantined);
    assert(retained==2 && !summarySent);
    lease=false;  // simulate a later fully drained/disconnected session
    assert(rejectWorkflowMutation({pgl::gld::GldSerialCommandType::RunNullingSingleJson}));
    assert(!rejectWorkflowMutation({pgl::gld::GldSerialCommandType::GetStatus}));
    assert(!rejectWorkflowMutation({pgl::gld::GldSerialCommandType::Restart}));
    checkQuarantineGuard(); assert(adcAfterGuard==0 && delays==1);
    batteryPowerMode=true; checkQuarantineGuard();
    assert(adcAfterGuard==0 && faultArms==1 && powerOffs==1);
    reset(); startTx(); radio.irq=RADIOLIB_SX126X_IRQ_TX_DONE; radio.finishError=-33; loraRxFlag=true; step();
    assert(workflowRadioScheduler.state()==State::Fault && incomplete && radio.standbys==1);
    reset(); startTx(); radio.irq=RADIOLIB_SX126X_IRQ_TX_DONE; radio.rxStartError=-33; loraRxFlag=true; step();
    assert(workflowRadioScheduler.state()==State::Fault && incomplete && radio.standbys==1);

    reset(); startTx(); enterRx(); radio.readError=-33; loraRxFlag=true; step();
    assert(workflowRadioScheduler.state()==State::Fault && incomplete && !radioReady && downlinks==0);
    reset(); startTx(); enterRx(); radio.readError=RADIOLIB_ERR_CRC_MISMATCH; loraRxFlag=true; step();
    assert(workflowRadioScheduler.state()==State::Idle && !incomplete && radioReady && downlinks==0);
    reset(); startTx(); enterRx(); radio.readError=RADIOLIB_ERR_LORA_HEADER_DAMAGED; loraRxFlag=true; step();
    assert(workflowRadioScheduler.state()==State::Idle && !incomplete && radioReady && downlinks==0);

    reset(); startTx(); enterRx(); nowMs+=2000; radio.irqError=-33; step();
    assert(workflowRadioScheduler.state()==State::Fault && incomplete && !radioReady);

    reset(); startTx(); pgl::gld::powerGood=false; step();
    assert(workflowRadioScheduler.state()==State::Fault && incomplete && !radioReady);

    reset(); workflowAppliedRadio.valid=false; step();
    assert(workflowRadioScheduler.state()==State::Fault && incomplete && !radioReady && reserves==0 && radio.starts==0);
    std::puts("ATEX production service interaction: PASS (fake workflow/radio)");
}
