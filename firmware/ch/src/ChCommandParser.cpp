#include "ChCommandParser.h"

#include <Arduino.h>
#include <cstring>

namespace pgl::ch {

namespace {

void resetCommand(ChSerialCommand& command) {
    command.type = ChSerialCommandType::None;
    command.payload[0] = '\0';
}

void copyPayload(ChSerialCommand& out, const char* rest) {
    strncpy(out.payload, rest, sizeof(out.payload) - 1);
    out.payload[sizeof(out.payload) - 1] = '\0';
}

bool decodeLine(const char* line, ChSerialCommand& outCommand) {
    if (strcmp(line, "APP_PING") == 0) {
        outCommand.type = ChSerialCommandType::AppPing;
        return true;
    }
    if (strcmp(line, "GET_INFO") == 0) {
        outCommand.type = ChSerialCommandType::GetInfo;
        return true;
    }
    if (strcmp(line, "GET_STATUS") == 0) {
        outCommand.type = ChSerialCommandType::GetStatus;
        return true;
    }
    if (strcmp(line, "GET_NODES") == 0) {
        outCommand.type = ChSerialCommandType::GetNodes;
        return true;
    }
    if (strcmp(line, "GET_PARENTS") == 0) {
        outCommand.type = ChSerialCommandType::GetParents;
        return true;
    }
    if (strcmp(line, "SEND_HELLO") == 0) {
        outCommand.type = ChSerialCommandType::SendHello;
        return true;
    }
    if (strcmp(line, "CLEAR_PARENT_NVS") == 0) {
        outCommand.type = ChSerialCommandType::ClearParentNvs;
        return true;
    }
    if (strcmp(line, "FORCE_FAILOVER") == 0) {
        outCommand.type = ChSerialCommandType::ForceFailover;
        return true;
    }
    if (strcmp(line, "RESTART") == 0) {
        outCommand.type = ChSerialCommandType::Restart;
        return true;
    }
    if (strcmp(line, "DEBUG_ON") == 0) {
        outCommand.type = ChSerialCommandType::DebugOn;
        return true;
    }
    if (strcmp(line, "DEBUG_OFF") == 0) {
        outCommand.type = ChSerialCommandType::DebugOff;
        return true;
    }
    if (strncmp(line, "SET_CH_ADDRESS_JSON ", 20) == 0) {
        outCommand.type = ChSerialCommandType::SetChAddressJson;
        copyPayload(outCommand, line + 20);
        return true;
    }
    if (strncmp(line, "SET_ROOT_GATEWAY_JSON ", 22) == 0) {
        outCommand.type = ChSerialCommandType::SetRootGatewayJson;
        copyPayload(outCommand, line + 22);
        return true;
    }
    if (strncmp(line, "SET_STAR_LORA_JSON ", 19) == 0) {
        outCommand.type = ChSerialCommandType::SetStarLoraJson;
        copyPayload(outCommand, line + 19);
        return true;
    }
    if (strncmp(line, "SET_MESH_LORA_JSON ", 19) == 0) {
        outCommand.type = ChSerialCommandType::SetMeshLoraJson;
        copyPayload(outCommand, line + 19);
        return true;
    }
    if (line[0] != '\0') {
        outCommand.type = ChSerialCommandType::Unknown;
        copyPayload(outCommand, line);
        return true;
    }
    return false;
}

bool readCommandFrom(Stream& stream, char* buf, uint16_t& pos,
                     ChSerialCommand& outCommand) {
    while (stream.available()) {
        const int value = stream.read();
        if (value < 0) break;
        const char c = static_cast<char>(value);
        if (c == '\n' || c == '\r') {
            buf[pos] = '\0';
            pos = 0;
            if (decodeLine(buf, outCommand)) return true;
        } else if (c == '\b' || c == 0x7F) {
            if (pos > 0) {
                --pos;
                buf[pos] = '\0';
            }
        } else if (pos < 511) {
            buf[pos++] = c;
        }
    }
    return false;
}

}  // namespace

bool parseSerialCommand(ChSerialCommand& outCommand) {
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

}  // namespace pgl::ch
