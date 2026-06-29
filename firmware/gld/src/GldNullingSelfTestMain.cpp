#include <Arduino.h>
#include <SPI.h>

#include <cstdarg>
#include <cstdio>
#include <cmath>

#include "BoardPins.h"
#include "FirmwareVersion.h"
#include "GldAds1256Reader.h"
#include "GldDacMux.h"
#include "GldPower.h"

namespace {

pgl::gld::GldAds1256Reader ads;
pgl::gld::GldDacMux dac;
SPIClass sensorSpi;

constexpr uint8_t NULLING_AVG_COUNT = 8;
constexpr uint8_t NULLING_CONFIRM_COUNT = 5;
constexpr uint16_t NULLING_BASELINE_PRESCAN_MAX = 10;
constexpr uint16_t NULLING_EXP_INIT_STEP = 1;
constexpr uint16_t NULLING_EXP_MAX_STEP = 2048;
constexpr uint16_t NULLING_CONFIRM_WINDOW = 10;
constexpr uint32_t NULLING_SETTLE_MS = 5;
constexpr float NULLING_THRESHOLD_V = 0.0001f;
constexpr float NULLING_MIN_FINAL_V = 0.0f;

struct NullingSnapshot {
    int32_t raw;
    float voltage;
    uint8_t gain;
    bool valid;
    bool saturated;
};

struct NullingResult {
    uint8_t channel;
    uint16_t dacCode;
    float baselineVoltage;
    float beforeVoltage;
    float afterVoltage;
    float deltaVoltage;
    bool success;
    uint8_t errorCode;
};

void beginLogPorts() {
    Serial.begin(115200);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.begin(115200);
#endif
}

void logPrint(const char* text) {
    Serial.print(text);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.print(text);
#endif
}

void logPrintln(const char* text) {
    Serial.println(text);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.println(text);
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

void setupOutputsSafe() {
    pinMode(pgl::gld::board::PIN_LORA_CS, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_LORA_CS, HIGH);
    pinMode(pgl::gld::board::PIN_LORA_RXEN, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_LORA_RXEN, LOW);
    pinMode(pgl::gld::board::PIN_LORA_TXEN, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_LORA_TXEN, LOW);
    pinMode(pgl::gld::board::PIN_ALARM_LAMP, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_ALARM_LAMP, LOW);
    pinMode(pgl::gld::board::PIN_BUZZER, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_BUZZER, LOW);
    pinMode(pgl::gld::board::PIN_DC_FAN, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_DC_FAN, LOW);
    pinMode(pgl::gld::board::PIN_STATUS_LED, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_STATUS_LED, LOW);
}

void printBootHeader() {
    logPrintln("");
    logPrintln("Pertamina GLD nulling self-test");
    logPrintf("Firmware name: %s\n", pgl::firmware::GLD_FIRMWARE_NAME);
    logPrintf("Firmware version: %s\n", pgl::firmware::GLD_FIRMWARE_VERSION);
    logPrintf("Build date/time: %s %s Asia/Jakarta\n", __DATE__, __TIME__);
    logPrintf("I2C SDA=%u SCL=%u TCA=0x%02X MCP=0x%02X\n",
              pgl::gld::board::PIN_I2C_SDA,
              pgl::gld::board::PIN_I2C_SCL,
              pgl::gld::board::TCA9548A_ADDR,
              pgl::gld::board::MCP4725_ADDR);
    logPrintf("NULLING_CONFIG thresholdV=%.6f avg=%u confirm=%u settleMs=%lu noSave=1\n",
              NULLING_THRESHOLD_V,
              NULLING_AVG_COUNT,
              NULLING_CONFIRM_COUNT,
              static_cast<unsigned long>(NULLING_SETTLE_MS));
}

bool reportPower() {
    const pgl::gld::GldPowerReading power = pgl::gld::readGldPower();
    logPrintf("POWER_SELFTEST mode=%s rawAdc=%u adcMv=%u batteryMv=%u batteryValid=%u externalPower=%u pg24=%u\n",
              pgl::gld::gldPowerModeName(power.mode),
              power.batteryRawAdc,
              power.batteryAdcMv,
              power.batteryMv,
              power.batteryValid ? 1 : 0,
              power.externalPower ? 1 : 0,
              power.pg24PowerGood ? 1 : 0);
    logPrintln(power.externalPower ? "POWER_SELFTEST_RESULT=PASS" : "POWER_SELFTEST_RESULT=FAIL");
    return power.externalPower;
}

NullingSnapshot readAverage(uint8_t channel, uint8_t count) {
    int64_t rawSum = 0;
    float voltageSum = 0.0f;
    uint8_t gain = 0;
    bool valid = true;
    bool saturated = false;

    for (uint8_t i = 0; i < count; ++i) {
        const pgl::gld::GldAds1256Reading reading = ads.readChannel(channel);
        rawSum += reading.raw;
        voltageSum += reading.voltage;
        gain = reading.gain;
        valid = valid && reading.status == pgl::gld::GldAds1256Status::Ok;
        saturated = saturated || reading.saturated;
    }

    return {
        static_cast<int32_t>(rawSum / count),
        voltageSum / static_cast<float>(count),
        gain,
        valid,
        saturated,
    };
}

void logSnapshot(const char* label, uint8_t channel, const NullingSnapshot& snapshot) {
    logPrintf("NULLING_%s ch=%u sensor=%s raw=%ld voltage=%.6f gain=%u valid=%u saturated=%u\n",
              label,
              channel,
              pgl::gld::board::SENSOR_NAMES[channel],
              static_cast<long>(snapshot.raw),
              snapshot.voltage,
              snapshot.gain,
              snapshot.valid ? 1 : 0,
              snapshot.saturated ? 1 : 0);
}

bool findRange(uint8_t channel, float baselineVoltage, uint16_t& low, uint16_t& high) {
    uint16_t step = NULLING_EXP_INIT_STEP;
    uint16_t previous = 0;
    uint16_t current = 1;

    while (current <= pgl::gld::board::GLD_DAC_CODE_MAX) {
        if (!dac.writeDac(channel, current)) {
            return false;
        }
        delay(NULLING_SETTLE_MS);
        const NullingSnapshot snapshot = readAverage(channel, NULLING_AVG_COUNT);
        const float delta = fabsf(snapshot.voltage - baselineVoltage);
        logPrintf("NULLING_EXP ch=%u dac=%u voltage=%.6f deltaV=%.6f\n",
                  channel,
                  current,
                  snapshot.voltage,
                  delta);

        if (snapshot.valid && delta >= NULLING_THRESHOLD_V) {
            low = previous;
            high = current;
            logPrintf("NULLING_RANGE ch=%u low=%u high=%u\n", channel, low, high);
            return true;
        }

        previous = current;
        step = static_cast<uint16_t>(min<uint32_t>(static_cast<uint32_t>(step) * 2U, NULLING_EXP_MAX_STEP));
        const uint32_t next = static_cast<uint32_t>(current) + step;
        current = next > pgl::gld::board::GLD_DAC_CODE_MAX
                      ? pgl::gld::board::GLD_DAC_CODE_MAX
                      : static_cast<uint16_t>(next);
        if (previous == current) {
            break;
        }
    }

    return false;
}

uint16_t binarySearch(uint8_t channel, float baselineVoltage, uint16_t low, uint16_t high) {
    while (low + 1 < high) {
        const uint16_t mid = static_cast<uint16_t>((low + high) / 2);
        dac.writeDac(channel, mid);
        delay(NULLING_SETTLE_MS);
        const NullingSnapshot snapshot = readAverage(channel, NULLING_AVG_COUNT);
        const float delta = fabsf(snapshot.voltage - baselineVoltage);
        logPrintf("NULLING_BINARY ch=%u mid=%u voltage=%.6f deltaV=%.6f low=%u high=%u\n",
                  channel,
                  mid,
                  snapshot.voltage,
                  delta,
                  low,
                  high);
        if (delta < NULLING_THRESHOLD_V) {
            low = mid;
        } else {
            high = mid;
        }
    }
    return high;
}

bool confirmCode(uint8_t channel, float baselineVoltage, uint16_t& dacCode) {
    int start = static_cast<int>(dacCode) - 5;
    if (start < pgl::gld::board::GLD_DAC_CODE_MIN) {
        start = pgl::gld::board::GLD_DAC_CODE_MIN;
    }

    int end = start + static_cast<int>(NULLING_CONFIRM_WINDOW) - 1;
    if (end > pgl::gld::board::GLD_DAC_CODE_MAX) {
        end = pgl::gld::board::GLD_DAC_CODE_MAX;
        start = max<int>(pgl::gld::board::GLD_DAC_CODE_MIN, end - static_cast<int>(NULLING_CONFIRM_WINDOW) + 1);
    }

    for (int code = start; code <= end; ++code) {
        const bool writeOk = dac.writeDac(channel, static_cast<uint16_t>(code));
        delay(NULLING_SETTLE_MS);
        const NullingSnapshot snapshot = readAverage(channel, NULLING_CONFIRM_COUNT);
        const float delta = fabsf(snapshot.voltage - baselineVoltage);
        const bool nonNegative = snapshot.voltage >= NULLING_MIN_FINAL_V;
        const bool changed = writeOk && snapshot.valid && nonNegative && delta >= NULLING_THRESHOLD_V;
        logPrintf("NULLING_CONFIRM ch=%u dac=%d voltage=%.9f deltaV=%.6f positive=%u write=%u changed=%u\n",
                  channel,
                  code,
                  snapshot.voltage,
                  delta,
                  nonNegative ? 1 : 0,
                  writeOk ? 1 : 0,
                  changed ? 1 : 0);
        if (changed) {
            dacCode = static_cast<uint16_t>(code);
            return true;
        }
    }
    return false;
}

NullingResult nullOne(uint8_t channel, const NullingSnapshot& before) {
    NullingResult result{};
    result.channel = channel;
    result.beforeVoltage = before.voltage;
    result.success = false;
    result.errorCode = 0;

    if (!dac.writeDac(channel, 0)) {
        result.errorCode = 1;
        return result;
    }
    delay(NULLING_SETTLE_MS);

    float baselineSum = 0.0f;
    uint16_t baselineCount = 0;
    for (uint16_t code = 0; code <= NULLING_BASELINE_PRESCAN_MAX; ++code) {
        dac.writeDac(channel, code);
        delay(NULLING_SETTLE_MS);
        const NullingSnapshot snapshot = readAverage(channel, NULLING_AVG_COUNT);
        logPrintf("NULLING_BASELINE ch=%u dac=%u voltage=%.6f valid=%u\n",
                  channel,
                  code,
                  snapshot.voltage,
                  snapshot.valid ? 1 : 0);
        if (snapshot.valid) {
            baselineSum += snapshot.voltage;
            ++baselineCount;
        }
    }

    if (baselineCount == 0) {
        result.errorCode = 2;
        return result;
    }

    result.baselineVoltage = baselineSum / static_cast<float>(baselineCount);
    uint16_t low = 0;
    uint16_t high = 0;
    if (!findRange(channel, result.baselineVoltage, low, high)) {
        result.errorCode = 3;
        return result;
    }

    uint16_t selected = binarySearch(channel, result.baselineVoltage, low, high);
    if (!confirmCode(channel, result.baselineVoltage, selected)) {
        result.errorCode = 4;
        return result;
    }

    if (!dac.writeDac(channel, selected)) {
        result.errorCode = 5;
        return result;
    }
    delay(NULLING_SETTLE_MS);

    const NullingSnapshot after = readAverage(channel, NULLING_AVG_COUNT);
    result.dacCode = selected;
    result.afterVoltage = after.voltage;
    result.deltaVoltage = after.voltage - result.baselineVoltage;
    result.success = after.valid && after.voltage >= NULLING_MIN_FINAL_V;
    result.errorCode = !after.valid ? 6 : (result.success ? 0 : 7);
    return result;
}

void runNullingSelftest() {
    logPrintln("NULLING_STAGE=BEFORE");
    NullingSnapshot before[pgl::gld::board::SENSOR_COUNT]{};
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        before[ch] = readAverage(ch, NULLING_AVG_COUNT);
        logSnapshot("BEFORE", ch, before[ch]);
    }

    logPrintln("NULLING_STAGE=RUN");
    bool allSuccess = true;
    NullingResult results[pgl::gld::board::SENSOR_COUNT]{};
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        results[ch] = nullOne(ch, before[ch]);
        allSuccess = allSuccess && results[ch].success;
        logPrintf("NULLING_RESULT ch=%u sensor=%s success=%u errorCode=%u dacCode=%u baselineV=%.6f beforeV=%.6f afterV=%.9f deltaV=%.6f\n",
                  ch,
                  pgl::gld::board::SENSOR_NAMES[ch],
                  results[ch].success ? 1 : 0,
                  results[ch].errorCode,
                  results[ch].dacCode,
                  results[ch].baselineVoltage,
                  results[ch].beforeVoltage,
                  results[ch].afterVoltage,
                  results[ch].deltaVoltage);
    }

