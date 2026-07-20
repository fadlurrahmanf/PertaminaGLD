#pragma once
#include <cstdint>
#include <cstring>

namespace pgl::gld {

enum class GldMode : uint8_t {
    INFERENCE = 0,
    DATASET   = 1,
    NULLING   = 2,
};

// readGldMode consumes a one-shot boot intent. Dataset/nulling can be requested
// by SET_MODE, but the stored default is immediately returned to INFERENCE so
// the next normal boot always starts in running mode.
GldMode     readGldMode();
void        writeGldMode(GldMode mode);
void        switchGldMode(GldMode mode);   // write one-shot boot intent + ESP.restart()
const char* gldModeName(GldMode mode);
GldMode     gldModeFromString(const char* str);  // unknown → INFERENCE

// Persists whether the last inference cycle latched an alarm. Survives the
// ESP.restart() that a mode switch triggers, so Dataset/Nulling boot can
// refuse to run while a previous alarm condition is still unacknowledged.
bool        readGldAlarmLatched();
void        writeGldAlarmLatched(bool active);

// Service hold is toggled by one debounced CFG-button press/release while the
// GLD is on battery power. It is persisted so an ESP reset during firmware
// upload cannot unexpectedly re-enable the power-latch CLR output.
bool        readGldServiceHold();
void        writeGldServiceHold(bool active);

struct GldPendingAlarm {
    bool active = false;
    uint8_t gasClass = 0;
    uint8_t confidence = 0;
};

// Alarm delivery is retried for a bounded number of attempts per wake. If no
// matching ACK arrives, retain the alarm in NVS for the following wake cycle.
GldPendingAlarm readGldPendingAlarm();
void            writeGldPendingAlarm(const GldPendingAlarm& pending);

}  // namespace pgl::gld
