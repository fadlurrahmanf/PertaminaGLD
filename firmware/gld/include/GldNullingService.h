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
    PartialSuccess,  // some channels failed, profile still saved for good ones
};

struct GldNullingServiceResult {
    GldNullingProfile profile;
    GldNullingStatus  status;
    uint8_t           successCount;  // out of 8
};

// Run the nulling algorithm on all 8 sensor channels.
// ads and dac must be initialized (begin() called) before calling.
// The profile dacCodes are applied to the DAC hardware after each channel.
GldNullingServiceResult runNullingService(GldAds1256Reader& ads, GldDacMux& dac);

// NVS persistence via ESP32 Preferences.
bool saveNullingProfile(const GldNullingProfile& profile);
bool loadNullingProfile(GldNullingProfile& out);

const char* gldNullingStatusName(GldNullingStatus s);

}  // namespace pgl::gld
