#include "ChPullRequest.h"

#include "ProtocolConstants.h"

namespace pgl::ch {

namespace {

uint16_t readU16Be(const uint8_t* in) {
    return static_cast<uint16_t>((static_cast<uint16_t>(in[0]) << 8) | in[1]);
}

}  // namespace

ChPullStatus parseServerPullRequestFrame(
    const uint8_t* frame,
    size_t frameLen,
    uint16_t localChId,
    ChPullRequestView& out) {
    pgl::protocol::FrameView decoded{};
    const pgl::protocol::FrameStatus frameStatus =
        pgl::protocol::decodeAppFrame(frame, frameLen, decoded, pgl::protocol::MESH_MAX_PAYLOAD);
    if (frameStatus != pgl::protocol::FrameStatus::Ok) {
        return ChPullStatus::BadFrame;
    }

    if (pgl::protocol::messageType(decoded.typeFlags) != pgl::protocol::MSG_SERVER_PULL_REQUEST) {
        return ChPullStatus::NotPullRequest;
    }

    if (decoded.dstId != localChId) {
        return ChPullStatus::WrongHop;
    }

    if (decoded.payloadLen < 4 || ((decoded.payloadLen - 2) % 2) != 0) {
        return ChPullStatus::InvalidPayloadLength;
    }

    const uint8_t hopCount = static_cast<uint8_t>((decoded.payloadLen - 2) / 2);
    if (hopCount == 0) {
        return ChPullStatus::InvalidPayloadLength;
    }

    bool localIsFinalHop = false;
    for (uint8_t i = 0; i < hopCount; ++i) {
        const uint16_t hop = readU16Be(&decoded.payload[2 + (i * 2)]);
        if (hop == localChId) {
            localIsFinalHop = (i == static_cast<uint8_t>(hopCount - 1));
            break;
        }
    }
    if (!localIsFinalHop) {
        return ChPullStatus::UnsupportedHopCount;
    }

    out.srcId = decoded.srcId;
    out.dstId = decoded.dstId;
    out.seq = decoded.seq;
    out.requestId = readU16Be(&decoded.payload[0]);
    out.hopCount = hopCount;
    out.hopListBytes = &decoded.payload[2];
    return ChPullStatus::Ok;
}

const char* chPullStatusName(ChPullStatus status) {
    switch (status) {
        case ChPullStatus::Ok:
            return "Ok";
        case ChPullStatus::BadFrame:
            return "BadFrame";
        case ChPullStatus::NotPullRequest:
            return "NotPullRequest";
        case ChPullStatus::InvalidPayloadLength:
            return "InvalidPayloadLength";
        case ChPullStatus::WrongHop:
            return "WrongHop";
        case ChPullStatus::UnsupportedHopCount:
            return "UnsupportedHopCount";
    }
    return "Unknown";
}

}  // namespace pgl::ch
