#pragma once

#include <cstdint>

#include "BoardPins.h"
#include "GldAds1256Reader.h"

namespace pgl::gld {

struct GldSensorSample {
    int32_t raw;
    float voltage;
    float movingAverageVoltage;
    uint8_t gain;
    GldAds1256Status status;
    bool valid;
    bool saturated;
};

struct GldSensorScan {
    GldSensorSample channels[pgl::gld::board::SENSOR_COUNT];
    uint32_t timestampMs;
    bool allValid;
};

}  // namespace pgl::gld
