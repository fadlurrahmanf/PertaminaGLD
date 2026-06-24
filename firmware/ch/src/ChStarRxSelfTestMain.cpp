#include <Arduino.h>
#include <RadioLib.h>
#include <SPI.h>

#include <cstdarg>
#include <cstdio>

#include "ChBoardPins.h"
#include "ChUplink.h"
#include "FirmwareVersion.h"
#include "ProtocolConstants.h"

namespace {

Module* starModule = nullptr;
SX1262* starRadio = nullptr;
const char* activeRadioName = "NONE";
bool radioReady = false;

constexpr float STAR_FREQ_MHZ = 920.0f;
constexpr float STAR_BW_KHZ = 125.0f;
constexpr uint8_t STAR_SF = 7;
constexpr uint8_t STAR_CR = 5;
constexpr uint8_t STAR_SYNC_WORD = 0x12;
constexpr int8_t STAR_TX_POWER_DBM = 17;
constexpr uint16_t STAR_PREAMBLE = 8;
constexpr float STAR_TCXO_VOLTAGE = 1.6f;
constexpr float STAR_XTAL_TCXO_VOLTAGE = 0.0f;
constexpr uint32_t STAR_SPI_HZ = 2000000;

struct RadioPins {
    uint8_t cs;
    uint8_t dio1;
    uint8_t rst;
    uint8_t busy;
    uint8_t rxen;
    uint8_t txen;
};

constexpr RadioPins RADIO_A_PINS{
    pgl::ch::board::PIN_RADIO_A_CS,
    pgl::ch::board::PIN_RADIO_A_DIO1,
    pgl::ch::board::PIN_RADIO_A_RST,
    pgl::ch::board::PIN_RADIO_A_BUSY,
    pgl::ch::board::PIN_RADIO_A_RXEN,
    pgl::ch::board::PIN_RADIO_A_TXEN,
};

constexpr RadioPins RADIO_B_PINS{
    pgl::ch::board::PIN_RADIO_B_CS,
    pgl::ch::board::PIN_RADIO_B_DIO1,
    pgl::ch::board::PIN_RADIO_B_RST,
    pgl::ch::board::PIN_RADIO_B_BUSY,
    pgl::ch::board::PIN_RADIO_B_RXEN,
    pgl::ch::board::PIN_RADIO_B_TXEN,
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

void printHex(const uint8_t* data, size_t len) {
    for (size_t i = 0; i < len; ++i) {
        logPrintf("%02X", data[i]);
        if (i + 1 < len) {
            logPrint(" ");
        }
    }
}

void setupRadioPinsSafe() {
    pinMode(pgl::ch::board::PIN_RADIO_A_CS, OUTPUT);
    digitalWrite(pgl::ch::board::PIN_RADIO_A_CS, HIGH);
    pinMode(pgl::ch::board::PIN_RADIO_B_CS, OUTPUT);
    digitalWrite(pgl::ch::board::PIN_RADIO_B_CS, HIGH);
    pinMode(pgl::ch::board::PIN_RADIO_A_RST, OUTPUT);
    digitalWrite(pgl::ch::board::PIN_RADIO_A_RST, LOW);
    pinMode(pgl::ch::board::PIN_RADIO_B_RST, OUTPUT);
    digitalWrite(pgl::ch::board::PIN_RADIO_B_RST, LOW);
    pinMode(pgl::ch::board::PIN_RADIO_A_RXEN, OUTPUT);
    digitalWrite(pgl::ch::board::PIN_RADIO_A_RXEN, LOW);
    pinMode(pgl::ch::board::PIN_RADIO_A_TXEN, OUTPUT);
    digitalWrite(pgl::ch::board::PIN_RADIO_A_TXEN, LOW);
    pinMode(pgl::ch::board::PIN_RADIO_B_RXEN, OUTPUT);
    digitalWrite(pgl::ch::board::PIN_RADIO_B_RXEN, LOW);
    pinMode(pgl::ch::board::PIN_RADIO_B_TXEN, OUTPUT);
    digitalWrite(pgl::ch::board::PIN_RADIO_B_TXEN, LOW);
}

void printBootHeader() {
    logPrintln("");
    logPrintln("Pertamina CH STAR RX self-test");
    logPrintln("SELFTEST_ONLY=1");
    logPrintf("Firmware name: %s\n", pgl::firmware::CH_FIRMWARE_NAME);
    logPrintf("Firmware version: %s\n", pgl::firmware::CH_FIRMWARE_VERSION);
    logPrintf("Protocol version: %s\n", pgl::firmware::PROTOCOL_VERSION);
    logPrintf("Build date/time: %s %s Asia/Jakarta\n", __DATE__, __TIME__);
    logPrintf("Pins SPI SCK=%u MOSI=%u MISO=%u NSS1=%u LRST1=%u BUSY1=%u DIO11=%u RXEN1=%u TXEN1=%u NSS2=%u LRST2=%u BUSY2=%u DIO12=%u RXEN2=%u TXEN2=%u\n",
              pgl::ch::board::PIN_SPI_SCK,
              pgl::ch::board::PIN_SPI_MOSI,
              pgl::ch::board::PIN_SPI_MISO,
              pgl::ch::board::PIN_RADIO_A_CS,
              pgl::ch::board::PIN_RADIO_A_RST,
              pgl::ch::board::PIN_RADIO_A_BUSY,
              pgl::ch::board::PIN_RADIO_A_DIO1,
              pgl::ch::board::PIN_RADIO_A_RXEN,
              pgl::ch::board::PIN_RADIO_A_TXEN,
              pgl::ch::board::PIN_RADIO_B_CS,
              pgl::ch::board::PIN_RADIO_B_RST,
              pgl::ch::board::PIN_RADIO_B_BUSY,
              pgl::ch::board::PIN_RADIO_B_DIO1,
              pgl::ch::board::PIN_RADIO_B_RXEN,
              pgl::ch::board::PIN_RADIO_B_TXEN);
    logPrintf("CH_STAR_RX_CONFIG freq=%.1f bw=%.1f sf=%u cr=%u sync=0x%02X power=%d preamble=%u maxFrame=%u\n",
              STAR_FREQ_MHZ,
              STAR_BW_KHZ,
              STAR_SF,
              STAR_CR,
              STAR_SYNC_WORD,
              STAR_TX_POWER_DBM,
              STAR_PREAMBLE,
              static_cast<unsigned>(pgl::protocol::APPFRAME_OVERHEAD + pgl::protocol::STAR_MAX_PAYLOAD));
}

void releaseRadioReset() {
    digitalWrite(pgl::ch::board::PIN_RADIO_A_RST, LOW);
    digitalWrite(pgl::ch::board::PIN_RADIO_B_RST, LOW);
    delay(50);
    digitalWrite(pgl::ch::board::PIN_RADIO_A_RST, HIGH);
    digitalWrite(pgl::ch::board::PIN_RADIO_B_RST, HIGH);
    delay(500);
}

void releaseRadio() {
    if (starRadio != nullptr) {
        delete starRadio;
        starRadio = nullptr;
    }
    if (starModule != nullptr) {
        delete starModule;
        starModule = nullptr;
    }
}

bool beginRadioWithPins(const char* radioName, const RadioPins& pins) {
    releaseRadio();
    digitalWrite(pgl::ch::board::PIN_RADIO_A_CS, HIGH);
    digitalWrite(pgl::ch::board::PIN_RADIO_B_CS, HIGH);
    starModule = new Module(pins.cs, pins.dio1, pins.rst, pins.busy, SPI, SPISettings(STAR_SPI_HZ, MSBFIRST, SPI_MODE0));
    starRadio = new SX1262(starModule);

    const int16_t tcxoState = starRadio->begin(
        STAR_FREQ_MHZ,
        STAR_BW_KHZ,
        STAR_SF,
        STAR_CR,
        STAR_SYNC_WORD,
        STAR_TX_POWER_DBM,
        STAR_PREAMBLE,
        STAR_TCXO_VOLTAGE,
        false);
    logPrintf("CH_STAR_PROBE radio=%s tcxo16State=%d\n", radioName, tcxoState);

    int16_t beginState = tcxoState;
    if (beginState == RADIOLIB_ERR_SPI_CMD_FAILED) {
        beginState = starRadio->begin(
            STAR_FREQ_MHZ,
            STAR_BW_KHZ,
            STAR_SF,
            STAR_CR,
            STAR_SYNC_WORD,
            STAR_TX_POWER_DBM,
            STAR_PREAMBLE,
            STAR_XTAL_TCXO_VOLTAGE,
            false);
        logPrintf("CH_STAR_PROBE radio=%s xtalState=%d\n", radioName, beginState);
    }
    logPrintf("CH_STAR_PROBE radio=%s beginState=%d\n", radioName, beginState);

    if (beginState != RADIOLIB_ERR_NONE) {
        releaseRadio();
        return false;
    }

    starRadio->setRfSwitchPins(pins.rxen, pins.txen);
    activeRadioName = radioName;
    logPrintf("CH_STAR_ACTIVE_RADIO=%s\n", activeRadioName);
    logPrintln("CH_STAR_RX_READY=1");
    return true;
}

bool beginStarRadio() {
    SPI.begin(
        pgl::ch::board::PIN_SPI_SCK,
        pgl::ch::board::PIN_SPI_MISO,
        pgl::ch::board::PIN_SPI_MOSI);
    releaseRadioReset();

    if (beginRadioWithPins("A/U1", RADIO_A_PINS)) {
        return true;
    }

    logPrintln("CH_STAR_RADIO_A_RESULT=CHIP_NOT_FOUND_OR_INIT_FAILED");
    if (beginRadioWithPins("B/U3", RADIO_B_PINS)) {
        logPrintln("CH_STAR_RADIO_B_DIAGNOSTIC_FALLBACK=1");
        return true;
    }

    logPrintln("CH_STAR_RX_READY=0");
    return false;
}

void receiveOnce() {
    uint8_t frame[pgl::protocol::APPFRAME_OVERHEAD + pgl::protocol::STAR_MAX_PAYLOAD]{};
    const int16_t state = starRadio->receive(frame, sizeof(frame));
    if (state == RADIOLIB_ERR_RX_TIMEOUT) {
        logPrintln("CH_STAR_RX_TIMEOUT");
        return;
    }

    const size_t packetLen = starRadio->getPacketLength();
    logPrintf("CH_STAR_RX_STATE=%d radio=%s len=%u rssi=%.2f snr=%.2f\n",
              state,
              activeRadioName,
              static_cast<unsigned>(packetLen),
              starRadio->getRSSI(),
              starRadio->getSNR());

    if (state != RADIOLIB_ERR_NONE) {
        logPrintln("CH_LORA_RX_RESULT=FAIL");
        return;
    }

    logPrint("CH_STAR_RX_HEX=");
    printHex(frame, packetLen);
    logPrintln("");

    pgl::ch::ChGldUplinkView uplink{};
    const pgl::ch::ChUplinkStatus parseStatus = pgl::ch::parseGldUplinkFrame(frame, packetLen, uplink);
    logPrintf("CH_STAR_PARSE status=%s nodeId=0x%04X chId=0x%04X seq=%u typeFlags=0x%02X alarm=%u externalPower=%u payloadLen=%u\n",
              pgl::ch::chUplinkStatusName(parseStatus),
              uplink.nodeId,
              uplink.chId,
              uplink.seq,
              uplink.typeFlags,
              uplink.alarm ? 1 : 0,
              uplink.externalPower ? 1 : 0,
              uplink.encryptedPayloadLen);
    logPrintln(parseStatus == pgl::ch::ChUplinkStatus::Ok ? "CH_LORA_RX_RESULT=PASS" : "CH_LORA_RX_RESULT=FAIL");
}

}  // namespace

void setup() {
    beginLogPorts();
    delay(1000);
    setupRadioPinsSafe();
    printBootHeader();
    radioReady = beginStarRadio();
}

void loop() {
    if (radioReady && starRadio != nullptr) {
        receiveOnce();
    } else {
        logPrintln("CH_STAR_RX_IDLE_NO_RADIO");
        delay(1000);
    }
    delay(100);
}
