#include "GldModelBinding.h"

#include <Preferences.h>

#include <cstring>

namespace pgl::gld {
namespace {

constexpr const char* NVS_NAMESPACE = "gld_model";
constexpr const char* NVS_KEY = "binding";
constexpr uint32_t CHECKSUM_SALT = 0xC35A91E7u;

uint32_t bindingChecksum(const GldModelBinding& binding) {
    return binding.magic ^ (static_cast<uint32_t>(binding.schemaVersion) << 16) ^
           binding.nullingProfileId ^ binding.modelFingerprint ^ CHECKSUM_SALT;
}

uint32_t fnv1aAppend(uint32_t hash, const char* value) {
    if (value == nullptr) return hash;
    while (*value != '\0') {
        hash ^= static_cast<uint8_t>(*value++);
        hash *= 16777619u;
    }
    return hash;
}

}  // namespace

uint32_t modelBindingFingerprint(const char* profileId, const char* scalerProfileId) {
    uint32_t hash = 2166136261u;
    hash = fnv1aAppend(hash, profileId);
    hash ^= static_cast<uint8_t>('|');
    hash *= 16777619u;
    return fnv1aAppend(hash, scalerProfileId);
}

bool isModelBindingValid(const GldModelBinding& binding) {
    return binding.magic == MODEL_BINDING_MAGIC &&
           binding.schemaVersion == MODEL_BINDING_SCHEMA_VERSION &&
           binding.nullingProfileId != 0 &&
           binding.modelFingerprint != 0 &&
           binding.checksum == bindingChecksum(binding);
}

bool saveModelBinding(const GldModelBinding& input) {
    if (!isModelBindingValid(input)) return false;
    Preferences prefs;
    if (!prefs.begin(NVS_NAMESPACE, false)) return false;

    // Invalidate before writing and only publish a valid complete record.
    GldModelBinding invalid{};
    bool ok = prefs.putBytes(NVS_KEY, &invalid, sizeof(invalid)) == sizeof(invalid);
    ok = prefs.putBytes(NVS_KEY, &input, sizeof(input)) == sizeof(input) && ok;
    GldModelBinding verify{};
    ok = prefs.getBytes(NVS_KEY, &verify, sizeof(verify)) == sizeof(verify) &&
         std::memcmp(&verify, &input, sizeof(input)) == 0 && ok;
    prefs.end();
    return ok;
}

bool loadModelBinding(GldModelBinding& out) {
    Preferences prefs;
    if (!prefs.begin(NVS_NAMESPACE, true)) return false;
    const size_t read = prefs.getBytes(NVS_KEY, &out, sizeof(out));
    prefs.end();
    return read == sizeof(out) && isModelBindingValid(out);
}

}  // namespace pgl::gld
