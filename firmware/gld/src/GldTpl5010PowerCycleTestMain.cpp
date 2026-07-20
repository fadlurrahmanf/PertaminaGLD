#include <Arduino.h>

#include "BoardPins.h"
#include "GldPower.h"

namespace {

constexpr uint32_t AWAKE_DELAY_MS = 60000;
constexpr uint32_t HEARTBEAT_INTERVAL_MS = 5000;

static_assert(pgl::gld::board::PIN_TPL5110_DONE == 14, "Unexpected GLD TPL5010 DONE pin");
static_assert(pgl::gld::board::PIN_POWER_LATCH_CLR == 38, "Unexpected GLD power-latch CLR pin");

void printBoth(const char* text) {
    Serial.println(text);
    Serial0.println(text);
}

void printHeartbeat(uint32_t elapsedMs) {
    const uint32_t remainingSeconds = (AWAKE_DELAY_MS - elapsedMs + 999U) / 1000U;
    Serial.printf("TPL5010_SMOKE_AWAKE elapsed_ms=%lu remaining_s=%lu\n",
                  static_cast<unsigned long>(elapsedMs),
                  static_cast<unsigned long>(remainingSeconds));
    Serial0.printf("TPL5010_SMOKE_AWAKE elapsed_ms=%lu remaining_s=%lu\n",
                   static_cast<unsigned long>(elapsedMs),
                   static_cast<unsigned long>(remainingSeconds));
}

}  // namespace

void setup() {
    // Establish safe idle levels before starting either serial interface:
    // DONE LOW and active-low CLR HIGH.
    pgl::gld::beginGldPowerPins();

    Serial.begin(115200);
    Serial0.begin(115200);
    delay(250);

    printBoth("TPL5010_SMOKE_BOOT version=1 awake_delay_ms=60000 done_pin=14 clr_pin=38");
    printBoth("TPL5010_SMOKE_EXPECT power_off_after_60s then_automatic_wake_without_host_action");

    const uint32_t startedAtMs = millis();
    uint32_t nextHeartbeatMs = 0;
    while (true) {
        const uint32_t elapsedMs = millis() - startedAtMs;
        if (elapsedMs >= AWAKE_DELAY_MS) {
            break;
        }
        if (elapsedMs >= nextHeartbeatMs) {
            printHeartbeat(elapsedMs);
            nextHeartbeatMs += HEARTBEAT_INTERVAL_MS;
        }
        delay(10);
    }

    printBoth("TPL5010_SMOKE_POWER_OFF_BEGIN done=LOW_HIGH_LOW:1000us gap=500us clr=HIGH_LOW_HIGH:1000us");
    Serial.flush();
    Serial0.flush();

    noInterrupts();
    pgl::gld::pulseGldTpl5010DoneThenPowerLatchClear();
    interrupts();

    // Reaching this line means the main rail did not turn off as intended.
    printBoth("TPL5010_SMOKE_POWER_OFF_FAILED main_cpu_still_running");
}

void loop() {
    delay(1000);
    printBoth("TPL5010_SMOKE_POWER_OFF_FAILED main_cpu_still_running");
}
