#pragma once
#include "GldModeManager.h"
#include <cstddef>
#include <cstdint>

namespace pgl::gld {

enum class GldSerialCommandType : uint8_t {
    None,
    SetMode,
    DebugOn,
    DebugOff,
    AppPing,
    GetInfo,
    GetStatus,
    SetAppConfigJson,
    SetDeviceIdJson,
};

struct GldSerialCommand {
    GldSerialCommandType type = GldSerialCommandType::None;
    GldMode mode = GldMode::INFERENCE;
    char payload[512]{};
};

// Read USB CDC Serial and UART0 Serial0 for supported GLD runtime commands:
// - SET_MODE inference|running|dataset|nulling
// - DEBUG_ON
// - DEBUG_OFF
// - APP_PING
// - GET_INFO
// - GET_STATUS
// - SET_APP_CONFIG_JSON {...}
// - SET_DEVICE_ID_JSON {...}
bool parseSerialCommand(GldSerialCommand& outCommand);

// Read Serial for "SET_MODE inference|running|dataset|nulling\n".
// Returns true + sets outMode when a valid SET_MODE line arrives.
// "GET_MODE\n" prints nothing here - caller should print current mode.
bool parseSerialModeCommand(GldMode& outMode);

// Parse a raw LoRa AppFrame for MSG_NODE_DOWNLINK.
// Validates magic, CRC, message type, and that targetNodeId == myNodeId.
// Returns true + sets outMode when a valid mode-switch command is found.
bool parseLoRaDownlinkCmd(const uint8_t* frame, size_t frameLen,
                          uint16_t myNodeId, GldMode& outMode);

}  // namespace pgl::gld
