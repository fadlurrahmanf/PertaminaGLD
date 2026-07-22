#pragma once

#include <cstddef>
#include <cstdint>

#include "ProtocolConstants.h"

namespace pgl::protocol {

enum class ServerNodeCommandStatus : uint8_t {
    Ok,
    InvalidArgument,
    BufferTooSmall,
    CommandTooLong,
    InvalidRoute,
    MalformedPayload,
    UnsupportedVersion,
};

struct ServerNodeCommandView {
    bool routed;
    uint8_t routeVersion;
    uint8_t hopCount;
    const uint8_t* hopBytes;
    uint16_t targetNodeId;
    uint16_t commandId;
    uint16_t ttlSec;
    uint8_t commandLen;
    const uint8_t* commandBytes;
};

inline uint16_t readServerNodeCommandU16Be(const uint8_t* in) {
    return static_cast<uint16_t>((static_cast<uint16_t>(in[0]) << 8) | in[1]);
}

inline void writeServerNodeCommandU16Be(uint8_t* out, uint16_t value) {
    out[0] = static_cast<uint8_t>((value >> 8) & 0xFF);
    out[1] = static_cast<uint8_t>(value & 0xFF);
}

inline const char* serverNodeCommandStatusName(ServerNodeCommandStatus status) {
    switch (status) {
        case ServerNodeCommandStatus::Ok:                 return "ok";
        case ServerNodeCommandStatus::InvalidArgument:    return "invalid-argument";
        case ServerNodeCommandStatus::BufferTooSmall:     return "buffer-too-small";
        case ServerNodeCommandStatus::CommandTooLong:     return "command-too-long";
        case ServerNodeCommandStatus::InvalidRoute:       return "invalid-route";
        case ServerNodeCommandStatus::MalformedPayload:   return "malformed-payload";
        case ServerNodeCommandStatus::UnsupportedVersion: return "unsupported-version";
    }
    return "unknown";
}

inline bool isRoutedServerNodeCommandPayload(const uint8_t* payload, size_t payloadLen) {
    return payload != nullptr &&
           payloadLen >= SERVER_NODE_COMMAND_ROUTE_V1_HEADER_SIZE &&
           payload[0] == SERVER_NODE_COMMAND_ROUTE_MAGIC &&
           payload[6] == SERVER_NODE_COMMAND_ROUTE_LEGACY_GUARD;
}

inline bool serverNodeCommandRouteIsValid(const uint16_t* hopList, size_t hopCount) {
    if (hopList == nullptr || hopCount == 0 || hopCount > 0xFF) return false;
    for (size_t i = 0; i < hopCount; ++i) {
        if (hopList[i] == 0 || hopList[i] == 0xFFFF) return false;
        for (size_t j = 0; j < i; ++j) {
            if (hopList[j] == hopList[i]) return false;
        }
    }
    return true;
}

inline ServerNodeCommandStatus encodeLegacyServerNodeCommandPayload(
    uint16_t targetNodeId,
    uint16_t commandId,
    uint16_t ttlSec,
    const uint8_t* commandBytes,
    size_t commandLen,
    uint8_t* out,
    size_t outCapacity,
    size_t& outLen) {
    outLen = 0;
    if (out == nullptr || (commandLen > 0 && commandBytes == nullptr)) {
        return ServerNodeCommandStatus::InvalidArgument;
    }
    if (commandLen > NODE_DOWNLINK_COMMAND_MAX_SIZE) {
        return ServerNodeCommandStatus::CommandTooLong;
    }
    const size_t totalLen = SERVER_NODE_COMMAND_LEGACY_HEADER_SIZE + commandLen;
    if (totalLen > MESH_MAX_PAYLOAD || outCapacity < totalLen) {
        return ServerNodeCommandStatus::BufferTooSmall;
    }

    writeServerNodeCommandU16Be(&out[0], targetNodeId);
    writeServerNodeCommandU16Be(&out[2], commandId);
    writeServerNodeCommandU16Be(&out[4], ttlSec);
    out[6] = static_cast<uint8_t>(commandLen);
    for (size_t i = 0; i < commandLen; ++i) out[7 + i] = commandBytes[i];
    outLen = totalLen;
    return ServerNodeCommandStatus::Ok;
}

inline ServerNodeCommandStatus encodeRoutedServerNodeCommandPayloadV1(
    const uint16_t* hopList,
    size_t hopCount,
    uint16_t targetNodeId,
    uint16_t commandId,
    uint16_t ttlSec,
    const uint8_t* commandBytes,
    size_t commandLen,
    uint8_t* out,
    size_t outCapacity,
    size_t& outLen) {
    outLen = 0;
    if (out == nullptr || (commandLen > 0 && commandBytes == nullptr)) {
        return ServerNodeCommandStatus::InvalidArgument;
    }
    if (!serverNodeCommandRouteIsValid(hopList, hopCount)) {
        return ServerNodeCommandStatus::InvalidRoute;
    }
    if (commandLen > NODE_DOWNLINK_COMMAND_MAX_SIZE) {
        return ServerNodeCommandStatus::CommandTooLong;
    }

    const size_t commandBodyOffset = SERVER_NODE_COMMAND_ROUTE_V1_HEADER_SIZE + (hopCount * 2);
    const size_t totalLen = commandBodyOffset + SERVER_NODE_COMMAND_LEGACY_HEADER_SIZE + commandLen;
    if (totalLen > MESH_MAX_PAYLOAD || outCapacity < totalLen) {
        return ServerNodeCommandStatus::BufferTooSmall;
    }

    out[0] = SERVER_NODE_COMMAND_ROUTE_MAGIC;
    out[1] = SERVER_NODE_COMMAND_ROUTE_VERSION_V1;
    out[2] = static_cast<uint8_t>(hopCount);
    out[3] = 0;  // flags, reserved for a later protocol version
    out[4] = 0;
    out[5] = 0;
    out[6] = SERVER_NODE_COMMAND_ROUTE_LEGACY_GUARD;
    for (size_t i = 0; i < hopCount; ++i) {
        writeServerNodeCommandU16Be(&out[SERVER_NODE_COMMAND_ROUTE_V1_HEADER_SIZE + (i * 2)],
                                    hopList[i]);
    }

    size_t commandBodyLen = 0;
    const ServerNodeCommandStatus bodyStatus = encodeLegacyServerNodeCommandPayload(
        targetNodeId, commandId, ttlSec, commandBytes, commandLen,
        &out[commandBodyOffset], outCapacity - commandBodyOffset, commandBodyLen);
    if (bodyStatus != ServerNodeCommandStatus::Ok) return bodyStatus;

    outLen = commandBodyOffset + commandBodyLen;
    return ServerNodeCommandStatus::Ok;
}

inline ServerNodeCommandStatus decodeServerNodeCommandPayload(
    const uint8_t* payload,
    size_t payloadLen,
    ServerNodeCommandView& out) {
    out = ServerNodeCommandView{};
    if (payload == nullptr || payloadLen < SERVER_NODE_COMMAND_LEGACY_HEADER_SIZE) {
        return ServerNodeCommandStatus::MalformedPayload;
    }

    size_t commandBodyOffset = 0;
    if (isRoutedServerNodeCommandPayload(payload, payloadLen)) {
        if (payload[1] != SERVER_NODE_COMMAND_ROUTE_VERSION_V1) {
            return ServerNodeCommandStatus::UnsupportedVersion;
        }
        const uint8_t hopCount = payload[2];
        if (hopCount == 0 || payload[3] != 0 || payload[4] != 0 || payload[5] != 0) {
            return ServerNodeCommandStatus::InvalidRoute;
        }
        commandBodyOffset = SERVER_NODE_COMMAND_ROUTE_V1_HEADER_SIZE +
                            (static_cast<size_t>(hopCount) * 2);
        if (commandBodyOffset > payloadLen ||
            payloadLen - commandBodyOffset < SERVER_NODE_COMMAND_LEGACY_HEADER_SIZE) {
            return ServerNodeCommandStatus::MalformedPayload;
        }
        for (uint8_t i = 0; i < hopCount; ++i) {
            const uint16_t hop = readServerNodeCommandU16Be(
                &payload[SERVER_NODE_COMMAND_ROUTE_V1_HEADER_SIZE +
                         (static_cast<size_t>(i) * 2)]);
            if (hop == 0 || hop == 0xFFFF) return ServerNodeCommandStatus::InvalidRoute;
            for (uint8_t j = 0; j < i; ++j) {
                const uint16_t prior = readServerNodeCommandU16Be(
                    &payload[SERVER_NODE_COMMAND_ROUTE_V1_HEADER_SIZE +
                             (static_cast<size_t>(j) * 2)]);
                if (hop == prior) return ServerNodeCommandStatus::InvalidRoute;
            }
        }
        out.routed = true;
        out.routeVersion = payload[1];
        out.hopCount = hopCount;
        out.hopBytes = &payload[SERVER_NODE_COMMAND_ROUTE_V1_HEADER_SIZE];
    }

    const uint8_t* commandBody = &payload[commandBodyOffset];
    const size_t commandBodyLen = payloadLen - commandBodyOffset;
    const uint8_t commandLen = commandBody[6];
    if (commandLen > NODE_DOWNLINK_COMMAND_MAX_SIZE) {
        return ServerNodeCommandStatus::CommandTooLong;
    }
    const size_t requiredLen = SERVER_NODE_COMMAND_LEGACY_HEADER_SIZE + commandLen;
    if (commandBodyLen < requiredLen || (out.routed && commandBodyLen != requiredLen)) {
        return ServerNodeCommandStatus::MalformedPayload;
    }

    out.targetNodeId = readServerNodeCommandU16Be(&commandBody[0]);
    out.commandId = readServerNodeCommandU16Be(&commandBody[2]);
    out.ttlSec = readServerNodeCommandU16Be(&commandBody[4]);
    out.commandLen = commandLen;
    out.commandBytes = &commandBody[SERVER_NODE_COMMAND_LEGACY_HEADER_SIZE];
    return ServerNodeCommandStatus::Ok;
}

inline uint16_t serverNodeCommandHopAt(const ServerNodeCommandView& command, uint8_t index) {
    if (!command.routed || command.hopBytes == nullptr || index >= command.hopCount) return 0;
    return readServerNodeCommandU16Be(&command.hopBytes[static_cast<size_t>(index) * 2]);
}

inline int16_t findServerNodeCommandHopIndex(const ServerNodeCommandView& command,
                                             uint16_t chId) {
    if (!command.routed || chId == 0) return -1;
    for (uint8_t i = 0; i < command.hopCount; ++i) {
        if (serverNodeCommandHopAt(command, i) == chId) return static_cast<int16_t>(i);
    }
    return -1;
}

}  // namespace pgl::protocol
