#pragma once

#include <cstddef>
#include <cstdint>

#include "AppFrame.h"
#include "NodeCache.h"

namespace pgl::ch {

enum class ClusterBuildStatus : uint8_t {
    Ok = 0,
    InvalidInput,
    OutputTooSmall,
    FrameEncodeFailed,
};

enum class ClusterDataStatus : uint8_t {
    DataOk = 0x00,
    DataEmpty = 0x01,
    DataNotAvail = 0x02,
    DataStale = 0x03,
    DataBusy = 0x04,
    DataInvalid = 0x05,
};

struct ClusterResponseBuildResult {
    ClusterBuildStatus status;
    ClusterDataStatus dataStatus;
    size_t size;
    uint8_t recordCount;
};

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
    size_t maxPayload = pgl::protocol::MESH_MAX_PAYLOAD);

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
    ClusterResponseBuildResult& result);

ClusterBuildStatus buildSingleRecordSensorPushFrame(
    uint16_t chId,
    uint16_t dstId,
    uint8_t meshSeq,
    const NodeCacheEntry& entry,
    uint8_t* out,
    size_t outCapacity,
    size_t& outSize);

NodeCacheStatus markSelectedNodeCacheEntriesSent(
    NodeCacheEntry* entries,
    size_t capacity,
    const size_t* selectedIndexes,
    size_t selectedCount,
    uint32_t nowMs);

const char* clusterBuildStatusName(ClusterBuildStatus status);
const char* clusterDataStatusName(ClusterDataStatus status);

}  // namespace pgl::ch
