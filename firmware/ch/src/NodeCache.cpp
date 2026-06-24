#include "NodeCache.h"

#include "GldRecord.h"

namespace pgl::ch {

namespace {

constexpr size_t NODE_CACHE_INDEX_NONE = static_cast<size_t>(-1);

bool isValidFlags(uint8_t flags) {
    return (flags & static_cast<uint8_t>(~CH_NODE_CACHE_ALLOWED_RECORD_FLAGS)) == 0;
}

bool payloadEquals(const NodeCacheEntry& entry, const ChGldUplinkView& uplink, uint8_t flags) {
    if (entry.flags != flags || entry.payloadLen != uplink.encryptedPayloadLen) {
        return false;
    }

    for (uint8_t i = 0; i < entry.payloadLen; ++i) {
        if (entry.payload[i] != uplink.encryptedPayload[i]) {
            return false;
        }
    }
    return true;
}

size_t findEntryIndex(const NodeCacheEntry* entries, size_t capacity, uint16_t nodeId) {
    if (entries == nullptr) {
        return NODE_CACHE_INDEX_NONE;
    }

    for (size_t i = 0; i < capacity; ++i) {
        if (entries[i].used && entries[i].nodeId == nodeId) {
            return i;
        }
    }
    return NODE_CACHE_INDEX_NONE;
}

size_t findFreeIndex(const NodeCacheEntry* entries, size_t capacity) {
    if (entries == nullptr) {
        return NODE_CACHE_INDEX_NONE;
    }

    for (size_t i = 0; i < capacity; ++i) {
        if (!entries[i].used) {
            return i;
        }
    }
    return NODE_CACHE_INDEX_NONE;
}

void copyPayload(NodeCacheEntry& entry, const ChGldUplinkView& uplink) {
    entry.payloadLen = uplink.encryptedPayloadLen;
    for (uint8_t i = 0; i < uplink.encryptedPayloadLen; ++i) {
        entry.payload[i] = uplink.encryptedPayload[i];
    }
}

}  // namespace

void clearNodeCache(NodeCacheEntry* entries, size_t capacity) {
    if (entries == nullptr) {
        return;
    }

    for (size_t i = 0; i < capacity; ++i) {
        entries[i] = {};
    }
}

bool isNodeCacheEntryUnsent(const NodeCacheEntry& entry) {
    return entry.used && entry.currentSeq != entry.sentSeq;
}

bool isNodeCacheEntryAlarm(const NodeCacheEntry& entry) {
    return entry.used && (entry.flags & pgl::protocol::NC_FLAG_ALARM) != 0;
}

bool isNodeCacheEntryValidPayload(const NodeCacheEntry& entry) {
    return entry.used &&
           entry.payloadLen > 0 &&
           entry.payloadLen <= CH_NODE_CACHE_PAYLOAD_MAX &&
           isValidFlags(entry.flags);
}

NodeCacheStatus updateNodeCacheFromUplink(
    NodeCacheEntry* entries,
    size_t capacity,
    const ChGldUplinkView& uplink,
    uint32_t nowMs,
    NodeCacheUpdateResult& out) {
    out = {NodeCacheStatus::InvalidInput, NODE_CACHE_INDEX_NONE, false, false, false};

    if (entries == nullptr || capacity == 0 || uplink.encryptedPayload == nullptr || uplink.nodeId == 0) {
        return NodeCacheStatus::InvalidInput;
    }

    if (uplink.encryptedPayloadLen != pgl::protocol::GLD_ENCRYPTED_PAYLOAD_SIZE ||
        uplink.encryptedPayloadLen > CH_NODE_CACHE_PAYLOAD_MAX) {
        out.status = NodeCacheStatus::InvalidPayloadLength;
        return out.status;
    }

    const uint8_t flags = pgl::protocol::makeRecordFlags(uplink.alarm, uplink.externalPower);
    if (!isValidFlags(flags)) {
        out.status = NodeCacheStatus::InvalidFlags;
        return out.status;
    }

    size_t index = findEntryIndex(entries, capacity, uplink.nodeId);
    const bool inserted = index == NODE_CACHE_INDEX_NONE;
    if (inserted) {
        index = findFreeIndex(entries, capacity);
        if (index == NODE_CACHE_INDEX_NONE) {
            out.status = NodeCacheStatus::CacheFull;
            return out.status;
        }
    }

    NodeCacheEntry& entry = entries[index];
    const bool previousAlarm = isNodeCacheEntryAlarm(entry);

    if (!inserted && uplink.seq == entry.currentSeq) {
        entry.lastSeenMs = nowMs;
        out.index = index;
        if (payloadEquals(entry, uplink, flags)) {
            out.shouldAckAlarm = uplink.alarm;
            out.status = NodeCacheStatus::Duplicate;
            return out.status;
        }
        out.shouldAckAlarm = false;
        out.status = NodeCacheStatus::Conflict;
        return out.status;
    }

    if (inserted) {
        entry = {};
        entry.used = true;
        entry.nodeId = uplink.nodeId;
        entry.sentSeq = static_cast<uint8_t>(uplink.seq - 1);
    }

    entry.currentSeq = uplink.seq;
    entry.flags = flags;
    entry.lastSeenMs = nowMs;
    copyPayload(entry, uplink);

    out.index = index;
    out.shouldAckAlarm = uplink.alarm;
    out.isNewRecord = true;
    out.isRecoveryClear = previousAlarm && !uplink.alarm;
    out.status = inserted ? NodeCacheStatus::Inserted : NodeCacheStatus::Updated;
    return out.status;
}

NodeCacheStatus markNodeCacheEntrySent(NodeCacheEntry& entry, uint32_t nowMs) {
    if (!entry.used) {
        return NodeCacheStatus::NotFound;
    }

    entry.sentSeq = entry.currentSeq;
    entry.lastSentMs = nowMs;
    return NodeCacheStatus::Ok;
}

size_t countNodeCacheUnsentNormal(const NodeCacheEntry* entries, size_t capacity) {
    if (entries == nullptr) {
        return 0;
    }

    size_t count = 0;
    for (size_t i = 0; i < capacity; ++i) {
        if (isNodeCacheEntryValidPayload(entries[i]) &&
            isNodeCacheEntryUnsent(entries[i]) &&
            !isNodeCacheEntryAlarm(entries[i])) {
            ++count;
        }
    }
    return count;
}

size_t countNodeCacheUnsentAlarm(const NodeCacheEntry* entries, size_t capacity) {
    if (entries == nullptr) {
        return 0;
    }

    size_t count = 0;
    for (size_t i = 0; i < capacity; ++i) {
        if (isNodeCacheEntryValidPayload(entries[i]) &&
            isNodeCacheEntryUnsent(entries[i]) &&
            isNodeCacheEntryAlarm(entries[i])) {
            ++count;
        }
    }
    return count;
}

const char* nodeCacheStatusName(NodeCacheStatus status) {
    switch (status) {
        case NodeCacheStatus::Ok:
            return "Ok";
        case NodeCacheStatus::Inserted:
            return "Inserted";
        case NodeCacheStatus::Updated:
            return "Updated";
        case NodeCacheStatus::Duplicate:
            return "Duplicate";
        case NodeCacheStatus::Conflict:
            return "Conflict";
        case NodeCacheStatus::CacheFull:
            return "CacheFull";
        case NodeCacheStatus::InvalidInput:
            return "InvalidInput";
        case NodeCacheStatus::InvalidFlags:
            return "InvalidFlags";
        case NodeCacheStatus::InvalidPayloadLength:
            return "InvalidPayloadLength";
        case NodeCacheStatus::NotFound:
            return "NotFound";
    }
    return "Unknown";
}

}  // namespace pgl::ch
