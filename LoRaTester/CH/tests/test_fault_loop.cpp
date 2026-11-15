#include <cassert>
#include <cstdio>
#include <vector>
#include "Arduino.h"
#include "SPI.h"
#include "WiFi.h"
uint32_t fakeMillis = 0;
uint32_t fakeRandom = 0x1234abcdU;
uint8_t fakeStaMac[6] = {};
int fakeMacResult = 0, fakeSetMacCount = 0, fakeStorageCount = 0;
int fakeStorageResult = 0, fakeReadResult = 0;
int fakePowerReadResult = 0, fakeResetReason = 4;
int8_t fakeMaxTxQuarterDbm = 78;
int fakeNowSendResult = 0;
bool fakeWifiStopped = false;
FakeSerial Serial0;
FakeSpi SPI;
FakeWiFi WiFi;
std::vector<std::vector<uint8_t>> fakeTx;
std::vector<std::vector<uint8_t>> fakeNowTx;
std::vector<uint8_t> fakeRx;
bool fakeInjectOnDetach = false;
bool fakeInjectInStandby = false;
int fakeStandbyResult = 0;
int fakeIrqResult = 0;
int fakeStartRxResult = 0;
uint32_t fakeIrq = 0;
#include "dut.cpp"

uint8_t frameType(const std::vector<uint8_t>& frame) {
  pgl::protocol::FrameView v{};
  assert(pgl::protocol::decodeAppFrame(frame.data(), frame.size(), v,
        pgl::protocol::MESH_MAX_PAYLOAD) == pgl::protocol::FrameStatus::Ok);
  RadioPayload p{}; memcpy(&p,v.payload,sizeof(p)); return p.type;
}
uint8_t lastType() { assert(!fakeTx.empty()); return frameType(fakeTx.back()); }
void queueFrame(uint8_t type, uint32_t sid, uint8_t seq=0, DirectionStats stats={}, uint8_t ageSec=3) {
  RadioPayload p{}; p.magic=kRadioMagic; p.version=5; p.type=type; p.session=sid; p.stats=stats; p.sampleAgeSec=ageSec;
  uint8_t payload[kLongPayload]={}; memcpy(payload,&p,sizeof(p));
  uint8_t buf[50]={};
  auto r=pgl::protocol::encodeAppFrame(kTestFrameType, LT_ROLE==1?kCh2:kCh1,
      LT_ROLE==1?kCh1:kCh2, seq,payload,LT_ROLE==1?kLongPayload:kShortPayload,
      buf,sizeof(buf),pgl::protocol::MESH_MAX_PAYLOAD);
  assert(r.status==pgl::protocol::FrameStatus::Ok);
  fakeRx.assign(buf,buf+r.size); onRadioRx();
}
void receive(uint8_t type, uint32_t sid, uint8_t seq=0, DirectionStats stats={}, uint8_t ageSec=3) {
  queueFrame(type,sid,seq,stats,ageSec); loop();
}
void tick(uint32_t t) { fakeMillis=t; loop(); }
#if LT_ROLE == 1
void control(uint8_t type,uint32_t sid) {
  uint8_t mac[6]={1,2,3,4,5,6}; NowMessage m{};
  m.magic=kNowMagic; m.version=kNowVersion; m.type=type; m.session=sid;
  onNowReceive(mac,reinterpret_cast<uint8_t*>(&m),sizeof(m)); loop();
}
#endif
int main() {
  setup(); assert(radioReady && state==TestState::Idle);
#if LT_ROLE == 1 && defined(LT_TEMP_ALT_MAC) && LT_TEMP_ALT_MAC
  assert(altMacReady && fakeStorageCount==1 && fakeSetMacCount==1 && !fakeWifiStopped);
  assert(memcmp(fakeStaMac,kTemporaryStaMac,6)==0 && (fakeStaMac[0]&3)==2);
#else
  assert(fakeSetMacCount==0 && fakeStorageCount==0);
#endif
#if LT_ROLE == 1
  Serial0.output.clear(); Serial0.input="IN"; lastWdt=fakeMillis;
  const uint32_t serialStarted=fakeMillis; loop();
  assert(fakeMillis==serialStarted && Serial0.output.find("LT_WIFI_INFO")==std::string::npos);
  Serial0.input="FO\n"; loop(); assert(Serial0.output.find("LT_WIFI_INFO")!=std::string::npos);
  Serial0.output.clear(); Serial0.input=std::string(80,'X')+"INFO\n";
  for (int i=0; i<4; ++i) loop();
  assert(Serial0.output.find("LT_WIFI_INFO")==std::string::npos);
  Serial0.output.clear(); Serial0.input="INFO\n"; loop();
  assert(Serial0.output.find("LT_WIFI_INFO") != std::string::npos);
  assert(Serial0.output.find("max_tx_read=0 max_tx_qdbm=78 reset_reason=4") != std::string::npos);
  assert(Serial0.output.find("mac_read=0") != std::string::npos);
  fakePowerReadResult=-7; fakeReadResult=-8; Serial0.output.clear(); Serial0.input="INFO\n"; loop();
  assert(Serial0.output.find("mac_read=-8") != std::string::npos);
  assert(Serial0.output.find("max_tx_read=-7") != std::string::npos);
  fakePowerReadResult=0; fakeReadResult=0;
  control(kNowDiscover,0);
  NowMessage presence{}; memcpy(&presence,fakeNowTx.back().data(),sizeof(presence));
  assert(presence.type==kNowPresence && presence.bootNonce==0x1234abcdU);
  control(kNowStart,123);
  assert(state==TestState::Starting && lastType()==RadioStart);
  assert(txCallbackResult==0 && txQueued>=2 && txRejected==0);
  const auto previousQueued=txQueued;
  fakeNowSendResult=-9; reportStatus();
  assert(txRejected==1 && txQueued==previousQueued && lastStatusResult==-9);
  fakeNowSendResult=0;
  onNowSend(nullptr,ESP_NOW_SEND_SUCCESS); onNowSend(nullptr,ESP_NOW_SEND_FAIL);
  assert(txAck==1 && txNoAck==1);
  NowMessage reported{}; memcpy(&reported,fakeNowTx.back().data(),sizeof(reported));
  assert(reported.type==kNowStatus && reported.reportSeq==1 && reported.bootNonce==presence.bootNonce);
  reportSequence=0xfffffffeU; reportStatus();
  memcpy(&reported,fakeNowTx.back().data(),sizeof(reported)); assert(reported.reportSeq==0xffffffffU);
  reportStatus(); memcpy(&reported,fakeNowTx.back().data(),sizeof(reported)); assert(reported.reportSeq==0);
  // Lost START_ACK is retried. No DATA is emitted while starting.
  tick(fakeMillis+2000); assert(lastType()==RadioStart);
  receive(RadioStartAck,123); assert(handshake==1);
  loop(); assert(lastType()==RadioCommit && commitToken==1);
  // A stale COMMIT_ACK must not unlock GO.
  receive(RadioCommitAck,123,0); assert(handshake==1);
  receive(RadioCommitAck,123,1); assert(handshake==2);
  loop(); assert(lastType()==RadioGo);
  // Losing the first two peer packets must not suppress our first two slots.
  tick(epoch); assert(state==TestState::Running);
  tick(epoch+1000); assert(senderCount==1 && lastType()==RadioReverseData);
  tick(epoch+3000); assert(senderCount==2 && lastType()==RadioReverseData);
  tick(epoch+4000); receive(RadioData,123,2);
  assert(state==TestState::Running && receiver.received()==1 && senderOk==2);
  tick(epoch+5000);
  for (unsigned i=3; i<100; ++i) {
    tick(epoch+i*2000U); receive(RadioData,123,static_cast<uint8_t>(i));
    tick(epoch+i*2000U+1000U);
  }
  loop(); assert(phase==3 && lastType()==RadioReverseEnd && senderOk==100 && receiver.received()==98);
  DirectionStats lossReport{}; lossReport.available=1; lossReport.final=1; lossReport.received=100;
  receive(RadioReport,123,100,lossReport);
  assert(state==TestState::Done && forwardFinal && receiver.received()==98);
  // Three missing STOP_ACKs leave the remote status unknown via Timeout.
  state=TestState::Stopping; handshake=0; startAttempts=0; lastRadioTx=fakeMillis-2000;
  loop(); assert(lastType()==RadioStop && startAttempts==1);
  tick(fakeMillis+2000); assert(lastType()==RadioStop && startAttempts==2);
  tick(fakeMillis+2000); assert(lastType()==RadioStop && startAttempts==3);
  tick(fakeMillis+3000); assert(state==TestState::Timeout);
  // CH1's current sample comes from its receiver, while CH2's sample comes
  // from the most recent accepted piggyback report.
  receiver.start(123,kCh2); state=TestState::Running; phase=4;
  slots.begin(fakeMillis+10000,1000);
  DirectionStats sample{}; sample.available=1; sample.received=1;
  sample.latestRssiDbm=-96; sample.latestSnrDb10=-43;
  receive(RadioData,123,1,sample);
  auto own=localStats(false);
  assert(own.received==1 && own.latestRssiDbm==-80 && own.latestSnrDb10==-73);
  assert(remoteStats.received==1 && remoteStats.latestRssiDbm==-96 && remoteStats.latestSnrDb10==-43);
  assert(remoteSampleSeen && millis()-lastRemoteSample==3000);
  sample.latestRssiDbm=-5; receive(RadioData,123,1,sample); // duplicate cannot replace snapshot
  assert(remoteStats.latestRssiDbm==-96 && receiver.received()==1);
  const uint32_t oldRemoteSample=lastRemoteSample;
  tick(fakeMillis+2000); sample.latestRssiDbm=-96;
  receive(RadioData,123,2,sample,5); // more return packets, but no new CH2 measurement
  assert(lastRemoteSample==oldRemoteSample && receiver.received()==2);
  const uint32_t ch1Last=lastLocalSample; auto beforeTimeout=fakeTx.size();
  fakeMillis=ch1Last+kPeerSilenceMs; lastWdt=fakeMillis;
  receive(RadioData,123,3,sample);
  assert(state==TestState::Stopping && fakeTx.size()==beforeTimeout+1 && lastType()==RadioStop);
  assert(receiver.received()==2 && lastLocalSample==ch1Last);
  receive(RadioStopAck,123); assert(state==TestState::Timeout);
  // Lost final report: END is retried. Duplicate final reports are ACKed.
  state=TestState::Running; phase=3; senderOk=100; lastRadioTx=fakeMillis-2000;
  loop(); assert(lastType()==RadioReverseEnd);
  tick(fakeMillis+2000); assert(lastType()==RadioReverseEnd);
  DirectionStats finalStats{}; finalStats.available=1; finalStats.final=1; finalStats.received=97;
  finalStats.latestRssiDbm=-103; finalStats.latestSnrDb10=-73;
  receive(RadioReport,123,100,finalStats);
  assert(state==TestState::Done && lastType()==RadioReportAck && remoteStats.received==97);
  assert(remoteStats.latestRssiDbm==-103 && remoteStats.latestSnrDb10==-73);
  const auto count=fakeTx.size(); receive(RadioReport,123,100,finalStats);
  assert(state==TestState::Done && fakeTx.size()==count+1 && lastType()==RadioReportAck);
  // New realtime session: run >100 samples and across 255->0 without a
  // finite-session timeout or fabricated packet-count statistics.
  control(kNowDiscover,0); control(kNowStartRealtime,455);
  receive(RadioStartAck,455); receive(RadioCommitAck,455,1);
  fakeMillis=epoch; const auto beforeEarlyStop=fakeTx.size();
  control(kNowStop,455);
  assert(state==TestState::Stopping && fakeTx.size()==beforeEarlyStop);
  tick(epoch+1000); assert(lastType()==RadioStop);
  receive(RadioStopAck,455); assert(state==TestState::Stopped);
  control(kNowDiscover,0); control(kNowStartRealtime,456);
  assert(state==TestState::Starting && phase==5 && lastType()==RadioStartRealtime);
  receive(RadioStartAck,456); assert(handshake==1);
  receive(RadioCommitAck,456,1); assert(handshake==2);
  DirectionStats liveReport{}; liveReport.available=1; liveReport.received=1;
  liveReport.latestRssiDbm=-99; liveReport.latestSnrDb10=-73;
  for (unsigned i=0; i<260; ++i) {
    fakeMillis=epoch+i*2000U;
    receive(RadioData,456,static_cast<uint8_t>(i),liveReport);
    assert(state==TestState::Running && phase==5 && receiver.received()==1);
  }
  memcpy(&reported,fakeNowTx.back().data(),sizeof(reported));
  assert(reported.type==kNowStatus && reported.phase==5 && reported.expected==0 &&
         reported.received==1 && reported.sentCh1==0xffff && reported.sentCh2==0xffff);
  control(kNowStop,456); assert(state==TestState::Stopping);
  for (int i=0; i<35 && lastType()!=RadioStop; ++i) tick(fakeMillis+100);
  assert(lastType()==RadioStop);
  const uint8_t previousAttempts=startAttempts;
  tick(fakeMillis+2000); assert(startAttempts==previousAttempts+1 && lastType()==RadioStop);
  receive(RadioStopAck,456); assert(state==TestState::Stopped);
  control(kNowDiscover,0); control(kNowStart,789);
  assert(state==TestState::Starting && !realtime && phase==4 && lastType()==RadioStart);
  fakeRandom=0x99aabbccU; setup();
  assert(bootNonce==fakeRandom && bootNonce!=presence.bootNonce);
#if defined(LT_TEMP_ALT_MAC) && LT_TEMP_ALT_MAC
  fakeMacResult=-1; setup(); assert(!altMacReady && !nowReady);
  fakeMacResult=0;
  int setsBefore=fakeSetMacCount;
  fakeStorageResult=-1; setup(); assert(!altMacReady && !nowReady && fakeSetMacCount==setsBefore);
  fakeStorageResult=0; fakeReadResult=-1; setup(); assert(!altMacReady && !nowReady);
  fakeReadResult=0;
#endif
#else
  receive(RadioStart,123); assert(state==TestState::Starting && lastType()==RadioStartAck);
  // Duplicate START and COMMIT support lost replies; old GO is rejected.
  receive(RadioStart,123); assert(state==TestState::Starting && lastType()==RadioStartAck);
  receive(RadioCommit,123,1); assert(handshake==1 && lastType()==RadioCommitAck);
  receive(RadioCommit,123,2); assert(commitToken==2);
  receive(RadioGo,123,1); assert(state==TestState::Starting);
  receive(RadioGo,123,2); assert(state==TestState::Running);
  tick(epoch); assert(senderCount==1 && lastType()==RadioData && fakeTx.back().size()==50);
  receive(RadioReverseData,123,0);
  tick(epoch+2000);
  pgl::protocol::FrameView packetView{};
  assert(pgl::protocol::decodeAppFrame(fakeTx.back().data(),fakeTx.back().size(),packetView,
      pgl::protocol::MESH_MAX_PAYLOAD)==pgl::protocol::FrameStatus::Ok);
  RadioPayload data{}; memcpy(&data,packetView.payload,sizeof(data));
  assert(data.stats.received==1 && data.stats.latestRssiDbm==-80 && data.stats.latestSnrDb10==-73);
  assert(data.sampleAgeSec >= 3 && data.sampleAgeSec != 255);
  receive(RadioStop,123); assert(state==TestState::Stopped && lastType()==RadioStopAck);
  auto count=fakeTx.size(); tick(epoch+4000); assert(fakeTx.size()==count);
  // No CH1 data after restart: CH2 stops within the 12-second window.
  state=TestState::Running; phase=4; localSampleSeen=true; lastLocalSample=fakeMillis;
  const uint32_t ch2Last=lastLocalSample;
  tick(ch2Last+8000); receive(RadioReverseData,123,0); // duplicate does not refresh watchdog
  assert(lastLocalSample==ch2Last);
  tick(ch2Last+kPeerSilenceMs-1); assert(state==TestState::Running);
  count=fakeTx.size(); fakeMillis=ch2Last+kPeerSilenceMs; lastWdt=fakeMillis;
  receive(RadioReverseData,123,1);
  assert(state==TestState::Timeout && fakeTx.size()==count && lastLocalSample==ch2Last);
  state=TestState::Running; phase=4; localSampleSeen=false; epoch=fakeMillis+4000; slots.begin(epoch,0);
  tick(epoch-1); assert(state==TestState::Running);
  lastWdt=epoch+kPeerSilenceMs-1;
  tick(epoch+kPeerSilenceMs-1); assert(state==TestState::Running);
  count=fakeTx.size(); tick(epoch+kPeerSilenceMs);
  assert(state==TestState::Timeout && fakeTx.size()==count);
  state=TestState::Running; phase=4; localSampleSeen=true; lastLocalSample=0xfffff000U;
  lastWdt=lastLocalSample+kPeerSilenceMs-1; slots.begin(lastWdt+5000,0);
  tick(lastLocalSample+kPeerSilenceMs-1); assert(state==TestState::Running);
  tick(lastLocalSample+kPeerSilenceMs); assert(state==TestState::Timeout);
  // Lost report or acknowledgement: final report repeats until ACK.
  slots.begin(0, 0); uint16_t ignored=0;
  for (unsigned i=0; i<100; ++i) assert(slots.next(i*2000, ignored)==SlotDecision::Send);
  state=TestState::Running; phase=4; senderCount=senderOk=100;
  localSampleSeen=true; lastLocalSample=fakeMillis;
  receive(RadioReverseEnd,123,100); assert(phase==3 && lastType()==RadioReport);
  count=fakeTx.size(); tick(fakeMillis+3000); assert(fakeTx.size()==count+1 && lastType()==RadioReport);
  receive(RadioReportAck,123); assert(state==TestState::Done);
  // A partial final report must stay Error after ACK, but duplicate END still
  // causes a report resend so lost ACK/report can be recovered.
  state=TestState::Running; phase=4; senderCount=senderOk=100;
  localSampleSeen=true; lastLocalSample=fakeMillis;
  receive(RadioReverseEnd,123,99); assert(phase==3 && finalPartial);
  count=fakeTx.size(); receive(RadioReverseEnd,123,100);
  assert(fakeTx.size()==count && finalPartial);
  count=fakeTx.size(); receive(RadioReverseEnd,123,99); assert(fakeTx.size()==count+1 && lastType()==RadioReport);
  receive(RadioReportAck,123); assert(state==TestState::Error);
  count=fakeTx.size(); receive(RadioReverseEnd,123,99); assert(state==TestState::Error && fakeTx.size()==count+1);
  state=TestState::Running; phase=4; senderCount=100; senderOk=99;
  localSampleSeen=true; lastLocalSample=fakeMillis;
  receive(RadioReverseEnd,123,100); receive(RadioReportAck,123); assert(state==TestState::Error);
  // A pending STOP at a slot deadline must suppress DATA immediately.
  state=TestState::Running; phase=4; senderCount=0; slots.begin(fakeMillis,0);
  count=fakeTx.size(); receive(RadioStop,123);
  assert(fakeTx.size()==count+1 && frameType(fakeTx[count])==RadioStopAck && state==TestState::Stopped);
  // RX_DONE arrives during detach, after loop's earlier radioRx check.
  state=TestState::Running; phase=4; radioRx=false; fakeInjectOnDetach=true;
  count=fakeTx.size(); assert(!transmit(RadioData,123,7));
  assert(fakeTx.size()==count && radioRx);
  loop(); assert(state==TestState::Stopped && fakeTx.size()==count+1 && lastType()==RadioStopAck);
  state=TestState::Running; phase=4; radioRx=false; fakeInjectInStandby=true;
  count=fakeTx.size(); assert(!transmit(RadioData,123,8));
  assert(fakeTx.size()==count && radioRx);
  loop(); assert(state==TestState::Stopped && fakeTx.size()==count+1 && lastType()==RadioStopAck);
  receive(RadioStartRealtime,456); assert(state==TestState::Starting && realtime && phase==5);
  receive(RadioCommit,456,1); receive(RadioGo,456,1); assert(state==TestState::Running);
  for (unsigned i=0; i<260; ++i) {
    fakeMillis=epoch+i*2000U;
    receive(RadioReverseData,456,static_cast<uint8_t>(i));
    assert(state==TestState::Running && receiver.received()==1);
  }
  receive(RadioStop,456); assert(state==TestState::Stopped && lastType()==RadioStopAck);
  receive(RadioStartRealtime,457); receive(RadioCommit,457,1); receive(RadioGo,457,1);
  assert(state==TestState::Running);
  count=fakeTx.size(); tick(epoch+kPeerSilenceMs);
  assert(state==TestState::Timeout && fakeTx.size()==count);
  receive(RadioStart,789); assert(state==TestState::Starting && !realtime && phase==4);
#endif
  // Actual ISR timestamp boundary: a packet completed before the deadline
  // is accepted even when the loop gets CPU later. Equal/late, malformed,
  // duplicate, and unknown-timestamp frames cannot extend the watchdog.
  const uint16_t remote = LT_ROLE==1 ? kCh2 : kCh1;
  const uint8_t dataType = LT_ROLE==1 ? RadioData : RadioReverseData;
  const uint32_t base = 0xfffff000U; // exercise millis rollover too
  auto armDeadline = [&]() {
    fakeMillis=base; lastWdt=base; radioReady=true; fakeStartRxResult=0;
    session=900; receiver.start(session,remote); state=TestState::Running;
    realtime=false; phase=4; epoch=base; stateStarted=base;
    localSampleSeen=true; lastLocalSample=base; slots.begin(base+60000,0);
    assert(startRx());
  };
  armDeadline(); fakeMillis=base+kPeerSilenceMs-1; queueFrame(dataType,900,1);
  fakeMillis=base+kPeerSilenceMs+5; lastWdt=fakeMillis; loop();
  assert(state==TestState::Running && receiver.received()==1 && lastLocalSample==base+kPeerSilenceMs-1);
  for (unsigned offset=0; offset<=1; ++offset) {
    armDeadline(); fakeMillis=base+kPeerSilenceMs+offset; queueFrame(dataType,900,1);
    lastWdt=fakeMillis; loop();
    assert(state==(LT_ROLE==1 ? TestState::Stopping : TestState::Timeout));
    assert(receiver.received()==0 && lastLocalSample==base);
  }
  armDeadline(); fakeMillis=base+kPeerSilenceMs-1; queueFrame(dataType,900,1);
  fakeRx[10]^=1; fakeMillis=base+kPeerSilenceMs+5; lastWdt=fakeMillis; loop();
  assert(state==(LT_ROLE==1 ? TestState::Stopping : TestState::Timeout) && receiver.received()==0);
  armDeadline(); assert(receiver.receive(900,remote,1,-80,-725)==ReceiveResult::Accepted);
  fakeMillis=base+kPeerSilenceMs-1; queueFrame(dataType,900,1);
  fakeMillis=base+kPeerSilenceMs+5; lastWdt=fakeMillis; loop();
  assert(state==(LT_ROLE==1 ? TestState::Stopping : TestState::Timeout) && receiver.received()==1 && lastLocalSample==base);
  armDeadline(); fakeMillis=base+kPeerSilenceMs-1; queueFrame(dataType,900,1);
  radioRxTimeKnown=false; fakeMillis=base+kPeerSilenceMs+5; lastWdt=fakeMillis; loop();
  assert(state==(LT_ROLE==1 ? TestState::Stopping : TestState::Timeout) && receiver.received()==0);
#if LT_ROLE == 2
  armDeadline(); fakeMillis=base+kPeerSilenceMs-1; queueFrame(RadioStop,900);
  fakeMillis=base+kPeerSilenceMs+5; lastWdt=fakeMillis; loop();
  assert(state==TestState::Stopped && lastType()==RadioStopAck);
#endif
  // A failed transition to standby fails closed instead of transmitting.
  radioReady=true; radioRx=false; fakeStandbyResult=-9; state=TestState::Running;
  const auto beforeFailure=fakeTx.size();
  assert(!transmit(LT_ROLE==1 ? RadioReverseData : RadioData,session,0));
  assert(!radioReady && state==TestState::Error && fakeTx.size()==beforeFailure);
  radioReady=true; fakeStandbyResult=0; fakeIrqResult=-8; state=TestState::Running;
  assert(!transmit(LT_ROLE==1 ? RadioReverseData : RadioData,session,0));
  assert(!radioReady && state==TestState::Error && fakeTx.size()==beforeFailure);
  radioReady=true; fakeIrqResult=0; fakeStartRxResult=-10; state=TestState::Running;
  assert(!transmit(LT_ROLE==1 ? RadioReverseData : RadioData,session,0));
  assert(!radioReady && state==TestState::Error && fakeTx.size()==beforeFailure+1);
  // A frame may have reached the receiver, but failed re-arming prevents
  // parsing it or replacing Error with a new state.
  radioReady=true; state=TestState::Running; radioRx=true;
  const auto beforeRxFailure=fakeTx.size(); loop();
  assert(!radioReady && state==TestState::Error && fakeTx.size()==beforeRxFailure);
  fakeStartRxResult=0;
  std::printf("CH%d deterministic loop fault tests passed\n", LT_ROLE);
}
