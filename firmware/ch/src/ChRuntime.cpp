#include "ChRuntime.h"

namespace pgl::ch {

namespace {

bool isAckableAlarmQueueStatus(AlarmQueueStatus status) {
    return status == AlarmQueueStatus::Queued || status == AlarmQueueStatus::AlreadyQueued;
}

struct NodeCacheSnapshot {
    bool existed;
    NodeCacheEntry entry;
};

NodeCacheSnapshot snapshotNodeCacheEntry(
    const NodeCacheEntry* entries,
    size_t capacity,
    uint16_t nodeId) {
    NodeCacheSnapshot snapshot{};
    if (entries == nullptr) {
        return snapshot;
    }

    for (size_t i = 0; i < capacity; ++i) {
        if (entries[i].used && entries[i].nodeId == nodeId) {
            snapshot.existed = true;
            snapshot.entry = entries[i];
            break;
        }
    }
    return snapshot;
}

void restoreNodeCacheEntry(
    NodeCacheEntry* entries,
    size_t capacity,
    size_t updatedIndex,
    const NodeCacheSnapshot& snapshot) {
    if (entries == nullptr || updatedIndex >= capacity) {
        return;
    }
    entries[updatedIndex] = snapshot.existed ? snapshot.entry : NodeCacheEntry{};
}

ChTxQueueStatus enqueueSingleRecordTx(
    const pgl::config::ChRuntimeConfig& config,
    ChTxItem* txQueue,
    size_t txQueueCapacity,
    uint8_t meshSeq,
    const NodeCacheEntry& entry,
    ChTxKind kind) {
    uint8_t frame[CH_TX_FRAME_MAX]{};
    size_t frameSize = 0;
    const ClusterBuildStatus buildStatus = buildSingleRecordSensorPushFrame(
        config.chId,
        config.meshDstId,
        meshSeq,
        entry,
        frame,
        sizeof(frame),
        frameSize);
    if (buildStatus != ClusterBuildStatus::Ok) {
        return ChTxQueueStatus::InvalidInput;
    }

    return enqueueChTxFrame(
        txQueue,
        txQueueCapacity,
        kind,
        entry.nodeId,
        entry.currentSeq,
        nullptr,
        nullptr,
        0,
        frame,
        frameSize);
}

}  // namespace

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
    ChRuntimeProcessResult& out) {
    out = {};
    // Caching a GLD's STAR uplink only needs this CH's own id to be valid -
    // it never touches meshDstId. Whether the CH has joined a MESH parent
    // yet (meshDstId) is a separate, later concern: it only matters for the
    // onward relay checked by canRelayToMesh below, so a CH sitting alone on
    // a bench with no parent still ingests and caches every GLD it hears.
    if (!pgl::config::isValidNodeId(config.chId)) {
        out.status = ChRuntimeStatus::InvalidConfig;
        return out.status;
    }
    const bool canRelayToMesh =
        pgl::config::isValidNodeId(config.meshDstId) && config.chId != config.meshDstId;

    ChGldUplinkView uplink{};
    out.uplinkStatus = parseGldUplinkFrame(frame, frameLen, uplink);
    if (out.uplinkStatus != ChUplinkStatus::Ok) {
        out.status = ChRuntimeStatus::ParseFailed;
        return out.status;
    }

    const NodeCacheSnapshot cacheSnapshot =
        snapshotNodeCacheEntry(cacheEntries, cacheCapacity, uplink.nodeId);
    NodeCacheUpdateResult cacheResult{};
    out.cacheStatus = updateNodeCacheFromUplink(cacheEntries, cacheCapacity, uplink, nowMs, cacheResult);
    if (out.cacheStatus != NodeCacheStatus::Inserted &&
        out.cacheStatus != NodeCacheStatus::Updated &&
        out.cacheStatus != NodeCacheStatus::Duplicate) {
        out.status = ChRuntimeStatus::CacheFailed;
        return out.status;
    }

    NodeCacheEntry& entry = cacheEntries[cacheResult.index];

    if (uplink.alarm && cacheResult.shouldAckAlarm) {
        out.alarmQueueStatus = enqueueAlarmIfAbsent(alarmQueue, alarmQueueCapacity, entry);
        if (out.alarmQueueStatus == AlarmQueueStatus::Full) {
            restoreNodeCacheEntry(cacheEntries, cacheCapacity, cacheResult.index, cacheSnapshot);
            out.status = ChRuntimeStatus::AlarmQueueFull;
            return out.status;
        }
        if (out.alarmQueueStatus == AlarmQueueStatus::Conflict) {
            restoreNodeCacheEntry(cacheEntries, cacheCapacity, cacheResult.index, cacheSnapshot);
            out.status = ChRuntimeStatus::AlarmQueueConflict;
            return out.status;
        }
        if (!isAckableAlarmQueueStatus(out.alarmQueueStatus)) {
            restoreNodeCacheEntry(cacheEntries, cacheCapacity, cacheResult.index, cacheSnapshot);
            out.status = ChRuntimeStatus::CacheFailed;
            return out.status;
        }

        // Only attempt the onward MESH push if this CH has actually joined a
        // parent. Without one there is nowhere to relay to yet, but the STAR
        // ack below still goes out and the alarm stays queued locally so it
        // relays as soon as a parent is found.
        if (out.alarmQueueStatus == AlarmQueueStatus::Queued && canRelayToMesh) {
            out.txQueueStatus = enqueueSingleRecordTx(
                config, txQueue, txQueueCapacity, meshSeq, entry, ChTxKind::AlarmPush);
            if (out.txQueueStatus != ChTxQueueStatus::Ok) {
                removeAlarmQueueItem(
                    alarmQueue, alarmQueueCapacity, entry.nodeId, entry.currentSeq);
                restoreNodeCacheEntry(cacheEntries, cacheCapacity, cacheResult.index, cacheSnapshot);
                out.status = out.txQueueStatus == ChTxQueueStatus::Full
                                 ? ChRuntimeStatus::TxQueueFull
                                 : ChRuntimeStatus::TxBuildFailed;
                return out.status;
            }
            out.onwardQueued = true;
        }

        const ChUplinkStatus ackStatus = buildCompactAlarmAck(
            config.chId,
            uplink.nodeId,
            uplink.seq,
            ackOut,
            ackCapacity,
            out.ackSize);
        if (ackStatus != ChUplinkStatus::Ok) {
            out.status = ChRuntimeStatus::AckBuildFailed;
            return out.status;
        }
        out.ackBuilt = true;
    }

    if (cacheResult.isRecoveryClear && canRelayToMesh) {
        out.txQueueStatus = enqueueSingleRecordTx(
            config, txQueue, txQueueCapacity, meshSeq, entry, ChTxKind::RecoveryClear);
        if (out.txQueueStatus != ChTxQueueStatus::Ok) {
            restoreNodeCacheEntry(cacheEntries, cacheCapacity, cacheResult.index, cacheSnapshot);
            out.status = out.txQueueStatus == ChTxQueueStatus::Full
                             ? ChRuntimeStatus::TxQueueFull
                             : ChRuntimeStatus::TxBuildFailed;
            return out.status;
        }
        out.onwardQueued = true;
        out.recoveryQueued = true;
    }

    out.status = ChRuntimeStatus::Ok;
    return out.status;
}

