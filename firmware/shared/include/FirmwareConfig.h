#pragma once

#include <cstddef>
#include <cstdint>

#include "ProtocolConstants.h"

namespace pgl::config {

constexpr size_t AES128_KEY_SIZE = 16;
constexpr uint16_t NODE_ID_INVALID = 0x0000;
constexpr uint16_t NODE_ID_SYSTEM_MIN = 0xFF00;

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
bool isValidAesKeyConfig(const AesKeyConfig& config);
bool isValidGldRuntimeConfig(const GldRuntimeConfig& config);
bool isValidChRuntimeConfig(const ChRuntimeConfig& config);

}  // namespace pgl::config
