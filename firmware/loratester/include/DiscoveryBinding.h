#pragma once
#include <cstdint>
#include <cstring>

namespace loratester {
// Bench-only source selection, not authentication. Keep the bound monitor
// throughout active tests; expire an idle binding after its heartbeat stops.
class DiscoveryBinding {
 public:
  static constexpr uint32_t kIdleTimeoutMs = 10000;
  bool consider(const uint8_t* mac, uint32_t now, bool active) {
    if (!mac) return false;
    expire(now, active);
    if (!bound_) { std::memcpy(mac_, mac, sizeof(mac_)); bound_ = true; }
    if (std::memcmp(mac_, mac, sizeof(mac_)) != 0) return false;
    seenAt_ = now;
    return true;
  }
  bool expire(uint32_t now, bool active) {
    if (bound_ && !active && uint32_t(now - seenAt_) >= kIdleTimeoutMs) {
      bound_ = false; return true;
    }
    return false;
  }
  bool matches(const uint8_t* mac) const {
    return bound_ && mac && std::memcmp(mac_, mac, sizeof(mac_)) == 0;
  }
  bool bound() const { return bound_; }
  void clear() { bound_ = false; }
 private:
  uint8_t mac_[6] = {};
  uint32_t seenAt_ = 0;
  bool bound_ = false;
};

// The last test result belongs to the monitor that started it. An idle
// discovery rebinding must not transfer the previous session to another peer.
class SessionOwner {
 public:
  void set(const uint8_t* mac) {
    if (!mac) { valid_ = false; return; }
    std::memcpy(mac_, mac, sizeof(mac_)); valid_ = true;
  }
  bool matches(const uint8_t* mac) const {
    return valid_ && mac && std::memcmp(mac_, mac, sizeof(mac_)) == 0;
  }
 private:
  uint8_t mac_[6] = {};
  bool valid_ = false;
};
}  // namespace loratester
