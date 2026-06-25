#include "GldCommandParser.h"
#include "AppFrame.h"
#include "ProtocolConstants.h"
#include <Arduino.h>
#include <cstring>

namespace pgl::gld {

namespace {

void resetCommand(GldSerialCommand& command) {
    command.type = GldSerialCommandType::None;
    command.mode = GldMode::INFERENCE;
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
    return false;
}

bool readCommandFrom(Stream& stream, char* buf, uint8_t& pos,
                     GldSerialCommand& outCommand) {
    while (stream.available()) {
        const int value = stream.read();
        if (value < 0) break;
        const char c = static_cast<char>(value);
        if (c == '\n' || c == '\r') {
            buf[pos] = '\0';
            pos = 0;
            if (decodeLine(buf, outCommand)) return true;
        } else if (pos < 31) {
            buf[pos++] = c;
        }
    }
    return false;
}

}  // namespace

bool parseSerialCommand(GldSerialCommand& outCommand) {
    static char usbBuf[32];
    static uint8_t usbPos = 0;
#if defined(ARDUINO_ARCH_ESP32)
    static char uart0Buf[32];
    static uint8_t uart0Pos = 0;
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
                          uint16_t myNodeId, GldMode& outMode) {
    if (frame == nullptr || frameLen == 0) return false;

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

    // Payload: cmdType(1) mode(1) — commandPayload forwarded verbatim by CH
    if (decoded.payloadLen < 2 || decoded.payload == nullptr) return false;

    if (decoded.payload[0] != 0x01) return false;  // cmdType SET_MODE

    const uint8_t modeVal = decoded.payload[1];
    if (modeVal > static_cast<uint8_t>(GldMode::NULLING)) return false;

    outMode = static_cast<GldMode>(modeVal);
    return true;
}

}  // namespace pgl::gld
