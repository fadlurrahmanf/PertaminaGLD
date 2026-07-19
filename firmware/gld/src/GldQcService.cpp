#include "GldQcService.h"

#include <Preferences.h>

namespace pgl::gld {

namespace {
constexpr const char* NVS_NAMESPACE = "gld-qc";
constexpr const char* NVS_KEY       = "profile";
}  // namespace

bool saveQcProfile(const GldQcProfile& profile) {
    Preferences prefs;
    if (!prefs.begin(NVS_NAMESPACE, false)) return false;
    const size_t written = prefs.putBytes(NVS_KEY, &profile, sizeof(profile));
    prefs.end();
    return written == sizeof(profile);
}

bool loadQcProfile(GldQcProfile& out) {
    Preferences prefs;
    if (!prefs.begin(NVS_NAMESPACE, true)) return false;
    const size_t read = prefs.getBytes(NVS_KEY, &out, sizeof(out));
    prefs.end();
    return read == sizeof(GldQcProfile) && isQcProfileValid(out);
}

}  // namespace pgl::gld
