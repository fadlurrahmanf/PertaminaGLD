#pragma once

#include <cstddef>
#include <cstdint>

#include "ProtocolConstants.h"

namespace pgl::protocol {

enum class FrameStatus : uint8_t {
    Ok = 0,
    OutputTooSmall,
    InputTooSmall,
    BadMagic,
    PayloadTooLong,
    LengthMismatch,
    BadCrc,
};

struct FrameEncodeResult {
    FrameStatus status;
    size_t size;
};

struct FrameView {
    uint8_t typeFlags;
    uint16_t srcId;
    uint16_t dstId;
    uint8_t seq;
    uint8_t payloadLen;
    const uint8_t* payload;
};

uint16_t crc16CcittFalse(const uint8_t* data, size_t len);

FrameEncodeResult encodeAppFrame(
    uint8_t typeFlags,
    uint16_t srcId,
    uint16_t dstId,
    uint8_t seq,
    const uint8_t* payload,
    uint8_t payloadLen,
    uint8_t* out,
    size_t outCapacity,
    uint8_t maxPayload = STAR_MAX_PAYLOAD);

FrameStatus decodeAppFrame(
    const uint8_t* frame,
    size_t frameLen,
    FrameView& out,
    uint8_t maxPayload = STAR_MAX_PAYLOAD);

}  // namespace pgl::protocol
