#include "FirmwareConfig.h"

namespace pgl::config {

bool isValidNodeId(uint16_t nodeId) {
    return nodeId != NODE_ID_INVALID && nodeId < NODE_ID_SYSTEM_MIN;
}

bool isValidAesKeyConfig(const AesKeyConfig& config) {
    return config.present && config.keyId != 0;
}

bool isValidGldRuntimeConfig(const GldRuntimeConfig& config) {
    return isValidNodeId(config.nodeId) &&
           isValidNodeId(config.chId) &&
           config.nodeId != config.chId &&
           isValidAesKeyConfig(config.aes) &&
           config.alarmThresholdPercent <= 100;
}

bool isValidChRuntimeConfig(const ChRuntimeConfig& config) {
    return isValidNodeId(config.chId) &&
           isValidNodeId(config.meshDstId) &&
           config.chId != config.meshDstId;
}

}  // namespace pgl::config
