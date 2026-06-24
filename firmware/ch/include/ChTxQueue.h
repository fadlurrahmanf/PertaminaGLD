#pragma once

#include <cstddef>
#include <cstdint>

#include "AppFrame.h"
#include "NodeCache.h"

namespace pgl::ch {

constexpr size_t CH_TX_FRAME_MAX = pgl::protocol::APPFRAME_OVERHEAD + pgl::protocol::MESH_MAX_PAYLOAD;
constexpr size_t CH_TX_SELECTED_INDEX_MAX = 2;

enum class ChTxKind : uint8_t {
    AlarmPush = 0,
    RecoveryClear,
    ClusterDataResponse,
    RelayFrame,
};

enum class ChTxQueueStatus : uint8_t {
    Ok = 0,
    Empty,
    Full,
    InvalidInput,
    OutputTooSmall,
};

struct ChTxItem {
    bool used;
    ChTxKind kind;
    uint16_t nodeId;
    uint8_t gldSeq;
    size_t selectedIndexes[CH_TX_SELECTED_INDEX_MAX];
    uint8_t selectedSeqs[CH_TX_SELECTED_INDEX_MAX];
    size_t selectedCount;
    uint8_t frame[CH_TX_FRAME_MAX];
    size_t frameSize;
};

void clearChTxQueue(ChTxItem* items, size_t capacity);
bool isChTxQueueEmpty(const ChTxItem* items, size_t capacity);
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
    size_t frameSize);
ChTxQueueStatus peekChTxFrame(const ChTxItem* items, size_t capacity, const ChTxItem*& out);
ChTxQueueStatus popChTxFrame(ChTxItem* items, size_t capacity);
NodeCacheStatus markChTxItemSentInCache(NodeCacheEntry* entries, size_t capacity, const ChTxItem& item, uint32_t nowMs);

const char* chTxQueueStatusName(ChTxQueueStatus status);

}  // namespace pgl::ch
