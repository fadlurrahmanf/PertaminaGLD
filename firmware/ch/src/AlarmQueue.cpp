#include "AlarmQueue.h"

namespace pgl::ch {

namespace {

bool payloadEquals(const AlarmQueueItem& item, const NodeCacheEntry& entry) {
    if (item.flags != entry.flags || item.payloadLen != entry.payloadLen) {
        return false;
    }

    for (uint8_t i = 0; i < item.payloadLen; ++i) {
        if (item.payload[i] != entry.payload[i]) {
            return false;
        }
    }
    return true;
}

void copyFromEntry(AlarmQueueItem& item, const NodeCacheEntry& entry) {
    item.used = true;
    item.nodeId = entry.nodeId;
    item.seq = entry.currentSeq;
    item.flags = entry.flags;
    item.payloadLen = entry.payloadLen;
    for (uint8_t i = 0; i < entry.payloadLen; ++i) {
        item.payload[i] = entry.payload[i];
    }
}

}  // namespace

void clearAlarmQueue(AlarmQueueItem* items, size_t capacity) {
    if (items == nullptr) {
        return;
    }
    for (size_t i = 0; i < capacity; ++i) {
        items[i] = {};
    }
}

AlarmQueueStatus enqueueAlarmIfAbsent(
    AlarmQueueItem* items,
    size_t capacity,
    const NodeCacheEntry& entry) {
    if (items == nullptr || capacity == 0 || !isNodeCacheEntryValidPayload(entry)) {
        return AlarmQueueStatus::InvalidInput;
    }
    if (!isNodeCacheEntryAlarm(entry)) {
        return AlarmQueueStatus::NotAlarm;
    }

    for (size_t i = 0; i < capacity; ++i) {
        if (!items[i].used || items[i].nodeId != entry.nodeId || items[i].seq != entry.currentSeq) {
            continue;
        }

        return payloadEquals(items[i], entry) ? AlarmQueueStatus::AlreadyQueued : AlarmQueueStatus::Conflict;
    }

    for (size_t i = 0; i < capacity; ++i) {
        if (!items[i].used) {
            copyFromEntry(items[i], entry);
            return AlarmQueueStatus::Queued;
        }
    }

    return AlarmQueueStatus::Full;
}

AlarmQueueStatus removeAlarmQueueItem(
    AlarmQueueItem* items,
    size_t capacity,
    uint16_t nodeId,
    uint8_t seq) {
    if (items == nullptr) {
        return AlarmQueueStatus::InvalidInput;
    }

    for (size_t i = 0; i < capacity; ++i) {
        if (items[i].used && items[i].nodeId == nodeId && items[i].seq == seq) {
            for (size_t j = i; j + 1 < capacity; ++j) {
                items[j] = items[j + 1];
            }
            items[capacity - 1] = {};
            return AlarmQueueStatus::Ok;
        }
    }
    return AlarmQueueStatus::Empty;
}

bool containsAlarmQueueItem(const AlarmQueueItem* items, size_t capacity, uint16_t nodeId, uint8_t seq) {
    if (items == nullptr) {
        return false;
    }
    for (size_t i = 0; i < capacity; ++i) {
        if (items[i].used && items[i].nodeId == nodeId && items[i].seq == seq) {
            return true;
        }
    }
    return false;
}

const char* alarmQueueStatusName(AlarmQueueStatus status) {
    switch (status) {
        case AlarmQueueStatus::Ok:
            return "Ok";
        case AlarmQueueStatus::Queued:
            return "Queued";
        case AlarmQueueStatus::AlreadyQueued:
            return "AlreadyQueued";
        case AlarmQueueStatus::Conflict:
            return "Conflict";
        case AlarmQueueStatus::Full:
            return "Full";
        case AlarmQueueStatus::Empty:
            return "Empty";
        case AlarmQueueStatus::InvalidInput:
            return "InvalidInput";
        case AlarmQueueStatus::NotAlarm:
            return "NotAlarm";
    }
    return "Unknown";
}

}  // namespace pgl::ch
