#pragma once

#include <cstdint>

namespace pgl::gld {

constexpr uint8_t NULLING_PROFILE_VALID_MAGIC = 0xA5;

struct GldNullingProfile {
    uint8_t  validMagic;    // NULLING_PROFILE_VALID_MAGIC when valid
    uint8_t  profileId;     // increments on each new save
    uint16_t dacCode[8];    // best DAC code per sensor channel
    float    baselineV[8];  // baseline voltage during nulling scan
    float    afterV[8];     // residual voltage after applying dacCode
    uint8_t  channelOk[8];  // 1 if channel succeeded, 0 if failed
};

inline bool isNullingProfileValid(const GldNullingProfile& p) {
    return p.validMagic == NULLING_PROFILE_VALID_MAGIC;
}

constexpr uint8_t NULLING_CONFIG_VALID_MAGIC = 0x5A;

constexpr float NULLING_CONFIG_DEFAULT_THRESHOLD_V = 0.0001f;
constexpr float NULLING_CONFIG_DEFAULT_MIN_FINAL_V  = 0.0f;

// Tunable nulling thresholds. minFinalV is intentionally allowed to be
// negative: sensor channels whose ADC baseline sits below zero (a wiring/
// polarity property of that channel, not a fault) can never pass a
// non-negative confirm check, so the operator must be able to relax it
// per-deployment instead of the firmware hard-failing every nulling run.
struct GldNullingConfig {
    uint8_t validMagic = NULLING_CONFIG_VALID_MAGIC;
    float   thresholdV = NULLING_CONFIG_DEFAULT_THRESHOLD_V;
    float   minFinalV  = NULLING_CONFIG_DEFAULT_MIN_FINAL_V;
};

inline bool isNullingConfigValid(const GldNullingConfig& c) {
    return c.validMagic == NULLING_CONFIG_VALID_MAGIC;
}

}  // namespace pgl::gld
