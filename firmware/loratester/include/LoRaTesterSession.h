#pragma once

#include <cstdint>

// Pure session accounting. No radio, timing, persistent storage, or GPIO.
namespace loratester {

constexpr uint16_t kPacketCount = 100;

enum class ReceiveResult : uint8_t {
  Accepted, Duplicate, WrongSession, WrongPeer, OutOfRange, Inactive
};

class ReceiverSession {
 public:
  void start(uint32_t sessionId, uint16_t peerId) {
    sessionId_ = sessionId;
    peerId_ = peerId;
    received_ = 0;
    latestRssi_ = 0;
    latestSnr_ = 0;
    sumRssi_ = 0;
    sumSnr_ = 0;
    minRssi_ = maxRssi_ = 0;
    minSnr_ = maxSnr_ = 0;
    metricsValid_ = false;
    active_ = true;
    for (auto& item : seen_) item = false;
  }

  ReceiveResult receive(uint32_t sessionId, uint16_t peerId, uint16_t sequence,
                        int16_t rssiDbm, int8_t snrDb) {
    if (!active_) return ReceiveResult::Inactive;
    if (sessionId != sessionId_) return ReceiveResult::WrongSession;
    if (peerId != peerId_) return ReceiveResult::WrongPeer;
    if (sequence >= kPacketCount) return ReceiveResult::OutOfRange;
    if (seen_[sequence]) return ReceiveResult::Duplicate;
    if (received_ == 0) {
      minRssi_ = maxRssi_ = rssiDbm;
      minSnr_ = maxSnr_ = snrDb;
    } else {
      if (rssiDbm < minRssi_) minRssi_ = rssiDbm;
      if (rssiDbm > maxRssi_) maxRssi_ = rssiDbm;
      if (snrDb < minSnr_) minSnr_ = snrDb;
      if (snrDb > maxSnr_) maxSnr_ = snrDb;
    }
    sumRssi_ += rssiDbm;
    sumSnr_ += snrDb;
    seen_[sequence] = true;
    ++received_;
    latestRssi_ = rssiDbm;
    latestSnr_ = snrDb;
    metricsValid_ = true;
    return ReceiveResult::Accepted;
  }

  void stop() { active_ = false; }
  bool active() const { return active_; }
  bool complete() const { return received_ == kPacketCount; }
  uint16_t received() const { return received_; }
  // A count is only a final loss count after the sender finished or timed out.
  uint16_t notYetReceived() const { return kPacketCount - received_; }
  bool metricsValid() const { return metricsValid_; }
  int16_t latestRssiDbm() const { return latestRssi_; }
  int8_t latestSnrDb() const { return latestSnr_; }
  int16_t averageRssiDbm10() const { return average10(sumRssi_); }
  int16_t minRssiDbm() const { return minRssi_; }
  int16_t maxRssiDbm() const { return maxRssi_; }
  int16_t averageSnrDb10() const { return average10(sumSnr_); }
  int8_t minSnrDb() const { return minSnr_; }
  int8_t maxSnrDb() const { return maxSnr_; }

 private:
  int16_t average10(int32_t sum) const {
    if (!received_) return 0;
    // At most 100 int16 samples: scaled total fits in signed 32 bits.
    int32_t scaled = sum * 10;
    int32_t rounded = (scaled >= 0 ? scaled + received_ / 2 : scaled - received_ / 2) / received_;
    if (rounded > 32767) return 32767;
    if (rounded < -32768) return -32768;
    return static_cast<int16_t>(rounded);
  }
  uint32_t sessionId_ = 0;
  uint16_t peerId_ = 0;
  uint16_t received_ = 0;
  int16_t latestRssi_ = 0;
  int8_t latestSnr_ = 0;
  int32_t sumRssi_ = 0, sumSnr_ = 0;
  int16_t minRssi_ = 0, maxRssi_ = 0;
  int8_t minSnr_ = 0, maxSnr_ = 0;
  bool metricsValid_ = false;
  bool active_ = false;
  bool seen_[kPacketCount] = {};
};
}  // namespace loratester
