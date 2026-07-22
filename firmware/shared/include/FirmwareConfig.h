#pragma once

#include <cstddef>
#include <cstdint>

#include "ProtocolConstants.h"

namespace pgl::config {

constexpr size_t AES128_KEY_SIZE = 16;
constexpr uint16_t NODE_ID_INVALID = 0x0000;
constexpr uint16_t NODE_ID_SYSTEM_MIN = 0xFF00;

// Operator identity allocation.  Keep device roles visually distinct and
// leave FFxx for protocol/system use.
constexpr uint16_t GATEWAY_ID_MIN = 0x0001;
constexpr uint16_t GATEWAY_ID_MAX = 0x000F;
constexpr uint16_t CH_ID_MIN = 0x0010;
constexpr uint16_t CH_ID_MAX = 0x0FFF;
constexpr uint16_t GLD_ID_MIN = 0x1001;
constexpr uint16_t GLD_ID_MAX = 0xFEFF;

struct AesKeyConfig {
    uint8_t keyId;
    uint8_t key[AES128_KEY_SIZE];
    bool present;
};

struct GldRuntimeConfig {
    uint16_t nodeId;
    uint16_t chId;
    AesKeyConfig aes;
    uint8_t alarmThresholdPercent;
    bool externalPower;
};

struct ChRuntimeConfig {
    uint16_t chId;
    uint16_t meshDstId;
    uint16_t chBatteryMv;
    uint32_t nodeStaleAfterMs;
};

bool isValidNodeId(uint16_t nodeId);
constexpr bool isProvisionableGatewayId(uint16_t nodeId) {
    return nodeId >= GATEWAY_ID_MIN && nodeId <= GATEWAY_ID_MAX;
}

constexpr bool isProvisionableChId(uint16_t nodeId) {
    return nodeId >= CH_ID_MIN && nodeId <= CH_ID_MAX;
}

constexpr bool isProvisionableGldId(uint16_t nodeId) {
    return nodeId >= GLD_ID_MIN && nodeId <= GLD_ID_MAX;
}
bool isValidAesKeyConfig(const AesKeyConfig& config);
bool isValidGldRuntimeConfig(const GldRuntimeConfig& config);
bool isValidChRuntimeConfig(const ChRuntimeConfig& config);

}  // namespace pgl::config
