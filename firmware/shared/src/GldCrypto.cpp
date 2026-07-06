#include "GldCrypto.h"

#if defined(ARDUINO_ARCH_ESP32) || defined(ESP_PLATFORM)
#include <mbedtls/aes.h>
#include <mbedtls/gcm.h>
#define PGL_HAS_MBEDTLS_AES 1
#define PGL_HAS_MBEDTLS_GCM 1
#else
#define PGL_HAS_MBEDTLS_AES 0
#define PGL_HAS_MBEDTLS_GCM 0
#endif

namespace pgl::protocol {

namespace {

constexpr unsigned int AES_BITS = 128;

void copyBytes(const uint8_t* src, uint8_t* dst, size_t len) {
    for (size_t i = 0; i < len; ++i) {
        dst[i] = src[i];
    }
}

void xorBlock(const uint8_t a[16], const uint8_t b[16], uint8_t out[16]) {
    for (size_t i = 0; i < 16; ++i) {
        out[i] = static_cast<uint8_t>(a[i] ^ b[i]);
    }
}

void leftShiftOneBit(const uint8_t in[16], uint8_t out[16]) {
    uint8_t carry = 0;
    for (int i = 15; i >= 0; --i) {
        const uint8_t nextCarry = (in[i] & 0x80) ? 1 : 0;
        out[i] = static_cast<uint8_t>((in[i] << 1) | carry);
        carry = nextCarry;
    }
}

}  // namespace

GldCryptoStatus encryptGldPayload(
    const uint8_t key[GLD_AES_KEY_SIZE],
    uint8_t keyId,
    const uint8_t nonce[GLD_AES_GCM_NONCE_SIZE],
    const GldPlainPayload& plain,
    uint16_t nodeId,
    uint8_t gldSeq,
    uint8_t recordFlags,
    GldEncryptedPayload& out) {
    uint8_t plaintext[GLD_PLAINTEXT_PAYLOAD_SIZE]{};
    if (!encodeGldPlainPayload(plain, plaintext)) {
        return GldCryptoStatus::InvalidInput;
    }

    uint8_t aad[GLD_AAD_SIZE]{};
    buildGldAad(nodeId, gldSeq, recordFlags, keyId, aad);

    out.bytes[0] = keyId;
    copyBytes(nonce, &out.bytes[GLD_KEY_ID_SIZE], GLD_AES_GCM_NONCE_SIZE);

#if PGL_HAS_MBEDTLS_GCM
    mbedtls_gcm_context ctx;
    mbedtls_gcm_init(&ctx);

    int rc = mbedtls_gcm_setkey(&ctx, MBEDTLS_CIPHER_ID_AES, key, AES_BITS);
    if (rc != 0) {
        mbedtls_gcm_free(&ctx);
        return GldCryptoStatus::CryptoInitFailed;
    }

    rc = mbedtls_gcm_crypt_and_tag(
        &ctx,
        MBEDTLS_GCM_ENCRYPT,
        GLD_AES_GCM_CIPHERTEXT_SIZE,
        nonce,
        GLD_AES_GCM_NONCE_SIZE,
        aad,
        GLD_AAD_SIZE,
        plaintext,
        &out.bytes[GLD_KEY_ID_SIZE + GLD_AES_GCM_NONCE_SIZE],
        GLD_AES_GCM_TAG_SIZE,
        &out.bytes[GLD_KEY_ID_SIZE + GLD_AES_GCM_NONCE_SIZE + GLD_AES_GCM_CIPHERTEXT_SIZE]);

    mbedtls_gcm_free(&ctx);
    return rc == 0 ? GldCryptoStatus::Ok : GldCryptoStatus::CryptoFailed;
#else
    (void)key;
    (void)aad;
    return GldCryptoStatus::UnsupportedPlatform;
#endif
}

GldCryptoStatus decryptGldPayload(
    const uint8_t key[GLD_AES_KEY_SIZE],
    const GldEncryptedPayload& encrypted,
    uint16_t nodeId,
    uint8_t gldSeq,
    uint8_t recordFlags,
    GldPlainPayload& out) {
    const uint8_t keyId = encrypted.bytes[0];
    const uint8_t* nonce = &encrypted.bytes[GLD_KEY_ID_SIZE];
    const uint8_t* ciphertext = &encrypted.bytes[GLD_KEY_ID_SIZE + GLD_AES_GCM_NONCE_SIZE];
    const uint8_t* tag =
        &encrypted.bytes[GLD_KEY_ID_SIZE + GLD_AES_GCM_NONCE_SIZE + GLD_AES_GCM_CIPHERTEXT_SIZE];

    uint8_t aad[GLD_AAD_SIZE]{};
    buildGldAad(nodeId, gldSeq, recordFlags, keyId, aad);

#if PGL_HAS_MBEDTLS_GCM
    uint8_t plaintext[GLD_PLAINTEXT_PAYLOAD_SIZE]{};

    mbedtls_gcm_context ctx;
    mbedtls_gcm_init(&ctx);

    int rc = mbedtls_gcm_setkey(&ctx, MBEDTLS_CIPHER_ID_AES, key, AES_BITS);
    if (rc != 0) {
        mbedtls_gcm_free(&ctx);
        return GldCryptoStatus::CryptoInitFailed;
    }

    rc = mbedtls_gcm_auth_decrypt(
        &ctx,
        GLD_AES_GCM_CIPHERTEXT_SIZE,
        nonce,
        GLD_AES_GCM_NONCE_SIZE,
        aad,
        GLD_AAD_SIZE,
        tag,
        GLD_AES_GCM_TAG_SIZE,
        ciphertext,
        plaintext);

    mbedtls_gcm_free(&ctx);
    if (rc != 0) {
        return GldCryptoStatus::AuthFailed;
    }

    return decodeGldPlainPayload(plaintext, out) ? GldCryptoStatus::Ok : GldCryptoStatus::InvalidInput;
#else
    (void)key;
    return GldCryptoStatus::UnsupportedPlatform;
#endif
}

GldCryptoStatus computeAesCmac128(
    const uint8_t key[GLD_AES_KEY_SIZE],
    const uint8_t* message,
    size_t messageLen,
    uint8_t out[16]) {
    if (key == nullptr || out == nullptr || (messageLen > 0 && message == nullptr)) {
        return GldCryptoStatus::InvalidInput;
    }

#if PGL_HAS_MBEDTLS_AES
    mbedtls_aes_context ctx;
    mbedtls_aes_init(&ctx);

    int rc = mbedtls_aes_setkey_enc(&ctx, key, AES_BITS);
    if (rc != 0) {
        mbedtls_aes_free(&ctx);
        return GldCryptoStatus::CryptoInitFailed;
    }

    uint8_t zero[16]{};
    uint8_t l[16]{};
    rc = mbedtls_aes_crypt_ecb(&ctx, MBEDTLS_AES_ENCRYPT, zero, l);
    if (rc != 0) {
        mbedtls_aes_free(&ctx);
        return GldCryptoStatus::CryptoFailed;
    }

    uint8_t k1[16]{};
    uint8_t k2[16]{};
    leftShiftOneBit(l, k1);
    if (l[0] & 0x80) {
        k1[15] ^= 0x87;
    }
    leftShiftOneBit(k1, k2);
    if (k1[0] & 0x80) {
        k2[15] ^= 0x87;
    }

    const bool complete = messageLen > 0 && (messageLen % 16) == 0;
    const size_t blockCount = complete ? (messageLen / 16) : (messageLen / 16 + 1);
    const size_t lastOffset = (blockCount - 1) * 16;

    uint8_t last[16]{};
    if (complete) {
        copyBytes(&message[lastOffset], last, 16);
        xorBlock(last, k1, last);
    } else {
        const size_t remaining = messageLen - lastOffset;
        if (remaining > 0) {
            copyBytes(&message[lastOffset], last, remaining);
        }
        last[remaining] = 0x80;
        xorBlock(last, k2, last);
    }

    uint8_t x[16]{};
    uint8_t y[16]{};
    for (size_t i = 0; i + 1 < blockCount; ++i) {
        xorBlock(x, &message[i * 16], y);
        rc = mbedtls_aes_crypt_ecb(&ctx, MBEDTLS_AES_ENCRYPT, y, x);
        if (rc != 0) {
            mbedtls_aes_free(&ctx);
            return GldCryptoStatus::CryptoFailed;
        }
    }

    xorBlock(x, last, y);
    rc = mbedtls_aes_crypt_ecb(&ctx, MBEDTLS_AES_ENCRYPT, y, out);
    mbedtls_aes_free(&ctx);
    return rc == 0 ? GldCryptoStatus::Ok : GldCryptoStatus::CryptoFailed;
#else
    (void)key;
    (void)message;
    (void)messageLen;
    return GldCryptoStatus::UnsupportedPlatform;
#endif
}

}  // namespace pgl::protocol
