#pragma once

#include <cstdint>

namespace pgl::gld {

// Delta above clean-air baseline that triggers gas detection.
constexpr float GLD_DETECT_DELTA_V    = 0.05f;  // 50 mV rise → gas suspected
constexpr float GLD_FULLSCALE_DELTA_V = 0.25f;  // 250 mV rise → 100% confidence

// Per-channel voltage thresholds for threshold-based gas classification.
// All voltages are gain-compensated absolute values in Volts.
// Populated by calibrateThreshold() after baseline measurement at boot.
struct GldThresholdConfig {
    float gasDetectV[8];  // baseline + GLD_DETECT_DELTA_V per channel
    float fullScaleV[8];  // baseline + GLD_DETECT_DELTA_V + GLD_FULLSCALE_DELTA_V per channel
    bool  calibrated;     // true after calibrateThreshold() has been called
};

struct GldClassifyResult {
    uint8_t gasClass;    // GLD_GAS_CLEAR=0, GLD_GAS_LPG=1, GLD_GAS_METHANE=4
    uint8_t confidence;  // 0-100
};

// Returns an uncalibrated config (calibrated=false).
GldThresholdConfig defaultThresholdConfig();

// Set gasDetectV = baselineV + GLD_DETECT_DELTA_V for each channel.
// Call once after moving average has fully primed.
void calibrateThreshold(GldThresholdConfig& cfg, const float baselineV[8]);

// Classify gas type from 8-channel moving-average voltages.
// cfg must be calibrated; returns GLD_GAS_CLEAR if cfg.calibrated is false.
GldClassifyResult classifyByThreshold(const float mavVoltage[8], const GldThresholdConfig& cfg);

const char* gldGasClassName(uint8_t gasClass);

}  // namespace pgl::gld
