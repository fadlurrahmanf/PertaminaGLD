#pragma once

#include <cstdint>

namespace pgl::gld {

constexpr uint8_t QC_PROFILE_VALID_MAGIC = 0xC3;
constexpr uint8_t QC_TIMESTAMP_LEN = 24;

// Per-channel operator QC verdict, persisted on the GLD board itself (NVS)
// so it survives app disconnects and USB cable unplug/replug. A fresh board
// (empty NVS) reports every channel as untested.
struct GldQcProfile {
    uint8_t validMagic;                       // QC_PROFILE_VALID_MAGIC when valid
    uint8_t tested[8];                        // 1 = operator has submitted a QC verdict
    uint8_t passed[8];                        // 1 = pass, 0 = fail (meaningful only if tested[i]==1)
    char    timestamp[8][QC_TIMESTAMP_LEN];   // ISO-8601 string supplied by the app (ESP32 has no RTC)
};

inline bool isQcProfileValid(const GldQcProfile& p) {
    return p.validMagic == QC_PROFILE_VALID_MAGIC;
}

}  // namespace pgl::gld
