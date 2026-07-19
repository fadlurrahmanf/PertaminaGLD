#pragma once

#include "GldQcProfile.h"

namespace pgl::gld {

// NVS persistence via ESP32 Preferences, separate namespace from the nulling
// profile so QC verdicts and nulling results are independently persisted.
bool saveQcProfile(const GldQcProfile& profile);
bool loadQcProfile(GldQcProfile& out);

}  // namespace pgl::gld
