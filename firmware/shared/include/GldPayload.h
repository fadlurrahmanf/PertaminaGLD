#pragma once

#include <cstddef>
#include <cstdint>

#include "ProtocolConstants.h"

namespace pgl::protocol {

struct GldPlainPayload {
    uint8_t gasClass;
    uint8_t confidence;
    uint16_t batteryMv;
};

bool isValidGasClass(uint8_t gasClass);
bool isValidConfidence(uint8_t confidence);
bool isGldAlarm(uint8_t gasClass, uint8_t confidence, uint8_t threshold = GLD_LEL_THRESHOLD_PERCENT);

bool encodeGldPlainPayload(const GldPlainPayload& payload, uint8_t out[GLD_PLAINTEXT_PAYLOAD_SIZE]);
bool decodeGldPlainPayload(const uint8_t in[GLD_PLAINTEXT_PAYLOAD_SIZE], GldPlainPayload& out);

void buildGldAad(
    uint16_t nodeId,
    uint8_t gldSeq,
    uint8_t recordFlags,
    uint8_t keyId,
    uint8_t out[GLD_AAD_SIZE]);

}  // namespace pgl::protocol
