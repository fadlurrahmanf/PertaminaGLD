#pragma once

#include <cstddef>
#include <cstdint>

#include "AppFrame.h"
#include "ProtocolConstants.h"

namespace pgl::ch {

enum class ChUplinkStatus : uint8_t {
    Ok = 0,
    BadFrame,
    NotSensorData,
    InvalidTypeFlags,
    InvalidPayloadLength,
    OutputTooSmall,
};

struct ChGldUplinkView {
    uint16_t nodeId;
    uint16_t chId;
    uint8_t seq;
    uint8_t typeFlags;
    bool alarm;
    bool externalPower;
    const uint8_t* encryptedPayload;
    uint8_t encryptedPayloadLen;
};

ChUplinkStatus parseGldUplinkFrame(
    const uint8_t* frame,
    size_t frameLen,
    ChGldUplinkView& out);

ChUplinkStatus buildCompactAlarmAck(
    uint16_t chId,
    uint16_t nodeId,
    uint8_t seq,
    uint8_t* out,
    size_t outCapacity,
    size_t& outSize);

const char* chUplinkStatusName(ChUplinkStatus status);

}  // namespace pgl::ch
