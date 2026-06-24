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

}  // namespace pgl::gld
