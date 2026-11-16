#pragma once
#include "../../CH/include/LoRaTesterWire.h"
namespace uinavigation {
enum class TestLongAction { Back, Start, Stop, Wait };
inline int nextTestPage(int page, bool realtime, bool done) {
  if (realtime) return page==3 ? 0 : 3;
  if (done) {
    if (page==2) return 1;
    if (page==1) return 3;
    if (page==3) return 4;
    return 2; // Summary or leftover page 0 goes to CH1 -> CH2.
  }
  return (page+1)%5;
}
inline TestLongAction testLongAction(int page, bool running, bool canStart) {
  if (page==3) return TestLongAction::Back;
  if (running) return TestLongAction::Stop;
  return canStart ? TestLongAction::Start : TestLongAction::Wait;
}
inline bool isCh1ToCh2(int page) { return page==2; }
inline const loratester::DirectionStats& directionStats(const loratester::NowMessage& s, int page) {
  return isCh1ToCh2(page) ? s.fromCh1 : s.fromCh2;
}
inline const char* directionLabel(int page) { return isCh1ToCh2(page) ? "CH1 -> CH2" : "CH2 -> CH1"; }
}
