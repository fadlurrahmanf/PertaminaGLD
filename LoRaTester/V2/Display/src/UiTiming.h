#pragma once
#include <cstdint>
namespace uitiming {
constexpr uint32_t kHoldMs = 800;
constexpr uint32_t kHoldBarPixels = 62;
inline uint32_t holdBarPixels(uint32_t elapsed) {
  return elapsed >= kHoldMs ? kHoldBarPixels : elapsed * kHoldBarPixels / kHoldMs;
}
}
