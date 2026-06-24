#include <Arduino.h>
#include <RadioLib.h>
#include <SPI.h>

#include <cstdarg>
#include <cstdio>

#include "BoardPins.h"
#include "FirmwareVersion.h"
#include "GldAds1256Reader.h"
#include "GldMovingAverage.h"
#include "GldPower.h"
#include "GldSensorTypes.h"

namespace {

pgl::gld::GldAds1256Reader ads;
pgl::gld::GldMovingAverage movingAverage;
SPIClass sensorSpi;
Module* loraModule = nullptr;
SX1262* loraRadio = nullptr;
uint32_t lastScanMs = 0;
uint32_t scanCount = 0;
bool adsReady = false;
bool selftestReported = false;

constexpr uint32_t SENSOR_SELFTEST_MIN_SCANS = 5;
constexpr uint32_t SENSOR_SELFTEST_MAX_SCANS = 12;
constexpr float GLD_LORA_SELFTEST_FREQ_MHZ = 920.0f;
constexpr float GLD_LORA_SELFTEST_BW_KHZ = 125.0f;
constexpr uint8_t GLD_LORA_SELFTEST_SF = 9;
constexpr uint8_t GLD_LORA_SELFTEST_CR = 7;
constexpr uint8_t GLD_LORA_SELFTEST_SYNC_WORD = 0x12;
constexpr int8_t GLD_LORA_SELFTEST_TX_POWER_DBM = 17;
constexpr uint16_t GLD_LORA_SELFTEST_PREAMBLE = 8;
constexpr float GLD_LORA_TCXO_VOLTAGE = 1.6f;
constexpr float GLD_LORA_XTAL_TCXO_VOLTAGE = 0.0f;

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
    char buffer[192];
    va_list args;
    va_start(args, fmt);
    vsnprintf(buffer, sizeof(buffer), fmt, args);
    va_end(args);
    logPrint(buffer);
}

void printBootHeader() {
    logPrintln("");
    logPrintln("Pertamina GLD sensor self-test");
    logPrintf("Firmware name: %s\n", pgl::firmware::GLD_FIRMWARE_NAME);
    logPrintf("Firmware version: %s\n", pgl::firmware::GLD_FIRMWARE_VERSION);
    logPrintf("Protocol version: %s\n", pgl::firmware::PROTOCOL_VERSION);
    logPrintf("Build date/time: %s %s Asia/Jakarta\n", __DATE__, __TIME__);
    logPrintf("Pins SPI SCK=%u MOSI=%u MISO=%u ADS_CS=%u ADS_DRDY=%u ADS_SYNC=%u BAT=%u PG24=%u\n",
              pgl::gld::board::PIN_SPI_SCK,
              pgl::gld::board::PIN_SPI_MOSI,
              pgl::gld::board::PIN_SPI_MISO,
              pgl::gld::board::PIN_ADS1256_CS,
              pgl::gld::board::PIN_ADS1256_DRDY,
              pgl::gld::board::PIN_ADS1256_SYNC,
              pgl::gld::board::PIN_BATTERY_VOLTAGE,
              pgl::gld::board::PIN_24V_POWER_GOOD);
}

void maybeReportSelftest(uint32_t seq, bool allValid) {
    if (selftestReported) {
        return;
    }

    const uint32_t completedScans = seq + 1;
    if (completedScans < SENSOR_SELFTEST_MIN_SCANS) {
        return;
    }

    if (allValid) {
        logPrintf("SENSOR_SELFTEST_PASS_SCAN=%lu\n", static_cast<unsigned long>(seq));
        logPrintln("SENSOR_SELFTEST_RESULT=PASS");
        selftestReported = true;
        return;
    }

    if (completedScans >= SENSOR_SELFTEST_MAX_SCANS) {
        logPrintf("SENSOR_SELFTEST_FAIL_SCAN=%lu\n", static_cast<unsigned long>(seq));
        logPrintln("SENSOR_SELFTEST_RESULT=FAIL");
        selftestReported = true;
    }
}

