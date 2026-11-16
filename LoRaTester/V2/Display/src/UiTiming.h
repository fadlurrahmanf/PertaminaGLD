#pragma once
#include <cstdint>
namespace uitiming {
constexpr uint32_t kHoldMs = 800;
constexpr uint32_t kHoldBarPixels = 62;
inline float ringAngle(int item) { return (item*6.2831853f/100.0f)-1.5707963f; }
inline uint32_t observedPacketProgress(uint32_t observedAt, uint32_t now, bool hasObservation) {
  if (!hasObservation) return 0;
  const uint32_t elapsed=now-observedAt;
  return elapsed>=2000 ? 100 : elapsed*100/2000;
}
struct RingAnimation {
  uint32_t session=0, frame=0, observation=0;
  int scene=0;
  bool active=false;
  uint32_t next(int sceneId, uint32_t sessionId, bool visible, uint32_t observedAt=0) {
    if (!visible) { active=false; return 0; }
    if (!active || sceneId!=scene || (sessionId && sessionId!=session) || observedAt!=observation) {
      active=true; scene=sceneId; session=sessionId; observation=observedAt; frame=0; return frame;
    }
    return ++frame;
  }
};
inline uint32_t holdBarPixels(uint32_t elapsed) {
  return elapsed >= kHoldMs ? kHoldBarPixels : elapsed * kHoldBarPixels / kHoldMs;
}
// Animate only inside real progress; one pixel cannot move around a 0/1-item
// range, so do not invent progress to increase the reported blit rate.
inline bool ringHighlight(int progress, uint32_t frame, int item) {
  if (progress<=0 || item<0 || item>=progress) return false;
  const int width=progress>3 ? 3 : 1;
  const int head=frame % static_cast<uint32_t>(progress);
  return (item+progress-head)%progress < width;
}
}
