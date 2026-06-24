#include <Arduino.h>
#include <RadioLib.h>
#include <SPI.h>
#include <esp_system.h>

#include <cstdarg>
#include <cstdio>

#include "BoardPins.h"
#include "FirmwareVersion.h"
#include "GldFrameBuilder.h"
#include "GldSelfTestConfig.h"
#include "ProtocolConstants.h"

namespace {

SPIClass gldSpi;
Module* loraModule = nullptr;
SX1262* loraRadio = nullptr;
uint8_t seq = 0;
uint32_t txCounter = 0;
uint32_t lastTxMs = 0;
bool radioReady = false;

constexpr float GLD_STAR_TX_FREQ_MHZ = 920.0f;
constexpr float GLD_STAR_TX_BW_KHZ = 125.0f;
constexpr uint8_t GLD_STAR_TX_SF = 7;
constexpr uint8_t GLD_STAR_TX_CR = 5;
constexpr uint8_t GLD_STAR_TX_SYNC_WORD = 0x12;
constexpr int8_t GLD_STAR_TX_POWER_DBM = 17;
constexpr uint16_t GLD_STAR_TX_PREAMBLE = 8;
constexpr float GLD_LORA_TCXO_VOLTAGE = 1.6f;
constexpr float GLD_LORA_XTAL_TCXO_VOLTAGE = 0.0f;
constexpr uint32_t TX_INTERVAL_MS = 10000;

#if defined(GLD_SELFTEST_ALARM_FRAME)
constexpr const char* GLD_TX_SCENARIO = "alarm-lpg";
constexpr uint8_t GLD_TX_GAS_CLASS = pgl::protocol::GLD_GAS_LPG;
constexpr uint8_t GLD_TX_CONFIDENCE = pgl::protocol::GLD_LEL_THRESHOLD_PERCENT;
#else
constexpr const char* GLD_TX_SCENARIO = "normal-clear";
constexpr uint8_t GLD_TX_GAS_CLASS = pgl::protocol::GLD_GAS_CLEAR;
constexpr uint8_t GLD_TX_CONFIDENCE = 100;
#endif

struct NonceContext {
    uint32_t counter;
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
    char buffer[256];
    va_list args;
    va_start(args, fmt);
    vsnprintf(buffer, sizeof(buffer), fmt, args);
    va_end(args);
    logPrint(buffer);
}

bool nonceProvider(uint8_t nonce[pgl::protocol::GLD_AES_GCM_NONCE_SIZE], void* context) {
    if (context == nullptr) {
        return false;
    }

    auto* nonceContext = static_cast<NonceContext*>(context);
    for (size_t i = 0; i < pgl::protocol::GLD_AES_GCM_NONCE_SIZE; ++i) {
        nonce[i] = pgl::gld::selftest::NONCE[i];
    }

    const uint32_t randomPart = esp_random();
    nonce[4] = static_cast<uint8_t>((randomPart >> 24) & 0xFF);
    nonce[5] = static_cast<uint8_t>((randomPart >> 16) & 0xFF);
    nonce[6] = static_cast<uint8_t>((randomPart >> 8) & 0xFF);
    nonce[7] = static_cast<uint8_t>(randomPart & 0xFF);
    nonce[8] = static_cast<uint8_t>((nonceContext->counter >> 24) & 0xFF);
    nonce[9] = static_cast<uint8_t>((nonceContext->counter >> 16) & 0xFF);
    nonce[10] = static_cast<uint8_t>((nonceContext->counter >> 8) & 0xFF);
    nonce[11] = static_cast<uint8_t>(nonceContext->counter & 0xFF);
    ++nonceContext->counter;
    return true;
}

void setupOutputsSafe() {
    pinMode(pgl::gld::board::PIN_ADS1256_CS, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_ADS1256_CS, HIGH);
    pinMode(pgl::gld::board::PIN_LORA_CS, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_LORA_CS, HIGH);
    pinMode(pgl::gld::board::PIN_LORA_RST, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_LORA_RST, HIGH);
    pinMode(pgl::gld::board::PIN_LORA_RXEN, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_LORA_RXEN, LOW);
    pinMode(pgl::gld::board::PIN_LORA_TXEN, OUTPUT);
    digitalWrite(pgl::gld::board::PIN_LORA_TXEN, LOW);
}

void printBootHeader() {
    logPrintln("");
    logPrintln("Pertamina GLD STAR TX self-test");
    logPrintln("SELFTEST_ONLY=1");
    logPrintf("Firmware name: %s\n", pgl::firmware::GLD_FIRMWARE_NAME);
    logPrintf("Firmware version: %s\n", pgl::firmware::GLD_FIRMWARE_VERSION);
    logPrintf("Protocol version: %s\n", pgl::firmware::PROTOCOL_VERSION);
    logPrintf("Build date/time: %s %s Asia/Jakarta\n", __DATE__, __TIME__);
    logPrintf("Pins SPI SCK=%u MOSI=%u MISO=%u LORA_CS=%u LORA_RST=%u LORA_BUSY=%u LORA_DIO1=%u LORA_RXEN=%u LORA_TXEN=%u ADS_CS=%u\n",
              pgl::gld::board::PIN_SPI_SCK,
              pgl::gld::board::PIN_SPI_MOSI,
              pgl::gld::board::PIN_SPI_MISO,
              pgl::gld::board::PIN_LORA_CS,
              pgl::gld::board::PIN_LORA_RST,
              pgl::gld::board::PIN_LORA_BUSY,
              pgl::gld::board::PIN_LORA_DIO1,
              pgl::gld::board::PIN_LORA_RXEN,
              pgl::gld::board::PIN_LORA_TXEN,
              pgl::gld::board::PIN_ADS1256_CS);
    logPrintf("GLD_STAR_TX_CONFIG freq=%.1f bw=%.1f sf=%u cr=%u sync=0x%02X power=%d preamble=%u intervalMs=%lu\n",
              GLD_STAR_TX_FREQ_MHZ,
              GLD_STAR_TX_BW_KHZ,
              GLD_STAR_TX_SF,
              GLD_STAR_TX_CR,
              GLD_STAR_TX_SYNC_WORD,
              GLD_STAR_TX_POWER_DBM,
              GLD_STAR_TX_PREAMBLE,
              static_cast<unsigned long>(TX_INTERVAL_MS));
    logPrintf("GLD_STAR_TX_SCENARIO=%s gasClass=%u confidence=%u threshold=%u\n",
              GLD_TX_SCENARIO,
              GLD_TX_GAS_CLASS,
              GLD_TX_CONFIDENCE,
              pgl::protocol::GLD_LEL_THRESHOLD_PERCENT);
}

bool beginLoraRadio() {
    gldSpi.begin(
        pgl::gld::board::PIN_SPI_SCK,
        pgl::gld::board::PIN_SPI_MISO,
        pgl::gld::board::PIN_SPI_MOSI,
        pgl::gld::board::PIN_LORA_CS);

    if (loraModule == nullptr) {
        loraModule = new Module(
            pgl::gld::board::PIN_LORA_CS,
            pgl::gld::board::PIN_LORA_DIO1,
            pgl::gld::board::PIN_LORA_RST,
            pgl::gld::board::PIN_LORA_BUSY,
            gldSpi);
    }
    if (loraRadio == nullptr) {
        loraRadio = new SX1262(loraModule);
    }

    const int16_t tcxoState = loraRadio->begin(
        GLD_STAR_TX_FREQ_MHZ,
        GLD_STAR_TX_BW_KHZ,
        GLD_STAR_TX_SF,
        GLD_STAR_TX_CR,
        GLD_STAR_TX_SYNC_WORD,
        GLD_STAR_TX_POWER_DBM,
        GLD_STAR_TX_PREAMBLE,
        GLD_LORA_TCXO_VOLTAGE);
    logPrintf("GLD_STAR_BEGIN_TCXO16_STATE=%d\n", tcxoState);

    int16_t beginState = tcxoState;
    if (beginState == RADIOLIB_ERR_SPI_CMD_FAILED) {
        beginState = loraRadio->begin(
            GLD_STAR_TX_FREQ_MHZ,
            GLD_STAR_TX_BW_KHZ,
            GLD_STAR_TX_SF,
            GLD_STAR_TX_CR,
            GLD_STAR_TX_SYNC_WORD,
            GLD_STAR_TX_POWER_DBM,
            GLD_STAR_TX_PREAMBLE,
            GLD_LORA_XTAL_TCXO_VOLTAGE);
        logPrintf("GLD_STAR_BEGIN_XTAL_STATE=%d\n", beginState);
    }
    logPrintf("GLD_STAR_BEGIN_STATE=%d\n", beginState);

    if (beginState != RADIOLIB_ERR_NONE) {
        logPrintln("GLD_STAR_TX_READY=0");
        return false;
    }

    loraRadio->setRfSwitchPins(pgl::gld::board::PIN_LORA_RXEN, pgl::gld::board::PIN_LORA_TXEN);
    logPrintln("GLD_STAR_TX_READY=1");
    return true;
}

void transmitOnce() {
    pgl::gld::GldFrameBuilderConfig config{
        pgl::gld::selftest::NODE_ID,
        pgl::gld::selftest::CH_ID,
        pgl::gld::selftest::KEY_ID,
        pgl::gld::selftest::AES_KEY,
        true,
        pgl::protocol::GLD_LEL_THRESHOLD_PERCENT,
    };
    pgl::gld::GldFrameBuildInput input{
        GLD_TX_GAS_CLASS,
        GLD_TX_CONFIDENCE,
        pgl::protocol::GLD_BATTERY_MV_INVALID,
        seq,
    };
    NonceContext nonceContext{txCounter};
    pgl::gld::GldBuiltFrame frame{};
    const pgl::gld::GldFrameStatus buildStatus =
        pgl::gld::buildGldUplinkFrame(config, input, nonceProvider, &nonceContext, frame);
    txCounter = nonceContext.counter;

    logPrintf("GLD_TX_HEADER status=%s src=0x%04X dst=0x%04X seq=%u typeFlags=0x%02X alarm=%u externalPower=%u frameSize=%u payloadLen=%u\n",
              pgl::gld::gldFrameStatusName(buildStatus),
              config.nodeId,
              config.chId,
              seq,
              frame.typeFlags,
              frame.alarm ? 1 : 0,
              config.externalPower ? 1 : 0,
              static_cast<unsigned>(frame.size),
              static_cast<unsigned>(pgl::protocol::GLD_ENCRYPTED_PAYLOAD_SIZE));

    if (buildStatus != pgl::gld::GldFrameStatus::Ok) {
        logPrintln("GLD_LORA_TX_RESULT=FAIL");
        return;
    }

    digitalWrite(pgl::gld::board::PIN_ADS1256_CS, HIGH);
    const int16_t txState = loraRadio->transmit(frame.bytes, frame.size);
    digitalWrite(pgl::gld::board::PIN_LORA_RXEN, LOW);
    digitalWrite(pgl::gld::board::PIN_LORA_TXEN, LOW);

    logPrintf("GLD_STAR_TX_STATE=%d seq=%u\n", txState, seq);
    logPrintln(txState == RADIOLIB_ERR_NONE ? "GLD_LORA_TX_RESULT=PASS" : "GLD_LORA_TX_RESULT=FAIL");
    ++seq;
}

}  // namespace

void setup() {
    beginLogPorts();
    delay(1000);
    setupOutputsSafe();
    printBootHeader();
    radioReady = beginLoraRadio();
    if (radioReady) {
        lastTxMs = millis();
        logPrintf("GLD_STAR_TX_WAIT intervalMs=%lu\n", static_cast<unsigned long>(TX_INTERVAL_MS));
    }
}

void loop() {
    if (radioReady && millis() - lastTxMs >= TX_INTERVAL_MS) {
        lastTxMs = millis();
        transmitOnce();
    }
}
