#pragma once

#include <cstdint>

namespace pgl::gld {

// Explicit operator approval that binds one complete Nulling profile to the
// exact compiled model/scaler pair. It is intentionally separate from both
// the Nulling profile and runtime app configuration.
constexpr uint32_t MODEL_BINDING_MAGIC = 0x50474C4Du; // "PGLM"
constexpr uint16_t MODEL_BINDING_SCHEMA_VERSION = 1;

struct GldModelBinding {
    uint32_t magic = 0;
    uint16_t schemaVersion = 0;
    uint8_t nullingProfileId = 0;
    uint8_t reserved = 0;
    uint32_t modelFingerprint = 0;
    uint32_t checksum = 0;
};

uint32_t modelBindingFingerprint(const char* profileId, const char* scalerProfileId);
bool isModelBindingValid(const GldModelBinding& binding);
bool saveModelBinding(const GldModelBinding& binding);
bool loadModelBinding(GldModelBinding& out);

}  // namespace pgl::gld