ChRuntimeStatus enqueueClusterResponseForPull(
    const pgl::config::ChRuntimeConfig& config,
    uint16_t requestId,
    uint8_t meshSeq,
    uint32_t nowMs,
    NodeCacheEntry* cacheEntries,
    size_t cacheCapacity,
    ChTxItem* txQueue,
    size_t txQueueCapacity,
    ChRuntimeProcessResult& out) {
    out = {};
    out.pullRequestId = requestId;
    if (!pgl::config::isValidChRuntimeConfig(config)) {
        out.status = ChRuntimeStatus::InvalidConfig;
        return out.status;
    }

    uint8_t frame[CH_TX_FRAME_MAX]{};
    size_t selectedIndexes[CH_TX_SELECTED_INDEX_MAX]{};
    uint8_t selectedSeqs[CH_TX_SELECTED_INDEX_MAX]{};
    ClusterResponseBuildResult buildResult{};
    const ClusterBuildStatus buildStatus = buildClusterDataResponseFrame(
        config.chId,
        config.meshDstId,
        meshSeq,
        requestId,
        config.chBatteryMv,
        cacheEntries,
        cacheCapacity,
        nowMs,
        config.nodeStaleAfterMs,
        frame,
        sizeof(frame),
        selectedIndexes,
        CH_TX_SELECTED_INDEX_MAX,
        buildResult);
    out.clusterBuildStatus = buildStatus;
    out.clusterDataStatus = buildResult.dataStatus;
    out.clusterRecordCount = buildResult.recordCount;
    out.clusterResponseSize = buildResult.size;
    if (buildStatus != ClusterBuildStatus::Ok) {
        out.status = ChRuntimeStatus::TxBuildFailed;
        return out.status;
    }
    for (size_t i = 0; i < buildResult.recordCount; ++i) {
        selectedSeqs[i] = cacheEntries[selectedIndexes[i]].currentSeq;
    }

    out.txQueueStatus = enqueueChTxFrame(
        txQueue,
        txQueueCapacity,
        ChTxKind::ClusterDataResponse,
        0,
        0,
        selectedIndexes,
        selectedSeqs,
        buildResult.recordCount,
        frame,
        buildResult.size);
    if (out.txQueueStatus != ChTxQueueStatus::Ok) {
        out.status = out.txQueueStatus == ChTxQueueStatus::Full
                         ? ChRuntimeStatus::TxQueueFull
                         : ChRuntimeStatus::TxBuildFailed;
        return out.status;
    }

    out.onwardQueued = true;
    out.status = ChRuntimeStatus::Ok;
    return out.status;
}

