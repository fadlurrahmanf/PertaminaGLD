#pragma once
#include "GldModeManager.h"
#include <cstddef>
#include <cstdint>

namespace pgl::gld {

enum class GldSerialCommandType : uint8_t {
    None,
    Unknown,
    SetMode,
    DebugOn,
    DebugOff,
    AppPing,
    GetInfo,
    GetStatus,
    Restart,
    RunBootCheck,
    RunAdsMcpSweep,
    SleepNow,
    SetAppConfigJson,
    SetDeviceIdJson,
    SetChAddressJson,
    SetNullingConfigJson,
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
// - RESTART
// - RUN_BOOT_CHECK
// - RUN_ADS_MCP_SWEEP
// - SLEEP_NOW
// - SET_APP_CONFIG_JSON {...}
// - SET_DEVICE_ID_JSON {...}
// - SET_CH_ADDRESS_JSON {"chId":"0064","reboot":true}
// - SET_NULLING_CONFIG_JSON {"thresholdV":0.00001,"minFinalV":0.0}
// Unknown non-empty lines are returned with type Unknown and the raw text in payload.
bool parseSerialCommand(GldSerialCommand& outCommand);

// Read Serial for "SET_MODE inference|running|dataset|nulling\n".
// Returns true + sets outMode when a valid SET_MODE line arrives.
// "GET_MODE\n" prints nothing here - caller should print current mode.
bool parseSerialModeCommand(GldMode& outMode);

// Parse a raw LoRa AppFrame for MSG_NODE_DOWNLINK.
// Validates magic, CRC, message type, targetNodeId, AES-CMAC auth tag, and
// replay commandId before accepting a mode-switch command.
bool parseLoRaDownlinkCmd(const uint8_t* frame, size_t frameLen,
                          uint16_t myNodeId,
                          const uint8_t aesKey[16],
                          bool aesKeyPresent,
                          uint16_t& lastCommandId,
                          GldMode& outMode);

}  // namespace pgl::gld
