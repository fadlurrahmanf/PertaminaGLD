#include "GldCommandParser.h"
#include "AppFrame.h"
#include "ProtocolConstants.h"
#include <Arduino.h>
#include <cstring>

namespace pgl::gld {

bool parseSerialModeCommand(GldMode& outMode) {
    static char buf[32];
    static uint8_t pos = 0;

    while (Serial.available()) {
        const char c = static_cast<char>(Serial.read());
        if (c == '\n' || c == '\r') {
            buf[pos] = '\0';
            pos = 0;
            if (strncmp(buf, "SET_MODE ", 9) == 0) {
                outMode = gldModeFromString(buf + 9);
                return true;
            }
        } else if (pos < static_cast<uint8_t>(sizeof(buf) - 1)) {
            buf[pos++] = c;
        }
    }
    return false;
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
