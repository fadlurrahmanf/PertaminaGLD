#include "GldModeManager.h"
#include <Arduino.h>
#include <Preferences.h>

namespace pgl::gld {

static constexpr const char* NVS_NS  = "gld";
static constexpr const char* NVS_KEY = "mode";

GldMode readGldMode() {
    Preferences prefs;
    prefs.begin(NVS_NS, true);
    const uint8_t val = prefs.getUChar(NVS_KEY, static_cast<uint8_t>(GldMode::INFERENCE));
    prefs.end();
    if (val > static_cast<uint8_t>(GldMode::NULLING)) return GldMode::INFERENCE;
    return static_cast<GldMode>(val);
}

void writeGldMode(GldMode mode) {
    Preferences prefs;
    prefs.begin(NVS_NS, false);
    prefs.putUChar(NVS_KEY, static_cast<uint8_t>(mode));
    prefs.end();
}

void switchGldMode(GldMode mode) {
    writeGldMode(mode);
    ESP.restart();
}

static constexpr const char* NVS_ALARM_KEY = "alarm";

bool readGldAlarmLatched() {
    Preferences prefs;
    prefs.begin(NVS_NS, true);
    const bool val = prefs.getBool(NVS_ALARM_KEY, false);
    prefs.end();
    return val;
}

void writeGldAlarmLatched(bool active) {
    Preferences prefs;
    prefs.begin(NVS_NS, false);
    prefs.putBool(NVS_ALARM_KEY, active);
    prefs.end();
}

const char* gldModeName(GldMode mode) {
    switch (mode) {
        case GldMode::INFERENCE: return "inference";
        case GldMode::DATASET:   return "dataset";
        case GldMode::NULLING:   return "nulling";
        default:                 return "unknown";
    }
}

GldMode gldModeFromString(const char* str) {
    if (str == nullptr) return GldMode::INFERENCE;
    if (strcmp(str, "dataset")   == 0) return GldMode::DATASET;
    if (strcmp(str, "nulling")   == 0) return GldMode::NULLING;
    if (strcmp(str, "running")   == 0) return GldMode::INFERENCE;
    if (strcmp(str, "inference") == 0) return GldMode::INFERENCE;
    return GldMode::INFERENCE;
}

}  // namespace pgl::gld
