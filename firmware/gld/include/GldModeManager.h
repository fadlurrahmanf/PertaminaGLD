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

}  // namespace pgl::gld
