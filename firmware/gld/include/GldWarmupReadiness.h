#pragma once

#include <cmath>
#include <cstdint>

// Standalone candidate evaluator. It has no production defaults and is not
// connected to the inference/alarm path until its parameters are validated.
namespace pgl { namespace gld {

class GldWarmupReadiness {
public:
    static constexpr uint8_t kChannels = 8;
    static constexpr uint8_t kMaxWindow = 32;
    struct Config {
        uint32_t minWarmupMs;
        uint32_t minSampleIntervalMs;
        uint32_t maxSampleGapMs;
        uint8_t windowSamples;
        uint8_t consecutiveWindows;
        float maxSpreadVolts[kChannels];
    };

    explicit GldWarmupReadiness(const Config& config) : config_(config) {
        configValid_ = config.minWarmupMs > 0 && config.minWarmupMs < 0x80000000UL &&
            config.minSampleIntervalMs > 0 && config.maxSampleGapMs >= config.minSampleIntervalMs &&
            config.maxSampleGapMs < 0x80000000UL && config.windowSamples >= 2 &&
            config.windowSamples <= kMaxWindow && config.consecutiveWindows > 0;
        for (float limit : config.maxSpreadVolts)
            configValid_ = configValid_ && std::isfinite(limit) && limit > 0.0f;
    }

    // Call on every known interruption or uncertain state of sensor power.
    void reset(uint32_t now) {
        startedAt_ = now;
        started_ = true;
        haveSample_ = false;
        for (auto& channel : channels_) channel = Channel{};
    }

    // validMask must exclude bad, saturated, unpowered and non-finite readings.
    void sample(uint32_t now, const float values[kChannels], uint8_t validMask) {
        if (!configValid_ || !started_ || values == nullptr) return;
        // A fault must revoke readiness immediately, even between timed samples.
        for (uint8_t i = 0; i < kChannels; ++i)
            if (!(validMask & (1U << i)) || !std::isfinite(values[i]))
                channels_[i] = Channel{};
        if (haveSample_) {
            const uint32_t gap = now - lastSampleAt_;
            if (gap < config_.minSampleIntervalMs) return;
            if (gap > config_.maxSampleGapMs)
                for (auto& channel : channels_) channel = Channel{};
        }
        haveSample_ = true;
        lastSampleAt_ = now;
        for (uint8_t i = 0; i < kChannels; ++i) {
            auto& channel = channels_[i];
            if (!(validMask & (1U << i)) || !std::isfinite(values[i])) {
                channel = Channel{};
                continue;
            }
            channel.samples[channel.next] = values[i];
            channel.next = static_cast<uint8_t>((channel.next + 1U) % config_.windowSamples);
            if (channel.count < config_.windowSamples) ++channel.count;
            if (channel.count < config_.windowSamples) continue;
            float low = channel.samples[0], high = low;
            for (uint8_t j = 1; j < config_.windowSamples; ++j) {
                if (channel.samples[j] < low) low = channel.samples[j];
                if (channel.samples[j] > high) high = channel.samples[j];
            }
            if (high - low <= config_.maxSpreadVolts[i]) {
                if (channel.stableWindows < config_.consecutiveWindows) ++channel.stableWindows;
            } else {
                channel.stableWindows = 0;
            }
        }
    }

    uint8_t stableMask(uint32_t now) const {
        uint8_t mask = 0;
        if (!configValid_ || !started_ || !haveSample_ ||
            now - lastSampleAt_ > config_.maxSampleGapMs) return mask;
        for (uint8_t i = 0; i < kChannels; ++i)
            if (channels_[i].stableWindows >= config_.consecutiveWindows) mask |= 1U << i;
        return mask;
    }
    bool ready(uint32_t now) const {
        return configValid_ && started_ && haveSample_ &&
            now - lastSampleAt_ <= config_.maxSampleGapMs &&
            now - startedAt_ >= config_.minWarmupMs && stableMask(now) == 0xff;
    }
    bool configValid() const { return configValid_; }

private:
    struct Channel {
        float samples[kMaxWindow]{};
        uint8_t next = 0;
        uint8_t count = 0;
        uint8_t stableWindows = 0;
    };
    Config config_;
    Channel channels_[kChannels]{};
    uint32_t startedAt_ = 0;
    uint32_t lastSampleAt_ = 0;
    bool configValid_ = false;
    bool started_ = false;
    bool haveSample_ = false;
};

}}  // namespace pgl::gld
