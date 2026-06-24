#pragma once

#include <cstddef>
#include <cstdint>

#include "ChUplink.h"
#include "ProtocolConstants.h"

namespace pgl::ch {

constexpr size_t CH_NODE_CACHE_PAYLOAD_MAX = pgl::protocol::STAR_MAX_PAYLOAD;
constexpr uint8_t CH_NODE_CACHE_ALLOWED_RECORD_FLAGS =
    pgl::protocol::NC_FLAG_ALARM | pgl::protocol::NC_FLAG_EXT_POWER;

enum class NodeCacheStatus : uint8_t {
    Ok = 0,
    Inserted,
    Updated,
    Duplicate,
    Conflict,
    CacheFull,
    InvalidInput,
    InvalidFlags,
    InvalidPayloadLength,
    NotFound,
};

struct NodeCacheEntry {
    bool used;
    uint16_t nodeId;
    uint8_t currentSeq;
    uint8_t sentSeq;
    uint8_t flags;
    uint32_t lastSeenMs;
    uint32_t lastSentMs;
    uint8_t payloadLen;
    uint8_t payload[CH_NODE_CACHE_PAYLOAD_MAX];
};

struct NodeCacheUpdateResult {
    NodeCacheStatus status;
    size_t index;
    bool shouldAckAlarm;
    bool isNewRecord;
    bool isRecoveryClear;
};

void clearNodeCache(NodeCacheEntry* entries, size_t capacity);
bool isNodeCacheEntryUnsent(const NodeCacheEntry& entry);
bool isNodeCacheEntryAlarm(const NodeCacheEntry& entry);
bool isNodeCacheEntryValidPayload(const NodeCacheEntry& entry);

NodeCacheStatus updateNodeCacheFromUplink(
    NodeCacheEntry* entries,
    size_t capacity,
    const ChGldUplinkView& uplink,
    uint32_t nowMs,
    NodeCacheUpdateResult& out);

NodeCacheStatus markNodeCacheEntrySent(NodeCacheEntry& entry, uint32_t nowMs);
size_t countNodeCacheUnsentNormal(const NodeCacheEntry* entries, size_t capacity);
size_t countNodeCacheUnsentAlarm(const NodeCacheEntry* entries, size_t capacity);

const char* nodeCacheStatusName(NodeCacheStatus status);

}  // namespace pgl::ch
