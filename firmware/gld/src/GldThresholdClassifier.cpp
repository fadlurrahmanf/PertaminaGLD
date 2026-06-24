#include "GldThresholdClassifier.h"

#include "ProtocolConstants.h"

namespace pgl::gld {

namespace {

// LPG-sensitive channels: MQ5(3), MQ6(6), MQ2(7)
constexpr uint8_t LPG_CHANNELS[] = {3, 6, 7};
constexpr uint8_t LPG_CHANNEL_COUNT = 3;

// Methane-sensitive channel: MQ4(4)
constexpr uint8_t METHANE_CHANNELS[] = {4};
constexpr uint8_t METHANE_CHANNEL_COUNT = 1;

float clamp01(float v) {
    if (v < 0.0f) return 0.0f;
    if (v > 1.0f) return 1.0f;
    return v;
}

}  // namespace

GldThresholdConfig defaultThresholdConfig() {
    GldThresholdConfig cfg{};
    cfg.calibrated = false;
    return cfg;
}

void calibrateThreshold(GldThresholdConfig& cfg, const float baselineV[8]) {
    for (uint8_t i = 0; i < 8; ++i) {
        cfg.gasDetectV[i] = baselineV[i] + GLD_DETECT_DELTA_V;
        cfg.fullScaleV[i] = baselineV[i] + GLD_DETECT_DELTA_V + GLD_FULLSCALE_DELTA_V;
    }
    cfg.calibrated = true;
}

GldClassifyResult classifyByThreshold(const float mavVoltage[8], const GldThresholdConfig& cfg) {
    if (!cfg.calibrated) {
        return {pgl::protocol::GLD_GAS_CLEAR, 100};
    }
    float bestLpgExcess = 0.0f;
    uint8_t bestLpgCh = LPG_CHANNELS[0];
    float bestMethaneExcess = 0.0f;
    uint8_t bestMethaneCh = METHANE_CHANNELS[0];

    for (uint8_t i = 0; i < LPG_CHANNEL_COUNT; ++i) {
        const uint8_t ch = LPG_CHANNELS[i];
        const float excess = mavVoltage[ch] - cfg.gasDetectV[ch];
        if (excess > bestLpgExcess) {
            bestLpgExcess = excess;
            bestLpgCh = ch;
        }
    }
    for (uint8_t i = 0; i < METHANE_CHANNEL_COUNT; ++i) {
        const uint8_t ch = METHANE_CHANNELS[i];
        const float excess = mavVoltage[ch] - cfg.gasDetectV[ch];
        if (excess > bestMethaneExcess) {
            bestMethaneExcess = excess;
            bestMethaneCh = ch;
        }
    }

    if (bestLpgExcess <= 0.0f && bestMethaneExcess <= 0.0f) {
        return {pgl::protocol::GLD_GAS_CLEAR, 100};
    }

    uint8_t gasClass;
    float excess;
    uint8_t bestCh;

    if (bestLpgExcess >= bestMethaneExcess) {
        gasClass = pgl::protocol::GLD_GAS_LPG;
        excess = bestLpgExcess;
        bestCh = bestLpgCh;
    } else {
        gasClass = pgl::protocol::GLD_GAS_METHANE;
        excess = bestMethaneExcess;
        bestCh = bestMethaneCh;
    }

    const float span = cfg.fullScaleV[bestCh] - cfg.gasDetectV[bestCh];
    const float ratio = span > 0.0f ? excess / span : 1.0f;
    const uint8_t confidence = static_cast<uint8_t>(clamp01(ratio) * 100.0f);

    return {gasClass, static_cast<uint8_t>(confidence < 1u ? 1u : confidence)};
}

const char* gldGasClassName(uint8_t gasClass) {
    switch (gasClass) {
        case pgl::protocol::GLD_GAS_CLEAR:   return "clearGas";
        case pgl::protocol::GLD_GAS_LPG:     return "LPG";
        case pgl::protocol::GLD_GAS_PROPANE: return "propane";
        case pgl::protocol::GLD_GAS_BUTANE:  return "butane";
        case pgl::protocol::GLD_GAS_METHANE: return "methane";
        case pgl::protocol::GLD_GAS_ANOMALY: return "anomaly";
        default:                              return "unknown";
    }
}

}  // namespace pgl::gld
