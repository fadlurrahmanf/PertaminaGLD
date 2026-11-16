#include "LoRaTesterSession.h"
#include "LoRaTesterWire.h"
#include "DiscoveryBinding.h"
#include "SlotSchedule.h"
#include "AppFrame.h"
#include "BatteryHealth.h"

#include <cassert>
#include <cstddef>

int main() {
  using namespace loratester;
  static_assert(sizeof(DirectionStats) == 20, "direction format mismatch");
  static_assert(sizeof(NowMessage) == 96, "wire format mismatch");
  static_assert(offsetof(NowMessage, sampleSeqFromCh2) == 93, "sample sequence offset mismatch");
  static_assert(offsetof(NowMessage, ch1Health) == 73, "CH1 health offset mismatch");
  static_assert(offsetof(NowMessage, ch2Health) == 83, "CH2 health offset mismatch");
  static_assert(offsetof(NowMessage, bootNonce) == 69, "boot nonce offset mismatch");
  static_assert(offsetof(NowMessage, reportSeq) == 65, "sequence offset mismatch");
  static_assert(offsetof(NowMessage, ageCh2Ms) == 57, "age offset mismatch");
  static_assert(offsetof(NowMessage, sentCh2) == 61, "progress offset mismatch");
  static_assert(offsetof(NowMessage, phase) == 16, "phase offset mismatch");
  static_assert(offsetof(NowMessage, fromCh2) == 17, "forward offset mismatch");
  static_assert(offsetof(NowMessage, fromCh1) == 37, "reverse offset mismatch");
  assert(kNowVersion == 8);
  auto h = unknownHealth();
  assert(!validHealth(h)); h.nodeBootNonce=1; h.ageSeconds=0;
  assert(validHealth(h) && h.batteryMv==0xffff && h.batteryPct==0xff);
  h.flags=kHealthBatteryValid; h.batteryMv=3700; h.batteryPct=50;
  assert(!validHealth(h)); h.flags|=kHealthAdcCalibrated; assert(validHealth(h));
  uint16_t battMv=0; uint8_t battPct=0;
  assert(calibratedBattery(1200,3000,4200,0,battMv,battPct) && battMv==3600 && battPct==50);
  assert(!calibratedBattery(0,3000,4200,0,battMv,battPct));
  assert(!calibratedBattery(1200,4200,3000,0,battMv,battPct));
  assert(kNowStart == 1 && kNowStatus == 2 && kNowStop == 3);
  assert(kNowDiscover == 4 && kNowPresence == 5);
  assert(static_cast<uint8_t>(TestState::Stopping) == 6);
  assert(static_cast<uint8_t>(TestState::Stopped) == 7);
  ReceiverSession s;
  assert(s.receive(1, 0xF2, 0, -80, 5) == ReceiveResult::Inactive);
  s.start(0x1234, 0xF2);
  assert(!s.metricsValid() && s.received() == 0 && s.notYetReceived() == 100);
  assert(s.receive(0x1235, 0xF2, 0, -80, 5) == ReceiveResult::WrongSession);
  assert(s.receive(0x1234, 0xF3, 0, -80, 5) == ReceiveResult::WrongPeer);
  assert(s.receive(0x1234, 0xF2, 100, -80, 5) == ReceiveResult::OutOfRange);
  assert(s.receive(0x1234, 0xF2, 42, -110, -80) == ReceiveResult::Accepted);
  assert(s.receive(0x1234, 0xF2, 42, -10, 10) == ReceiveResult::Duplicate);
  assert(s.received() == 1 && s.metricsValid() && s.latestRssiDbm() == -110 && s.latestSnrDb10() == -8);
  for (uint16_t i = 0; i < kPacketCount; ++i) {
    if (i != 42) assert(s.receive(0x1234, 0xF2, i, -90, 4) == ReceiveResult::Accepted);
  }
  assert(s.complete() && s.received() == 100 && s.notYetReceived() == 0);
  s.stop();
  assert(s.receive(0x1234, 0xF2, 0, -80, 5) == ReceiveResult::Inactive);
  s.start(0x5678, 0xF2);
  assert(!s.complete() && !s.metricsValid() && s.received() == 0);
  assert(s.receive(0x1234, 0xF2, 0, -80, 5) == ReceiveResult::WrongSession);

  s.start(1, 9);
  assert(s.receive(1, 9, 0, -90, -10) == ReceiveResult::Accepted);
  assert(s.receive(1, 9, 1, -91, -20) == ReceiveResult::Accepted);
  assert(s.receive(1, 9, 2, -91, 0) == ReceiveResult::Accepted);
  assert(s.receive(1, 9, 2, 100, 100) == ReceiveResult::Duplicate);
  assert(s.averageRssiDbm10() == -907 && s.minRssiDbm() == -91 && s.maxRssiDbm() == -90);
  assert(s.averageSnrDb10() == -1 && s.minSnrDb10() == -2 && s.maxSnrDb10() == 0);
  s.start(2, 9);
  for (int i = 0; i < 4; ++i) {
    assert(s.receive(2, 9, i, i == 0 ? 1 : 0, i == 0 ? -100 : 0) == ReceiveResult::Accepted);
  }
  assert(s.averageRssiDbm10() == 3 && s.averageSnrDb10() == -3);
  s.start(3, 9);
  assert(s.receive(3, 9, 0, 32767, 12700) == ReceiveResult::Accepted);
  assert(s.averageRssiDbm10() == 32767 && s.averageSnrDb10() == 1270);
  s.start(4, 9);
  assert(s.receive(4, 9, 0, -32768, -12800) == ReceiveResult::Accepted);
  assert(s.averageRssiDbm10() == -32768 && s.averageSnrDb10() == -1280);
  s.start(5, 9);
  assert(s.receive(5, 9, 0, -90, -730) == ReceiveResult::Accepted);
  assert(s.receive(5, 9, 1, -91, -680) == ReceiveResult::Accepted);
  assert(s.latestSnrDb10() == -68 && s.minSnrDb10() == -73 && s.maxSnrDb10() == -68);
  assert(s.averageSnrDb10() == -71); // -7.05 dB rounded away from zero
  s.start(6, 9);
  assert(s.receive(6, 9, 0, -90, -725) == ReceiveResult::Accepted);
  assert(s.receive(6, 9, 1, -90, -675) == ReceiveResult::Accepted);
  assert(s.minSnrDb10() == -73 && s.maxSnrDb10() == -68 && s.averageSnrDb10() == -70);

  DiscoveryBinding binding;
  const uint8_t a[] = {1,2,3,4,5,6}, b[] = {1,2,3,4,5,7};
  assert(!binding.consider(nullptr, 0, false));
  assert(binding.consider(a, 100, false) && binding.matches(a));
  assert(!binding.consider(b, 200, false));
  assert(!binding.consider(b, 20000, true));
  assert(binding.matches(a));
  assert(binding.consider(b, 20000, false) && binding.matches(b));
  assert(!binding.expire(25000, false));
  assert(binding.expire(30000, false));
  assert(binding.consider(a, 0xfffffff0U, false));
  assert(!binding.expire(50, false)); // millis() wrap is safe.
  assert(binding.expire(10000, false));
  SessionOwner owner;
  assert(!owner.matches(a)); // Fresh boot has no recoverable RAM session.
  owner.set(a);
  assert(owner.matches(a) && !owner.matches(b));
  assert(binding.consider(b, 20000, false));
  assert(binding.matches(b) && !owner.matches(b)); // New peer cannot claim old results.
  owner.set(b);
  assert(owner.matches(b) && !owner.matches(a));
  owner.set(nullptr);
  assert(!owner.matches(b));
  SlotSchedule slots; uint16_t seq = 999;
  slots.begin(0xfffffff0U, 0);
  assert(slots.next(0xffffffefU, seq) == SlotDecision::Waiting);
  assert(slots.next(0xfffffff0U, seq) == SlotDecision::Send && seq == 0);
  assert(slots.next(1984U, seq) == SlotDecision::Send && seq == 1);
  assert(slots.next(4335U, seq) == SlotDecision::Skip && seq == 2);
  assert(slots.next(4335U, seq) == SlotDecision::Waiting);
  slots.begin(10000, 1000);
  assert(slots.next(10999, seq) == SlotDecision::Waiting);
  assert(slots.next(11350, seq) == SlotDecision::Send && seq == 0);
  assert(slots.next(15351, seq) == SlotDecision::Skip && seq == 1);
  assert(slots.next(15351, seq) == SlotDecision::Skip && seq == 2);
  assert(slots.next(15351, seq) == SlotDecision::Waiting);
  for (uint16_t i = 3; i < 100; ++i)
    assert(slots.next(11000 + uint32_t(i) * 2000, seq) == SlotDecision::Send && seq == i);
  assert(slots.elapsed() == 100 && slots.next(300000, seq) == SlotDecision::Finished);
  LiveSlotSchedule live; live.begin(0xfffffff0U,0);
  for (unsigned i=0; i<257; ++i) {
    uint32_t when=0xfffffff0U+i*2000U;
    assert(live.next(when,seq)==SlotDecision::Send && seq==uint8_t(i));
  }
  assert(live.next(0xfffffff0U+257U*2000U+500U,seq)==SlotDecision::Skip);
  assert(live.next(0xfffffff0U+257U*2000U+500U,seq)==SlotDecision::Waiting);
  assert(live.next(0xfffffff0U+258U*2000U,seq)==SlotDecision::Send && seq==2);
  s.start(99,9);
  assert(s.receiveLive(99,9,254,-95,-725)==ReceiveResult::Accepted);
  assert(s.receiveLive(99,9,255,-95,-725)==ReceiveResult::Accepted);
  assert(s.receiveLive(99,9,0,-95,-675)==ReceiveResult::Accepted);
  assert(s.receiveLive(99,9,255,-95,100)==ReceiveResult::Duplicate);
  assert(s.receiveLive(99,9,0,-95,100)==ReceiveResult::Duplicate);
  assert(s.received()==1 && s.latestSnrDb10()==-68);
  assert(stopWindow(999, 1000, true));
  assert(!stopWindow(1000, 1000, true));
  assert(!stopWindow(1999, 1000, true));
  assert(stopWindow(2000, 1000, true));
  assert(stopWindow(2200, 1000, true));
  assert(!stopWindow(2201, 1000, true));
  assert(stopWindow(3000, 1000, false));
  assert(stopWindow(984, 0xfffffff0U, true)); // epoch + 1000 across wrap
  uint8_t data[40] = {}, frame[50] = {};
  const unsigned sizes[] = {29U, 40U};
  for (unsigned size : sizes) {
    auto encoded = pgl::protocol::encodeAppFrame(0x3f, 0x10, 0xf2, 42, data, size,
                                               frame, sizeof(frame), pgl::protocol::MESH_MAX_PAYLOAD);
    assert(encoded.status == pgl::protocol::FrameStatus::Ok && encoded.size == size + 10);
    pgl::protocol::FrameView view{};
    assert(pgl::protocol::decodeAppFrame(frame, encoded.size, view, pgl::protocol::MESH_MAX_PAYLOAD) == pgl::protocol::FrameStatus::Ok);
    assert(view.typeFlags == 0x3f && view.srcId == 0x10 && view.dstId == 0xf2 && view.seq == 42 && view.payloadLen == size);
    frame[10] ^= 1;
    assert(pgl::protocol::decodeAppFrame(frame, encoded.size, view, pgl::protocol::MESH_MAX_PAYLOAD) == pgl::protocol::FrameStatus::BadCrc);
  }
}
