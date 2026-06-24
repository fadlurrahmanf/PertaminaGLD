#pragma once

#include <cstdint>

#include "ProtocolConstants.h"

namespace pgl::gld {

constexpr float GLD_BATTERY_ADC_MAX_VOLTAGE = 3.3f;
constexpr float GLD_BATTERY_ADC_MAX_COUNT = 4095.0f;
constexpr float GLD_BATTERY_DIVIDER_RATIO = 3.0f;
constexpr uint8_t GLD_BATTERY_SAMPLE_COUNT = 16;

enum class GldPowerMode : uint8_t {
    Battery = 0,
    External5V,
    External24V,
};

struct GldPowerReading {
    uint16_t batteryMv;
    uint16_t batteryAdcMv;
    uint16_t batteryRawAdc;
    bool batteryValid;
    bool pg24PowerGood;
    bool externalPower;
    GldPowerMode mode;
};

void beginGldPowerPins();
uint16_t readGldBatteryMv();
bool readGldExternalPower();
GldPowerReading readGldPower();
const char* gldPowerModeName(GldPowerMode mode);

}  // namespace pgl::gld
