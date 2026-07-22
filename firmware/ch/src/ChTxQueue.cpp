#include "ChTxQueue.h"

namespace pgl::ch {

namespace {

void copyTxFrame(ChTxItem& item, const uint8_t* frame, size_t frameSize) {
    item.frameSize = frameSize;
    for (size_t i = 0; i < frameSize; ++i) {
        item.frame[i] = frame[i];
    }
}

size_t firstUsedIndex(const ChTxItem* items, size_t capacity) {
    for (size_t i = 0; i < capacity; ++i) {
        if (items[i].used) {
            return i;
        }
    }
    return static_cast<size_t>(-1);
}

}  // namespace

void clearChTxQueue(ChTxItem* items, size_t capacity) {
    if (items == nullptr) {
        return;
    }
    for (size_t i = 0; i < capacity; ++i) {
        items[i] = {};
    }
}

bool isChTxQueueEmpty(const ChTxItem* items, size_t capacity) {
    if (items == nullptr) {
        return true;
    }
    return firstUsedIndex(items, capacity) == static_cast<size_t>(-1);
}

ChTxQueueStatus enqueueChTxFrame(
    ChTxItem* items,
    size_t capacity,
    ChTxKind kind,
    uint16_t nodeId,
    uint8_t gldSeq,
    const size_t* selectedIndexes,
    const uint8_t* selectedSeqs,
    size_t selectedCount,
    const uint8_t* frame,
    size_t frameSize) {
    if (items == nullptr || capacity == 0 || frame == nullptr || frameSize == 0) {
        return ChTxQueueStatus::InvalidInput;
    }
    if (frameSize > CH_TX_FRAME_MAX || selectedCount > CH_TX_SELECTED_INDEX_MAX) {
        return ChTxQueueStatus::OutputTooSmall;
    }

    for (size_t i = 0; i < capacity; ++i) {
        if (items[i].used) {
            continue;
        }

        items[i] = {};
        items[i].used = true;
        items[i].kind = kind;
        items[i].nodeId = nodeId;
        items[i].gldSeq = gldSeq;
        items[i].selectedCount = selectedCount;
        for (size_t j = 0; j < selectedCount; ++j) {
            items[i].selectedIndexes[j] = selectedIndexes == nullptr ? static_cast<size_t>(-1) : selectedIndexes[j];
            items[i].selectedSeqs[j] = selectedSeqs == nullptr ? 0 : selectedSeqs[j];
        }
        copyTxFrame(items[i], frame, frameSize);
        return ChTxQueueStatus::Ok;
    }

    return ChTxQueueStatus::Full;
}

ChTxQueueStatus peekChTxFrame(const ChTxItem* items, size_t capacity, const ChTxItem*& out) {
    out = nullptr;
    if (items == nullptr) {
        return ChTxQueueStatus::InvalidInput;
    }

    const size_t index = firstUsedIndex(items, capacity);
    if (index == static_cast<size_t>(-1)) {
        return ChTxQueueStatus::Empty;
    }
    out = &items[index];
    return ChTxQueueStatus::Ok;
}

ChTxQueueStatus popChTxFrame(ChTxItem* items, size_t capacity) {
    if (items == nullptr) {
        return ChTxQueueStatus::InvalidInput;
    }

    const size_t index = firstUsedIndex(items, capacity);
    if (index == static_cast<size_t>(-1)) {
        return ChTxQueueStatus::Empty;
    }

    for (size_t i = index; i + 1 < capacity; ++i) {
        items[i] = items[i + 1];
    }
    items[capacity - 1] = {};
    return ChTxQueueStatus::Ok;
}

NodeCacheStatus markChTxItemSentInCache(NodeCacheEntry* entries, size_t capacity, const ChTxItem& item, uint32_t nowMs) {
    if (entries == nullptr) {
        return NodeCacheStatus::InvalidInput;
    }

    if (item.kind == ChTxKind::ClusterDataResponse) {
        for (size_t i = 0; i < item.selectedCount; ++i) {
            if (item.selectedIndexes[i] >= capacity) {
                return NodeCacheStatus::InvalidInput;
            }

            NodeCacheEntry& entry = entries[item.selectedIndexes[i]];
            if (!entry.used || entry.currentSeq != item.selectedSeqs[i]) {
                // The response carried an older immutable snapshot. Do not
                // mark the newer cache value sent, but do not fail retirement
                // of the response that was successfully transmitted either.
                continue;
            }

            const NodeCacheStatus status = markNodeCacheEntrySent(entry, nowMs);
            if (status != NodeCacheStatus::Ok) {
                return status;
            }
        }
        return NodeCacheStatus::Ok;
    }

    if (item.kind == ChTxKind::RelayFrame) {
        return NodeCacheStatus::Ok;
    }

    for (size_t i = 0; i < capacity; ++i) {
        if (entries[i].used && entries[i].nodeId == item.nodeId && entries[i].currentSeq == item.gldSeq) {
            return markNodeCacheEntrySent(entries[i], nowMs);
        }
    }
    return NodeCacheStatus::NotFound;
}

const char* chTxQueueStatusName(ChTxQueueStatus status) {
    switch (status) {
        case ChTxQueueStatus::Ok:
            return "Ok";
        case ChTxQueueStatus::Empty:
            return "Empty";
        case ChTxQueueStatus::Full:
            return "Full";
        case ChTxQueueStatus::InvalidInput:
            return "InvalidInput";
        case ChTxQueueStatus::OutputTooSmall:
            return "OutputTooSmall";
    }
    return "Unknown";
}

}  // namespace pgl::ch
