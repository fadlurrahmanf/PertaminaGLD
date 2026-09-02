#pragma once

#include <cstdint>

namespace pgl::gld {

// Product alarm policy. AUTO is deliberately encoded as zero and is restored
// unconditionally on every boot. MANUAL is a volatile commissioning mode and
// must never be loaded from, or written to, NVS.
enum class GldAlarmControlMode : uint8_t {
    Auto = 0,
    Manual = 1,
};

constexpr bool isValidGldAlarmControlMode(uint8_t raw) {
    return raw == static_cast<uint8_t>(GldAlarmControlMode::Auto) ||
           raw == static_cast<uint8_t>(GldAlarmControlMode::Manual);
}

constexpr const char* gldAlarmControlModeName(GldAlarmControlMode mode) {
    return mode == GldAlarmControlMode::Manual ? "manual" : "auto";
}

// Manual mode suppresses inference-driven physical output, but does not
// suppress the inference alarm itself. This keeps telemetry/radio alarm state
// truthful while allowing an operator to test the external alarm device.
constexpr bool gldPhysicalAlarmCommanded(GldAlarmControlMode mode,
                                         bool inferenceAlarm,
                                         bool manualCommanded) {
    return mode == GldAlarmControlMode::Manual
        ? manualCommanded
        : inferenceAlarm;
}

static_assert(static_cast<uint8_t>(GldAlarmControlMode::Auto) == 0,
              "An erased alarm-mode setting must default to AUTO");
static_assert(!gldPhysicalAlarmCommanded(GldAlarmControlMode::Auto, false, true),
              "AUTO must ignore the manual test command");
static_assert(gldPhysicalAlarmCommanded(GldAlarmControlMode::Auto, true, false),
              "AUTO must follow a valid inference alarm");
static_assert(!gldPhysicalAlarmCommanded(GldAlarmControlMode::Manual, true, false),
              "MANUAL must suppress inference-driven physical output");
static_assert(gldPhysicalAlarmCommanded(GldAlarmControlMode::Manual, false, true),
              "MANUAL must allow operator alarm testing");

}  // namespace pgl::gld
