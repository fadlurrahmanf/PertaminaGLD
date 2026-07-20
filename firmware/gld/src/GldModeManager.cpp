#include "GldModeManager.h"
#include "ProtocolConstants.h"
#include <Arduino.h>
#include <Preferences.h>

namespace pgl::gld {

static constexpr const char* NVS_NS  = "gld";
static constexpr const char* NVS_KEY = "mode";

GldMode readGldMode() {
    Preferences prefs;
    prefs.begin(NVS_NS, false);
    const uint8_t val = prefs.getUChar(NVS_KEY, static_cast<uint8_t>(GldMode::INFERENCE));
    const GldMode mode = val <= static_cast<uint8_t>(GldMode::NULLING)
        ? static_cast<GldMode>(val)
        : GldMode::INFERENCE;
    if (mode != GldMode::INFERENCE || val > static_cast<uint8_t>(GldMode::NULLING)) {
        prefs.putUChar(NVS_KEY, static_cast<uint8_t>(GldMode::INFERENCE));
    }
    prefs.end();
    return mode;
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
static constexpr const char* NVS_SERVICE_HOLD_KEY = "svc_hold";
static constexpr const char* NVS_PENDING_ALARM_KEY = "pending_alarm";
static constexpr const char* NVS_PENDING_GAS_KEY = "pending_gas";
static constexpr const char* NVS_PENDING_CONFIDENCE_KEY = "pending_conf";

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

bool readGldServiceHold() {
    Preferences prefs;
    prefs.begin(NVS_NS, true);
    const bool active = prefs.getBool(NVS_SERVICE_HOLD_KEY, false);
    prefs.end();
    return active;
}

void writeGldServiceHold(bool active) {
    Preferences prefs;
    prefs.begin(NVS_NS, false);
    prefs.putBool(NVS_SERVICE_HOLD_KEY, active);
    prefs.end();
}

GldPendingAlarm readGldPendingAlarm() {
    Preferences prefs;
    prefs.begin(NVS_NS, true);
    GldPendingAlarm pending{};
    pending.active = prefs.getBool(NVS_PENDING_ALARM_KEY, false);
    pending.gasClass = prefs.getUChar(NVS_PENDING_GAS_KEY, 0);
    pending.confidence = prefs.getUChar(NVS_PENDING_CONFIDENCE_KEY, 0);
    prefs.end();

    if (!pending.active) {
        pending.gasClass = 0;
        pending.confidence = 0;
        return pending;
    }

    if (pending.gasClass == pgl::protocol::GLD_GAS_CLEAR ||
        pending.confidence < pgl::protocol::GLD_LEL_THRESHOLD_PERCENT ||
        pending.gasClass > pgl::protocol::GLD_GAS_ANOMALY ||
        pending.confidence > 100) {
        pending = {};
        writeGldPendingAlarm(pending);
    }
    return pending;
}

void writeGldPendingAlarm(const GldPendingAlarm& pending) {
    Preferences prefs;
    prefs.begin(NVS_NS, false);
    if (pending.active) {
        prefs.putUChar(NVS_PENDING_GAS_KEY, pending.gasClass);
        prefs.putUChar(NVS_PENDING_CONFIDENCE_KEY, pending.confidence);
    }
    // Write the validity flag last so a reset cannot expose half-written data.
    prefs.putBool(NVS_PENDING_ALARM_KEY, pending.active);
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
