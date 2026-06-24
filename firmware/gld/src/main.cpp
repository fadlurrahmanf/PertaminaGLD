#include <Arduino.h>

#include "AppFrame.h"
#include "FirmwareVersion.h"
#include "GldCrypto.h"
#include "GldFrameBuilder.h"
#include "GldPayload.h"
#include "GldSelfTestConfig.h"
#include "GldRecord.h"

namespace {

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

void logPrint(char value) {
    Serial.print(value);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.print(value);
#endif
}

void logPrint(size_t value) {
    Serial.print(value);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.print(value);
#endif
}

void logPrintHexByte(uint8_t value) {
    if (value < 0x10) {
        logPrint('0');
    }
    Serial.print(value, HEX);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.print(value, HEX);
#endif
}

void logPrintln() {
    Serial.println();
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.println();
#endif
}

void logPrintln(const char* text) {
    Serial.println(text);
#if defined(ARDUINO_ARCH_ESP32)
    Serial0.println(text);
#endif
}

bool bytesEqual(const uint8_t* left, const uint8_t* right, size_t len) {
    for (size_t i = 0; i < len; ++i) {
        if (left[i] != right[i]) {
            return false;
        }
    }
    return true;
}

bool fixedNonceProvider(uint8_t nonce[pgl::protocol::GLD_AES_GCM_NONCE_SIZE], void* context) {
    const uint8_t* fixedNonce = static_cast<const uint8_t*>(context);
    if (fixedNonce == nullptr) {
        return false;
    }

    for (size_t i = 0; i < pgl::protocol::GLD_AES_GCM_NONCE_SIZE; ++i) {
        nonce[i] = fixedNonce[i];
    }
    return true;
}

bool randomNonceProvider(uint8_t nonce[pgl::protocol::GLD_AES_GCM_NONCE_SIZE], void*) {
    for (size_t i = 0; i < pgl::protocol::GLD_AES_GCM_NONCE_SIZE; i += 4) {
        const uint32_t value = esp_random();
        nonce[i] = static_cast<uint8_t>((value >> 24) & 0xFF);
        nonce[i + 1] = static_cast<uint8_t>((value >> 16) & 0xFF);
        nonce[i + 2] = static_cast<uint8_t>((value >> 8) & 0xFF);
        nonce[i + 3] = static_cast<uint8_t>(value & 0xFF);
    }
    return true;
}

void printHex(const char* label, const uint8_t* data, size_t len) {
    logPrint(label);
    logPrint(": ");
    for (size_t i = 0; i < len; ++i) {
        logPrintHexByte(data[i]);
    }
    logPrintln();
}

const char* cryptoStatusName(pgl::protocol::GldCryptoStatus status) {
    using pgl::protocol::GldCryptoStatus;
    switch (status) {
        case GldCryptoStatus::Ok:
            return "Ok";
        case GldCryptoStatus::InvalidInput:
            return "InvalidInput";
        case GldCryptoStatus::UnsupportedPlatform:
            return "UnsupportedPlatform";
        case GldCryptoStatus::CryptoInitFailed:
            return "CryptoInitFailed";
        case GldCryptoStatus::CryptoFailed:
            return "CryptoFailed";
        case GldCryptoStatus::AuthFailed:
            return "AuthFailed";
    }
    return "Unknown";
}

bool printAndValidateFrame(
    const char* label,
    const pgl::gld::GldBuiltFrame& frame,
    bool expectedAlarm,
    uint8_t expectedTypeFlags,
    bool printFrameHex) {
    using namespace pgl::protocol;

    logPrint(label);
    logPrint(" alarm=");
    logPrintln(frame.alarm ? "true" : "false");
    logPrint(label);
    logPrint(" typeFlags=0x");
    logPrintHexByte(frame.typeFlags);
    logPrintln();
    logPrint(label);
    logPrint(" payloadLen=");
    logPrint(GLD_ENCRYPTED_PAYLOAD_SIZE);
    logPrint(" frameSize=");
    logPrint(frame.size);
    logPrintln();

    FrameView decoded{};
    const FrameStatus decodeStatus = decodeAppFrame(frame.bytes, frame.size, decoded, STAR_MAX_PAYLOAD);
    const bool pass =
        frame.alarm == expectedAlarm &&
        frame.typeFlags == expectedTypeFlags &&
        frame.size == APPFRAME_OVERHEAD + GLD_ENCRYPTED_PAYLOAD_SIZE &&
        decodeStatus == FrameStatus::Ok &&
        decoded.payloadLen == GLD_ENCRYPTED_PAYLOAD_SIZE &&
        decoded.typeFlags == expectedTypeFlags;

    if (printFrameHex) {
        printHex(label, frame.bytes, frame.size);
    }

    logPrint(label);
    logPrint("_RESULT=");
    logPrintln(pass ? "PASS" : "FAIL");
    return pass;
}

bool runVectorSelfTest() {
    using namespace pgl::protocol;
    using namespace pgl::gld::selftest;

    logPrintln();
    logPrintln("Pertamina GLD self-test");
    logPrint("Firmware name: ");
    logPrintln(pgl::firmware::GLD_FIRMWARE_NAME);
    logPrint("Firmware version: ");
    logPrintln(pgl::firmware::GLD_FIRMWARE_VERSION);
    logPrint("Protocol version: ");
    logPrintln(pgl::firmware::PROTOCOL_VERSION);
    logPrint("Build date/time: ");
    logPrint(__DATE__);
    logPrint(' ');
    logPrint(__TIME__);
    logPrintln(" Asia/Jakarta");

    const GldPlainPayload plain{
        GLD_GAS_LPG,
        80,
        3700,
    };

    uint8_t plainBytes[GLD_PLAINTEXT_PAYLOAD_SIZE]{};
    const bool plainOk = encodeGldPlainPayload(plain, plainBytes);
    printHex("Plaintext", plainBytes, sizeof(plainBytes));

    const uint8_t recordFlags = makeRecordFlags(true, true);
    uint8_t aad[GLD_AAD_SIZE]{};
    buildGldAad(NODE_ID, GLD_SEQ, recordFlags, KEY_ID, aad);
    printHex("AAD", aad, sizeof(aad));

    GldEncryptedPayload encrypted{};
    const GldCryptoStatus cryptoStatus =
        encryptGldPayload(AES_KEY, KEY_ID, NONCE, plain, NODE_ID, GLD_SEQ, recordFlags, encrypted);
    logPrint("Crypto status: ");
    logPrintln(cryptoStatusName(cryptoStatus));
    printHex("Encrypted payload", encrypted.bytes, GLD_ENCRYPTED_PAYLOAD_SIZE);

    pgl::gld::GldBuiltFrame frame{};
    pgl::gld::GldFrameBuilderConfig builderConfig{
        NODE_ID,
        CH_ID,
        KEY_ID,
        AES_KEY,
        true,
        GLD_LEL_THRESHOLD_PERCENT,
    };
    pgl::gld::GldFrameBuildInput builderInput{
        GLD_GAS_LPG,
        80,
        3700,
        GLD_SEQ,
    };
    const pgl::gld::GldFrameStatus frameStatus =
        buildGldUplinkFrame(builderConfig, builderInput, fixedNonceProvider, const_cast<uint8_t*>(NONCE), frame);

    logPrint("AppFrame status: ");
    logPrintln(pgl::gld::gldFrameStatusName(frameStatus));
    logPrint("AppFrame size: ");
    logPrint(frame.size);
    logPrintln();
    if (frameStatus == pgl::gld::GldFrameStatus::Ok) {
        printHex("AppFrame", frame.bytes, frame.size);
    }

    const bool pass =
        plainOk &&
        bytesEqual(plainBytes, EXPECTED_PLAINTEXT, GLD_PLAINTEXT_PAYLOAD_SIZE) &&
        bytesEqual(aad, EXPECTED_AAD, GLD_AAD_SIZE) &&
        cryptoStatus == GldCryptoStatus::Ok &&
        bytesEqual(encrypted.bytes, EXPECTED_ENCRYPTED_PAYLOAD, GLD_ENCRYPTED_PAYLOAD_SIZE) &&
        frameStatus == pgl::gld::GldFrameStatus::Ok &&
        bytesEqual(frame.encrypted.bytes, EXPECTED_ENCRYPTED_PAYLOAD, GLD_ENCRYPTED_PAYLOAD_SIZE);

    logPrint("VECTOR_RESULT=");
    logPrintln(pass ? "PASS" : "FAIL");
    return pass;
}

bool runFrameBuilderSelfTest() {
    using namespace pgl::protocol;
    using namespace pgl::gld::selftest;

    const pgl::gld::GldFrameBuilderConfig batteryConfig{
        NODE_ID,
        CH_ID,
        KEY_ID,
        AES_KEY,
        false,
        GLD_LEL_THRESHOLD_PERCENT,
    };

    pgl::gld::GldBuiltFrame normalFrame{};
    const pgl::gld::GldFrameStatus normalStatus = buildGldUplinkFrame(
        batteryConfig,
        {GLD_GAS_CLEAR, 100, 3700, static_cast<uint8_t>(GLD_SEQ + 1)},
        randomNonceProvider,
        nullptr,
        normalFrame);
    const bool normalPass =
        normalStatus == pgl::gld::GldFrameStatus::Ok &&
        printAndValidateFrame("NORMAL", normalFrame, false, TYPE_GLD_NORMAL_BATTERY, false);

    pgl::gld::GldBuiltFrame alarmFrame{};
    const pgl::gld::GldFrameStatus alarmStatus = buildGldUplinkFrame(
        batteryConfig,
        {GLD_GAS_LPG, GLD_LEL_THRESHOLD_PERCENT, 3700, static_cast<uint8_t>(GLD_SEQ + 2)},
        randomNonceProvider,
        nullptr,
        alarmFrame);
    const bool alarmPass =
        alarmStatus == pgl::gld::GldFrameStatus::Ok &&
        printAndValidateFrame("ALARM", alarmFrame, true, TYPE_GLD_ALARM_BATTERY, false);

    pgl::gld::GldBuiltFrame retryFrame = alarmFrame;
    const bool retryPass =
        alarmPass &&
        bytesEqual(retryFrame.bytes, alarmFrame.bytes, alarmFrame.size) &&
        retryFrame.size == alarmFrame.size &&
        printAndValidateFrame("RETRY", retryFrame, true, TYPE_GLD_ALARM_BATTERY, false);
    logPrint("RETRY_IDENTICAL_RESULT=");
    logPrintln(retryPass ? "PASS" : "FAIL");

    pgl::gld::GldBuiltFrame clearFrame{};
    const pgl::gld::GldFrameStatus clearStatus = buildGldUplinkFrame(
        batteryConfig,
        {GLD_GAS_CLEAR, 0, 3700, static_cast<uint8_t>(GLD_SEQ + 3)},
        randomNonceProvider,
        nullptr,
        clearFrame);
    const bool clearPass =
        clearStatus == pgl::gld::GldFrameStatus::Ok &&
        printAndValidateFrame("CLEAR", clearFrame, false, TYPE_GLD_NORMAL_BATTERY, false);

    return normalPass && alarmPass && retryPass && clearPass;
}

void runSelfTest() {
    const bool vectorPass = runVectorSelfTest();
    const bool frameBuilderPass = runFrameBuilderSelfTest();
    logPrint("SELFTEST_RESULT=");
    logPrintln(vectorPass && frameBuilderPass ? "PASS" : "FAIL");
}

}  // namespace

void setup() {
    beginLogPorts();
    delay(1000);
    runSelfTest();
}

void loop() {
    delay(1000);
}