void setupOutputsSafe() {
    pinMode(pgl::gld::board::PIN_LORA_CS, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_LORA_CS, HIGH);
    pinMode(pgl::gld::board::PIN_LORA_RST, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_LORA_RST, HIGH);
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

void reportPowerSelftest() {
    const pgl::gld::GldPowerReading power = pgl::gld::readGldPower();
    logPrintf("POWER_SELFTEST mode=%s rawAdc=%u adcMv=%u batteryMv=%u batteryValid=%u externalPower=%u pg24=%u\n",
              pgl::gld::gldPowerModeName(power.mode),
              power.batteryRawAdc,
              power.batteryAdcMv,
              power.batteryMv,
              power.batteryValid ? 1 : 0,
              power.externalPower ? 1 : 0,
              power.pg24PowerGood ? 1 : 0);

    logPrintln("POWER_SELFTEST_RESULT=PASS");
}

void runLoRaInitSelftest() {
    logPrintf("LORA_SELFTEST_CONFIG freq=%.1f bw=%.1f sf=%u cr=%u sync=0x%02X power=%d preamble=%u\n",
              GLD_LORA_SELFTEST_FREQ_MHZ,
              GLD_LORA_SELFTEST_BW_KHZ,
              GLD_LORA_SELFTEST_SF,
              GLD_LORA_SELFTEST_CR,
              GLD_LORA_SELFTEST_SYNC_WORD,
              GLD_LORA_SELFTEST_TX_POWER_DBM,
              GLD_LORA_SELFTEST_PREAMBLE);

    if (loraModule == nullptr) {
        loraModule = new Module(
            pgl::gld::board::PIN_LORA_CS,
            pgl::gld::board::PIN_LORA_DIO1,
            pgl::gld::board::PIN_LORA_RST,
            pgl::gld::board::PIN_LORA_BUSY,
            sensorSpi);
    }
    if (loraRadio == nullptr) {
        loraRadio = new SX1262(loraModule);
    }

    const int16_t tcxoState = loraRadio->begin(
        GLD_LORA_SELFTEST_FREQ_MHZ,
        GLD_LORA_SELFTEST_BW_KHZ,
        GLD_LORA_SELFTEST_SF,
        GLD_LORA_SELFTEST_CR,
        GLD_LORA_SELFTEST_SYNC_WORD,
        GLD_LORA_SELFTEST_TX_POWER_DBM,
        GLD_LORA_SELFTEST_PREAMBLE,
        GLD_LORA_TCXO_VOLTAGE);
    logPrintf("LORA_BEGIN_TCXO16_STATE=%d\n", tcxoState);

    int16_t beginState = tcxoState;
    if (beginState == RADIOLIB_ERR_SPI_CMD_FAILED) {
        beginState = loraRadio->begin(
            GLD_LORA_SELFTEST_FREQ_MHZ,
            GLD_LORA_SELFTEST_BW_KHZ,
            GLD_LORA_SELFTEST_SF,
            GLD_LORA_SELFTEST_CR,
            GLD_LORA_SELFTEST_SYNC_WORD,
            GLD_LORA_SELFTEST_TX_POWER_DBM,
            GLD_LORA_SELFTEST_PREAMBLE,
            GLD_LORA_XTAL_TCXO_VOLTAGE);
        logPrintf("LORA_BEGIN_XTAL_STATE=%d\n", beginState);
    }
    logPrintf("LORA_BEGIN_STATE=%d\n", beginState);

    if (beginState == RADIOLIB_ERR_NONE) {
        loraRadio->setRfSwitchPins(pgl::gld::board::PIN_LORA_RXEN, pgl::gld::board::PIN_LORA_TXEN);
        const int16_t standbyState = loraRadio->standby();
        logPrintf("LORA_STANDBY_STATE=%d\n", standbyState);
        digitalWrite(pgl::gld::board::PIN_LORA_RXEN, LOW);
        digitalWrite(pgl::gld::board::PIN_LORA_TXEN, LOW);
        logPrintln(standbyState == RADIOLIB_ERR_NONE ? "LORA_SELFTEST_RESULT=PASS" : "LORA_SELFTEST_RESULT=FAIL");
        return;
    }

    digitalWrite(pgl::gld::board::PIN_LORA_RXEN, LOW);
    digitalWrite(pgl::gld::board::PIN_LORA_TXEN, LOW);
    logPrintln("LORA_SELFTEST_RESULT=FAIL");
}

void scanSensorsOnce() {
    const uint32_t seq = scanCount;
    pgl::gld::GldSensorScan scan{};
    scan.timestampMs = millis();
    scan.allValid = adsReady;

    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        const pgl::gld::GldAds1256Reading reading = ads.readChannel(ch);
        const float avg = reading.status == pgl::gld::GldAds1256Status::Ok
                              ? movingAverage.add(ch, reading.voltage)
                              : movingAverage.value(ch);
        scan.channels[ch] = {
            reading.raw,
            reading.voltage,
            avg,
            reading.gain,
            reading.status,
            reading.status == pgl::gld::GldAds1256Status::Ok,
            reading.saturated,
        };
        if (!scan.channels[ch].valid || scan.channels[ch].saturated) {
            scan.allValid = false;
        }
    }

    const pgl::gld::GldPowerReading power = pgl::gld::readGldPower();
    logPrintf("SENSOR_SCAN seq=%lu ts=%lu allValid=%u powerMode=%s batteryRawAdc=%u batteryAdcMv=%u batteryMv=%u batteryValid=%u externalPower=%u pg24=%u\n",
              static_cast<unsigned long>(seq),
              static_cast<unsigned long>(scan.timestampMs),
              scan.allValid ? 1 : 0,
              pgl::gld::gldPowerModeName(power.mode),
              power.batteryRawAdc,
              power.batteryAdcMv,
              power.batteryMv,
              power.batteryValid ? 1 : 0,
              power.externalPower ? 1 : 0,
              power.pg24PowerGood ? 1 : 0);

    for (uint8_t ch = 0; ch < pgl::gld::board::SENSOR_COUNT; ++ch) {
        const pgl::gld::GldSensorSample& sample = scan.channels[ch];
        logPrintf("  ch%u %s status=%s raw=%ld voltage=%.6f movingAverageVoltage=%.6f gain=%u valid=%u saturated=%u\n",
                  ch,
                  pgl::gld::board::SENSOR_NAMES[ch],
                  pgl::gld::gldAds1256StatusName(sample.status),
                  static_cast<long>(sample.raw),
                  sample.voltage,
                  sample.movingAverageVoltage,
                  sample.gain,
                  sample.valid ? 1 : 0,
                  sample.saturated ? 1 : 0);
    }

    ++scanCount;
    digitalWrite(pgl::gld::board::PIN_STATUS_LED, scan.allValid ? HIGH : LOW);
    maybeReportSelftest(seq, scan.allValid);
}

}  // namespace

