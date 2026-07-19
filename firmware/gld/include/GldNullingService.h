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
    SingleChannelFailed,  // runNullingServiceSingleChannel() only: that one channel did not confirm
};

struct GldNullingServiceResult {
    GldNullingProfile profile;
    GldNullingStatus  status;
    uint8_t           successCount;  // out of 8
};

struct GldNullingSingleResult {
    uint16_t          dacCode;
    float              baselineV;
    float              afterV;
    bool               success;
    GldNullingStatus   status;
};

struct GldFullScaleSweepResult {
    bool             success;
    GldNullingStatus status;
    uint16_t         restoredCode;
};

using GldNullingLogFn = void (*)(const char* line);
using GldNullingTickFn = void (*)();

// Run the nulling algorithm on all 8 sensor channels.
// ads and dac must be initialized (begin() called) before calling.
// The profile dacCodes are applied to the DAC hardware after each channel.
// config.thresholdV is the minimum floor for the dynamic baseline-relative
// threshold used by range search, binary search, confirm, and final check.
GldNullingServiceResult runNullingService(GldAds1256Reader& ads,
                                          GldDacMux& dac,
                                          GldNullingLogFn logFn = nullptr,
                                          GldNullingTickFn tickFn = nullptr,
                                          const GldNullingConfig& config = GldNullingConfig{});

// Runs the same nulling algorithm as runNullingService(), but for exactly one
// sensor channel (0..7) instead of all 8 - used by the QC tab to test a
// single MQ sensor without pausing telemetry/LoRa for the whole board. The
// caller is responsible for merging the result into the persisted profile
// (see GldUnifiedMain.cpp's onRunNullingSingleJson) since a single-channel
// run should not overwrite the other 7 channels' saved state.
GldNullingSingleResult runNullingServiceSingleChannel(GldAds1256Reader& ads,
                                                      GldDacMux& dac,
                                                      uint8_t channel,
                                                      GldNullingLogFn logFn = nullptr,
                                                      GldNullingTickFn tickFn = nullptr,
                                                      const GldNullingConfig& config = GldNullingConfig{});

// Steps the DAC across its full range (GLD_DAC_CODE_MIN..GLD_DAC_CODE_MAX) for
// one sensor channel, in increments of stepSize, logging a FULLSCALE_STEP
// line with the resulting voltage at each code so the operator UI can plot a
// live voltage-vs-DAC-code characterization curve. Purely diagnostic - does
// not touch the persisted nulling profile. The DAC is restored to
// restoreCode (normally the channel's currently-nulled code) once the sweep
// finishes, including on early failure.
GldFullScaleSweepResult runFullScaleSweep(GldAds1256Reader& ads,
                                          GldDacMux& dac,
                                          uint8_t channel,
                                          uint16_t restoreCode,
                                          uint16_t stepSize = 1,
                                          GldNullingLogFn logFn = nullptr,
                                          GldNullingTickFn tickFn = nullptr);

// NVS persistence via ESP32 Preferences.
bool saveNullingProfile(const GldNullingProfile& profile);
bool loadNullingProfile(GldNullingProfile& out);

// NVS persistence for tunable nulling thresholds (separate namespace from the profile).
bool saveNullingConfig(const GldNullingConfig& config);
bool loadNullingConfig(GldNullingConfig& out);

const char* gldNullingStatusName(GldNullingStatus s);

}  // namespace pgl::gld
