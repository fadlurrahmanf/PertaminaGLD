#include "ChUplink.h"

namespace pgl::ch {

namespace {

bool isAllowedGldSensorTypeFlags(uint8_t typeFlags) {
    using namespace pgl::protocol;
    return typeFlags == TYPE_GLD_NORMAL_BATTERY ||
           typeFlags == TYPE_GLD_ALARM_BATTERY ||
           typeFlags == TYPE_GLD_NORMAL_EXTERNAL ||
           typeFlags == TYPE_GLD_ALARM_EXTERNAL;
}

}  // namespace

ChUplinkStatus parseGldUplinkFrame(
    const uint8_t* frame,
    size_t frameLen,
    ChGldUplinkView& out) {
    using namespace pgl::protocol;

    FrameView decoded{};
    const FrameStatus frameStatus = decodeAppFrame(frame, frameLen, decoded, STAR_MAX_PAYLOAD);
    if (frameStatus != FrameStatus::Ok) {
        return ChUplinkStatus::BadFrame;
    }

    if (messageType(decoded.typeFlags) != MSG_SENSOR_DATA) {
        return ChUplinkStatus::NotSensorData;
    }

    if (!isAllowedGldSensorTypeFlags(decoded.typeFlags)) {
        return ChUplinkStatus::InvalidTypeFlags;
    }

    if (decoded.payloadLen != GLD_ENCRYPTED_PAYLOAD_SIZE) {
        return ChUplinkStatus::InvalidPayloadLength;
    }

    out.nodeId = decoded.srcId;
    out.chId = decoded.dstId;
    out.seq = decoded.seq;
    out.typeFlags = decoded.typeFlags;
    out.alarm = hasAlarmAckFlag(decoded.typeFlags);
    out.externalPower = hasGldExternalPowerFlag(decoded.typeFlags);
    out.encryptedPayload = decoded.payload;
    out.encryptedPayloadLen = decoded.payloadLen;
    return ChUplinkStatus::Ok;
}

ChUplinkStatus buildCompactAlarmAck(
    uint16_t chId,
    uint16_t nodeId,
    uint8_t seq,
    uint8_t* out,
    size_t outCapacity,
    size_t& outSize) {
    using namespace pgl::protocol;

    const FrameEncodeResult result = encodeAppFrame(
        TYPE_ALARM_ACK_COMPACT,
        chId,
        nodeId,
        seq,
        nullptr,
        0,
        out,
        outCapacity,
        STAR_MAX_PAYLOAD);

    if (result.status == FrameStatus::OutputTooSmall) {
        return ChUplinkStatus::OutputTooSmall;
    }
    if (result.status != FrameStatus::Ok) {
        return ChUplinkStatus::BadFrame;
    }

    outSize = result.size;
    return ChUplinkStatus::Ok;
}

const char* chUplinkStatusName(ChUplinkStatus status) {
    switch (status) {
        case ChUplinkStatus::Ok:
            return "Ok";
        case ChUplinkStatus::BadFrame:
            return "BadFrame";
        case ChUplinkStatus::NotSensorData:
            return "NotSensorData";
        case ChUplinkStatus::InvalidTypeFlags:
            return "InvalidTypeFlags";
        case ChUplinkStatus::InvalidPayloadLength:
            return "InvalidPayloadLength";
        case ChUplinkStatus::OutputTooSmall:
            return "OutputTooSmall";
    }
    return "Unknown";
}

}  // namespace pgl::ch
