#include "GldPower.h"

#include <Arduino.h>

#include "BoardPins.h"

namespace pgl::gld {

namespace {

struct BatteryAdcReading {
    uint16_t rawAdc;
    uint16_t adcMv;
    uint16_t batteryMv;
    bool valid;
};

// EMA-filtered battery voltage, persisted across calls (alpha = GLD_BATTERY_FILTER_ALPHA).
float g_filteredBatteryVoltage = 0.0f;
bool g_filterPrimed = false;

BatteryAdcReading readBatteryAdc() {
    uint32_t total = 0;
    for (uint8_t i = 0; i < GLD_BATTERY_SAMPLE_COUNT; ++i) {
        total += static_cast<uint32_t>(analogRead(pgl::gld::board::PIN_BATTERY_VOLTAGE));
        delay(2);
    }

    const float avg = static_cast<float>(total) / static_cast<float>(GLD_BATTERY_SAMPLE_COUNT);
    const float adcVoltage = (avg / GLD_BATTERY_ADC_MAX_COUNT) * GLD_BATTERY_ADC_MAX_VOLTAGE;
    const float rawBatteryVoltage = adcVoltage * GLD_BATTERY_DIVIDER_RATIO;
    const uint16_t rawAdc = static_cast<uint16_t>(avg + 0.5f);
    const uint16_t adcMv = static_cast<uint16_t>((adcVoltage * 1000.0f) + 0.5f);

    if (rawBatteryVoltage <= 0.05f || rawBatteryVoltage > 20.0f) {
        return {rawAdc, adcMv, pgl::protocol::GLD_BATTERY_MV_INVALID, false};
    }

    // Smooth the reading with an EMA filter before applying the validity threshold,
    // so a single noisy sample can't flip battery-low/critical state.
    if (!g_filterPrimed) {
        g_filteredBatteryVoltage = rawBatteryVoltage;
        g_filterPrimed = true;
    } else {
        g_filteredBatteryVoltage = (GLD_BATTERY_FILTER_ALPHA * rawBatteryVoltage) +
                                   ((1.0f - GLD_BATTERY_FILTER_ALPHA) * g_filteredBatteryVoltage);
    }

    if (g_filteredBatteryVoltage < GLD_BATTERY_MIN_VALID_VOLTAGE) {
        return {rawAdc, adcMv, pgl::protocol::GLD_BATTERY_MV_INVALID, false};
    }
    return {
        rawAdc,
        adcMv,
        static_cast<uint16_t>((g_filteredBatteryVoltage * 1000.0f) + 0.5f),
        true,
    };
}

}  // namespace

void beginGldPowerPins() {
    pinMode(pgl::gld::board::PIN_BATTERY_VOLTAGE, INPUT);
    pinMode(pgl::gld::board::PIN_24V_POWER_GOOD, INPUT);
    digitalWrite(pgl::gld::board::PIN_TPL5110_DONE, LOW);
    pinMode(pgl::gld::board::PIN_TPL5110_DONE, OUTPUT);
    // CLR is active-low; idle HIGH means "not clearing" (latch stays set / power stays on).
    digitalWrite(pgl::gld::board::PIN_POWER_LATCH_CLR, HIGH);
    pinMode(pgl::gld::board::PIN_POWER_LATCH_CLR, OUTPUT);
#if defined(ARDUINO_ARCH_ESP32)
    analogReadResolution(12);
    analogSetPinAttenuation(pgl::gld::board::PIN_BATTERY_VOLTAGE, ADC_11db);
#endif
}

void pulseGldTpl5010Keepalive() {
    digitalWrite(pgl::gld::board::PIN_TPL5110_DONE, HIGH);
    delay(GLD_TPL5010_KEEPALIVE_PULSE_MS);
    digitalWrite(pgl::gld::board::PIN_TPL5110_DONE, LOW);
}

void pulseGldPowerLatchClear() {
    digitalWrite(pgl::gld::board::PIN_POWER_LATCH_CLR, HIGH);
    delay(GLD_POWER_LATCH_CLEAR_PULSE_MS);
    digitalWrite(pgl::gld::board::PIN_POWER_LATCH_CLR, LOW);
    delay(GLD_POWER_LATCH_CLEAR_PULSE_MS);
    digitalWrite(pgl::gld::board::PIN_POWER_LATCH_CLR, HIGH);
}

uint16_t readGldBatteryMv() {
    return readBatteryAdc().batteryMv;
}

bool readGldExternalPower() {
    return digitalRead(pgl::gld::board::PIN_24V_POWER_GOOD) == HIGH;
}

GldPowerReading readGldPower() {
    const BatteryAdcReading battery = readBatteryAdc();
    const bool external24V = readGldExternalPower();
    const GldPowerMode mode = external24V ? GldPowerMode::External24V
                              : battery.valid ? GldPowerMode::Battery
                                              : GldPowerMode::External5V;
    const float batteryVolts = static_cast<float>(battery.batteryMv) / 1000.0f;
    const bool low = battery.valid && batteryVolts <= GLD_BATTERY_LOW_VOLTAGE;
    const bool critical = battery.valid && batteryVolts <= GLD_BATTERY_CRITICAL_VOLTAGE;
    return {
        battery.batteryMv,
        battery.adcMv,
        battery.rawAdc,
        battery.valid,
        low,
        critical,
        external24V,
        mode != GldPowerMode::Battery,
        mode,
    };
}

const char* gldPowerModeName(GldPowerMode mode) {
    switch (mode) {
        case GldPowerMode::Battery:
            return "battery";
        case GldPowerMode::External5V:
            return "5v";
        case GldPowerMode::External24V:
            return "24v";
    }
    return "unknown";
}

}  // namespace pgl::gld
