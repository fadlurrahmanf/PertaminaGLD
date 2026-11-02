#pragma once

#if defined(PGL_GLD_DATASET_WIFI) && PGL_GLD_DATASET_WIFI
#include <cstdint>

namespace pgl::gld::datasetwifi {

// The sampler owns ADS access after begin(). No network calls belong in capture.
struct Sample {
    float voltage[8]{};
    uint8_t gain[8]{};
    uint8_t status[8]{};
    uint32_t timestampMs = 0;
    uint32_t scanEndMs = 0;
};

using Capture = bool (*)(Sample& sample);
using Ready = bool (*)();

bool begin(const char* deviceId, uint8_t nullingProfileId,
           Ready ready, Capture capture);
void poll();

}  // namespace pgl::gld::datasetwifi
#endif
