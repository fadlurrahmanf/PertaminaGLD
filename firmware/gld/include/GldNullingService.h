#pragma once

#include <cstdint>

#include "GldAds1256Reader.h"
#include "GldDacMux.h"
#include "GldNullingProfile.h"

namespace pgl::gld {

enum class GldNullingStatus : uint8_t {
    Ok = 0,
    AdsNotReady,
    DacNotReady,
    AllChannelsFailed,
    PartialSuccess,  // some channels failed; unified runtime must retry, not save as complete profile
};

struct GldNullingServiceResult {
    GldNullingProfile profile;
    GldNullingStatus  status;
    uint8_t           successCount;  // out of 8
};

using GldNullingLogFn = void (*)(const char* line);

// Run the nulling algorithm on all 8 sensor channels.
// ads and dac must be initialized (begin() called) before calling.
// The profile dacCodes are applied to the DAC hardware after each channel.
GldNullingServiceResult runNullingService(GldAds1256Reader& ads,
                                          GldDacMux& dac,
                                          GldNullingLogFn logFn = nullptr);

// NVS persistence via ESP32 Preferences.
bool saveNullingProfile(const GldNullingProfile& profile);
bool loadNullingProfile(GldNullingProfile& out);

const char* gldNullingStatusName(GldNullingStatus s);

}  // namespace pgl::gld
