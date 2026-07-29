#include <Arduino.h>

namespace {

constexpr uint8_t OUTPUT_PIN = 8;
constexpr uint16_t HIGH_DURATION_MS = 125;
constexpr uint16_t LOW_DURATION_MS = 875;

}  // namespace

void setup() {
    pinMode(OUTPUT_PIN, OUTPUT);
    digitalWrite(OUTPUT_PIN, LOW);
}

void loop() {
    digitalWrite(OUTPUT_PIN, HIGH);
    delay(HIGH_DURATION_MS);

    digitalWrite(OUTPUT_PIN, LOW);
    delay(LOW_DURATION_MS);
}
