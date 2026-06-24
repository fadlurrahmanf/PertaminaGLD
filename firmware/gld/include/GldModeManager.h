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

}  // namespace pgl::gld
