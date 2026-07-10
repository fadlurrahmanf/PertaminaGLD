#pragma once

#include <cstdint>

#include "ProtocolConstants.h"

namespace pgl::gld {

constexpr float GLD_BATTERY_ADC_MAX_VOLTAGE = 3.3f;
constexpr float GLD_BATTERY_ADC_MAX_COUNT = 4095.0f;
constexpr float GLD_BATTERY_DIVIDER_RATIO = 3.0f;
constexpr uint8_t GLD_BATTERY_SAMPLE_COUNT = 16;
constexpr float GLD_BATTERY_MIN_VALID_VOLTAGE = 3.00f;
constexpr float GLD_BATTERY_LOW_VOLTAGE = 3.50f;
constexpr float GLD_BATTERY_CRITICAL_VOLTAGE = 3.30f;
constexpr float GLD_BATTERY_FILTER_ALPHA = 0.20f;

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
    bool batteryLow;
    bool batteryCritical;
    bool pg24PowerGood;
    bool externalPower;
    GldPowerMode mode;
};

void beginGldPowerPins();
uint16_t readGldBatteryMv();
bool readGldExternalPower();
GldPowerReading readGldPower();
const char* gldPowerModeName(GldPowerMode mode);

// WDT/TPL5010 wake/keepalive/sleep cycle on IO14:
// - pulseGldTpl5010Keepalive() emits the short DONE/keepalive pulse.
// - The runtime services IO14 frequently in every mode while the node is doing
//   work, or the external WDT can assert RSTn and force-reset the ESP32.
// - pulseGldPowerLatchClear() clears the SN74AUP1G74 power latch once all
//   work for the wake cycle is complete, cutting ESP32 power (real sleep).
constexpr uint32_t GLD_WDT_KEEPALIVE_INTERVAL_MS = 10000;
constexpr uint32_t GLD_TPL5010_KEEPALIVE_INTERVAL_MS = GLD_WDT_KEEPALIVE_INTERVAL_MS;
constexpr uint32_t GLD_TPL5010_KEEPALIVE_PULSE_MS = 5;
constexpr uint32_t GLD_POWER_LATCH_CLEAR_PULSE_MS = 5;
void pulseGldTpl5010Keepalive();
void pulseGldPowerLatchClear();

}  // namespace pgl::gld
