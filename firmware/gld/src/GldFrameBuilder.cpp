#include "GldFrameBuilder.h"

#include "GldRecord.h"

namespace pgl::gld {

namespace {

bool isValidConfig(const GldFrameBuilderConfig& config) {
    return config.nodeId != 0 &&
           config.chId != 0 &&
           config.keyId != 0 &&
           config.aesKey != nullptr &&
           config.alarmThreshold <= 100;
}

bool isValidInput(const GldFrameBuildInput& input) {
    return pgl::protocol::isValidGasClass(input.gasClass) &&
           pgl::protocol::isValidConfidence(input.confidence);
}

void clearBuiltFrame(GldBuiltFrame& frame) {
    frame.alarm = false;
    frame.typeFlags = 0;
    frame.recordFlags = 0;
    frame.encrypted = {};
    frame.size = 0;
    for (size_t i = 0; i < sizeof(frame.bytes); ++i) {
        frame.bytes[i] = 0;
    }
}

}  // namespace

GldFrameStatus buildGldUplinkFrame(
    const GldFrameBuilderConfig& config,
    const GldFrameBuildInput& input,
    GldNonceProvider nonceProvider,
    void* nonceContext,
    GldBuiltFrame& out) {
    using namespace pgl::protocol;

    clearBuiltFrame(out);

    if (!isValidConfig(config) || nonceProvider == nullptr) {
        return GldFrameStatus::InvalidConfig;
    }

    if (!isValidInput(input)) {
        return GldFrameStatus::InvalidInput;
    }

    const GldPlainPayload plain{
        input.gasClass,
        input.confidence,
        input.batteryMv,
    };

    const bool alarm = isGldAlarm(input.gasClass, input.confidence, config.alarmThreshold);
    const uint8_t recordFlags = makeRecordFlags(alarm, config.externalPower);
    const uint8_t typeFlags = makeGldSensorTypeFlags(alarm, config.externalPower);

    uint8_t nonce[GLD_AES_GCM_NONCE_SIZE]{};
    if (!nonceProvider(nonce, nonceContext)) {
        return GldFrameStatus::NonceFailed;
    }

    GldEncryptedPayload encrypted{};
    const GldCryptoStatus cryptoStatus = encryptGldPayload(
        config.aesKey,
        config.keyId,
        nonce,
        plain,
        config.nodeId,
        input.seq,
        recordFlags,
        encrypted);
    if (cryptoStatus != GldCryptoStatus::Ok) {
        return GldFrameStatus::CryptoFailed;
    }

    const FrameEncodeResult frameResult = encodeAppFrame(
        typeFlags,
        config.nodeId,
        config.chId,
        input.seq,
        encrypted.bytes,
        GLD_ENCRYPTED_PAYLOAD_SIZE,
        out.bytes,
        sizeof(out.bytes),
        STAR_MAX_PAYLOAD);
    if (frameResult.status != FrameStatus::Ok) {
        return GldFrameStatus::FrameEncodeFailed;
    }

    out.alarm = alarm;
    out.typeFlags = typeFlags;
    out.recordFlags = recordFlags;
    out.encrypted = encrypted;
    out.size = frameResult.size;
    return GldFrameStatus::Ok;
}

const char* gldFrameStatusName(GldFrameStatus status) {
    switch (status) {
        case GldFrameStatus::Ok:
            return "Ok";
        case GldFrameStatus::InvalidConfig:
            return "InvalidConfig";
        case GldFrameStatus::InvalidInput:
            return "InvalidInput";
        case GldFrameStatus::NonceFailed:
            return "NonceFailed";
        case GldFrameStatus::CryptoFailed:
            return "CryptoFailed";
        case GldFrameStatus::FrameEncodeFailed:
            return "FrameEncodeFailed";
    }
    return "Unknown";
}

}  // namespace pgl::gld
