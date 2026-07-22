#pragma once

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace pgl::gld {

constexpr size_t GLD_DATASET_FEATURE_COUNT = 8;
constexpr uint8_t GLD_DATASET_STATUS_OK = 0;

// This order is the persisted dataset/model contract. Keep it independent of
// the board label table so an accidental board-map reorder fails closed.
constexpr const char* GLD_DATASET_CANONICAL_FEATURE_ORDER[GLD_DATASET_FEATURE_COUNT] = {
    "MQ8", "MQ135", "MQ3", "MQ5", "MQ4", "MQ7", "MQ6", "MQ2",
};

enum class GldDatasetRejectReason : uint8_t {
    None = 0,
    NullingProfileNotReady,
    ChannelCount,
    FeatureOrder,
    StatusNotOk,
    NonFiniteVoltage,
    Saturated,
    InvalidGain,
    PayloadEncoding,
};

struct GldDatasetChannelSample {
    const char* feature = nullptr;
    uint8_t status = 0xFF;
    float voltage = 0.0f;
    uint8_t gain = 0;
    bool saturated = false;

    GldDatasetChannelSample() = default;
    GldDatasetChannelSample(const char* featureValue,
                            uint8_t statusValue,
                            float voltageValue,
                            uint8_t gainValue,
                            bool saturatedValue)
        : feature(featureValue),
          status(statusValue),
          voltage(voltageValue),
          gain(gainValue),
          saturated(saturatedValue) {}
};

struct GldDatasetValidationResult {
    bool accepted = false;
    GldDatasetRejectReason reason = GldDatasetRejectReason::ChannelCount;
    int8_t channel = -1;
    uint8_t okFiniteCount = 0;
};

inline bool isGldDatasetGainValid(uint8_t gain) {
    return gain == 1 || gain == 2 || gain == 4 || gain == 8 ||
           gain == 16 || gain == 32 || gain == 64;
}

inline const char* gldDatasetRejectReasonName(GldDatasetRejectReason reason) {
    switch (reason) {
        case GldDatasetRejectReason::None: return "none";
        case GldDatasetRejectReason::NullingProfileNotReady: return "nulling_profile_not_ready";
        case GldDatasetRejectReason::ChannelCount: return "channel_count";
        case GldDatasetRejectReason::FeatureOrder: return "feature_order";
        case GldDatasetRejectReason::StatusNotOk: return "status_not_ok";
        case GldDatasetRejectReason::NonFiniteVoltage: return "non_finite_voltage";
        case GldDatasetRejectReason::Saturated: return "saturated";
        case GldDatasetRejectReason::InvalidGain: return "invalid_gain";
        case GldDatasetRejectReason::PayloadEncoding: return "payload_encoding";
    }
    return "unknown";
}

inline GldDatasetValidationResult validateGldDatasetSample(
    const GldDatasetChannelSample* samples,
    size_t count,
    bool nullingProfileApplied,
    uint8_t nullingProfileId) {
    GldDatasetValidationResult result{};

    if (!nullingProfileApplied || nullingProfileId == 0) {
        result.reason = GldDatasetRejectReason::NullingProfileNotReady;
        return result;
    }
    if (samples == nullptr || count != GLD_DATASET_FEATURE_COUNT) {
        result.reason = GldDatasetRejectReason::ChannelCount;
        return result;
    }

    for (size_t i = 0; i < GLD_DATASET_FEATURE_COUNT; ++i) {
        result.channel = static_cast<int8_t>(i);
        const GldDatasetChannelSample& sample = samples[i];
        if (sample.feature == nullptr ||
            strcmp(sample.feature, GLD_DATASET_CANONICAL_FEATURE_ORDER[i]) != 0) {
            result.reason = GldDatasetRejectReason::FeatureOrder;
            return result;
        }
        if (sample.status != GLD_DATASET_STATUS_OK) {
            result.reason = GldDatasetRejectReason::StatusNotOk;
            return result;
        }
        if (!std::isfinite(sample.voltage)) {
            result.reason = GldDatasetRejectReason::NonFiniteVoltage;
            return result;
        }
        ++result.okFiniteCount;
        if (sample.saturated) {
            result.reason = GldDatasetRejectReason::Saturated;
            return result;
        }
        if (!isGldDatasetGainValid(sample.gain)) {
            result.reason = GldDatasetRejectReason::InvalidGain;
            return result;
        }
    }

    result.accepted = true;
    result.reason = GldDatasetRejectReason::None;
    result.channel = -1;
    return result;
}

}  // namespace pgl::gld