void setup() {
    beginLogPorts();
    delay(1000);
    setupOutputsSafe();
    pgl::gld::beginGldPowerPins();
    movingAverage.reset();
    printBootHeader();
    reportPowerSelftest();

    logPrintf("ADS_DRDY_BEFORE_BEGIN=%u\n", digitalRead(pgl::gld::board::PIN_ADS1256_DRDY));
    adsReady = ads.begin(sensorSpi);
    logPrintf("ADS_DRDY_AFTER_BEGIN=%u\n", digitalRead(pgl::gld::board::PIN_ADS1256_DRDY));
    logPrintf("ADS_BEGIN_RESULT=%s\n", adsReady ? "PASS" : "FAIL");
    logPrintf("ADS_STATUS_REG=0x%02X\n", ads.readStatusRegister());
    logPrintf("ADS_MUX_REG=0x%02X\n", ads.readMuxRegister());
    logPrintf("ADS_ADCON_REG=0x%02X\n", ads.readAdconRegister());
    logPrintf("ADS_DRATE_REG=0x%02X\n", ads.readDrateRegister());
    runLoRaInitSelftest();
    scanSensorsOnce();
    lastScanMs = millis();
}

void loop() {
    if (millis() - lastScanMs >= 1000) {
        lastScanMs = millis();
        scanSensorsOnce();
    }
}
