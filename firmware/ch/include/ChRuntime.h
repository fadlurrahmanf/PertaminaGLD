#pragma once

#include <cstddef>
#include <cstdint>

#include "AlarmQueue.h"
#include "ChPullRequest.h"
#include "ChTxQueue.h"
#include "ClusterResponse.h"
#include "FirmwareConfig.h"

namespace pgl::ch {

enum class ChRuntimeStatus : uint8_t {
    Ok = 0,
    InvalidConfig,
    ParseFailed,
    CacheFailed,
    AlarmQueueFull,
    AlarmQueueConflict,
    AckBuildFailed,
    TxQueueFull,
    TxBuildFailed,
    PullRequestFailed,
};

struct ChRuntimeProcessResult {
    ChRuntimeStatus status;
    ChUplinkStatus uplinkStatus;
    ChPullStatus pullStatus;
    NodeCacheStatus cacheStatus;
    AlarmQueueStatus alarmQueueStatus;
    ChTxQueueStatus txQueueStatus;
    bool ackBuilt;
    size_t ackSize;
    bool onwardQueued;
    bool recoveryQueued;
};

ChRuntimeStatus processGldStarFrame(
    const pgl::config::ChRuntimeConfig& config,
    const uint8_t* frame,
    size_t frameLen,
    uint32_t nowMs,
    uint8_t meshSeq,
    NodeCacheEntry* cacheEntries,
    size_t cacheCapacity,
    AlarmQueueItem* alarmQueue,
    size_t alarmQueueCapacity,
    ChTxItem* txQueue,
    size_t txQueueCapacity,
    uint8_t* ackOut,
    size_t ackCapacity,
    ChRuntimeProcessResult& out);

ChRuntimeStatus enqueueClusterResponseForPull(
    const pgl::config::ChRuntimeConfig& config,
    uint16_t requestId,
    uint8_t meshSeq,
    uint32_t nowMs,
    NodeCacheEntry* cacheEntries,
    size_t cacheCapacity,
    ChTxItem* txQueue,
    size_t txQueueCapacity,
    ChRuntimeProcessResult& out);

ChRuntimeStatus handleServerPullRequestFrame(
    const pgl::config::ChRuntimeConfig& config,
    const uint8_t* frame,
    size_t frameLen,
    uint32_t nowMs,
    NodeCacheEntry* cacheEntries,
    size_t cacheCapacity,
    ChTxItem* txQueue,
    size_t txQueueCapacity,
    ChRuntimeProcessResult& out);

ChRuntimeStatus markChTxSuccess(
    ChTxItem* txQueue,
    size_t txQueueCapacity,
    NodeCacheEntry* cacheEntries,
    size_t cacheCapacity,
    AlarmQueueItem* alarmQueue,
    size_t alarmQueueCapacity,
    uint32_t nowMs);

ChRuntimeStatus markChTxFailed(ChTxItem* txQueue, size_t txQueueCapacity);

// Hapus alarm dari alarmQueue saat ACK diterima dari parent.
// Dipanggil oleh main ketika menerima FLAG_ALARM_ACK dari MESH parent.
ChRuntimeStatus markAlarmAcked(
    uint16_t nodeId,
    uint8_t seq,
    AlarmQueueItem* alarmQueue,
    size_t alarmQueueCapacity);

const char* chRuntimeStatusName(ChRuntimeStatus status);

}  // namespace pgl::ch
