#include "AppFrame.h"

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

uint16_t crc16CcittFalse(const uint8_t* data, size_t len) {
    uint16_t crc = 0xFFFF;

    for (size_t i = 0; i < len; ++i) {
        crc ^= static_cast<uint16_t>(data[i]) << 8;
        for (uint8_t bit = 0; bit < 8; ++bit) {
            if ((crc & 0x8000) != 0) {
                crc = static_cast<uint16_t>((crc << 1) ^ 0x1021);
            } else {
                crc = static_cast<uint16_t>(crc << 1);
            }
        }
    }

    return crc;
}

FrameEncodeResult encodeAppFrame(
    uint8_t typeFlags,
    uint16_t srcId,
    uint16_t dstId,
    uint8_t seq,
    const uint8_t* payload,
    uint8_t payloadLen,
    uint8_t* out,
    size_t outCapacity,
    uint8_t maxPayload) {
    if (payloadLen > maxPayload) {
        return {FrameStatus::PayloadTooLong, 0};
    }

    const size_t totalLen = APPFRAME_OVERHEAD + payloadLen;
    if (outCapacity < totalLen) {
        return {FrameStatus::OutputTooSmall, 0};
    }

    out[0] = APPFRAME_MAGIC;
    out[1] = typeFlags;
    writeU16Be(&out[2], srcId);
    writeU16Be(&out[4], dstId);
    out[6] = seq;
    out[7] = payloadLen;

    for (uint8_t i = 0; i < payloadLen; ++i) {
        out[APPFRAME_HEADER_SIZE + i] = payload[i];
    }

    const uint16_t crc = crc16CcittFalse(out, APPFRAME_HEADER_SIZE + payloadLen);
    writeU16Be(&out[APPFRAME_HEADER_SIZE + payloadLen], crc);

    return {FrameStatus::Ok, totalLen};
}

FrameStatus decodeAppFrame(
    const uint8_t* frame,
    size_t frameLen,
    FrameView& out,
    uint8_t maxPayload) {
    if (frameLen < APPFRAME_OVERHEAD) {
        return FrameStatus::InputTooSmall;
    }

    if (frame[0] != APPFRAME_MAGIC) {
        return FrameStatus::BadMagic;
    }

    const uint8_t payloadLen = frame[7];
    if (payloadLen > maxPayload) {
        return FrameStatus::PayloadTooLong;
    }

    const size_t expectedLen = APPFRAME_OVERHEAD + payloadLen;
    if (frameLen != expectedLen) {
        return FrameStatus::LengthMismatch;
    }

    const uint16_t expectedCrc = crc16CcittFalse(frame, APPFRAME_HEADER_SIZE + payloadLen);
    const uint16_t actualCrc = readU16Be(&frame[APPFRAME_HEADER_SIZE + payloadLen]);
    if (expectedCrc != actualCrc) {
        return FrameStatus::BadCrc;
    }

    out.typeFlags = frame[1];
    out.srcId = readU16Be(&frame[2]);
    out.dstId = readU16Be(&frame[4]);
    out.seq = frame[6];
    out.payloadLen = payloadLen;
    out.payload = &frame[APPFRAME_HEADER_SIZE];

    return FrameStatus::Ok;
}

}  // namespace pgl::protocol
