#pragma once

#include <cstddef>
#include <cstdint>

#include "AppFrame.h"
#include "GldCrypto.h"
#include "GldPayload.h"
#include "ProtocolConstants.h"

namespace pgl::gld {

using GldNonceProvider = bool (*)(uint8_t nonce[pgl::protocol::GLD_AES_GCM_NONCE_SIZE], void* context);

enum class GldFrameStatus : uint8_t {
    Ok = 0,
    InvalidConfig,
    InvalidInput,
    NonceFailed,
    CryptoFailed,
    FrameEncodeFailed,
};

struct GldFrameBuilderConfig {
    uint16_t nodeId;
    uint16_t chId;
    uint8_t keyId;
    const uint8_t* aesKey;
    bool externalPower;
    uint8_t alarmThreshold;
};

struct GldFrameBuildInput {
    uint8_t gasClass;
    uint8_t confidence;
    uint16_t batteryMv;
    uint8_t seq;
};

struct GldBuiltFrame {
    bool alarm;
    uint8_t typeFlags;
    uint8_t recordFlags;
    pgl::protocol::GldEncryptedPayload encrypted;
    size_t size;
    uint8_t bytes[pgl::protocol::APPFRAME_OVERHEAD + pgl::protocol::GLD_ENCRYPTED_PAYLOAD_SIZE];
};

GldFrameStatus buildGldUplinkFrame(
    const GldFrameBuilderConfig& config,
    const GldFrameBuildInput& input,
    GldNonceProvider nonceProvider,
    void* nonceContext,
    GldBuiltFrame& out);

const char* gldFrameStatusName(GldFrameStatus status);

}  // namespace pgl::gld
