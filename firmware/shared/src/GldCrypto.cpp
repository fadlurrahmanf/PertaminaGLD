#include "GldCrypto.h"

#if defined(ARDUINO_ARCH_ESP32) || defined(ESP_PLATFORM)
#include <mbedtls/gcm.h>
#define PGL_HAS_MBEDTLS_GCM 1
#else
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

}  // namespace pgl::protocol
