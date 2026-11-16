#pragma once
#include <cstdint>
// Windowed measured task rates and worst times; no invented display scan rate.
struct FrameStats {
  uint32_t windowAt=0, renders=0, blits=0, full=0, pixels=0, maxFrameUs=0, maxBlitUs=0, maxLoopUs=0;
  uint32_t holdUpdates=0, maxHoldUs=0;
  uint32_t lastWindowUs=0, lastRenders=0, lastBlits=0, lastFull=0, lastPixels=0, lastMaxFrameUs=0, lastMaxBlitUs=0, lastMaxLoopUs=0;
  uint32_t lastHoldUpdates=0, lastMaxHoldUs=0;
  void loop(uint32_t elapsedUs) { if (elapsedUs>maxLoopUs) maxLoopUs=elapsedUs; }
  void frame(uint32_t frameUs, uint32_t blitUs, uint32_t changedPixels, bool wasFull) {
    ++renders; if (changedPixels) ++blits; if (wasFull) ++full; pixels+=changedPixels;
    if(frameUs>maxFrameUs) maxFrameUs=frameUs; if(blitUs>maxBlitUs) maxBlitUs=blitUs;
  }
  void hold(uint32_t elapsedUs) { ++holdUpdates; if (elapsedUs>maxHoldUs) maxHoldUs=elapsedUs; }
  void tick(uint32_t now) {
    if (!windowAt) { windowAt=now; return; }
    const uint32_t elapsed=now-windowAt;
    if (elapsed<1000000) return;
    lastWindowUs=elapsed;lastRenders=renders;lastBlits=blits;lastFull=full;lastPixels=pixels;
    lastMaxFrameUs=maxFrameUs;lastMaxBlitUs=maxBlitUs;lastMaxLoopUs=maxLoopUs;
    lastHoldUpdates=holdUpdates;lastMaxHoldUs=maxHoldUs;
    windowAt=now;renders=blits=full=pixels=maxFrameUs=maxBlitUs=maxLoopUs=0;
    holdUpdates=maxHoldUs=0;
  }
};
