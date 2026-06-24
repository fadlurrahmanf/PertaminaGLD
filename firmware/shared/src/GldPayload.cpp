#include "GldPayload.h"

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

bool isValidGasClass(uint8_t gasClass) {
    return gasClass <= GLD_GAS_ANOMALY;
}

bool isValidConfidence(uint8_t confidence) {
    return confidence <= 100;
}

bool isGldAlarm(uint8_t gasClass, uint8_t confidence, uint8_t threshold) {
    return gasClass != GLD_GAS_CLEAR && confidence >= threshold;
}

bool encodeGldPlainPayload(const GldPlainPayload& payload, uint8_t out[GLD_PLAINTEXT_PAYLOAD_SIZE]) {
    if (!isValidGasClass(payload.gasClass) || !isValidConfidence(payload.confidence)) {
        return false;
    }

    out[0] = payload.gasClass;
    out[1] = payload.confidence;
    writeU16Be(&out[2], payload.batteryMv);
    return true;
}

bool decodeGldPlainPayload(const uint8_t in[GLD_PLAINTEXT_PAYLOAD_SIZE], GldPlainPayload& out) {
    out.gasClass = in[0];
    out.confidence = in[1];
    out.batteryMv = readU16Be(&in[2]);

    return isValidGasClass(out.gasClass) && isValidConfidence(out.confidence);
}

void buildGldAad(
    uint16_t nodeId,
    uint8_t gldSeq,
    uint8_t recordFlags,
    uint8_t keyId,
    uint8_t out[GLD_AAD_SIZE]) {
    writeU16Be(&out[0], nodeId);
    out[2] = gldSeq;
    out[3] = recordFlags;
    out[4] = keyId;
}

}  // namespace pgl::protocol
