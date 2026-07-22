#pragma once

#include <cstdint>

#include "ProtocolConstants.h"

namespace pgl::gld {

constexpr float GLD_BATTERY_ADC_MAX_VOLTAGE = 3.3f;
constexpr float GLD_BATTERY_ADC_MAX_COUNT = 4095.0f;
constexpr float GLD_BATTERY_DIVIDER_RATIO = 3.0f;
constexpr uint8_t GLD_BATTERY_SAMPLE_COUNT = 16;
constexpr float GLD_BATTERY_DETECT_FLOOR_VOLTAGE = 0.05f;
constexpr float GLD_BATTERY_MIN_VALID_VOLTAGE = 3.00f;
constexpr float GLD_BATTERY_MAX_VALID_VOLTAGE = 20.0f;
constexpr float GLD_BATTERY_LOW_VOLTAGE = 3.50f;
constexpr float GLD_BATTERY_CRITICAL_VOLTAGE = 3.30f;
constexpr float GLD_BATTERY_FILTER_ALPHA = 0.20f;

enum class GldBatterySenseStatus : uint8_t {
    NotDetected = 0,
    DetectedBelowValidRange,
    Valid,
    Invalid,
};

enum class GldPowerMode : uint8_t {
    Battery = 0,
    External5V,
    External24V,
    Ambiguous,
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
    bool batteryDetected;
    bool powerSourceAmbiguous;
    GldBatterySenseStatus batterySenseStatus;
};

void beginGldPowerPins();
uint16_t readGldBatteryMv();
bool readGldExternalPower();
GldPowerReading readGldPower();
const char* gldPowerModeName(GldPowerMode mode);
const char* gldBatterySenseStatusName(GldBatterySenseStatus status);

// WDT/TPL5010 wake/keepalive/sleep cycle on IO14:
// - pulseGldTpl5010Keepalive() emits a periodic DONE pulse for external-power
//   runtime only.
// - Battery wake sessions must not pulse DONE periodically; they emit one final
//   DONE pulse, then CLR, after the scan/inference/TX/RX procedure finishes.
// - pulseGldPowerLatchClear() clears the SN74AUP1G74 power latch without a DONE
//   pulse, used by explicit service commands such as SLEEP_NOW.
constexpr uint32_t GLD_WDT_KEEPALIVE_INTERVAL_MS = 10000;
constexpr uint32_t GLD_TPL5010_KEEPALIVE_INTERVAL_MS = GLD_WDT_KEEPALIVE_INTERVAL_MS;
constexpr uint32_t GLD_TPL5010_KEEPALIVE_PULSE_MS = 5;
constexpr uint32_t GLD_POWER_LATCH_CLEAR_PULSE_MS = 5;
constexpr uint32_t GLD_TPL5010_DONE_PULSE_US = 1000;
constexpr uint32_t GLD_DONE_TO_CLR_DELAY_US = 500;
constexpr uint32_t GLD_POWER_LATCH_CLEAR_PULSE_US = GLD_TPL5010_DONE_PULSE_US;
void pulseGldTpl5010Keepalive();
void pulseGldPowerLatchClear();
void pulseGldTpl5010DoneThenPowerLatchClear();

}  // namespace pgl::gld
