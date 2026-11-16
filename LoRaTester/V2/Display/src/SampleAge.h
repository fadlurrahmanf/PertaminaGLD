#pragma once
#include <cstdint>
namespace sampleage {
constexpr uint16_t kUnknown=0xffff;
constexpr uint16_t kMaxKnown=0xfffe;
inline uint16_t effective(uint16_t reported, uint32_t receivedAt, uint32_t now, bool statusSeen) {
  if (!statusSeen || reported==kUnknown) return kUnknown;
  const uint32_t elapsed=now-receivedAt;
  if (elapsed>=kMaxKnown || reported>kMaxKnown-elapsed) return kMaxKnown;
  return static_cast<uint16_t>(reported+elapsed);
}
}
