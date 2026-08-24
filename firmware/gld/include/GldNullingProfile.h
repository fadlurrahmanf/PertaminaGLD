#pragma once

#include <cstdint>

namespace pgl::gld {

constexpr uint8_t NULLING_PROFILE_VALID_MAGIC = 0xA5;
// Version 8 requires stable, non-saturated ADS samples while Nulling.  Earlier
// profiles may have been selected from an AGC transition and must be renewed.
constexpr uint8_t NULLING_PROFILE_ALGORITHM_VERSION = 8;
constexpr uint16_t NULLING_PROFILE_MAX_DAC_CODE = 4095;

struct GldNullingProfile {
    uint8_t  validMagic;    // NULLING_PROFILE_VALID_MAGIC when valid
    uint8_t  profileId;     // increments on each new save
    uint8_t  algorithmVersion; // baseline-rise algorithm version
    uint16_t dacCode[8];    // best DAC code per sensor channel
    float    baselineV[8];  // baseline voltage during nulling scan
    float    afterV[8];     // residual voltage after applying dacCode
    uint8_t  channelOk[8];  // 1 if channel succeeded, 0 if failed
};

inline bool isNullingProfileValid(const GldNullingProfile& p) {
    if (p.validMagic != NULLING_PROFILE_VALID_MAGIC || p.profileId == 0 ||
        p.algorithmVersion != NULLING_PROFILE_ALGORITHM_VERSION) {
        return false;
    }
    for (uint8_t channel = 0; channel < 8; ++channel) {
        if (p.channelOk[channel] != 1 ||
            p.dacCode[channel] > NULLING_PROFILE_MAX_DAC_CODE) {
            return false;
        }
    }
    return true;
}

constexpr uint8_t NULLING_CONFIG_VALID_MAGIC = 0x5A;

constexpr float NULLING_CONFIG_DEFAULT_THRESHOLD_V = 0.0001f;
constexpr float NULLING_CONFIG_DEFAULT_MIN_FINAL_V  = 0.0f;

// Full nulling requires both V >= -thresholdV (zero-margin) and a directional
// rise of thresholdV above the measured baseline. minFinalV remains the
// absolute final-voltage floor and may be negative when explicitly permitted.
struct GldNullingConfig {
    uint8_t validMagic = NULLING_CONFIG_VALID_MAGIC;
    float   thresholdV = NULLING_CONFIG_DEFAULT_THRESHOLD_V;
    float   minFinalV  = NULLING_CONFIG_DEFAULT_MIN_FINAL_V;
};

inline bool isNullingConfigValid(const GldNullingConfig& c) {
    return c.validMagic == NULLING_CONFIG_VALID_MAGIC;
}

}  // namespace pgl::gld