ChRuntimeStatus handleServerPullRequestFrame(
    const pgl::config::ChRuntimeConfig& config,
    const uint8_t* frame,
    size_t frameLen,
    uint32_t nowMs,
    NodeCacheEntry* cacheEntries,
    size_t cacheCapacity,
    ChTxItem* txQueue,
    size_t txQueueCapacity,
    ChRuntimeProcessResult& out) {
    out = {};
    if (!pgl::config::isValidChRuntimeConfig(config)) {
        out.status = ChRuntimeStatus::InvalidConfig;
        return out.status;
    }

    ChPullRequestView request{};
    out.pullStatus = parseServerPullRequestFrame(frame, frameLen, config.chId, request);
    out.pullRequestId = request.requestId;
    if (out.pullStatus != ChPullStatus::Ok) {
        out.status = ChRuntimeStatus::PullRequestFailed;
        return out.status;
    }

    return enqueueClusterResponseForPull(
        config,
        request.requestId,
        request.seq,
        nowMs,
        cacheEntries,
        cacheCapacity,
        txQueue,
        txQueueCapacity,
        out);
}

ChRuntimeStatus markChTxSuccess(
    ChTxItem* txQueue,
    size_t txQueueCapacity,
    NodeCacheEntry* cacheEntries,
    size_t cacheCapacity,
    AlarmQueueItem* alarmQueue,
    size_t alarmQueueCapacity,
    uint32_t nowMs) {
    const ChTxItem* item = nullptr;
    const ChTxQueueStatus peekStatus = peekChTxFrame(txQueue, txQueueCapacity, item);
    if (peekStatus != ChTxQueueStatus::Ok || item == nullptr) {
        return ChRuntimeStatus::TxBuildFailed;
    }

    const ChTxItem snapshot = *item;
    // Physical TX has already succeeded, so retire the immutable queue item
    // first. Cache bookkeeping is conditional: a newer GLD sequence may have
    // replaced the snapshot while this item was waiting in the queue.
    if (popChTxFrame(txQueue, txQueueCapacity) != ChTxQueueStatus::Ok) {
        return ChRuntimeStatus::TxBuildFailed;
    }

    const NodeCacheStatus cacheStatus =
        markChTxItemSentInCache(cacheEntries, cacheCapacity, snapshot, nowMs);

    // AlarmPush: TIDAK hapus dari alarmQueue di sini.
    // alarmQueue entry tetap sampai markAlarmAcked() dipanggil saat ACK diterima dari parent.
    return cacheStatus == NodeCacheStatus::Ok || cacheStatus == NodeCacheStatus::NotFound
               ? ChRuntimeStatus::Ok
               : ChRuntimeStatus::CacheFailed;
}

ChRuntimeStatus markAlarmAcked(
    uint16_t nodeId,
    uint8_t seq,
    AlarmQueueItem* alarmQueue,
    size_t alarmQueueCapacity) {
    removeAlarmQueueItem(alarmQueue, alarmQueueCapacity, nodeId, seq);
    return ChRuntimeStatus::Ok;
}

ChRuntimeStatus markChTxFailed(ChTxItem* txQueue, size_t txQueueCapacity) {
    const ChTxItem* item = nullptr;
    const ChTxQueueStatus status = peekChTxFrame(txQueue, txQueueCapacity, item);
    return status == ChTxQueueStatus::Ok ? ChRuntimeStatus::Ok : ChRuntimeStatus::TxBuildFailed;
}

const char* chRuntimeStatusName(ChRuntimeStatus status) {
    switch (status) {
        case ChRuntimeStatus::Ok:
            return "Ok";
        case ChRuntimeStatus::InvalidConfig:
            return "InvalidConfig";
        case ChRuntimeStatus::ParseFailed:
            return "ParseFailed";
        case ChRuntimeStatus::CacheFailed:
            return "CacheFailed";
        case ChRuntimeStatus::AlarmQueueFull:
            return "AlarmQueueFull";
        case ChRuntimeStatus::AlarmQueueConflict:
            return "AlarmQueueConflict";
        case ChRuntimeStatus::AckBuildFailed:
            return "AckBuildFailed";
        case ChRuntimeStatus::TxQueueFull:
            return "TxQueueFull";
        case ChRuntimeStatus::TxBuildFailed:
            return "TxBuildFailed";
        case ChRuntimeStatus::PullRequestFailed:
            return "PullRequestFailed";
    }
    return "Unknown";
}

}  // namespace pgl::ch
