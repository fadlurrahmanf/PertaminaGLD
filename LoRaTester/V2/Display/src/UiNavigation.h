#pragma once
namespace uinavigation {
enum class TestLongAction { Back, Start, Stop, Wait };
inline int nextTestPage(int page, bool realtime, bool done) {
  if (realtime) return page==3 ? 0 : 3;
  if (done) {
    if (page==1) return 2;
    if (page==2) return 3;
    if (page==3) return 4;
    return 1; // Summary or any leftover page 0 goes to first direction.
  }
  return (page+1)%5;
}
inline TestLongAction testLongAction(int page, bool running, bool canStart) {
  if (page==3) return TestLongAction::Back;
  if (running) return TestLongAction::Stop;
  return canStart ? TestLongAction::Start : TestLongAction::Wait;
}
}
