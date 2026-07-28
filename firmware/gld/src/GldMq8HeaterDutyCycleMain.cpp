#include <Arduino.h>
#include <SPI.h>

#include <cstdarg>
#include <cstdio>

#include "BoardPins.h"
#include "GldAds1256Reader.h"

namespace {

// Bench experiment only. GPIO42 is controlled directly by this isolated env.
constexpr uint8_t MQ8_CHANNEL = 0;
constexpr uint32_t IO42_HIGH_US = 125000;
constexpr uint32_t IO42_LOW_US = 875000;
constexpr uint32_t IO42_PERIOD_US = IO42_HIGH_US + IO42_LOW_US;
constexpr uint32_t SAMPLE_INTERVAL_US = 25000;
constexpr uint32_t CFG_DEBOUNCE_MS = 40;
constexpr uint32_t CFG_LONG_PRESS_MS = 5000;
constexpr uint32_t LED_BLINK_MS = 250;
constexpr uint8_t LED_ON = LOW;
constexpr uint8_t LED_OFF = HIGH;

pgl::gld::GldAds1256Reader ads;
SPIClass sensorSpi;
bool adsReady = false;
bool io42High = false;
uint32_t cycleStartUs = 0;
uint32_t lastSampleUs = 0;
uint32_t sampleSequence = 0;
bool manualMode = false;
bool cfgRawHigh = true;
bool cfgStableHigh = true;
bool cfgLongPressHandled = false;
uint32_t cfgRawChangedMs = 0;
uint32_t cfgPressStartedMs = 0;
bool ledBlinkActive = false;
bool ledBlinkOn = false;
uint8_t ledBlinkPairsRemaining = 0;
uint32_t ledBlinkNextMs = 0;

void logPrint(const char* text) {
    Serial.print(text);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.print(text);
#endif
}

void logPrintf(const char* fmt, ...) {
    char buffer[224];
    va_list args;
    va_start(args, fmt);
    vsnprintf(buffer, sizeof(buffer), fmt, args);
    va_end(args);
    logPrint(buffer);
}

void setIo42(bool high, uint32_t nowUs) {
    if (io42High == high) {
        return;
    }

    io42High = high;
    digitalWrite(pgl::gld::board::PIN_DC_FAN, high ? HIGH : LOW);
    logPrintf("MQ8_IO42_EDGE tsUs=%lu io42=%s\n",
              static_cast<unsigned long>(nowUs),
              high ? "HIGH" : "LOW");
}

void startLedBlinks(uint8_t count, uint32_t nowMs) {
    ledBlinkPairsRemaining = count;
    ledBlinkActive = count > 0;
    ledBlinkOn = ledBlinkActive;
    digitalWrite(pgl::gld::board::PIN_STATUS_LED, ledBlinkOn ? LED_ON : LED_OFF);
    ledBlinkNextMs = nowMs + LED_BLINK_MS;
}

void maintainLedBlinks(uint32_t nowMs) {
    if (!ledBlinkActive || static_cast<int32_t>(nowMs - ledBlinkNextMs) < 0) {
        return;
    }

    if (ledBlinkOn) {
        ledBlinkOn = false;
        digitalWrite(pgl::gld::board::PIN_STATUS_LED, LED_OFF);
        ledBlinkNextMs = nowMs + LED_BLINK_MS;
        return;
    }

    if (--ledBlinkPairsRemaining == 0) {
        ledBlinkActive = false;
        return;
    }

    ledBlinkOn = true;
    digitalWrite(pgl::gld::board::PIN_STATUS_LED, LED_ON);
    ledBlinkNextMs = nowMs + LED_BLINK_MS;
}

void updateIo42Duty(uint32_t nowUs) {
    if (manualMode) {
        return;
    }

    const uint32_t phaseUs = (nowUs - cycleStartUs) % IO42_PERIOD_US;
    setIo42(phaseUs < IO42_HIGH_US, nowUs);
}

void setManualMode(bool enabled, uint32_t nowUs, uint32_t nowMs) {
    manualMode = enabled;
    if (manualMode) {
        setIo42(false, nowUs);
        startLedBlinks(5, nowMs);
        logPrintf("MQ8_MANUAL_MODE=ENTER io42=LOW\n");
        return;
    }

    cycleStartUs = nowUs;
    setIo42(true, nowUs);
    startLedBlinks(10, nowMs);
    logPrintf("MQ8_MANUAL_MODE=EXIT io42Auto=HIGH125ms/LOW875ms\n");
}

void maintainCfgButton(uint32_t nowUs, uint32_t nowMs) {
    const bool rawHigh = digitalRead(pgl::gld::board::PIN_USER_BUTTON) == HIGH;
    if (rawHigh != cfgRawHigh) {
        cfgRawHigh = rawHigh;
        cfgRawChangedMs = nowMs;
    }

    if (cfgRawHigh != cfgStableHigh && nowMs - cfgRawChangedMs >= CFG_DEBOUNCE_MS) {
        cfgStableHigh = cfgRawHigh;
        if (!cfgStableHigh) {
            cfgPressStartedMs = nowMs;
            cfgLongPressHandled = false;
            logPrintf("MQ8_CFG event=PRESS level=LOW\n");
        } else {
            const uint32_t heldMs = nowMs - cfgPressStartedMs;
            logPrintf("MQ8_CFG event=RISING level=HIGH heldMs=%lu\n",
                      static_cast<unsigned long>(heldMs));
            if (manualMode && !cfgLongPressHandled) {
                setIo42(!io42High, nowUs);
                startLedBlinks(io42High ? 1 : 2, nowMs);
                logPrintf("MQ8_MANUAL_TOGGLE io42=%s\n", io42High ? "HIGH" : "LOW");
            }
        }
    }

    if (!cfgStableHigh && !cfgLongPressHandled &&
        nowMs - cfgPressStartedMs >= CFG_LONG_PRESS_MS) {
        cfgLongPressHandled = true;
        setManualMode(!manualMode, nowUs, nowMs);
    }
}

void readMq8(uint32_t nowUs) {
    if (!adsReady) {
        logPrintf("MQ8_SAMPLE seq=%lu tsUs=%lu mode=%s io42=%s status=ADS_NOT_READY\n",
                  static_cast<unsigned long>(sampleSequence++),
                  static_cast<unsigned long>(nowUs),
                  manualMode ? "MANUAL" : "AUTO",
                  io42High ? "HIGH" : "LOW");
        return;
    }

    const pgl::gld::GldAds1256Reading reading = ads.readChannel(MQ8_CHANNEL);
    logPrintf("MQ8_SAMPLE seq=%lu tsUs=%lu mode=%s io42=%s phaseUs=%lu status=%s raw=%ld voltage=%.6f gain=%u saturated=%u\n",
              static_cast<unsigned long>(sampleSequence++),
              static_cast<unsigned long>(nowUs),
              manualMode ? "MANUAL" : "AUTO",
              io42High ? "HIGH" : "LOW",
              static_cast<unsigned long>((nowUs - cycleStartUs) % IO42_PERIOD_US),
              pgl::gld::gldAds1256StatusName(reading.status),
              static_cast<long>(reading.raw),
              reading.voltage,
              reading.gain,
              reading.saturated ? 1 : 0);
}

}  // namespace

