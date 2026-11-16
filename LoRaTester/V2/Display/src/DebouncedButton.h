#pragma once
#include <cstdint>
#include "UiTiming.h"

class DebouncedButton {
 public:
  enum class Event : uint8_t { None, Short, Long };
  Event update(bool rawLow, uint32_t now) {
    if (rawLow!=observedLow_) { observedLow_=rawLow; changedAt_=now; }
    if (observedLow_!=stableLow_ && uint32_t(now-changedAt_)>=30) {
      stableLow_=observedLow_;
      if (stableLow_) { pressedAt_=changedAt_; longHandled_=false; }
      else if (!longHandled_) {
        longHandled_=true;
        return uint32_t(changedAt_-pressedAt_)>=uitiming::kHoldMs ? Event::Long : Event::Short;
      }
    }
    if (stableLow_ && observedLow_ && !longHandled_ && uint32_t(now-pressedAt_)>=uitiming::kHoldMs) {
      longHandled_=true; return Event::Long;
    }
    return Event::None;
  }
  bool pressed() const { return stableLow_; }
  bool longHandled() const { return longHandled_; }
  uint32_t pressedAt() const { return pressedAt_; }
 private:
  bool observedLow_=false, stableLow_=false, longHandled_=false;
  uint32_t changedAt_=0, pressedAt_=0;
};
