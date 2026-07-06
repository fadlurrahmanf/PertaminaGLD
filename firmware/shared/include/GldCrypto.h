#pragma once

#include <cstddef>
#include <cstdint>

#include "GldPayload.h"
#include "ProtocolConstants.h"

namespace pgl::protocol {

constexpr size_t GLD_AES_KEY_SIZE = 16;

enum class GldCryptoStatus : uint8_t {
    Ok = 0,
    InvalidInput,
    UnsupportedPlatform,
    CryptoInitFailed,
    CryptoFailed,
    AuthFailed,
};

struct GldEncryptedPayload {
    uint8_t bytes[GLD_ENCRYPTED_PAYLOAD_SIZE];
};

GldCryptoStatus encryptGldPayload(
    const uint8_t key[GLD_AES_KEY_SIZE],
    uint8_t keyId,
    const uint8_t nonce[GLD_AES_GCM_NONCE_SIZE],
    const GldPlainPayload& plain,
    uint16_t nodeId,
    uint8_t gldSeq,
    uint8_t recordFlags,
    GldEncryptedPayload& out);

GldCryptoStatus decryptGldPayload(
    const uint8_t key[GLD_AES_KEY_SIZE],
    const GldEncryptedPayload& encrypted,
    uint16_t nodeId,
    uint8_t gldSeq,
    uint8_t recordFlags,
    GldPlainPayload& out);

GldCryptoStatus computeAesCmac128(
    const uint8_t key[GLD_AES_KEY_SIZE],
    const uint8_t* message,
    size_t messageLen,
    uint8_t out[16]);

}  // namespace pgl::protocol
