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
    ServiceHoldOff,
    SetAppConfigJson,
    SetDeviceIdJson,
    SetChAddressJson,
    SetLoraConfigJson,
    SetNullingConfigJson,
    SetQcResultJson,
    GetQcStatus,
    RunNullingSingleJson,
    ResetQcResultJson,
    ResetQcAll,
    RunFullScaleSweepJson,
    InjectTplDone,
    InjectTplClr,
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
// - SERVICE_HOLD_OFF
// - SET_APP_CONFIG_JSON {...}
// - SET_DEVICE_ID_JSON {...}
// - SET_CH_ADDRESS_JSON {"chId":"0010","reboot":true}
// - SET_LORA_CONFIG_JSON {"freqMHz":920.0,"bwKHz":125,"sf":7,"cr":5,"syncWord":18}
// - SET_NULLING_CONFIG_JSON {"thresholdV":0.00001,"minFinalV":0.0}
// - SET_QC_RESULT_JSON {"channel":0,"pass":true,"timestamp":"2026-07-16T09:30:00"}
// - GET_QC_STATUS
// - RUN_NULLING_SINGLE_JSON {"channel":0}
// - RESET_QC_RESULT_JSON {"channel":0}
// - RESET_QC_ALL
// - RUN_FULLSCALE_SWEEP_JSON {"channel":0}
// - INJECT_TPL_DONE  (QC bench: pulse the TPL5010 DONE pin once, same pulse
//   as the automatic keepalive)
// - INJECT_TPL_CLR   (QC bench: pulse the power-latch CLR pin once, same
//   HIGH-LOW-HIGH pulse as SLEEP_NOW - this cuts board power)
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

// Validate the compact, payload-less alarm ACK emitted by the configured CH.
// A match requires CRC-valid AppFrame fields plus exact CH, GLD, and uplink
// sequence IDs. The current STAR protocol does not authenticate compact ACKs.
bool parseCompactAlarmAck(const uint8_t* frame, size_t frameLen,
                          uint16_t expectedChId,
                          uint16_t myNodeId,
                          uint8_t expectedSeq);

}  // namespace pgl::gld
