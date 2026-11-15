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
// Continuous half-duplex slots. The radio sequence wraps at 255; the next
// deadline uses modular millis arithmetic and is advanced without catch-up TX.
class LiveSlotSchedule {
 public:
  void begin(uint32_t epoch, uint32_t offset) { deadline_ = epoch + offset; sequence_ = 0; }
  SlotDecision next(uint32_t now, uint16_t& sequence) {
    int32_t late = static_cast<int32_t>(now - deadline_);
    if (late < 0) return SlotDecision::Waiting;
    const uint32_t skipped = static_cast<uint32_t>(late) / 2000;
    if (skipped || late > 350) {
      const uint32_t advance = skipped + 1;
      sequence_ = static_cast<uint8_t>(sequence_ + advance);
      deadline_ += advance * 2000U;
      return SlotDecision::Skip;
    }
    sequence = sequence_++;
    deadline_ += 2000;
    return SlotDecision::Send;
  }
  bool stopWindow(uint32_t now) const {
    const int32_t sincePrevious = static_cast<int32_t>(now - (deadline_ - 2000U));
    return sincePrevious >= 0 && (static_cast<uint32_t>(sincePrevious) % 2000U) <= 200;
  }
 private:
  uint32_t deadline_ = 0;
  uint8_t sequence_ = 0;
};
}
