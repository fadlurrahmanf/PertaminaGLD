#pragma once
#include <cstdint>
#include <cstring>

namespace pgl::gld {

enum class GldMode : uint8_t {
    INFERENCE = 0,
    DATASET   = 1,
    NULLING   = 2,
};

GldMode     readGldMode();
void        writeGldMode(GldMode mode);
void        switchGldMode(GldMode mode);   // writeGldMode + ESP.restart()
const char* gldModeName(GldMode mode);
GldMode     gldModeFromString(const char* str);  // unknown → INFERENCE

// Persists whether the last inference cycle latched an alarm. Survives the
// ESP.restart() that a mode switch triggers, so Dataset/Nulling boot can
// refuse to run while a previous alarm condition is still unacknowledged.
bool        readGldAlarmLatched();
void        writeGldAlarmLatched(bool active);

}  // namespace pgl::gld
