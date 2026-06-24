#pragma once

#include <cstddef>
#include <cstdint>

#include "NodeCache.h"

namespace pgl::ch {

enum class AlarmQueueStatus : uint8_t {
    Ok = 0,
    Queued,
    AlreadyQueued,
    Conflict,
    Full,
    Empty,
    InvalidInput,
    NotAlarm,
};

struct AlarmQueueItem {
    bool used;
    uint16_t nodeId;
    uint8_t seq;
    uint8_t flags;
    uint8_t payloadLen;
    uint8_t payload[CH_NODE_CACHE_PAYLOAD_MAX];
};

void clearAlarmQueue(AlarmQueueItem* items, size_t capacity);
AlarmQueueStatus enqueueAlarmIfAbsent(
    AlarmQueueItem* items,
    size_t capacity,
    const NodeCacheEntry& entry);
AlarmQueueStatus removeAlarmQueueItem(
    AlarmQueueItem* items,
    size_t capacity,
    uint16_t nodeId,
    uint8_t seq);
bool containsAlarmQueueItem(const AlarmQueueItem* items, size_t capacity, uint16_t nodeId, uint8_t seq);

const char* alarmQueueStatusName(AlarmQueueStatus status);

}  // namespace pgl::ch
