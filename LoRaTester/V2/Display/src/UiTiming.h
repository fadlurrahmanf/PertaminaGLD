#pragma once
#include <cstdint>
namespace uitiming {
constexpr uint32_t kHoldMs = 800;
constexpr uint32_t kHoldBarPixels = 62;
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
