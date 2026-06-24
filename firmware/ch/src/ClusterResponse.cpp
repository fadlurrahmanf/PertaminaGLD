#include "ClusterResponse.h"

#include "GldRecord.h"

namespace pgl::ch {

namespace {

constexpr size_t SELECT_INDEX_NONE = static_cast<size_t>(-1);

void writeU16Be(uint8_t* out, uint16_t value) {
    out[0] = static_cast<uint8_t>((value >> 8) & 0xFF);
    out[1] = static_cast<uint8_t>(value & 0xFF);
}

bool isStale(const NodeCacheEntry& entry, uint32_t nowMs, uint32_t staleAfterMs) {
    return staleAfterMs > 0 && nowMs >= entry.lastSeenMs && (nowMs - entry.lastSeenMs) > staleAfterMs;
}

bool wasSelected(const size_t* selected, size_t count, size_t index) {
    if (selected == nullptr) {
        return false;
    }

    for (size_t i = 0; i < count; ++i) {
        if (selected[i] == index) {
            return true;
        }
    }
    return false;
}

size_t findOldestNormalUnsent(
    const NodeCacheEntry* entries,
    size_t capacity,
    uint32_t nowMs,
    uint32_t staleAfterMs,
    const size_t* selected,
    size_t selectedCount,
    const size_t* skipped,
    size_t skippedCount) {
    size_t best = SELECT_INDEX_NONE;
    uint32_t bestLastSeen = 0;

    for (size_t i = 0; i < capacity; ++i) {
        const NodeCacheEntry& entry = entries[i];
        if (wasSelected(selected, selectedCount, i) ||
            wasSelected(skipped, skippedCount, i) ||
            !isNodeCacheEntryValidPayload(entry) ||
            !isNodeCacheEntryUnsent(entry) ||
            isNodeCacheEntryAlarm(entry) ||
            isStale(entry, nowMs, staleAfterMs)) {
            continue;
        }

        if (best == SELECT_INDEX_NONE || entry.lastSeenMs < bestLastSeen) {
            best = i;
            bestLastSeen = entry.lastSeenMs;
        }
    }

    return best;
}

ClusterDataStatus emptyDataStatus(const NodeCacheEntry* entries, size_t capacity, uint32_t nowMs, uint32_t staleAfterMs) {
    bool hasValid = false;
    bool hasNonStale = false;

    for (size_t i = 0; i < capacity; ++i) {
        if (!isNodeCacheEntryValidPayload(entries[i])) {
            continue;
        }

        hasValid = true;
        if (!isStale(entries[i], nowMs, staleAfterMs)) {
            hasNonStale = true;
        }
    }

    if (!hasValid) {
        return ClusterDataStatus::DataNotAvail;
    }
    if (!hasNonStale) {
        return ClusterDataStatus::DataStale;
    }
    return ClusterDataStatus::DataEmpty;
}

}  // namespace

ClusterBuildStatus buildClusterDataResponsePayload(
    uint16_t requestId,
    uint16_t chBatteryMv,
    const NodeCacheEntry* entries,
    size_t capacity,
    uint32_t nowMs,
    uint32_t staleAfterMs,
    uint8_t* out,
    size_t outCapacity,
    size_t* selectedIndexes,
    size_t selectedCapacity,
    ClusterResponseBuildResult& result,
    size_t maxPayload) {
    result = {ClusterBuildStatus::InvalidInput, ClusterDataStatus::DataInvalid, 0, 0};

    if (entries == nullptr || out == nullptr || outCapacity < pgl::protocol::CLUSTER_DATA_RESPONSE_HEADER_SIZE ||
        maxPayload < pgl::protocol::CLUSTER_DATA_RESPONSE_HEADER_SIZE) {
        return result.status;
    }

    if (outCapacity < maxPayload) {
        result.status = ClusterBuildStatus::OutputTooSmall;
        return result.status;
    }

    if (selectedIndexes != nullptr) {
        for (size_t i = 0; i < selectedCapacity; ++i) {
            selectedIndexes[i] = SELECT_INDEX_NONE;
        }
    }

    writeU16Be(&out[0], requestId);
    out[2] = static_cast<uint8_t>(ClusterDataStatus::DataEmpty);
    writeU16Be(&out[3], chBatteryMv);
    out[5] = 0;

    size_t used = pgl::protocol::CLUSTER_DATA_RESPONSE_HEADER_SIZE;
    size_t selectedCount = 0;
    size_t skippedIndexes[16]{};
    size_t skippedCount = 0;
    for (size_t i = 0; i < sizeof(skippedIndexes) / sizeof(skippedIndexes[0]); ++i) {
        skippedIndexes[i] = SELECT_INDEX_NONE;
    }

    while (true) {
        const size_t index = findOldestNormalUnsent(
            entries,
            capacity,
            nowMs,
            staleAfterMs,
            selectedIndexes,
            selectedCount,
            skippedIndexes,
            skippedCount);
        if (index == SELECT_INDEX_NONE) {
            break;
        }

        const NodeCacheEntry& entry = entries[index];
        const size_t recordSize = pgl::protocol::gldRecordSize(entry.payloadLen);
        if (used + recordSize > maxPayload) {
            if (skippedCount < sizeof(skippedIndexes) / sizeof(skippedIndexes[0])) {
                skippedIndexes[skippedCount++] = index;
                continue;
            }
            break;
        }

        const pgl::protocol::RecordEncodeResult recordResult = pgl::protocol::encodeGldRecord(
            entry.nodeId,
            entry.currentSeq,
            entry.flags,
            entry.payload,
            entry.payloadLen,
            &out[used],
            maxPayload - used);
        if (recordResult.status != pgl::protocol::RecordStatus::Ok) {
            break;
        }

        if (selectedIndexes != nullptr && selectedCount < selectedCapacity) {
            selectedIndexes[selectedCount] = index;
        }
        ++selectedCount;
        used += recordResult.size;
        ++result.recordCount;
    }

    if (result.recordCount > 0) {
        result.dataStatus = ClusterDataStatus::DataOk;
        result.size = used;
    } else {
        result.dataStatus = emptyDataStatus(entries, capacity, nowMs, staleAfterMs);
        result.size = pgl::protocol::CLUSTER_DATA_RESPONSE_HEADER_SIZE;
    }

    out[2] = static_cast<uint8_t>(result.dataStatus);
    out[5] = result.recordCount;
    result.status = ClusterBuildStatus::Ok;
    return result.status;
}

ClusterBuildStatus buildClusterDataResponseFrame(
    uint16_t chId,
    uint16_t dstId,
    uint8_t meshSeq,
    uint16_t requestId,
    uint16_t chBatteryMv,
    const NodeCacheEntry* entries,
    size_t capacity,
    uint32_t nowMs,
    uint32_t staleAfterMs,
    uint8_t* out,
    size_t outCapacity,
    size_t* selectedIndexes,
    size_t selectedCapacity,
    ClusterResponseBuildResult& result) {
    uint8_t payload[pgl::protocol::MESH_MAX_PAYLOAD]{};
    const ClusterBuildStatus payloadStatus = buildClusterDataResponsePayload(
        requestId,
        chBatteryMv,
        entries,
        capacity,
        nowMs,
        staleAfterMs,
        payload,
        sizeof(payload),
        selectedIndexes,
        selectedCapacity,
        result,
        pgl::protocol::MESH_MAX_PAYLOAD);
    if (payloadStatus != ClusterBuildStatus::Ok) {
        return payloadStatus;
    }

    const pgl::protocol::FrameEncodeResult frameResult = pgl::protocol::encodeAppFrame(
        pgl::protocol::MSG_CLUSTER_DATA_RESPONSE,
        chId,
        dstId,
        meshSeq,
        payload,
        static_cast<uint8_t>(result.size),
        out,
        outCapacity,
        pgl::protocol::MESH_MAX_PAYLOAD);
    if (frameResult.status != pgl::protocol::FrameStatus::Ok) {
        result.status = frameResult.status == pgl::protocol::FrameStatus::OutputTooSmall
                            ? ClusterBuildStatus::OutputTooSmall
                            : ClusterBuildStatus::FrameEncodeFailed;
        result.size = 0;
        return result.status;
    }

    result.size = frameResult.size;
    result.status = ClusterBuildStatus::Ok;
    return result.status;
}

ClusterBuildStatus buildSingleRecordSensorPushFrame(
    uint16_t chId,
    uint16_t dstId,
    uint8_t meshSeq,
    const NodeCacheEntry& entry,
    uint8_t* out,
    size_t outCapacity,
    size_t& outSize) {
    outSize = 0;
    if (!isNodeCacheEntryValidPayload(entry) || out == nullptr) {
        return ClusterBuildStatus::InvalidInput;
    }

    uint8_t record[pgl::protocol::GLD_RECORD_PHASE1_SIZE]{};
    const pgl::protocol::RecordEncodeResult recordResult = pgl::protocol::encodeGldRecord(
        entry.nodeId,
        entry.currentSeq,
        entry.flags,
        entry.payload,
        entry.payloadLen,
        record,
        sizeof(record));
    if (recordResult.status != pgl::protocol::RecordStatus::Ok) {
        return ClusterBuildStatus::InvalidInput;
    }

    const uint8_t typeFlags =
        pgl::protocol::MSG_SENSOR_DATA |
        (isNodeCacheEntryAlarm(entry) ? pgl::protocol::FLAG_ALARM_ACK : 0) |
        ((entry.flags & pgl::protocol::NC_FLAG_EXT_POWER) != 0 ? pgl::protocol::FLAG_GLD_EXT_POWER : 0);

    const pgl::protocol::FrameEncodeResult frameResult = pgl::protocol::encodeAppFrame(
        typeFlags,
        chId,
        dstId,
        meshSeq,
        record,
        static_cast<uint8_t>(recordResult.size),
        out,
        outCapacity,
        pgl::protocol::MESH_MAX_PAYLOAD);
    if (frameResult.status != pgl::protocol::FrameStatus::Ok) {
        return frameResult.status == pgl::protocol::FrameStatus::OutputTooSmall
                   ? ClusterBuildStatus::OutputTooSmall
                   : ClusterBuildStatus::FrameEncodeFailed;
    }

    outSize = frameResult.size;
    return ClusterBuildStatus::Ok;
}

NodeCacheStatus markSelectedNodeCacheEntriesSent(
    NodeCacheEntry* entries,
    size_t capacity,
    const size_t* selectedIndexes,
    size_t selectedCount,
    uint32_t nowMs) {
    if (entries == nullptr || selectedIndexes == nullptr) {
        return NodeCacheStatus::InvalidInput;
    }

    for (size_t i = 0; i < selectedCount; ++i) {
        if (selectedIndexes[i] >= capacity) {
            return NodeCacheStatus::InvalidInput;
        }
    }

    for (size_t i = 0; i < selectedCount; ++i) {
        const NodeCacheStatus status = markNodeCacheEntrySent(entries[selectedIndexes[i]], nowMs);
        if (status != NodeCacheStatus::Ok) {
            return status;
        }
    }
    return NodeCacheStatus::Ok;
}

const char* clusterBuildStatusName(ClusterBuildStatus status) {
    switch (status) {
        case ClusterBuildStatus::Ok:
            return "Ok";
        case ClusterBuildStatus::InvalidInput:
            return "InvalidInput";
        case ClusterBuildStatus::OutputTooSmall:
            return "OutputTooSmall";
        case ClusterBuildStatus::FrameEncodeFailed:
            return "FrameEncodeFailed";
    }
    return "Unknown";
}

const char* clusterDataStatusName(ClusterDataStatus status) {
    switch (status) {
        case ClusterDataStatus::DataOk:
            return "DataOk";
        case ClusterDataStatus::DataEmpty:
            return "DataEmpty";
        case ClusterDataStatus::DataNotAvail:
            return "DataNotAvail";
        case ClusterDataStatus::DataStale:
            return "DataStale";
        case ClusterDataStatus::DataBusy:
            return "DataBusy";
        case ClusterDataStatus::DataInvalid:
            return "DataInvalid";
    }
    return "Unknown";
}

}  // namespace pgl::ch
