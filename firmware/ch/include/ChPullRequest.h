#pragma once

#include <cstddef>
#include <cstdint>

#include "AppFrame.h"

namespace pgl::ch {

enum class ChPullStatus : uint8_t {
    Ok = 0,
    BadFrame,
    NotPullRequest,
    InvalidPayloadLength,
    WrongHop,
    UnsupportedHopCount,
};

struct ChPullRequestView {
    uint16_t srcId;
    uint16_t dstId;
    uint8_t seq;
    uint16_t requestId;
    uint8_t hopCount;
    const uint8_t* hopListBytes;
};

ChPullStatus parseServerPullRequestFrame(
    const uint8_t* frame,
    size_t frameLen,
    uint16_t localChId,
    ChPullRequestView& out);

const char* chPullStatusName(ChPullStatus status);

}  // namespace pgl::ch
