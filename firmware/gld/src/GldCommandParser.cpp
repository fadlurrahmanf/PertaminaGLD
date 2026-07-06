#include "GldCommandParser.h"
#include "AppFrame.h"
#include "GldCrypto.h"
#include "ProtocolConstants.h"
#include <Arduino.h>
#include <cstring>

namespace pgl::gld {

namespace {

constexpr uint8_t CMD_SET_MODE_AUTHENTICATED = 0x81;
constexpr size_t AUTHENTICATED_MODE_CMD_LEN = 8;
constexpr size_t AUTH_TAG_LEN = 4;

void resetCommand(GldSerialCommand& command) {
    command.type = GldSerialCommandType::None;
    command.mode = GldMode::INFERENCE;
    command.payload[0] = '\0';
}

bool decodeLine(const char* line, GldSerialCommand& outCommand) {
    if (strncmp(line, "SET_MODE ", 9) == 0) {
        outCommand.type = GldSerialCommandType::SetMode;
        outCommand.mode = gldModeFromString(line + 9);
        return true;
    }
    if (strcmp(line, "DEBUG_ON") == 0) {
        outCommand.type = GldSerialCommandType::DebugOn;
        return true;
    }
    if (strcmp(line, "DEBUG_OFF") == 0) {
        outCommand.type = GldSerialCommandType::DebugOff;
        return true;
    }
    if (strcmp(line, "APP_PING") == 0) {
        outCommand.type = GldSerialCommandType::AppPing;
        return true;
    }
    if (strcmp(line, "GET_INFO") == 0) {
        outCommand.type = GldSerialCommandType::GetInfo;
        return true;
    }
    if (strcmp(line, "GET_STATUS") == 0) {
        outCommand.type = GldSerialCommandType::GetStatus;
        return true;
    }
    if (strncmp(line, "SET_APP_CONFIG_JSON ", 20) == 0) {
        outCommand.type = GldSerialCommandType::SetAppConfigJson;
        strncpy(outCommand.payload, line + 20, sizeof(outCommand.payload) - 1);
        outCommand.payload[sizeof(outCommand.payload) - 1] = '\0';
        return true;
    }
    if (strncmp(line, "SET_DEVICE_ID_JSON ", 19) == 0) {
        outCommand.type = GldSerialCommandType::SetDeviceIdJson;
        strncpy(outCommand.payload, line + 19, sizeof(outCommand.payload) - 1);
        outCommand.payload[sizeof(outCommand.payload) - 1] = '\0';
        return true;
    }
    return false;
}

bool readCommandFrom(Stream& stream, char* buf, uint16_t& pos,
                     GldSerialCommand& outCommand) {
    while (stream.available()) {
        const int value = stream.read();
        if (value < 0) break;
        const char c = static_cast<char>(value);
        if (c == '\n' || c == '\r') {
            buf[pos] = '\0';
            pos = 0;
            if (decodeLine(buf, outCommand)) return true;
        } else if (pos < 511) {
            buf[pos++] = c;
        }
    }
    return false;
}

bool commandIdIsNewer(uint16_t candidate, uint16_t lastAccepted) {
    if (candidate == 0 || candidate == lastAccepted) {
        return false;
    }
    if (lastAccepted == 0) {
        return true;
    }
    return static_cast<uint16_t>(candidate - lastAccepted) < 0x8000;
}

bool verifyModeCommandCmac(const pgl::protocol::FrameView& decoded,
                           const uint8_t aesKey[16]) {
    if (decoded.payload == nullptr || decoded.payloadLen != AUTHENTICATED_MODE_CMD_LEN || aesKey == nullptr) {
        return false;
    }

    uint8_t macInput[9]{};
    macInput[0] = static_cast<uint8_t>((decoded.srcId >> 8) & 0xFF);
    macInput[1] = static_cast<uint8_t>(decoded.srcId & 0xFF);
    macInput[2] = static_cast<uint8_t>((decoded.dstId >> 8) & 0xFF);
    macInput[3] = static_cast<uint8_t>(decoded.dstId & 0xFF);
    macInput[4] = decoded.seq;
    memcpy(&macInput[5], decoded.payload, 4);

    uint8_t cmac[16]{};
    if (pgl::protocol::computeAesCmac128(aesKey, macInput, sizeof(macInput), cmac)
        != pgl::protocol::GldCryptoStatus::Ok) {
        return false;
    }
    return memcmp(cmac, &decoded.payload[4], AUTH_TAG_LEN) == 0;
}

}  // namespace

bool parseSerialCommand(GldSerialCommand& outCommand) {
    static char usbBuf[512];
    static uint16_t usbPos = 0;
#if defined(ARDUINO_ARCH_ESP32)
    static char uart0Buf[512];
    static uint16_t uart0Pos = 0;
#endif
    resetCommand(outCommand);

    if (readCommandFrom(Serial, usbBuf, usbPos, outCommand)) return true;
#if defined(ARDUINO_ARCH_ESP32)
    if (readCommandFrom(Serial0, uart0Buf, uart0Pos, outCommand)) return true;
#endif
    return false;
}

bool parseSerialModeCommand(GldMode& outMode) {
    GldSerialCommand command{};
    if (!parseSerialCommand(command)) return false;
    if (command.type != GldSerialCommandType::SetMode) return false;
    outMode = command.mode;
    return true;
}

bool parseLoRaDownlinkCmd(const uint8_t* frame, size_t frameLen,
                          uint16_t myNodeId,
                          const uint8_t aesKey[16],
                          bool aesKeyPresent,
                          uint16_t& lastCommandId,
                          GldMode& outMode) {
    if (frame == nullptr || frameLen == 0) return false;
    if (!aesKeyPresent || aesKey == nullptr) return false;

    pgl::protocol::FrameView decoded{};
    if (pgl::protocol::decodeAppFrame(frame, frameLen, decoded,
                                       pgl::protocol::STAR_MAX_PAYLOAD)
        != pgl::protocol::FrameStatus::Ok) {
        return false;
    }

    if (pgl::protocol::messageType(decoded.typeFlags)
        != pgl::protocol::MSG_NODE_DOWNLINK) {
        return false;
    }

    // dstId in AppFrame header must match this GLD
    if (decoded.dstId != myNodeId) return false;

    // Payload: cmdType(1)=0x81, mode(1), commandId:uint16BE, cmacTag4.
    if (decoded.payloadLen != AUTHENTICATED_MODE_CMD_LEN || decoded.payload == nullptr) return false;

    if (decoded.payload[0] != CMD_SET_MODE_AUTHENTICATED) return false;

    const uint8_t modeVal = decoded.payload[1];
    if (modeVal > static_cast<uint8_t>(GldMode::NULLING)) return false;

    const uint16_t commandId =
        (static_cast<uint16_t>(decoded.payload[2]) << 8) | decoded.payload[3];
    if (!commandIdIsNewer(commandId, lastCommandId)) return false;
    if (!verifyModeCommandCmac(decoded, aesKey)) return false;

    lastCommandId = commandId;
    outMode = static_cast<GldMode>(modeVal);
    return true;
}

}  // namespace pgl::gld