    logPrintln("NULLING_STAGE=AFTER");
    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        const NullingSnapshot after = readAverage(ch, NULLING_AVG_COUNT);
        logSnapshot("AFTER", ch, after);
    }

    logPrintln(allSuccess ? "NULLING_SELFTEST_RESULT=PASS" : "NULLING_SELFTEST_RESULT=FAIL");
}

}  // namespace

void setup() {
    beginLogPorts();
    delay(1000);
    setupOutputsSafe();
    pgl::gld::beginGldPowerPins();
    printBootHeader();
    const bool externalPower = reportPower();

    logPrintf("ADS_DRDY_BEFORE_BEGIN=%u\n", digitalRead(pgl::gld::board::PIN_ADS1256_DRDY));
    const bool adsReady = ads.begin(sensorSpi);
    logPrintf("ADS_DRDY_AFTER_BEGIN=%u\n", digitalRead(pgl::gld::board::PIN_ADS1256_DRDY));
    logPrintf("ADS_BEGIN_RESULT=%s\n", adsReady ? "PASS" : "FAIL");
    logPrintf("ADS_STATUS_REG=0x%02X\n", ads.readStatusRegister());
    logPrintf("ADS_MUX_REG=0x%02X\n", ads.readMuxRegister());
    logPrintf("ADS_ADCON_REG=0x%02X\n", ads.readAdconRegister());
    logPrintf("ADS_DRATE_REG=0x%02X\n", ads.readDrateRegister());

    const bool dacReady = dac.begin(Wire);
    logPrintf("DAC_MUX_BEGIN_RESULT=%s\n", dacReady ? "PASS" : "FAIL");

    if (adsReady && dacReady && externalPower) {
        runNullingSelftest();
    } else {
        if (!externalPower) {
            logPrintln("NULLING_BLOCKED reason=requires_external_power");
        }
        logPrintln("NULLING_SELFTEST_RESULT=FAIL");
    }
}

void loop() {
    delay(1000);
}
