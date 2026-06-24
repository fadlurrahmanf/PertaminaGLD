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

BatteryAdcReading readBatteryAdc() {
    uint32_t total = 0;
    for (uint8_t i = 0; i < GLD_BATTERY_SAMPLE_COUNT; ++i) {
        total += static_cast<uint32_t>(analogRead(pgl::gld::board::PIN_BATTERY_VOLTAGE));
        delay(2);
    }

    const float avg = static_cast<float>(total) / static_cast<float>(GLD_BATTERY_SAMPLE_COUNT);
    const float adcVoltage = (avg / GLD_BATTERY_ADC_MAX_COUNT) * GLD_BATTERY_ADC_MAX_VOLTAGE;
    const float batteryVoltage = adcVoltage * GLD_BATTERY_DIVIDER_RATIO;
    const uint16_t rawAdc = static_cast<uint16_t>(avg + 0.5f);
    const uint16_t adcMv = static_cast<uint16_t>((adcVoltage * 1000.0f) + 0.5f);

    if (batteryVoltage <= 0.05f || batteryVoltage > 20.0f) {
        return {rawAdc, adcMv, pgl::protocol::GLD_BATTERY_MV_INVALID, false};
    }
    return {
        rawAdc,
        adcMv,
        static_cast<uint16_t>((batteryVoltage * 1000.0f) + 0.5f),
        true,
    };
}

}  // namespace

void beginGldPowerPins() {
    pinMode(pgl::gld::board::PIN_BATTERY_VOLTAGE, INPUT);
    pinMode(pgl::gld::board::PIN_24V_POWER_GOOD, INPUT);
    pinMode(pgl::gld::board::PIN_TPL5110_DONE, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_TPL5110_DONE, LOW);
#if defined(ARDUINO_ARCH_ESP32)
    analogReadResolution(12);
    analogSetPinAttenuation(pgl::gld::board::PIN_BATTERY_VOLTAGE, ADC_11db);
#endif
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
    return {
        battery.batteryMv,
        battery.adcMv,
        battery.rawAdc,
        battery.valid,
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
