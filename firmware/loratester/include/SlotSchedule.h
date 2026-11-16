#pragma once
#include <cstdint>
namespace loratester {
enum class SlotDecision : uint8_t { Waiting, Send, Skip, Finished };
inline bool stopWindow(uint32_t now, uint32_t epoch, bool synced) {
  const int32_t elapsed = static_cast<int32_t>(now - epoch);
  if (!synced || elapsed < 0 || elapsed >= 200000) return true;
  const uint32_t phase = static_cast<uint32_t>(elapsed) % 2000;
  return phase >= 1000 && phase <= 1200;
}
// Fixed 1 s alternating slots; late local work is never sent as a burst.
class SlotSchedule {
 public:
  void begin(uint32_t epoch, uint32_t offset) { epoch_ = epoch + offset; next_ = 0; }
  SlotDecision next(uint32_t now, uint16_t& sequence) {
    if (next_ >= 100) return SlotDecision::Finished;
    const int32_t late = static_cast<int32_t>(now - (epoch_ + uint32_t(next_) * 2000));
    if (late < 0) return SlotDecision::Waiting;
    sequence = next_++;
    return late <= 350 ? SlotDecision::Send : SlotDecision::Skip;
  }
  uint16_t elapsed() const { return next_; }
 private:
  uint32_t epoch_ = 0; uint16_t next_ = 0;
};
}
