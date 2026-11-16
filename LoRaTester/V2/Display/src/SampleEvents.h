#pragma once
#include <cstdint>
// A displayed event is emitted only when the corresponding sample identifier
// was actually reported in the current session, not when an age merely drops.
struct SampleEvents {
  uint32_t session=0;
  uint8_t lastCh2=0, lastCh1=0, seen=0;
  uint8_t update(uint32_t sid, uint8_t valid, uint8_t seqCh2, uint8_t seqCh1) {
    if (sid!=session) { session=sid; seen=0; }
    uint8_t changed=0;
    if ((valid&1) && (!(seen&1) || lastCh2!=seqCh2)) { changed|=1; lastCh2=seqCh2; seen|=1; }
    if ((valid&2) && (!(seen&2) || lastCh1!=seqCh1)) { changed|=2; lastCh1=seqCh1; seen|=2; }
    return changed;
  }
};

// A missing snapshot is not a new session and must not replay old counts.
struct PdrPacketEvents {
  uint32_t session=0;
  uint16_t lastCh2=0, lastCh1=0;
  uint8_t update(uint32_t sid, uint16_t countCh2, uint16_t countCh1) {
    if (!sid) return 0;
    if (sid!=session) { session=sid; lastCh2=lastCh1=0; }
    uint8_t changed=0;
    if (countCh2>lastCh2) { changed|=1; lastCh2=countCh2; }
    if (countCh1>lastCh1) { changed|=2; lastCh1=countCh1; }
    return changed;
  }
};
