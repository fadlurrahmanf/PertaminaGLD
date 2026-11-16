#pragma once
#include <cstdint>

namespace runninganimation {
constexpr int kTrackY=96;
constexpr int kRtDir1=107, kRtValue1=122, kRtUnits1=135;
constexpr int kRtDir2=144, kRtValue2=159, kRtUnits2=172;
// The graphic is decorative and is never a source of packet measurements.
inline bool visible(bool tester, bool simulation, bool link, bool running,
                    uint8_t state, bool stopPending, bool stopUnconfirmed,
                    bool calibration) {
  return tester && !simulation && link && running && state==2 &&
         !stopPending && !stopUnconfirmed && !calibration;
}
constexpr uint32_t kPacketDurationMs=900;
struct Packet { bool visible; int x; };
inline Packet packet(uint32_t now, uint32_t observedAt, bool observed, bool ch1ToCh2) {
  const uint32_t elapsed=now-observedAt;
  if (!observed || elapsed>=kPacketDurationMs) return {false,0};
  const int distance=int((elapsed*44U+kPacketDurationMs/2)/kPacketDurationMs);
  return {true,ch1ToCh2 ? 100+distance : 144-distance};
}
inline int packetY(bool ch1ToCh2, bool both) { return both ? (ch1ToCh2 ? 93 : 99) : 96; }
}
