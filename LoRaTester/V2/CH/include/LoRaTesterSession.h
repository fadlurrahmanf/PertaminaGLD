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
    liveSeen_ = false;
    active_ = true;
    for (auto& item : seen_) item = false;
  }

  // Live mode keeps a single latest unique sample, not packet-loss statistics.
  // Sequence distance >=128 is treated as old; the 12 s timeout bounds gaps.
  ReceiveResult receiveLive(uint32_t sid, uint16_t peer, uint8_t seq, int16_t rssi, int16_t snr100) {
    if (!active_) return ReceiveResult::Inactive;
    if (sid != sessionId_) return ReceiveResult::WrongSession;
    if (peer != peerId_) return ReceiveResult::WrongPeer;
    const uint8_t distance = static_cast<uint8_t>(seq - liveSeq_);
    if (liveSeen_ && (distance == 0 || distance >= 128)) return ReceiveResult::Duplicate;
    liveSeen_ = true; liveSeq_ = seq;
    received_ = 0; sumRssi_ = sumSnr_ = 0; metricsValid_ = false;
    for (auto& item : seen_) item = false;
    return receive(sid, peer, 0, rssi, snr100);
  }

  ReceiveResult receive(uint32_t sessionId, uint16_t peerId, uint16_t sequence,
                        int16_t rssiDbm, int16_t snrDb100) {
    if (!active_) return ReceiveResult::Inactive;
    if (sessionId != sessionId_) return ReceiveResult::WrongSession;
    if (peerId != peerId_) return ReceiveResult::WrongPeer;
    if (sequence >= kPacketCount) return ReceiveResult::OutOfRange;
    if (seen_[sequence]) return ReceiveResult::Duplicate;
    if (received_ == 0) {
      minRssi_ = maxRssi_ = rssiDbm;
      minSnr_ = maxSnr_ = snrDb100;
    } else {
      if (rssiDbm < minRssi_) minRssi_ = rssiDbm;
      if (rssiDbm > maxRssi_) maxRssi_ = rssiDbm;
      if (snrDb100 < minSnr_) minSnr_ = snrDb100;
      if (snrDb100 > maxSnr_) maxSnr_ = snrDb100;
    }
    sumRssi_ += rssiDbm;
    sumSnr_ += snrDb100;
    seen_[sequence] = true;
    ++received_;
    latestRssi_ = rssiDbm;
    latestSnr_ = snrDb100;
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
  int16_t latestSnrDb10() const { return divideRound(latestSnr_, 10); }
  int16_t averageRssiDbm10() const { return average10(sumRssi_); }
  int16_t minRssiDbm() const { return minRssi_; }
  int16_t maxRssiDbm() const { return maxRssi_; }
  int16_t averageSnrDb10() const { return received_ ? divideRound(sumSnr_, int32_t(received_) * 10) : 0; }
  int16_t minSnrDb10() const { return divideRound(minSnr_, 10); }
  int16_t maxSnrDb10() const { return divideRound(maxSnr_, 10); }

 private:
  int16_t divideRound(int32_t sum, int32_t divisor) const {
    int32_t rounded = (sum >= 0 ? sum + divisor / 2 : sum - divisor / 2) / divisor;
    if (rounded > 32767) return 32767;
    if (rounded < -32768) return -32768;
    return static_cast<int16_t>(rounded);
  }
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
  int16_t latestSnr_ = 0;
  int32_t sumRssi_ = 0, sumSnr_ = 0;
  int16_t minRssi_ = 0, maxRssi_ = 0;
  int16_t minSnr_ = 0, maxSnr_ = 0;
  bool metricsValid_ = false;
  bool liveSeen_ = false;
  uint8_t liveSeq_ = 0;
  bool active_ = false;
  bool seen_[kPacketCount] = {};
};
}  // namespace loratester
