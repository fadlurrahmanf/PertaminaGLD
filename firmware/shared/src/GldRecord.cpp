#include "GldRecord.h"

namespace pgl::protocol {

namespace {

void writeU16Be(uint8_t* out, uint16_t value) {
    out[0] = static_cast<uint8_t>((value >> 8) & 0xFF);
    out[1] = static_cast<uint8_t>(value & 0xFF);
}

uint16_t readU16Be(const uint8_t* in) {
    return static_cast<uint16_t>((static_cast<uint16_t>(in[0]) << 8) | in[1]);
}

}  // namespace

uint8_t makeRecordFlags(bool alarm, bool externalPower) {
    return static_cast<uint8_t>((alarm ? NC_FLAG_ALARM : 0) |
                                (externalPower ? NC_FLAG_EXT_POWER : 0));
}

RecordEncodeResult encodeGldRecord(
    uint16_t nodeId,
    uint8_t seq,
    uint8_t flags,
    const uint8_t* payload,
    uint8_t payloadLen,
    uint8_t* out,
    size_t outCapacity) {
    if (payloadLen > STAR_MAX_PAYLOAD) {
        return {RecordStatus::PayloadTooLong, 0};
    }

    const size_t totalLen = gldRecordSize(payloadLen);
    if (outCapacity < totalLen) {
        return {RecordStatus::OutputTooSmall, 0};
    }

    writeU16Be(&out[0], nodeId);
    out[2] = seq;
    out[3] = flags;
    out[4] = payloadLen;

    for (uint8_t i = 0; i < payloadLen; ++i) {
        out[GLD_RECORD_HEADER_SIZE + i] = payload[i];
    }

    return {RecordStatus::Ok, totalLen};
}

RecordStatus decodeGldRecord(
    const uint8_t* record,
    size_t recordLen,
    GldRecordView& out) {
    if (recordLen < GLD_RECORD_HEADER_SIZE) {
        return RecordStatus::InputTooSmall;
    }

    const uint8_t payloadLen = record[4];
    if (payloadLen > STAR_MAX_PAYLOAD) {
        return RecordStatus::PayloadTooLong;
    }

    const size_t expectedLen = gldRecordSize(payloadLen);
    if (recordLen != expectedLen) {
        return RecordStatus::LengthMismatch;
    }

    out.nodeId = readU16Be(&record[0]);
    out.seq = record[2];
    out.flags = record[3];
    out.payloadLen = payloadLen;
    out.payload = &record[GLD_RECORD_HEADER_SIZE];

    return RecordStatus::Ok;
}

size_t gldRecordSize(uint8_t payloadLen) {
    return GLD_RECORD_HEADER_SIZE + payloadLen;
}

size_t maxGldRecordsInClusterDataResponse(size_t meshPayloadMax, uint8_t gldPayloadLen) {
    if (meshPayloadMax <= CLUSTER_DATA_RESPONSE_HEADER_SIZE) {
        return 0;
    }

    const size_t recordSize = gldRecordSize(gldPayloadLen);
    if (recordSize == 0) {
        return 0;
    }

    return (meshPayloadMax - CLUSTER_DATA_RESPONSE_HEADER_SIZE) / recordSize;
}

}  // namespace pgl::protocol
