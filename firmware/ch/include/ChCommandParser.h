#pragma once
#include <cstddef>
#include <cstdint>

namespace pgl::ch {

// Serial command surface for the ClusterHead operator console. Mirrors the
// GLD parser (firmware/gld/include/GldCommandParser.h): newline-terminated
// ASCII commands read from USB CDC Serial and (on ESP32) UART0 Serial0 at
// 115200. The firmware answers query commands with single-line CH_*_JSON and
// acknowledges actions with CH_CMD_ACK_JSON.
//
// Supported commands:
//   APP_PING                    -> CH_CMD_ACK_JSON {cmd:"APP_PING",status:"ok"}
//   GET_INFO                    -> CH_INFO_JSON   (identity + versions + LoRa)
//   GET_STATUS                  -> CH_STATUS_JSON (state, battery, parent, queues)
//   GET_NODES                   -> CH_NODES_JSON  (NodeCache: which GLDs + ageMs)
//   GET_PARENTS                 -> CH_PARENTS_JSON (parent candidate table)
//   SEND_HELLO                  -> force a CH_HELLO now
//   CLEAR_PARENT_NVS            -> forget the stored parent, re-discover
//   FORCE_FAILOVER              -> enter PARENT_FAILOVER
//   RESTART                     -> ESP.restart()
//   DEBUG_ON / DEBUG_OFF        -> toggle verbose logging
//   SET_CH_ADDRESS_JSON {...}   -> recognised; persistence handled by caller
//   SET_ROOT_GATEWAY_JSON {...} -> recognised; persistence handled by caller
//   SET_STAR_LORA_JSON {...}    -> recognised; persistence handled by caller
//   SET_MESH_LORA_JSON {...}    -> recognised; persistence handled by caller
// Unknown non-empty lines are returned as Unknown with the raw text in payload.

enum class ChSerialCommandType : uint8_t {
    None,
    Unknown,
    AppPing,
    GetInfo,
    GetStatus,
    GetNodes,
    GetParents,
    SendHello,
    ClearParentNvs,
    ForceFailover,
    Restart,
    DebugOn,
    DebugOff,
    SetChAddressJson,
    SetRootGatewayJson,
    SetStarLoraJson,
    SetMeshLoraJson,
};

struct ChSerialCommand {
    ChSerialCommandType type = ChSerialCommandType::None;
    char payload[512]{};
};

// Poll the serial console. Returns true and fills outCommand when a full line
// has been decoded. Call once per loop() iteration.
bool parseSerialCommand(ChSerialCommand& outCommand);

}  // namespace pgl::ch