void setup() {
    Serial.begin(115200);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.begin(115200);
#endif
    delay(500);

    pinMode(pgl::gld::board::PIN_DC_FAN, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_DC_FAN, LOW);
    io42High = false;
    pinMode(pgl::gld::board::PIN_STATUS_LED, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_STATUS_LED, LED_OFF);
    pinMode(pgl::gld::board::PIN_USER_BUTTON, INPUT_PULLUP);
    cfgRawHigh = digitalRead(pgl::gld::board::PIN_USER_BUTTON) == HIGH;
    cfgStableHigh = cfgRawHigh;
    cfgRawChangedMs = millis();

    logPrintf("MQ8_IO42_DUTY_TEST start io42=%u channel=%u highUs=%lu lowUs=%lu sampleIntervalUs=%lu cfgPin=%u ledPin=%u\n",
              pgl::gld::board::PIN_DC_FAN,
              MQ8_CHANNEL,
              static_cast<unsigned long>(IO42_HIGH_US),
              static_cast<unsigned long>(IO42_LOW_US),
              static_cast<unsigned long>(SAMPLE_INTERVAL_US),
              pgl::gld::board::PIN_USER_BUTTON,
              pgl::gld::board::PIN_STATUS_LED);

    adsReady = ads.begin(sensorSpi);
    logPrintf("MQ8_ADS_BEGIN=%s\n", adsReady ? "PASS" : "FAIL");

    cycleStartUs = micros();
    lastSampleUs = cycleStartUs - SAMPLE_INTERVAL_US;
    updateIo42Duty(cycleStartUs);
}

void loop() {
    const uint32_t nowUs = micros();
    const uint32_t nowMs = millis();
    maintainCfgButton(nowUs, nowMs);
    maintainLedBlinks(nowMs);
    updateIo42Duty(nowUs);

    if (static_cast<uint32_t>(nowUs - lastSampleUs) >= SAMPLE_INTERVAL_US) {
        lastSampleUs = nowUs;
        readMq8(nowUs);
    }
}
