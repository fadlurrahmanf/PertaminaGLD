#pragma once

#include <cstddef>
#include <cstdint>

#include "ProtocolConstants.h"

namespace pgl::protocol {

enum class RecordStatus : uint8_t {
    Ok = 0,
    OutputTooSmall,
    InputTooSmall,
    PayloadTooLong,
    LengthMismatch,
};

struct RecordEncodeResult {
    RecordStatus status;
    size_t size;
};

struct GldRecordView {
    uint16_t nodeId;
    uint8_t seq;
    uint8_t flags;
    uint8_t payloadLen;
    const uint8_t* payload;
};

uint8_t makeRecordFlags(bool alarm, bool externalPower);

RecordEncodeResult encodeGldRecord(
    uint16_t nodeId,
    uint8_t seq,
    uint8_t flags,
    const uint8_t* payload,
    uint8_t payloadLen,
    uint8_t* out,
    size_t outCapacity);

RecordStatus decodeGldRecord(
    const uint8_t* record,
    size_t recordLen,
    GldRecordView& out);

size_t gldRecordSize(uint8_t payloadLen);
size_t maxGldRecordsInClusterDataResponse(size_t meshPayloadMax, uint8_t gldPayloadLen);

}  // namespace pgl::protocol
