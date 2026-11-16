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
inline int packetX(uint32_t now) {
  const uint32_t phase=now%1000U;
  return 100 + int(phase<500 ? phase*44/500 : (1000-phase)*44/500);
}
}
