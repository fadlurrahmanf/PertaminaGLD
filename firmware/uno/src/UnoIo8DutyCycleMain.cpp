#include <Arduino.h>
#include <ctype.h>
#include <stdlib.h>

namespace {

// Bench-only control for the MQ8 heater MOSFET. The verified wiring is
// D8 HIGH = heater ON and D8 LOW = heater OFF.
constexpr uint8_t OUTPUT_PIN = 8;
constexpr uint32_t SERIAL_BAUD = 115200;
constexpr uint32_t MAX_DURATION_MS = 60000;
constexpr size_t COMMAND_BUFFER_SIZE = 24;

uint32_t onDurationMs = 0;
uint32_t offDurationMs = 1000;
uint32_t phaseStartedMs = 0;
bool outputHigh = false;
char commandBuffer[COMMAND_BUFFER_SIZE] = {};
size_t commandLength = 0;

void setOutput(bool high) {
    outputHigh = high;
    digitalWrite(OUTPUT_PIN, high ? HIGH : LOW);
}

void printCurrentSetting() {
    Serial.print(F("DUTY onMs="));
    Serial.print(onDurationMs);
    Serial.print(F(" offMs="));
    Serial.print(offDurationMs);
    Serial.print(F(" dutyPct="));

    const uint32_t periodMs = onDurationMs + offDurationMs;
    if (periodMs == 0) {
        Serial.print(F("INVALID"));
    } else {
        Serial.print((100.0f * static_cast<float>(onDurationMs)) /
                     static_cast<float>(periodMs), 2);
    }

    Serial.print(F(" output="));
    Serial.println(outputHigh ? F("HIGH_ON") : F("LOW_OFF"));
}

bool parseDuration(const char* text, uint32_t& value) {
    if (*text == '\0') {
        return false;
    }

    char* end = nullptr;
    const unsigned long parsed = strtoul(text, &end, 10);
    if (end == text || *end != '\0' || parsed > MAX_DURATION_MS) {
        return false;
    }

    value = static_cast<uint32_t>(parsed);
    return true;
}

void applyCommand(char* command) {
    while (isspace(static_cast<unsigned char>(*command))) {
        ++command;
    }

    char* separator = strchr(command, ',');
    if (separator == nullptr || strchr(separator + 1, ',') != nullptr) {
        Serial.println(F("ERR expected ONms,OFFms (example: 125,875)"));
        return;
    }

    *separator = '\0';
    char* offText = separator + 1;
    while (isspace(static_cast<unsigned char>(*offText))) {
        ++offText;
    }

    char* onEnd = command + strlen(command);
    while (onEnd > command && isspace(static_cast<unsigned char>(onEnd[-1]))) {
        *--onEnd = '\0';
    }
    char* offEnd = offText + strlen(offText);
    while (offEnd > offText && isspace(static_cast<unsigned char>(offEnd[-1]))) {
        *--offEnd = '\0';
    }

    uint32_t newOnMs = 0;
    uint32_t newOffMs = 0;
    if (!parseDuration(command, newOnMs) || !parseDuration(offText, newOffMs) ||
        (newOnMs == 0 && newOffMs == 0)) {
        Serial.println(F("ERR use 0..60000 ms; ON and OFF cannot both be 0"));
        return;
    }

    onDurationMs = newOnMs;
    offDurationMs = newOffMs;
    phaseStartedMs = millis();

    // Apply the new setting immediately. `0,N` is a continuous heater OFF
    // baseline; `N,0` is continuous heater ON.
    setOutput(onDurationMs > 0);
    printCurrentSetting();
}

void serviceSerial() {
    while (Serial.available() > 0) {
        const char received = static_cast<char>(Serial.read());
        if (received == '\r' || received == '\n') {
            if (commandLength > 0) {
                commandBuffer[commandLength] = '\0';
                applyCommand(commandBuffer);
                commandLength = 0;
            }
            continue;
        }

        if (commandLength + 1 >= COMMAND_BUFFER_SIZE) {
            commandLength = 0;
            Serial.println(F("ERR command too long"));
            continue;
        }
        commandBuffer[commandLength++] = received;
    }
}

void serviceDutyCycle() {
    if (onDurationMs == 0) {
        if (outputHigh) {
            setOutput(false);
        }
        return;
    }
    if (offDurationMs == 0) {
        if (!outputHigh) {
            setOutput(true);
        }
        return;
    }

    const uint32_t elapsedMs = millis() - phaseStartedMs;
    const uint32_t activeDurationMs = outputHigh ? onDurationMs : offDurationMs;
    if (elapsedMs >= activeDurationMs) {
        phaseStartedMs = millis();
        setOutput(!outputHigh);
    }
}

}  // namespace

void setup() {
    pinMode(OUTPUT_PIN, OUTPUT);
    setOutput(false);  // Safe state until an explicit serial command arrives.

    Serial.begin(SERIAL_BAUD);
    Serial.println(F("MQ8_MOSFET_READY D8_HIGH=HEATER_ON D8_LOW=HEATER_OFF"));
    Serial.println(F("Send ONms,OFFms; examples: 0,1000 | 125,875 | 1000,0"));
    printCurrentSetting();
}

void loop() {
    serviceSerial();
    serviceDutyCycle();
}
