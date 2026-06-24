#pragma once
#include "GldModeManager.h"
#include <cstddef>
#include <cstdint>

namespace pgl::gld {

// Read Serial for "SET_MODE inference|dataset|nulling\n".
// Returns true + sets outMode when a valid SET_MODE line arrives.
// "GET_MODE\n" prints nothing here — caller should print current mode.
bool parseSerialModeCommand(GldMode& outMode);

// Parse a raw LoRa AppFrame for MSG_GLD_DOWNLINK_CMD.
// Validates magic, CRC, message type, and that targetNodeId == myNodeId.
// Returns true + sets outMode when a valid mode-switch command is found.
bool parseLoRaDownlinkCmd(const uint8_t* frame, size_t frameLen,
                          uint16_t myNodeId, GldMode& outMode);

}  // namespace pgl::gld
